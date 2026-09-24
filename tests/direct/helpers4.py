"""Stage 4 fixtures: full local lifecycles built only through normal contract calls. The model is MOCKED
everywhere here (direct mode); no test built on these helpers claims live model behaviour."""
import datetime
import json

from helpers import (
    CONTRACT_PATH, ONE_DAY, ONE_GEN, S3_COVERED, S3_EXCLUDED, S3_URL, adjudicate, create_constitution_stage2,
    file_claim, freeze_evidence, fund, issue, model_result, respond, submit_evidence,
)

REMEDY_TABLE = [
    {"outcome": "COVERED", "clause_id": "C-001", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
    {"outcome": "COVERED", "clause_id": "C-002", "remedy_kind": "PARTIAL_BPS", "remedy_value": 5000},
    {"outcome": "NOT_COVERED", "clause_id": "", "remedy_kind": "NONE", "remedy_value": 0},
    {"outcome": "ACCEPTED_NO_CONTEST", "clause_id": "", "remedy_kind": "FULL_REFUND", "remedy_value": 0},
]

CITE_NONE = {"evidence_ids": [], "clause_ids": [], "constitution_id": 0, "timestamp_field": ""}


def cite(evidence_ids=(), clause_ids=(), constitution_id=0, timestamp_field=""):
    return {"evidence_ids": list(evidence_ids), "clause_ids": list(clause_ids),
            "constitution_id": constitution_id, "timestamp_field": timestamp_field}


def iso(ts):
    return datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc).isoformat()


def warp_to(direct_vm, ts):
    direct_vm.warp(iso(ts))


def capture_transfers(direct_vm):
    """Records every emitted value transfer as (recipient_hex_lower, value)."""
    sent = []

    def hook(vm, request):
        if "EthSend" in request:
            body = request["EthSend"]
            sent.append((body["address"].as_hex.lower(), int(body["value"])))
        return None

    direct_vm._gl_call_hook = hook
    return sent


def new_contract(direct_deploy, direct_vm, direct_accounts):
    direct_vm.sender = direct_accounts[0]
    return direct_deploy(CONTRACT_PATH)


def build_env(direct_deploy, direct_vm, direct_accounts, *, remedy_table=None, insufficient="RULE_FOR_MANUFACTURER",
              unavailable="RULE_FOR_MANUFACTURER", max_remedy=5 * ONE_GEN, pool_funding=10 * ONE_GEN,
              targeted=("C-001",), evidence=None, decision="DISPUTE", freeze=True, challenge_window_s=7 * ONE_DAY,
              contract=None, program_id=None, constitution_id=None, holder=None, failure_offset_s=0,
              coverage_seconds=365 * ONE_DAY, commitment_seed=1):
    """Program -> constitution -> funded pool -> warranty -> claim -> manufacturer response -> (evidence ->
    freeze). Reuses an existing contract/program/constitution when given (multi-warranty scenarios)."""
    manufacturer = direct_accounts[0]
    holder = holder if holder is not None else direct_accounts[1]
    if contract is None:
        direct_vm.sender = manufacturer
        contract = direct_deploy(CONTRACT_PATH)
        program_id = contract.create_program("Acme")
        constitution_id = create_constitution_stage2(
            contract, program_id, covered_clauses=S3_COVERED, excluded_clauses=S3_EXCLUDED,
            source_policy="docs.genlayer.com", evidence_categories=["RECEIPT"],
            challenge_window_s=challenge_window_s, insufficient_evidence_behavior=insufficient,
            unavailable_evidence_behavior=unavailable,
            remedy_table=remedy_table if remedy_table is not None else REMEDY_TABLE,
        )
        if pool_funding:
            fund(contract, direct_vm, program_id, manufacturer, pool_funding)
    now = int(contract.now())
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder,
                        max_remedy=max_remedy, coverage_start=now, coverage_end=now + coverage_seconds,
                        commitment_seed=commitment_seed)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder, targeted_clause_ids=list(targeted),
                          failure_asserted_at=now + failure_offset_s)
    env = {"contract": contract, "manufacturer": manufacturer, "holder": holder, "other": direct_accounts[2],
           "program_id": program_id, "constitution_id": constitution_id, "warranty_id": warranty_id,
           "claim_id": claim_id, "evidence_ids": [], "now": now, "max_remedy": max_remedy}
    if decision is None:
        return env
    respond(contract, direct_vm, claim_id, manufacturer, decision)
    if decision == "ACCEPT":
        return env
    ev = evidence if evidence is not None else [("e1", 200, "Unit failed.")]
    for path, status, body in ev:
        url = path if path.startswith("http") else S3_URL + path
        if status is not None:
            direct_vm.mock_web(url.replace(".", r"\.").replace("?", r"\?"), {"status": status, "body": body})
        env["evidence_ids"].append(submit_evidence(contract, direct_vm, claim_id, holder, url, "RECEIPT"))
    if freeze:
        freeze_evidence(contract, direct_vm, claim_id, holder)
    return env


def mock_reply(direct_vm, reply, pattern):
    direct_vm.clear_mocks()
    direct_vm.mock_llm(pattern, reply if isinstance(reply, str) else json.dumps(reply))


ADJ_PATTERN = r"GOVERNING RULES"
CHAL_PATTERN = r"ORIGINAL ADJUDICATION \(the decision under review\)"
REMAND_PATTERN = r"RECONSIDERATION \(bounded\)"


def decide(env, direct_vm, reply=None, caller=None):
    """Adjudicate (model mocked unless the claim short-circuits deterministically)."""
    if reply is not None:
        mock_reply(direct_vm, reply, ADJ_PATTERN)
    return adjudicate(env["contract"], direct_vm, env["claim_id"], caller or env["holder"])


def review(direct_vm, decision="DEFECT_NOT_CONFIRMED", corrections=None, remand_issue="", reasoning="Reviewed."):
    return {"decision": decision, "corrections": corrections or {}, "remand_issue": remand_issue, "reasoning": reasoning}


def challenge(env, direct_vm, ground, citation, explanation="The decision looks wrong.", who=None):
    direct_vm.sender = who or env["holder"]
    return env["contract"].file_challenge(claim_id=env["claim_id"], ground=ground, explanation=explanation, citation=citation)


def resolve(env, direct_vm, reply=None, caller=None):
    if reply is not None:
        mock_reply(direct_vm, reply, CHAL_PATTERN)
    direct_vm.sender = caller or env["other"]
    return env["contract"].resolve_challenge(claim_id=env["claim_id"])


def finalize(env, direct_vm, caller=None):
    direct_vm.sender = caller or env["other"]
    env["contract"].finalize_claim(claim_id=env["claim_id"])


def settle(env, direct_vm, caller=None):
    direct_vm.sender = caller or env["other"]
    env["contract"].settle_claim(claim_id=env["claim_id"])


def withdraw(env, direct_vm, caller=None):
    direct_vm.sender = caller or env["holder"]
    env["contract"].withdraw_settlement(claim_id=env["claim_id"])


def past_challenge_window(env, direct_vm):
    a = env["contract"].get_adjudication(env["contract"].get_claim(env["claim_id"])["adjudication_id"])
    warp_to(direct_vm, a["challenge_window_closes_at"] + 1)


COVERED_REPLY = model_result()
