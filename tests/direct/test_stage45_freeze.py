"""Stage 4.5 contract-freeze tests (direct mode; model MOCKED): (1) remedy-table completeness makes payable
deadlocks unreachable, (2) the grace-window reservation invariant, (3) audit of the challenge `corrections`
representation."""
import itertools

import pytest

from helpers import ONE_DAY, ONE_GEN, S3_COVERED, S3_EXCLUDED, create_constitution_stage2, fund, model_result
from helpers4 import (
    CHAL_PATTERN, build_env, challenge, cite, decide, finalize, mock_reply, past_challenge_window, resolve, review,
    settle, warp_to,
)
from test_stage4_pure_logic import select

FIVE = 5 * ONE_GEN
COVERED3 = S3_COVERED + [{"clause_id": "C-003", "text": "Screen defects are covered."}]
CIDS = ["C-001", "C-002", "C-003"]
NOT_COVERED_ROW = {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0}


def row(outcome, clause, kind="FULL_REFUND", value=0):
    return {"outcome": outcome, "clause_id": clause, "remedy_kind": kind, "remedy_value": value}


# ---------------------------------------------------------------- 1. remedy-table completeness

CANDIDATES = [("COVERED", "C-001"), ("COVERED", "C-002"), ("COVERED", "C-003"), ("COVERED", ""), ("ACCEPTED_NO_CONTEST", "")]


def oracle_complete(pairs):
    """Independent statement of completeness."""
    if ("ACCEPTED_NO_CONTEST", "") not in pairs:
        return False
    if ("COVERED", "") in pairs:
        return True
    return all(("COVERED", c) in pairs for c in CIDS)


def test_completeness_exhaustive_over_every_table_shape(direct_deploy, direct_vm, direct_accounts):
    direct_vm.sender = direct_accounts[0]
    c = direct_deploy("contracts/clause_protocol.py")
    pid = c.create_program("Acme")
    accepted = rejected = 0
    for n, mask in enumerate(itertools.product([False, True], repeat=len(CANDIDATES))):
        pairs = {CANDIDATES[i] for i, on in enumerate(mask) if on}
        table = [row(o, cl) for o, cl in sorted(pairs)] + [NOT_COVERED_ROW]
        try:
            cid = create_constitution_stage2(c, pid, version=f"v{n}", covered_clauses=COVERED3, excluded_clauses=S3_EXCLUDED,
                                             source_policy="docs.genlayer.com", evidence_categories=["RECEIPT"], remedy_table=table)
            ok = True
        except Exception as e:
            ok = False
            assert "remedy_table incomplete" in str(e), (pairs, str(e))
        assert ok == oracle_complete(pairs), pairs
        if ok:
            accepted += 1
            rows = c.get_constitution(cid)["remedy_table"]
            # every reachable payable final state resolves to a row, within the frozen max
            for r in range(1, 4):
                for subset in itertools.combinations(CIDS, r):
                    for outcome, ins, una in (("COVERED", "X", "X"), ("INSUFFICIENT_EVIDENCE", "RULE_FOR_HOLDER", "X"),
                                              ("EVIDENCE_UNAVAILABLE", "X", "RULE_FOR_HOLDER")):
                        res = select(rows, outcome, list(subset), list(subset), ins, una, FIVE)
                        assert 0 <= res["amount"] <= FIVE and res["basis"] != "NON_PAYABLE"
            res = select(rows, "ACCEPTED_NO_CONTEST", [], ["C-001"], "X", "X", FIVE)
            assert 0 <= res["amount"] <= FIVE
        else:
            rejected += 1
    assert (accepted, rejected) == (sum(oracle_complete({CANDIDATES[i] for i, on in enumerate(m) if on}) for m in itertools.product([False, True], repeat=5)), 32 - accepted)
    assert accepted > 0 and rejected > 0


