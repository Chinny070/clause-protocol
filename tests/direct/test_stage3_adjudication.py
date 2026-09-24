"""Stage 3: semantic fixtures, deterministic short-circuits, outcome derivation, state
transition, counterfactual independence. The model is MOCKED here (direct mode); no test in
this file claims live model consensus - see STAGE_3_VERIFICATION.md for what is/isn't verified."""
import pytest

from helpers import (
    ONE_GEN, adjudicate, build_frozen_claim, mock_model, model_result,
)


def _run(direct_deploy, direct_vm, direct_accounts, reply=None, **kw):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts, **kw)
    if reply is not None:
        mock_model(direct_vm, reply)
    aid = adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    return env, env["contract"].get_adjudication(aid)


# ---- the eight controlled semantic fixtures ---------------------------------------------------

def test_clearly_covered(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, model_result())
    assert a["outcome"] == "COVERED"
    assert (a["product_match"], a["warranty_version_match"], a["coverage_window"]) == ("PASS", "PASS", "PASS")
    assert a["covered_clause_ids"] == ["C-001"] and a["exclusion_clause_ids"] == []
    assert a["evidence_sufficiency"] == "SUFFICIENT" and a["source_authority"] == "PASS"
    assert a["evidence_ids_relied_on"] == [1] and a["decision_path"] == "SEMANTIC"


def test_clearly_not_covered_sufficient_evidence_but_no_covered_condition(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, model_result(covered=()))
    assert a["outcome"] == "NOT_COVERED" and a["evidence_sufficiency"] == "SUFFICIENT"


def test_insufficient_evidence(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts,
                  model_result(product_match="UNCLEAR", covered=(), sufficiency="INSUFFICIENT", relied=()))
    assert a["outcome"] == "INSUFFICIENT_EVIDENCE" and a["source_authority"] == "UNCLEAR"


def test_evidence_unavailable_is_deterministic_and_never_calls_the_model(direct_deploy, direct_vm, direct_accounts):
    # No LLM mock registered at all: any model call would raise and the adjudication would revert.
    env, a = _run(direct_deploy, direct_vm, direct_accounts, evidence=[("gone", 404, "")])
    assert a["outcome"] == "EVIDENCE_UNAVAILABLE"
    assert a["decision_path"] == "DETERMINISTIC_EVIDENCE_UNAVAILABLE" and a["evidence_sufficiency"] == "UNAVAILABLE"


def test_no_admissible_evidence_is_deterministic_insufficient(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, evidence=[])
    assert a["outcome"] == "INSUFFICIENT_EVIDENCE" and a["decision_path"] == "DETERMINISTIC_NO_ADMISSIBLE_EVIDENCE"


def test_only_ineligible_evidence_is_treated_as_no_admissible_evidence(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, evidence=[("https://evil.example/x", None, "")])
    assert a["outcome"] == "INSUFFICIENT_EVIDENCE" and a["evidence_ids_considered"] == []


def test_wrong_product(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, model_result(product_match="FAIL", covered=()))
    assert a["outcome"] == "NOT_COVERED" and a["product_match"] == "FAIL"


def test_outside_coverage_window_is_deterministic(direct_deploy, direct_vm, direct_accounts):
    # failure asserted 10 days BEFORE coverage_start; no model reply registered => model never consulted
    env, a = _run(direct_deploy, direct_vm, direct_accounts, failure_offset_s=-10 * 86400)
    assert a["outcome"] == "NOT_COVERED" and a["coverage_window"] == "FAIL"
    assert a["decision_path"] == "DETERMINISTIC_PREDICATE"


def test_exclusion_established(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts,
                  model_result(covered=(), exclusions=("X-001",)))
    assert a["outcome"] == "NOT_COVERED" and a["exclusion_clause_ids"] == ["X-001"]


def test_exclusion_beats_a_simultaneously_established_covered_clause(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, model_result(exclusions=("X-001",)))
    assert a["outcome"] == "NOT_COVERED"
    assert a["covered_clause_ids"] == ["C-001"] and a["exclusion_clause_ids"] == ["X-001"]


