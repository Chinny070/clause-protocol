/** Human-readable error classification. Raw technical detail is always preserved for the diagnostics panel. */
export type ErrorKind =
  | "wallet-rejected" | "wrong-chain" | "rpc-unavailable" | "contract-unavailable" | "malformed-response"
  | "invalid-claim-state" | "challenge-window-closed" | "evidence-cap" | "ineligible-source" | "retrieval-failure"
  | "consensus-failure" | "undetermined" | "not-finalized" | "insufficient-capacity" | "unauthorized" | "already-withdrawn"
  | "nothing-to-withdraw" | "unknown";

export interface HumanError { kind: ErrorKind; title: string; message: string; technical: string }

const RULES: Array<{ kind: ErrorKind; test: RegExp; title: string; message: string }> = [
  { kind: "wallet-rejected", test: /user rejected|rejected the request|denied transaction|ACTION_REJECTED|4001/i, title: "Signature rejected",
    message: "You rejected the request in your wallet. Nothing was sent and nothing changed." },
  { kind: "wrong-chain", test: /wallet is on chain|wrong (chain|network)|chain mismatch|unrecognized chain/i, title: "Wrong network",
    message: "Your wallet is not on GenLayer StudioNet (chain 61999). Switch networks and try again." },
  { kind: "rpc-unavailable", test: /failed to fetch|fetch failed|networkerror|ECONNREFUSED|ETIMEDOUT|timeout|network request failed|HTTP request failed|502|503|504/i,
    title: "RPC unavailable", message: "The GenLayer StudioNet RPC endpoint could not be reached. Check your connection and retry; nothing was changed." },
  { kind: "already-withdrawn", test: /settlement already withdrawn/i, title: "Already withdrawn", message: "This settlement has already been withdrawn. Nothing more is claimable." },
  { kind: "nothing-to-withdraw", test: /nothing to withdraw/i, title: "Nothing to withdraw", message: "This claim settled with no claimable GEN (a non-payable outcome, or the warranty cap was already used)." },
  { kind: "challenge-window-closed", test: /challenge window has closed|challenge window has not opened|resolution period has lapsed/i, title: "Challenge window closed",
    message: "The Application Challenge window for this decision is closed." },
  { kind: "evidence-cap", test: /maximum of 10 adjudicable evidence/i, title: "Evidence limit reached",
    message: "This claim already has the maximum of 10 adjudicable evidence records. Slots are first-come and cannot be freed." },
  { kind: "ineligible-source", test: /ineligible|source policy|not one of this constitution/i, title: "Source not eligible",
    message: "That source is not permitted by the frozen source policy or evidence categories." },
  { kind: "insufficient-capacity", test: /insufficient pool capacity|exceeds available/i, title: "Insufficient warranty capacity",
    message: "The pool does not have enough unreserved capacity for this action." },
  { kind: "unauthorized", test: /caller is not|neither the holder nor the manufacturer|not the settlement recipient|not this warranty|not this claim/i,
    title: "Not authorized", message: "The connected account is not allowed to perform this action on this record." },
  { kind: "retrieval-failure", test: /model call failed|LLM_ERROR|retrieval/i, title: "Consensus step failed",
    message: "The validators could not produce a usable result. Nothing was changed and the step can be retried." },
  { kind: "invalid-claim-state", test: /not (in|awaiting)|is not final|not settled|already (finalized|settled|adjudicated|frozen)|unresolved|still open|no adjudication|not a state|no pending|has no |not ACTIVE|unsettled claim|grace/i,
    title: "Not available in this state", message: "The claim or warranty is not in a state that allows this action right now." },
];

export function humanizeError(err: unknown): HumanError {
  const technical = err instanceof Error ? `${err.name}: ${err.message}` : typeof err === "string" ? err : JSON.stringify(err);
  const hit = RULES.find((r) => r.test.test(technical));
  if (hit) return { kind: hit.kind, title: hit.title, message: hit.message, technical };
  return { kind: "unknown", title: "Something went wrong", message: "The action could not be completed. Nothing was changed. Details are available below.", technical };
}
