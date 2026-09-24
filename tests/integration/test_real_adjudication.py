"""Stage 3 real-simulator run (glsim, no mocks). Run via scripts/run_real_web.sh (fresh simulator).

HONEST SCOPE: glsim has no model provider configured here (no API key, no local model), so a
genuine model-backed leader/validator SEMANTIC consensus cannot be exercised - that stays a
StudioNet gate. What this DOES exercise on the real runtime:
  * real web retrieval -> frozen evidence (Stage 2) feeding Stage 3,
  * the deterministic adjudication paths end to end (no model needed): evidence unavailable,
    outside-window, with authoritative rereads,
  * the SEMANTIC path against a real runtime with NO model: it must fail closed - the tx errors,
    nothing is stored, the claim stays EVIDENCE_FROZEN.
Writes docs/STAGE_3_RUN_LOG.json."""
import json
from pathlib import Path

from gltest import get_accounts
from rt import client, deploy, leader_result, read, votes, wait

LOG = Path(__file__).resolve().parents[2] / "docs" / "STAGE_3_RUN_LOG.json"
ONE_YEAR = 365 * 24 * 3600
log: dict = {"steps": []}


def w(addr, fn, args, acct, value=0, expect="SUCCESS"):
    h = client().write_contract(address=addr, function_name=fn, account=acct, args=args, value=value)
    r = wait(h)
    lr = leader_result(r)
    step = {"fn": fn, "tx": h, "status_name": r.get("status_name"), "votes": votes(r),
            "leader_execution_result": lr["execution_result"], "leader_stderr": (lr["stderr"] or "")[:300]}
    log["steps"].append(step)
    assert r.get("status_name") == "FINALIZED", step
    assert set(votes(r).values()) == {"agree"}, step
    assert lr["execution_result"] == expect, step
    return r


def test_real_runtime_adjudication_paths():
    try:
        _run()
    finally:
        LOG.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")


def _claim_with_evidence(addr, mfr, holder, urls, failure_at, claim_id):
    w(addr, "file_claim", [1, ["C-001"], failure_at], holder)
    w(addr, "respond_to_claim", [claim_id, "DISPUTE"], mfr)
    for u in urls:
        w(addr, "submit_evidence", [claim_id, u, "RECEIPT"], holder)
    w(addr, "freeze_evidence", [claim_id], holder)


def _run():
    a = get_accounts()
    mfr, holder = a[0], a[1]
    addr, dr = deploy(mfr)
    assert addr and leader_result(dr)["execution_result"] == "SUCCESS"
    w(addr, "create_program", ["Acme Stage3"], mfr)
    w(addr, "create_constitution", [
        1, "2026.1", "Widget Model X", "flat 1-year term",
        [{"clause_id": "C-001", "text": "Manufacturing defects are covered."}],
        [{"clause_id": "X-001", "text": "Accidental impact is excluded."}],
        ["RECEIPT"], "example.org", 30 * 86400, 14 * 86400, 7 * 86400, 1,
        "RULE_FOR_MANUFACTURER", "RULE_FOR_MANUFACTURER", "Cancel before any claim.",
        [{"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
         {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0}],
    ], mfr)
    w(addr, "fund_pool", [1], mfr, value=3 * 10**15)
    now = int(read(addr, "now"))
    w(addr, "issue_warranty", [1, 1, holder.address, "WIDGET-X-001", format(1, "064x"), now, now + ONE_YEAR, 10**15], mfr)
    pool_before = read(addr, "get_pool", [1])

    # claim 1: real 200 evidence -> SEMANTIC path -> real runtime, NO model provider => must fail closed
    _claim_with_evidence(addr, mfr, holder, ["https://example.org/"], now, 1)
    assert read(addr, "get_evidence", [1])["retrieval_status"] == "AVAILABLE"
    r = w(addr, "adjudicate_claim", [1], holder, expect="ERROR")
    log["semantic_without_model"] = {"leader": leader_result(r), "claim": read(addr, "get_claim", [1]),
                                     "adjudication_1": read(addr, "get_adjudication", [1])}
    assert "[LLM_ERROR]" in (leader_result(r)["stderr"] or "")
    assert read(addr, "get_claim", [1])["status"] == "EVIDENCE_FROZEN" and read(addr, "get_claim", [1])["adjudication_id"] == 0
    assert read(addr, "get_adjudication", [1]) == {}

    # claim 2: real 404 evidence -> deterministic EVIDENCE_UNAVAILABLE (no model consulted)
    _claim_with_evidence(addr, mfr, holder, ["https://example.org/stage3-missing-page"], now, 2)
    assert read(addr, "get_evidence", [2])["retrieval_status"] == "FETCH_FAILED"
    w(addr, "adjudicate_claim", [2], holder)
    adj = read(addr, "get_adjudication", [1])
    claim2 = read(addr, "get_claim", [2])
    log["unavailable_path"] = {"adjudication": adj, "claim": claim2}
    assert adj["outcome"] == "EVIDENCE_UNAVAILABLE" and adj["decision_path"] == "DETERMINISTIC_EVIDENCE_UNAVAILABLE"
    assert adj["claim_id"] == 2 and adj["evidence_sufficiency"] == "UNAVAILABLE"
    assert claim2["status"] == "DECIDED" and claim2["adjudication_id"] == 1
    assert adj["challenge_window_closes_at"] == adj["adjudicated_at"] + 7 * 86400

    # claim 3: failure asserted before coverage_start -> deterministic NOT_COVERED
    _claim_with_evidence(addr, mfr, holder, ["https://example.org/"], now - 10 * 86400, 3)
    w(addr, "adjudicate_claim", [3], holder)
    adj3 = read(addr, "get_adjudication", [2])
    log["outside_window_path"] = adj3
    assert adj3["outcome"] == "NOT_COVERED" and adj3["coverage_window"] == "FAIL"
    assert adj3["decision_path"] == "DETERMINISTIC_PREDICATE"

    # immutability + no money in the real runtime
    w(addr, "adjudicate_claim", [2], holder, expect="ERROR")
    assert read(addr, "get_adjudication", [1]) == adj
    assert read(addr, "get_pool", [1]) == pool_before
    log["pool_unchanged"] = True
