import pytest

from helpers import CONTRACT_PATH, ONE_GEN, create_constitution, fund, issue


def test_non_manufacturer_cannot_pause_program(direct_deploy, direct_vm, direct_accounts):
    manufacturer, attacker = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")

    direct_vm.sender = attacker
    with pytest.raises(Exception):
        contract.pause_program(program_id)


def test_non_manufacturer_cannot_retire_or_resume_program(direct_deploy, direct_vm, direct_accounts):
    manufacturer, attacker = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")

    direct_vm.sender = attacker
    with pytest.raises(Exception):
        contract.retire_program(program_id)
    with pytest.raises(Exception):
        contract.resume_program(program_id)


def test_non_manufacturer_cannot_create_constitution(direct_deploy, direct_vm, direct_accounts):
    manufacturer, attacker = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")

    direct_vm.sender = attacker
    with pytest.raises(Exception):
        create_constitution(contract, program_id)


def test_non_manufacturer_cannot_withdraw_pool(direct_deploy, direct_vm, direct_accounts):
    manufacturer, attacker = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    direct_vm.sender = attacker
    with pytest.raises(Exception):
        contract.withdraw_pool(program_id, 1 * ONE_GEN)


def test_non_manufacturer_cannot_issue_warranty(direct_deploy, direct_vm, direct_accounts):
    manufacturer, attacker, holder = direct_accounts[0], direct_accounts[1], direct_accounts[2]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    direct_vm.sender = attacker
    with pytest.raises(Exception):
        issue(contract, direct_vm, program_id, constitution_id, attacker, holder)


def test_non_party_cannot_cancel_warranty(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder, stranger = direct_accounts[0], direct_accounts[1], direct_accounts[2]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder)

    direct_vm.sender = stranger
    with pytest.raises(Exception):
        contract.cancel_warranty(warranty_id)


def test_holder_can_cancel_own_warranty(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder)

    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)
    assert contract.get_passport(warranty_id)["status"] == "CANCELLED"


def test_manufacturer_can_cancel_warranty(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder)

    direct_vm.sender = manufacturer
    contract.cancel_warranty(warranty_id)
    assert contract.get_passport(warranty_id)["status"] == "CANCELLED"


def test_unauthorized_pool_funding_ownership_is_irrelevant(direct_deploy, direct_vm, direct_accounts):
    """fund_pool is intentionally permissionless (anyone may top up a manufacturer's pool -
    docs/ECONOMIC_INVARIANTS.md never restricts deposits), unlike withdraw_pool."""
    manufacturer, stranger = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")

    direct_vm.sender = stranger
    direct_vm.value = 1 * ONE_GEN
    try:
        contract.fund_pool(program_id)
    finally:
        direct_vm.value = 0
    assert contract.get_pool(program_id)["total_balance"] == 1 * ONE_GEN
