"""Stage 4 pure-logic tests: the remedy table, remedy arithmetic, the deterministic challenge pre-check and
materiality. These functions are plain Python (no gl.* dependency besides UserError), so they are loaded
straight from the contract source and exercised exhaustively - independent of the contract's own storage."""
import ast
import itertools
import types

import pytest

SRC = open("contracts/clause_protocol.py", encoding="utf-8").read()
_TREE = ast.parse(SRC)


class _UserError(Exception):
    pass


def _load(names, consts):
    ns = {"gl": types.SimpleNamespace(vm=types.SimpleNamespace(UserError=_UserError))}
    for node in _TREE.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in consts for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), "c", "exec"), ns)
        if isinstance(node, ast.FunctionDef) and node.name in names:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "f", "exec"), ns)
    return ns


NS = _load(
    {"_remedy_amount", "_select_remedy", "_challenge_precheck", "_is_material"},
    {"REMEDY_FULL_REFUND", "REMEDY_REPAIR_CREDIT", "REMEDY_PARTIAL_BPS", "REMEDY_NONE", "CLAUSE_COVERED", "CLAUSE_EXCLUDED"},
)
amount = NS["_remedy_amount"]
select = NS["_select_remedy"]
precheck = NS["_challenge_precheck"]
material = NS["_is_material"]

GEN = 10**18


def row(outcome, clause, kind, value=0):
    return {"outcome": outcome, "clause_id": clause, "remedy_kind": kind, "remedy_value": value}


TABLE = [
    row("COVERED", "C-001", "FULL_REFUND"),
    row("COVERED", "C-002", "PARTIAL_BPS", 2500),
    row("COVERED", "C-003", "REPAIR_CREDIT", 3 * GEN),
    row("COVERED", "", "PARTIAL_BPS", 1000),
    row("NOT_COVERED", "", "NONE"),
    row("NOT_COVERED", "X-001", "FULL_REFUND"),  # a (nonsensical) payable row for a non-payable outcome
    row("ACCEPTED_NO_CONTEST", "", "PARTIAL_BPS", 10_000),
]


# ---- remedy arithmetic -----------------------------------------------------------------------------------

