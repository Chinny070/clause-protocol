import { useMemo, useState } from "react";
import { useTx } from "../app/context";
import { useClause, useWallet } from "../app/context";
import { loadClaimBundle, type ClaimBundle } from "../app/data";
import { calls } from "../contract/calls";
import type { Challenge, ChallengeGround, Citation } from "../contract/types";
import { evaluateAction } from "../domain/checklist";
import { formatUtc } from "../domain/format";
import { GatedActionButton, useFinality } from "./actions";
import { Badge, Checklist, Seal } from "./kit";

export const GROUNDS: Record<ChallengeGround, { label: string; blurb: string; how: string; cite: "evidence" | "clause-covered" | "clause-excluded" | "constitution" | "timestamp" }> = {
  IGNORED_EVIDENCE: { label: "Ignored evidence", cite: "evidence", how: "Reviewed by validators (after deterministic checks)",
    blurb: "A frozen evidence record that was considered but not relied on should have mattered." },
  WRONG_WARRANTY_VERSION: { label: "Wrong warranty version", cite: "constitution", how: "Decided deterministically by plain code",
    blurb: "The governing terms version is wrong. The governing version is frozen at issuance, so this can only succeed if the stored check disagrees with the frozen record." },
  WRONG_CLAUSE: { label: "Wrong clause", cite: "clause-covered", how: "Reviewed by validators (after deterministic checks)",
    blurb: "A covered clause your claim targeted was misapplied." },
  EXCLUSION_MISAPPLIED: { label: "Exclusion misapplied", cite: "clause-excluded", how: "Reviewed by validators (after deterministic checks)",
    blurb: "An exclusion was applied (or missed) although the evidence does not establish it." },
  TEMPORAL_ERROR: { label: "Temporal error", cite: "timestamp", how: "Decided deterministically by plain code",
    blurb: "The coverage window was miscalculated from the frozen timestamps." },
  SOURCE_AUTHORITY_ERROR: { label: "Source authority error", cite: "evidence", how: "Decided deterministically by plain code",
    blurb: "A source was wrongly treated as (in)eligible. Eligibility is decided by the frozen source policy and cannot be overridden." },
  PRODUCT_MATCH_ERROR: { label: "Product match error", cite: "evidence", how: "Reviewed by validators (after deterministic checks)",
    blurb: "The evidence was matched (or not matched) to the registered product incorrectly." },
};
const TIMESTAMPS = ["failure_asserted_at", "coverage_start", "coverage_end", "filed_at", "adjudicated_at", "evidence_frozen_at"];

const RESULT_TEXT: Record<string, string> = {
  UPHELD: "Upheld — a well-formed challenge found no material error; the original decision stands.",
  REVERSED: "Reversed — a material error was confirmed; a corrected decision was recorded and the original kept for history.",
  REMAND: "Remand — one bounded re-adjudication was ordered; its result is final.",
  INVALID_CHALLENGE: "Invalid — the premise is impossible under the frozen rules, or the challenge lapsed unresolved. The original decision stands.",
};

export function ChallengeHistory({ challenge }: { challenge: Challenge }) {
  const g = GROUNDS[challenge.ground];
  return (
    <section className="challenge-plate" aria-labelledby="challenge-h">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 id="challenge-h">Application Challenge</h2>
        <Badge tone="plum" glyph="⚑">{challenge.status === "RESOLVED" ? challenge.result.replace("_", " ") : challenge.status.replace("_", " ")}</Badge>
      </div>
      <p className="small">An Application Challenge contests a material error in a CLAUSE adjudication. It is not a GenLayer Protocol Appeal.</p>
      <div className="grid auto">
        <div className="kv"><dt>Ground</dt><dd>{g?.label ?? challenge.ground}</dd></div>
        <div className="kv"><dt>Filed</dt><dd><Seal at={challenge.filedAt} provenance="protocol" /></dd></div>
        <div className="kv"><dt>Filed by</dt><dd className="mono wrap">{challenge.challenger}</dd></div>
        <div className="kv"><dt>Resolved</dt><dd>{challenge.resolvedAt ? <Seal at={challenge.resolvedAt} provenance="protocol" /> : "Not yet"}</dd></div>
      </div>
      <h3>Explanation (by the challenger, unverified)</h3>
      <blockquote className="wrap" style={{ margin: 0 }}>{challenge.explanation}</blockquote>
      <p className="small">Cites: {challenge.citation.evidence_ids.length ? `evidence ${challenge.citation.evidence_ids.map((i) => "#" + i).join(", ")}; ` : ""}{challenge.citation.clause_ids.length ? `clauses ${challenge.citation.clause_ids.join(", ")}; ` : ""}{challenge.citation.constitution_id ? `terms version id ${challenge.citation.constitution_id}; ` : ""}{challenge.citation.timestamp_field ? `timestamp ${challenge.citation.timestamp_field}` : ""}</p>
      {challenge.result ? <p><strong>{RESULT_TEXT[challenge.result]}</strong></p> : <p><strong>Awaiting resolution.</strong></p>}
      {challenge.resolutionReason ? <p className="small wrap">{challenge.resolutionReason}</p> : null}
      {challenge.remandIssue ? <p className="small wrap"><strong>Remand issue:</strong> {challenge.remandIssue}</p> : null}
      {challenge.resolutionPath ? <p className="small">Resolved by: {challenge.resolutionPath === "DETERMINISTIC" ? "plain code" : challenge.resolutionPath === "LAPSED" ? "lapse (unresolved in time)" : challenge.resolutionPath === "REMAND_REVIEW" ? "remand re-adjudication" : "validator review"}.</p> : null}
    </section>
  );
}

