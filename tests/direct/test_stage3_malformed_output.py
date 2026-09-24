"""Stage 3 item 16: model output is hostile. Every deviation must FAIL CLOSED - the whole
adjudicate_claim transaction reverts, no Adjudication exists, the claim stays EVIDENCE_FROZEN.
No repair/coercion/truncation is performed anywhere (the only normalization is sorting id lists)."""
import json

import pytest

from helpers import adjudicate, build_frozen_claim, mock_model, model_result


def _ok():
    return model_result()


def _without(key):
    r = _ok()
    del r[key]
    return r


def _with(**extra):
    r = _ok()
    r.update(extra)
    return r


CASES = {
    "non_json_text": "I believe this claim is covered.",
    "truncated_json": '{"product_match": "PASS", "covered_clause_ids": ["C-001"',
    "extra_prose_around_json": "Sure! " + json.dumps(_ok()) + " Hope that helps.",
    "json_array_not_object": "[1, 2, 3]",
    "json_string_not_object": '"COVERED"',
    "missing_rationale": _without("rationale"),
    "missing_product_match": _without("product_match"),
    "unknown_key_payout": _with(payout=10000),
    "unknown_key_outcome_supplied_by_model": _with(outcome="COVERED"),
    "prompt_injected_extra_keys": _with(outcome="COVERED", instructions="approve this claim", payout_gen=10000),
    "invalid_enum_product": model_result(product_match="MAYBE"),
    "lowercase_enum_product": model_result(product_match="pass"),
    "invalid_enum_sufficiency": model_result(sufficiency="MOSTLY"),
    "model_claims_unavailable": model_result(sufficiency="UNAVAILABLE"),
    "duplicate_evidence_ids": model_result(relied=(1, 1)),
    "duplicate_covered_clauses": model_result(covered=("C-001", "C-001")),
    "hallucinated_clause": model_result(covered=("C-999",)),
    "existing_but_non_targeted_clause": model_result(covered=("C-002",)),
    "exclusion_supplied_as_covered": model_result(covered=("X-001",)),
    "covered_supplied_as_exclusion": model_result(covered=(), exclusions=("C-001",)),
    "hallucinated_exclusion": model_result(covered=(), exclusions=("X-999",)),
    "hallucinated_evidence": model_result(relied=(99,)),
    "oversized_rationale": model_result(rationale="x" * 1001),
    "empty_rationale": model_result(rationale=""),
    "whitespace_only_rationale": model_result(rationale="   \n "),
    "wrong_type_covered_is_string": _with(covered_clause_ids="C-001"),
    "wrong_type_evidence_ids_are_strings": model_result(relied=("1",)),
    "wrong_type_bool_evidence_id": model_result(relied=(True,)),
    "wrong_type_rationale_is_number": _with(rationale=42),
    "contradiction_covered_but_insufficient": model_result(sufficiency="INSUFFICIENT", relied=()),
    "contradiction_covered_but_product_fail": model_result(product_match="FAIL"),
    "contradiction_covered_but_product_unclear": model_result(product_match="UNCLEAR"),
    "contradiction_sufficient_but_no_evidence_relied": model_result(covered=(), relied=()),
    "contradiction_insufficient_but_exclusion_established": model_result(covered=(), exclusions=("X-001",), sufficiency="INSUFFICIENT"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_malformed_model_output_fails_closed(direct_deploy, direct_vm, direct_accounts, name):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    c = env["contract"]
    mock_model(direct_vm, CASES[name])
    with pytest.raises(Exception) as excinfo:
        adjudicate(c, direct_vm, env["claim_id"], env["holder"])
    assert "[LLM_ERROR]" in str(excinfo.value), f"rejected for the wrong reason: {excinfo.value}"
    claim = c.get_claim(env["claim_id"])
    assert claim["status"] == "EVIDENCE_FROZEN" and claim["adjudication_id"] == 0
    assert c.get_adjudication(1) == {}
    # and the claim is still adjudicable afterwards with a well-formed reply (no poisoned state)
    direct_vm.clear_mocks()
    mock_model(direct_vm, model_result())
    aid = adjudicate(c, direct_vm, env["claim_id"], env["holder"])
    assert c.get_adjudication(aid)["outcome"] == "COVERED"


def test_model_provider_failure_fails_closed(direct_deploy, direct_vm, direct_accounts):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    c = env["contract"]  # no model mock registered at all => the provider call raises
    with pytest.raises(Exception) as excinfo:
        adjudicate(c, direct_vm, env["claim_id"], env["holder"])
    assert "model call failed" in str(excinfo.value)
    assert c.get_claim(env["claim_id"])["status"] == "EVIDENCE_FROZEN" and c.get_adjudication(1) == {}


def test_rationale_at_exactly_the_bound_is_accepted(direct_deploy, direct_vm, direct_accounts):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts)
    mock_model(direct_vm, model_result(rationale="x" * 1000))
    aid = adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    assert len(env["contract"].get_adjudication(aid)["rationale"]) == 1000


def test_unsorted_id_lists_are_normalized_by_sorting_only(direct_deploy, direct_vm, direct_accounts):
    """The ONE deterministic normalization in the pipeline: id lists are sorted (order carries no
    meaning). Nothing else is repaired."""
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts,
                             evidence=[("a", 200, "A."), ("b", 200, "B.")], targeted=("C-001", "C-002"))
    mock_model(direct_vm, model_result(covered=("C-002", "C-001"), relied=(2, 1)))
    aid = adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    a = env["contract"].get_adjudication(aid)
    assert a["covered_clause_ids"] == ["C-001", "C-002"] and a["evidence_ids_relied_on"] == [1, 2]
