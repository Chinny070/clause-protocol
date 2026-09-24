import type { Adjudication, ResolutionReceipt } from "../contract/types";
import { formatGen, formatUtc } from "../domain/format";
import { OUTCOME } from "./kit";
import { Copyable, FrozenStamp } from "./kit";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="rrow"><span>{k}</span><span>{v}</span></div>;
}

function AdjBlock({ a, title }: { a: Adjudication; title: string }) {
  return (
    <>
      <h3>{title}{a.superseded ? " · SUPERSEDED" : ""}</h3>
      <Row k="Outcome" v={OUTCOME[a.outcome]?.text ?? a.outcome} />
      <Row k="Product match" v={a.productMatch} />
      <Row k="Warranty version" v={a.warrantyVersionMatch} />
      <Row k="Coverage window" v={a.coverageWindow} />
      <Row k="Evidence" v={a.evidenceSufficiency} />
      <Row k="Source authority" v={a.sourceAuthority} />
      <Row k="Covered clauses" v={a.coveredClauseIds.join(", ") || "none"} />
      <Row k="Exclusions" v={a.exclusionClauseIds.join(", ") || "none"} />
      <Row k="Evidence relied on" v={a.evidenceIdsRelied.map((i) => `#${i}`).join(", ") || "none"} />
      <Row k="Decided" v={formatUtc(a.adjudicatedAt)} />
      <Row k="Path" v={a.decisionPath} />
    </>
  );
}

/** Public Resolution Receipt: thermal-receipt / inspection-certificate treatment. Readable with no wallet connected. */
export function ReceiptView({ r }: { r: ResolutionReceipt }) {
  const f = r.finalDecision;
  const final = r.correctedAdjudication ?? r.originalAdjudication;
  return (
    <article className="receipt print" aria-label={`Resolution receipt for claim ${r.claimId}`}>
      <FrozenStamp text="Frozen terms" />
      <h2 style={{ marginTop: 0 }}>CLAUSE · Resolution Receipt</h2>
      <Row k="Claim №" v={String(r.claimId).padStart(6, "0")} />
      <Row k="Status" v={r.claimStatus} />

      <h3>Warranty</h3>
      <Row k="Passport №" v={String(r.warranty.warrantyId).padStart(5, "0")} />
      <Row k="Product / model" v={r.warranty.productModelId} />
      <Row k="Coverage" v={`${formatUtc(r.warranty.coverageStart).slice(0, 10)} → ${formatUtc(r.warranty.coverageEnd).slice(0, 10)}`} />
      <Row k="Holder" v={<span className="mono">{r.warranty.holder}</span>} />
      <Row k="Manufacturer" v={<span className="mono">{r.warranty.manufacturer}</span>} />
      <Row k="Maximum remedy" v={`${formatGen(r.warranty.maxDeterministicRemedy)} GEN`} />
      <Row k="Terms version" v={r.warranty.constitutionVersion} />
      <div style={{ margin: "6px 0" }}>Constitution fingerprint:<br /><Copyable value={r.warranty.constitutionFingerprint} label="constitution fingerprint" /></div>

      <h3>Claim</h3>
      <Row k="Targeted clauses" v={r.claim.targetedClauseIds.join(", ")} />
      <Row k="Filed (protocol time)" v={formatUtc(r.claim.filedAt)} />
      <Row k="Manufacturer response" v={r.claim.manufacturerResponse || "none (silence = dispute)"} />
      <Row k="Response (protocol time)" v={r.claim.respondedAt ? formatUtc(r.claim.respondedAt) : "n/a"} />
      <Row k="Evidence frozen" v={r.claim.evidenceFrozenAt ? formatUtc(r.claim.evidenceFrozenAt) : "not yet"} />

      <h3>Evidence ({r.evidence.length} eligible{r.ineligibleEvidenceCount ? `, ${r.ineligibleEvidenceCount} ineligible` : ""})</h3>
      {r.evidence.length === 0 ? <div>none</div> : r.evidence.map((e) => (
        <div key={e.evidenceId} style={{ marginBottom: 6 }}>
          <Row k={`#${e.evidenceId} ${e.host}`} v={e.retrievalStatus || "pending"} />
          <div className="wrap" style={{ color: "#555" }}>fp {e.fingerprint}</div>
        </div>
      ))}

      {r.originalAdjudication ? <AdjBlock a={r.originalAdjudication} title="Original adjudication" /> : <><h3>Adjudication</h3><div>none (no-contest or not yet adjudicated)</div></>}
      {r.challenge ? (
        <>
          <h3>Application Challenge</h3>
          <Row k="Ground" v={r.challenge.ground} />
          <Row k="Filed" v={formatUtc(r.challenge.filedAt)} />
          <Row k="Result" v={r.challenge.result || r.challenge.status} />
          <Row k="Resolved by" v={r.challenge.resolutionPath || "pending"} />
        </>
      ) : null}
      {r.correctedAdjudication ? <AdjBlock a={r.correctedAdjudication} title="Corrected adjudication" /> : null}

      <h3>Final application decision</h3>
      {f ? (
        <>
          <Row k="Outcome" v={OUTCOME[f.finalOutcome]?.text ?? f.finalOutcome} />
          <Row k="Decision source" v={f.source} />
          <Row k="Finalized" v={formatUtc(f.finalizedAt)} />
          <div className="total"><Row k="REMEDY" v={`${formatGen(f.remedyAmount)} GEN`} /></div>
          <Row k="Remedy rule" v={`${f.remedyKind} (${f.remedyBasis})`} />
          <Row k="Settled" v={f.settledAt ? `${formatGen(f.settledAmount)} GEN · ${formatUtc(f.settledAt)}${f.capped ? " · capped" : ""}` : "not yet"} />
          <Row k="Withdrawn" v={f.withdrawnAt ? `${formatGen(f.withdrawnAmount)} GEN · ${formatUtc(f.withdrawnAt)}` : "not yet"} />
          <Row k="Still claimable" v={`${formatGen(f.claimable)} GEN`} />
        </>
      ) : <div>Not finalized yet{final ? ` (latest decision: ${OUTCOME[final.outcome]?.text ?? final.outcome})` : ""}.</div>}
      <div className="barcode" aria-hidden="true" />
      <p style={{ color: "#555", marginTop: 10 }}>Application finality is not GenLayer Protocol Finality: verify the transactions before relying on this receipt for settlement. Read from the CLAUSE contract; no server involved.</p>
    </article>
  );
}
