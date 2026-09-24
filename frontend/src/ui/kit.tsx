import { useState, type ReactNode } from "react";
import type { ClaimStatus, Outcome, PassportStatus } from "../contract/types";
import type { ChecklistItem } from "../domain/checklist";
import type { Provenance, TimelineEvent } from "../domain/timeline";
import { STAGES } from "../domain/timeline";
import { formatUtc } from "../domain/format";

export function Loading({ what = "Reading the contract" }: { what?: string }) {
  return <p role="status" className="muted">{what}…</p>;
}

export function ErrorBox({ title, message, technical }: { title: string; message: string; technical?: string }) {
  return (
    <div className="banner bad" role="alert">
      <strong>{title}</strong>
      <p>{message}</p>
      {technical ? <details><summary>Technical diagnostics</summary><pre className="diag">{technical}</pre></details> : null}
    </div>
  );
}

/** Copyable identifier that always wraps (never clipped) and stays selectable. */
export function Copyable({ value, label }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  const copy = () => {
    try { void navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); }); } catch { /* clipboard unavailable */ }
  };
  return (
    <span className="wrap mono">
      {value}{" "}
      <button type="button" className="btn secondary small" onClick={copy} aria-label={`Copy ${label ?? "value"}`}>{done ? "Copied" : "Copy"}</button>
    </span>
  );
}

export function Hex({ value }: { value: string }) { return <span className="wrap mono">{value}</span>; }

const PROV_LABEL: Record<Provenance, string> = { protocol: "Protocol time", asserted: "Claimant-asserted", deadline: "Deadline" };
const PROV_GLYPH: Record<Provenance, string> = { protocol: "●", asserted: "?", deadline: "◷" };

/** Every timestamp carries its provenance: on-chain protocol time, a claimant assertion, or a derived deadline. */
export function Seal({ at, provenance, label }: { at: number; provenance: Provenance; label?: string }) {
  return (
    <span className={`seal ${provenance}`}>
      <span className="seal-ring" aria-hidden="true">{PROV_GLYPH[provenance]}</span>
      <span>
        <span className="seal-tag">{label ?? PROV_LABEL[provenance]}</span><br />
        <time dateTime={at ? new Date(at * 1000).toISOString() : undefined}>{formatUtc(at)}</time>
      </span>
    </span>
  );
}

export function FrozenStamp({ animate = false, text = "Frozen terms" }: { animate?: boolean; text?: string }) {
  return <span className={`frozen-stamp${animate ? " animate" : ""}`} role="img" aria-label={text}>{text}</span>;
}

export function Sticker({ id, text, kind, picked }: { id: string; text?: string; kind: "COVERED" | "EXCLUDED"; picked?: boolean }) {
  return (
    <span className={`sticker${kind === "EXCLUDED" ? " excl" : ""}${picked ? " picked" : ""}`}>
      <b>{id}</b><span className="sr-only">{kind === "EXCLUDED" ? "exclusion" : "covered clause"} </span>{text}
    </span>
  );
}

