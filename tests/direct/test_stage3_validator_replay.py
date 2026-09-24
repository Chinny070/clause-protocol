"""Stage 3 item 17 - validator REPLAY regression. gltest-direct only ever runs the leader; the
validator path is exercised here explicitly via direct_vm.run_validator(). This is the class of
test that found the Stage 2.5 closure bug (leader-only tests were blind to it).

What is proven: the validator (a) agrees with an equivalent independent evaluation even when the
rationale prose differs, (b) disagrees on ANY change to a structural finding, (c) rejects a
leader result that is malformed or tampered, (d) rejects on its own model failure instead of
raising, and (e) evaluates ITS OWN claim's prompt/context - no variable is shared between the
leader path and validator path or between two adjudications in one contract instance.
What is NOT proven (glsim/direct-mode limits): that a `False` vote rolls the transaction back."""
import pytest

from helpers import (
    CONTRACT_PATH, ONE_GEN, adjudicate, build_frozen_claim, file_claim, freeze_evidence, issue,
    mock_model, model_result, respond, submit_evidence,
)


def _adjudicated(direct_deploy, direct_vm, direct_accounts, reply=None, evidence=None):
    env = build_frozen_claim(direct_deploy, direct_vm, direct_accounts,
                             evidence=evidence if evidence is not None else [("a", 200, "A."), ("b", 200, "B.")])
    mock_model(direct_vm, reply if reply is not None else model_result())
    direct_vm.clear_validators()
    adjudicate(env["contract"], direct_vm, env["claim_id"], env["holder"])
    return env


def _swap_mock(direct_vm, reply):
    direct_vm.clear_mocks()
    if reply is not None:
        mock_model(direct_vm, reply)


def test_validator_agrees_when_independent_evaluation_matches(direct_deploy, direct_vm, direct_accounts):
    _adjudicated(direct_deploy, direct_vm, direct_accounts)
    assert direct_vm.run_validator() is True


def test_validator_ignores_rationale_prose_differences(direct_deploy, direct_vm, direct_accounts):
    _adjudicated(direct_deploy, direct_vm, direct_accounts)
    _swap_mock(direct_vm, model_result(rationale="Completely different wording, same findings."))
    assert direct_vm.run_validator() is True


@pytest.mark.parametrize("label, alt", [
    ("covered_set", model_result(covered=())),
    ("exclusion_set", model_result(exclusions=("X-001",))),
    ("product_match", model_result(product_match="FAIL", covered=())),
    ("evidence_sufficiency", model_result(sufficiency="INSUFFICIENT", covered=(), relied=())),
    ("evidence_relied_set", model_result(relied=(1, 2))),
    ("evidence_relied_other", model_result(relied=(2,))),
])
def test_validator_disagrees_on_any_structural_change(direct_deploy, direct_vm, direct_accounts, label, alt):
    _adjudicated(direct_deploy, direct_vm, direct_accounts)  # leader: covered C-001, relied [1]
    _swap_mock(direct_vm, alt)
    assert direct_vm.run_validator() is False, label


@pytest.mark.parametrize("label, tampered", [
    ("different_but_valid", model_result(covered=())),
    ("unknown_clause", model_result(covered=("C-999",))),
    ("unshown_evidence", model_result(relied=(77,))),
    ("extra_key_outcome", {**model_result(), "outcome": "COVERED"}),
    ("contradiction", model_result(product_match="FAIL")),
    ("not_a_dict", "COVERED"),
    ("none", None),
])
def test_validator_rejects_tampered_or_malformed_leader_result(direct_deploy, direct_vm, direct_accounts, label, tampered):
    _adjudicated(direct_deploy, direct_vm, direct_accounts)
    assert direct_vm.run_validator(leader_result=tampered) is False, label


def test_validator_rejects_a_leader_error(direct_deploy, direct_vm, direct_accounts):
    _adjudicated(direct_deploy, direct_vm, direct_accounts)
    assert direct_vm.run_validator(leader_error=RuntimeError("[LLM_ERROR] leader failed")) is False


def test_validator_votes_false_instead_of_raising_when_its_own_model_call_fails(direct_deploy, direct_vm, direct_accounts):
    _adjudicated(direct_deploy, direct_vm, direct_accounts)
    _swap_mock(direct_vm, None)  # no model available to the validator
    assert direct_vm.run_validator() is False


