import datetime

import pytest

from helpers import (
    CONTRACT_PATH, ONE_GEN, create_constitution_stage2, file_claim, fund, issue, respond,
)


def _iso(unix_seconds: int) -> str:
    return datetime.datetime.fromtimestamp(unix_seconds, tz=datetime.timezone.utc).isoformat()


def _setup(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    return contract, program_id, constitution_id, manufacturer, holder, warranty_id


def test_valid_claim_fields(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    claim_id = file_claim(contract, direct_vm, warranty_id, holder, targeted_clause_ids=["C-001"], failure_asserted_at=now - 100)
    claim = contract.get_claim(claim_id)
    assert claim["warranty_id"] == warranty_id
    assert claim["program_id"] == program_id
    assert claim["constitution_id"] == constitution_id
    assert claim["targeted_clause_ids"] == ["C-001"]
    assert claim["status"] == "RESPONSE_WINDOW"
    assert claim["failure_asserted_at"] == now - 100
    assert claim["filed_at"] == now
    assert claim["response_deadline"] > now


def test_constitution_fingerprint_captured_immutably(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    claim = contract.get_claim(claim_id)
    constitution = contract.get_constitution(constitution_id)
    assert claim["constitution_fingerprint"] == constitution["fingerprint"]

    # Creating a NEW constitution under the same program afterward must never redirect this
    # already-filed claim's governing reference.
    direct_vm.sender = manufacturer
    create_constitution_stage2(contract, program_id, version="2026.2")
    claim_after = contract.get_claim(claim_id)
    assert claim_after["constitution_id"] == constitution_id
    assert claim_after["constitution_fingerprint"] == constitution["fingerprint"]


def test_unauthorized_claimant_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    stranger = direct_accounts[2]
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, stranger)


def test_manufacturer_cannot_file_claim_on_own_warranty(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, manufacturer)


def test_nonexistent_passport_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, 999, holder)


def test_invalid_covered_clause_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder, targeted_clause_ids=["C-999"])


def test_exclusion_clause_supplied_as_covered_rejected(direct_deploy, direct_vm, direct_accounts):
    """X-001 exists on the constitution but is an exclusion, not a covered clause - citing it
    as a targeted clause for a claim must be rejected, not silently accepted."""
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder, targeted_clause_ids=["X-001"])


def test_empty_targeted_clauses_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder, targeted_clause_ids=[])


def test_duplicate_targeted_clause_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder, targeted_clause_ids=["C-001", "C-001"])


def test_duplicate_open_claim_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    file_claim(contract, direct_vm, warranty_id, holder)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder)


def test_new_claim_allowed_after_prior_claim_accepted(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    claim1 = file_claim(contract, direct_vm, warranty_id, holder)
    respond(contract, direct_vm, claim1, manufacturer, "ACCEPT")
    claim2 = file_claim(contract, direct_vm, warranty_id, holder)
    assert claim2 != claim1


def test_claim_before_coverage_start_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=5 * ONE_GEN, coverage_start=now + 10_000, coverage_end=now + 20_000,
    )
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder)


def test_claim_at_exact_deadline_boundary_succeeds(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id, claim_deadline_s=1000)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=5 * ONE_GEN, coverage_start=now, coverage_end=now + 500,
    )
    direct_vm.warp(_iso(now + 500 + 1000))  # exactly coverage_end + claim_deadline_s
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    assert contract.get_claim(claim_id)["claim_id"] == claim_id


def test_claim_one_second_past_deadline_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id, claim_deadline_s=1000)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=5 * ONE_GEN, coverage_start=now, coverage_end=now + 500,
    )
    direct_vm.warp(_iso(now + 500 + 1000 + 1))
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder)


def test_invalid_failure_date_type_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        contract.file_claim(warranty_id=warranty_id, targeted_clause_ids=["C-001"], failure_asserted_at="not-a-number")


def test_claim_against_cancelled_warranty_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder, warranty_id = _setup(direct_deploy, direct_vm, direct_accounts)
    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder)


def test_claim_against_expired_warranty_rejected(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id, claim_deadline_s=0)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=5 * ONE_GEN, coverage_start=now, coverage_end=now + 100,
    )
    direct_vm.warp(_iso(now + 200))  # expired AND past the (zero) claim deadline
    with pytest.raises(Exception):
        file_claim(contract, direct_vm, warranty_id, holder)