type Tone = "ok" | "bad" | "wait" | "plum" | "neutral" | "final";
export function Badge({ tone, glyph, children }: { tone: Tone; glyph?: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{glyph ? <span className="g" aria-hidden="true">{glyph}</span> : null}{children}</span>;
}

export const CLAIM_STATUS_LABEL: Record<ClaimStatus, { text: string; tone: Tone; glyph: string }> = {
  RESPONSE_WINDOW: { text: "Awaiting manufacturer response", tone: "wait", glyph: "◷" },
  ACCEPTED: { text: "Accepted (no contest)", tone: "ok", glyph: "✔" },
  DISPUTED: { text: "Disputed - evidence phase", tone: "wait", glyph: "◐" },
  EVIDENCE_FROZEN: { text: "Evidence frozen", tone: "neutral", glyph: "❄" },
  DECIDED: { text: "Decided - challenge window", tone: "wait", glyph: "◷" },
  CHALLENGED: { text: "Application Challenge open", tone: "plum", glyph: "⚑" },
  CHALLENGE_RESOLVED: { text: "Application Challenge resolved", tone: "plum", glyph: "⚑" },
  FINAL: { text: "Final decision", tone: "final", glyph: "■" },
  SETTLED: { text: "Settled", tone: "final", glyph: "■" },
};
export function ClaimStatusBadge({ status }: { status: ClaimStatus }) {
  const s = CLAIM_STATUS_LABEL[status] ?? { text: status, tone: "neutral" as Tone, glyph: "•" };
  return <Badge tone={s.tone} glyph={s.glyph}>{s.text}</Badge>;
}

export const PASSPORT_STATUS: Record<PassportStatus, { text: string; tone: Tone; glyph: string }> = {
  ACTIVE: { text: "Coverage active", tone: "ok", glyph: "✔" },
  EXPIRED: { text: "Coverage ended", tone: "neutral", glyph: "◌" },
  CANCELLED: { text: "Cancelled", tone: "bad", glyph: "✖" },
};
export function PassportStatusBadge({ status }: { status: PassportStatus }) {
  const s = PASSPORT_STATUS[status] ?? { text: status, tone: "neutral" as Tone, glyph: "•" };
  return <Badge tone={s.tone} glyph={s.glyph}>{s.text}</Badge>;
}

/** Outcomes are deliberately distinct: INSUFFICIENT_EVIDENCE and EVIDENCE_UNAVAILABLE are never presented as "rejected". */
export const OUTCOME: Record<Outcome, { text: string; tone: Tone; glyph: string; explain: string }> = {
  COVERED: { text: "Covered", tone: "ok", glyph: "✔", explain: "The frozen evidence establishes that the failure satisfies a covered clause under the frozen terms." },
  NOT_COVERED: { text: "Not covered", tone: "bad", glyph: "✖", explain: "Coverage fails for an affirmative reason: outside the coverage window, the wrong product, or an established exclusion." },
  INSUFFICIENT_EVIDENCE: { text: "Insufficient evidence", tone: "wait", glyph: "◐", explain: "The evidence did not establish either coverage or a reason it fails. This is NOT a finding that the claim is false. The frozen terms decide what follows." },
  EVIDENCE_UNAVAILABLE: { text: "Evidence unavailable", tone: "wait", glyph: "◌", explain: "Submitted evidence could not be retrieved. Unavailable evidence is not treated as proof against either party. The frozen terms decide what follows." },
  INVALID_CLAIM: { text: "Invalid claim", tone: "bad", glyph: "⊘", explain: "The claim does not match the governing frozen warranty version." },
  ACCEPTED_NO_CONTEST: { text: "Accepted by manufacturer", tone: "ok", glyph: "✔", explain: "The manufacturer accepted the claim without contest; no adjudication was needed." },
};
export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const o = OUTCOME[outcome] ?? { text: outcome, tone: "neutral" as Tone, glyph: "•" };
  return <Badge tone={o.tone} glyph={o.glyph}>{o.text}</Badge>;
}

export function StageStrip({ reached }: { reached: number }) {
  return (
    <ol className="stages" aria-label="Claim progress">
      {STAGES.map((s, i) => (
        <li key={s} className={i < reached ? "done" : i === reached ? "now" : ""} aria-current={i === reached ? "step" : undefined}>
          <span>{s}<span className="sr-only">{i < reached ? " (done)" : i === reached ? " (current)" : " (upcoming)"}</span></span>
        </li>
      ))}
    </ol>
  );
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="timeline" aria-label="Diagnostic timeline">
      {events.map((e) => (
        <li key={e.key} className={e.done ? "done" : "todo"}>
          <div className="t-label">{e.label}{e.done ? <span className="sr-only"> (happened)</span> : <span className="sr-only"> (not yet)</span>}</div>
          {e.at ? <Seal at={e.at} provenance={e.provenance} /> : <span className="muted small">Not yet</span>}
          {e.detail ? <div className="small muted">{e.detail}</div> : null}
        </li>
      ))}
    </ol>
  );
}

const IC: Record<ChecklistItem["status"], string> = { ok: "✔", blocked: "✖", checking: "…", unverified: "?" };
export function Checklist({ items }: { items: ChecklistItem[] }) {
  return (
    <ul className="checklist">
      {items.map((i) => (
        <li key={i.key} className={i.status}>
          <span className="ic" aria-hidden="true">{IC[i.status]}</span>
          <span><strong>{i.label}</strong> <span className="sr-only">{i.status}: </span><br /><span className="small">{i.detail}</span></span>
        </li>
      ))}
    </ul>
  );
}

export function Gauge({ total, reserved, format }: { total: bigint; reserved: bigint; format: (v: bigint) => string }) {
  const pct = total === 0n ? 0 : Number((reserved * 100n) / total);
  return (
    <div className="gauge">
      <div className="gauge-dial" style={{ ["--res" as string]: pct }} role="img" aria-label={`${pct}% of capacity reserved`}><span>{pct}%</span></div>
      <dl>
        <div className="kv"><dt>Total capacity</dt><dd>{format(total)} GEN</dd></div>
        <div className="kv"><dt>Reserved for warranties</dt><dd>{format(reserved)} GEN</dd></div>
        <div className="kv"><dt>Unreserved (available)</dt><dd>{format(total - reserved)} GEN</dd></div>
      </dl>
    </div>
  );
}
