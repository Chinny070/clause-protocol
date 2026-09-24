"""Stage 4 real-simulator run (glsim, no mocks). Run via scripts/run_real_web.sh (fresh simulator).

HONEST SCOPE: glsim has no model provider here, so NO semantic step is exercised (no semantic adjudication, no
semantic challenge review, no remand) - those remain StudioNet gates. What this DOES run on the real runtime:
  * no-contest lifecycle: accept -> finalize -> settle -> withdraw_settlement, with the payable shim
    (scripts/glsim_with_msg_value.py, i.e. NOT genuine StudioNet payable behaviour),
  * a deterministic dispute: real web retrieval -> deterministic adjudication -> real-clock challenge window
    (60 s) -> deterministic challenge -> finalize -> zero settlement,
  * consensus votes for every write, one-shot guards, and authoritative rereads.
Writes docs/STAGE_4_RUN_LOG.json."""
import json
import time
from pathlib import Path

from gltest import get_accounts
from rt import client, deploy, leader_result, read, votes, wait

LOG = Path(__file__).resolve().parents[2] / "docs" / "STAGE_4_RUN_LOG.json"
ONE_YEAR = 365 * 24 * 3600
FUND = 3 * 10**15
MAXR = 10**15
log: dict = {"steps": []}


def w(addr, fn, args, acct, value=0, expect="SUCCESS"):
    h = client().write_contract(address=addr, function_name=fn, account=acct, args=args, value=value)
    r = wait(h)
    lr = leader_result(r)
    step = {"fn": fn, "tx": h, "status_name": r.get("status_name"), "votes": votes(r),
            "leader_execution_result": lr["execution_result"], "leader_stderr": (lr["stderr"] or "")[:200]}
    log["steps"].append(step)
    assert r.get("status_name") == "FINALIZED", step
    assert set(votes(r).values()) == {"agree"}, step
    assert lr["execution_result"] == expect, step
    return r


