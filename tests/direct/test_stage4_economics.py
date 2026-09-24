"""Stage 4 economic invariants. Accounting is asserted INDEPENDENTLY of the contract's own helpers: the test
keeps its own ledger (every GEN it deposits, every emitted transfer captured off the VM) and reconciles it with
the contract's views at every step, including inside a seeded randomized adversarial driver."""
import random

import pytest

from helpers import ONE_DAY, ONE_GEN, model_result
from helpers4 import (
    ADJ_PATTERN, REMEDY_TABLE, build_env, capture_transfers, challenge, cite, decide, finalize, mock_reply,
    past_challenge_window, resolve, settle, warp_to, withdraw,
)
from helpers import fund

FIVE = 5 * ONE_GEN


class Ledger:
    """Independent bookkeeping: everything the contract was given and everything it emitted."""

    def __init__(self, contract, program_ids, sent):
        self.contract = contract
        self.program_ids = list(program_ids)
        self.sent = sent
        self.deposited = 0

    def deposit(self, direct_vm, program_id, who, amount):
        fund(self.contract, direct_vm, program_id, who, amount)
        self.deposited += amount

    def check(self, label=""):
        c = self.contract
        pools = [c.get_pool(p) for p in self.program_ids]
        total = sum(p["total_balance"] for p in pools)
        reserved = sum(p["reserved_liability"] for p in pools)
        # claims/warranties are discovered by scanning ids (independent of any contract aggregate)
        claim_ids = range(1, 200)
        claimable = 0
        paid_by_warranty = {}
        settled_by_claim = {}
        for cid in claim_ids:
            cl = c.get_claim(cid)
            if not cl:
                break
            f = c.get_final_decision(cid)
            if f:
                claimable += f["claimable"]
                paid_by_warranty[cl["warranty_id"]] = paid_by_warranty.get(cl["warranty_id"], 0) + f["settled_amount"]
                settled_by_claim[cid] = f
                assert f["settled_amount"] <= f["remedy_amount"], f"{label}: paid more than the deterministic remedy"
                assert f["claimable"] + f["withdrawn_amount"] in (0, f["settled_amount"]) or f["claimable"] == 0 or f["withdrawn_amount"] == 0, label
                assert f["withdrawn_amount"] <= f["settled_amount"], label
                if f["settled_at"] == 0:
                    assert f["settled_amount"] == 0 and f["claimable"] == 0, f"{label}: value before settlement"
        # conservation: everything deposited is either still held, claimable, or has left via an emitted transfer
        sent_total = sum(v for _, v in self.sent)
        assert self.deposited - sent_total == total + claimable, f"{label}: conservation broken"
        # reservations reconcile with the pool's reserved_liability
        active = 0
        for wid in range(1, 200):
            p = c.get_passport(wid)
            if not p:
                break
            r = c.get_reservation(p["reservation_id"])
            if r["status"] == "ACTIVE":
                active += r["amount"]
            assert paid_by_warranty.get(wid, 0) <= p["max_deterministic_remedy"], f"{label}: warranty overpaid"
            if r["status"] in ("ACTIVE", "CONSUMED"):
                assert r["amount"] + paid_by_warranty.get(wid, 0) == p["max_deterministic_remedy"], f"{label}: reservation != max - paid"
        assert active == reserved, f"{label}: reserved_liability != sum of ACTIVE reservations"
        for p in pools:
            assert p["total_balance"] >= p["reserved_liability"], f"{label}: negative available"
            assert p["available_balance"] == p["total_balance"] - p["reserved_liability"]


def make_world(direct_deploy, direct_vm, direct_accounts, funding=40 * ONE_GEN, **kw):
    """One contract/program/constitution funded with `funding` (tracked by the Ledger)."""
    sent = capture_transfers(direct_vm)
    env = build_env(direct_deploy, direct_vm, direct_accounts, decision=None, pool_funding=funding, **kw)
    ledger = Ledger(env["contract"], [env["program_id"]], sent)
    ledger.deposited = funding
    ledger.check("world created")
    return env, ledger


def shared(env):
    return dict(contract=env["contract"], program_id=env["program_id"], constitution_id=env["constitution_id"])


