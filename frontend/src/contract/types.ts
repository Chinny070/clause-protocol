/**
 * Typed read models for the FROZEN CLAUSE contract interface (docs/FRONTEND_CONTRACT_INTERFACE.md, commit 0b472ce).
 * Amounts are bigint (the SDK returns integers above 2^53 as decimal strings; decode.ts normalizes them).
 */
export type Hex = string;

export type ProgramStatus = "ACTIVE" | "PAUSED" | "RETIRED";
export type PassportStatus = "ACTIVE" | "EXPIRED" | "CANCELLED";
export type ReservationStatus = "ACTIVE" | "RELEASED" | "CONSUMED";
export type ClaimStatus =
  | "RESPONSE_WINDOW" | "ACCEPTED" | "DISPUTED" | "EVIDENCE_FROZEN" | "DECIDED"
  | "CHALLENGED" | "CHALLENGE_RESOLVED" | "FINAL" | "SETTLED";
export type Outcome = "COVERED" | "NOT_COVERED" | "INSUFFICIENT_EVIDENCE" | "EVIDENCE_UNAVAILABLE" | "INVALID_CLAIM" | "ACCEPTED_NO_CONTEST";
export type Tri = "PASS" | "FAIL" | "UNCLEAR";
export type Sufficiency = "SUFFICIENT" | "INSUFFICIENT" | "UNAVAILABLE";
export type RemedyKind = "FULL_REFUND" | "REPAIR_CREDIT" | "PARTIAL_BPS" | "NONE";
export type ChallengeGround =
  | "IGNORED_EVIDENCE" | "WRONG_WARRANTY_VERSION" | "WRONG_CLAUSE" | "EXCLUSION_MISAPPLIED"
  | "TEMPORAL_ERROR" | "SOURCE_AUTHORITY_ERROR" | "PRODUCT_MATCH_ERROR";
export type ChallengeStatus = "OPEN" | "REMAND_PENDING" | "RESOLVED";
export type ChallengeResult = "" | "UPHELD" | "REVERSED" | "REMAND" | "INVALID_CHALLENGE";
export type EvidenceEligibility = "ELIGIBLE" | "INELIGIBLE";
export type RetrievalStatus = "" | "AVAILABLE" | "UNAVAILABLE" | "FETCH_FAILED" | "RENDER_FAILED" | "INSUFFICIENT";
export type EvidenceGapBehavior = "RULE_FOR_HOLDER" | "RULE_FOR_MANUFACTURER" | "BLOCK";

export interface Program { programId: number; manufacturer: Hex; name: string; status: ProgramStatus; createdAt: number }
export interface Pool { poolId: number; programId: number; manufacturer: Hex; totalBalance: bigint; reservedLiability: bigint; availableBalance: bigint }
export interface RemedyRow { outcome: Outcome; clause_id: string; remedy_kind: RemedyKind; remedy_value: bigint }
export interface Constitution {
  constitutionId: number; programId: number; version: string; fingerprint: Hex; productScope: string; coverageCalc: string;
  coveredClauseIds: string[]; excludedClauseIds: string[]; acceptableEvidenceCategories: string[]; sourceEligibilityPolicy: string;
  claimDeadlineS: number; manufacturerResponsePeriodS: number; challengeWindowS: number; challengeDepth: number;
  insufficientEvidenceBehavior: EvidenceGapBehavior; unavailableEvidenceBehavior: EvidenceGapBehavior;
  expiryCancellationRules: string; remedyTable: RemedyRow[]; frozenAt: number; isFrozen: boolean;
}
export interface Clause { clauseId: string; kind: "COVERED" | "EXCLUDED"; text: string }
export interface Passport {
  warrantyId: number; programId: number; manufacturer: Hex; holder: Hex; productModelId: string; productCommitment: Hex;
  registeredAt: number; coverageStart: number; coverageEnd: number; constitutionId: number; constitutionVersion: string;
  constitutionFingerprint: Hex; maxDeterministicRemedy: bigint; reservationId: number; status: PassportStatus;
}
export interface Reservation { reservationId: number; poolId: number; warrantyId: number; amount: bigint; status: ReservationStatus; createdAt: number; releasedAt: number }
export interface Claim {
  claimId: number; warrantyId: number; programId: number; holder: Hex; manufacturer: Hex; constitutionId: number; constitutionFingerprint: Hex;
  failureAssertedAt: number; targetedClauseIds: string[]; filedAt: number; responseDeadline: number; manufacturerResponse: "" | "ACCEPT" | "DISPUTE";
  respondedAt: number; evidenceFrozenAt: number; status: ClaimStatus; adjudicationId: number;
}
export interface Evidence {
  evidenceId: number; claimId: number; submitter: Hex; originalUrl: string; category: string; host: string; retrievalMethod: "GET" | "RENDER";
  submittedAt: number; eligibility: EvidenceEligibility; retrievalStatus: RetrievalStatus; retrievedAt: number; frozenAt: number;
  extractedContent: string; fingerprint: Hex; available: boolean;
}
export interface Adjudication {
  adjudicationId: number; claimId: number; constitutionId: number; adjudicatedAt: number; productMatch: Tri; warrantyVersionMatch: Tri;
  coverageWindow: Tri; coveredClauseIds: string[]; exclusionClauseIds: string[]; evidenceSufficiency: Sufficiency; sourceAuthority: Tri;
  evidenceIdsRelied: number[]; evidenceIdsConsidered: number[]; outcome: Outcome; rationale: string; decisionPath: string;
  challengeWindowClosesAt: number; superseded: boolean;
}
export interface Citation { evidence_ids: number[]; clause_ids: string[]; constitution_id: number; timestamp_field: string }
export interface Challenge {
  challengeId: number; claimId: number; adjudicationId: number; challenger: Hex; ground: ChallengeGround; explanation: string; citation: Citation;
  filedAt: number; status: ChallengeStatus; result: ChallengeResult; resolutionPath: string; resolutionReason: string; remandIssue: string;
  correctedAdjudicationId: number; resolvedAt: number;
}
export interface FinalDecision {
  claimId: number; source: string; adjudicationId: number; challengeId: number; finalOutcome: Outcome; establishedClauseIds: string[];
  remedyBasis: string; remedyKind: RemedyKind; remedyValue: bigint; remedyAmount: bigint; recipient: Hex; finalizedAt: number; settledAt: number;
  settledAmount: bigint; capped: boolean; claimable: bigint; withdrawnAt: number; withdrawnAmount: bigint;
}
export interface ReceiptEvidence { evidenceId: number; category: string; host: string; retrievalStatus: RetrievalStatus; fingerprint: Hex; frozenAt: number }
export interface ResolutionReceipt {
  claimId: number; claimStatus: ClaimStatus;
  warranty: {
    warrantyId: number; holder: Hex; manufacturer: Hex; productModelId: string; coverageStart: number; coverageEnd: number;
    maxDeterministicRemedy: bigint; constitutionId: number; constitutionVersion: string; constitutionFingerprint: Hex;
  };
  claim: { targetedClauseIds: string[]; filedAt: number; manufacturerResponse: string; respondedAt: number; evidenceFrozenAt: number };
  evidence: ReceiptEvidence[]; ineligibleEvidenceCount: number;
  originalAdjudication: Adjudication | null; challenge: Challenge | null; correctedAdjudication: Adjudication | null; finalDecision: FinalDecision | null;
}
