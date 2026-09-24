import { describe, expect, it } from "vitest";
import { calls } from "../src/contract/calls";
import { runTransaction, type TxPhase } from "../src/tx/runner";
import { classifyTx, executionResult, isSafeToContinue, statusName } from "../src/tx/status";
import { verifyFinality } from "../src/tx/finality";
import { TxJournal, isTxHash } from "../src/tx/journal";
import { ADDR, HASH, makeTransport, tx } from "./helpers/mock";

const fast = { pollMs: 0, sleep: async () => undefined };

describe("status classification", () => {
  it("decodes named and numeric statuses (SDK 1.1.8: 7 = FINALIZED)", () => {
    expect(statusName({ status: 7 })).toBe("FINALIZED");
    expect(statusName({ status: "7" })).toBe("FINALIZED");
    expect(statusName({ status_name: "accepted" })).toBe("ACCEPTED");
    expect(statusName({ status: 99 })).toBeUndefined();
  });
  it("FINALIZED alone is not enough: the leader execution result decides", () => {
    expect(classifyTx(tx("FINALIZED", "SUCCESS"))).toBe("finalized-success");
    expect(classifyTx(tx("FINALIZED", "ERROR"))).toBe("finalized-error");
    expect(classifyTx(tx("FINALIZED", null))).toBe("finalized-unknown");
    expect(executionResult(tx("FINALIZED", null))).toBe("UNKNOWN");
  });
  it("only finalized-success is safe to continue; everything uncertain fails closed", () => {
    for (const s of ["ACCEPTED", "READY_TO_FINALIZE", "PENDING", "PROPOSING", "COMMITTING", "UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "CANCELED", "APPEAL_COMMITTING", "WHATEVER"]) {
      expect(isSafeToContinue(classifyTx(tx(s)))).toBe(false);
    }
    expect(isSafeToContinue(classifyTx({}))).toBe(false);
    expect(isSafeToContinue(classifyTx(tx("FINALIZED", "SUCCESS")))).toBe(true);
  });
});

describe("runTransaction lifecycle", () => {
  it("walks prepare, wallet, submitted, consensus, accepted, finalized, reread - and only rereads after finality", async () => {
    const phases: string[] = [];
    let rereadAtPhase = "";
    const t = makeTransport({ txSequence: [tx("PENDING"), tx("COMMITTING"), tx("ACCEPTED"), tx("ACCEPTED"), tx("FINALIZED")] });
    const out = await runTransaction(t, ADDR, calls.freezeEvidence(1), {
      ...fast, onPhase: (p: TxPhase) => phases.push(p.phase),
      reread: async () => { rereadAtPhase = phases[phases.length - 1]; return { claim: "EVIDENCE_FROZEN" }; },
    });
    expect(out).toMatchObject({ ok: true, hash: HASH, data: { claim: "EVIDENCE_FROZEN" }, rereadFailed: false });
    expect(phases).toEqual(["preparing", "awaiting-wallet", "submitted", "consensus", "consensus", "accepted", "finalized", "confirmed"]);
    expect(rereadAtPhase).toBe("finalized");
  });

  it("wallet rejection stops before submission and changes nothing", async () => {
    const t = makeTransport({ write: () => { throw Object.assign(new Error("User rejected the request."), { code: 4001 }); } });
    const phases: string[] = [];
    const out = await runTransaction(t, ADDR, calls.settleClaim(1), { ...fast, onPhase: (p) => phases.push(p.phase) });
    expect(out).toMatchObject({ ok: false, reason: "wallet-rejected", error: { kind: "wallet-rejected" } });
    expect(phases).toContain("wallet-rejected");
    expect(t.calls.getTx).toBe(0);
  });

  it("a FINALIZED transaction whose execution errored is a failure, never success, and no reread happens", async () => {
    let reread = false;
    const t = makeTransport({ txSequence: [tx("FINALIZED", "ERROR")] });
    const out = await runTransaction(t, ADDR, calls.finalizeClaim(1), { ...fast, reread: async () => { reread = true; return 1; } });
    expect(out).toMatchObject({ ok: false, reason: "execution-error", hash: HASH });
    expect(reread).toBe(false);
  });

  it("an unverifiable execution result is treated as failure (fail closed)", async () => {
    const out = await runTransaction(makeTransport({ txSequence: [tx("FINALIZED", null)] }), ADDR, calls.finalizeClaim(1), fast);
    expect(out).toMatchObject({ ok: false, reason: "execution-error" });
    expect(out.ok === false && out.error.title).toBe("Result could not be verified");
  });

  it("undetermined consensus is reported as undetermined, not failure and not success", async () => {
    const out = await runTransaction(makeTransport({ txSequence: [tx("PENDING"), tx("UNDETERMINED")] }), ADDR, calls.adjudicateClaim(1), fast);
    expect(out).toMatchObject({ ok: false, reason: "undetermined", error: { kind: "undetermined" } });
  });

  it("canceled and timed-out transactions are failures", async () => {
    expect(await runTransaction(makeTransport({ txSequence: [tx("CANCELED")] }), ADDR, calls.freezeEvidence(1), fast)).toMatchObject({ ok: false, reason: "canceled" });
    expect(await runTransaction(makeTransport({ txSequence: [tx("LEADER_TIMEOUT")] }), ADDR, calls.freezeEvidence(1), fast)).toMatchObject({ ok: false, reason: "timeout" });
  });

  it("never reports success from a hash alone: a transaction stuck at ACCEPTED ends as pending-unknown", async () => {
    const out = await runTransaction(makeTransport({ txSequence: [tx("ACCEPTED")] }), ADDR, calls.freezeEvidence(1), { ...fast, maxPolls: 4 });
    expect(out).toMatchObject({ ok: false, reason: "pending-unknown", hash: HASH });
  });

  it("transient status-read errors do not abort or fake success", async () => {
    const out = await runTransaction(makeTransport({ txSequence: [new Error("Failed to fetch"), new Error("Failed to fetch"), tx("FINALIZED")] }), ADDR, calls.freezeEvidence(1), fast);
    expect(out.ok).toBe(true);
  });

  it("a failed authoritative reread is surfaced, and no data is invented", async () => {
    const out = await runTransaction(makeTransport({ txSequence: [tx("FINALIZED")] }), ADDR, calls.freezeEvidence(1), { ...fast, reread: async () => { throw new Error("rpc down"); } });
    expect(out).toMatchObject({ ok: true, rereadFailed: true, data: undefined });
  });

  it("passes the exact frozen method, args and payable value to the transport", async () => {
    const seen: Array<[string, unknown[], bigint | undefined]> = [];
    const t = makeTransport({ write: (fn, args, value) => { seen.push([fn, args, value]); return HASH; }, txSequence: [tx("FINALIZED")] });
    await runTransaction(t, ADDR, calls.fundPool(2, 3n * 10n ** 18n), fast);
    expect(seen).toEqual([["fund_pool", [2], 3n * 10n ** 18n]]);
  });
});

describe("GenLayer Protocol Finality verification", () => {
  it("is safe only for Finalized + successful; read errors fail closed", async () => {
    expect((await verifyFinality(makeTransport({ txSequence: [tx("FINALIZED")] }), HASH)).safe).toBe(true);
    expect((await verifyFinality(makeTransport({ txSequence: [tx("ACCEPTED")] }), HASH)).safe).toBe(false);
    const err = await verifyFinality(makeTransport({ txSequence: [new Error("boom")] }), HASH);
    expect(err).toMatchObject({ safe: false, txClass: "unknown" });
  });
});

describe("TxJournal", () => {
  const mem = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }; };
  it("records and finds the most recent hash by claim and function", () => {
    const j = new TxJournal(mem(), "t");
    const h2 = ("0x" + "cd".repeat(32)) as `0x${string}`;
    j.record(1, "adjudicate_claim", HASH, 1);
    j.record(1, "adjudicate_claim", h2, 2);
    j.record(2, "adjudicate_claim", HASH, 3);
    expect(j.find(1, ["adjudicate_claim"])?.hash).toBe(h2);
    expect(j.find(1, ["settle_claim"])).toBeUndefined();
  });
  it("persists across instances and works with no storage or corrupt storage", () => {
    const s = mem();
    new TxJournal(s, "t").record(1, "x", HASH, 1);
    expect(new TxJournal(s, "t").find(1, ["x"])?.hash).toBe(HASH);
    expect(new TxJournal(null).all()).toEqual([]);
    s.setItem("clause.txjournal.v1:bad", "{not json");
    expect(new TxJournal(s, "bad").all()).toEqual([]);
  });
  it("validates hashes", () => {
    expect(isTxHash(HASH)).toBe(true);
    expect(isTxHash("0x12")).toBe(false);
  });
});
