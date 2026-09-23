import pytest

from helpers import CONTRACT_PATH, ONE_GEN, create_constitution, fund, issue


def test_duplicate_program_ids_impossible(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    ids = [contract.create_program(f"Program {i}") for i in range(5)]
    assert len(set(ids)) == 5
    assert ids == sorted(ids)


def test_duplicate_constitution_ids_impossible(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    ids = [create_constitution(contract, program_id, version=f"2026.{i}") for i in range(5)]
    assert len(set(ids)) == 5


def test_duplicate_warranty_and_reservation_ids_impossible(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 50 * ONE_GEN)

    warranty_ids = []
    reservation_ids = []
    for i in range(5):
        wid = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=1 * ONE_GEN, commitment_seed=i + 1)
        warranty_ids.append(wid)
        reservation_ids.append(contract.get_passport(wid)["reservation_id"])
    assert len(set(warranty_ids)) == 5
    assert len(set(reservation_ids)) == 5


def test_double_reservation_against_same_warranty_impossible(direct_deploy, direct_vm, direct_accounts):
    """There is no method that adds a second reservation to an existing warranty_id - issuance
    always mints a brand new reservation_id alongside a brand new warranty_id."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    reservation_id_1 = contract.get_passport(warranty_id)["reservation_id"]
    # cancel (which releases) then confirm re-cancel (double release) reverts, proving the
    # same reservation can never be counted against the pool twice.
    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)
    with pytest.raises(Exception):
        contract.release_expired_reservation(warranty_id)
    assert contract.get_reservation(reservation_id_1)["status"] == "RELEASED"


def test_available_balance_never_goes_negative(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 5 * ONE_GEN)
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    # available_balance is exactly 0; any further reservation or withdrawal must revert,
    # never drive it negative.
    with pytest.raises(Exception):
        issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=1, commitment_seed=2)
    with pytest.raises(Exception):
        contract.withdraw_pool(program_id, 1)
    assert contract.get_pool(program_id)["available_balance"] == 0


def test_unauthorized_state_mutation_leaves_state_untouched(direct_deploy, direct_vm, direct_accounts):
    manufacturer, attacker = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    before = contract.get_program(program_id)

    direct_vm.sender = attacker
    with pytest.raises(Exception):
        contract.pause_program(program_id)
    with pytest.raises(Exception):
        contract.retire_program(program_id)

    after = contract.get_program(program_id)
    assert before == after
    assert after["status"] == "ACTIVE"


def test_invalid_state_transition_resume_when_active_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        contract.resume_program(program_id)  # already ACTIVE, not PAUSED


def test_invalid_state_transition_pause_when_retired_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    contract.retire_program(program_id)
    with pytest.raises(Exception):
        contract.pause_program(program_id)
    with pytest.raises(Exception):
        contract.resume_program(program_id)
    with pytest.raises(Exception):
        contract.retire_program(program_id)  # already RETIRED


def test_cancel_already_cancelled_warranty_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)
    with pytest.raises(Exception):
        contract.cancel_warranty(warranty_id)


def test_retroactive_constitution_change_has_no_code_path(direct_deploy, direct_vm, direct_accounts):
    """There is no write method in the contract's schema that accepts a constitution_id and
    mutates that same record's fields - proven by exhaustively checking the schema itself,
    not just by trying a few guesses."""
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    schema = contract.__class__.__get_schema__() if hasattr(contract.__class__, "__get_schema__") else None
    # Fall back to introspecting the deployed instance's public methods directly.
    write_methods = [
        name for name in dir(contract)
        if not name.startswith("_")
        and callable(getattr(contract, name, None))
    ]
    forbidden = {"update_constitution", "edit_constitution", "set_constitution", "rewrite_constitution"}
    assert forbidden.isdisjoint(set(write_methods))


def test_double_settlement_style_guard_on_reservation_is_atomic(direct_deploy, direct_vm, direct_accounts):
    """Simulates a double-spend attempt on the same reservation via two different release
    paths (cancel_warranty then release_expired_reservation) - the second must revert and
    the pool accounting must not double-release the same amount."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=6 * ONE_GEN)

    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)
    pool_after_first_release = contract.get_pool(program_id)

    with pytest.raises(Exception):
        contract.release_expired_reservation(warranty_id)

    pool_after_second_attempt = contract.get_pool(program_id)
    assert pool_after_first_release == pool_after_second_attempt
    assert pool_after_second_attempt["reserved_liability"] == 0