def test_validator_votes_false_when_its_own_model_output_is_malformed(direct_deploy, direct_vm, direct_accounts):
    _adjudicated(direct_deploy, direct_vm, direct_accounts)
    _swap_mock(direct_vm, "not json at all")
    assert direct_vm.run_validator() is False


def test_prompt_injected_leader_disagrees_with_an_honest_validator(direct_deploy, direct_vm, direct_accounts):
    """Leader was 'convinced' by hostile evidence (says COVERED); an independent honest validator
    reading the same frozen data does not - the consensus rule, not the leader, decides."""
    _adjudicated(direct_deploy, direct_vm, direct_accounts)  # leader stored COVERED
    _swap_mock(direct_vm, model_result(covered=(), sufficiency="INSUFFICIENT", product_match="UNCLEAR", relied=()))
    assert direct_vm.run_validator() is False


def _two_claims(direct_deploy, direct_vm, direct_accounts):
    """Two adjudications of DIFFERENT claims/evidence inside one contract instance."""
    env1 = build_frozen_claim(direct_deploy, direct_vm, direct_accounts, evidence=[("one", 200, "Evidence for claim one.")])
    c, m, h = env1["contract"], env1["manufacturer"], env1["holder"]
    w2 = issue(c, direct_vm, env1["program_id"], env1["constitution_id"], m, h, max_remedy=1 * ONE_GEN, commitment_seed=2)
    claim2 = file_claim(c, direct_vm, w2, h)
    respond(c, direct_vm, claim2, m, "DISPUTE")
    direct_vm.mock_web(r"https://docs\.genlayer\.com/two", {"status": 200, "body": "Evidence for claim two."})
    ev2 = submit_evidence(c, direct_vm, claim2, h, "https://docs.genlayer.com/two", "RECEIPT")
    freeze_evidence(c, direct_vm, claim2, h)
    assert (env1["claim_id"], claim2, env1["evidence_ids"], ev2) == (1, 2, [1], 2)
    return c, h, env1["claim_id"], claim2


REPLY_1 = model_result(relied=(1,), rationale="claim one reply")
REPLY_2 = model_result(covered=(), exclusions=("X-001",), relied=(2,), rationale="claim two reply")
P1, P2 = r'"claim_id": 1,', r'"claim_id": 2,'


def test_each_validator_evaluates_its_own_claims_prompt_and_context(direct_deploy, direct_vm, direct_accounts):
    c, h, claim1, claim2 = _two_claims(direct_deploy, direct_vm, direct_accounts)
    mock_model(direct_vm, REPLY_1, pattern=P1)
    mock_model(direct_vm, REPLY_2, pattern=P2)
    direct_vm.clear_validators()
    a1 = c.get_adjudication(adjudicate(c, direct_vm, claim1, h))
    a2 = c.get_adjudication(adjudicate(c, direct_vm, claim2, h))
    assert (a1["outcome"], a2["outcome"]) == ("COVERED", "NOT_COVERED")
    # both validators agree with their own leader when every model is available
    assert direct_vm.run_validator(index=0) is True
    assert direct_vm.run_validator(index=1) is True

    # Only claim 1's model exists: validator 0 must succeed and validator 1 must NOT - which is only
    # possible if validator 1 really uses claim 2's prompt and not claim 1's (captured-variable bug).
    direct_vm.clear_mocks()
    mock_model(direct_vm, REPLY_1, pattern=P1)
    assert direct_vm.run_validator(index=0) is True
    assert direct_vm.run_validator(index=1) is False

    # ...and the mirror image.
    direct_vm.clear_mocks()
    mock_model(direct_vm, REPLY_2, pattern=P2)
    assert direct_vm.run_validator(index=0) is False
    assert direct_vm.run_validator(index=1) is True


def test_leader_result_of_one_claim_is_not_valid_under_the_other_claims_context(direct_deploy, direct_vm, direct_accounts):
    """Evidence-specific context: claim 2's leader result relies on evidence id 2, which is not
    shown for claim 1. Feeding it to claim 1's validator must fail - ctx['shown'] is per call."""
    c, h, claim1, claim2 = _two_claims(direct_deploy, direct_vm, direct_accounts)
    mock_model(direct_vm, REPLY_1, pattern=P1)
    mock_model(direct_vm, REPLY_2, pattern=P2)
    direct_vm.clear_validators()
    adjudicate(c, direct_vm, claim1, h)
    adjudicate(c, direct_vm, claim2, h)
    assert direct_vm.run_validator(index=0, leader_result=REPLY_2) is False
    assert direct_vm.run_validator(index=1, leader_result=REPLY_1) is False
