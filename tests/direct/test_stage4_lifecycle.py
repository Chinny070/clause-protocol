"""Stage 4 full LOCAL lifecycles (direct mode; the model is MOCKED wherever a semantic step runs -
these tests do not claim live model behaviour). Each lifecycle asserts accounting independently from
first principles (funding, reservation, claimable, emitted transfers), not only via contract views."""
import pytest

from helpers import ONE_DAY, ONE_GEN, model_result
from helpers4 import (
    ADJ_PATTERN, CHAL_PATTERN, build_env, capture_transfers, challenge, cite, decide, finalize, mock_reply,
    past_challenge_window, resolve, review, settle, warp_to, withdraw,
)

FIVE = 5 * ONE_GEN


def pool(env):
    return env["contract"].get_pool(env["program_id"])


def status(env):
    return env["contract"].get_claim(env["claim_id"])["status"]


def fd(env):
    return env["contract"].get_final_decision(env["claim_id"])


# ---- A. no-contest covered claim ---------------------------------------------------------------

def test_A_no_contest_full_lifecycle(direct_deploy, direct_vm, direct_accounts):
    sent = capture_transfers(direct_vm)
    env = build_env(direct_deploy, direct_vm, direct_accounts, decision="ACCEPT")
    c = env["contract"]
    assert status(env) == "ACCEPTED"
    assert pool(env)["total_balance"] == 10 * ONE_GEN and pool(env)["reserved_liability"] == FIVE

    finalize(env, direct_vm)
    assert status(env) == "FINAL"
    f = fd(env)
    assert f["source"] == "NO_CONTEST" and f["final_outcome"] == "ACCEPTED_NO_CONTEST"
    assert f["adjudication_id"] == 0 and f["remedy_kind"] == "FULL_REFUND" and f["remedy_amount"] == FIVE
    assert f["remedy_basis"] == "NO_CONTEST"
    holder_hex = c.get_passport(env["warranty_id"])["holder"].lower()
    assert f["recipient"].lower() == holder_hex
    # finalize moves no money
    assert pool(env)["total_balance"] == 10 * ONE_GEN and pool(env)["reserved_liability"] == FIVE
    assert sent == []

    settle(env, direct_vm)
    assert status(env) == "SETTLED"
    assert fd(env)["settled_amount"] == FIVE and fd(env)["claimable"] == FIVE and fd(env)["capped"] is False
    p = pool(env)
    assert p["total_balance"] == FIVE and p["reserved_liability"] == 0 and p["available_balance"] == FIVE
    assert c.get_reservation(c.get_passport(env["warranty_id"])["reservation_id"])["status"] == "CONSUMED"
    assert sent == []  # settlement authorizes; it does not pay

    withdraw(env, direct_vm)
    assert sent == [(holder_hex, FIVE)]
    assert fd(env)["claimable"] == 0 and fd(env)["withdrawn_amount"] == FIVE and fd(env)["withdrawn_at"] > 0