def test_rejected_constitution_never_exists_so_no_warranty_can_bind_to_it(direct_deploy, direct_vm, direct_accounts):
    direct_vm.sender = direct_accounts[0]
    c = direct_deploy("contracts/clause_protocol.py")
    pid = c.create_program("Acme")
    fund(c, direct_vm, pid, direct_accounts[0], 10 * ONE_GEN)
    with pytest.raises(Exception, match="remedy_table incomplete"):
        create_constitution_stage2(c, pid, covered_clauses=COVERED3, excluded_clauses=S3_EXCLUDED, source_policy="docs.genlayer.com",
                                   evidence_categories=["RECEIPT"], remedy_table=[row("COVERED", "C-001"), NOT_COVERED_ROW])
    assert c.get_constitution(1) == {}  # nothing was stored
    from helpers import issue
    with pytest.raises(Exception):
        issue(c, direct_vm, pid, 1, direct_accounts[0], direct_accounts[1])


@pytest.mark.parametrize("name,table", [
    ("outcome_level_only", [row("COVERED", ""), row("ACCEPTED_NO_CONTEST", ""), NOT_COVERED_ROW]),
    ("per_clause_only", [row("COVERED", "C-001"), row("COVERED", "C-002", "PARTIAL_BPS", 5000), row("COVERED", "C-003", "REPAIR_CREDIT", 10**30),
                         row("ACCEPTED_NO_CONTEST", "", "PARTIAL_BPS", 10_000), NOT_COVERED_ROW]),
    ("mixed", [row("COVERED", "C-001"), row("COVERED", "", "PARTIAL_BPS", 2500), row("ACCEPTED_NO_CONTEST", ""), NOT_COVERED_ROW]),
])
def test_an_issued_warranty_can_never_reach_a_payable_state_without_a_remedy(direct_deploy, direct_vm, direct_accounts, name, table):
    """End to end: every covered-clause configuration x every payable route finalizes and settles."""
    from helpers import respond, freeze_evidence, submit_evidence, S3_URL
    direct_vm.sender = direct_accounts[0]
    c = direct_deploy("contracts/clause_protocol.py")
    pid = c.create_program("Acme")
    cid = create_constitution_stage2(c, pid, covered_clauses=COVERED3, excluded_clauses=S3_EXCLUDED, source_policy="docs.genlayer.com",
                                     evidence_categories=["RECEIPT"], insufficient_evidence_behavior="RULE_FOR_HOLDER",
                                     unavailable_evidence_behavior="RULE_FOR_HOLDER", remedy_table=table)
    fund(c, direct_vm, pid, direct_accounts[0], 200 * ONE_GEN)
    seed = [100]
    subsets = [s for r in range(1, 4) for s in itertools.combinations(CIDS, r)]
    for subset in subsets:
        for route in ("covered", "insufficient", "unavailable", "accepted"):
            seed[0] += 1
            kw = dict(contract=c, program_id=pid, constitution_id=cid, commitment_seed=seed[0], targeted=subset)
            if route == "accepted":
                env = build_env(direct_deploy, direct_vm, direct_accounts, decision="ACCEPT", **kw)
            elif route == "covered":
                env = build_env(direct_deploy, direct_vm, direct_accounts, evidence=[(f"s{seed[0]}", 200, "Unit failed.")], **kw)
                decide(env, direct_vm, model_result(covered=subset, relied=(env["evidence_ids"][0],)))
                past_challenge_window(env, direct_vm)
            elif route == "insufficient":
                env = build_env(direct_deploy, direct_vm, direct_accounts, evidence=[("https://evil.example.net/x", None, "")], **kw)
                decide(env, direct_vm)
                past_challenge_window(env, direct_vm)
            else:
                env = build_env(direct_deploy, direct_vm, direct_accounts, evidence=[(f"m{seed[0]}", 404, "no")], **kw)
                decide(env, direct_vm)
                past_challenge_window(env, direct_vm)
            finalize(env, direct_vm)  # must never raise "failing closed"
            settle(env, direct_vm)
            f = c.get_final_decision(env["claim_id"])
            assert f["remedy_amount"] > 0 and f["settled_amount"] == f["remedy_amount"] or f["remedy_kind"] == "NONE" or f["capped"], (name, subset, route, f)
            assert f["settled_amount"] <= 5 * ONE_GEN


