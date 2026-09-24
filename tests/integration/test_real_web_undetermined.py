"""Stage 2.5 item 5: real failed/undetermined consensus. httpbin.org/uuid returns a different
UUID on every request, so the leader's and every validator's independent fetch disagree ->
glsim rotates leaders -> UNDETERMINED. The invariant under test: no frozen evidence may appear.
Run via scripts/run_real_web.sh (fresh simulator process)."""
import json
import time
from pathlib import Path

import pytest

from gltest import get_accounts
from rt import client, deploy, read, votes

LOG = Path(__file__).resolve().parents[2] / "docs" / "STAGE_2_5_UNDETERMINED_LOG.json"
ONE_YEAR = 365 * 24 * 3600
log: dict = {}


def send(addr, fn, args, acct, value=0):
    h = client().write_contract(address=addr, function_name=fn, account=acct, args=args, value=value)
    for _ in range(120):
        tx = client().get_transaction(transaction_hash=h)
        if tx.get("status_name") in ("FINALIZED", "UNDETERMINED", "CANCELED"):
            return h, tx
        time.sleep(0.5)
    raise AssertionError(f"tx {h} never reached a terminal status")


@pytest.mark.xfail(
    strict=True,
    reason=("glsim 0.29.2 rotation does not undo the rejected leader's storage writes: all 5 validators "
            "disagree (correct), but the retry then sees leaked state and finalizes the REJECTED leader's "
            "evidence. Simulator-fidelity limitation; real undetermined-rollback must be verified on StudioNet."),
)
def test_volatile_source_gives_undetermined_and_no_frozen_state():
    a = get_accounts()
    mfr, holder = a[0], a[1]
    addr, _ = deploy(mfr)
    for fn, args, acct, val in [
        ("create_program", ["Acme"], mfr, 0),
        ("create_constitution", [1, "2026.1", "Widget", "flat", [{"clause_id": "C-001", "text": "Defects."}], [],
                                 ["RECEIPT"], "example.org,httpbin.org", 86400 * 30, 86400 * 14, 86400 * 7, 1,
                                 "RULE_FOR_MANUFACTURER", "RULE_FOR_MANUFACTURER", "Cancel before claim.",
                                 [{"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
                                  {"outcome": "ACCEPTED_NO_CONTEST", "clause_id": "", "remedy_kind": "FULL_REFUND", "remedy_value": 0}]], mfr, 0),
        ("fund_pool", [1], mfr, 3 * 10**15),
    ]:
        h, tx = send(addr, fn, args, acct, val)
        assert tx["status_name"] == "FINALIZED"
    now = int(read(addr, "now"))
    for fn, args, acct in [
        ("issue_warranty", [1, 1, holder.address, "W-1", format(1, "064x"), now, now + ONE_YEAR, 10**15], mfr),
        ("file_claim", [1, ["C-001"], now], holder),
        ("respond_to_claim", [1, "DISPUTE"], mfr),
        ("submit_evidence", [1, "https://httpbin.org/uuid", "RECEIPT"], holder),
    ]:
        h, tx = send(addr, fn, args, acct)
        assert tx["status_name"] == "FINALIZED", (fn, tx)

    before = {"claim": read(addr, "get_claim", [1]), "evidence": read(addr, "get_evidence", [1])}
    assert before["evidence"]["eligibility"] == "ELIGIBLE" and before["evidence"]["retrieval_status"] == ""

    h, tx = send(addr, "freeze_evidence", [1], holder)
    log["freeze_tx"] = h
    log["freeze_status_name"] = tx.get("status_name")
    log["freeze_votes"] = votes(tx) if tx.get("consensus_data") else None
    after = {"claim": read(addr, "get_claim", [1]), "evidence": read(addr, "get_evidence", [1])}
    log["before"], log["after"] = before, after
    LOG.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print("UNDETERMINED_OBSERVED status=", tx.get("status_name"), "claim=", after["claim"]["status"],
          "evidence_status=", repr(after["evidence"]["retrieval_status"]), "frozen_at=", after["evidence"]["frozen_at"])

    assert tx.get("status_name") == "UNDETERMINED", tx.get("status_name")
    assert after["claim"]["status"] == "DISPUTED" and after["claim"]["evidence_frozen_at"] == 0
    assert after["evidence"]["retrieval_status"] == "" and after["evidence"]["frozen_at"] == 0
    assert after == before