def test_ambiguous_fails_safe_and_is_never_forced_into_covered(direct_deploy, direct_vm, direct_accounts):
    # product UNCLEAR with otherwise SUFFICIENT evidence must not become COVERED (derivation rule 5)
    env, a = _run(direct_deploy, direct_vm, direct_accounts,
                  model_result(product_match="UNCLEAR", covered=(), sufficiency="SUFFICIENT"))
    assert a["outcome"] == "INSUFFICIENT_EVIDENCE"


# ---- outcome derivation table, exhaustively (pure function via contract behaviour) -------------

@pytest.mark.parametrize("reply, expected", [
    (model_result(), "COVERED"),
    (model_result(covered=()), "NOT_COVERED"),
    (model_result(product_match="FAIL", covered=()), "NOT_COVERED"),
    (model_result(product_match="UNCLEAR", covered=()), "INSUFFICIENT_EVIDENCE"),
    (model_result(covered=(), exclusions=("X-001",)), "NOT_COVERED"),
    (model_result(product_match="UNCLEAR", covered=(), sufficiency="INSUFFICIENT", relied=()), "INSUFFICIENT_EVIDENCE"),
])
def test_outcome_derivation_table(direct_deploy, direct_vm, direct_accounts, reply, expected):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, reply)
    assert a["outcome"] == expected


# ---- state transition, preconditions, no money ------------------------------------------------

def test_accepted_adjudication_advances_claim_and_stores_challenge_window_data(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, model_result(), challenge_window_s=3 * 86400)
    claim = env["contract"].get_claim(env["claim_id"])
    assert claim["status"] == "DECIDED" and claim["adjudication_id"] == a["adjudication_id"]
    assert a["challenge_window_closes_at"] == a["adjudicated_at"] + 3 * 86400
    assert a["superseded"] is False and a["constitution_id"] == env["constitution_id"]


def test_adjudication_moves_no_money_and_releases_no_reservation(direct_deploy, direct_vm, direct_accounts):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    c = env["contract"]
    pool_before = c.get_pool(env["program_id"])
    reservation_before = c.get_reservation(c.get_passport(env["warranty_id"])["reservation_id"])
    mock_model(direct_vm, model_result())
    adjudicate(c, direct_vm, env["claim_id"], env["holder"])
    assert c.get_pool(env["program_id"]) == pool_before
    assert c.get_reservation(c.get_passport(env["warranty_id"])["reservation_id"]) == reservation_before
    assert reservation_before["status"] == "ACTIVE"


def test_adjudication_is_permissionless(direct_deploy, direct_vm, direct_accounts):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    mock_model(direct_vm, model_result())
    aid = adjudicate(env["contract"], direct_vm, env["claim_id"], direct_accounts[5])
    assert env["contract"].get_adjudication(aid)["outcome"] == "COVERED"


def test_double_adjudication_rejected_and_first_record_untouched(direct_deploy, direct_vm, direct_accounts):
    env, a = _run(direct_deploy, direct_vm, direct_accounts, model_result())
    with pytest.raises(Exception):
        adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    assert env["contract"].get_adjudication(a["adjudication_id"]) == a


