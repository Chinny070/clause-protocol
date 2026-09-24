import type { Address } from "../../src/config/contract";
import type { Calldata, ClauseTransport, RawTx } from "../../src/contract/transport";

export const ADDR: Address = "0x1111111111111111111111111111111111111111";
export const HASH = ("0x" + "ab".repeat(32)) as `0x${string}`;

export interface MockOptions {
  reads?: Record<string, (args: Calldata[]) => unknown>;
  write?: (fn: string, args: Calldata[], value?: bigint) => `0x${string}` | Promise<`0x${string}`>;
  /** Sequence of transaction records returned by successive getTransaction calls (the last repeats). */
  txSequence?: Array<RawTx | Error>;
}

export function makeTransport(o: MockOptions = {}): ClauseTransport & { calls: { reads: string[]; writes: string[]; getTx: number } } {
  const calls = { reads: [] as string[], writes: [] as string[], getTx: 0 };
  const seq = o.txSequence ?? [];
  return {
    calls,
    async readContract({ functionName, args }) {
      calls.reads.push(functionName);
      const h = o.reads?.[functionName];
      if (!h) throw new Error(`no mock for read ${functionName}`);
      return h(args ?? []);
    },
    async writeContract({ functionName, args, value }) {
      calls.writes.push(functionName);
      if (o.write) return o.write(functionName, args ?? [], value);
      return HASH;
    },
    async waitForTransactionReceipt() { return seq[seq.length - 1] as RawTx; },
    async getTransaction() {
      const i = Math.min(calls.getTx, seq.length - 1);
      calls.getTx += 1;
      const v = seq[i];
      if (v instanceof Error) throw v;
      return v as RawTx;
    },
  };
}

export const tx = (status: string, exec: "SUCCESS" | "ERROR" | null = "SUCCESS"): RawTx => ({
  hash: HASH, status_name: status,
  consensus_data: exec ? { leader_receipt: [{ execution_result: exec, genvm_result: { stderr: exec === "ERROR" ? "claim is not final" : "" } }] } : {},
});