@pytest.mark.parametrize("kind,value,maxr,expected", [
    ("FULL_REFUND", 0, 5 * GEN, 5 * GEN),
    ("FULL_REFUND", 999, 5 * GEN, 5 * GEN),  # remedy_value is ignored for FULL_REFUND
    ("PARTIAL_BPS", 0, 5 * GEN, 0),
    ("PARTIAL_BPS", 1, 5 * GEN, 5 * GEN // 10_000),
    ("PARTIAL_BPS", 2500, 5 * GEN, 5 * GEN // 4),
    ("PARTIAL_BPS", 10_000, 5 * GEN, 5 * GEN),
    ("PARTIAL_BPS", 3333, 7, 7 * 3333 // 10_000),  # floors, never rounds up
    ("REPAIR_CREDIT", 3 * GEN, 5 * GEN, 3 * GEN),
    ("REPAIR_CREDIT", 9 * GEN, 5 * GEN, 5 * GEN),  # capped at the frozen maximum
    ("REPAIR_CREDIT", 0, 5 * GEN, 0),
    ("NONE", 0, 5 * GEN, 0),
])
def test_remedy_amount_arithmetic(kind, value, maxr, expected):
    assert amount(kind, value, maxr) == expected
    assert 0 <= amount(kind, value, maxr) <= maxr


def test_remedy_amount_never_exceeds_the_frozen_maximum_over_a_grid():
    for kind, value, maxr in itertools.product(
        ("FULL_REFUND", "PARTIAL_BPS", "REPAIR_CREDIT", "NONE", "UNKNOWN_KIND"),
        (0, 1, 5000, 10_000, 10**30),
        (1, 7, GEN, 10_000_000 * GEN),
    ):
        got = amount(kind, min(value, 10_000) if kind == "PARTIAL_BPS" else value, maxr)
        assert 0 <= got <= maxr, (kind, value, maxr, got)
    assert amount("UNKNOWN_KIND", 5, GEN) == 0  # unknown kinds pay nothing


# ---- remedy selection ------------------------------------------------------------------------------------

MAXR = 5 * GEN


def sel(outcome, established=(), targeted=("C-001",), ins="RULE_FOR_MANUFACTURER", una="RULE_FOR_MANUFACTURER", table=None):
    return select(TABLE if table is None else table, outcome, list(established), list(targeted), ins, una, MAXR)


def test_covered_uses_the_clause_specific_row():
    r = sel("COVERED", ["C-001"])
    assert (r["kind"], r["amount"], r["basis"]) == ("FULL_REFUND", MAXR, "COVERED")
    r = sel("COVERED", ["C-002"])
    assert (r["kind"], r["value"], r["amount"]) == ("PARTIAL_BPS", 2500, MAXR // 4)
    r = sel("COVERED", ["C-003"])
    assert r["amount"] == 3 * GEN


def test_covered_without_clause_row_falls_back_to_the_outcome_level_row():
    r = sel("COVERED", ["C-009"])  # no C-009 row: (COVERED, "") applies
    assert (r["kind"], r["amount"]) == ("PARTIAL_BPS", MAXR // 10)


def test_covered_with_several_clauses_takes_the_highest_single_row_never_a_sum():
    r = sel("COVERED", ["C-002", "C-003", "C-001"])
    assert r["amount"] == MAXR  # FULL_REFUND is the max; 0.25+3+5 is NOT summed
    r = sel("COVERED", ["C-002", "C-003"])
    assert r["amount"] == 3 * GEN
    assert r["amount"] <= MAXR


def test_selection_is_order_independent():
    a = sel("COVERED", ["C-003", "C-002", "C-001"])
    b = sel("COVERED", ["C-001", "C-002", "C-003"])
    assert a == b


def test_covered_with_no_matching_row_and_no_outcome_row_fails_closed():
    table = [row("COVERED", "C-001", "FULL_REFUND"), row("ACCEPTED_NO_CONTEST", "", "FULL_REFUND")]
    with pytest.raises(_UserError, match="failing closed"):
        sel("COVERED", ["C-002"], table=table)
    with pytest.raises(_UserError, match="failing closed"):
        sel("COVERED", [], table=table)  # COVERED with nothing established can never be paid


def test_accepted_no_contest_needs_its_own_row_else_fails_closed():
    r = sel("ACCEPTED_NO_CONTEST")
    assert (r["basis"], r["amount"]) == ("NO_CONTEST", MAXR)
    with pytest.raises(_UserError, match="failing closed"):
        sel("ACCEPTED_NO_CONTEST", table=[row("COVERED", "C-001", "FULL_REFUND")])


@pytest.mark.parametrize("outcome", ["NOT_COVERED", "INVALID_CLAIM"])
def test_non_payable_outcomes_pay_zero_regardless_of_table_contents(outcome):
    r = sel(outcome, ["C-001"], ins="RULE_FOR_HOLDER", una="RULE_FOR_HOLDER")
    assert r["amount"] == 0 and r["kind"] == "NONE" and r["basis"] == "NON_PAYABLE"


@pytest.mark.parametrize("outcome,ins,una,basis,paid", [
    ("INSUFFICIENT_EVIDENCE", "RULE_FOR_MANUFACTURER", "RULE_FOR_HOLDER", "NON_PAYABLE", False),
    ("INSUFFICIENT_EVIDENCE", "BLOCK", "RULE_FOR_HOLDER", "POLICY_BLOCK", False),
    ("INSUFFICIENT_EVIDENCE", "RULE_FOR_HOLDER", "RULE_FOR_MANUFACTURER", "POLICY_RULE_FOR_HOLDER", True),
    ("EVIDENCE_UNAVAILABLE", "RULE_FOR_HOLDER", "RULE_FOR_MANUFACTURER", "NON_PAYABLE", False),
    ("EVIDENCE_UNAVAILABLE", "RULE_FOR_HOLDER", "BLOCK", "POLICY_BLOCK", False),
    ("EVIDENCE_UNAVAILABLE", "RULE_FOR_MANUFACTURER", "RULE_FOR_HOLDER", "POLICY_RULE_FOR_HOLDER", True),
])
def test_evidence_gap_outcomes_follow_only_their_own_frozen_policy(outcome, ins, una, basis, paid):
    r = sel(outcome, [], ["C-001"], ins, una)
    assert r["basis"] == basis and (r["amount"] > 0) == paid


def test_rule_for_holder_prices_the_targeted_clauses_and_fails_closed_without_a_row():
    r = sel("INSUFFICIENT_EVIDENCE", [], ["C-002"], "RULE_FOR_HOLDER")
    assert r["amount"] == MAXR // 4
    with pytest.raises(_UserError, match="failing closed"):
        sel("INSUFFICIENT_EVIDENCE", [], ["C-002"], "RULE_FOR_HOLDER", table=[row("NOT_COVERED", "", "NONE")])


def test_remedy_never_exceeds_the_warranty_maximum_for_any_row_kind():
    for kind, value in (("FULL_REFUND", 0), ("PARTIAL_BPS", 10_000), ("REPAIR_CREDIT", 10**30)):
        r = select([row("COVERED", "C-001", kind, value)], "COVERED", ["C-001"], ["C-001"], "RULE_FOR_MANUFACTURER", "RULE_FOR_MANUFACTURER", MAXR)
        assert r["amount"] <= MAXR


# ---- materiality ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("orig,new,oc,nc,expected", [
    ("COVERED", "COVERED", ["C-001"], ["C-001"], False),
    ("COVERED", "COVERED", ["C-001"], ["C-001", "C-002"], True),  # different remedy row may apply
    ("NOT_COVERED", "NOT_COVERED", [], [], False),
    ("INSUFFICIENT_EVIDENCE", "COVERED", [], ["C-001"], True),
    ("COVERED", "NOT_COVERED", ["C-001"], ["C-001"], True),
    ("NOT_COVERED", "INSUFFICIENT_EVIDENCE", [], [], True),
])
def test_materiality(orig, new, oc, nc, expected):
    assert material(orig, new, oc, nc) is expected


# ---- deterministic challenge pre-check ---------------------------------------------------------------------

def facts(**kw):
    base = {
        "governing_constitution_id": 1, "orig_version": "PASS", "orig_window": "PASS", "new_version": "PASS",
        "new_window": "PASS", "orig_path": "SEMANTIC", "considered": [1, 2], "relied": [1],
        "evidence": {1: {"eligible": True, "usable": True}, 2: {"eligible": True, "usable": True},
                     3: {"eligible": False, "usable": False}},
        "targeted": ["C-001"], "cited_clause_kinds": {"C-001": "COVERED", "C-002": "COVERED", "X-001": "EXCLUDED"},
    }
    base.update(kw)
    return base


def cit(**kw):
    base = {"evidence_ids": [], "clause_ids": [], "constitution_id": 0, "timestamp_field": ""}
    base.update(kw)
    return base


def test_version_ground():
    assert precheck("WRONG_WARRANTY_VERSION", cit(constitution_id=1), facts())[0] == "UPHELD"
    assert precheck("WRONG_WARRANTY_VERSION", cit(constitution_id=2), facts())[0] == "INVALID_CHALLENGE"
    assert precheck("WRONG_WARRANTY_VERSION", cit(constitution_id=1), facts(orig_version="FAIL", new_version="PASS"))[0] == "REVERSED"


def test_temporal_ground():
    assert precheck("TEMPORAL_ERROR", cit(timestamp_field="filed_at"), facts())[0] == "UPHELD"
    assert precheck("TEMPORAL_ERROR", cit(timestamp_field="filed_at"), facts(orig_window="FAIL", new_window="PASS"))[0] == "REVERSED"
    assert precheck("TEMPORAL_ERROR", cit(timestamp_field="filed_at"), facts(orig_window="PASS", new_window="FAIL"))[0] == "REVERSED"


def test_source_authority_ground_never_lets_ineligible_evidence_through():
    assert precheck("SOURCE_AUTHORITY_ERROR", cit(evidence_ids=[1]), facts())[0] == "UPHELD"
    assert precheck("SOURCE_AUTHORITY_ERROR", cit(evidence_ids=[3]), facts())[0] == "INVALID_CHALLENGE"
    assert precheck("SOURCE_AUTHORITY_ERROR", cit(evidence_ids=[1, 3]), facts())[0] == "INVALID_CHALLENGE"


def test_ignored_evidence_gates():
    assert precheck("IGNORED_EVIDENCE", cit(evidence_ids=[2]), facts())[0] == "SEMANTIC"
    assert precheck("IGNORED_EVIDENCE", cit(evidence_ids=[1]), facts())[0] == "INVALID_CHALLENGE"  # was relied on
    assert precheck("IGNORED_EVIDENCE", cit(evidence_ids=[3]), facts())[0] == "INVALID_CHALLENGE"  # never adjudicable
    assert precheck("IGNORED_EVIDENCE", cit(evidence_ids=[9]), facts(evidence={9: {"eligible": True, "usable": True}}))[0] == "INVALID_CHALLENGE"  # not considered


def test_wrong_clause_and_exclusion_gates():
    assert precheck("WRONG_CLAUSE", cit(clause_ids=["C-001"]), facts())[0] == "SEMANTIC"
    assert precheck("WRONG_CLAUSE", cit(clause_ids=["C-002"]), facts())[0] == "INVALID_CHALLENGE"  # not targeted
    assert precheck("WRONG_CLAUSE", cit(clause_ids=["X-001"]), facts())[0] == "INVALID_CHALLENGE"  # wrong kind
    assert precheck("EXCLUSION_MISAPPLIED", cit(clause_ids=["X-001"]), facts())[0] == "SEMANTIC"
    assert precheck("EXCLUSION_MISAPPLIED", cit(clause_ids=["C-001"]), facts())[0] == "INVALID_CHALLENGE"


def test_product_match_gates():
    assert precheck("PRODUCT_MATCH_ERROR", cit(evidence_ids=[1]), facts())[0] == "SEMANTIC"
    assert precheck("PRODUCT_MATCH_ERROR", cit(evidence_ids=[3]), facts())[0] == "INVALID_CHALLENGE"


@pytest.mark.parametrize("ground,c", [
    ("WRONG_CLAUSE", cit(clause_ids=["C-001"])),
    ("EXCLUSION_MISAPPLIED", cit(clause_ids=["X-001"])),
    ("PRODUCT_MATCH_ERROR", cit(evidence_ids=[1])),
    ("IGNORED_EVIDENCE", cit(evidence_ids=[2])),
])
def test_semantic_grounds_never_reach_the_model_when_the_original_was_deterministic(ground, c):
    v, _ = precheck(ground, c, facts(orig_path="DETERMINISTIC_PREDICATE"))
    assert v == "UPHELD"
    v, _ = precheck(ground, c, facts(orig_path="DETERMINISTIC_NO_ADMISSIBLE_EVIDENCE", considered=[], evidence={1: {"eligible": True, "usable": True}, 2: {"eligible": True, "usable": True}}))
    assert v == "INVALID_CHALLENGE"


def test_every_verdict_is_one_of_the_documented_four():
    for ground in ("IGNORED_EVIDENCE", "WRONG_WARRANTY_VERSION", "WRONG_CLAUSE", "EXCLUSION_MISAPPLIED", "TEMPORAL_ERROR", "SOURCE_AUTHORITY_ERROR", "PRODUCT_MATCH_ERROR"):
        for c in (cit(evidence_ids=[1]), cit(evidence_ids=[2]), cit(clause_ids=["C-001"]), cit(clause_ids=["X-001"]), cit(constitution_id=1), cit(timestamp_field="filed_at")):
            try:
                v, reason = precheck(ground, c, facts())
            except KeyError:
                continue  # a citation kind that this ground can never carry (rejected at filing)
            assert v in ("UPHELD", "INVALID_CHALLENGE", "REVERSED", "SEMANTIC") and reason
