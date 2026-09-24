"""Stage 3.5 hardening: (1) hard evidence cap with no silent truncation, (2) exhaustive outcome
truth table, (3) source_authority invariant. Model is mocked in direct mode."""
import ast
import itertools
import json
import re

import pytest

from helpers import (
    ONE_GEN, S3_COVERED, S3_EXCLUDED, S3_URL, adjudicate, build_frozen_claim, create_constitution_stage2,
    file_claim, fund, freeze_evidence, issue, mock_model, model_result, respond, submit_evidence,
)

CAP = 10
BAD_URL = "https://evil.example.net/"


def _open_claim(direct_deploy, direct_vm, direct_accounts):
    """Claim in DISPUTED (accepting evidence), NOT frozen."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy("contracts/clause_protocol.py")
    program_id = contract.create_program("Acme")
    cid = create_constitution_stage2(contract, program_id, covered_clauses=S3_COVERED,
                                     excluded_clauses=S3_EXCLUDED, source_policy="docs.genlayer.com",
                                     evidence_categories=["RECEIPT", "PHOTO"])
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    wid = issue(contract, direct_vm, program_id, cid, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, wid, holder, targeted_clause_ids=["C-001"],
                          failure_asserted_at=int(contract.now()))
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    return contract, manufacturer, holder, claim_id


def _mock(direct_vm, url):
    direct_vm.mock_web(url.replace(".", r"\.").replace("?", r"\?"), {"status": 200, "body": "Unit failed."})


def _submit(contract, direct_vm, claim_id, who, i, category="RECEIPT"):
    url = f"{S3_URL}e{i}"
    _mock(direct_vm, url)
    return submit_evidence(contract, direct_vm, claim_id, who, url, category)


def _capture(monkeypatch, relied):
    import genlayer.gl as gl_mod
    seen = []

    def fake(prompt, **kw):
        seen.append(prompt)
        return model_result(relied=relied)

    monkeypatch.setattr(gl_mod.nondet, "exec_prompt", fake)
    return seen


def _shown_ids(prompt):
    return sorted(int(x) for x in re.findall(r'"evidence_id":\s*(\d+)', prompt))


def _adj(env_contract, claim_id):
    return env_contract.get_adjudication(adjudication_id=env_contract.get_claim(claim_id=claim_id)["adjudication_id"])


# ---------------------------------------------------------------- 1. evidence cap

@pytest.mark.parametrize("n", [9, 10])
def test_up_to_cap_accepted_and_every_record_adjudicated(direct_deploy, direct_vm, direct_accounts, monkeypatch, n):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts,
                             evidence=[(f"e{i}", 200, f"Unit failed {i}.") for i in range(n)])
    seen = _capture(monkeypatch, (env["evidence_ids"][0],))
    adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    expected = sorted(int(x) for x in env["evidence_ids"])
    assert _shown_ids(seen[0]) == expected and len(expected) == n
    a = _adj(env["contract"], env["claim_id"])
    considered = a.get("evidence_ids_considered_json", a.get("evidence_ids_considered"))
    if isinstance(considered, str):
        considered = json.loads(considered)
    assert sorted(int(x) for x in considered) == expected


def test_eleventh_eligible_record_rejected_before_freeze(direct_deploy, direct_vm, direct_accounts):
    contract, man, holder, claim_id = _open_claim(direct_deploy, direct_vm, direct_accounts)
    for i in range(CAP):
        _submit(contract, direct_vm, claim_id, holder, i)
    with pytest.raises(Exception, match="maximum of 10"):
        _submit(contract, direct_vm, claim_id, holder, CAP)
    with pytest.raises(Exception, match="maximum of 10"):
        _submit(contract, direct_vm, claim_id, man, CAP + 1)  # the other party shares the same cap


def test_multi_transaction_multi_party_then_freeze_adjudicates_exactly_ten(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    contract, man, holder, claim_id = _open_claim(direct_deploy, direct_vm, direct_accounts)
    ids = [_submit(contract, direct_vm, claim_id, holder if i % 2 else man, i) for i in range(CAP)]
    with pytest.raises(Exception, match="maximum of 10"):
        _submit(contract, direct_vm, claim_id, holder, 99)
    freeze_evidence(contract, direct_vm, claim_id, holder)
    seen = _capture(monkeypatch, (ids[0],))
    adjudicate(contract, direct_vm, claim_id, holder)
    assert _shown_ids(seen[0]) == sorted(int(i) for i in ids)


def test_duplicate_attempts_do_not_consume_capacity(direct_deploy, direct_vm, direct_accounts):
    contract, man, holder, claim_id = _open_claim(direct_deploy, direct_vm, direct_accounts)
    for i in range(CAP - 1):
        _submit(contract, direct_vm, claim_id, holder, i)
    for _ in range(5):  # a rejected duplicate must not eat the last slot
        with pytest.raises(Exception, match="duplicate"):
            _submit(contract, direct_vm, claim_id, holder, 0)
    _submit(contract, direct_vm, claim_id, holder, 500)  # the 10th still fits
    with pytest.raises(Exception, match="maximum of 10"):
        _submit(contract, direct_vm, claim_id, holder, 501)


def test_cap_not_bypassable_by_category_or_url_variants(direct_deploy, direct_vm, direct_accounts):
    contract, man, holder, claim_id = _open_claim(direct_deploy, direct_vm, direct_accounts)
    for i in range(CAP):
        _submit(contract, direct_vm, claim_id, holder, i, category="RECEIPT" if i % 2 else "PHOTO")
    for cat in ("RECEIPT", "PHOTO"):
        with pytest.raises(Exception, match="maximum of 10"):
            _submit(contract, direct_vm, claim_id, holder, 700, category=cat)
    for variant in (S3_URL + "e0?x=1", "https://DOCS.GENLAYER.COM/e0", S3_URL + "e0#frag", S3_URL + "brand-new"):
        _mock(direct_vm, variant)
        with pytest.raises(Exception):  # duplicate or cap: never accepted
            submit_evidence(contract, direct_vm, claim_id, holder, variant, "RECEIPT")


def test_ineligible_records_do_not_consume_capacity_and_never_reach_the_prompt(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    contract, man, holder, claim_id = _open_claim(direct_deploy, direct_vm, direct_accounts)
    for j in range(4):  # ordering: ineligible submitted first
        submit_evidence(contract, direct_vm, claim_id, man, f"{BAD_URL}x{j}", "RECEIPT")
    ids = [_submit(contract, direct_vm, claim_id, holder, i) for i in range(CAP)]
    with pytest.raises(Exception, match="maximum of 10"):
        _submit(contract, direct_vm, claim_id, holder, 42)
    freeze_evidence(contract, direct_vm, claim_id, holder)
    seen = _capture(monkeypatch, (ids[0],))
    adjudicate(contract, direct_vm, claim_id, holder)
    assert "evil.example.net" not in seen[0]
    assert len(_shown_ids(seen[0])) == CAP


def test_no_submission_after_freeze(direct_deploy, direct_vm, direct_accounts):
    contract, man, holder, claim_id = _open_claim(direct_deploy, direct_vm, direct_accounts)
    _submit(contract, direct_vm, claim_id, holder, 0)
    freeze_evidence(contract, direct_vm, claim_id, holder)
    with pytest.raises(Exception):
        _submit(contract, direct_vm, claim_id, holder, 1)


def test_no_silent_slicing_in_contract_source():
    src = open("contracts/clause_protocol.py", encoding="utf-8").read()
    assert not re.search(r"shown\s*=\s*.*\[:\s*\d+\]", src)
    assert "_MAX_EVIDENCE_IN_PROMPT" not in src
    assert "len(shown) < " not in src


# ---------------------------------------------------------------- 2. truth table

def _load_derive():
    tree = ast.parse(open("contracts/clause_protocol.py", encoding="utf-8").read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_derive_outcome")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "derive", "exec"), ns)
    return ns["_derive_outcome"]


def _oracle(product, version, window, suff, source, covered, excl):
    """Independent formulation of the documented precedence table."""
    if version == "FAIL":
        return "INVALID_CLAIM"
    if window == "FAIL":
        return "NOT_COVERED"
    if suff == "UNAVAILABLE":
        return "EVIDENCE_UNAVAILABLE"
    if suff != "SUFFICIENT":
        return "INSUFFICIENT_EVIDENCE"
    if product == "FAIL":
        return "NOT_COVERED"
    if product != "PASS":
        return "INSUFFICIENT_EVIDENCE"
    if excl:
        return "NOT_COVERED"
    if covered and source == "PASS":
        return "COVERED"
    return "INSUFFICIENT_EVIDENCE"


ALL = list(itertools.product(("PASS", "FAIL", "UNCLEAR"), ("PASS", "FAIL"), ("PASS", "FAIL"),
                             ("SUFFICIENT", "INSUFFICIENT", "UNAVAILABLE"), ("PASS", "FAIL", "UNCLEAR"),
                             (False, True), (False, True)))


def _call(d, p, v, w, s, src, cov, ex):
    return d(p, v, w, s, src, ["C-001"] if cov else [], ["X-001"] if ex else [])


def test_truth_table_exhaustive_matches_oracle():
    d = _load_derive()
    assert len(ALL) == 3 * 2 * 2 * 3 * 3 * 2 * 2
    for combo in ALL:
        assert _call(d, *combo) == _oracle(*combo), combo


def test_covered_only_when_every_condition_positive():
    d = _load_derive()
    for combo in ALL:
        p, v, w, s, src, cov, ex = combo
        positive = (p == "PASS" and v == "PASS" and w == "PASS" and s == "SUFFICIENT"
                    and src == "PASS" and cov and not ex)
        assert (_call(d, *combo) == "COVERED") == positive, combo


def test_not_covered_only_with_affirmative_reason():
    d = _load_derive()
    for combo in ALL:
        p, v, w, s, src, cov, ex = combo
        if _call(d, *combo) == "NOT_COVERED":
            assert v == "PASS"
            assert w == "FAIL" or (s == "SUFFICIENT" and (p == "FAIL" or (p == "PASS" and ex))), combo


def test_named_cases():
    d = _load_derive()
    assert d("PASS", "PASS", "PASS", "SUFFICIENT", "PASS", [], []) == "INSUFFICIENT_EVIDENCE"  # no coverage established
    assert d("PASS", "PASS", "PASS", "SUFFICIENT", "PASS", [], ["X-001"]) == "NOT_COVERED"
    assert d("PASS", "PASS", "PASS", "SUFFICIENT", "PASS", ["C-001"], ["X-001"]) == "NOT_COVERED"
    assert d("PASS", "PASS", "PASS", "SUFFICIENT", "PASS", ["C-001"], []) == "COVERED"
    for src in ("FAIL", "UNCLEAR"):
        assert d("PASS", "PASS", "PASS", "SUFFICIENT", src, ["C-001"], []) == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------- 3. source_authority semantics

def test_only_ineligible_evidence_means_no_model_call_and_unclear_authority(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts,
                             evidence=[(BAD_URL + "a", None, ""), (BAD_URL + "b", None, "")])
    called = _capture(monkeypatch, (1,))
    adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    assert called == []
    a = _adj(env["contract"], env["claim_id"])
    assert a["source_authority"] == "UNCLEAR" and a["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert a["decision_path"] == "DETERMINISTIC_NO_ADMISSIBLE_EVIDENCE"


def test_model_cannot_rely_on_ineligible_evidence_id(direct_deploy, direct_vm, direct_accounts):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts,
                             evidence=[("e1", 200, "Unit failed."), (BAD_URL + "a", None, "")])
    good, bad = env["evidence_ids"]
    mock_model(direct_vm, model_result(relied=(bad,)))
    with pytest.raises(Exception, match="LLM_ERROR"):
        adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    assert env["contract"].get_claim(claim_id=env["claim_id"])["status"] == "EVIDENCE_FROZEN"


def test_ineligible_evidence_id_absent_from_prompt_when_mixed(direct_deploy, direct_vm, direct_accounts, monkeypatch):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts,
                             evidence=[("e1", 200, "Unit failed."), (BAD_URL + "a", None, "")])
    good, bad = env["evidence_ids"]
    seen = _capture(monkeypatch, (good,))
    adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    assert _shown_ids(seen[0]) == [int(good)] and "evil.example.net" not in seen[0]


def test_source_authority_pass_with_relied_evidence(direct_deploy, direct_vm, direct_accounts):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    mock_model(direct_vm, model_result())
    adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    a = _adj(env["contract"], env["claim_id"])
    assert a["source_authority"] == "PASS" and a["outcome"] == "COVERED"
