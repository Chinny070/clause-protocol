import type { ClauseTransport } from "../contract/transport";
import type { FinalityState } from "../domain/checklist";
import { classifyTx, isSafeToContinue, type TxClass } from "./status";
import type { TxJournal } from "./journal";

export interface FinalityVerdict { txClass: TxClass; safe: boolean; reason: string }

const REASONS: Record<TxClass, string> = {
  "finalized-success": "Finalized with a successful execution.",
  "finalized-error": "The transaction finalized but its execution failed, so it did not change contract state.",
  "finalized-unknown": "The transaction finalized but its execution result could not be verified.",
  accepted: "Accepted by validators but not Finalized yet (the protocol appeal window is still open).",
  "in-consensus": "Still in consensus.",
  undetermined: "Consensus was undetermined.",
  timeout: "Validators timed out.",
  canceled: "The transaction was canceled.",
  unknown: "The transaction status could not be determined.",
};

/**
 * GenLayer Protocol Finality check for one transaction hash, straight from the network. Anything other than
 * "Finalized + successful execution" - including errors reading the status - is NOT safe (fail closed).
 */
export async function verifyFinality(transport: ClauseTransport, hash: `0x${string}`): Promise<FinalityVerdict> {
  try {
    const tx = await transport.getTransaction({ hash });
    const c = classifyTx(tx);
    return { txClass: c, safe: isSafeToContinue(c), reason: REASONS[c] };
  } catch (e) {
    return { txClass: "unknown", safe: false, reason: `Could not read the transaction from GenLayer (${e instanceof Error ? e.message : String(e)}).` };
  }
}

/** Resolves the FinalityState for an action from the journal (or a user-supplied hash) plus a live network check. */
export async function resolveFinality(
  transport: ClauseTransport, journal: TxJournal, claimId: number, prerequisites: readonly string[], manualHash?: `0x${string}`,
): Promise<FinalityState> {
  if (prerequisites.length === 0) return { state: "not-required" };
  const hash = manualHash ?? journal.find(claimId, prerequisites)?.hash;
  if (!hash) return { state: "no-transaction", needs: [...prerequisites] };
  const v = await verifyFinality(transport, hash);
  return v.safe ? { state: "safe", hash } : { state: "not-safe", hash, reason: v.reason };
}
