import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { CallBuildError, calls } from "../src/contract/calls";

/** The frozen interface document is the ABI source of truth: every write builder must match it exactly. */
const doc = readFileSync(resolve(__dirname, "../../docs/FRONTEND_CONTRACT_INTERFACE.md"), "utf8");
const section = doc.slice(doc.indexOf("### Write methods"), doc.indexOf("### View methods"));
const writeAbi = new Map<string, string[]>();
for (const m of section.matchAll(/#### `(\w+)\(([^)]*)\)/g)) {
  const params = m[2].trim() === "" ? [] : m[2].split(",").map((p) => p.split(":")[0].trim());
  writeAbi.set(m[1], params);
}
const viewSection = doc.slice(doc.indexOf("### View methods"), doc.indexOf("### Enumerations"));
const viewNames = [...viewSection.matchAll(/#### `(\w+)\(/g)].map((m) => m[1]);

const cit = { evidence_ids: [1], clause_ids: [], constitution_id: 0, timestamp_field: "" };
const specs = [
  calls.createProgram("Acme"), calls.pauseProgram(1), calls.resumeProgram(1), calls.retireProgram(1), calls.fundPool(1, 10n), calls.withdrawPool(1, 10n),
  calls.createConstitution({ programId: 1, version: "v", productScope: "s", coverageCalc: "c", coveredClauses: [{ clause_id: "C-001", text: "t" }], excludedClauses: [],
    acceptableEvidenceCategories: ["RECEIPT"], sourceEligibilityPolicy: "x.example", claimDeadlineS: 1, manufacturerResponsePeriodS: 1, challengeWindowS: 1, challengeDepth: 1,
    insufficientEvidenceBehavior: "RULE_FOR_MANUFACTURER", unavailableEvidenceBehavior: "RULE_FOR_MANUFACTURER", expiryCancellationRules: "r", remedyTable: [] }),
  calls.issueWarranty({ programId: 1, constitutionId: 1, holder: "0x" + "1".repeat(40), productModelId: "M", productCommitmentHex: "a".repeat(64), coverageStart: 1, coverageEnd: 2, maxDeterministicRemedy: 1n }),
  calls.cancelWarranty(1), calls.releaseExpiredReservation(1), calls.fileClaim(1, ["C-001"], 5), calls.respondToClaim(1, "ACCEPT"),
  calls.submitEvidence(1, "https://x.example/", "RECEIPT"), calls.freezeEvidence(1), calls.adjudicateClaim(1), calls.fileChallenge(1, "IGNORED_EVIDENCE", "why", cit),
  calls.resolveChallenge(1), calls.executeRemand(1), calls.lapseChallenge(1), calls.finalizeClaim(1), calls.settleClaim(1), calls.withdrawSettlement(1),
];

describe("frozen ABI parity (docs/FRONTEND_CONTRACT_INTERFACE.md)", () => {
  it("the document lists 22 write and 18 view methods", () => {
    expect(writeAbi.size).toBe(22);
    expect(viewNames.length).toBe(18);
  });
  it("every write builder uses the exact contract method name and parameter names, in order", () => {
    for (const s of specs) {
      expect(writeAbi.has(s.functionName), s.functionName).toBe(true);
      expect(s.params, s.functionName).toEqual(writeAbi.get(s.functionName));
      expect(s.args.length, s.functionName).toBe(s.params.length);
    }
  });
  it("every documented write method has a builder (no method left uncovered)", () => {
    expect(new Set(specs.map((s) => s.functionName))).toEqual(new Set(writeAbi.keys()));
  });
  it("only fund_pool is payable", () => {
    expect(specs.filter((s) => s.value > 0n).map((s) => s.functionName)).toEqual(["fund_pool"]);
    expect(doc).toContain("1 payable: `fund_pool`");
  });
});

describe("call argument validation", () => {
  it("rejects unsafe or ambiguous arguments before anything is sent", () => {
    expect(() => calls.fundPool(1, 0n)).toThrow(CallBuildError);
    expect(() => calls.fileClaim(1, [], 5)).toThrow(CallBuildError);
    expect(() => calls.pauseProgram(0)).toThrow(CallBuildError);
    expect(() => calls.pauseProgram(-1)).toThrow(CallBuildError);
    expect(() => calls.pauseProgram(1.5)).toThrow(CallBuildError);
    expect(() => calls.createProgram("  ")).toThrow(CallBuildError);
    expect(() => calls.issueWarranty({ programId: 1, constitutionId: 1, holder: "0x1", productModelId: "M", productCommitmentHex: "zz", coverageStart: 1, coverageEnd: 2, maxDeterministicRemedy: 1n })).toThrow(CallBuildError);
    expect(() => calls.issueWarranty({ programId: 1, constitutionId: 1, holder: "0x1", productModelId: "M", productCommitmentHex: "a".repeat(64), coverageStart: 5, coverageEnd: 2, maxDeterministicRemedy: 1n })).toThrow(CallBuildError);
  });
  it("sends the challenge citation with exactly the four contract keys and no extras", () => {
    const s = calls.fileChallenge(3, "WRONG_CLAUSE", "x", { evidence_ids: [], clause_ids: ["C-001"], constitution_id: 0, timestamp_field: "", ...({ url: "https://evil.example" } as object) } as never);
    expect(Object.keys(s.args[3] as object).sort()).toEqual(["clause_ids", "constitution_id", "evidence_ids", "timestamp_field"]);
  });
  it("marks value-moving and irreversible steps and their finality prerequisites", () => {
    expect(calls.withdrawSettlement(1).irreversible).toBe(true);
    expect(calls.withdrawSettlement(1).finalityPrerequisites).toEqual(["settle_claim"]);
    expect(calls.settleClaim(1).finalityPrerequisites).toEqual(["finalize_claim"]);
    expect(calls.fileClaim(1, ["C-001"], 5).irreversible).toBe(false);
  });
});