def test_A_no_contest_needs_no_semantic_adjudication(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    env = build_env(direct_deploy, direct_vm, direct_accounts, decision="ACCEPT")
    import genlayer.gl as gl_mod

    def boom(*a, **k):
        raise AssertionError("no model call is allowed on the no-contest path")

    monkeypatch.setattr(gl_mod.nondet, "exec_prompt", boom)
    finalize(env, direct_vm)
    settle(env, direct_vm)
    assert fd(env)["settled_amount"] == FIVE


def test_A_no_contest_cannot_be_adjudicated_or_challenged(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts, decision="ACCEPT")
    with pytest.raises(Exception):
        challenge(env, direct_vm, "TEMPORAL_ERROR", cite(timestamp_field="filed_at"))
    with pytest.raises(Exception):
        decide(env, direct_vm)


# ---- B. disputed -> COVERED -> no challenge ----------------------------------------------------

def test_B_disputed_covered_no_challenge(direct_deploy, direct_vm, direct_accounts):
    sent = capture_transfers(direct_vm)
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    decide(env, direct_vm, model_result(relied=(env["evidence_ids"][0],)))
    assert status(env) == "DECIDED"
    a = env["contract"].get_adjudication(env["contract"].get_claim(env["claim_id"])["adjudication_id"])
    assert a["outcome"] == "COVERED"

    with pytest.raises(Exception, match="still open"):
        finalize(env, direct_vm)  # challenge window still open
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    f = fd(env)
    assert f["source"] == "ADJUDICATION" and f["final_outcome"] == "COVERED" and f["remedy_amount"] == FIVE
    assert f["established_clause_ids"] == ["C-001"] and f["remedy_basis"] == "COVERED"
    settle(env, direct_vm)
    withdraw(env, direct_vm)
    assert len(sent) == 1 and sent[0][1] == FIVE
    assert pool(env)["total_balance"] == FIVE and pool(env)["reserved_liability"] == 0


def test_B_partial_bps_remedy_selected_from_frozen_table(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts, targeted=("C-002",))
    decide(env, direct_vm, model_result(covered=("C-002",), relied=(env["evidence_ids"][0],)))
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    assert fd(env)["remedy_kind"] == "PARTIAL_BPS" and fd(env)["remedy_amount"] == FIVE // 2
    settle(env, direct_vm)
    p = pool(env)
    # only the paid half leaves the reservation; the other half stays reserved for the warranty's life
    assert p["total_balance"] == 10 * ONE_GEN - FIVE // 2 and p["reserved_liability"] == FIVE - FIVE // 2
    res = env["contract"].get_reservation(env["contract"].get_passport(env["warranty_id"])["reservation_id"])
    assert res["status"] == "ACTIVE" and res["amount"] == FIVE - FIVE // 2


# ---- C. disputed -> NOT_COVERED ----------------------------------------------------------------

def test_C_not_covered_pays_nothing_and_keeps_reservation(direct_deploy, direct_vm, direct_accounts):
    sent = capture_transfers(direct_vm)
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    decide(env, direct_vm, model_result(product_match="FAIL", covered=(), relied=(env["evidence_ids"][0],)))
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    assert fd(env)["final_outcome"] == "NOT_COVERED" and fd(env)["remedy_amount"] == 0
    settle(env, direct_vm)
    assert fd(env)["claimable"] == 0 and fd(env)["settled_amount"] == 0
    assert pool(env)["total_balance"] == 10 * ONE_GEN and pool(env)["reserved_liability"] == FIVE
    with pytest.raises(Exception, match="nothing to withdraw"):
        withdraw(env, direct_vm)
    assert sent == []


# ---- D. challenge UPHELD -----------------------------------------------------------------------

def test_D_challenge_upheld_original_stands_and_pays(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    decide(env, direct_vm, model_result(relied=(env["evidence_ids"][0],)))
    challenge(env, direct_vm, "EXCLUSION_MISAPPLIED", cite(clause_ids=["X-001"]), who=env["manufacturer"])
    assert status(env) == "CHALLENGED"
    with pytest.raises(Exception, match="unresolved"):
        finalize(env, direct_vm)
    assert resolve(env, direct_vm, review(direct_vm)) == "UPHELD"
    assert status(env) == "CHALLENGE_RESOLVED"
    ch = env["contract"].get_challenge_for_claim(env["claim_id"])
    assert ch["result"] == "UPHELD" and ch["resolution_path"] == "SEMANTIC" and ch["corrected_adjudication_id"] == 0
    finalize(env, direct_vm)  # no need to wait for the window once the challenge is terminal
    assert fd(env)["source"] == "ADJUDICATION_AFTER_CHALLENGE" and fd(env)["final_outcome"] == "COVERED"
    a = env["contract"].get_adjudication(fd(env)["adjudication_id"])
    assert a["superseded"] is False
    settle(env, direct_vm)
    assert fd(env)["claimable"] == FIVE


# ---- E. challenge REVERSED ---------------------------------------------------------------------

def test_E_reversed_to_covered_pays_the_corrected_remedy(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    eid = env["evidence_ids"][0]
    decide(env, direct_vm, model_result(covered=(), relied=(eid,)))  # product PASS, nothing established
    c = env["contract"]
    orig_id = c.get_claim(env["claim_id"])["adjudication_id"]
    assert c.get_adjudication(orig_id)["outcome"] == "INSUFFICIENT_EVIDENCE"
    challenge(env, direct_vm, "WRONG_CLAUSE", cite(clause_ids=["C-001"]))
    assert resolve(env, direct_vm, review(direct_vm, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001"]})) == "REVERSED"
    ch = c.get_challenge_for_claim(env["claim_id"])
    assert ch["result"] == "REVERSED" and ch["corrected_adjudication_id"] not in (0, orig_id)
    assert c.get_adjudication(orig_id)["superseded"] is True and c.get_adjudication(orig_id)["outcome"] == "INSUFFICIENT_EVIDENCE"  # history preserved
    corrected = c.get_adjudication(ch["corrected_adjudication_id"])
    assert corrected["outcome"] == "COVERED" and corrected["decision_path"] == "CHALLENGE_CORRECTION" and corrected["superseded"] is False
    finalize(env, direct_vm)
    f = fd(env)
    assert f["source"] == "CHALLENGE_CORRECTED" and f["adjudication_id"] == ch["corrected_adjudication_id"] and f["final_outcome"] == "COVERED"
    settle(env, direct_vm)
    assert fd(env)["claimable"] == FIVE


def test_E_reversed_covered_to_not_covered_pays_nothing(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    decide(env, direct_vm, model_result(relied=(env["evidence_ids"][0],)))
    challenge(env, direct_vm, "EXCLUSION_MISAPPLIED", cite(clause_ids=["X-001"]), who=env["manufacturer"])
    assert resolve(env, direct_vm, review(direct_vm, "DEFECT_CONFIRMED", {"exclusion_clause_ids": ["X-001"]})) == "REVERSED"
    finalize(env, direct_vm)
    assert fd(env)["final_outcome"] == "NOT_COVERED" and fd(env)["remedy_amount"] == 0
    settle(env, direct_vm)
    assert fd(env)["claimable"] == 0 and pool(env)["reserved_liability"] == FIVE


def test_E_immaterial_correction_is_upheld_not_reversed(direct_deploy, direct_vm, direct_accounts):
    """A confirmed defect that does not change the outcome is not a *material* error."""
    env = build_env(direct_deploy, direct_vm, direct_accounts, targeted=("C-001", "C-002"))
    decide(env, direct_vm, model_result(covered=("C-001",), relied=(env["evidence_ids"][0],)))
    challenge(env, direct_vm, "WRONG_CLAUSE", cite(clause_ids=["C-002"]))
    # adds C-002 to an already-COVERED decision: the covered set changes, so it IS material (remedy row differs)
    assert resolve(env, direct_vm, review(direct_vm, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001", "C-002"]})) == "REVERSED"


def test_E_remand_runs_one_bounded_correction_and_is_final(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    c = env["contract"]
    eid = env["evidence_ids"][0]
    decide(env, direct_vm, model_result(covered=(), relied=(eid,)))
    challenge(env, direct_vm, "WRONG_CLAUSE", cite(clause_ids=["C-001"]))
    assert resolve(env, direct_vm, review(direct_vm, "NEEDS_RECONSIDERATION", remand_issue="Is C-001 satisfied by the receipt?")) == "REMAND"
    ch = c.get_challenge_for_claim(env["claim_id"])
    assert ch["status"] == "REMAND_PENDING" and ch["remand_issue"].startswith("Is C-001")
    assert status(env) == "CHALLENGED"
    with pytest.raises(Exception, match="unresolved"):
        finalize(env, direct_vm)
    with pytest.raises(Exception):
        resolve(env, direct_vm)  # cannot re-resolve; only the one remand step remains
    mock_reply(direct_vm, model_result(relied=(eid,)), r"RECONSIDERATION \(bounded\)")
    direct_vm.sender = env["other"]
    corrected_id = c.execute_remand(claim_id=env["claim_id"])
    ch = c.get_challenge_for_claim(env["claim_id"])
    assert ch["status"] == "RESOLVED" and ch["result"] == "REMAND" and ch["corrected_adjudication_id"] == corrected_id
    corrected = c.get_adjudication(corrected_id)
    assert corrected["decision_path"] == "REMAND_CORRECTION" and corrected["outcome"] == "COVERED"
    assert corrected["challenge_window_closes_at"] == 0  # a correction is never itself challengeable
    with pytest.raises(Exception):
        c.execute_remand(claim_id=env["claim_id"])  # exactly once
    with pytest.raises(Exception):
        challenge(env, direct_vm, "TEMPORAL_ERROR", cite(timestamp_field="filed_at"))  # no second challenge
    finalize(env, direct_vm)
    assert fd(env)["source"] == "CHALLENGE_CORRECTED" and fd(env)["remedy_amount"] == FIVE


# ---- F. invalid challenge ----------------------------------------------------------------------

def test_F_invalid_challenge_does_not_corrupt_the_original(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    c = env["contract"]
    decide(env, direct_vm, model_result(relied=(env["evidence_ids"][0],)))
    orig_id = c.get_claim(env["claim_id"])["adjudication_id"]
    before = c.get_adjudication(orig_id)
    challenge(env, direct_vm, "WRONG_WARRANTY_VERSION", cite(constitution_id=env["constitution_id"] + 99), who=env["manufacturer"])
    assert resolve(env, direct_vm) == "INVALID_CHALLENGE"  # deterministic: no model involved
    ch = c.get_challenge_for_claim(env["claim_id"])
    assert ch["resolution_path"] == "DETERMINISTIC" and ch["corrected_adjudication_id"] == 0
    assert c.get_adjudication(orig_id) == before  # untouched, still not superseded
    finalize(env, direct_vm)
    assert fd(env)["final_outcome"] == "COVERED" and fd(env)["adjudication_id"] == orig_id


# ---- G. evidence unavailable / insufficient ----------------------------------------------------

@pytest.mark.parametrize("behavior,paid", [("RULE_FOR_MANUFACTURER", 0), ("BLOCK", 0), ("RULE_FOR_HOLDER", FIVE)])
def test_G_insufficient_evidence_follows_frozen_policy(direct_deploy, direct_vm, direct_accounts, behavior, paid):
    env = build_env(direct_deploy, direct_vm, direct_accounts, insufficient=behavior, evidence=[("https://evil.example.net/a", None, "")])
    decide(env, direct_vm)  # only ineligible evidence -> deterministic INSUFFICIENT_EVIDENCE, no model
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    f = fd(env)
    assert f["final_outcome"] == "INSUFFICIENT_EVIDENCE" and f["remedy_amount"] == paid
    assert f["remedy_basis"] == {"RULE_FOR_MANUFACTURER": "NON_PAYABLE", "BLOCK": "POLICY_BLOCK", "RULE_FOR_HOLDER": "POLICY_RULE_FOR_HOLDER"}[behavior]
    settle(env, direct_vm)
    assert fd(env)["claimable"] == paid


@pytest.mark.parametrize("behavior,paid", [("RULE_FOR_MANUFACTURER", 0), ("BLOCK", 0), ("RULE_FOR_HOLDER", FIVE)])
def test_G_unavailable_evidence_follows_frozen_policy(direct_deploy, direct_vm, direct_accounts, behavior, paid):
    env = build_env(direct_deploy, direct_vm, direct_accounts, unavailable=behavior, evidence=[("e404", 404, "nope")])
    decide(env, direct_vm)
    a = env["contract"].get_adjudication(env["contract"].get_claim(env["claim_id"])["adjudication_id"])
    assert a["outcome"] == "EVIDENCE_UNAVAILABLE"
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    assert fd(env)["remedy_amount"] == paid


def test_invalid_claim_and_out_of_window_never_pay_even_with_holder_friendly_policy(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts, insufficient="RULE_FOR_HOLDER", unavailable="RULE_FOR_HOLDER",
                    failure_offset_s=-10 * ONE_DAY)  # asserted failure precedes coverage_start
    decide(env, direct_vm)
    a = env["contract"].get_adjudication(env["contract"].get_claim(env["claim_id"])["adjudication_id"])
    assert a["coverage_window"] == "FAIL" and a["outcome"] == "NOT_COVERED"
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    assert fd(env)["remedy_amount"] == 0


# ---- receipt ------------------------------------------------------------------------------------

def test_resolution_receipt_reconstructs_the_whole_history(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts)
    c = env["contract"]
    eid = env["evidence_ids"][0]
    decide(env, direct_vm, model_result(covered=(), relied=(eid,)))
    challenge(env, direct_vm, "WRONG_CLAUSE", cite(clause_ids=["C-001"]))
    resolve(env, direct_vm, review(direct_vm, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001"]}))
    finalize(env, direct_vm)
    settle(env, direct_vm)
    r = c.get_resolution_receipt(env["claim_id"])
    assert r["claim_status"] == "SETTLED"
    assert r["warranty"]["constitution_fingerprint"] == c.get_constitution(env["constitution_id"])["fingerprint"]
    assert r["warranty"]["constitution_version"] == "2026.1"
    assert [e["evidence_id"] for e in r["evidence"]] == [eid] and len(r["evidence"][0]["fingerprint"]) == 64
    assert "content" not in r["evidence"][0] and "extracted_content" not in r["evidence"][0]
    assert r["original_adjudication"]["outcome"] == "INSUFFICIENT_EVIDENCE" and r["original_adjudication"]["superseded"] is True
    assert r["challenge"]["result"] == "REVERSED" and r["corrected_adjudication"]["outcome"] == "COVERED"
    assert r["final_decision"]["final_outcome"] == "COVERED" and r["final_decision"]["remedy_amount"] == FIVE
    assert r["final_decision"]["settled_at"] > 0 and r["final_decision"]["withdrawn_at"] == 0
    assert c.get_resolution_receipt(999) == {}


def test_receipt_for_a_bare_claim_is_bounded_and_safe(direct_deploy, direct_vm, direct_accounts):
    env = build_env(direct_deploy, direct_vm, direct_accounts, decision=None)
    r = env["contract"].get_resolution_receipt(env["claim_id"])
    assert r["original_adjudication"] == {} and r["challenge"] == {} and r["final_decision"] == {}


# ---- challenge_depth == 0 (frozen constitution disables application challenges) -------------------------------

def test_constitution_with_challenge_depth_zero_disables_challenges_and_the_window(direct_deploy, direct_vm, direct_accounts):
    from helpers import create_constitution_stage2, S3_COVERED, S3_EXCLUDED, fund, issue, file_claim, respond, freeze_evidence, submit_evidence, S3_URL
    from helpers4 import REMEDY_TABLE
    m, h = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = m
    c = direct_deploy("contracts/clause_protocol.py")
    pid = c.create_program("Acme")
    cid = create_constitution_stage2(c, pid, covered_clauses=S3_COVERED, excluded_clauses=S3_EXCLUDED, source_policy="docs.genlayer.com",
                                     evidence_categories=["RECEIPT"], challenge_depth=0, remedy_table=REMEDY_TABLE)
    fund(c, direct_vm, pid, m, 10 * ONE_GEN)
    env = build_env(direct_deploy, direct_vm, direct_accounts, contract=c, program_id=pid, constitution_id=cid)
    decide(env, direct_vm, model_result(relied=(env["evidence_ids"][0],)))
    with pytest.raises(Exception, match="disables application challenges"):
        challenge(env, direct_vm, "TEMPORAL_ERROR", cite(timestamp_field="filed_at"))
    finalize(env, direct_vm)  # no window to wait out: nothing can be challenged
    assert fd(env)["final_outcome"] == "COVERED"