@pytest.mark.parametrize("stop_after", ["file", "dispute", "accept"])
def test_adjudication_before_evidence_freeze_rejected(direct_deploy, direct_vm, direct_accounts, stop_after):
    from helpers import (CONTRACT_PATH, create_constitution_stage2, file_claim, fund, issue, respond)
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    c = direct_deploy(CONTRACT_PATH)
    pid = c.create_program("A")
    cid = create_constitution_stage2(c, pid)
    fund(c, direct_vm, pid, manufacturer, 10 * ONE_GEN)
    wid = issue(c, direct_vm, pid, cid, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(c, direct_vm, wid, holder)
    if stop_after == "dispute":
        respond(c, direct_vm, claim_id, manufacturer, "DISPUTE")
    if stop_after == "accept":
        respond(c, direct_vm, claim_id, manufacturer, "ACCEPT")
    mock_model(direct_vm, model_result())
    with pytest.raises(Exception):
        adjudicate(c, direct_vm, claim_id, holder)
    assert c.get_claim(claim_id)["adjudication_id"] == 0


def test_unknown_claim_rejected(direct_deploy, direct_vm, direct_accounts):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        adjudicate(env["contract"], direct_vm, 999, env["holder"])


def test_new_claim_still_allowed_on_a_decided_warranty_like_stage_2_terminal_states(direct_deploy, direct_vm, direct_accounts):
    from helpers import file_claim
    env, a = _run(direct_deploy, direct_vm, direct_accounts, model_result())
    second = file_claim(env["contract"], direct_vm, env["warranty_id"], env["holder"])
    assert second != env["claim_id"]


# ---- counterfactual independence: exactly what enters the prompt ------------------------------

def _capture_prompt(monkeypatch):
    import genlayer.gl as gl_mod
    seen = []

    def fake(prompt, **kw):
        seen.append(prompt)
        return model_result()

    monkeypatch.setattr(gl_mod.nondet, "exec_prompt", fake)
    return seen


def test_prompt_contains_no_financial_or_identity_fields(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    seen = _capture_prompt(monkeypatch)
    adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    prompt = seen[0]
    from genlayer.py.types import Address
    forbidden = [
        str(5 * ONE_GEN), str(10 * ONE_GEN), "total_balance", "reserved_liability", "available_balance",
        "max_deterministic_remedy", "remedy_table", "remedy_kind", "FULL_REFUND", "reservation",
        Address(env["holder"]).as_hex, Address(env["manufacturer"]).as_hex,
        "product_commitment", format(1, "064x"), "fingerprint", "insufficient_evidence_behavior",
    ]
    for token in forbidden:
        assert token not in prompt, f"prompt leaked {token!r}"


def test_prompt_contains_exactly_the_documented_sections_and_fields(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    import json
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    seen = _capture_prompt(monkeypatch)
    adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    prompt = seen[0]
    rules = json.loads(prompt.split("GOVERNING RULES (frozen, authoritative):\n")[1].split("\nCLAIM FACTS:\n")[0])
    facts = json.loads(prompt.split("\nCLAIM FACTS:\n")[1].split("\nEVIDENCE (untrusted data):\n")[0])
    evidence = json.loads(prompt.split("\nEVIDENCE (untrusted data):\n")[1].split("\nOUTPUT:")[0])
    assert set(rules) == {"constitution_version", "product_scope", "coverage_calc", "targeted_covered_clauses", "exclusion_clauses"}
    assert set(facts) == {"claim_id", "registered_product_model", "failure_date_asserted_by_claimant_unverified",
                          "coverage_start", "coverage_end", "protocol_determined"}
    assert set(evidence[0]) == {"evidence_id", "category", "submitted_by", "source_host", "retrieved_at", "content"}
    assert [c["clause_id"] for c in rules["targeted_covered_clauses"]] == ["C-001"]  # C-002 not targeted => not shown
    assert [x["clause_id"] for x in rules["exclusion_clauses"]] == ["X-001"]
    for rule in ("untrusted DATA", "Do not browse", "Do not invent", "not proof", "payout", "EXACTLY these keys"):
        assert rule in prompt


def test_only_available_eligible_frozen_evidence_is_shown(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts, evidence=[
        ("ok", 200, "Good evidence."), ("missing", 404, ""), ("https://evil.example/x", None, "")])
    seen = _capture_prompt(monkeypatch)
    a_id = adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    assert env["contract"].get_adjudication(a_id)["evidence_ids_considered"] == [1]
    import json
    shown = json.loads(seen[0].split("\nEVIDENCE (untrusted data):\n")[1].split("\nOUTPUT:")[0])
    assert [e["evidence_id"] for e in shown] == [1] and shown[0]["source_host"] == "docs.genlayer.com"
    assert "evil.example" not in seen[0]