def test_reversed_and_remanded_outcomes_also_resolve_to_a_row(direct_deploy, direct_vm, direct_accounts):
    table = [row("COVERED", "C-001"), row("COVERED", "C-002", "PARTIAL_BPS", 5000), row("ACCEPTED_NO_CONTEST", ""), NOT_COVERED_ROW]
    env = build_env(direct_deploy, direct_vm, direct_accounts, targeted=("C-001", "C-002"), remedy_table=table)
    eid = env["evidence_ids"][0]
    decide(env, direct_vm, model_result(covered=(), relied=(eid,)))
    challenge(env, direct_vm, "WRONG_CLAUSE", cite(clause_ids=["C-002"]))
    assert resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-002"]})) == "REVERSED"
    finalize(env, direct_vm)
    assert env["contract"].get_final_decision(env["claim_id"])["remedy_amount"] == FIVE // 2

    env2 = build_env(direct_deploy, direct_vm, direct_accounts, contract=env["contract"], program_id=env["program_id"],
                     constitution_id=env["constitution_id"], commitment_seed=44, targeted=("C-001", "C-002"),
                     evidence=[("rm", 200, "Unit failed.")])
    e2 = env2["evidence_ids"][0]
    decide(env2, direct_vm, model_result(covered=(), relied=(e2,)))
    challenge(env2, direct_vm, "WRONG_CLAUSE", cite(clause_ids=["C-001"]))
    resolve(env2, direct_vm, review(None, "NEEDS_RECONSIDERATION", remand_issue="Is C-001 met?"))
    mock_reply(direct_vm, model_result(covered=("C-001", "C-002"), relied=(e2,)), r"RECONSIDERATION \(bounded\)")
    direct_vm.sender = env2["other"]
    env2["contract"].execute_remand(claim_id=env2["claim_id"])
    finalize(env2, direct_vm)
    assert env2["contract"].get_final_decision(env2["claim_id"])["remedy_amount"] == FIVE  # highest single row, never a sum


# ---------------------------------------------------------------- 2. grace-window reservation invariant

GRACE = 30 * ONE_DAY
COV = 1000


def release(env, direct_vm, who=None):
    direct_vm.sender = who or env["other"]
    env["contract"].release_expired_reservation(env["warranty_id"])


def cancel(env, direct_vm):
    direct_vm.sender = env["manufacturer"]
    env["contract"].cancel_warranty(env["warranty_id"])


def after_grace(env, direct_vm, extra=1):
    warp_to(direct_vm, env["now"] + COV + GRACE + extra)


def world(direct_deploy, direct_vm, direct_accounts, **kw):
    kw.setdefault("coverage_seconds", COV)
    kw.setdefault("pool_funding", 20 * ONE_GEN)
    return build_env(direct_deploy, direct_vm, direct_accounts, **kw)


def test_grace_open_blocks_release_and_exact_boundary(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, decision=None)
    # (this claim is unsettled; use a fresh warranty without claims for the pure-timing cases)
    c = env["contract"]
    # a warranty with no claims, for the pure-timing cases
    from helpers import issue
    now = int(c.now())
    wid = issue(c, direct_vm, env["program_id"], env["constitution_id"], env["manufacturer"], env["holder"], max_remedy=ONE_GEN,
                coverage_start=now, coverage_end=now + COV, commitment_seed=77)
    end = now + COV
    direct_vm.sender = env["other"]
    warp_to(direct_vm, end - 1)
    with pytest.raises(Exception, match="not expired"):
        c.release_expired_reservation(wid)  # coverage still running
    warp_to(direct_vm, end + 1)
    with pytest.raises(Exception, match="grace"):
        c.release_expired_reservation(wid)  # coverage over, claim grace open
    warp_to(direct_vm, end + GRACE)  # exact claim-deadline boundary: a claim filed AT this second is still valid
    with pytest.raises(Exception, match="grace"):
        c.release_expired_reservation(wid)
    warp_to(direct_vm, end + GRACE + 1)
    c.release_expired_reservation(wid)  # after grace, no claims: allowed
    assert c.get_reservation(c.get_passport(wid)["reservation_id"])["status"] == "RELEASED"


