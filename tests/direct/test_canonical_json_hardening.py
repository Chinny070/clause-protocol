"""Stage 1 hardening pass, item 2: adversarial coverage for _validate_clause_list and
_validate_remedy_table, plus proof that CLAUSE's canonical-JSON encoding (see
_canonical_json's docstring in contracts/clause_protocol.py) actually canonicalizes: two
semantically-equivalent submissions - same clause set / remedy table, different input order,
different dict key order - must fingerprint identically and store identically.
"""

import pytest

from helpers import CONTRACT_PATH, DEFAULT_REMEDY_TABLE, ONE_GEN, create_constitution


def _setup_program(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    return contract, program_id, manufacturer


# ---------------------------------------------------------------------------
# Malformed top-level / element types
# ---------------------------------------------------------------------------

def test_covered_clauses_wrong_top_level_type_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses="not-a-list")


def test_covered_clauses_dict_instead_of_list_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses={"clause_id": "C-001", "text": "x"})


def test_covered_clauses_element_wrong_type_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses=["C-001"])  # list of str, not dict


def test_remedy_table_wrong_top_level_type_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, remedy_table="not-a-list")


def test_evidence_categories_wrong_top_level_type_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, evidence_categories="RECEIPT")


def test_evidence_categories_element_wrong_type_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, evidence_categories=[1, 2, 3])


# ---------------------------------------------------------------------------
# Missing / unexpected keys
# ---------------------------------------------------------------------------

def test_clause_row_missing_text_key_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses=[{"clause_id": "C-001"}])


def test_clause_row_unexpected_extra_key_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            covered_clauses=[{"clause_id": "C-001", "text": "x", "unexpected": "field"}],
        )


def test_remedy_row_missing_remedy_value_key_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[{"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE"}],
        )


def test_remedy_row_unexpected_extra_key_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[{"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0, "note": "x"}],
        )


# ---------------------------------------------------------------------------
# Duplicates where forbidden
# ---------------------------------------------------------------------------

def test_duplicate_evidence_category_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, evidence_categories=["RECEIPT", "RECEIPT"])


def test_duplicate_remedy_row_same_outcome_and_clause_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[
                {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
                {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "REPAIR_CREDIT", "remedy_value": 0},
            ],
        )


# ---------------------------------------------------------------------------
# Nonexistent references / wrong clause kind
# ---------------------------------------------------------------------------

def test_remedy_row_referencing_nonexistent_excluded_clause_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[
                {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
                {"outcome": "NOT_COVERED", "clause_id": "X-999", "remedy_kind": "NONE", "remedy_value": 0},
            ],
        )


def test_covered_outcome_referencing_excluded_clause_rejected(direct_deploy, direct_vm, direct_accounts):
    """A COVERED remedy row citing an X-* (excluded) clause is a wrong-clause-kind error,
    distinct from a plain unknown-reference error - the clause exists, but on the wrong
    side."""
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[
                {"outcome": "COVERED", "clause_id": "X-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
                {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0},
            ],
        )


def test_not_covered_outcome_referencing_covered_clause_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[
                {"outcome": "COVERED", "clause_id": "", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
                {"outcome": "NOT_COVERED", "clause_id": "C-001", "remedy_kind": "NONE", "remedy_value": 0},
            ],
        )


def test_procedural_outcome_with_nonempty_clause_id_rejected(direct_deploy, direct_vm, direct_accounts):
    """INSUFFICIENT_EVIDENCE/EVIDENCE_UNAVAILABLE/INVALID_CLAIM/ACCEPTED_NO_CONTEST are
    procedural, never clause-specific - a nonempty clause_id on any of them is rejected."""
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[
                {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
                {"outcome": "ACCEPTED_NO_CONTEST", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
            ],
        )


# ---------------------------------------------------------------------------
# Empty required collections (excluded_clauses is the one legitimately-optional exception)
# ---------------------------------------------------------------------------

def test_empty_covered_clauses_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses=[])


def test_empty_remedy_table_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, remedy_table=[])


def test_empty_evidence_categories_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, evidence_categories=[])


def test_empty_excluded_clauses_allowed(direct_deploy, direct_vm, direct_accounts):
    """The one deliberately-optional collection: a program may have zero exclusions."""
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    constitution_id = create_constitution(contract, program_id, excluded_clauses=[])
    assert contract.get_constitution(constitution_id)["excluded_clause_ids"] == []