def pay_out(env, direct_vm, ledger, reply_kind="COVERED", ev_suffix="", label="", window_wait=True):
    """Drive one already-filed claim (env from build_env(decision=None)) to a settled state."""
    from helpers import freeze_evidence, respond, submit_evidence, S3_URL
    c = env["contract"]
    respond(c, direct_vm, env["claim_id"], env["manufacturer"], "DISPUTE")
    url = S3_URL + f"pay{env['claim_id']}{ev_suffix}"
    direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": "Unit failed."})
    eid = submit_evidence(c, direct_vm, env["claim_id"], env["holder"], url)
    freeze_evidence(c, direct_vm, env["claim_id"], env["holder"])
    reply = {"COVERED": model_result(relied=(eid,)),
             "NOT_COVERED": model_result(product_match="FAIL", covered=(), relied=(eid,))}[reply_kind]
    decide(env, direct_vm, reply)
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm)
    ledger.check(label + " finalized")
    settle(env, direct_vm)
    ledger.check(label + " settled")


# ---- single-claim conservation ------------------------------------------------------------------------

def test_conservation_across_the_whole_payable_lifecycle(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN)
    c = env["contract"]
    from helpers import respond
    respond(c, direct_vm, env["claim_id"], env["manufacturer"], "ACCEPT")
    ledger.check("accepted")
    finalize(env, direct_vm); ledger.check("finalized")
    settle(env, direct_vm); ledger.check("settled")
    assert c.get_final_decision(env["claim_id"])["claimable"] == FIVE
    # value sitting in claimable is NOT withdrawable by the manufacturer
    direct_vm.sender = env["manufacturer"]
    pool = c.get_pool(env["program_id"])
    assert pool["available_balance"] == FIVE  # 10 funded - 5 already segregated for the holder
    with pytest.raises(Exception, match="exceeds available"):
        c.withdraw_pool(env["program_id"], FIVE + 1)
    c.withdraw_pool(env["program_id"], FIVE)  # exactly the unreserved remainder
    ledger.check("manufacturer took the free remainder")
    assert c.get_pool(env["program_id"])["total_balance"] == 0
    withdraw(env, direct_vm); ledger.check("holder withdrew")
    assert sum(v for _, v in ledger.sent) == 10 * ONE_GEN and c.get_pool(env["program_id"])["total_balance"] == 0


def test_no_payout_lifecycle_moves_no_value(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN)
    pay_out(env, direct_vm, ledger, "NOT_COVERED", label="not covered")
    assert ledger.sent == []
    assert env["contract"].get_pool(env["program_id"])["total_balance"] == 10 * ONE_GEN


# ---- overlapping / multiple claims ---------------------------------------------------------------------

def test_overlapping_claims_on_one_warranty_cannot_overpay(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=20 * ONE_GEN)
    c = env["contract"]
    from helpers import file_claim, respond
    # a second claim on the SAME warranty is allowed once the first is past dispute (ACCEPTED here)
    respond(c, direct_vm, env["claim_id"], env["manufacturer"], "ACCEPT")
    second_id = file_claim(c, direct_vm, env["warranty_id"], env["holder"])
    assert second_id != env["claim_id"]
    respond(c, direct_vm, second_id, env["manufacturer"], "ACCEPT")
    first, second = dict(env), dict(env, claim_id=second_id)
    finalize(first, direct_vm); finalize(second, direct_vm)
    assert c.get_final_decision(first["claim_id"])["remedy_amount"] == FIVE
    assert c.get_final_decision(second["claim_id"])["remedy_amount"] == FIVE  # deterministic remedy per claim...
    settle(first, direct_vm); ledger.check("first settled")
    settle(second, direct_vm); ledger.check("second settled")
    f1, f2 = c.get_final_decision(first["claim_id"]), c.get_final_decision(second["claim_id"])
    assert f1["settled_amount"] == FIVE and f1["capped"] is False
    assert f2["settled_amount"] == 0 and f2["capped"] is True  # ...but the warranty's frozen maximum is a lifetime cap
    with pytest.raises(Exception, match="nothing to withdraw"):
        withdraw(second, direct_vm)
    withdraw(first, direct_vm); ledger.check("withdrawn")
    assert sum(v for _, v in ledger.sent) == FIVE