def balance(address):
    """Raw JSON-RPC eth_getBalance against the local simulator (independent of the client wrapper)."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:4000/api", method="POST", headers={"Content-Type": "application/json"},
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [address, "latest"]}).encode(),
        )
        return int(json.loads(urllib.request.urlopen(req, timeout=5).read())["result"], 16)
    except Exception as e:  # pragma: no cover - simulator dependent
        return f"unavailable: {e}"


def test_real_runtime_settlement_paths():
    try:
        _run()
    finally:
        LOG.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")


def _run():
    a = get_accounts()
    mfr, holder, other = a[0], a[1], a[2]
    addr, dr = deploy(mfr)
    assert addr and leader_result(dr)["execution_result"] == "SUCCESS"
    w(addr, "create_program", ["Acme Stage4"], mfr)
    w(addr, "create_constitution", [
        1, "2026.1", "Widget Model X", "flat 1-year term",
        [{"clause_id": "C-001", "text": "Manufacturing defects are covered."}],
        [{"clause_id": "X-001", "text": "Accidental impact is excluded."}],
        ["RECEIPT"], "example.org", 30 * 86400, 14 * 86400, 60, 1,
        "RULE_FOR_MANUFACTURER", "RULE_FOR_MANUFACTURER", "Cancel before any claim.",
        [{"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
         {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0},
         {"outcome": "ACCEPTED_NO_CONTEST", "clause_id": "", "remedy_kind": "FULL_REFUND", "remedy_value": 0}],
    ], mfr)
    # Stage 4.5: an incomplete remedy table (no ACCEPTED_NO_CONTEST row) is refused before any warranty can bind to it
    w(addr, "create_constitution", [
        1, "2026.bad", "Widget Model X", "flat 1-year term",
        [{"clause_id": "C-001", "text": "Manufacturing defects are covered."}], [],
        ["RECEIPT"], "example.org", 30 * 86400, 14 * 86400, 60, 1, "RULE_FOR_MANUFACTURER", "RULE_FOR_MANUFACTURER", "x",
        [{"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0}],
    ], mfr, expect="ERROR")
    assert read(addr, "get_constitution", [2]) == {}
    w(addr, "fund_pool", [1], mfr, value=FUND)
    now = int(read(addr, "now"))
    w(addr, "issue_warranty", [1, 1, holder.address, "WIDGET-X-001", format(1, "064x"), now, now + ONE_YEAR, MAXR], mfr)
    w(addr, "issue_warranty", [1, 1, holder.address, "WIDGET-X-001", format(2, "064x"), now, now + ONE_YEAR, MAXR], mfr)
    assert read(addr, "get_pool", [1])["reserved_liability"] == 2 * MAXR

    # ---- A. no-contest lifecycle (claim 1 on warranty 1) ----
    w(addr, "file_claim", [1, ["C-001"], now], holder)
    w(addr, "respond_to_claim", [1, "ACCEPT"], mfr)
    w(addr, "adjudicate_claim", [1], holder, expect="ERROR")  # no semantic adjudication on an accepted claim
    w(addr, "withdraw_settlement", [1], holder, expect="ERROR")  # not settled yet
    w(addr, "settle_claim", [1], other, expect="ERROR")  # not final yet
    w(addr, "finalize_claim", [1], other)
    fd = read(addr, "get_final_decision", [1])
    log["A_final_decision"] = fd
    assert fd["source"] == "NO_CONTEST" and fd["remedy_amount"] == MAXR and fd["settled_at"] == 0
    assert read(addr, "get_pool", [1])["total_balance"] == FUND  # finalize moves nothing
    w(addr, "finalize_claim", [1], other, expect="ERROR")  # one-shot
    w(addr, "settle_claim", [1], other)
    pool = read(addr, "get_pool", [1])
    assert pool["total_balance"] == FUND - MAXR and pool["reserved_liability"] == MAXR  # only warranty 2 still reserved
    w(addr, "settle_claim", [1], other, expect="ERROR")  # one-shot
    w(addr, "withdraw_settlement", [1], other, expect="ERROR")  # not the recipient
    before = (balance(holder.address), balance(addr))
    w(addr, "withdraw_settlement", [1], holder)
    after = (balance(holder.address), balance(addr))
    # INFORMATIONAL ONLY: glsim's EOA/contract balance accounting is not asserted (see STAGE_4_VERIFICATION.md);
    # the contract-side accounting above is what is verified. Genuine transfer emission is a StudioNet gate.
    log["A_balances_holder_contract"] = {"before": before, "after": after}
    fd = read(addr, "get_final_decision", [1])
    assert fd["claimable"] == 0 and fd["withdrawn_amount"] == MAXR and fd["withdrawn_at"] > 0
    w(addr, "withdraw_settlement", [1], holder, expect="ERROR")  # one-shot
    log["A_receipt"] = read(addr, "get_resolution_receipt", [1])

    # ---- B. deterministic dispute with a real-clock challenge window (claim 2 on warranty 2) ----
    w(addr, "file_claim", [2, ["C-001"], now - 10 * 86400], holder)  # asserted failure predates coverage_start
    w(addr, "respond_to_claim", [2, "DISPUTE"], mfr)
    w(addr, "submit_evidence", [2, "https://example.org/", "RECEIPT"], holder)
    w(addr, "freeze_evidence", [2], holder)
    w(addr, "adjudicate_claim", [2], holder)  # window FAIL -> deterministic NOT_COVERED, no model
    adj = read(addr, "get_adjudication", [1])
    assert adj["outcome"] == "NOT_COVERED" and adj["decision_path"] == "DETERMINISTIC_PREDICATE"
    assert adj["challenge_window_closes_at"] == adj["adjudicated_at"] + 60
    w(addr, "finalize_claim", [2], other, expect="ERROR")  # window still open (protocol clock)
    w(addr, "file_challenge", [2, "TEMPORAL_ERROR", "Please recheck the window.",
                               {"evidence_ids": [], "clause_ids": [], "constitution_id": 0, "timestamp_field": "failure_asserted_at"}], holder)
    w(addr, "file_challenge", [2, "TEMPORAL_ERROR", "again",
                               {"evidence_ids": [], "clause_ids": [], "constitution_id": 0, "timestamp_field": "filed_at"}], mfr, expect="ERROR")
    w(addr, "settle_claim", [2], other, expect="ERROR")  # challenge unresolved
    w(addr, "resolve_challenge", [2], other)
    ch = read(addr, "get_challenge_for_claim", [2])
    log["B_challenge"] = ch
    assert ch["result"] == "UPHELD" and ch["resolution_path"] == "DETERMINISTIC"
    w(addr, "finalize_claim", [2], other)
    fd2 = read(addr, "get_final_decision", [2])
    assert fd2["final_outcome"] == "NOT_COVERED" and fd2["remedy_amount"] == 0
    w(addr, "settle_claim", [2], other)
    w(addr, "withdraw_settlement", [2], holder, expect="ERROR")  # nothing to withdraw
    log["B_receipt"] = read(addr, "get_resolution_receipt", [2])
    pool = read(addr, "get_pool", [1])
    assert pool["total_balance"] == FUND - MAXR and pool["reserved_liability"] == MAXR  # warranty 2's reservation untouched
    log["real_clock_note"] = "challenge window boundary checked against the real simulator clock only at coarse grain"