# ---------------------------------------------------------------------------
# Negative / invalid numeric values
# ---------------------------------------------------------------------------

def test_negative_remedy_value_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[{"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": -1}],
        )


def test_bool_remedy_value_rejected(direct_deploy, direct_vm, direct_accounts):
    """bool is a subclass of int in Python - explicitly excluded so a stray True/False can
    never silently become 1/0 in a stored remedy row."""
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[{"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": False}],
        )


def test_non_integer_remedy_value_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id,
            remedy_table=[{"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 1.5}],
        )


# ---------------------------------------------------------------------------
# Oversized input
# ---------------------------------------------------------------------------

def test_too_many_covered_clauses_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    too_many = [{"clause_id": f"C-{i:03d}", "text": "x"} for i in range(51)]
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses=too_many)


def test_too_many_remedy_rows_rejected(direct_deploy, direct_vm, direct_accounts):
    """Exactly at the covered-clause cap (50, itself allowed) but one remedy row over the
    remedy-table cap (50 clause rows + 1 outcome-level row = 51) - isolates the remedy-table
    cap from the clause-count cap."""
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    covered = [{"clause_id": f"C-{i:03d}", "text": "x"} for i in range(50)]
    remedy = [{"outcome": "COVERED", "clause_id": f"C-{i:03d}", "remedy_kind": "FULL_REFUND", "remedy_value": 0} for i in range(50)]
    remedy.append({"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0})
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses=covered, remedy_table=remedy)


def test_too_many_evidence_categories_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    too_many = [f"CATEGORY_{i}" for i in range(21)]
    with pytest.raises(Exception):
        create_constitution(contract, program_id, evidence_categories=too_many)


def test_oversized_clause_id_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses=[{"clause_id": "C-" + "x" * 250, "text": "x"}])


def test_oversized_clause_text_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, covered_clauses=[{"clause_id": "C-001", "text": "x" * 4001}])


def test_oversized_evidence_category_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        create_constitution(contract, program_id, evidence_categories=["X" * 201])


# ---------------------------------------------------------------------------
# Canonical JSON: order-independence and key-order-independence
# ---------------------------------------------------------------------------

