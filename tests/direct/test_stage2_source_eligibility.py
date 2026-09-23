import pytest

from helpers import (
    CONTRACT_PATH, ONE_GEN, create_constitution_stage2, file_claim, fund, issue, respond,
    submit_evidence,
)


def _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, source_policy):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id, source_policy=source_policy)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    return contract, manufacturer, holder, claim_id


def test_exact_allowed_host_eligible(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example/warranty-terms", "RECEIPT")
    assert contract.get_evidence(evidence_id)["eligibility"] == "ELIGIBLE"


def test_bare_host_does_not_match_subdomain_by_default(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://support.manufacturer.example/page", "RECEIPT")
    assert contract.get_evidence(evidence_id)["eligibility"] == "INELIGIBLE"


def test_wildcard_subdomain_policy_allows_subdomain(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "*.manufacturer.example")
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://support.manufacturer.example/page", "RECEIPT")
    assert contract.get_evidence(evidence_id)["eligibility"] == "ELIGIBLE"


def test_wildcard_subdomain_policy_excludes_bare_domain(direct_deploy, direct_vm, direct_accounts):
    """A "*.manufacturer.example" rule matches subdomains only - the bare domain must be
    listed separately if it should also be allowed."""
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "*.manufacturer.example")
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example/page", "RECEIPT")
    assert contract.get_evidence(evidence_id)["eligibility"] == "INELIGIBLE"


def test_domain_suffix_lookalike_attack_rejected(direct_deploy, direct_vm, direct_accounts):
    """Exact host-boundary test from the build brief: policy allows only "manufacturer.example"
    (no wildcard); "manufacturer.example.attacker.example" must NOT be treated as eligible
    just because it starts with the allowed string."""
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    evidence_id = submit_evidence(
        contract, direct_vm, claim_id, holder, "https://manufacturer.example.attacker.example/page", "RECEIPT",
    )
    assert contract.get_evidence(evidence_id)["eligibility"] == "INELIGIBLE"


def test_lookalike_prefix_attack_rejected(direct_deploy, direct_vm, direct_accounts):
    """The mirror-image lookalike: a host that merely CONTAINS the allowed domain as a
    substring, but is not it and is not a subdomain of it."""
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    evidence_id = submit_evidence(
        contract, direct_vm, claim_id, holder, "https://notmanufacturer.example/page", "RECEIPT",
    )
    assert contract.get_evidence(evidence_id)["eligibility"] == "INELIGIBLE"


def test_wrong_scheme_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "http://manufacturer.example/page", "RECEIPT")
    assert contract.get_evidence(evidence_id)["eligibility"] == "INELIGIBLE"


def test_javascript_scheme_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    evidence_id = submit_evidence(contract, direct_vm, claim_id, holder, "javascript://manufacturer.example/x", "RECEIPT")
    assert contract.get_evidence(evidence_id)["eligibility"] == "INELIGIBLE"


def test_malformed_url_missing_scheme_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, "manufacturer.example/page", "RECEIPT")


def test_empty_url_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, "", "RECEIPT")


def test_oversized_url_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    long_url = "https://manufacturer.example/" + ("x" * 600)
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, long_url, "RECEIPT")


def test_category_not_in_constitution_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example/page", "NOT_A_REAL_CATEGORY")


def test_duplicate_evidence_url_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example/page", "RECEIPT")
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example/page", "RECEIPT")


def test_duplicate_evidence_url_normalization_query_order_still_flagged_if_identical(direct_deploy, direct_vm, direct_accounts):
    """Same scheme/host/path/query string submitted twice (byte-identical) is a duplicate -
    normalization here covers scheme/host case only, documented as a Stage 2 simplification,
    not full query-parameter-order canonicalization."""
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    submit_evidence(contract, direct_vm, claim_id, holder, "https://Manufacturer.Example/page", "RECEIPT")
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example/page", "RECEIPT")


def test_port_included_in_dedupe_key(direct_deploy, direct_vm, direct_accounts):
    """Two URLs differing only by explicit port are NOT treated as duplicates - a different
    port is a different endpoint. The eligibility policy in this Stage 2 mini-DSL matches on
    host only (not port), so both remain ELIGIBLE; the point of this test is that the second
    submission is accepted at all (not rejected as a duplicate of the first)."""
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example:8443/page", "RECEIPT")
    evidence_id_2 = submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example:9443/page", "RECEIPT")
    assert contract.get_evidence(evidence_id_2)["eligibility"] == "ELIGIBLE"


def test_manufacturer_can_also_submit_evidence(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    evidence_id = submit_evidence(contract, direct_vm, claim_id, manufacturer, "https://manufacturer.example/counter-evidence", "RECEIPT")
    assert contract.get_evidence(evidence_id)["submitter"] is not None


def test_stranger_cannot_submit_evidence(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_disputed_claim(direct_deploy, direct_vm, direct_accounts, "manufacturer.example")
    stranger = direct_accounts[2]
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, stranger, "https://manufacturer.example/page", "RECEIPT")


def test_evidence_submission_before_dispute_rejected(direct_deploy, direct_vm, direct_accounts):
    """Evidence cannot be submitted while a claim is still in RESPONSE_WINDOW or ACCEPTED -
    only DISPUTED claims accept evidence."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id, source_policy="manufacturer.example")
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    with pytest.raises(Exception):
        submit_evidence(contract, direct_vm, claim_id, holder, "https://manufacturer.example/page", "RECEIPT")
