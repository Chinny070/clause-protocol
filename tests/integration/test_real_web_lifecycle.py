"""Stage 2.5: the real Stage 2 lifecycle through the official local GenLayer simulator (glsim),
NO mocks: deploy -> setup -> claim -> dispute -> evidence -> real gl.nondet.web.get ->
consensus -> freeze -> authoritative reread -> independent fingerprint -> immutability.

Run via scripts/run_real_web.sh (fresh simulator process; glsim 0.29.2 loads one contract per
process). Writes docs/STAGE_2_5_RUN_LOG.json with the raw observations."""
import hashlib
import json
from pathlib import Path

import pytest

from gltest import get_accounts
from rt import client, deploy, leader_result, read, votes, wait

LOG = Path(__file__).resolve().parents[2] / "docs" / "STAGE_2_5_RUN_LOG.json"
STATIC_URL = "https://example.org/"
MISSING_URL = "https://example.org/stage25-missing-page"
DISALLOWED_URL = "https://not-allowed.example/page"
ONE_YEAR = 365 * 24 * 3600
log: dict = {"steps": []}


def w(addr, fn, args, acct, value=0, expect="SUCCESS"):
    h = client().write_contract(address=addr, function_name=fn, account=acct, args=args, value=value)
    r = wait(h)
    lr = leader_result(r)
    step = {
        "fn": fn, "tx": h, "status_name": r.get("status_name"),
        "votes": votes(r), "leader_execution_result": lr["execution_result"],
        "leader_result_status": (lr["result"] or {}).get("status"),
        "leader_stderr": (lr["stderr"] or "")[:200],
    }
    log["steps"].append(step)
    assert r.get("status_name") == "FINALIZED", step
    assert set(votes(r).values()) == {"agree"}, step
    assert lr["execution_result"] == expect, step
    return r