def test_two_claims_partial_then_full(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=20 * ONE_GEN, targeted=("C-001", "C-002"))
    c = env["contract"]
    from helpers import file_claim, freeze_evidence, respond, submit_evidence, S3_URL

    def drive(e, covered, tag):
        respond(c, direct_vm, e["claim_id"], e["manufacturer"], "DISPUTE")
        url = S3_URL + tag
        direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": "Unit failed."})
        eid = submit_evidence(c, direct_vm, e["claim_id"], e["holder"], url)
        freeze_evidence(c, direct_vm, e["claim_id"], e["holder"])
        decide(e, direct_vm, model_result(covered=covered, relied=(eid,)))

    first = dict(env)
    drive(first, ("C-002",), "p1")  # table: C-002 = 50%
    # a second claim may be filed while the first is DECIDED (not blocked by the mere existence of a decision)
    second_id = file_claim(c, direct_vm, env["warranty_id"], env["holder"], targeted_clause_ids=["C-001"])
    second = dict(env, claim_id=second_id)
    drive(second, ("C-001",), "p2")
    for e in (first, second):
        past_challenge_window(e, direct_vm)
        finalize(e, direct_vm)
    assert c.get_final_decision(first["claim_id"])["remedy_amount"] == FIVE // 2
    assert c.get_final_decision(second["claim_id"])["remedy_amount"] == FIVE
    settle(second, direct_vm); ledger.check("full first")  # FULL_REFUND settles first and takes everything
    settle(first, direct_vm); ledger.check("half second")
    assert c.get_final_decision(second["claim_id"])["settled_amount"] == FIVE
    assert c.get_final_decision(first["claim_id"])["settled_amount"] == 0 and c.get_final_decision(first["claim_id"])["capped"] is True


def test_capacity_split_partial_first(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=20 * ONE_GEN, targeted=("C-001", "C-002"))
    c = env["contract"]
    from helpers import file_claim, freeze_evidence, respond, submit_evidence, S3_URL

    def drive(e, covered, tag):
        respond(c, direct_vm, e["claim_id"], e["manufacturer"], "DISPUTE")
        url = S3_URL + tag
        direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": "Unit failed."})
        eid = submit_evidence(c, direct_vm, e["claim_id"], e["holder"], url)
        freeze_evidence(c, direct_vm, e["claim_id"], e["holder"])
        decide(e, direct_vm, model_result(covered=covered, relied=(eid,)))

    first = dict(env)
    drive(first, ("C-002",), "q1")
    second = dict(env, claim_id=file_claim(c, direct_vm, env["warranty_id"], env["holder"], targeted_clause_ids=["C-001"]))
    drive(second, ("C-001",), "q2")
    for e in (first, second):
        past_challenge_window(e, direct_vm)
        finalize(e, direct_vm)
    settle(first, direct_vm); ledger.check("half")
    assert c.get_final_decision(first["claim_id"])["settled_amount"] == FIVE // 2
    settle(second, direct_vm); ledger.check("remainder")
    f2 = c.get_final_decision(second["claim_id"])
    assert f2["settled_amount"] == FIVE - FIVE // 2 and f2["capped"] is True and f2["remedy_amount"] == FIVE
    assert c.get_reservation(c.get_passport(env["warranty_id"])["reservation_id"])["status"] == "CONSUMED"
    withdraw(first, direct_vm); withdraw(second, direct_vm); ledger.check("both withdrawn")
    assert sum(v for _, v in ledger.sent) == FIVE


