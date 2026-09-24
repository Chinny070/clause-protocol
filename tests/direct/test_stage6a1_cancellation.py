"""Stage 6A.1 - V1 cancellation policy: an issued warranty is a commitment. The manufacturer can NOT cancel it (not
immediately, not after a failure, not in the claim grace period, not via program pause/retire); only the holder can.
Existing claim/reservation protections and frozen terms are unchanged."""
import pytest

from helpers import ONE_DAY, ONE_GEN, S3_COVERED, S3_EXCLUDED, create_constitution_stage2, file_claim, fund, issue, respond
from helpers4 import REMEDY_TABLE, capture_transfers, finalize, settle, warp_to, withdraw

FIVE = 5 * ONE_GEN
COV = 1000
GRACE = 30 * ONE_DAY


def world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=COV, pool_funding=10 * ONE_GEN, commitment_seed=1, contract=None,
          program_id=None, constitution_id=None):
    """Program -> funded pool -> ONE issued warranty with NO claim (build_env always files a claim, which would mask the cases here)."""
    m, h = direct_accounts[0], direct_accounts[1]
    if contract is None:
        direct_vm.sender = m
        contract = direct_deploy("contracts/clause_protocol.py")
        program_id = contract.create_program("Acme")
        constitution_id = create_constitution_stage2(contract, program_id, covered_clauses=S3_COVERED, excluded_clauses=S3_EXCLUDED,
                                                     source_policy="docs.genlayer.com", evidence_categories=["RECEIPT"], remedy_table=REMEDY_TABLE)
        fund(contract, direct_vm, program_id, m, pool_funding)
    now = int(contract.now())
    wid = issue(contract, direct_vm, program_id, constitution_id, m, h, max_remedy=FIVE, coverage_start=now, coverage_end=now + coverage_seconds,
                commitment_seed=commitment_seed)
    return {"contract": contract, "manufacturer": m, "holder": h, "other": direct_accounts[2], "program_id": program_id,
            "constitution_id": constitution_id, "warranty_id": wid, "now": now}


def try_cancel(env, direct_vm, who):
    direct_vm.sender = who
    env["contract"].cancel_warranty(env["warranty_id"])


def passport(env):
    return env["contract"].get_passport(env["warranty_id"])


def reservation(env):
    c = env["contract"]
    return c.get_reservation(passport(env)["reservation_id"])


def assert_untouched(env, before):
    """Passport, reservation and pool are exactly as before a rejected cancellation."""
    c = env["contract"]
    assert passport(env) == before["passport"]
    assert reservation(env) == before["reservation"]
    assert c.get_pool(env["program_id"]) == before["pool"]


def snapshot(env):
    c = env["contract"]
    return {"passport": passport(env), "reservation": reservation(env), "pool": c.get_pool(env["program_id"])}


# ---- the manufacturer can never cancel an issued warranty ----------------------------------------------------

def test_manufacturer_cannot_cancel_immediately_after_issuance(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts)
    before = snapshot(env)
    with pytest.raises(Exception, match="only the holder can cancel"):
        try_cancel(env, direct_vm, env["manufacturer"])
    assert_untouched(env, before)
    assert passport(env)["status"] == "ACTIVE" and reservation(env)["status"] == "ACTIVE"


def test_manufacturer_cannot_cancel_after_a_failure_but_before_claim_filing(direct_deploy, direct_vm, direct_accounts):
    """The product fails (time passes, the holder has not filed yet): the manufacturer still cannot walk away."""
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY)
    before = snapshot(env)
    for dt in (60, ONE_DAY, 30 * ONE_DAY, 200 * ONE_DAY):
        warp_to(direct_vm, env["now"] + dt)
        with pytest.raises(Exception, match="only the holder can cancel"):
            try_cancel(env, direct_vm, env["manufacturer"])
    assert_untouched(env, before)
    # ...and the holder can still file and be paid
    respond_env = file_claim(env["contract"], direct_vm, env["warranty_id"], env["holder"], failure_asserted_at=env["now"] + 100)
    respond(env["contract"], direct_vm, respond_env, env["manufacturer"], "ACCEPT")
    e2 = dict(env, claim_id=respond_env)
    finalize(e2, direct_vm)
    settle(e2, direct_vm)
    assert env["contract"].get_final_decision(respond_env)["claimable"] == FIVE


def test_manufacturer_cannot_cancel_during_the_claim_grace_period_and_holder_can_still_claim(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts)
    c = env["contract"]
    end = env["now"] + COV
    for t in (end + 1, end + GRACE):  # coverage over, grace open (exact boundary included)
        warp_to(direct_vm, t)
        assert passport(env)["status"] == "EXPIRED"
        before = snapshot(env)
        with pytest.raises(Exception):
            try_cancel(env, direct_vm, env["manufacturer"])
        assert_untouched(env, before)
        assert reservation(env)["status"] == "ACTIVE" and reservation(env)["amount"] == FIVE
    # the holder still files inside the grace window and the reservation still backs the payout
    cid = file_claim(c, direct_vm, env["warranty_id"], env["holder"], failure_asserted_at=end - 5)
    respond(c, direct_vm, cid, env["manufacturer"], "ACCEPT")
    e2 = dict(env, claim_id=cid)
    finalize(e2, direct_vm)
    settle(e2, direct_vm)
    assert c.get_final_decision(cid)["settled_amount"] == FIVE