def test_a_claim_can_still_be_filed_exactly_when_release_is_still_blocked(direct_deploy, direct_vm, direct_accounts):
    """The two boundaries agree: file_claim's deadline (<=) and the release grace (<=) are the same second."""
    from helpers import file_claim, issue
    env = world(direct_deploy, direct_vm, direct_accounts, decision=None)
    c = env["contract"]
    now = int(c.now())
    wid = issue(c, direct_vm, env["program_id"], env["constitution_id"], env["manufacturer"], env["holder"], max_remedy=ONE_GEN,
                coverage_start=now, coverage_end=now + COV, commitment_seed=78)
    end = now + COV
    warp_to(direct_vm, end + GRACE)
    direct_vm.sender = env["other"]
    with pytest.raises(Exception, match="grace"):
        c.release_expired_reservation(wid)
    file_claim(c, direct_vm, wid, env["holder"], failure_asserted_at=end - 5)  # still fileable at the exact boundary
    warp_to(direct_vm, end + GRACE + 1)
    with pytest.raises(Exception):
        file_claim(c, direct_vm, wid, env["holder"], failure_asserted_at=end - 5)  # one second later: too late
    with pytest.raises(Exception, match="unsettled claim"):
        release(env | {"warranty_id": wid}, direct_vm)  # and the filed claim now protects the reservation


def _state_env(direct_deploy, direct_vm, direct_accounts, state, cov=COV):
    """A single-claim warranty driven to `state`."""
    from helpers import respond, freeze_evidence, submit_evidence, S3_URL
    if state == "RESPONSE_WINDOW":
        return world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=cov, decision=None)
    if state == "ACCEPTED":
        return world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=cov, decision="ACCEPT")
    if state == "DISPUTED":
        return world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=cov, freeze=False)
    if state == "EVIDENCE_FROZEN":
        return world(direct_deploy, direct_vm, direct_accounts)
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=cov, targeted=("C-002",))
    decide(env, direct_vm, model_result(covered=("C-002",), relied=(env["evidence_ids"][0],)))
    if state == "DECIDED":
        return env
    if state == "CHALLENGED":
        challenge(env, direct_vm, "TEMPORAL_ERROR", cite(timestamp_field="filed_at"))
        return env
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    if state == "FINAL":
        return env
    settle(env, direct_vm)
    return env


@pytest.mark.parametrize("state", ["RESPONSE_WINDOW", "ACCEPTED", "DISPUTED", "EVIDENCE_FROZEN", "DECIDED", "CHALLENGED", "FINAL"])
def test_unsettled_claim_in_any_state_blocks_release_even_after_grace(direct_deploy, direct_vm, direct_accounts, state):
    env = _state_env(direct_deploy, direct_vm, direct_accounts, state)
    after_grace(env, direct_vm, extra=40 * ONE_DAY)
    reserved = env["contract"].get_pool(env["program_id"])["reserved_liability"]
    with pytest.raises(Exception, match="unsettled claim"):
        release(env, direct_vm)
    assert env["contract"].get_pool(env["program_id"])["reserved_liability"] == reserved  # nothing released
    assert env["contract"].get_claim(env["claim_id"])["status"] != "SETTLED"