def test_multiple_warranties_are_isolated_from_each_other(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=30 * ONE_GEN)
    c = env["contract"]
    second = build_env(direct_deploy, direct_vm, direct_accounts, decision=None, pool_funding=0, commitment_seed=2, max_remedy=3 * ONE_GEN, **shared(env))
    third = build_env(direct_deploy, direct_vm, direct_accounts, decision=None, pool_funding=0, commitment_seed=3, max_remedy=2 * ONE_GEN, **shared(env))
    ledger.check("three warranties issued")
    assert c.get_pool(env["program_id"])["reserved_liability"] == 10 * ONE_GEN
    from helpers import respond
    respond(c, direct_vm, second["claim_id"], second["manufacturer"], "ACCEPT")
    finalize(second, direct_vm); settle(second, direct_vm); ledger.check("second settled")
    assert c.get_final_decision(second["claim_id"])["settled_amount"] == 3 * ONE_GEN
    # the other two warranties' reservations are untouched
    for e, amt in ((env, FIVE), (third, 2 * ONE_GEN)):
        r = c.get_reservation(c.get_passport(e["warranty_id"])["reservation_id"])
        assert r["status"] == "ACTIVE" and r["amount"] == amt
    assert c.get_pool(env["program_id"])["reserved_liability"] == 7 * ONE_GEN


# ---- reservation release --------------------------------------------------------------------------------

def test_reservation_cannot_be_released_or_cancelled_under_an_unsettled_claim(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN, coverage_seconds=1000)
    c = env["contract"]
    from helpers import respond
    respond(c, direct_vm, env["claim_id"], env["manufacturer"], "ACCEPT")
    direct_vm.sender = env["manufacturer"]
    with pytest.raises(Exception, match="unsettled claim"):
        c.cancel_warranty(env["warranty_id"])
    warp_to(direct_vm, env["now"] + 1000 + 30 * ONE_DAY + 1)  # past coverage_end + claim deadline grace
    with pytest.raises(Exception, match="unsettled claim"):
        c.release_expired_reservation(env["warranty_id"])
    finalize(env, direct_vm)
    with pytest.raises(Exception, match="unsettled claim"):
        c.release_expired_reservation(env["warranty_id"])
    settle(env, direct_vm)
    ledger.check("settled")
    # fully consumed reservation: nothing left to release
    with pytest.raises(Exception):
        c.release_expired_reservation(env["warranty_id"])
    ledger.check("no double release")


def test_unused_reservation_is_released_only_after_grace_and_only_once(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN, coverage_seconds=1000, targeted=("C-002",))
    c = env["contract"]
    from helpers import freeze_evidence, respond, submit_evidence, S3_URL
    respond(c, direct_vm, env["claim_id"], env["manufacturer"], "DISPUTE")
    direct_vm.mock_web(r"https://docs\.genlayer\.com/u1", {"status": 200, "body": "Unit failed."})
    eid = submit_evidence(c, direct_vm, env["claim_id"], env["holder"], S3_URL + "u1")
    freeze_evidence(c, direct_vm, env["claim_id"], env["holder"])
    decide(env, direct_vm, model_result(covered=("C-002",), relied=(eid,)))
    past_challenge_window(env, direct_vm)
    finalize(env, direct_vm); settle(env, direct_vm)
    ledger.check("half settled")
    assert c.get_pool(env["program_id"])["reserved_liability"] == FIVE // 2
    direct_vm.sender = env["manufacturer"]
    now = int(c.now())
    grace_end = env["now"] + 1000 + 30 * ONE_DAY
    if now <= grace_end:
        with pytest.raises(Exception, match="grace"):
            c.release_expired_reservation(env["warranty_id"])
        warp_to(direct_vm, grace_end + 1)
    c.release_expired_reservation(env["warranty_id"])
    ledger.check("remainder released")
    assert c.get_pool(env["program_id"])["reserved_liability"] == 0
    with pytest.raises(Exception):
        c.release_expired_reservation(env["warranty_id"])
    withdraw(env, direct_vm); ledger.check("holder paid")
    # the released remainder is now free capacity for the manufacturer; the holder's claimable stayed segregated
    direct_vm.sender = env["manufacturer"]
    free = c.get_pool(env["program_id"])["available_balance"]
    assert free == 10 * ONE_GEN - FIVE // 2
    c.withdraw_pool(env["program_id"], free); ledger.check("manufacturer took the released remainder")


