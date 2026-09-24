import type { Calldata } from "./transport";
import type { ChallengeGround, Citation, RemedyRow } from "./types";

/**
 * One prepared contract call. `params` are the contract's own parameter names in order (checked against
 * docs/FRONTEND_CONTRACT_INTERFACE.md by tests/abi-parity.test.ts), so the frontend cannot drift from the frozen ABI.
 */
export interface CallSpec {
  functionName: string;
  params: readonly string[];
  args: Calldata[];
  value: bigint;
  label: string;
  /** True for steps that move value or cannot be undone; the UI requires explicit confirmation and finality gating. */
  irreversible: boolean;
  /** Contract state the call needs finalized on the protocol first (frontend-enforced; the contract cannot verify it). */
  finalityPrerequisites: readonly string[];
}

export class CallBuildError extends Error {
  constructor(message: string) { super(message); this.name = "CallBuildError"; }
}

function uint(v: number | bigint, name: string): number {
  if (typeof v === "bigint") {
    if (v < 0n || v > BigInt(Number.MAX_SAFE_INTEGER)) throw new CallBuildError(`${name} must be a safe non-negative integer`);
    return Number(v);
  }
  if (!Number.isSafeInteger(v) || v < 0) throw new CallBuildError(`${name} must be a safe non-negative integer`);
  return v;
}
function nonEmpty(v: string, name: string): string {
  if (typeof v !== "string" || v.trim() === "") throw new CallBuildError(`${name} must not be empty`);
  return v;
}
function id(v: number, name: string): number {
  const n = uint(v, name);
  if (n === 0) throw new CallBuildError(`${name} must be greater than 0`);
  return n;
}

function spec(functionName: string, params: readonly string[], args: Calldata[], label: string, extra: Partial<Pick<CallSpec, "value" | "irreversible" | "finalityPrerequisites">> = {}): CallSpec {
  if (params.length !== args.length) throw new CallBuildError(`${functionName}: argument count does not match the frozen ABI`);
  return { functionName, params, args, value: extra.value ?? 0n, label, irreversible: extra.irreversible ?? false, finalityPrerequisites: extra.finalityPrerequisites ?? [] };
}

export interface ConstitutionInput {
  programId: number; version: string; productScope: string; coverageCalc: string;
  coveredClauses: { clause_id: string; text: string }[]; excludedClauses: { clause_id: string; text: string }[];
  acceptableEvidenceCategories: string[]; sourceEligibilityPolicy: string;
  claimDeadlineS: number; manufacturerResponsePeriodS: number; challengeWindowS: number; challengeDepth: 0 | 1;
  insufficientEvidenceBehavior: string; unavailableEvidenceBehavior: string; expiryCancellationRules: string; remedyTable: RemedyRow[];
}
export interface IssueInput {
  programId: number; constitutionId: number; holder: string; productModelId: string; productCommitmentHex: string;
  coverageStart: number; coverageEnd: number; maxDeterministicRemedy: bigint;
}