def test_final_but_unsettled_payable_claim_keeps_its_capacity(direct_deploy, direct_vm, direct_accounts):
    env = _state_env(direct_deploy, direct_vm, direct_accounts, "FINAL")
    after_grace(env, direct_vm, extra=60 * ONE_DAY)
    with pytest.raises(Exception, match="unsettled claim"):
        release(env, direct_vm)
    settle(env, direct_vm)  # the payout can still be funded in full
    f = env["contract"].get_final_decision(env["claim_id"])
    assert f["settled_amount"] == FIVE // 2 and f["capped"] is False


def test_settled_claim_allows_release_of_the_remainder_after_grace(direct_deploy, direct_vm, direct_accounts):
    env = _state_env(direct_deploy, direct_vm, direct_accounts, "SETTLED")
    c = env["contract"]
    if int(c.now()) <= env["now"] + COV + GRACE:
        after_grace(env, direct_vm)
    release(env, direct_vm)
    pool = c.get_pool(env["program_id"])
    assert pool["reserved_liability"] == 0
    assert c.get_final_decision(env["claim_id"])["claimable"] == FIVE // 2  # the holder's segregated funds are untouched
    with pytest.raises(Exception):
        release(env, direct_vm)


def test_multiple_claims_one_unresolved_blocks_release(direct_deploy, direct_vm, direct_accounts):
    from helpers import file_claim, respond
    env = world(direct_deploy, direct_vm, direct_accounts, decision=None)
    c = env["contract"]
    respond(c, direct_vm, env["claim_id"], env["manufacturer"], "ACCEPT")
    second = file_claim(c, direct_vm, env["warranty_id"], env["holder"])  # allowed: first is past dispute
    finalize(env, direct_vm)
    settle(env, direct_vm)  # first claim settles
    after_grace(env, direct_vm, extra=1)
    with pytest.raises(Exception, match="unsettled claim"):
        release(env, direct_vm)  # the second claim is still unresolved
    assert second != env["claim_id"]


@pytest.mark.parametrize("state", ["RESPONSE_WINDOW", "DECIDED", "CHALLENGED", "FINAL"])
def test_cancel_is_blocked_while_any_claim_is_unsettled(direct_deploy, direct_vm, direct_accounts, state):
    env = _state_env(direct_deploy, direct_vm, direct_accounts, state, cov=365 * ONE_DAY)
    with pytest.raises(Exception, match="unsettled claim"):
        cancel(env, direct_vm)
    assert env["contract"].get_passport(env["warranty_id"])["status"] == "ACTIVE"


def test_cancel_after_every_claim_settled_releases_the_remainder(direct_deploy, direct_vm, direct_accounts):
    env = _state_env(direct_deploy, direct_vm, direct_accounts, "SETTLED", cov=365 * ONE_DAY)
    cancel(env, direct_vm)  # every claim settled: cancellation (which also stops any new claim) may release
    assert env["contract"].get_pool(env["program_id"])["reserved_liability"] == 0
    assert env["contract"].get_final_decision(env["claim_id"])["claimable"] == FIVE // 2


# ---------------------------------------------------------------- 3. `corrections` representation audit

ALLOWED = {"WRONG_CLAUSE": {"covered_clause_ids"}, "EXCLUSION_MISAPPLIED": {"exclusion_clause_ids"},
           "PRODUCT_MATCH_ERROR": {"product_match"},
           "IGNORED_EVIDENCE": {"product_match", "covered_clause_ids", "exclusion_clause_ids", "evidence_sufficiency", "evidence_ids_relied_on"}}
SAMPLE = {"product_match": "FAIL", "covered_clause_ids": ["C-001"], "exclusion_clause_ids": ["X-001"],
          "evidence_sufficiency": "INSUFFICIENT", "evidence_ids_relied_on": [1]}
CITE_FOR = {"WRONG_CLAUSE": cite(clause_ids=["C-001"]), "EXCLUSION_MISAPPLIED": cite(clause_ids=["X-001"]),
            "PRODUCT_MATCH_ERROR": cite(evidence_ids=[1]), "IGNORED_EVIDENCE": cite(evidence_ids=[2])}