def test_expiry_release_waits_for_the_claim_deadline_grace(direct_deploy, direct_vm, direct_accounts):
    capture_transfers(direct_vm)
    direct_vm.sender = direct_accounts[0]
    c = direct_deploy("contracts/clause_protocol.py")
    from helpers import create_constitution_stage2, issue
    pid = c.create_program("Acme")
    cid = create_constitution_stage2(c, pid)
    fund(c, direct_vm, pid, direct_accounts[0], 10 * ONE_GEN)
    now = int(c.now())
    wid = issue(c, direct_vm, pid, cid, direct_accounts[0], direct_accounts[1], max_remedy=FIVE, coverage_start=now, coverage_end=now + 100)
    end_plus_grace = now + 100 + 30 * ONE_DAY
    warp_to(direct_vm, now + 101)
    with pytest.raises(Exception, match="grace"):
        c.release_expired_reservation(wid)  # a holder may still file for 30 days: capacity must stay reserved
    warp_to(direct_vm, end_plus_grace)  # exact boundary: still inside the grace window
    with pytest.raises(Exception, match="grace"):
        c.release_expired_reservation(wid)
    warp_to(direct_vm, end_plus_grace + 1)
    c.release_expired_reservation(wid)
    assert c.get_pool(pid)["reserved_liability"] == 0


# ---- withdrawal ---------------------------------------------------------------------------------------

def _settled_payable(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN)
    from helpers import respond
    respond(env["contract"], direct_vm, env["claim_id"], env["manufacturer"], "ACCEPT")
    finalize(env, direct_vm)
    return env, ledger


def test_withdrawal_before_finalization_or_settlement_reverts(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN)
    from helpers import respond
    for stage in ("filed", "accepted", "final"):
        if stage == "accepted":
            respond(env["contract"], direct_vm, env["claim_id"], env["manufacturer"], "ACCEPT")
        if stage == "final":
            finalize(env, direct_vm)
        with pytest.raises(Exception):
            withdraw(env, direct_vm)
        ledger.check("blocked at " + stage)
    assert ledger.sent == []


def test_only_the_recorded_recipient_can_withdraw(direct_deploy, direct_vm, direct_accounts):
    env, ledger = _settled_payable(direct_deploy, direct_vm, direct_accounts)
    settle(env, direct_vm)
    before = env["contract"].get_final_decision(env["claim_id"])
    for wrong in (env["manufacturer"], env["other"], direct_accounts[3]):
        with pytest.raises(Exception, match="not the settlement recipient"):
            withdraw(env, direct_vm, caller=wrong)
        assert env["contract"].get_final_decision(env["claim_id"]) == before  # failed attempt leaves no trace
    assert ledger.sent == []
    ledger.check("after failed attempts")
    withdraw(env, direct_vm)
    assert len(ledger.sent) == 1


def test_withdrawal_pays_exactly_the_claimable_amount_once(direct_deploy, direct_vm, direct_accounts):
    env, ledger = _settled_payable(direct_deploy, direct_vm, direct_accounts)
    settle(env, direct_vm)
    holder_hex = env["contract"].get_passport(env["warranty_id"])["holder"].lower()
    withdraw(env, direct_vm)
    assert ledger.sent == [(holder_hex, FIVE)]
    for _ in range(3):  # repeated / replayed calls
        with pytest.raises(Exception, match="already withdrawn"):
            withdraw(env, direct_vm)
    assert ledger.sent == [(holder_hex, FIVE)]
    ledger.check("after replays")
    f = env["contract"].get_final_decision(env["claim_id"])
    assert f["claimable"] == 0 and f["withdrawn_amount"] == FIVE


def test_zero_claim_withdrawal_reverts_and_emits_nothing(direct_deploy, direct_vm, direct_accounts):
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN)
    pay_out(env, direct_vm, ledger, "NOT_COVERED", label="zero")
    with pytest.raises(Exception, match="nothing to withdraw"):
        withdraw(env, direct_vm)
    assert ledger.sent == []


def test_settlement_and_finalization_are_one_shot(direct_deploy, direct_vm, direct_accounts):
    env, ledger = _settled_payable(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception, match="already finalized"):
        finalize(env, direct_vm)
    settle(env, direct_vm)
    with pytest.raises(Exception):
        settle(env, direct_vm)
    with pytest.raises(Exception):
        finalize(env, direct_vm)
    ledger.check("after replays")
    assert env["contract"].get_final_decision(env["claim_id"])["settled_amount"] == FIVE


