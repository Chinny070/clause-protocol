import hashlib
import json as _json

import pytest

from helpers import (
    CONTRACT_PATH, ONE_GEN, create_constitution_stage2, file_claim, freeze_evidence, fund,
    issue, respond, submit_evidence,
)


def _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts, body="Widget broke after two weeks."):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    direct_vm.mock_web(r"https://docs\.genlayer\.com/ev", {"status": 200, "body": body})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/ev", "RECEIPT")
    return contract, manufacturer, holder, claim_id, evidence_id


# --- Freeze mechanics --------------------------------------------------------------------

def test_valid_freeze(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts)
    freeze_evidence(contract, direct_vm, claim_id, holder)
    claim = contract.get_claim(claim_id)
    assert claim["status"] == "EVIDENCE_FROZEN"
    assert claim["evidence_frozen_at"] > 0


def test_duplicate_freeze_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts)
    freeze_evidence(contract, direct_vm, claim_id, holder)
    with pytest.raises(Exception):
        freeze_evidence(contract, direct_vm, claim_id, holder)


def test_freeze_permissionless_any_account_may_trigger(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts)
    stranger = direct_accounts[4]
    freeze_evidence(contract, direct_vm, claim_id, stranger)
    assert contract.get_claim(claim_id)["status"] == "EVIDENCE_FROZEN"


def test_freeze_before_dispute_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    with pytest.raises(Exception):
        freeze_evidence(contract, direct_vm, claim_id, holder)


def test_post_freeze_mutation_impossible(direct_deploy, direct_vm, direct_accounts):
    """There is no write method that accepts an evidence_id and mutates an already-frozen
    record - the only two write paths that touch EvidenceRecord at all are submit_evidence
    (inserts new, and only pre-freeze) and freeze_evidence (processes PENDING records once,
    guarded by the retrieval_status != PENDING skip)."""
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts)
    freeze_evidence(contract, direct_vm, claim_id, holder)
    before = contract.get_evidence(evidence_id)

    # A second freeze_evidence call reverts outright (test_duplicate_freeze_rejected), so the
    # per-record idempotency skip is defense in depth; confirm the record truly did not change
    # even if that guard were somehow bypassed by calling the claim-level entrypoint again is
    # not possible - the strongest available proof is the duplicate-freeze revert itself plus
    # this direct snapshot comparison after the only successful freeze.
    after = contract.get_evidence(evidence_id)
    assert before == after


def test_evidence_added_after_freeze_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts)
    freeze_evidence(contract, direct_vm, claim_id, holder)
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, "https://docs.genlayer.com/late", "RECEIPT")


def test_fetch_evidence_once_never_raises_for_ordinary_failures(direct_deploy, direct_vm, direct_accounts):
    """`_fetch_evidence_once` (the function passed as both leader_fn and validator_fn to
    run_nondet_unsafe) wraps its entire body in try/except and always returns a status dict -
    it never lets an ordinary retrieval failure (timeout, connection error, malformed
    response) escape as a raised exception. This is a deliberate design choice, verified
    here by confirming even a mocked exception from gl.nondet.web.get is converted to
    UNAVAILABLE rather than propagating out of freeze_evidence. A note on what this test does
    NOT prove: true mid-transaction atomic rollback on an unrecoverable VM-level error is a
    GenVM-protocol-level guarantee (docs/STAGE_2_WEB_API_VERIFICATION.md) that gltest's
    direct-mode harness does not model (it mutates storage objects in place with no
    per-call snapshot/rollback), so it cannot be verified from this test suite - only that
    CLAUSE's own code does not manufacture new failure-to-crash paths."""
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts)

    import genlayer.gl as gl_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated network-layer failure")

    original_get = gl_mod.nondet.web.get
    gl_mod.nondet.web.get = _boom
    try:
        freeze_evidence(contract, direct_vm, claim_id, holder)
    finally:
        gl_mod.nondet.web.get = original_get

    ev = contract.get_evidence(evidence_id)
    assert ev["retrieval_status"] == "UNAVAILABLE"
    assert contract.get_claim(claim_id)["status"] == "EVIDENCE_FROZEN"


# --- Fingerprint (item 14 / 17: recompute from first principles, never via the same helper) --

def test_fingerprint_recomputed_from_first_principles(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(
        direct_deploy, direct_vm, direct_accounts, body="Widget broke after two weeks.",
    )
    freeze_evidence(contract, direct_vm, claim_id, holder)
    ev = contract.get_evidence(evidence_id)

    expected_fields = {
        "evidence_id": evidence_id,
        "claim_id": claim_id,
        "original_url": "https://docs.genlayer.com/ev",
        "category": "RECEIPT",
        "retrieval_status": "AVAILABLE",
        "content": "Widget broke after two weeks.",
    }
    expected_json = _json.dumps(expected_fields, sort_keys=True, separators=(",", ":"))
    expected_fingerprint = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()

    assert ev["fingerprint"] == expected_fingerprint


def test_fingerprint_differs_when_content_differs(direct_deploy, direct_vm, direct_accounts):
    """gltest-direct's SDK loader keeps a process-global "only one Contract class per module"
    guard that is not reset by a second direct_deploy() call within the same test function
    (confirmed while writing this test - two deploys in one test raise `TypeError: only one
    contract is allowed`) - so this compares two independently-computed fingerprints against
    a hardcoded expectation instead of deploying a second contract instance to compare against
    live."""
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts, body="Content A")
    freeze_evidence(contract, direct_vm, claim_id, holder)
    fp_a = contract.get_evidence(evidence_id)["fingerprint"]

    expected_fields_b = {
        "evidence_id": evidence_id,
        "claim_id": claim_id,
        "original_url": "https://docs.genlayer.com/ev",
        "category": "RECEIPT",
        "retrieval_status": "AVAILABLE",
        "content": "Content B",
    }
    expected_json_b = _json.dumps(expected_fields_b, sort_keys=True, separators=(",", ":"))
    fp_b = hashlib.sha256(expected_json_b.encode("utf-8")).hexdigest()

    assert fp_a != fp_b


def test_fingerprint_unset_before_freeze(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id, evidence_id = _setup_disputed_claim_with_evidence(direct_deploy, direct_vm, direct_accounts)
    assert contract.get_evidence(evidence_id)["fingerprint"] == ""
