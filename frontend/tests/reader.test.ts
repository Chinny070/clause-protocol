import { describe, expect, it } from "vitest";
import { ContractReadError, ClauseReader } from "../src/contract/reader";
import { ADDR, makeTransport } from "./helpers/mock";

describe("ClauseReader", () => {
  it("calls the frozen view names with typed arguments and decodes results", async () => {
    const t = makeTransport({ reads: {
      get_pool: (a) => (a[0] === 1 ? { pool_id: 1, program_id: 1, manufacturer: "0xabc", total_balance: "5000000000000000000", reserved_liability: 0, available_balance: "5000000000000000000" } : {}),
      list_program_ids: () => [1],
      now: () => 1_790_000_000,
    } });
    const r = new ClauseReader(t, ADDR);
    expect((await r.getPool(1))?.availableBalance).toBe(5n * 10n ** 18n);
    expect(await r.getPool(9)).toBeNull();
    expect(await r.healthCheck()).toEqual({ protocolNow: 1_790_000_000, programCount: 1 });
    expect(t.calls.reads).toEqual(["get_pool", "get_pool", "now", "list_program_ids"]);
  });

  it("classifies RPC outage vs contract failure vs malformed data", async () => {
    const down = new ClauseReader(makeTransport({ reads: { now: () => { throw new Error("TypeError: Failed to fetch"); } } }), ADDR);
    await expect(down.now()).rejects.toMatchObject({ name: "ContractReadError", kind: "rpc-unavailable" });
    const bad = new ClauseReader(makeTransport({ reads: { now: () => { throw new Error("contract not found at address"); } } }), ADDR);
    await expect(bad.now()).rejects.toMatchObject({ kind: "contract-read-failed" });
    const mal = new ClauseReader(makeTransport({ reads: { now: () => "not-a-number" } }), ADDR);
    await expect(mal.now()).rejects.toMatchObject({ kind: "malformed" });
    await expect(mal.now()).rejects.toBeInstanceOf(ContractReadError);
  });

  it("loads all evidence records for a claim, skipping unknown ids", async () => {
    const ev = (id: number) => ({ evidence_id: id, claim_id: 1, submitter: "0xabc", original_url: "https://x.example/" + id, category: "RECEIPT", host: "x.example",
      retrieval_method: "GET", submitted_at: 1, eligibility: "ELIGIBLE", retrieval_status: "AVAILABLE", retrieved_at: 2, frozen_at: 2, extracted_content: "c", fingerprint: "ff", available: true });
    const r = new ClauseReader(makeTransport({ reads: { list_evidence_ids_for_claim: () => [1, 2, 3], get_evidence: (a) => (a[0] === 2 ? {} : ev(a[0] as number)) } }), ADDR);
    expect((await r.getEvidenceForClaim(1)).map((e) => e.evidenceId)).toEqual([1, 3]);
  });
});
