/**
 * Frontend adapter <-> REAL CLAUSE contract on a LOCAL GenLayer simulator (glsim). No mocks: this drives the exact
 * production code paths (calls.ts builders, runTransaction with the real genlayer-js 1.1.8 client, ClauseReader decoders,
 * finality verification) against the frozen contract ABI.
 *
 * Run against a FRESH simulator (glsim loads one contract per process):
 *   bash scripts/run_frontend_integration.sh
 * Throwaway ephemeral keys generated inside this test are the only signers; no user wallet or key is involved.
 * Not a StudioNet deployment.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { createClient, createAccount } from "genlayer-js";
import { describe, expect, it } from "vitest";
import { LOCALNET } from "../../src/config/networks";
import { calls } from "../../src/contract/calls";
import { ClauseReader } from "../../src/contract/reader";
import type { ClauseTransport } from "../../src/contract/transport";
import { createEphemeralTestTransport } from "../helpers/ephemeral";
import { loadClaimBundle } from "../../src/app/data";
import { verifyFinality } from "../../src/tx/finality";
import { runTransaction, type TxOutcome, type TxPhase } from "../../src/tx/runner";
import type { Address } from "../../src/config/contract";

const CONTRACT = resolve(__dirname, "../../../contracts/clause_protocol.py");
const ONE_GEN = 10n ** 18n;
const DAY = 86400;

interface Actor { transport: ClauseTransport; address: Address }

async function deploy(): Promise<Address> {
  const deployer = createAccount();
  const client = createClient({ chain: LOCALNET.chain, account: deployer });
  const hash = await client.deployContract({ code: readFileSync(CONTRACT, "utf8"), args: [] });
  const receipt = await client.waitForTransactionReceipt({ hash: hash as never, status: "FINALIZED" as never, retries: 90, interval: 1000 });
  const addr = (receipt as { data?: { contract_address?: string } }).data?.contract_address;
  if (!addr) throw new Error("deploy did not return a contract address");
  return addr as Address;
}

describe("adapter against the real contract on a local simulator", () => {
  it("full lifecycle through the production adapter", async () => {
    const address = await deploy();
    writeFileSync(resolve(__dirname, "../../../.scratch/local_address.txt"), address);
    const mfr: Actor = createEphemeralTestTransport(LOCALNET);
    const holder: Actor = createEphemeralTestTransport(LOCALNET);
    const other: Actor = createEphemeralTestTransport(LOCALNET);
    const reader = new ClauseReader(mfr.transport, address);
    const fast = { pollMs: 500 };

    const run = async <T,>(a: Actor, spec: ReturnType<(typeof calls)[keyof typeof calls]>, reread?: () => Promise<T>) => {
      const phases: string[] = [];
      const out = await runTransaction<T>(a.transport, address, spec, { ...fast, reread, onPhase: (p: TxPhase) => phases.push(p.phase) });
      return { out, phases };
    };

    // health: a real contract answers the two health reads
    const health = await reader.healthCheck();
    expect(health.programCount).toBe(0);

    // program + funding (payable) + frozen terms with a remedy table that includes a REPAIR_CREDIT above 2^53 atoms
    let r: { out: TxOutcome<unknown>; phases: string[] } = await run(mfr, calls.createProgram("Acme Stage5"), () => reader.listProgramIds());
    expect(r.out).toMatchObject({ ok: true, data: [1] });
    expect(r.phases).toContain("finalized");
    expect(r.phases[r.phases.length - 1]).toBe("confirmed");

    r = await run(mfr, calls.fundPool(1, 3n * ONE_GEN), () => reader.getPool(1));
    expect(r.out.ok).toBe(true);
    expect((await reader.getPool(1))?.totalBalance).toBe(3n * ONE_GEN);

    r = await run(mfr, calls.createConstitution({
      programId: 1, version: "2026.1", productScope: "Widget Model X", coverageCalc: "flat term",
      coveredClauses: [{ clause_id: "C-001", text: "Manufacturing defects are covered." }],
      excludedClauses: [{ clause_id: "X-001", text: "Accidental impact is excluded." }],
      acceptableEvidenceCategories: ["RECEIPT"], sourceEligibilityPolicy: "example.org", claimDeadlineS: 30 * DAY,
      manufacturerResponsePeriodS: 14 * DAY, challengeWindowS: 60, challengeDepth: 1,
      insufficientEvidenceBehavior: "RULE_FOR_MANUFACTURER", unavailableEvidenceBehavior: "RULE_FOR_MANUFACTURER", expiryCancellationRules: "Cancel while no claim is unsettled.",
      remedyTable: [
        { outcome: "COVERED", clause_id: "C-001", remedy_kind: "REPAIR_CREDIT", remedy_value: ONE_GEN },
        { outcome: "NOT_COVERED", clause_id: "", remedy_kind: "NONE", remedy_value: 0n },
        { outcome: "ACCEPTED_NO_CONTEST", clause_id: "", remedy_kind: "FULL_REFUND", remedy_value: 0n },
      ],
    }), () => reader.getConstitution(1));
    expect(r.out.ok).toBe(true);
    const cons = await reader.getConstitution(1);
    expect(cons?.remedyTable.find((x) => x.outcome === "COVERED")?.remedy_value).toBe(ONE_GEN); // bigint above 2^53 round-trips exactly
    expect(cons?.isFrozen).toBe(false);
    expect(cons?.challengeDepth).toBe(1);

    // the contract refuses an incomplete remedy table: a FINALIZED-but-errored transaction is a failure in the adapter
    r = await run(mfr, calls.createConstitution({
      programId: 1, version: "bad", productScope: "s", coverageCalc: "c", coveredClauses: [{ clause_id: "C-001", text: "t" }], excludedClauses: [],
      acceptableEvidenceCategories: ["RECEIPT"], sourceEligibilityPolicy: "example.org", claimDeadlineS: DAY, manufacturerResponsePeriodS: DAY, challengeWindowS: 60, challengeDepth: 1,
      insufficientEvidenceBehavior: "RULE_FOR_MANUFACTURER", unavailableEvidenceBehavior: "RULE_FOR_MANUFACTURER", expiryCancellationRules: "x",
      remedyTable: [{ outcome: "COVERED", clause_id: "C-001", remedy_kind: "FULL_REFUND", remedy_value: 0n }],
    }));
    expect(r.out).toMatchObject({ ok: false, reason: "execution-error", hash: expect.stringMatching(/^0x[0-9a-f]{64}$/) });
    expect(r.phases).toContain("failed");
    expect(await reader.getConstitution(2)).toBeNull();

    // issue two warranties
    const now = await reader.now();
    for (const seed of [1, 2]) {
      r = await run(mfr, calls.issueWarranty({ programId: 1, constitutionId: 1, holder: holder.address, productModelId: "WIDGET-X-001",
        productCommitmentHex: seed.toString(16).padStart(64, "0"), coverageStart: now, coverageEnd: now + 365 * DAY, maxDeterministicRemedy: ONE_GEN }));
      expect(r.out.ok).toBe(true);
    }
    const passport = await reader.getPassport(1);
    expect(passport).toMatchObject({ status: "ACTIVE", maxDeterministicRemedy: ONE_GEN });
    expect(passport?.holder.toLowerCase()).toBe(holder.address.toLowerCase());
    expect((await reader.getPool(1))?.reservedLiability).toBe(2n * ONE_GEN);
    expect((await reader.getConstitution(1))?.isFrozen).toBe(true);
    expect(await reader.listPassportIds(1)).toEqual([1, 2]);

    // ---- A. no-contest lifecycle through finality-verified steps ----
    r = await run(holder, calls.fileClaim(1, ["C-001"], now));
    expect(r.out.ok).toBe(true);
    // unauthorized caller: surfaced as a failed transaction with a human message
    r = await run(other, calls.respondToClaim(1, "ACCEPT"));
    expect(r.out).toMatchObject({ ok: false, reason: "execution-error", error: { kind: "unauthorized" } });
    r = await run(mfr, calls.respondToClaim(1, "ACCEPT"), () => reader.getClaim(1));
    expect(r.out).toMatchObject({ ok: true, data: { status: "ACCEPTED", manufacturerResponse: "ACCEPT" } });
    const respondHash = (r.out as { hash: `0x${string}` }).hash;
    expect((await verifyFinality(mfr.transport, respondHash)).safe).toBe(true);

    r = await run(other, calls.finalizeClaim(1), () => reader.getFinalDecision(1));
    expect(r.out).toMatchObject({ ok: true, data: { source: "NO_CONTEST", remedyAmount: ONE_GEN, settledAt: 0 } });
    r = await run(other, calls.settleClaim(1), () => reader.getFinalDecision(1));
    expect(r.out).toMatchObject({ ok: true, data: { claimable: ONE_GEN, settledAmount: ONE_GEN } });
    r = await run(other, calls.withdrawSettlement(1));
    expect(r.out).toMatchObject({ ok: false, error: { kind: "unauthorized" } }); // only the recorded recipient
    r = await run(holder, calls.withdrawSettlement(1), () => reader.getFinalDecision(1));
    expect(r.out).toMatchObject({ ok: true, data: { claimable: 0n, withdrawnAmount: ONE_GEN } });
    r = await run(holder, calls.withdrawSettlement(1));
    expect(r.out).toMatchObject({ ok: false, error: { kind: "already-withdrawn" } });
    const receipt = await reader.getResolutionReceipt(1);
    expect(receipt).toMatchObject({ claimId: 1, claimStatus: "SETTLED", finalDecision: { finalOutcome: "ACCEPTED_NO_CONTEST", withdrawnAmount: ONE_GEN } });
    expect(receipt?.warranty.constitutionFingerprint).toBe(cons?.fingerprint);

    // ---- B. dispute -> real retrieval -> deterministic adjudication -> deterministic Application Challenge ----
    r = await run(holder, calls.fileClaim(2, ["C-001"], now - 10 * DAY)); // asserted failure predates coverage: window FAIL
    expect(r.out.ok).toBe(true);
    r = await run(mfr, calls.respondToClaim(2, "DISPUTE"), () => reader.getClaim(2));
    expect(r.out).toMatchObject({ ok: true, data: { status: "DISPUTED" } });
    r = await run(holder, calls.submitEvidence(2, "https://example.org/", "RECEIPT"));
    expect(r.out.ok).toBe(true);
    r = await run(other, calls.freezeEvidence(2), () => reader.getEvidenceForClaim(2));
    expect(r.out.ok).toBe(true);
    const ev = (await reader.getEvidenceForClaim(2))[0];
    expect(ev).toMatchObject({ eligibility: "ELIGIBLE", retrievalStatus: "AVAILABLE", available: true });
    expect(ev.frozenAt).toBeGreaterThan(0);
    r = await run(other, calls.adjudicateClaim(2), () => reader.getAdjudication(1));
    expect(r.out).toMatchObject({ ok: true, data: { outcome: "NOT_COVERED", coverageWindow: "FAIL", decisionPath: "DETERMINISTIC_PREDICATE" } });
    r = await run(holder, calls.fileChallenge(2, "TEMPORAL_ERROR", "Please recheck the window.", { evidence_ids: [], clause_ids: [], constitution_id: 0, timestamp_field: "failure_asserted_at" }), () => reader.getChallengeForClaim(2));
    expect(r.out).toMatchObject({ ok: true, data: { ground: "TEMPORAL_ERROR", status: "OPEN" } });
    r = await run(other, calls.settleClaim(2));
    expect(r.out).toMatchObject({ ok: false, error: { kind: "invalid-claim-state" } });
    r = await run(other, calls.resolveChallenge(2), () => reader.getChallengeForClaim(2));
    expect(r.out).toMatchObject({ ok: true, data: { result: "UPHELD", resolutionPath: "DETERMINISTIC" } });
    r = await run(other, calls.finalizeClaim(2), () => reader.getFinalDecision(2));
    expect(r.out).toMatchObject({ ok: true, data: { finalOutcome: "NOT_COVERED", remedyAmount: 0n } });
    r = await run(other, calls.settleClaim(2), () => reader.getFinalDecision(2));
    expect(r.out).toMatchObject({ ok: true, data: { claimable: 0n } });
    r = await run(holder, calls.withdrawSettlement(2));
    expect(r.out).toMatchObject({ ok: false, error: { kind: "nothing-to-withdraw" } });

    // authoritative bundle used by the claim page decodes real data end to end
    const bundle = await loadClaimBundle(reader, 2);
    expect(bundle).toMatchObject({ claim: { status: "SETTLED" }, adjudication: { superseded: false }, challenge: { result: "UPHELD" }, finalDecision: { settledAt: expect.any(Number) } });
    expect(bundle?.evidence).toHaveLength(1);
    expect(bundle?.clauses.map((c) => c.clauseId).sort()).toEqual(["C-001", "X-001"]);

    // unknown ids decode to null, never throw
    expect(await reader.getClaim(999)).toBeNull();
    expect(await reader.getResolutionReceipt(999)).toBeNull();
    expect(await reader.getPassport(0)).toBeNull();
  });
});
