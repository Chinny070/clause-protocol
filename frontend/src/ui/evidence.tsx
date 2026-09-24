import type { Constitution, Evidence } from "../contract/types";
import { formatUtc } from "../domain/format";
import { Badge, Seal } from "./kit";

const MAX_EVIDENCE = 10;

export function evidenceState(e: Evidence): { tone: "ok" | "bad" | "wait" | "neutral"; glyph: string; text: string; explain: string; cls: string } {
  if (e.eligibility === "INELIGIBLE") return { tone: "bad", glyph: "⊘", text: "Ineligible source", cls: "inelig",
    explain: "This host or scheme is not permitted by the frozen source policy. It was recorded but never retrieved and can never reach adjudication." };
  switch (e.retrievalStatus) {
    case "AVAILABLE": return { tone: "ok", glyph: "✔", text: "Available", cls: "", explain: "Retrieved through validator consensus and frozen." };
    case "FETCH_FAILED": case "RENDER_FAILED": case "UNAVAILABLE":
      return { tone: "wait", glyph: "◌", text: e.retrievalStatus === "RENDER_FAILED" ? "Render failed" : "Fetch failed", cls: "bad",
        explain: "The source could not be retrieved. This does NOT mean the claim is false: unavailable evidence is not treated as proof against either party." };
    case "INSUFFICIENT": return { tone: "wait", glyph: "◐", text: "Insufficient content", cls: "bad", explain: "The page was reachable but held no usable content. It is not treated as proof against either party." };
    default: return { tone: "neutral", glyph: "…", text: "Awaiting retrieval", cls: "", explain: "Retrieval happens once, when the evidence is frozen." };
  }
}

/** The Evidence Locker: one inspection strip per EvidenceRecord. */
export function EvidenceLocker({ evidence, constitution, submitterLabel }: { evidence: Evidence[]; constitution?: Constitution | null; submitterLabel?: (addr: string) => string }) {
  const used = evidence.filter((e) => e.eligibility === "ELIGIBLE").length;
  return (
    <section className="plate plastic" aria-labelledby="locker-h">
      <h2 id="locker-h">Evidence Locker</h2>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>Adjudicable evidence slots used: <strong>{used} / {MAX_EVIDENCE}</strong></span>
        <span className="slots" aria-hidden="true">{Array.from({ length: MAX_EVIDENCE }, (_, i) => <span key={i} className={`slot${i < used ? " used" : ""}`} />)}</span>
      </div>
      <p className="hint">Maximum {MAX_EVIDENCE} adjudicable evidence records per claim. Slots are first-come and cannot be freed; ineligible records do not use a slot.</p>
      <div className="perf" />
      {evidence.length === 0 ? <p className="muted">No evidence submitted yet.</p> : null}
      {evidence.map((e) => {
        const st = evidenceState(e);
        const frozen = e.frozenAt > 0;
        return (
          <article key={e.evidenceId} className={`strip ${st.cls}`} aria-label={`Evidence ${e.evidenceId}`}>
            <span className="scan" aria-hidden="true" />
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>Evidence #{e.evidenceId}</strong>
              <span className="row">
                <Badge tone={st.tone} glyph={st.glyph}>{st.text}</Badge>
                <Badge tone={frozen ? "final" : "neutral"} glyph={frozen ? "❄" : "○"}>{frozen ? "Frozen" : "Not frozen"}</Badge>
              </span>
            </div>
            <p className="wrap small" style={{ margin: "6px 0" }}><span className="mono">{e.originalUrl}</span></p>
            <p className="small">{st.explain}</p>
            <div className="grid auto small">
              <div className="kv"><dt>Source host</dt><dd>{e.host}</dd></div>
              <div className="kv"><dt>Category</dt><dd>{e.category}</dd></div>
              <div className="kv"><dt>Retrieval method</dt><dd>{e.retrievalMethod === "RENDER" ? "Browser render" : "Static fetch"}</dd></div>
              <div className="kv"><dt>Submitted by</dt><dd className="mono wrap">{submitterLabel ? submitterLabel(e.submitter) : e.submitter}</dd></div>
              <div className="kv"><dt>Submitted</dt><dd><Seal at={e.submittedAt} provenance="protocol" /></dd></div>
              <div className="kv"><dt>{frozen ? "Retrieved / frozen" : "Retrieved"}</dt><dd>{e.retrievedAt ? <Seal at={e.retrievedAt} provenance="protocol" /> : "Not yet"}</dd></div>
            </div>
            <dl className="kv small"><dt>Fingerprint</dt><dd className="mono wrap">{e.fingerprint || "not yet computed"}</dd></dl>
            {e.extractedContent ? <details><summary>Frozen extracted content (bounded)</summary><pre className="diag">{e.extractedContent}</pre></details> : null}
          </article>
        );
      })}
      {constitution ? <p className="hint">Source policy: <code>{constitution.sourceEligibilityPolicy}</code>. Frozen at {formatUtc(constitution.frozenAt)}.</p> : null}
    </section>
  );
}
