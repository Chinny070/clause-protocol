import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useClause, useWallet } from "../app/context";
import { loadClaimBundle, type ClaimBundle } from "../app/data";
import { useAsync } from "../app/useAsync";
import { calls } from "../contract/calls";
import type { ClauseReader } from "../contract/reader";
import { previewSourceEligibility, isRenderedCategory } from "../domain/constitutionDraft";
import { formatUtc, sameAddress } from "../domain/format";
import { buildTimeline, stageReached } from "../domain/timeline";
import { GatedActionButton, TxButton } from "../ui/actions";
import { ChallengeHistory, ChallengeResolution, FileChallengeForm } from "../ui/challenge";
import { AdjudicationView, FinalDecisionView } from "../ui/decision";
import { EvidenceLocker } from "../ui/evidence";
import { Badge, ClaimStatusBadge, Seal, StageStrip, Sticker, Timeline } from "../ui/kit";
import { AsyncBoundary, NeedsContract, NotFoundBox, idParam } from "./common";

function SubmitEvidence({ b, reader, onDone }: { b: ClaimBundle; reader: ClauseReader; onDone: () => void }) {
  const wallet = useWallet();
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState(b.constitution?.acceptableEvidenceCategories[0] ?? "");
  const eligibleUsed = b.evidence.filter((e) => e.eligibility === "ELIGIBLE").length;
  const policy = b.constitution?.sourceEligibilityPolicy ?? "";
  const preview = url.trim() === "" ? null : previewSourceEligibility(url.trim(), policy);
  const party = !!wallet.address && (sameAddress(wallet.address, b.claim.holder) || sameAddress(wallet.address, b.claim.manufacturer));
  const full = preview?.eligible && eligibleUsed >= 10;
  const reason = !party ? "Only the holder or manufacturer of this claim can submit evidence." : url.trim() === "" ? "Enter an evidence URL." : full ? "This claim already has the maximum of 10 adjudicable evidence records." : null;
  return (
    <section className="plate" aria-labelledby="se-h">
      <h2 id="se-h">Submit evidence</h2>
      <p className="hint">Evidence can be added until it is frozen. Only https sources on the frozen source policy (<code>{policy}</code>) are eligible; an ineligible URL is recorded but never used. Maximum 10 adjudicable records per claim; slots are first-come. Nothing is retrieved until the evidence is frozen.</p>
      <div className="field"><label htmlFor="ev-url">Evidence URL</label><input id="ev-url" value={url} onChange={(e) => setUrl(e.target.value)} inputMode="url" placeholder="https://…" spellCheck={false} /></div>
      {preview ? <p className={preview.eligible ? "small" : "err"} role="status">{preview.eligible ? "✔ Eligible under the frozen policy (preview). " : "✖ "}{preview.reason}{preview.eligible ? "" : " It would be recorded as ineligible and can never reach adjudication."}</p> : null}
      <div className="field"><label htmlFor="ev-cat">Category</label>
        <select id="ev-cat" value={category} onChange={(e) => setCategory(e.target.value)}>{(b.constitution?.acceptableEvidenceCategories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}</select>
        {isRenderedCategory(category) ? <p className="hint">This category is retrieved with a browser render (a StudioNet-gated capability).</p> : null}</div>
      <p className="small">Slots used: <strong>{eligibleUsed} / 10</strong></p>
      <TxButton spec={calls.submitEvidence(b.claim.claimId, url.trim() || "https://x", category || "x")} claimId={b.claim.claimId} disabledReason={reason ?? (wallet.ready ? null : "Connect a wallet on StudioNet.")}
        reread={() => loadClaimBundle(reader, b.claim.claimId)} onDone={() => { setUrl(""); onDone(); }} description="Records this URL on the claim. If eligible it permanently uses one of the 10 evidence slots." />
    </section>
  );
}

function Body({ reader, id }: { reader: ClauseReader; id: number }) {
  const wallet = useWallet();
  const { protocolNow } = useClause();
  const q = useAsync(() => loadClaimBundle(reader, id), [reader, id]);
  const b = q.data;
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading claim">
      {!b ? <NotFoundBox what="Claim" /> : (() => {
        const c = b.claim;
        const now = protocolNow();
        const isMfr = sameAddress(wallet.address, c.manufacturer);
        const isHolder = sameAddress(wallet.address, c.holder);
        const responseOpen = c.status === "RESPONSE_WINDOW" && now <= c.responseDeadline;
        const evidencePhase = c.status === "DISPUTED" && c.evidenceFrozenAt === 0;
        const timeline = buildTimeline({ passport: b.passport, claim: c, evidence: b.evidence, adjudication: b.adjudication, challenge: b.challenge, correctedAdjudication: b.corrected, finalDecision: b.finalDecision, challengeWindowClosesAt: b.adjudication?.challengeWindowClosesAt ?? 0 });
        const stage = stageReached(c.status, !!b.challenge);
        return (
          <div className="stack">
            <section className="plate metal" aria-labelledby="claim-h">
              <div className="row" style={{ justifyContent: "space-between" }}><h1 id="claim-h" style={{ fontSize: "1.8rem", margin: 0 }}>Claim № {String(c.claimId).padStart(6, "0")}</h1><ClaimStatusBadge status={c.status} /></div>
              <p><Link to={`/passport/${c.warrantyId}`}>Warranty Passport {c.warrantyId}</Link> · {b.passport?.productModelId} · terms <span className="mono wrap">{c.constitutionFingerprint.slice(0, 16)}…</span></p>
              <StageStrip reached={stage} />
              <div className="grid auto" style={{ marginTop: 14 }}>
                <div className="kv"><dt>Filed</dt><dd><Seal at={c.filedAt} provenance="protocol" /></dd></div>
                <div className="kv"><dt>Failure date (claimant-asserted)</dt><dd><Seal at={c.failureAssertedAt} provenance="asserted" /></dd></div>
                <div className="kv"><dt>Manufacturer response deadline</dt><dd><Seal at={c.responseDeadline} provenance="deadline" /></dd></div>
                <div className="kv"><dt>Targeted clauses</dt><dd>{c.targetedClauseIds.map((id2) => { const cl = b.clauses.find((x) => x.clauseId === id2); return <Sticker key={id2} id={id2} text={cl?.text} kind="COVERED" />; })}</dd></div>
              </div>
              <p className="row">{b.finalDecision ? <Link className="btn small" to={`/receipt/${c.claimId}`}>Resolution Receipt</Link> : <Badge tone="neutral" glyph="◌">Receipt available once finalized</Badge>}<button type="button" className="btn small secondary" onClick={q.reload}>Reload from contract</button></p>
            </section>

            {responseOpen && isMfr ? (
              <section className="plate petrol" aria-labelledby="resp-h">
                <h2 id="resp-h" style={{ color: "#fff" }}>Respond to this claim</h2>
                <p>Respond by <strong>{formatUtc(c.responseDeadline)}</strong>. Silence counts as a dispute. Accepting (no contest) skips adjudication and pays the frozen no-contest remedy after finality.</p>
                <div className="row">
                  <TxButton spec={calls.respondToClaim(id, "ACCEPT")} claimId={id} reread={() => loadClaimBundle(reader, id)} onDone={q.reload} description="Accepts the claim without contest. The frozen no-contest remedy row then applies. This cannot be undone." />
                  <TxButton spec={calls.respondToClaim(id, "DISPUTE")} claimId={id} variant="secondary" reread={() => loadClaimBundle(reader, id)} onDone={q.reload} description="Disputes the claim so evidence can be submitted and adjudicated. This cannot be undone." />
                </div>
              </section>
            ) : null}
            {c.status === "RESPONSE_WINDOW" && !isMfr ? <p className="banner" role="status">Waiting for the manufacturer to respond by {formatUtc(c.responseDeadline)}. Evidence submission opens when the manufacturer disputes, or when this window closes (silence counts as a dispute).</p> : null}

            <EvidenceLocker evidence={b.evidence} constitution={b.constitution} submitterLabel={(a) => (sameAddress(a, c.holder) ? `${a} (holder)` : sameAddress(a, c.manufacturer) ? `${a} (manufacturer)` : a)} />
            {evidencePhase && (isHolder || isMfr) ? <SubmitEvidence b={b} reader={reader} onDone={q.reload} /> : null}

            {(c.status === "DISPUTED" || (c.status === "RESPONSE_WINDOW" && now > c.responseDeadline)) ? (
              <GatedActionButton action="freeze_evidence" bundle={b} spec={calls.freezeEvidence(id)} onDone={q.reload}
                description="Closes evidence submission, retrieves every eligible source through validator consensus and freezes the results. Permissionless." />
            ) : null}
            {c.status === "EVIDENCE_FROZEN" ? (
              <GatedActionButton action="adjudicate_claim" bundle={b} spec={calls.adjudicateClaim(id)} onDone={q.reload}
                description="Asks GenLayer validators to decide the structured findings from the frozen evidence. The outcome and remedy are derived by plain code. Permissionless." />
            ) : null}

            {b.adjudication ? <AdjudicationView a={b.adjudication} clauses={b.clauses} title="Original adjudication" /> : null}
            {b.challenge ? <ChallengeHistory challenge={b.challenge} /> : null}
            {b.corrected ? <AdjudicationView a={b.corrected} clauses={b.clauses} title="Corrected adjudication" /> : null}
            {c.status === "DECIDED" && (isHolder || isMfr) ? <FileChallengeForm bundle={b} onDone={q.reload} /> : null}
            {c.status === "DECIDED" && !isHolder && !isMfr ? <p className="banner" role="note">The holder or the manufacturer may file one Application Challenge until {formatUtc(b.adjudication?.challengeWindowClosesAt ?? 0)}.</p> : null}
            <ChallengeResolution bundle={b} onDone={q.reload} />

            {(c.status === "ACCEPTED" || c.status === "DECIDED" || c.status === "CHALLENGE_RESOLVED") ? (
              <GatedActionButton action="finalize_claim" bundle={b} spec={calls.finalizeClaim(id)} onDone={q.reload}
                description="Records the final application decision and the deterministic remedy. Moves no money. This is application finality, not GenLayer Protocol Finality." />
            ) : null}
            {c.status === "FINAL" ? (
              <GatedActionButton action="settle_claim" bundle={b} spec={calls.settleClaim(id)} onDone={q.reload}
                description="Authorizes settlement: converts the deterministic remedy into a claimable amount (bounded by the warranty maximum). No GEN leaves the contract yet." />
            ) : null}
            {b.finalDecision ? <FinalDecisionView f={b.finalDecision} /> : null}
            {c.status === "SETTLED" && b.finalDecision && b.finalDecision.claimable > 0n ? (
              <GatedActionButton action="withdraw_settlement" bundle={b} spec={calls.withdrawSettlement(id)} onDone={q.reload}
                description="Withdraws the claimable GEN to the recorded recipient (the warranty holder). Pull payment: only the recipient can call it, and only once." />
            ) : null}

            <section className="plate" aria-labelledby="tl-h"><h2 id="tl-h">Diagnostic timeline</h2><p className="hint">Each timestamp is tagged: protocol time (on-chain), claimant-asserted (unverified), or a derived deadline.</p><Timeline events={timeline} /></section>
          </div>
        );
      })()}
    </AsyncBoundary>
  );
}

export function ClaimPage() {
  const { id } = useParams();
  const n = idParam(id);
  if (n === null) return <NotFoundBox what="Claim" />;
  return <NeedsContract what={`Claim ${n}`}>{(reader) => <Body reader={reader} id={n} />}</NeedsContract>;
}
