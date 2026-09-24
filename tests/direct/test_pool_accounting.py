import pytest

from helpers import CONTRACT_PATH, ONE_GEN, create_constitution, fund, issue


def test_deposit_increases_available_capacity(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")

    fund(contract, direct_vm, program_id, manufacturer, 7 * ONE_GEN)
    pool = contract.get_pool(program_id)
    assert pool["total_balance"] == 7 * ONE_GEN
    assert pool["reserved_liability"] == 0
    assert pool["available_balance"] == 7 * ONE_GEN


def test_zero_value_fund_pool_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        contract.fund_pool(program_id)  # direct_vm.value defaults to 0


def test_issue_warranty_increases_reservation(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=3 * ONE_GEN)
    pool = contract.get_pool(program_id)
    assert pool["reserved_liability"] == 3 * ONE_GEN
    assert pool["available_balance"] == 7 * ONE_GEN


def test_multiple_warranties_accumulate_reservations(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=3 * ONE_GEN, commitment_seed=1)
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=4 * ONE_GEN, commitment_seed=2)
    pool = contract.get_pool(program_id)
    assert pool["reserved_liability"] == 7 * ONE_GEN
    assert pool["available_balance"] == 3 * ONE_GEN


def test_withdraw_only_unreserved_balance(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=6 * ONE_GEN)

    direct_vm.sender = manufacturer
    contract.withdraw_pool(program_id, 4 * ONE_GEN)  # exactly available
    pool = contract.get_pool(program_id)
    assert pool["total_balance"] == 6 * ONE_GEN
    assert pool["reserved_liability"] == 6 * ONE_GEN
    assert pool["available_balance"] == 0


def test_withdraw_more_than_available_reverts(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=6 * ONE_GEN)

    with pytest.raises(Exception):
        contract.withdraw_pool(program_id, 5 * ONE_GEN)  # only 4 available

    # state must be unchanged after the reverted attempt
    pool = contract.get_pool(program_id)
    assert pool["total_balance"] == 10 * ONE_GEN
    assert pool["reserved_liability"] == 6 * ONE_GEN


def test_withdraw_reserved_funds_reverts_even_at_full_pool(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 5 * ONE_GEN)
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    with pytest.raises(Exception):
        contract.withdraw_pool(program_id, 1)  # available_balance is exactly 0


def test_release_expired_reservation_frees_capacity(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 100,
    )

    direct_vm.warp(_iso(now + 200 + 30 * 24 * 3600))  # past coverage_end AND the 30-day claim-deadline grace  # past coverage_end
    contract.release_expired_reservation(warranty_id)

    pool = contract.get_pool(program_id)
    assert pool["reserved_liability"] == 0
    assert pool["available_balance"] == 10 * ONE_GEN
    assert contract.get_passport(warranty_id)["status"] == "EXPIRED"


def test_new_warranty_after_release_succeeds(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 6 * ONE_GEN)

    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 100, commitment_seed=1,
    )
    direct_vm.warp(_iso(now + 200 + 30 * 24 * 3600))  # past coverage_end AND the 30-day claim-deadline grace
    contract.release_expired_reservation(warranty_id)

    # A fresh warranty should now succeed against the freed capacity.
    new_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now + 200, coverage_end=now + 400, commitment_seed=2,
    )
    assert new_id != warranty_id
    pool = contract.get_pool(program_id)
    assert pool["reserved_liability"] == 6 * ONE_GEN


def test_double_release_reverts(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 100,
    )
    direct_vm.warp(_iso(now + 200 + 30 * 24 * 3600))  # past coverage_end AND the 30-day claim-deadline grace
    contract.release_expired_reservation(warranty_id)

    with pytest.raises(Exception):
        contract.release_expired_reservation(warranty_id)


def test_release_before_expiry_reverts(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=6 * ONE_GEN)

    with pytest.raises(Exception):
        contract.release_expired_reservation(warranty_id)


def test_cancel_releases_reservation(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=6 * ONE_GEN)

    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)

    pool = contract.get_pool(program_id)
    assert pool["reserved_liability"] == 0
    assert pool["available_balance"] == 10 * ONE_GEN
    reservation = contract.get_reservation(contract.get_passport(warranty_id)["reservation_id"])
    assert reservation["status"] == "RELEASED"


def test_conservation_across_full_sequence(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)

    fund(contract, direct_vm, program_id, manufacturer, 20 * ONE_GEN)
    w1 = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN, commitment_seed=1)
    w2 = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN, commitment_seed=2)

    pool = contract.get_pool(program_id)
    assert pool["total_balance"] - pool["reserved_liability"] == pool["available_balance"]
    assert pool["reserved_liability"] == 10 * ONE_GEN

    direct_vm.sender = manufacturer
    contract.withdraw_pool(program_id, 3 * ONE_GEN)
    pool = contract.get_pool(program_id)
    assert pool["total_balance"] == 17 * ONE_GEN
    assert pool["total_balance"] - pool["reserved_liability"] == pool["available_balance"]

    direct_vm.sender = holder
    contract.cancel_warranty(w1)
    pool = contract.get_pool(program_id)
    assert pool["reserved_liability"] == 5 * ONE_GEN
    assert pool["total_balance"] - pool["reserved_liability"] == pool["available_balance"]

    fund(contract, direct_vm, program_id, manufacturer, 2 * ONE_GEN)
    pool = contract.get_pool(program_id)
    assert pool["total_balance"] == 19 * ONE_GEN
    assert pool["total_balance"] - pool["reserved_liability"] == pool["available_balance"]


def _iso(unix_seconds: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(unix_seconds, tz=datetime.timezone.utc).isoformat()
