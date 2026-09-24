import type { ClauseReader } from "../contract/reader";
import type {
  Adjudication, Challenge, Claim, Clause, Constitution, Evidence, FinalDecision, Passport, Pool, Program, Reservation, ResolutionReceipt,
} from "../contract/types";

/** Bounded fan-out so a large deployment cannot fire unbounded parallel RPCs. */
export async function mapLimit<T, R>(items: readonly T[], limit: number, fn: (x: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    for (;;) {
      const i = next++;
      if (i >= items.length) return;
      out[i] = await fn(items[i]);
    }
  });
  await Promise.all(workers);
  return out;
}

export interface PassportListing { passport: Passport; program: Program | null; claimCount: number }

/** Every issued warranty across all programs (public explorer; no wallet required). */
export async function listAllPassports(reader: ClauseReader): Promise<PassportListing[]> {
  const programIds = await reader.listProgramIds();
  const programs = await mapLimit(programIds, 4, async (id) => ({ id, program: await reader.getProgram(id), passportIds: await reader.listPassportIds(id) }));
  const flat = programs.flatMap((p) => p.passportIds.map((pid) => ({ pid, program: p.program })));
  const rows = await mapLimit(flat, 6, async ({ pid, program }) => {
    const [passport, claims] = await Promise.all([reader.getPassport(pid), reader.listClaimIdsForWarranty(pid)]);
    return passport ? { passport, program, claimCount: claims.length } : null;
  });
  return rows.filter((r): r is PassportListing => r !== null).sort((a, b) => b.passport.warrantyId - a.passport.warrantyId);
}

export interface PassportBundle {
  passport: Passport; program: Program | null; pool: Pool | null; constitution: Constitution | null; clauses: Clause[];
  reservation: Reservation | null; claims: Claim[];
}

export async function loadPassportBundle(reader: ClauseReader, warrantyId: number): Promise<PassportBundle | null> {
  const passport = await reader.getPassport(warrantyId);
  if (!passport) return null;
  const [program, pool, constitution, clauses, reservation, claimIds] = await Promise.all([
    reader.getProgram(passport.programId), reader.getPool(passport.programId), reader.getConstitution(passport.constitutionId),
    reader.getClauses(passport.constitutionId), reader.getReservation(passport.reservationId), reader.listClaimIdsForWarranty(warrantyId),
  ]);
  const claims = (await mapLimit(claimIds, 6, (id) => reader.getClaim(id))).filter((c): c is Claim => c !== null);
  return { passport, program, pool, constitution, clauses, reservation, claims };
}

export interface ClaimBundle {
  claim: Claim; passport: Passport | null; constitution: Constitution | null; clauses: Clause[]; evidence: Evidence[];
  adjudication: Adjudication | null; challenge: Challenge | null; corrected: Adjudication | null; finalDecision: FinalDecision | null;
  program: Program | null;
}

export async function loadClaimBundle(reader: ClauseReader, claimId: number): Promise<ClaimBundle | null> {
  const claim = await reader.getClaim(claimId);
  if (!claim) return null;
  const [passport, constitution, clauses, evidence, adjudication, challenge, finalDecision, program] = await Promise.all([
    reader.getPassport(claim.warrantyId), reader.getConstitution(claim.constitutionId), reader.getClauses(claim.constitutionId),
    reader.getEvidenceForClaim(claimId), claim.adjudicationId ? reader.getAdjudication(claim.adjudicationId) : Promise.resolve(null),
    reader.getChallengeForClaim(claimId), reader.getFinalDecision(claimId), reader.getProgram(claim.programId),
  ]);
  const corrected = challenge && challenge.correctedAdjudicationId ? await reader.getAdjudication(challenge.correctedAdjudicationId) : null;
  return { claim, passport, constitution, clauses, evidence, adjudication, challenge, corrected, finalDecision, program };
}

export async function loadReceipt(reader: ClauseReader, claimId: number): Promise<ResolutionReceipt | null> { return reader.getResolutionReceipt(claimId); }

/** Constitution ids are a global contiguous counter starting at 1; scan until the first unknown id. */
export async function listConstitutionsForProgram(reader: ClauseReader, programId: number, cap = 200): Promise<Constitution[]> {
  const out: Constitution[] = [];
  for (let id = 1; id <= cap; id++) {
    const c = await reader.getConstitution(id);
    if (!c) break;
    if (c.programId === programId) out.push(c);
  }
  return out;
}

export interface ProgramSummary { program: Program; pool: Pool | null }
export async function listPrograms(reader: ClauseReader): Promise<ProgramSummary[]> {
  const ids = await reader.listProgramIds();
  const rows = await mapLimit(ids, 4, async (id) => {
    const [program, pool] = await Promise.all([reader.getProgram(id), reader.getPool(id)]);
    return program ? { program, pool } : null;
  });
  return rows.filter((r): r is ProgramSummary => r !== null);
}

export interface InboxItem { claim: Claim; passport: Passport }
/** Every claim on every warranty of a program (manufacturer inbox). */
export async function listProgramClaims(reader: ClauseReader, programId: number): Promise<InboxItem[]> {
  const pids = await reader.listPassportIds(programId);
  const perPassport = await mapLimit(pids, 4, async (pid) => {
    const [passport, ids] = await Promise.all([reader.getPassport(pid), reader.listClaimIdsForWarranty(pid)]);
    if (!passport) return [] as InboxItem[];
    const claims = (await mapLimit(ids, 6, (id) => reader.getClaim(id))).filter((c): c is Claim => c !== null);
    return claims.map((claim) => ({ claim, passport }));
  });
  return perPassport.flat().sort((a, b) => b.claim.claimId - a.claim.claimId);
}
