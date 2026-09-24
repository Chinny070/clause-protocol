import type { Address } from "../config/contract";
import {
  DecodeError, decodeAdjudication, decodeChallenge, decodeClaim, decodeClauses, decodeConstitution, decodeEvidence, decodeFinalDecision,
  decodeIdList, decodePassport, decodePool, decodeProgram, decodeReceipt, decodeReservation, decodeU64,
} from "./decode";
import type { ClauseTransport } from "./transport";
import type {
  Adjudication, Challenge, Claim, Clause, Constitution, Evidence, FinalDecision, Passport, Pool, Program, Reservation, ResolutionReceipt,
} from "./types";

export type ReadFailureKind = "rpc-unavailable" | "contract-read-failed" | "malformed";

export class ContractReadError extends Error {
  constructor(public readonly kind: ReadFailureKind, public readonly functionName: string, public readonly cause: unknown) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    super(`${functionName}: ${detail}`);
    this.name = "ContractReadError";
  }
}

const RPC_DOWN = /failed to fetch|fetch failed|networkerror|ECONNREFUSED|ETIMEDOUT|timeout|network request failed|HTTP request failed|ENOTFOUND|502|503|504/i;

/** Typed, decoded, authoritative reads against the FROZEN CLAUSE ABI. Every method maps 1:1 to a contract view. */
export class ClauseReader {
  constructor(private readonly transport: ClauseTransport, private readonly address: Address) {}

  private async call<T>(functionName: string, args: (number | bigint | string)[], decode: (v: unknown) => T): Promise<T> {
    let raw: unknown;
    try {
      raw = await this.transport.readContract({ address: this.address, functionName, args });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      throw new ContractReadError(RPC_DOWN.test(msg) ? "rpc-unavailable" : "contract-read-failed", functionName, e);
    }
    try {
      return decode(raw);
    } catch (e) {
      if (e instanceof DecodeError) throw new ContractReadError("malformed", functionName, e);
      throw e;
    }
  }

  now(): Promise<number> { return this.call("now", [], (v) => decodeU64(v, "now")); }
  listProgramIds(): Promise<number[]> { return this.call("list_program_ids", [], (v) => decodeIdList(v, "program ids")); }
  getProgram(id: number): Promise<Program | null> { return this.call("get_program", [id], decodeProgram); }
  getPool(programId: number): Promise<Pool | null> { return this.call("get_pool", [programId], decodePool); }
  getConstitution(id: number): Promise<Constitution | null> { return this.call("get_constitution", [id], decodeConstitution); }
  getClauses(constitutionId: number): Promise<Clause[]> { return this.call("get_clauses", [constitutionId], decodeClauses); }
  listPassportIds(programId: number): Promise<number[]> { return this.call("list_passport_ids", [programId], (v) => decodeIdList(v, "passport ids")); }
  getPassport(id: number): Promise<Passport | null> { return this.call("get_passport", [id], decodePassport); }
  getReservation(id: number): Promise<Reservation | null> { return this.call("get_reservation", [id], decodeReservation); }
  listClaimIdsForWarranty(warrantyId: number): Promise<number[]> { return this.call("list_claim_ids_for_warranty", [warrantyId], (v) => decodeIdList(v, "claim ids")); }
  getClaim(id: number): Promise<Claim | null> { return this.call("get_claim", [id], decodeClaim); }
  listEvidenceIdsForClaim(claimId: number): Promise<number[]> { return this.call("list_evidence_ids_for_claim", [claimId], (v) => decodeIdList(v, "evidence ids")); }
  getEvidence(id: number): Promise<Evidence | null> { return this.call("get_evidence", [id], decodeEvidence); }
  getAdjudication(id: number): Promise<Adjudication | null> { return this.call("get_adjudication", [id], decodeAdjudication); }
  getChallenge(id: number): Promise<Challenge | null> { return this.call("get_challenge", [id], decodeChallenge); }
  getChallengeForClaim(claimId: number): Promise<Challenge | null> { return this.call("get_challenge_for_claim", [claimId], decodeChallenge); }
  getFinalDecision(claimId: number): Promise<FinalDecision | null> { return this.call("get_final_decision", [claimId], decodeFinalDecision); }
  getResolutionReceipt(claimId: number): Promise<ResolutionReceipt | null> { return this.call("get_resolution_receipt", [claimId], decodeReceipt); }

  async getEvidenceForClaim(claimId: number): Promise<Evidence[]> {
    const ids = await this.listEvidenceIdsForClaim(claimId);
    const rows = await Promise.all(ids.map((id) => this.getEvidence(id)));
    return rows.filter((e): e is Evidence => e !== null);
  }

  /** Public reachability check for the configured contract: two cheap authoritative reads. */
  async healthCheck(): Promise<{ protocolNow: number; programCount: number }> {
    const protocolNow = await this.now();
    const ids = await this.listProgramIds();
    return { protocolNow, programCount: ids.length };
  }
}
