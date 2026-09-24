import { describe, expect, it } from "vitest";
import { DecodeError, decodeChallenge, decodeClaim, decodeFinalDecision, decodePassport, decodePool, decodeReceipt, isEmptyObject, toBigInt, toInt } from "../src/contract/decode";

describe("numeric decoding", () => {
  it("normalizes SDK number / decimal-string / bigint amounts to bigint", () => {
    expect(toBigInt(5, "x")).toBe(5n);
    expect(toBigInt("5000000000000000000", "x")).toBe(5n * 10n ** 18n);
    expect(toBigInt(7n, "x")).toBe(7n);
  });
  it("rejects negatives, floats, garbage", () => {
    for (const v of [-1, 1.5, "abc", "-3", null, undefined, {}]) expect(() => toBigInt(v, "x")).toThrow(DecodeError);
    expect(() => toInt("99999999999999999999", "x")).toThrow(DecodeError);
  });
});

describe("unknown ids", () => {
  it("decodes {} to null for every read model", () => {
    for (const f of [decodePool, decodePassport, decodeClaim, decodeChallenge, decodeFinalDecision, decodeReceipt]) expect(f({})).toBeNull();
    expect(isEmptyObject({})).toBe(true);
    expect(isEmptyObject({ a: 1 })).toBe(false);
  });
});

describe("pool / passport decoding with SDK string amounts", () => {
  it("keeps exact 18-decimal amounts", () => {
    const pool = decodePool({ pool_id: 1, program_id: 1, manufacturer: "0xabc", total_balance: "5000000000000000000", reserved_liability: "5000000000000000000", available_balance: 0 });
    expect(pool).toMatchObject({ totalBalance: 5n * 10n ** 18n, reservedLiability: 5n * 10n ** 18n, availableBalance: 0n });
  });
  it("throws a DecodeError on a malformed shape (fail closed, never guess)", () => {
    expect(() => decodePool({ pool_id: 1, program_id: 1, manufacturer: 5, total_balance: 1, reserved_liability: 1, available_balance: 1 })).toThrow(DecodeError);
    expect(() => decodeClaim({ claim_id: 1 })).toThrow(DecodeError);
  });
});

describe("final decision", () => {
  const base = {
    claim_id: 1, source: "ADJUDICATION", adjudication_id: 1, challenge_id: 0, final_outcome: "COVERED", established_clause_ids: ["C-001"],
    remedy_basis: "COVERED", remedy_kind: "FULL_REFUND", remedy_value: 0, remedy_amount: "5000000000000000000", recipient: "0xabc", finalized_at: 10,
    settled_at: 11, settled_amount: "5000000000000000000", capped: false, claimable: "5000000000000000000", withdrawn_at: 0, withdrawn_amount: 0,
  };
  it("decodes amounts and flags", () => {
    const f = decodeFinalDecision(base)!;
    expect(f.claimable).toBe(5n * 10n ** 18n);
    expect(f.capped).toBe(false);
    expect(f.withdrawnAmount).toBe(0n);
  });
});
