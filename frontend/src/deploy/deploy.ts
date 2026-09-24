import { EXPECTED_CONTRACT_BYTES, EXPECTED_CONTRACT_SHA256 } from "./expected";

export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export interface SourceCheck { ok: boolean; sha256: string; bytes: number; expected: string; reason: string }

/** The tool refuses to deploy anything but the audited release candidate. */
export async function checkSource(code: string): Promise<SourceCheck> {
  const sha256 = await sha256Hex(code);
  const bytes = new TextEncoder().encode(code).length;
  const ok = sha256 === EXPECTED_CONTRACT_SHA256 && bytes === EXPECTED_CONTRACT_BYTES;
  return { ok, sha256, bytes, expected: EXPECTED_CONTRACT_SHA256, reason: ok ? "Source matches the audited release candidate." : "SOURCE DOES NOT MATCH THE AUDITED RELEASE CANDIDATE. Do not deploy." };
}

/** The minimal client surface used (genlayer-js 1.1.8). */
export interface DeployClient {
  deployContract(a: { code: string; args: never[] }): Promise<string>;
  getTransaction(a: { hash: never }): Promise<Record<string, unknown>>;
  getContractCode(address: never): Promise<string>;
}

export interface DeployResult { hash: string; status: string; executionResult: string; contractAddress: string | null; raw: unknown }

const NAMES = ["UNINITIALIZED", "PENDING", "PROPOSING", "COMMITTING", "REVEALING", "ACCEPTED", "UNDETERMINED", "FINALIZED", "CANCELED", "APPEAL_REVEALING", "APPEAL_COMMITTING", "READY_TO_FINALIZE", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"];

function statusOf(tx: Record<string, unknown>): string {
  const n = (tx.statusName ?? tx.status_name) as string | undefined;
  if (typeof n === "string") return n.toUpperCase();
  const s = Number(tx.status);
  return Number.isInteger(s) && NAMES[s] ? NAMES[s] : "UNKNOWN";
}

function pickAddress(tx: Record<string, unknown>): string | null {
  const data = tx.data as Record<string, unknown> | undefined;
  const cand = [data?.contract_address, (tx.txDataDecoded as Record<string, unknown> | undefined)?.contractAddress, tx.to_address, tx.recipient];
  for (const c of cand) if (typeof c === "string" && /^0x[0-9a-fA-F]{40}$/.test(c)) return c;
  return null;
}

/** Sends the deployment (the wallet prompts here), then polls until FINALIZED; never claims success without FINALIZED + SUCCESS. */
export async function deployAndWatch(client: DeployClient, code: string, onUpdate: (line: string) => void, opts: { pollMs?: number; maxPolls?: number; sleep?: (ms: number) => Promise<void> } = {}): Promise<DeployResult> {
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  onUpdate("Waiting for your wallet to approve the deployment...");
  const hash = await client.deployContract({ code, args: [] });
  onUpdate(`Submitted. Transaction hash: ${hash}`);
  let last: Record<string, unknown> = {};
  for (let i = 0; i < (opts.maxPolls ?? 180); i++) {
    try { last = await client.getTransaction({ hash: hash as never }); } catch { /* transient */ }
    const status = statusOf(last);
    const leader = ((last.consensus_data as { leader_receipt?: Array<{ execution_result?: string }> } | undefined)?.leader_receipt ?? [])[0]?.execution_result ?? "UNKNOWN";
    onUpdate(`Status: ${status}${leader !== "UNKNOWN" ? ` (execution ${leader})` : ""}`);
    if (status === "FINALIZED") return { hash, status, executionResult: leader, contractAddress: leader === "SUCCESS" ? pickAddress(last) : null, raw: last };
    if (["UNDETERMINED", "CANCELED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT"].includes(status)) return { hash, status, executionResult: leader, contractAddress: null, raw: last };
    await sleep(opts.pollMs ?? 2000);
  }
  return { hash, status: "NOT_FINALIZED_YET", executionResult: "UNKNOWN", contractAddress: null, raw: last };
}

/** Post-deployment parity: fetch the deployed source and compare its hash (informational; the network may normalize source). */
export async function checkDeployedSource(client: DeployClient, address: string): Promise<{ matches: boolean; sha256: string }> {
  const deployed = await client.getContractCode(address as never);
  const sha256 = await sha256Hex(deployed);
  return { matches: sha256 === EXPECTED_CONTRACT_SHA256, sha256 };
}
