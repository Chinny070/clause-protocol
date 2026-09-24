"""Regression for a bug the real simulator exposed (Stage 2.5): freeze_evidence built its
leader_fn/validator_fn as closures over loop variables, so a validator replayed AFTER the
loop (which is what glsim, and any faithful runtime, does) re-fetched the LAST record's URL
instead of its own. gltest-direct never runs validators automatically, so it was invisible
until every captured validator was replayed explicitly via direct_vm.run_validator()."""
from helpers import (
    CONTRACT_PATH, ONE_GEN, create_constitution_stage2, file_claim, freeze_evidence, fund,
    issue, respond, submit_evidence,
)


def test_every_captured_validator_agrees_with_its_own_leader_result(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")

    direct_vm.mock_web(r"https://docs\.genlayer\.com/one", {"status": 200, "body": "First page content."})
    direct_vm.mock_web(r"https://docs\.genlayer\.com/two", {"status": 404, "body": ""})
    direct_vm.mock_web(r"https://docs\.genlayer\.com/three", {"status": 200, "body": "Third page content."})
    for path in ("one", "two", "three"):
        submit_evidence(contract, direct_vm, claim_id, holder, f"https://docs.genlayer.com/{path}", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)

    # One captured (leader_result, leader_fn, validator_fn) per processed record, in order.
    for index in range(3):
        assert direct_vm.run_validator(index=index) is True, f"validator #{index} disagreed with its own leader result"