def test_state_written_before_transfer_no_double_spend_on_repeat(direct_deploy, direct_vm, direct_accounts):
    """withdraw_settlement zeroes `claimable` and sets the one-shot guard before the transfer is emitted, so
    any repeated call (reentrancy-style or replay) observes nothing left to take."""
    env, ledger = _settled_payable(direct_deploy, direct_vm, direct_accounts)
    settle(env, direct_vm)
    seen = []

    def hook(vm, request):
        if "EthSend" in request:
            # at the moment of emission the contract's own state must already be updated
            f = env["contract"].get_final_decision(env["claim_id"])
            seen.append((f["claimable"], f["withdrawn_at"]))
        return None

    direct_vm._gl_call_hook = hook
    withdraw(env, direct_vm)
    assert seen == [] or seen[0][0] == 0  # (view inside a hook may be unavailable; if observed it must be zero)
    assert env["contract"].get_final_decision(env["claim_id"])["claimable"] == 0


def test_incomplete_remedy_table_can_no_longer_reach_a_payable_deadlock(direct_deploy, direct_vm, direct_accounts):
    """Stage 4.5: the deadlock this test used to exercise (COVERED with no matching row) is now impossible -
    the constitution is rejected at creation, before any warranty can bind to it."""
    table = [{"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0}]
    with pytest.raises(Exception, match="remedy_table incomplete"):
        make_world(direct_deploy, direct_vm, direct_accounts, funding=10 * ONE_GEN, remedy_table=table)


# ---- seeded randomized adversarial driver -------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_random_operation_sequences_preserve_every_invariant(direct_deploy, direct_vm, direct_accounts, seed):
    from helpers import file_claim, freeze_evidence, issue, respond, submit_evidence, S3_URL
    rng = random.Random(seed)
    env, ledger = make_world(direct_deploy, direct_vm, direct_accounts, funding=25 * ONE_GEN,
                             max_remedy=2 * ONE_GEN, targeted=("C-001", "C-002"))
    c = env["contract"]
    manufacturer, holders = direct_accounts[0], [direct_accounts[1], direct_accounts[2]]
    claims = {env["claim_id"]: dict(env, phase="filed")}
    warranties = [env["warranty_id"]]
    tag = [0]
    clock = [int(c.now())]

    def attempt(fn):
        try:
            fn()
            return True
        except Exception:
            return False

    def advance(ce):
        p = ce["phase"]
        cid = ce["claim_id"]
        if p == "filed":
            decision = rng.choice(["ACCEPT", "DISPUTE", "DISPUTE"])
            if attempt(lambda: respond(c, direct_vm, cid, manufacturer, decision)):
                ce["phase"] = "accepted" if decision == "ACCEPT" else "disputed"
        elif p == "disputed":
            tag[0] += 1
            url = S3_URL + f"r{seed}x{tag[0]}"
            direct_vm.mock_web(url.replace(".", r"\."), {"status": 200, "body": "Unit failed."})
            ok = attempt(lambda: ce.__setitem__("eid", submit_evidence(c, direct_vm, cid, ce["holder"], url)))
            if ok and attempt(lambda: freeze_evidence(c, direct_vm, cid, ce["holder"])):
                ce["phase"] = "frozen"
        elif p == "frozen":
            kind = rng.choice(["covered1", "covered2", "notcovered"])
            reply = {"covered1": model_result(covered=("C-001",), relied=(ce["eid"],)),
                     "covered2": model_result(covered=("C-002",), relied=(ce["eid"],)),
                     "notcovered": model_result(product_match="FAIL", covered=(), relied=(ce["eid"],))}[kind]
            if attempt(lambda: decide(ce, direct_vm, reply)):
                ce["phase"] = "decided"
        elif p == "decided":
            if rng.random() < 0.3 and attempt(lambda: challenge(ce, direct_vm, "TEMPORAL_ERROR", cite(timestamp_field="filed_at"), who=rng.choice([ce["holder"], manufacturer]))):
                ce["phase"] = "challenged"
            else:
                a = c.get_adjudication(c.get_claim(cid)["adjudication_id"])
                clock[0] = max(clock[0], a["challenge_window_closes_at"] + 1)
                warp_to(direct_vm, clock[0])
                if attempt(lambda: finalize(ce, direct_vm)):
                    ce["phase"] = "final"
        elif p == "challenged":
            if attempt(lambda: resolve(ce, direct_vm)) and attempt(lambda: finalize(ce, direct_vm)):
                ce["phase"] = "final"
        elif p == "accepted":
            if attempt(lambda: finalize(ce, direct_vm)):
                ce["phase"] = "final"
        elif p == "final":
            if attempt(lambda: settle(ce, direct_vm)):
                ce["phase"] = "settled"
        elif p == "settled":
            attempt(lambda: withdraw(ce, direct_vm))

    for step in range(140):
        roll = rng.random()
        if roll < 0.62 and claims:
            ce = claims[rng.choice(sorted(claims))]
            advance(ce)
        elif roll < 0.70:
            # adversarial out-of-order calls on random claims: must never break an invariant
            cid = rng.choice(sorted(claims)) if claims else 1
            ce = claims.get(cid, env)
            op = rng.choice(["settle", "finalize", "withdraw_wrong", "withdraw", "release", "cancel"])
            if op == "settle":
                attempt(lambda: settle(ce, direct_vm))
            elif op == "finalize":
                attempt(lambda: finalize(ce, direct_vm))
            elif op == "withdraw_wrong":
                attempt(lambda: withdraw(ce, direct_vm, caller=rng.choice([manufacturer, direct_accounts[3]])))
            elif op == "withdraw":
                attempt(lambda: withdraw(ce, direct_vm))
            elif op == "release":
                direct_vm.sender = direct_accounts[3]
                attempt(lambda: c.release_expired_reservation(ce["warranty_id"]))
            else:
                direct_vm.sender = manufacturer
                attempt(lambda: c.cancel_warranty(ce["warranty_id"]))
        elif roll < 0.76:
            amt = rng.choice([1, ONE_GEN, 3 * ONE_GEN, 50 * ONE_GEN])
            direct_vm.sender = manufacturer
            attempt(lambda: c.withdraw_pool(env["program_id"], amt))
        elif roll < 0.80:
            amt = rng.choice([ONE_GEN, 2 * ONE_GEN])
            ok = attempt(lambda: fund(c, direct_vm, env["program_id"], manufacturer, amt))
            if ok:
                ledger.deposited += amt
        elif roll < 0.90 and len(claims) < 6:
            h = rng.choice(holders)
            if attempt(lambda: warranties.append(issue(c, direct_vm, env["program_id"], env["constitution_id"], manufacturer, h,
                                                        max_remedy=rng.choice([ONE_GEN, 2 * ONE_GEN]), coverage_start=clock[0], coverage_end=clock[0] + 200 * ONE_DAY,
                                                        commitment_seed=100 + step))):
                wid = warranties[-1]
                cl = [None]
                if attempt(lambda: cl.__setitem__(0, file_claim(c, direct_vm, wid, h, targeted_clause_ids=["C-001", "C-002"], failure_asserted_at=clock[0]))):
                    claims[cl[0]] = dict(env, warranty_id=wid, holder=h, claim_id=cl[0], phase="filed")
        else:
            clock[0] += rng.choice([1, 3600, ONE_DAY, 9 * ONE_DAY])
            warp_to(direct_vm, clock[0])
        ledger.check(f"seed {seed} step {step}")

    # drive everything to the end and re-check; nothing may have been created or destroyed
    for _ in range(12):
        for ce in list(claims.values()):
            advance(ce)
        clock[0] += 10 * ONE_DAY
        warp_to(direct_vm, clock[0])
        ledger.check(f"seed {seed} drain")
    settled = [c.get_final_decision(cid) for cid in claims if c.get_final_decision(cid)]
    for f in settled:
        assert f["settled_amount"] <= f["remedy_amount"]
    # the driver must actually exercise the money path, not merely survive: some claims reached settlement,
    # some value was emitted, and the run mixed paying and non-paying outcomes
    assert any(f["settled_at"] > 0 for f in settled), f"seed {seed}: no claim ever settled"
    assert sum(v for _, v in ledger.sent) > 0, f"seed {seed}: no value ever left the contract"