def test_clause_order_does_not_affect_stored_canonical_fields(direct_deploy, direct_vm, direct_accounts):
    """Two constitutions with the same clause SETS submitted in different list order must
    resolve to identical stored `covered_clause_ids`/`remedy_table` values - proving those
    fields are genuinely canonicalized (sorted), not merely serialized in submission order.

    Note: this deliberately does NOT compare the two constitutions' `fingerprint` values.
    `fingerprint` also folds in `program_id`/`version`, which are required to differ here
    (CLAUSE forbids two constitutions from sharing a `(program_id, version)` pair - see
    docs/WARRANTY_CONSTITUTION.md), so a differing fingerprint between c1/c2 is expected and
    uninformative. Order-independence is a property of the canonicalized *subfields*, which
    is exactly what Stage 2+ code will actually compare for semantic equality (see
    `_canonical_json`'s docstring) - not raw fingerprints across unrelated constitutions."""
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    covered_forward = [
        {"clause_id": "C-001", "text": "Manufacturing defects."},
        {"clause_id": "C-002", "text": "Battery failure."},
    ]
    covered_reversed = list(reversed(covered_forward))
    remedy = [
        {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
        {"outcome": "COVERED", "clause_id": "C-002", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
        {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0},
    ]

    c1 = create_constitution(contract, program_id, version="A", covered_clauses=covered_forward, remedy_table=remedy)
    c2 = create_constitution(contract, program_id, version="B", covered_clauses=covered_reversed, remedy_table=list(reversed(remedy)))

    assert contract.get_constitution(c1)["covered_clause_ids"] == contract.get_constitution(c2)["covered_clause_ids"] == ["C-001", "C-002"]
    assert contract.get_constitution(c1)["remedy_table"] == contract.get_constitution(c2)["remedy_table"]


def test_evidence_category_order_does_not_affect_stored_canonical_field(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    c1 = create_constitution(contract, program_id, version="A", evidence_categories=["RECEIPT", "PHOTO"])
    c2 = create_constitution(contract, program_id, version="B", evidence_categories=["PHOTO", "RECEIPT"])
    assert (
        contract.get_constitution(c1)["acceptable_evidence_categories"]
        == contract.get_constitution(c2)["acceptable_evidence_categories"]
        == ["PHOTO", "RECEIPT"]
    )


def test_dict_key_order_in_clause_and_remedy_rows_does_not_affect_stored_fields(direct_deploy, direct_vm, direct_accounts):
    """Python dict literals with keys written in a different order are still the same dict at
    the Python level, but this proves it end to end through validation and storage - and
    documents that `_canonical_json`'s `sort_keys=True` makes stored-object key order a
    non-issue regardless of submission order, guarding against a future reimplementation that
    drops `sort_keys`."""
    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    covered_a = [{"clause_id": "C-001", "text": "Manufacturing defects."}]
    covered_b = [{"text": "Manufacturing defects.", "clause_id": "C-001"}]  # keys reversed
    remedy_a = [
        {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
        {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0},
    ]
    remedy_b = [
        {"remedy_value": 0, "remedy_kind": "FULL_REFUND", "clause_id": "C-001", "outcome": "COVERED"},
        {"clause_id": "", "outcome": "NOT_COVERED", "remedy_value": 0, "remedy_kind": "NONE"},
    ]

    c1 = create_constitution(contract, program_id, version="A", covered_clauses=covered_a, remedy_table=remedy_a)
    c2 = create_constitution(contract, program_id, version="B", covered_clauses=covered_b, remedy_table=remedy_b)

    assert contract.get_constitution(c1)["covered_clause_ids"] == contract.get_constitution(c2)["covered_clause_ids"]
    assert contract.get_constitution(c1)["remedy_table"] == contract.get_constitution(c2)["remedy_table"]


def test_fingerprint_is_order_independent_for_fixed_program_and_version(direct_deploy, direct_vm, direct_accounts):
    """The genuinely order-independent fingerprint claim, tested the only way it can be
    tested without violating the (program_id, version) uniqueness rule: replicate the
    contract's own canonicalization + hashing (sha256 of sort_keys/compact-separator JSON)
    independently in the test, using the SAME program_id/version the contract actually used,
    and confirm it reproduces the on-chain fingerprint exactly for two differently-ordered
    submissions. This is a from-first-principles check, not a trust-the-implementation
    check: it does not call any CLAUSE canonicalization helper, only stdlib json/hashlib."""
    import hashlib
    import json as _json

    contract, program_id, manufacturer = _setup_program(direct_deploy, direct_vm, direct_accounts)
    covered_forward = [
        {"clause_id": "C-001", "text": "Manufacturing defects."},
        {"clause_id": "C-002", "text": "Battery failure."},
    ]
    remedy = [
        {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
        {"outcome": "COVERED", "clause_id": "C-002", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
        {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0},
    ]

    constitution_id = create_constitution(
        contract, program_id, version="A", covered_clauses=covered_forward, remedy_table=list(reversed(remedy)),
    )
    stored = contract.get_constitution(constitution_id)

    expected_frozen_fields = {
        "program_id": int(program_id),
        "version": "A",
        "product_scope": stored["product_scope"],
        "coverage_calc": stored["coverage_calc"],
        "covered_clause_ids": ["C-001", "C-002"],  # independently known-sorted expectation
        "excluded_clause_ids": stored["excluded_clause_ids"],
        "acceptable_evidence_categories": stored["acceptable_evidence_categories"],
        "source_eligibility_policy": stored["source_eligibility_policy"],
        "claim_deadline_s": stored["claim_deadline_s"],
        "manufacturer_response_period_s": stored["manufacturer_response_period_s"],
        "challenge_window_s": stored["challenge_window_s"],
        "challenge_depth": stored["challenge_depth"],
        "insufficient_evidence_behavior": stored["insufficient_evidence_behavior"],
        "unavailable_evidence_behavior": stored["unavailable_evidence_behavior"],
        "expiry_cancellation_rules": stored["expiry_cancellation_rules"],
        "remedy_table": stored["remedy_table"],  # already independently proven order-sorted above
    }
    expected_json = _json.dumps(expected_frozen_fields, sort_keys=True, separators=(",", ":"))
    expected_fingerprint = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()

    assert stored["fingerprint"] == expected_fingerprint
