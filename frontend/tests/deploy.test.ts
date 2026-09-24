import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { checkDeployedSource, checkSource, deployAndWatch, type DeployClient } from "../src/deploy/deploy";
import { EXPECTED_CONTRACT_BYTES, EXPECTED_CONTRACT_SHA256 } from "../src/deploy/expected";

const file = readFileSync(resolve(__dirname, "../../contracts/clause_protocol.py"));
const text = file.toString("utf8");
const ADDR = "0x9e4efafad0fac013a9bac31c8bba86f1c516c866";
const fin = (exec: string, extra: Record<string, unknown> = {}) => ({ status_name: "FINALIZED", consensus_data: { leader_receipt: [{ execution_result: exec }] }, data: { contract_address: ADDR }, ...extra });

const client = (txs: Array<Record<string, unknown>>, code = text): DeployClient => {
  let i = 0;
  return { deployContract: async () => "0x" + "ab".repeat(32), getTransaction: async () => txs[Math.min(i++, txs.length - 1)], getContractCode: async () => code };
};
const fast = { pollMs: 0, sleep: async () => undefined };

describe("release-candidate source parity", () => {
  it("the audited constants equal the real contract file (LF, ASCII)", () => {
    expect(createHash("sha256").update(file).digest("hex")).toBe(EXPECTED_CONTRACT_SHA256);
    expect(file.length).toBe(EXPECTED_CONTRACT_BYTES);
    expect(text.includes("\r")).toBe(false);
    expect([...file].every((b) => b < 128)).toBe(true);
  });
  it("the deploy tool accepts exactly the audited source and rejects any change", async () => {
    expect((await checkSource(text)).ok).toBe(true);
    expect((await checkSource(text + "\n")).ok).toBe(false);
    expect((await checkSource(text.replace("class ClauseProtocol", "class ClauseProtocol2"))).ok).toBe(false);
    expect((await checkSource(text.replace(/\n/g, "\r\n"))).ok).toBe(false);
  });
});

describe("deploy watcher never over-claims", () => {
  it("returns the address only after FINALIZED with a successful execution", async () => {
    const seen: string[] = [];
    const r = await deployAndWatch(client([{ status_name: "PENDING" }, { status_name: "ACCEPTED", data: { contract_address: ADDR } }, fin("SUCCESS")]), text, (l) => seen.push(l), fast);
    expect(r).toMatchObject({ status: "FINALIZED", executionResult: "SUCCESS", contractAddress: ADDR });
    expect(seen[0]).toMatch(/wallet/i);
  });
  it("a FINALIZED-with-error deployment yields NO address", async () => {
    expect(await deployAndWatch(client([fin("ERROR")]), text, () => undefined, fast)).toMatchObject({ contractAddress: null, executionResult: "ERROR" });
  });
  it("undetermined / stuck deployments yield no address", async () => {
    expect((await deployAndWatch(client([{ status_name: "UNDETERMINED" }]), text, () => undefined, fast)).contractAddress).toBeNull();
    expect((await deployAndWatch(client([{ status_name: "ACCEPTED", data: { contract_address: ADDR } }]), text, () => undefined, { ...fast, maxPolls: 3 }))).toMatchObject({ status: "NOT_FINALIZED_YET", contractAddress: null });
  });
  it("post-deployment parity compares the deployed source hash to the audited hash", async () => {
    expect((await checkDeployedSource(client([]), ADDR)).matches).toBe(true);
    expect((await checkDeployedSource(client([], text + " "), ADDR)).matches).toBe(false);
  });
});

describe("exactly one canonical address configuration source", () => {
  const files: string[] = [];
  const walk = (d: string) => { for (const f of readdirSync(d)) { const p = join(d, f); if (statSync(p).isDirectory()) walk(p); else if (/\.(ts|tsx)$/.test(f)) files.push(p); } };
  walk(resolve(__dirname, "../src"));
  it("the environment (and so VITE_CLAUSE_CONTRACT_ADDRESS) is read only in src/config/contract.ts", () => {
    const users = files.filter((f) => readFileSync(f, "utf8").includes("import.meta.env")).map((f) => f.split("\\").join("/").split("/src/")[1]);
    expect(users).toEqual(["config/contract.ts"]);
    expect(readFileSync(resolve(__dirname, "../src/config/contract.ts"), "utf8").match(/import\.meta\.env/g)?.length).toBeGreaterThan(0);
  });
});
