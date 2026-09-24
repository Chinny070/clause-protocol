import type {
  Adjudication, Challenge, Citation, Claim, Clause, Constitution, Evidence, FinalDecision, Passport, Pool, Program,
  RemedyRow, Reservation, ResolutionReceipt,
} from "./types";

export class DecodeError extends Error {
  constructor(what: string, detail: string) {
    super(`Unexpected ${what} from the contract: ${detail}`);
    this.name = "DecodeError";
  }
}

type Raw = Record<string, unknown>;

/** The SDK returns small integers as numbers and integers above 2^53 as decimal strings. Amounts become bigint. */
export function toBigInt(v: unknown, field: string): bigint {
  if (typeof v === "bigint") return v;
  if (typeof v === "number" && Number.isSafeInteger(v) && v >= 0) return BigInt(v);
  if (typeof v === "string" && /^\d+$/.test(v)) return BigInt(v);
  throw new DecodeError(field, `not a non-negative integer (${typeof v})`);
}

export function toInt(v: unknown, field: string): number {
  if (typeof v === "number" && Number.isSafeInteger(v) && v >= 0) return v;
  if (typeof v === "bigint" && v >= 0n && v <= BigInt(Number.MAX_SAFE_INTEGER)) return Number(v);
  if (typeof v === "string" && /^\d+$/.test(v) && Number(v) <= Number.MAX_SAFE_INTEGER) return Number(v);
  throw new DecodeError(field, `not a safe non-negative integer (${typeof v})`);
}

function str(v: unknown, field: string): string {
  if (typeof v === "string") return v;
  throw new DecodeError(field, `not a string (${typeof v})`);
}
function bool(v: unknown, field: string): boolean {
  if (typeof v === "boolean") return v;
  throw new DecodeError(field, `not a boolean (${typeof v})`);
}
function arr(v: unknown, field: string): unknown[] {
  if (Array.isArray(v)) return v;
  throw new DecodeError(field, `not a list (${typeof v})`);
}
function strList(v: unknown, field: string): string[] { return arr(v, field).map((x, i) => str(x, `${field}[${i}]`)); }
function intList(v: unknown, field: string): number[] { return arr(v, field).map((x, i) => toInt(x, `${field}[${i}]`)); }

function asRaw(v: unknown): Raw | null {
  if (v instanceof Map) return Object.fromEntries(v as Map<string, unknown>);
  if (typeof v === "object" && v !== null && !Array.isArray(v)) return v as Raw;
  return null;
}
function raw(v: unknown, what: string): Raw {
  const r = asRaw(v);
  if (r === null) throw new DecodeError(what, "not an object");
  return r;
}
/** `{}` means "unknown id" in the frozen interface. */
export function isEmptyObject(v: unknown): boolean {
  const r = asRaw(v);
  return r !== null && Object.keys(r).length === 0;
}

