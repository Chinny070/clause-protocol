import type { RawTx } from "../contract/transport";

/** Order of genlayer-js 1.1.8 `TransactionStatus` (numeric receipts carry the index). */
const NUMERIC_STATUS = [
  "UNINITIALIZED", "PENDING", "PROPOSING", "COMMITTING", "REVEALING", "ACCEPTED", "UNDETERMINED", "FINALIZED", "CANCELED",
  "APPEAL_REVEALING", "APPEAL_COMMITTING", "READY_TO_FINALIZE", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT",
] as const;

export function statusName(tx: RawTx): string | undefined {
  const named = tx.status_name ?? tx.statusName;
  if (typeof named === "string" && named !== "") return named.toUpperCase();
  if (typeof tx.status === "string" && Number.isNaN(Number(tx.status))) return tx.status.toUpperCase();
  const n = typeof tx.status === "string" ? Number(tx.status) : tx.status;
  if (typeof n === "number" && Number.isInteger(n) && n >= 0 && n < NUMERIC_STATUS.length) return NUMERIC_STATUS[n];
  return undefined;
}

export type ExecutionResult = "SUCCESS" | "ERROR" | "UNKNOWN";

/** The leader's execution result: a FINALIZED transaction can still have reverted (a UserError). Unknown fails closed. */
export function executionResult(tx: RawTx): ExecutionResult {
  const named = tx.txExecutionResultName;
  const leader = tx.consensus_data?.leader_receipt?.[0]?.execution_result;
  const v = (typeof leader === "string" ? leader : typeof named === "string" ? named : "").toUpperCase();
  if (v === "SUCCESS" || v === "FINISHED_WITH_RETURN") return "SUCCESS";
  if (v === "ERROR" || v === "FAILURE" || v === "FINISHED_WITH_ERROR") return "ERROR";
  return "UNKNOWN";
}

export function leaderError(tx: RawTx): string {
  return tx.consensus_data?.leader_receipt?.[0]?.genvm_result?.stderr ?? "";
}

export type TxClass =
  | "finalized-success" | "finalized-error" | "finalized-unknown" | "accepted" | "in-consensus"
  | "undetermined" | "timeout" | "canceled" | "unknown";

export function classifyTx(tx: RawTx): TxClass {
  const s = statusName(tx);
  if (s === undefined) return "unknown";
  switch (s) {
    case "FINALIZED": {
      const r = executionResult(tx);
      return r === "SUCCESS" ? "finalized-success" : r === "ERROR" ? "finalized-error" : "finalized-unknown";
    }
    case "ACCEPTED":
    case "READY_TO_FINALIZE":
      return "accepted";
    case "UNDETERMINED":
      return "undetermined";
    case "VALIDATORS_TIMEOUT":
    case "LEADER_TIMEOUT":
      return "timeout";
    case "CANCELED":
      return "canceled";
    case "PENDING": case "PROPOSING": case "COMMITTING": case "REVEALING": case "APPEAL_REVEALING": case "APPEAL_COMMITTING": case "UNINITIALIZED":
      return "in-consensus";
    default:
      return "unknown";
  }
}

/** Only this class is ever "Safe to continue". Everything uncertain fails closed. */
export function isSafeToContinue(c: TxClass): boolean { return c === "finalized-success"; }