export const calls = {
  createProgram: (name: string) => spec("create_program", ["name"], [nonEmpty(name, "name")], "Create warranty program"),
  pauseProgram: (programId: number) => spec("pause_program", ["program_id"], [id(programId, "program_id")], "Pause program"),
  resumeProgram: (programId: number) => spec("resume_program", ["program_id"], [id(programId, "program_id")], "Resume program"),
  retireProgram: (programId: number) => spec("retire_program", ["program_id"], [id(programId, "program_id")], "Retire program", { irreversible: true }),
  fundPool: (programId: number, amount: bigint) => {
    if (amount <= 0n) throw new CallBuildError("amount must be greater than 0");
    return spec("fund_pool", ["program_id"], [id(programId, "program_id")], "Fund warranty capacity", { value: amount });
  },
  withdrawPool: (programId: number, amount: bigint) => {
    if (amount <= 0n) throw new CallBuildError("amount must be greater than 0");
    return spec("withdraw_pool", ["program_id", "amount"], [id(programId, "program_id"), amount], "Withdraw unreserved capacity", { irreversible: true });
  },
  createConstitution: (c: ConstitutionInput) =>
    spec("create_constitution",
      ["program_id", "version", "product_scope", "coverage_calc", "covered_clauses", "excluded_clauses", "acceptable_evidence_categories",
        "source_eligibility_policy", "claim_deadline_s", "manufacturer_response_period_s", "challenge_window_s", "challenge_depth",
        "insufficient_evidence_behavior", "unavailable_evidence_behavior", "expiry_cancellation_rules", "remedy_table"],
      [id(c.programId, "program_id"), nonEmpty(c.version, "version"), c.productScope, c.coverageCalc,
        c.coveredClauses.map((x) => ({ clause_id: x.clause_id, text: x.text })), c.excludedClauses.map((x) => ({ clause_id: x.clause_id, text: x.text })),
        c.acceptableEvidenceCategories, c.sourceEligibilityPolicy, uint(c.claimDeadlineS, "claim_deadline_s"),
        uint(c.manufacturerResponsePeriodS, "manufacturer_response_period_s"), uint(c.challengeWindowS, "challenge_window_s"), c.challengeDepth,
        c.insufficientEvidenceBehavior, c.unavailableEvidenceBehavior, c.expiryCancellationRules,
        c.remedyTable.map((r) => ({ outcome: r.outcome, clause_id: r.clause_id, remedy_kind: r.remedy_kind, remedy_value: r.remedy_value }))],
      "Freeze warranty terms"),
  issueWarranty: (i: IssueInput) => {
    if (i.maxDeterministicRemedy <= 0n) throw new CallBuildError("max_deterministic_remedy must be greater than 0");
    if (!/^[0-9a-fA-F]{64}$/.test(i.productCommitmentHex)) throw new CallBuildError("product_commitment_hex must be 64 hex characters");
    if (uint(i.coverageStart, "coverage_start") >= uint(i.coverageEnd, "coverage_end")) throw new CallBuildError("coverage_start must be before coverage_end");
    return spec("issue_warranty",
      ["program_id", "constitution_id", "holder", "product_model_id", "product_commitment_hex", "coverage_start", "coverage_end", "max_deterministic_remedy"],
      [id(i.programId, "program_id"), id(i.constitutionId, "constitution_id"), i.holder, nonEmpty(i.productModelId, "product_model_id"),
        i.productCommitmentHex.toLowerCase(), i.coverageStart, i.coverageEnd, i.maxDeterministicRemedy],
      "Issue warranty passport");
  },
  cancelWarranty: (warrantyId: number) => spec("cancel_warranty", ["warranty_id"], [id(warrantyId, "warranty_id")], "Cancel warranty", { irreversible: true }),
  releaseExpiredReservation: (warrantyId: number) => spec("release_expired_reservation", ["warranty_id"], [id(warrantyId, "warranty_id")], "Release expired reservation", { irreversible: true }),
  fileClaim: (warrantyId: number, targetedClauseIds: string[], failureAssertedAt: number) => {
    if (targetedClauseIds.length < 1) throw new CallBuildError("choose at least one covered clause");
    return spec("file_claim", ["warranty_id", "targeted_clause_ids", "failure_asserted_at"],
      [id(warrantyId, "warranty_id"), [...targetedClauseIds], uint(failureAssertedAt, "failure_asserted_at")], "File claim");
  },
  respondToClaim: (claimId: number, decision: "ACCEPT" | "DISPUTE") =>
    spec("respond_to_claim", ["claim_id", "decision"], [id(claimId, "claim_id"), decision], decision === "ACCEPT" ? "Accept claim (no contest)" : "Dispute claim", { irreversible: true }),
  submitEvidence: (claimId: number, originalUrl: string, category: string) =>
    spec("submit_evidence", ["claim_id", "original_url", "category"], [id(claimId, "claim_id"), nonEmpty(originalUrl, "original_url"), nonEmpty(category, "category")], "Submit evidence"),
  freezeEvidence: (claimId: number) => spec("freeze_evidence", ["claim_id"], [id(claimId, "claim_id")], "Freeze evidence", { irreversible: true }),
  adjudicateClaim: (claimId: number) => spec("adjudicate_claim", ["claim_id"], [id(claimId, "claim_id")], "Request GenLayer adjudication", { irreversible: true, finalityPrerequisites: ["freeze_evidence"] }),
  fileChallenge: (claimId: number, ground: ChallengeGround, explanation: string, citation: Citation) =>
    spec("file_challenge", ["claim_id", "ground", "explanation", "citation"],
      [id(claimId, "claim_id"), ground, nonEmpty(explanation, "explanation"), {
        evidence_ids: [...citation.evidence_ids], clause_ids: [...citation.clause_ids], constitution_id: citation.constitution_id, timestamp_field: citation.timestamp_field }],
      "File Application Challenge", { irreversible: true }),
  resolveChallenge: (claimId: number) => spec("resolve_challenge", ["claim_id"], [id(claimId, "claim_id")], "Resolve Application Challenge", { irreversible: true }),
  executeRemand: (claimId: number) => spec("execute_remand", ["claim_id"], [id(claimId, "claim_id")], "Run remand review", { irreversible: true }),
  lapseChallenge: (claimId: number) => spec("lapse_challenge", ["claim_id"], [id(claimId, "claim_id")], "Lapse unresolved challenge", { irreversible: true }),
  finalizeClaim: (claimId: number) => spec("finalize_claim", ["claim_id"], [id(claimId, "claim_id")], "Finalize application decision",
    { irreversible: true, finalityPrerequisites: ["respond_to_claim", "adjudicate_claim", "resolve_challenge", "execute_remand", "lapse_challenge"] }),
  settleClaim: (claimId: number) => spec("settle_claim", ["claim_id"], [id(claimId, "claim_id")], "Authorize settlement",
    { irreversible: true, finalityPrerequisites: ["finalize_claim"] }),
  withdrawSettlement: (claimId: number) => spec("withdraw_settlement", ["claim_id"], [id(claimId, "claim_id")], "Withdraw claimable GEN",
    { irreversible: true, finalityPrerequisites: ["settle_claim"] }),
} as const;

export type CallName = keyof typeof calls;
