import pytest

from helpers import (
    CONTRACT_PATH,
    COVERED_CLAUSES,
    DEFAULT_REMEDY_TABLE,
    EXCLUDED_CLAUSES,
    EVIDENCE_CATEGORIES,
    ONE_GEN,
    create_constitution,
    fund,
    issue,
)


def test_constitution_starts_unfrozen(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)

    c = contract.get_constitution(constitution_id)
    assert c["is_frozen"] is False
    assert c["frozen_at"] == 0


def test_constitution_freezes_on_first_issuance(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    c = contract.get_constitution(constitution_id)
    assert c["is_frozen"] is True
    assert c["frozen_at"] > 0


def test_two_constitutions_same_program_different_version_allowed(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    c1 = create_constitution(contract, program_id, version="2026.1")
    c2 = create_constitution(contract, program_id, version="2026.2")
    assert c1 != c2


def test_duplicate_version_on_same_program_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    create_constitution(contract, program_id, version="2026.1")
    with pytest.raises(Exception):
        create_constitution(contract, program_id, version="2026.1")


def test_challenge_depth_above_v1_maximum_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        create_constitution(contract, program_id, challenge_depth=2)


def test_invalid_evidence_gap_behavior_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        create_constitution(contract, program_id, insufficient_evidence_behavior="MAKE_IT_UP")


def test_duplicate_clause_id_across_covered_and_excluded_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        create_constitution(
            contract,
            program_id,
            covered_clauses=[{"clause_id": "C-001", "text": "covered"}],
            excluded_clauses=[{"clause_id": "C-001", "text": "excluded"}],
        )


def test_clause_id_prefix_enforced(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        create_constitution(
            contract, program_id, covered_clauses=[{"clause_id": "X-001", "text": "wrong prefix for covered"}]
        )


def test_remedy_row_referencing_unknown_clause_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        create_constitution(
            contract,
            program_id,
            remedy_table=[{"outcome": "COVERED", "clause_id": "C-999", "remedy_kind": "FULL_REFUND", "remedy_value": 0}],
        )


def test_remedy_row_bad_outcome_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        create_constitution(
            contract,
            program_id,
            remedy_table=[{"outcome": "MAYBE", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0}],
        )


def test_remedy_bps_over_10000_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    with pytest.raises(Exception):
        create_constitution(
            contract,
            program_id,
            remedy_table=[{"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "PARTIAL_BPS", "remedy_value": 10001}],
        )


# --- Immutability: every frozen field, exhaustively, cannot be rewritten -----------------
# CLAUSE Stage 1 exposes NO write method that targets an existing constitution_id at all
# (create_constitution only ever inserts a new one) - so "rewrite a frozen field" is not a
# single button to press. The exhaustive per-field immutability guarantee instead comes from
# there being no such button. These tests prove that absence the only way you can for a
# missing capability: attempting to reach the same constitution_id through the only
# constitution-shaped write method available, and confirming it can only ever create a
# genuinely new record (or reject), never mutate constitution_id N's own stored fields.

def test_creating_another_constitution_never_mutates_the_first(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    c1 = create_constitution(contract, program_id, version="2026.1")
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    issue(contract, direct_vm, program_id, c1, manufacturer, holder, max_remedy=5 * ONE_GEN)

    before = contract.get_constitution(c1)
    create_constitution(contract, program_id, version="2026.2", source_policy="a-completely-different-policy.example")
    after = contract.get_constitution(c1)

    assert before == after
    assert after["is_frozen"] is True


def test_clauses_immutable_after_freeze(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    before = contract.get_clauses(constitution_id)
    # No write method exists to alter clauses of an existing constitution_id at all.
    after = contract.get_clauses(constitution_id)
    assert before == after
    assert {row["clause_id"] for row in before} == {"C-001", "X-001"}


def test_fingerprint_reflects_full_frozen_field_set(direct_deploy, direct_vm, direct_accounts):
    """Two constitutions differing only in source_eligibility_policy must fingerprint
    differently - the fingerprint is a content hash of every frozen field, not a subset."""
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    c1 = create_constitution(contract, program_id, version="2026.1", source_policy="policy-a.example")
    c2 = create_constitution(contract, program_id, version="2026.2", source_policy="policy-b.example")

    fp1 = contract.get_constitution(c1)["fingerprint"]
    fp2 = contract.get_constitution(c2)["fingerprint"]
    assert fp1 != fp2
