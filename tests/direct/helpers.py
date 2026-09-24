"""Shared builders for CLAUSE Stage 1 direct-mode tests."""

CONTRACT_PATH = "contracts/clause_protocol.py"

ONE_GEN = 10**18

COVERED_CLAUSES = [{"clause_id": "C-001", "text": "Manufacturing defects are covered."}]
EXCLUDED_CLAUSES = [{"clause_id": "X-001", "text": "Water damage is excluded."}]
EVIDENCE_CATEGORIES = ["RECEIPT", "PHOTO", "MANUFACTURER_STATEMENT"]
SOURCE_POLICY = "manufacturer.example.com/warranty-terms only"

DEFAULT_REMEDY_TABLE = [
    {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
    {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0},
    {"outcome": "ACCEPTED_NO_CONTEST", "clause_id": "", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
]

ONE_DAY = 24 * 3600
ONE_YEAR = 365 * ONE_DAY


def create_constitution(
    contract,
    program_id,
    version="2026.1",
    covered_clauses=None,
    excluded_clauses=None,
    evidence_categories=None,
    source_policy=SOURCE_POLICY,
    claim_deadline_s=30 * ONE_DAY,
    manufacturer_response_period_s=14 * ONE_DAY,
    challenge_window_s=7 * ONE_DAY,
    challenge_depth=1,
    insufficient_evidence_behavior="RULE_FOR_MANUFACTURER",
    unavailable_evidence_behavior="RULE_FOR_MANUFACTURER",
    expiry_cancellation_rules="Holder or manufacturer may cancel before any claim is filed.",
    remedy_table=None,
):
    return contract.create_constitution(
        program_id=program_id,
        version=version,
        product_scope="Widget Model X",
        coverage_calc="flat 1-year term from coverage_start",
        covered_clauses=covered_clauses if covered_clauses is not None else COVERED_CLAUSES,
        excluded_clauses=excluded_clauses if excluded_clauses is not None else EXCLUDED_CLAUSES,
        acceptable_evidence_categories=evidence_categories if evidence_categories is not None else EVIDENCE_CATEGORIES,
        source_eligibility_policy=source_policy,
        claim_deadline_s=claim_deadline_s,
        manufacturer_response_period_s=manufacturer_response_period_s,
        challenge_window_s=challenge_window_s,
        challenge_depth=challenge_depth,
        insufficient_evidence_behavior=insufficient_evidence_behavior,
        unavailable_evidence_behavior=unavailable_evidence_behavior,
        expiry_cancellation_rules=expiry_cancellation_rules,
        remedy_table=remedy_table if remedy_table is not None else DEFAULT_REMEDY_TABLE,
    )


def make_commitment_hex(seed: int = 1) -> str:
    return format(seed, "064x")


def setup_program_with_constitution(contract, direct_vm, manufacturer):
    direct_vm.sender = manufacturer
    program_id = contract.create_program("Acme Widgets")
    constitution_id = create_constitution(contract, program_id)
    return program_id, constitution_id


def fund(contract, direct_vm, program_id, manufacturer, amount):
    direct_vm.sender = manufacturer
    direct_vm.value = amount
    try:
        contract.fund_pool(program_id)
    finally:
        direct_vm.value = 0


def issue(
    contract,
    direct_vm,
    program_id,
    constitution_id,
    manufacturer,
    holder,
    max_remedy=5 * ONE_GEN,
    coverage_start=None,
    coverage_end=None,
    commitment_seed=1,
    product_model_id="WIDGET-X-001",
):
    direct_vm.sender = manufacturer
    now = int(contract.now())
    start = now if coverage_start is None else coverage_start
    end = (start + ONE_YEAR) if coverage_end is None else coverage_end
    return contract.issue_warranty(
        program_id=program_id,
        constitution_id=constitution_id,
        holder=holder,
        product_model_id=product_model_id,
        product_commitment_hex=make_commitment_hex(commitment_seed),
        coverage_start=start,
        coverage_end=end,
        max_deterministic_remedy=max_remedy,
    )


# --- Stage 2: Claims + Evidence Locker -----------------------------------------------------

# A source-eligibility policy under CLAUSE's Stage 2 mini-DSL (comma-separated host rules,
# see contracts/clause_protocol.py::_parse_source_policy_hosts / _host_allowed).
STAGE2_SOURCE_POLICY = "docs.genlayer.com,*.manufacturer.example"
STAGE2_EVIDENCE_CATEGORIES = ["RECEIPT", "PHOTO", "MANUFACTURER_PAGE_RENDERED"]


def create_constitution_stage2(contract, program_id, **overrides):
    """Same as create_constitution but defaulted to a real, testable Stage 2 source policy
    and category set (one GET-style category, one *_RENDERED category)."""
    overrides.setdefault("source_policy", STAGE2_SOURCE_POLICY)
    overrides.setdefault("evidence_categories", STAGE2_EVIDENCE_CATEGORIES)
    return create_constitution(contract, program_id, **overrides)


def file_claim(
    contract,
    direct_vm,
    warranty_id,
    holder,
    targeted_clause_ids=None,
    failure_asserted_at=None,
):
    direct_vm.sender = holder
    now = int(contract.now())
    return contract.file_claim(
        warranty_id=warranty_id,
        targeted_clause_ids=targeted_clause_ids if targeted_clause_ids is not None else ["C-001"],
        failure_asserted_at=failure_asserted_at if failure_asserted_at is not None else now,
    )


def respond(contract, direct_vm, claim_id, manufacturer, decision):
    direct_vm.sender = manufacturer
    contract.respond_to_claim(claim_id=claim_id, decision=decision)


def submit_evidence(contract, direct_vm, claim_id, submitter, url, category="RECEIPT"):
    direct_vm.sender = submitter
    return contract.submit_evidence(claim_id=claim_id, original_url=url, category=category)


def freeze_evidence(contract, direct_vm, claim_id, caller):
    direct_vm.sender = caller
    contract.freeze_evidence(claim_id=claim_id)


# --- Stage 3: adjudication fixtures ----------------------------------------------------------
import json as _json_s3

S3_COVERED = [
    {"clause_id": "C-001", "text": "Manufacturing defects in materials or workmanship are covered."},
    {"clause_id": "C-002", "text": "Battery capacity loss below 60 percent within the term is covered."},
]
S3_EXCLUDED = [{"clause_id": "X-001", "text": "Accidental impact or water damage is excluded."}]
S3_URL = "https://docs.genlayer.com/"


def build_frozen_claim(direct_deploy, direct_vm, direct_accounts, evidence=None, failure_offset_s=0,
                       targeted=("C-001",), challenge_window_s=7 * ONE_DAY):
    """Full deterministic setup up to a claim in EVIDENCE_FROZEN, via normal contract calls.
    `evidence` = list of (path, http_status, body); http_status None => no mock (unreachable),
    path starting with 'http' is used as a full URL (e.g. an ineligible host)."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(
        contract, program_id, covered_clauses=S3_COVERED, excluded_clauses=S3_EXCLUDED,
        source_policy="docs.genlayer.com", evidence_categories=["RECEIPT"], challenge_window_s=challenge_window_s,
    )
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    now = int(contract.now())
    claim_id = file_claim(contract, direct_vm, warranty_id, holder, targeted_clause_ids=list(targeted),
                          failure_asserted_at=now + failure_offset_s)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    evidence_ids = []
    for i, (path, status, body) in enumerate(evidence if evidence is not None else [("e1", 200, "Unit failed.")]):
        url = path if path.startswith("http") else S3_URL + path
        if status is not None:
            direct_vm.mock_web(url.replace(".", r"\.").replace("?", r"\?"), {"status": status, "body": body})
        evidence_ids.append(submit_evidence(contract, direct_vm, claim_id, holder, url, "RECEIPT"))
    freeze_evidence(contract, direct_vm, claim_id, holder)
    return {"contract": contract, "manufacturer": manufacturer, "holder": holder, "program_id": program_id,
            "constitution_id": constitution_id, "warranty_id": warranty_id, "claim_id": claim_id,
            "evidence_ids": evidence_ids, "now": now}


def model_result(product_match="PASS", covered=("C-001",), exclusions=(), sufficiency="SUFFICIENT",
                 relied=(1,), rationale="Evidence supports the finding."):
    return {"product_match": product_match, "covered_clause_ids": list(covered),
            "exclusion_clause_ids": list(exclusions), "evidence_sufficiency": sufficiency,
            "evidence_ids_relied_on": list(relied), "rationale": rationale}


def mock_model(direct_vm, result, pattern=r"GOVERNING RULES"):
    """Registers a canned model reply (JSON text or dict). direct-mode auto-parses JSON strings."""
    direct_vm.mock_llm(pattern, result if isinstance(result, str) else _json_s3.dumps(result))


def adjudicate(contract, direct_vm, claim_id, caller):
    direct_vm.sender = caller
    return contract.adjudicate_claim(claim_id=claim_id)
