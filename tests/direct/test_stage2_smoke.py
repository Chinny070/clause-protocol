from helpers import (
    CONTRACT_PATH,
    ONE_GEN,
    create_constitution_stage2,
    file_claim,
    fund,
    issue,
    freeze_evidence,
    respond,
    submit_evidence,
)


def test_full_claim_and_evidence_lifecycle(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)

    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    claim = contract.get_claim(claim_id)
    assert claim["status"] == "RESPONSE_WINDOW"
    assert claim["constitution_id"] == constitution_id

    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    assert contract.get_claim(claim_id)["status"] == "DISPUTED"

    direct_vm.mock_web(r"https://docs\.genlayer\.com/evidence", {"status": 200, "body": "The widget was defective on arrival."})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/evidence", "RECEIPT")
    ev_before = contract.get_evidence(evidence_id)
    assert ev_before["eligibility"] == "ELIGIBLE"
    assert ev_before["retrieval_status"] == ""

    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev_after = contract.get_evidence(evidence_id)
    assert ev_after["retrieval_status"] == "AVAILABLE"
    assert ev_after["available"] is True
    assert "defective" in ev_after["extracted_content"]
    assert ev_after["fingerprint"] != ""

    claim_after = contract.get_claim(claim_id)
    assert claim_after["status"] == "EVIDENCE_FROZEN"
    assert claim_after["evidence_frozen_at"] > 0