def corr_env(direct_deploy, direct_vm, direct_accounts, ground):
    env = build_env(direct_deploy, direct_vm, direct_accounts, targeted=("C-001", "C-002"),
                    evidence=[("e1", 200, "Unit failed."), ("e2", 200, "Second.")])
    e1 = env["evidence_ids"][0]
    if ground == "IGNORED_EVIDENCE":
        decide(env, direct_vm, model_result(covered=(), relied=(e1,)))
        challenge(env, direct_vm, ground, cite(evidence_ids=[env["evidence_ids"][1]]))
    else:
        decide(env, direct_vm, model_result(covered=(), relied=(e1,)))
        challenge(env, direct_vm, ground, {"WRONG_CLAUSE": cite(clause_ids=["C-001"]), "EXCLUSION_MISAPPLIED": cite(clause_ids=["X-001"]),
                                           "PRODUCT_MATCH_ERROR": cite(evidence_ids=[e1])}[ground])
    return env


@pytest.mark.parametrize("ground", sorted(ALLOWED))
def test_every_field_outside_the_ground_allow_list_is_rejected(direct_deploy, direct_vm, direct_accounts, ground):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, ground)
    for field, value in SAMPLE.items():
        if field in ALLOWED[ground]:
            continue
        with pytest.raises(Exception, match="may not change"):
            resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", {field: value}))
    assert env["contract"].get_claim(env["claim_id"])["status"] == "CHALLENGED"


@pytest.mark.parametrize("key", ["outcome", "remedy_amount", "remedy_kind", "remedy_value", "payout", "recipient", "constitution_id",
                                 "warranty_version_match", "coverage_window", "source_authority", "evidence_ids_considered",
                                 "decision_path", "rationale", "superseded", "challenge_window_closes_at", "adjudicated_at",
                                 "remedy_table", "evidence", "url", "urls", "new_evidence", "settled_amount", "claimable", "", " covered_clause_ids"])
@pytest.mark.parametrize("ground", ["IGNORED_EVIDENCE", "WRONG_CLAUSE"])
def test_economic_constitution_and_evidence_keys_can_never_be_corrected(direct_deploy, direct_vm, direct_accounts, ground, key):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, ground)
    good = {"covered_clause_ids": ["C-001"]}
    for corrections in ({key: 1}, {key: "x"}, {**good, key: 10**30}):
        with pytest.raises(Exception, match="LLM_ERROR"):
            resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", corrections))
    f = env["contract"].get_final_decision(env["claim_id"])
    assert f == {} and env["contract"].get_claim(env["claim_id"])["status"] == "CHALLENGED"


@pytest.mark.parametrize("corrections", [
    {"covered_clause_ids": "C-001"}, {"covered_clause_ids": [1]}, {"covered_clause_ids": [None]}, {"covered_clause_ids": [["C-001"]]},
    {"covered_clause_ids": [{"id": "C-001"}]}, {"covered_clause_ids": {"C-001": True}}, {"covered_clause_ids": None},
    {"covered_clause_ids": ["C-001", "C-001"]}, {"covered_clause_ids": ["c-001"]}, {"covered_clause_ids": ["C-001 "]},
    {"covered_clause_ids": ["C-001"] * 500}, {"covered_clause_ids": [f"C-{i:03d}" for i in range(1000)]},
    {"covered_clause_ids": ["X-001"]}, {"covered_clause_ids": ["C-999"]}, {"covered_clause_ids": ["C-003"]},
])
def test_malformed_or_unbounded_wrong_clause_corrections_rejected(direct_deploy, direct_vm, direct_accounts, corrections):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, "WRONG_CLAUSE")
    with pytest.raises(Exception, match="LLM_ERROR"):
        resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", corrections))


