import type { Address } from "../config/contract";
import type { CallSpec } from "../contract/calls";
import type { ClauseTransport } from "../contract/transport";
import { humanizeError, type HumanError } from "../domain/errors";
import { classifyTx, leaderError, type TxClass } from "./status";

export type TxPhase =
  | { phase: "idle" }
  | { phase: "preparing"; label: string }
  | { phase: "awaiting-wallet"; label: string }
  | { phase: "wallet-rejected"; error: HumanError }
  | { phase: "submitted"; hash: `0x${string}` }
  | { phase: "consensus"; hash: `0x${string}`; detail: TxClass }
  | { phase: "accepted"; hash: `0x${string}` }
  | { phase: "finalized"; hash: `0x${string}` }
  | { phase: "confirmed"; hash: `0x${string}`; rereadFailed: boolean }
  | { phase: "failed"; hash?: `0x${string}`; error: HumanError }
  | { phase: "undetermined"; hash: `0x${string}` }
  | { phase: "pending-unknown"; hash: `0x${string}` };

export type TxOutcome<T> =
  | { ok: true; hash: `0x${string}`; data: T | undefined; rereadFailed: boolean }
  | { ok: false; reason: "wallet-rejected" | "submit-failed" | "execution-error" | "undetermined" | "canceled" | "timeout" | "pending-unknown"; hash?: `0x${string}`; error: HumanError };

export interface RunOptions<T> {
  onPhase?: (p: TxPhase) => void;
  /** Authoritative contract reread performed ONLY after the transaction is FINALIZED with a successful execution. */
  reread?: () => Promise<T>;
  pollMs?: number;
  maxPolls?: number;
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Full write lifecycle: prepare -> wallet confirmation -> submitted -> consensus -> accepted -> FINALIZED -> authoritative reread.
 * A transaction hash alone is never success; a FINALIZED transaction with a failed/unknown execution result is a failure;
 * nothing is optimistically applied - callers only receive data that was re-read from the contract after finality.
 */
export async function runTransaction<T>(transport: ClauseTransport, address: Address, spec: CallSpec, opts: RunOptions<T> = {}): Promise<TxOutcome<T>> {
  const emit = opts.onPhase ?? (() => undefined);
  const sleep = opts.sleep ?? defaultSleep;
  const pollMs = opts.pollMs ?? 2000;
  const maxPolls = opts.maxPolls ?? 150;

  emit({ phase: "preparing", label: spec.label });
  let hash: `0x${string}`;
  try {
    emit({ phase: "awaiting-wallet", label: spec.label });
    hash = await transport.writeContract({ address, functionName: spec.functionName, args: spec.args, value: spec.value });
  } catch (e) {
    const error = humanizeError(e);
    if (error.kind === "wallet-rejected") {
      emit({ phase: "wallet-rejected", error });
      return { ok: false, reason: "wallet-rejected", error };
    }
    emit({ phase: "failed", error });
    return { ok: false, reason: "submit-failed", error };
  }
  emit({ phase: "submitted", hash });

  let sawAccepted = false;
  for (let i = 0; i < maxPolls; i++) {
    let cls: TxClass = "unknown";
    let tx;
    try {
      tx = await transport.getTransaction({ hash });
      cls = classifyTx(tx);
    } catch {
      cls = "unknown"; // transient read failure: keep polling, never assume success
    }
    if (cls === "finalized-success") {
      emit({ phase: "finalized", hash });
      let data: T | undefined;
      let rereadFailed = false;
      if (opts.reread) {
        try { data = await opts.reread(); } catch { rereadFailed = true; }
      }
      emit({ phase: "confirmed", hash, rereadFailed });
      return { ok: true, hash, data, rereadFailed };
    }
    if (cls === "finalized-error" || cls === "finalized-unknown") {
      const detail = tx ? leaderError(tx) : "";
      const error = humanizeError(detail || (cls === "finalized-unknown" ? "finalized with an unverifiable execution result" : "execution error"));
      const shown = cls === "finalized-unknown" ? { ...error, title: "Result could not be verified", message: "The transaction finalized but its execution result could not be verified, so it is treated as NOT successful. Re-check the contract state before retrying." } : error;
      emit({ phase: "failed", hash, error: shown });
      return { ok: false, reason: "execution-error", hash, error: shown };
    }
    if (cls === "undetermined") {
      const error = humanizeError("undetermined");
      emit({ phase: "undetermined", hash });
      return { ok: false, reason: "undetermined", hash, error: { ...error, kind: "undetermined", title: "Consensus undetermined", message: "The validators did not reach agreement. No state was changed. The action can be retried." } };
    }
    if (cls === "canceled" || cls === "timeout") {
      const error = { kind: "consensus-failure" as const, title: cls === "canceled" ? "Transaction canceled" : "Validators timed out", message: "The network did not complete this transaction. No state was changed.", technical: cls };
      emit({ phase: "failed", hash, error });
      return { ok: false, reason: cls === "canceled" ? "canceled" : "timeout", hash, error };
    }
    if (cls === "accepted" && !sawAccepted) { sawAccepted = true; emit({ phase: "accepted", hash }); }
    else if (cls === "in-consensus") emit({ phase: "consensus", hash, detail: cls });
    await sleep(pollMs);
  }
  const error = { kind: "not-finalized" as const, title: "Still waiting for finality", message: "The transaction has not finalized yet. Nothing is assumed: track it by hash and re-check before continuing.", technical: `no final status after ${maxPolls} polls` };
  emit({ phase: "pending-unknown", hash });
  return { ok: false, reason: "pending-unknown", hash, error };
}
