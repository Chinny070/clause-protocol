import type { Adjudication, Challenge, Claim, Evidence, FinalDecision, Passport } from "../contract/types";

/** Which of the time facts a timestamp is. Never shown without one of these tags. */
export type Provenance = "protocol" | "asserted" | "deadline";

export interface TimelineEvent {
  key: string;
  label: string;
  at: number; // unix seconds; 0 = not happened / not set
  provenance: Provenance;
  done: boolean;
  detail?: string;
}

export interface TimelineInput {
  passport: Passport | null;
  claim: Claim;
  evidence: Evidence[];
  adjudication: Adjudication | null;
  challenge: Challenge | null;
  correctedAdjudication: Adjudication | null;
  finalDecision: FinalDecision | null;
  challengeWindowClosesAt: number;
}

/** Builds the diagnostic timeline from contract timestamps only. Claimant-asserted dates are tagged `asserted`. */
export function buildTimeline(i: TimelineInput): TimelineEvent[] {
  const ev: TimelineEvent[] = [];
  if (i.passport) ev.push({ key: "issued", label: "Warranty issued", at: i.passport.registeredAt, provenance: "protocol", done: true });
  ev.push({ key: "failure", label: "Failure date asserted by claimant", at: i.claim.failureAssertedAt, provenance: "asserted", done: true,
    detail: "Not verified by the protocol. Used only to check the coverage window." });
  ev.push({ key: "filed", label: "Claim filed", at: i.claim.filedAt, provenance: "protocol", done: true });
  ev.push({ key: "response-deadline", label: "Manufacturer response deadline", at: i.claim.responseDeadline, provenance: "deadline", done: i.claim.respondedAt > 0 });
  return finishTimeline(ev, i);
}

function finishTimeline(ev: TimelineEvent[], i: TimelineInput): TimelineEvent[] {
  const c = i.claim;
  ev.push({
    key: "response", label: c.manufacturerResponse === "ACCEPT" ? "Manufacturer accepted (no contest)" : c.manufacturerResponse === "DISPUTE" ? "Manufacturer disputed" : "Manufacturer response",
    at: c.respondedAt, provenance: "protocol", done: c.respondedAt > 0, detail: c.manufacturerResponse === "" ? "Silence after the deadline is treated as a dispute." : undefined,
  });
  for (const e of [...i.evidence].sort((a, b) => a.submittedAt - b.submittedAt)) {
    ev.push({ key: `evidence-${e.evidenceId}`, label: `Evidence #${e.evidenceId} submitted`, at: e.submittedAt, provenance: "protocol", done: true, detail: e.host });
  }
  ev.push({ key: "frozen", label: "Evidence frozen", at: c.evidenceFrozenAt, provenance: "protocol", done: c.evidenceFrozenAt > 0 });
  const a = i.adjudication;
  ev.push({ key: "adjudicated", label: "GenLayer adjudication recorded", at: a?.adjudicatedAt ?? 0, provenance: "protocol", done: !!a, detail: a?.outcome });
  ev.push({ key: "window-open", label: "Application Challenge window opened", at: a?.adjudicatedAt ?? 0, provenance: "protocol", done: !!a });
  ev.push({ key: "window-close", label: "Application Challenge window closes", at: i.challengeWindowClosesAt, provenance: "deadline", done: false });
  const ch = i.challenge;
  if (ch) {
    ev.push({ key: "challenge-filed", label: "Application Challenge filed", at: ch.filedAt, provenance: "protocol", done: true, detail: ch.ground });
    ev.push({ key: "challenge-resolved", label: "Application Challenge resolved", at: ch.resolvedAt, provenance: "protocol", done: ch.status === "RESOLVED", detail: ch.result || undefined });
  }
  const f = i.finalDecision;
  ev.push({ key: "final", label: "Final application decision", at: f?.finalizedAt ?? 0, provenance: "protocol", done: !!f, detail: f?.finalOutcome });
  ev.push({ key: "settled", label: "Settlement authorized", at: f?.settledAt ?? 0, provenance: "protocol", done: !!f && f.settledAt > 0 });
  ev.push({ key: "withdrawn", label: "Withdrawal", at: f?.withdrawnAt ?? 0, provenance: "protocol", done: !!f && f.withdrawnAt > 0 });
  return ev;
}

/** The main stage strip: index of the furthest completed stage. */
export const STAGES = ["Terms frozen", "Product registered", "Claim filed", "Evidence frozen", "GenLayer decision", "Challenge", "Final remedy"] as const;

export function stageReached(status: Claim["status"], hasChallenge: boolean): number {
  switch (status) {
    case "RESPONSE_WINDOW": case "DISPUTED": return 2;
    case "ACCEPTED": return 5;
    case "EVIDENCE_FROZEN": return 3;
    case "DECIDED": return 4;
    case "CHALLENGED": return 5;
    case "CHALLENGE_RESOLVED": return hasChallenge ? 5 : 4;
    case "FINAL": case "SETTLED": return 6;
    default: return 1;
  }
}
