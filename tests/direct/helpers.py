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