def test_a_stranger_cannot_cancel_either(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts)
    before = snapshot(env)
    with pytest.raises(Exception, match="only the holder can cancel"):
        try_cancel(env, direct_vm, env["other"])
    assert_untouched(env, before)


def test_manufacturer_still_cannot_cancel_once_every_claim_is_settled(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY, pool_funding=20 * ONE_GEN)
    c = env["contract"]
    cid = file_claim(c, direct_vm, env["warranty_id"], env["holder"])
    respond(c, direct_vm, cid, env["manufacturer"], "ACCEPT")
    e2 = dict(env, claim_id=cid)
    finalize(e2, direct_vm)
    settle(e2, direct_vm)
    with pytest.raises(Exception, match="only the holder can cancel"):
        try_cancel(env, direct_vm, env["manufacturer"])


# ---- program pause / retirement never touches issued warranties -----------------------------------------------

def test_pause_and_retire_do_not_cancel_shorten_or_rewrite_issued_warranties(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY)
    c = env["contract"]
    constitution_before = c.get_constitution(env["constitution_id"])
    before = snapshot(env)
    direct_vm.sender = env["manufacturer"]
    c.pause_program(env["program_id"])
    assert passport(env) == before["passport"] and reservation(env) == before["reservation"]
    c.resume_program(env["program_id"])
    c.retire_program(env["program_id"])
    assert c.get_program(env["program_id"])["status"] == "RETIRED"
    assert passport(env) == before["passport"]  # status, coverage window, fingerprint, max remedy all unchanged
    assert reservation(env) == before["reservation"] and c.get_pool(env["program_id"])["reserved_liability"] == FIVE
    assert c.get_constitution(env["constitution_id"]) == constitution_before  # frozen terms untouched


def test_an_issued_warranty_completes_its_whole_lifecycle_after_the_program_is_retired(direct_deploy, direct_vm, direct_accounts):
    sent = capture_transfers(direct_vm)
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY)
    c = env["contract"]
    direct_vm.sender = env["manufacturer"]
    c.pause_program(env["program_id"])
    c.resume_program(env["program_id"])
    c.retire_program(env["program_id"])
    cid = file_claim(c, direct_vm, env["warranty_id"], env["holder"])  # claiming is unaffected by retirement
    respond(c, direct_vm, cid, env["manufacturer"], "ACCEPT")
    e2 = dict(env, claim_id=cid)
    finalize(e2, direct_vm)
    settle(e2, direct_vm)
    withdraw(e2, direct_vm)
    assert len(sent) == 1 and sent[0][1] == FIVE
    assert c.get_final_decision(cid)["withdrawn_amount"] == FIVE


def test_pause_and_retire_still_stop_future_issuance_and_new_terms(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY, pool_funding=20 * ONE_GEN)
    c = env["contract"]
    m, h = env["manufacturer"], env["holder"]
    direct_vm.sender = m
    c.pause_program(env["program_id"])
    with pytest.raises(Exception, match="not ACTIVE"):
        issue(c, direct_vm, env["program_id"], env["constitution_id"], m, h, commitment_seed=50)
    c.resume_program(env["program_id"])
    issue(c, direct_vm, env["program_id"], env["constitution_id"], m, h, commitment_seed=51)  # resumed: issuance works again
    direct_vm.sender = m
    c.retire_program(env["program_id"])
    with pytest.raises(Exception, match="not ACTIVE"):
        issue(c, direct_vm, env["program_id"], env["constitution_id"], m, h, commitment_seed=52)
    with pytest.raises(Exception, match="RETIRED"):
        create_constitution_stage2(c, env["program_id"], version="after-retire", covered_clauses=S3_COVERED, excluded_clauses=S3_EXCLUDED,
                                   source_policy="docs.genlayer.com", evidence_categories=["RECEIPT"], remedy_table=REMEDY_TABLE)


def test_a_retired_program_cannot_release_capacity_backing_issued_warranties(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY)
    c = env["contract"]
    direct_vm.sender = env["manufacturer"]
    c.retire_program(env["program_id"])
    free = c.get_pool(env["program_id"])["available_balance"]
    with pytest.raises(Exception, match="exceeds available"):
        c.withdraw_pool(env["program_id"], free + 1)  # reserved capacity is untouchable
    direct_vm.sender = env["other"]
    with pytest.raises(Exception, match="not expired"):
        c.release_expired_reservation(env["warranty_id"])
    assert reservation(env)["status"] == "ACTIVE"


# ---- holder cancellation (V1 rules) ---------------------------------------------------------------------------