@pytest.mark.parametrize("corrections", [
    {"product_match": "pass"}, {"product_match": True}, {"product_match": ["PASS"]}, {"product_match": None}, {"product_match": "MAYBE"},
    {"product_match": "UNCLEAR "}, {"product_match": {"v": "PASS"}}, {"product_match": "PASS"},  # last: unchanged vs original -> rejected
])
def test_malformed_product_match_corrections_rejected(direct_deploy, direct_vm, direct_accounts, corrections):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, "PRODUCT_MATCH_ERROR")
    with pytest.raises(Exception, match="LLM_ERROR"):
        resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", corrections))


@pytest.mark.parametrize("corrections", [
    {"covered_clause_ids": ["C-001"], "product_match": "FAIL"},  # covered with product FAIL: contradiction
    {"covered_clause_ids": ["C-001"], "evidence_sufficiency": "INSUFFICIENT"},  # covered with INSUFFICIENT
    {"evidence_sufficiency": "SUFFICIENT", "evidence_ids_relied_on": []},  # SUFFICIENT relying on nothing
    {"evidence_sufficiency": "UNAVAILABLE"},  # the model can never assert UNAVAILABLE
    {"evidence_ids_relied_on": [1, 2, 2]}, {"evidence_ids_relied_on": [1, 3]},  # duplicate / unshown evidence
    {"evidence_ids_relied_on": [True, 2]}, {"evidence_ids_relied_on": ["2"]},
    {"covered_clause_ids": ["C-001"], "exclusion_clause_ids": ["C-001"]},  # conflicting kinds
    {"evidence_ids_relied_on": [1]},  # ignores the cited evidence 2 / equals the original
])
def test_conflicting_or_incoherent_ignored_evidence_corrections_rejected(direct_deploy, direct_vm, direct_accounts, corrections):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, "IGNORED_EVIDENCE")
    with pytest.raises(Exception, match="LLM_ERROR"):
        resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", corrections))
    assert env["contract"].get_challenge_for_claim(env["claim_id"])["status"] == "OPEN"


def test_duplicate_keys_in_raw_json_cannot_smuggle_a_second_value(direct_deploy, direct_vm, direct_accounts):
    """JSON with a duplicated key parses to the LAST value only; the checker sees exactly one value per key, so
    'conflicting' duplicates collapse before validation and the surviving value must itself be legal."""
    env = corr_env(direct_deploy, direct_vm, direct_accounts, "WRONG_CLAUSE")
    raw = ('{"decision":"DEFECT_CONFIRMED","remand_issue":"","reasoning":"x",'
           '"corrections":{"covered_clause_ids":["C-001"],"covered_clause_ids":["C-999"]}}')
    with pytest.raises(Exception, match="LLM_ERROR"):
        resolve(env, direct_vm, raw)
    raw_ok = raw.replace('"covered_clause_ids":["C-999"]', '"covered_clause_ids":["C-001"]')
    assert resolve(env, direct_vm, raw_ok) == "REVERSED"