/** File form: ground picker, ground-specific citation picker, bounded explanation, review step, then a gated submit. */
export function FileChallengeForm({ bundle, onDone }: { bundle: ClaimBundle; onDone: () => void }) {
  const { protocolNow } = useClause();
  const wallet = useWallet();
  const tx = useTx();
  const { reader } = useClause();
  const [ground, setGround] = useState<ChallengeGround>("IGNORED_EVIDENCE");
  const [evidenceIds, setEvidenceIds] = useState<number[]>([]);
  const [clauseIds, setClauseIds] = useState<string[]>([]);
  const [constitutionId, setConstitutionId] = useState("");
  const [tsField, setTsField] = useState("failure_asserted_at");
  const [explanation, setExplanation] = useState("");
  const [review, setReview] = useState(false);
  const g = GROUNDS[ground];
  const a = bundle.adjudication;

  const citation: Citation = useMemo(() => ({
    evidence_ids: g.cite === "evidence" ? evidenceIds : [], clause_ids: g.cite.startsWith("clause") ? clauseIds : [],
    constitution_id: g.cite === "constitution" ? Number(constitutionId) || 0 : 0, timestamp_field: g.cite === "timestamp" ? tsField : "",
  }), [g.cite, evidenceIds, clauseIds, constitutionId, tsField]);

  const problems: string[] = [];
  if (g.cite === "evidence" && evidenceIds.length === 0) problems.push("Pick at least one evidence record.");
  if (g.cite.startsWith("clause") && clauseIds.length === 0) problems.push("Pick at least one clause.");
  if (g.cite === "constitution" && !(Number(constitutionId) > 0)) problems.push("Enter the terms version id you believe should govern.");
  if (explanation.trim() === "") problems.push("Write a short explanation.");
  if (explanation.length > 1000) problems.push("The explanation is limited to 1,000 characters.");

  const fin = useFinality("file_challenge", bundle.claim);
  const gate = evaluateAction("file_challenge", { claim: bundle.claim, constitution: bundle.constitution, adjudication: a, challenge: null, finalDecision: null, protocolNow: protocolNow(), account: wallet.address, finality: fin.finality });
  const stateItems = gate.items;

  const candidates = g.cite === "evidence"
    ? bundle.evidence.filter((e) => ground === "SOURCE_AUTHORITY_ERROR" || (a?.evidenceIdsConsidered.includes(e.evidenceId) && (ground !== "IGNORED_EVIDENCE" || !a.evidenceIdsRelied.includes(e.evidenceId))))
    : [];
  const clauseCandidates = g.cite === "clause-covered" ? bundle.clauses.filter((c) => c.kind === "COVERED" && bundle.claim.targetedClauseIds.includes(c.clauseId))
    : g.cite === "clause-excluded" ? bundle.clauses.filter((c) => c.kind === "EXCLUDED") : [];

  const submit = async () => {
    await tx.run({ spec: calls.fileChallenge(bundle.claim.claimId, ground, explanation.trim(), citation), claimId: bundle.claim.claimId,
      reread: () => (reader ? loadClaimBundle(reader, bundle.claim.claimId) : Promise.reject(new Error("no reader"))), onConfirmed: onDone });
  };
  const canSubmit = problems.length === 0 && stateItems.every((i) => i.status === "ok") && wallet.ready;

  if (bundle.claim.status !== "DECIDED") return null;
  return (
    <section className="challenge-plate" aria-labelledby="fc-h">
      <h2 id="fc-h">File an Application Challenge</h2>
      <p>An <strong>Application Challenge</strong> contests a material error in this CLAUSE adjudication under the frozen terms and the frozen evidence. It is <strong>not</strong> a GenLayer Protocol Appeal, cannot add new evidence, and there is <strong>one</strong> per claim.</p>
      {a ? <p className="small">Window closes: <strong>{formatUtc(a.challengeWindowClosesAt)}</strong> (protocol time).</p> : null}
      <Checklist items={stateItems} />
      <div className="field"><label htmlFor="chal-hash">Hash of the adjudication transaction to verify (optional)</label><input id="chal-hash" value={fin.manual} onChange={(e) => fin.setManual(e.target.value)} placeholder="0x… (only if this browser did not send it)" spellCheck={false} /><button type="button" className="btn small secondary" onClick={fin.recheck}>Re-check finality</button></div>
      {!review ? (
        <form onSubmit={(e) => { e.preventDefault(); if (problems.length === 0) setReview(true); }}>
          <div className="field">
            <label htmlFor="ground">Ground</label>
            <select id="ground" value={ground} onChange={(e) => { setGround(e.target.value as ChallengeGround); setEvidenceIds([]); setClauseIds([]); }}>
              {Object.entries(GROUNDS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
            <p className="hint">{g.blurb} <strong>{g.how}.</strong></p>
          </div>
          {g.cite === "evidence" ? (
            <fieldset><legend>Cite evidence (frozen records only)</legend>
              {candidates.length === 0 ? <p className="muted">No frozen evidence qualifies for this ground.</p> : candidates.map((e) => (
                <label key={e.evidenceId} className="check"><input type="checkbox" checked={evidenceIds.includes(e.evidenceId)}
                  onChange={(ev) => setEvidenceIds(ev.target.checked ? [...evidenceIds, e.evidenceId] : evidenceIds.filter((x) => x !== e.evidenceId))} />
                  <span>#{e.evidenceId} · {e.host} · {e.retrievalStatus || "pending"}</span></label>
              ))}
            </fieldset>
          ) : null}
          {g.cite.startsWith("clause") ? (
            <fieldset><legend>Cite clause</legend>
              {clauseCandidates.map((c) => (
                <label key={c.clauseId} className="check"><input type="checkbox" checked={clauseIds.includes(c.clauseId)}
                  onChange={(ev) => setClauseIds(ev.target.checked ? [...clauseIds, c.clauseId] : clauseIds.filter((x) => x !== c.clauseId))} />
                  <span><b className="mono">{c.clauseId}</b> {c.text}</span></label>
              ))}
            </fieldset>
          ) : null}
          {g.cite === "constitution" ? (
            <div className="field"><label htmlFor="cid">Terms version id you believe should govern</label>
              <input id="cid" inputMode="numeric" value={constitutionId} onChange={(e) => setConstitutionId(e.target.value)} />
              <p className="hint">This claim is governed by terms id {bundle.claim.constitutionId} (frozen at issuance).</p></div>
          ) : null}
          {g.cite === "timestamp" ? (
            <div className="field"><label htmlFor="ts">Timestamp you say was misread</label>
              <select id="ts" value={tsField} onChange={(e) => setTsField(e.target.value)}>{TIMESTAMPS.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
          ) : null}
          <div className="field"><label htmlFor="why">Explanation (max 1,000 characters)</label>
            <textarea id="why" value={explanation} maxLength={1000} onChange={(e) => setExplanation(e.target.value)} />
            <p className="hint">{explanation.length}/1000. Treated as untrusted text: it cannot change an amount, a recipient or the frozen terms.</p></div>
          {problems.length > 0 && explanation !== "" ? <ul>{problems.map((p) => <li key={p} className="err">{p}</li>)}</ul> : null}
          <button type="submit" className="btn plum" disabled={problems.length > 0}>Review challenge</button>
        </form>
      ) : (
        <div>
          <h3>Review before submitting</h3>
          <dl className="grid auto">
            <div className="kv"><dt>Ground</dt><dd>{g.label}</dd></div>
            <div className="kv"><dt>Citation</dt><dd className="wrap">{JSON.stringify(citation)}</dd></div>
            <div className="kv"><dt>Explanation</dt><dd className="wrap">{explanation}</dd></div>
          </dl>
          <p className="banner bad"><strong>Irreversible.</strong> This claim gets exactly one Application Challenge, even if it is later found invalid.</p>
          <div className="row">
            <button type="button" className="btn plum" disabled={!canSubmit} onClick={() => void submit()}>Submit Application Challenge</button>
            <button type="button" className="btn secondary" onClick={() => setReview(false)}>Back</button>
          </div>
          {!canSubmit ? <p className="small"><strong>Why disabled?</strong> {!wallet.ready ? "Connect a wallet on StudioNet." : stateItems.find((i) => i.status !== "ok")?.detail ?? problems[0]}</p> : null}
        </div>
      )}
    </section>
  );
}

/** Resolve / remand / lapse steps for an open Application Challenge (permissionless, finality-gated). */
export function ChallengeResolution({ bundle, onDone }: { bundle: ClaimBundle; onDone: () => void }) {
  const ch = bundle.challenge;
  if (!ch || bundle.claim.status !== "CHALLENGED") return null;
  const id = bundle.claim.claimId;
  return (
    <div className="stack">
      {ch.status === "OPEN" ? <GatedActionButton action="resolve_challenge" bundle={bundle} spec={calls.resolveChallenge(id)} onDone={onDone} variant="plum"
        description="Has the contract review this Application Challenge (deterministic checks first; validators only where interpretation is needed)." /> : null}
      {ch.status === "REMAND_PENDING" ? <GatedActionButton action="execute_remand" bundle={bundle} spec={calls.executeRemand(id)} onDone={onDone} variant="plum"
        description="Runs the single bounded re-adjudication ordered by the remand. Its result is final." /> : null}
      <GatedActionButton action="lapse_challenge" bundle={bundle} spec={calls.lapseChallenge(id)} onDone={onDone} variant="plum"
        description="If the challenge could not be resolved within its window, lapse it so the original decision stands and the claim can proceed." />
    </div>
  );
}