def test_holder_can_cancel_their_own_active_warranty_and_capacity_returns_to_the_pool(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY)
    c = env["contract"]
    try_cancel(env, direct_vm, env["holder"])
    assert passport(env)["status"] == "CANCELLED"
    assert reservation(env)["status"] == "RELEASED"
    pool = c.get_pool(env["program_id"])
    assert pool["reserved_liability"] == 0 and pool["available_balance"] == pool["total_balance"]
    with pytest.raises(Exception):  # cancelled warranties accept no new claims
        file_claim(c, direct_vm, env["warranty_id"], env["holder"])
    with pytest.raises(Exception, match="not ACTIVE"):
        try_cancel(env, direct_vm, env["holder"])  # cannot cancel twice


def test_holder_cancellation_is_blocked_while_a_claim_is_unsettled(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY, pool_funding=20 * ONE_GEN)
    c = env["contract"]
    cid = file_claim(c, direct_vm, env["warranty_id"], env["holder"])
    with pytest.raises(Exception, match="unsettled claim"):
        try_cancel(env, direct_vm, env["holder"])
    respond(c, direct_vm, cid, env["manufacturer"], "ACCEPT")
    e2 = dict(env, claim_id=cid)
    finalize(e2, direct_vm)
    with pytest.raises(Exception, match="unsettled claim"):
        try_cancel(env, direct_vm, env["holder"])
    settle(e2, direct_vm)
    # every claim is settled, so the unsettled-claim guard no longer applies. This warranty's whole reservation was consumed
    # by the payout, so there is nothing left to release and the (pre-existing, unchanged) release step reverts atomically.
    with pytest.raises(Exception, match="reservation is not ACTIVE"):
        try_cancel(env, direct_vm, env["holder"])
    # (a reverted transaction is atomic on GenVM; gltest direct mode does not roll storage back, so state is not asserted here)


def test_a_holder_cannot_cancel_an_expired_warranty(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts)
    warp_to(direct_vm, env["now"] + COV + 5)
    with pytest.raises(Exception, match="not ACTIVE"):
        try_cancel(env, direct_vm, env["holder"])


def test_cancelling_one_warranty_does_not_touch_another(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY, pool_funding=20 * ONE_GEN)
    other = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY, commitment_seed=9,
                  contract=env["contract"], program_id=env["program_id"], constitution_id=env["constitution_id"])
    other_before = env["contract"].get_passport(other["warranty_id"])
    try_cancel(env, direct_vm, env["holder"])
    assert env["contract"].get_passport(other["warranty_id"]) == other_before
    assert env["contract"].get_reservation(other_before["reservation_id"])["status"] == "ACTIVE"
    with pytest.raises(Exception, match="only the holder can cancel"):
        direct_vm.sender = env["manufacturer"]
        env["contract"].cancel_warranty(other["warranty_id"])


def test_terms_and_fingerprint_survive_every_permitted_operation(direct_deploy, direct_vm, direct_accounts):
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY)
    c = env["contract"]
    terms = c.get_constitution(env["constitution_id"])
    fp = passport(env)["constitution_fingerprint"]
    direct_vm.sender = env["manufacturer"]
    c.pause_program(env["program_id"])
    c.retire_program(env["program_id"])
    try_cancel(env, direct_vm, env["holder"])
    assert c.get_constitution(env["constitution_id"]) == terms and terms["is_frozen"] is True
    assert passport(env)["constitution_fingerprint"] == fp == terms["fingerprint"]


def test_holder_can_cancel_after_a_partial_settlement_and_the_remainder_is_released(direct_deploy, direct_vm, direct_accounts):
    """A claim settled for LESS than the maximum leaves reservation behind; the holder's cancellation then releases it."""
    env = world(direct_deploy, direct_vm, direct_accounts, coverage_seconds=365 * ONE_DAY)
    c = env["contract"]
    # NOT_COVERED path: settle pays nothing, the whole reservation remains
    from helpers import freeze_evidence, model_result, submit_evidence, S3_URL
    from helpers4 import decide, past_challenge_window
    cid = file_claim(c, direct_vm, env["warranty_id"], env["holder"], failure_asserted_at=env["now"] - 10 * ONE_DAY)  # window FAIL -> NOT_COVERED
    respond(c, direct_vm, cid, env["manufacturer"], "DISPUTE")
    direct_vm.mock_web(r"https://docs\.genlayer\.com/x1", {"status": 200, "body": "Unit failed."})
    submit_evidence(c, direct_vm, cid, env["holder"], S3_URL + "x1")
    freeze_evidence(c, direct_vm, cid, env["holder"])
    e2 = dict(env, claim_id=cid)
    decide(e2, direct_vm)
    past_challenge_window(e2, direct_vm)
    finalize(e2, direct_vm)
    settle(e2, direct_vm)
    assert c.get_final_decision(cid)["claimable"] == 0 and reservation(env)["amount"] == FIVE
    try_cancel(env, direct_vm, env["holder"])
    assert passport(env)["status"] == "CANCELLED" and c.get_pool(env["program_id"])["reserved_liability"] == 0
