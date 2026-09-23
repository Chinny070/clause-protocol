import pytest

from helpers import CONTRACT_PATH, ONE_GEN, create_constitution, fund, issue, make_commitment_hex


def test_valid_issuance_fields(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    from genlayer.py.types import Address

    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    now_before = int(contract.now())
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    now_after = int(contract.now())

    p = contract.get_passport(warranty_id)
    assert p["program_id"] == program_id
    assert p["constitution_id"] == constitution_id
    assert p["manufacturer"] == Address(manufacturer).as_hex
    assert p["holder"] == Address(holder).as_hex
    assert p["status"] == "ACTIVE"
    assert now_before <= p["registered_at"] <= now_after
    assert p["max_deterministic_remedy"] == 5 * ONE_GEN
    assert p["reservation_id"] > 0


def test_unique_warranty_ids(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 100 * ONE_GEN)

    ids = set()
    for i in range(5):
        wid = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=1 * ONE_GEN, commitment_seed=i + 1)
        assert wid not in ids
        ids.add(wid)
    assert len(ids) == 5


def test_reservation_created_and_linked(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    passport = contract.get_passport(warranty_id)
    reservation = contract.get_reservation(passport["reservation_id"])
    assert reservation["warranty_id"] == warranty_id
    assert reservation["amount"] == 5 * ONE_GEN
    assert reservation["status"] == "ACTIVE"


def test_insufficient_pool_capacity_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 1 * ONE_GEN)

    with pytest.raises(Exception):
        issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=2 * ONE_GEN)


def test_issuance_against_unknown_program_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    with pytest.raises(Exception):
        contract.issue_warranty(
            program_id=999,
            constitution_id=1,
            holder=holder,
            product_model_id="X",
            product_commitment_hex=make_commitment_hex(1),
            coverage_start=0,
            coverage_end=1000,
            max_deterministic_remedy=1 * ONE_GEN,
        )


def test_issuance_against_unknown_constitution_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    with pytest.raises(Exception):
        issue(contract, direct_vm, program_id, 999, manufacturer, holder, max_remedy=1 * ONE_GEN)


def test_issuance_with_constitution_from_another_program_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_a = contract.create_program("Acme A")
    program_b = contract.create_program("Acme B")
    constitution_a = create_constitution(contract, program_a)
    fund(contract, direct_vm, program_b, manufacturer, 10 * ONE_GEN)

    with pytest.raises(Exception):
        issue(contract, direct_vm, program_b, constitution_a, manufacturer, holder, max_remedy=1 * ONE_GEN)


def test_malformed_product_commitment_rejected_short(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    with pytest.raises(Exception):
        contract.issue_warranty(
            program_id=program_id,
            constitution_id=constitution_id,
            holder=holder,
            product_model_id="X",
            product_commitment_hex="ab12",  # too short
            coverage_start=0,
            coverage_end=1000,
            max_deterministic_remedy=1 * ONE_GEN,
        )


def test_malformed_product_commitment_rejected_non_hex(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    with pytest.raises(Exception):
        contract.issue_warranty(
            program_id=program_id,
            constitution_id=constitution_id,
            holder=holder,
            product_model_id="X",
            product_commitment_hex="z" * 64,  # not valid hex
            coverage_start=0,
            coverage_end=1000,
            max_deterministic_remedy=1 * ONE_GEN,
        )


def test_zero_max_remedy_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    with pytest.raises(Exception):
        issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=0)


def test_issuance_against_paused_program_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    contract.pause_program(program_id)

    with pytest.raises(Exception):
        issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=1 * ONE_GEN)


def test_issuance_against_retired_program_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    contract.retire_program(program_id)

    with pytest.raises(Exception):
        issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=1 * ONE_GEN)


def test_privacy_no_raw_serial_exposed(direct_deploy, direct_vm, direct_accounts):
    """The passport view exposes only the commitment hash, never a raw serial number -
    docs/DATA_MODEL.md privacy-preserving requirement."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=1 * ONE_GEN)

    p = contract.get_passport(warranty_id)
    assert set(p.keys()) == {
        "warranty_id", "program_id", "manufacturer", "holder", "product_model_id",
        "product_commitment", "registered_at", "coverage_start", "coverage_end",
        "constitution_id", "constitution_version", "constitution_fingerprint",
        "max_deterministic_remedy", "reservation_id", "status",
    }
    assert len(p["product_commitment"]) == 64  # 32-byte hex digest, not a raw serial