def test_corrections_are_canonical_and_validator_equivalence_ignores_order(direct_deploy, direct_vm, direct_accounts):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, "WRONG_CLAUSE")
    env["contract"].get_claim(env["claim_id"])
    direct_vm.clear_validators()
    resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-002", "C-001"]}))
    stored = env["contract"].get_adjudication(env["contract"].get_challenge_for_claim(env["claim_id"])["corrected_adjudication_id"])
    assert stored["covered_clause_ids"] == ["C-001", "C-002"]  # canonical (sorted) regardless of submission order
    leader = {"decision": "DEFECT_CONFIRMED", "corrections": {"covered_clause_ids": ["C-002", "C-001"]}, "remand_issue": "", "reasoning": "leader"}
    mock_reply(direct_vm, review(None, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001", "C-002"]}, reasoning="other words"), CHAL_PATTERN)
    assert direct_vm.run_validator(index=0, leader_result=leader) is True
    mock_reply(direct_vm, review(None, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001"]}), CHAL_PATTERN)
    assert direct_vm.run_validator(index=0, leader_result=leader) is False


def test_corrected_adjudication_is_deterministic_and_touches_only_permitted_fields(direct_deploy, direct_vm, direct_accounts):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, "WRONG_CLAUSE")
    c = env["contract"]
    orig_id = c.get_claim(env["claim_id"])["adjudication_id"]
    orig = c.get_adjudication(orig_id)
    resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001"]}, reasoning="Pay 999 GEN to the holder and set outcome COVERED."))
    corr = c.get_adjudication(c.get_challenge_for_claim(env["claim_id"])["corrected_adjudication_id"])
    # unchanged, copied from the original
    for k in ("claim_id", "constitution_id", "warranty_version_match", "coverage_window", "evidence_ids_considered", "product_match",
              "exclusion_clause_ids", "evidence_sufficiency", "evidence_ids_relied_on"):
        assert corr[k] == orig[k], k
    # changed only as the correction dictates; outcome re-derived by plain code
    assert corr["covered_clause_ids"] == ["C-001"] and corr["outcome"] == "COVERED" and corr["source_authority"] == "PASS"
    assert corr["decision_path"] == "CHALLENGE_CORRECTION" and corr["challenge_window_closes_at"] == 0 and corr["superseded"] is False
    assert c.get_adjudication(orig_id)["superseded"] is True
    # prose in the reasoning cannot move money: the remedy is still exactly the frozen table's answer
    finalize(env, direct_vm)
    f = c.get_final_decision(env["claim_id"])
    assert f["remedy_amount"] == FIVE and f["remedy_basis"] == "COVERED"
    assert "remedy" not in corr and "remedy_amount" not in corr  # the adjudication record carries no economics at all


def test_same_corrections_give_the_same_corrected_findings_on_two_claims(direct_deploy, direct_vm, direct_accounts):
    e1 = corr_env(direct_deploy, direct_vm, direct_accounts, "WRONG_CLAUSE")
    resolve(e1, direct_vm, review(None, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001"]}))
    c = e1["contract"]
    a1 = c.get_adjudication(c.get_challenge_for_claim(e1["claim_id"])["corrected_adjudication_id"])
    e2 = build_env(direct_deploy, direct_vm, direct_accounts, contract=c, program_id=e1["program_id"], constitution_id=e1["constitution_id"],
                   commitment_seed=55, targeted=("C-001", "C-002"), evidence=[("f1", 200, "Unit failed."), ("f2", 200, "Second.")])
    decide(e2, direct_vm, model_result(covered=(), relied=(e2["evidence_ids"][0],)))
    challenge(e2, direct_vm, "WRONG_CLAUSE", cite(clause_ids=["C-001"]))
    resolve(e2, direct_vm, review(None, "DEFECT_CONFIRMED", {"covered_clause_ids": ["C-001"]}))
    a2 = c.get_adjudication(c.get_challenge_for_claim(e2["claim_id"])["corrected_adjudication_id"])
    for k in ("product_match", "warranty_version_match", "coverage_window", "covered_clause_ids", "exclusion_clause_ids",
              "evidence_sufficiency", "source_authority", "outcome", "decision_path"):
        assert a1[k] == a2[k], k


def test_a_correction_cannot_add_evidence_the_original_never_considered(direct_deploy, direct_vm, direct_accounts):
    env = corr_env(direct_deploy, direct_vm, direct_accounts, "IGNORED_EVIDENCE")
    for eid in (0, 3, 999):
        with pytest.raises(Exception, match="LLM_ERROR"):
            resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", {"evidence_ids_relied_on": [1, 2, eid]}))
    assert resolve(env, direct_vm, review(None, "DEFECT_CONFIRMED", {"evidence_ids_relied_on": [1, 2], "covered_clause_ids": ["C-001"]})) == "REVERSED"
    corr = env["contract"].get_adjudication(env["contract"].get_challenge_for_claim(env["claim_id"])["corrected_adjudication_id"])
    assert corr["evidence_ids_considered"] == [1, 2]
