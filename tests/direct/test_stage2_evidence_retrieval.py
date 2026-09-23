import pytest

from helpers import (
    CONTRACT_PATH, ONE_GEN, create_constitution_stage2, file_claim, freeze_evidence, fund,
    issue, respond, submit_evidence,
)


def _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    return contract, manufacturer, holder, claim_id


def test_static_get_success(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    direct_vm.mock_web(r"https://docs\.genlayer\.com/warranty-page", {"status": 200, "body": "Widget failed under normal use."})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/warranty-page", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == "AVAILABLE"
    assert ev["available"] is True
    assert ev["extracted_content"] == "Widget failed under normal use."


def test_rendered_page_success(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    direct_vm.mock_web(r"https://docs\.genlayer\.com/js-page", {"status": 200, "body": "Rendered widget defect notice."})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/js-page", "MANUFACTURER_PAGE_RENDERED")
    assert contract.get_evidence(evidence_id)["retrieval_method"] == "RENDER"
    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == "AVAILABLE"
    assert ev["extracted_content"] == "Rendered widget defect notice."


def test_404_is_fetch_failed_not_not_covered(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    direct_vm.mock_web(r"https://docs\.genlayer\.com/missing", {"status": 404, "body": ""})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/missing", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == "FETCH_FAILED"
    assert ev["available"] is False
    # Critically: nothing about the claim's own status/outcome is touched by a failed fetch.
    assert contract.get_claim(claim_id)["status"] == "EVIDENCE_FROZEN"


def test_server_error_is_fetch_failed(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    direct_vm.mock_web(r"https://docs\.genlayer\.com/error", {"status": 500, "body": ""})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/error", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    assert contract.get_evidence(evidence_id)["retrieval_status"] == "FETCH_FAILED"


def test_empty_body_is_insufficient(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    direct_vm.mock_web(r"https://docs\.genlayer\.com/empty", {"status": 200, "body": ""})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/empty", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == "INSUFFICIENT"
    assert ev["available"] is False


def test_whitespace_only_body_is_insufficient(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    direct_vm.mock_web(r"https://docs\.genlayer\.com/blank", {"status": 200, "body": "   \n\t  "})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/blank", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    assert contract.get_evidence(evidence_id)["retrieval_status"] == "INSUFFICIENT"


def test_unreachable_host_is_unavailable(direct_deploy, direct_vm, direct_accounts):
    """No mock registered at all for this URL - direct-mode's strict-mock-not-found path is
    NOT what a real GenVM network-level failure looks like, but it exercises the same
    leader_fn exception -> UNAVAILABLE branch our code defines for a real connection failure."""
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/unreachable-nomock", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == "UNAVAILABLE"
    assert ev["available"] is False


def test_oversized_content_is_bounded(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    huge = "A" * 50_000
    direct_vm.mock_web(r"https://docs\.genlayer\.com/huge", {"status": 200, "body": huge})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/huge", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == "AVAILABLE"
    assert len(ev["extracted_content"]) == 2000  # _MAX_EXTRACT_LEN


def test_ineligible_evidence_never_retrieved(direct_deploy, direct_vm, direct_accounts):
    """An INELIGIBLE record must never even attempt retrieval - freeze_evidence skips it
    entirely, leaving retrieval_status empty."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id, source_policy="manufacturer.example")
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")

    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://evil.example/page", "RECEIPT")
    assert contract.get_evidence(evidence_id)["eligibility"] == "INELIGIBLE"

    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == ""
    assert ev["frozen_at"] == 0
    assert ev["available"] is False


def test_multiple_evidence_records_each_processed_independently(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts)
    direct_vm.mock_web(r"https://docs\.genlayer\.com/one", {"status": 200, "body": "First piece of evidence."})
    direct_vm.mock_web(r"https://docs\.genlayer\.com/two", {"status": 404, "body": ""})
    e1 = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/one", "RECEIPT")
    e2 = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/two", "RECEIPT")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    assert contract.get_evidence(e1)["retrieval_status"] == "AVAILABLE"
    assert contract.get_evidence(e2)["retrieval_status"] == "FETCH_FAILED"
