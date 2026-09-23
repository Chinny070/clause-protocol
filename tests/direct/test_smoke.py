from helpers import CONTRACT_PATH, ONE_GEN, create_constitution, fund, issue


def test_deploy_and_basic_lifecycle(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    holder = direct_accounts[1]

    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)

    # genlayer is only importable after direct_deploy has run the SDK loader.
    from genlayer.py.types import Address

    program_id = contract.create_program("Acme Widgets")
    assert program_id == 1

    constitution_id = create_constitution(contract, program_id)
    assert constitution_id == 1

    c = contract.get_constitution(constitution_id)
    assert c["is_frozen"] is False
    assert c["version"] == "2026.1"

    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    pool = contract.get_pool(program_id)
    assert pool["total_balance"] == 10 * ONE_GEN
    assert pool["available_balance"] == 10 * ONE_GEN

    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    assert warranty_id == 1

    c2 = contract.get_constitution(constitution_id)
    assert c2["is_frozen"] is True

    pool2 = contract.get_pool(program_id)
    assert pool2["reserved_liability"] == 5 * ONE_GEN
    assert pool2["available_balance"] == 5 * ONE_GEN

    passport = contract.get_passport(warranty_id)
    assert passport["status"] == "ACTIVE"
    assert passport["holder"] == Address(holder).as_hex
    assert passport["manufacturer"] == Address(manufacturer).as_hex