export function decodeProgram(v: unknown): Program | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "program");
  return { programId: toInt(r.program_id, "program_id"), manufacturer: str(r.manufacturer, "manufacturer"), name: str(r.name, "name"),
    status: str(r.status, "status") as Program["status"], createdAt: toInt(r.created_at, "created_at") };
}
export function decodePool(v: unknown): Pool | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "pool");
  return { poolId: toInt(r.pool_id, "pool_id"), programId: toInt(r.program_id, "program_id"), manufacturer: str(r.manufacturer, "manufacturer"),
    totalBalance: toBigInt(r.total_balance, "total_balance"), reservedLiability: toBigInt(r.reserved_liability, "reserved_liability"),
    availableBalance: toBigInt(r.available_balance, "available_balance") };
}
export function decodeRemedyTable(v: unknown): RemedyRow[] {
  return arr(v, "remedy_table").map((x, i) => {
    const r = raw(x, `remedy_table[${i}]`);
    return { outcome: str(r.outcome, "outcome") as RemedyRow["outcome"], clause_id: str(r.clause_id, "clause_id"),
      remedy_kind: str(r.remedy_kind, "remedy_kind") as RemedyRow["remedy_kind"], remedy_value: toBigInt(r.remedy_value, "remedy_value") };
  });
}
export function decodeConstitution(v: unknown): Constitution | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "constitution");
  return {
    constitutionId: toInt(r.constitution_id, "constitution_id"), programId: toInt(r.program_id, "program_id"), version: str(r.version, "version"),
    fingerprint: str(r.fingerprint, "fingerprint"), productScope: str(r.product_scope, "product_scope"), coverageCalc: str(r.coverage_calc, "coverage_calc"),
    coveredClauseIds: strList(r.covered_clause_ids, "covered_clause_ids"), excludedClauseIds: strList(r.excluded_clause_ids, "excluded_clause_ids"),
    acceptableEvidenceCategories: strList(r.acceptable_evidence_categories, "acceptable_evidence_categories"),
    sourceEligibilityPolicy: str(r.source_eligibility_policy, "source_eligibility_policy"),
    claimDeadlineS: toInt(r.claim_deadline_s, "claim_deadline_s"), manufacturerResponsePeriodS: toInt(r.manufacturer_response_period_s, "manufacturer_response_period_s"),
    challengeWindowS: toInt(r.challenge_window_s, "challenge_window_s"), challengeDepth: toInt(r.challenge_depth, "challenge_depth"),
    insufficientEvidenceBehavior: str(r.insufficient_evidence_behavior, "insufficient_evidence_behavior") as Constitution["insufficientEvidenceBehavior"],
    unavailableEvidenceBehavior: str(r.unavailable_evidence_behavior, "unavailable_evidence_behavior") as Constitution["unavailableEvidenceBehavior"],
    expiryCancellationRules: str(r.expiry_cancellation_rules, "expiry_cancellation_rules"), remedyTable: decodeRemedyTable(r.remedy_table),
    frozenAt: toInt(r.frozen_at, "frozen_at"), isFrozen: bool(r.is_frozen, "is_frozen"),
  };
}
export function decodeClauses(v: unknown): Clause[] {
  return arr(v, "clauses").map((x, i) => {
    const r = raw(x, `clauses[${i}]`);
    return { clauseId: str(r.clause_id, "clause_id"), kind: str(r.kind, "kind") as Clause["kind"], text: str(r.text, "text") };
  });
}
export function decodePassport(v: unknown): Passport | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "passport");
  return {
    warrantyId: toInt(r.warranty_id, "warranty_id"), programId: toInt(r.program_id, "program_id"), manufacturer: str(r.manufacturer, "manufacturer"),
    holder: str(r.holder, "holder"), productModelId: str(r.product_model_id, "product_model_id"), productCommitment: str(r.product_commitment, "product_commitment"),
    registeredAt: toInt(r.registered_at, "registered_at"), coverageStart: toInt(r.coverage_start, "coverage_start"), coverageEnd: toInt(r.coverage_end, "coverage_end"),
    constitutionId: toInt(r.constitution_id, "constitution_id"), constitutionVersion: str(r.constitution_version, "constitution_version"),
    constitutionFingerprint: str(r.constitution_fingerprint, "constitution_fingerprint"),
    maxDeterministicRemedy: toBigInt(r.max_deterministic_remedy, "max_deterministic_remedy"), reservationId: toInt(r.reservation_id, "reservation_id"),
    status: str(r.status, "status") as Passport["status"],
  };
}
export function decodeReservation(v: unknown): Reservation | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "reservation");
  return { reservationId: toInt(r.reservation_id, "reservation_id"), poolId: toInt(r.pool_id, "pool_id"), warrantyId: toInt(r.warranty_id, "warranty_id"),
    amount: toBigInt(r.amount, "amount"), status: str(r.status, "status") as Reservation["status"], createdAt: toInt(r.created_at, "created_at"),
    releasedAt: toInt(r.released_at, "released_at") };
}
export function decodeClaim(v: unknown): Claim | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "claim");
  return {
    claimId: toInt(r.claim_id, "claim_id"), warrantyId: toInt(r.warranty_id, "warranty_id"), programId: toInt(r.program_id, "program_id"),
    holder: str(r.holder, "holder"), manufacturer: str(r.manufacturer, "manufacturer"), constitutionId: toInt(r.constitution_id, "constitution_id"),
    constitutionFingerprint: str(r.constitution_fingerprint, "constitution_fingerprint"), failureAssertedAt: toInt(r.failure_asserted_at, "failure_asserted_at"),
    targetedClauseIds: strList(r.targeted_clause_ids, "targeted_clause_ids"), filedAt: toInt(r.filed_at, "filed_at"),
    responseDeadline: toInt(r.response_deadline, "response_deadline"), manufacturerResponse: str(r.manufacturer_response, "manufacturer_response") as Claim["manufacturerResponse"],
    respondedAt: toInt(r.responded_at, "responded_at"), evidenceFrozenAt: toInt(r.evidence_frozen_at, "evidence_frozen_at"),
    status: str(r.status, "status") as Claim["status"], adjudicationId: toInt(r.adjudication_id, "adjudication_id"),
  };
}
export function decodeEvidence(v: unknown): Evidence | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "evidence");
  return {
    evidenceId: toInt(r.evidence_id, "evidence_id"), claimId: toInt(r.claim_id, "claim_id"), submitter: str(r.submitter, "submitter"),
    originalUrl: str(r.original_url, "original_url"), category: str(r.category, "category"), host: str(r.host, "host"),
    retrievalMethod: str(r.retrieval_method, "retrieval_method") as Evidence["retrievalMethod"], submittedAt: toInt(r.submitted_at, "submitted_at"),
    eligibility: str(r.eligibility, "eligibility") as Evidence["eligibility"], retrievalStatus: str(r.retrieval_status, "retrieval_status") as Evidence["retrievalStatus"],
    retrievedAt: toInt(r.retrieved_at, "retrieved_at"), frozenAt: toInt(r.frozen_at, "frozen_at"), extractedContent: str(r.extracted_content, "extracted_content"),
    fingerprint: str(r.fingerprint, "fingerprint"), available: bool(r.available, "available"),
  };
}
export function decodeAdjudication(v: unknown): Adjudication | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "adjudication");
  return {
    adjudicationId: toInt(r.adjudication_id, "adjudication_id"), claimId: toInt(r.claim_id, "claim_id"), constitutionId: toInt(r.constitution_id, "constitution_id"),
    adjudicatedAt: toInt(r.adjudicated_at, "adjudicated_at"), productMatch: str(r.product_match, "product_match") as Adjudication["productMatch"],
    warrantyVersionMatch: str(r.warranty_version_match, "warranty_version_match") as Adjudication["warrantyVersionMatch"],
    coverageWindow: str(r.coverage_window, "coverage_window") as Adjudication["coverageWindow"],
    coveredClauseIds: strList(r.covered_clause_ids, "covered_clause_ids"), exclusionClauseIds: strList(r.exclusion_clause_ids, "exclusion_clause_ids"),
    evidenceSufficiency: str(r.evidence_sufficiency, "evidence_sufficiency") as Adjudication["evidenceSufficiency"],
    sourceAuthority: str(r.source_authority, "source_authority") as Adjudication["sourceAuthority"],
    evidenceIdsRelied: intList(r.evidence_ids_relied_on, "evidence_ids_relied_on"), evidenceIdsConsidered: intList(r.evidence_ids_considered, "evidence_ids_considered"),
    outcome: str(r.outcome, "outcome") as Adjudication["outcome"], rationale: str(r.rationale, "rationale"), decisionPath: str(r.decision_path, "decision_path"),
    challengeWindowClosesAt: toInt(r.challenge_window_closes_at, "challenge_window_closes_at"), superseded: bool(r.superseded, "superseded"),
  };
}
function decodeCitation(v: unknown): Citation {
  const r = raw(v, "citation");
  return { evidence_ids: intList(r.evidence_ids, "evidence_ids"), clause_ids: strList(r.clause_ids, "clause_ids"),
    constitution_id: toInt(r.constitution_id, "constitution_id"), timestamp_field: str(r.timestamp_field, "timestamp_field") };
}
export function decodeChallenge(v: unknown): Challenge | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "challenge");
  return {
    challengeId: toInt(r.challenge_id, "challenge_id"), claimId: toInt(r.claim_id, "claim_id"), adjudicationId: toInt(r.adjudication_id, "adjudication_id"),
    challenger: str(r.challenger, "challenger"), ground: str(r.ground, "ground") as Challenge["ground"], explanation: str(r.explanation, "explanation"),
    citation: decodeCitation(r.citation), filedAt: toInt(r.filed_at, "filed_at"), status: str(r.status, "status") as Challenge["status"],
    result: str(r.result, "result") as Challenge["result"], resolutionPath: str(r.resolution_path, "resolution_path"), resolutionReason: str(r.resolution_reason, "resolution_reason"),
    remandIssue: str(r.remand_issue, "remand_issue"), correctedAdjudicationId: toInt(r.corrected_adjudication_id, "corrected_adjudication_id"),
    resolvedAt: toInt(r.resolved_at, "resolved_at"),
  };
}
export function decodeFinalDecision(v: unknown): FinalDecision | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "final decision");
  return {
    claimId: toInt(r.claim_id, "claim_id"), source: str(r.source, "source"), adjudicationId: toInt(r.adjudication_id, "adjudication_id"),
    challengeId: toInt(r.challenge_id, "challenge_id"), finalOutcome: str(r.final_outcome, "final_outcome") as FinalDecision["finalOutcome"],
    establishedClauseIds: strList(r.established_clause_ids, "established_clause_ids"), remedyBasis: str(r.remedy_basis, "remedy_basis"),
    remedyKind: str(r.remedy_kind, "remedy_kind") as FinalDecision["remedyKind"], remedyValue: toBigInt(r.remedy_value, "remedy_value"),
    remedyAmount: toBigInt(r.remedy_amount, "remedy_amount"), recipient: str(r.recipient, "recipient"), finalizedAt: toInt(r.finalized_at, "finalized_at"),
    settledAt: toInt(r.settled_at, "settled_at"), settledAmount: toBigInt(r.settled_amount, "settled_amount"), capped: bool(r.capped, "capped"),
    claimable: toBigInt(r.claimable, "claimable"), withdrawnAt: toInt(r.withdrawn_at, "withdrawn_at"), withdrawnAmount: toBigInt(r.withdrawn_amount, "withdrawn_amount"),
  };
}
export function decodeReceipt(v: unknown): ResolutionReceipt | null {
  if (isEmptyObject(v)) return null;
  const r = raw(v, "receipt");
  const w = raw(r.warranty, "receipt.warranty");
  const c = raw(r.claim, "receipt.claim");
  return {
    claimId: toInt(r.claim_id, "claim_id"), claimStatus: str(r.claim_status, "claim_status") as ResolutionReceipt["claimStatus"],
    warranty: {
      warrantyId: toInt(w.warranty_id, "warranty_id"), holder: str(w.holder, "holder"), manufacturer: str(w.manufacturer, "manufacturer"),
      productModelId: str(w.product_model_id, "product_model_id"), coverageStart: toInt(w.coverage_start, "coverage_start"), coverageEnd: toInt(w.coverage_end, "coverage_end"),
      maxDeterministicRemedy: toBigInt(w.max_deterministic_remedy, "max_deterministic_remedy"), constitutionId: toInt(w.constitution_id, "constitution_id"),
      constitutionVersion: str(w.constitution_version, "constitution_version"), constitutionFingerprint: str(w.constitution_fingerprint, "constitution_fingerprint"),
    },
    claim: { targetedClauseIds: strList(c.targeted_clause_ids, "targeted_clause_ids"), filedAt: toInt(c.filed_at, "filed_at"),
      manufacturerResponse: str(c.manufacturer_response, "manufacturer_response"), respondedAt: toInt(c.responded_at, "responded_at"),
      evidenceFrozenAt: toInt(c.evidence_frozen_at, "evidence_frozen_at") },
    evidence: arr(r.evidence, "evidence").map((x, i) => {
      const e = raw(x, `evidence[${i}]`);
      return { evidenceId: toInt(e.evidence_id, "evidence_id"), category: str(e.category, "category"), host: str(e.host, "host"),
        retrievalStatus: str(e.retrieval_status, "retrieval_status") as ResolutionReceipt["evidence"][number]["retrievalStatus"],
        fingerprint: str(e.fingerprint, "fingerprint"), frozenAt: toInt(e.frozen_at, "frozen_at") };
    }),
    ineligibleEvidenceCount: toInt(r.ineligible_evidence_count, "ineligible_evidence_count"),
    originalAdjudication: decodeAdjudication(r.original_adjudication), challenge: decodeChallenge(r.challenge),
    correctedAdjudication: decodeAdjudication(r.corrected_adjudication), finalDecision: decodeFinalDecision(r.final_decision),
  };
}
export function decodeIdList(v: unknown, field: string): number[] { return intList(v, field); }
export function decodeU64(v: unknown, field: string): number { return toInt(v, field); }