def fingerprint(ev: dict) -> str:
    fields = {
        "evidence_id": ev["evidence_id"], "claim_id": ev["claim_id"],
        "original_url": ev["original_url"], "category": ev["category"],
        "retrieval_status": ev["retrieval_status"], "content": ev["extracted_content"],
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_real_lifecycle_get_and_404_and_immutability():
    try:
        _run()
    finally:
        LOG.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")


def _run():
    a = get_accounts()
    mfr, holder = a[0], a[1]

    addr, dr = deploy(mfr)
    assert addr and leader_result(dr)["execution_result"] == "SUCCESS", leader_result(dr)
    log["deploy"] = {"address": addr, "status_name": dr.get("status_name"), "votes": votes(dr)}
    assert set(votes(dr).values()) == {"agree"}

    w(addr, "create_program", ["Acme Real-Web Fixture"], mfr)
    w(addr, "create_constitution", [
        1, "2026.1", "Widget Model X", "flat 1-year term",
        [{"clause_id": "C-001", "text": "Manufacturing defects are covered."}],
        [{"clause_id": "X-001", "text": "Water damage is excluded."}],
        ["RECEIPT", "PAGE_RENDERED"], "example.org", 30 * 86400, 14 * 86400, 7 * 86400, 1,
        "RULE_FOR_MANUFACTURER", "RULE_FOR_MANUFACTURER", "Cancel before any claim.",
        [{"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
         {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0}],
    ], mfr)
    w(addr, "fund_pool", [1], mfr, value=3 * 10**15)
    now = int(read(addr, "now"))
    w(addr, "issue_warranty", [1, 1, holder.address, "WIDGET-X-001", format(1, "064x"), now, now + ONE_YEAR, 10**15], mfr)
    pool = read(addr, "get_pool", [1])
    assert pool["reserved_liability"] == 10**15 and pool["total_balance"] == 3 * 10**15
    w(addr, "file_claim", [1, ["C-001"], now], holder)
    w(addr, "respond_to_claim", [1, "DISPUTE"], mfr)
    assert read(addr, "get_claim", [1])["status"] == "DISPUTED"

    w(addr, "submit_evidence", [1, STATIC_URL, "RECEIPT"], holder)
    w(addr, "submit_evidence", [1, MISSING_URL, "RECEIPT"], holder)
    w(addr, "submit_evidence", [1, DISALLOWED_URL, "RECEIPT"], holder)
    for i in (1, 2, 3):
        pre = read(addr, "get_evidence", [i])
        assert pre["retrieval_status"] == "" and pre["frozen_at"] == 0 and pre["fingerprint"] == ""
    assert read(addr, "get_evidence", [3])["eligibility"] == "INELIGIBLE"

    log["claim_before_freeze"] = read(addr, "get_claim", [1])
    try:
        fr = w(addr, "freeze_evidence", [1], holder)  # REAL gl.nondet.web.get x2, real consensus
    except AssertionError:
        log["state_after_failed_freeze"] = {"claim": read(addr, "get_claim", [1]),
                                            "evidence": [read(addr, "get_evidence", [i]) for i in (1, 2, 3)]}
        raise
    log["freeze_receipt_consensus"] = {
        "status_name": fr.get("status_name"), "votes": votes(fr),
        "leader_eq_outputs": fr["consensus_data"]["leader_receipt"][0].get("eq_outputs"),
    }

    claim = read(addr, "get_claim", [1])
    e1, e2, e3 = (read(addr, "get_evidence", [i]) for i in (1, 2, 3))
    log["claim_after_freeze"], log["evidence_after_freeze"] = claim, [e1, e2, e3]
    assert claim["status"] == "EVIDENCE_FROZEN" and claim["evidence_frozen_at"] > 0

    assert e1["claim_id"] == 1 and e1["evidence_id"] == 1
    assert e1["original_url"] == STATIC_URL and e1["category"] == "RECEIPT"
    assert e1["retrieval_method"] == "GET" and e1["retrieval_status"] == "AVAILABLE" and e1["available"] is True
    assert "Example Domain" in e1["extracted_content"] and 0 < len(e1["extracted_content"]) <= 2000
    assert e1["frozen_at"] > 0 and e1["retrieved_at"] == e1["frozen_at"]
    assert e1["fingerprint"] == fingerprint(e1), "independent recomputation must equal stored fingerprint"
    log["independent_fingerprint_e1"] = fingerprint(e1)

    # failure path: a REAL 404 is FETCH_FAILED, not a claim outcome
    assert e2["retrieval_status"] == "FETCH_FAILED" and e2["available"] is False and e2["extracted_content"] == ""
    assert e2["fingerprint"] == fingerprint(e2)
    assert claim["status"] == "EVIDENCE_FROZEN" and "outcome" not in claim  # no NOT_COVERED anywhere

    # ineligible record never retrieved
    assert e3["eligibility"] == "INELIGIBLE" and e3["retrieval_status"] == "" and e3["frozen_at"] == 0

    # immutability in the real runtime: re-freeze and post-freeze submission must be rejected
    w(addr, "freeze_evidence", [1], holder, expect="ERROR")
    w(addr, "submit_evidence", [1, "https://example.org/late", "RECEIPT"], holder, expect="ERROR")
    assert read(addr, "get_claim", [1]) == claim
    assert [read(addr, "get_evidence", [i]) for i in (1, 2, 3)] == [e1, e2, e3]
    log["immutability"] = "re-freeze and post-freeze submit both ERROR/rollback; records byte-identical on reread"

    # RENDER path (claim 2). glsim emulates WebRender as a plain GET body (see docs) - recorded, NOT claimed as verified.
    w(addr, "file_claim", [1, ["C-001"], now], holder)
    w(addr, "respond_to_claim", [2, "DISPUTE"], mfr)
    w(addr, "submit_evidence", [2, STATIC_URL, "PAGE_RENDERED"], holder)
    w(addr, "freeze_evidence", [2], holder)
    r_ev = read(addr, "get_evidence", [4])
    log["render_evidence_glsim_emulated"] = r_ev
    assert r_ev["retrieval_method"] == "RENDER" and r_ev["retrieval_status"] == "AVAILABLE"
    assert r_ev["fingerprint"] == fingerprint(r_ev)

    LOG.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print("LIFECYCLE_OK", len(log["steps"]), "txs")
