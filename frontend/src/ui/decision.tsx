import { Link } from "react-router-dom";
import type { Adjudication, Clause, FinalDecision } from "../contract/types";
import { formatGen } from "../domain/format";
import { Badge, OUTCOME, OutcomeBadge, Seal, Sticker } from "./kit";

export function TriBadge({ v }: { v: "PASS" | "FAIL" | "UNCLEAR" }) {
  return v === "PASS" ? <Badge tone="ok" glyph="✔">Pass</Badge> : v === "FAIL" ? <Badge tone="bad" glyph="✖">Fail</Badge> : <Badge tone="wait" glyph="?">Unclear</Badge>;
}

const PATH: Record<string, string> = {
  SEMANTIC: "GenLayer validators interpreted the frozen evidence; only structured findings were compared for agreement.",
  DETERMINISTIC_PREDICATE: "Decided by plain code from frozen protocol facts (warranty version or coverage window). No model was consulted.",
  DETERMINISTIC_NO_ADMISSIBLE_EVIDENCE: "Decided by plain code: no eligible evidence existed. No model was consulted.",
  DETERMINISTIC_EVIDENCE_UNAVAILABLE: "Decided by plain code: eligible evidence could not be retrieved. No model was consulted.",
  CHALLENGE_CORRECTION: "Corrected after an Application Challenge confirmed a material error; the outcome was re-derived by plain code.",
  REMAND_CORRECTION: "Re-adjudicated once after an Application Challenge remand. This result is final.",
};

/** Renders the structured decision, not a paragraph: every frozen schema field is shown as its own row. */
export function AdjudicationView({ a, clauses, title = "GenLayer adjudication" }: { a: Adjudication; clauses: Clause[]; title?: string }) {
  const text = (id: string) => clauses.find((c) => c.clauseId === id);
  const o = OUTCOME[a.outcome];
  return (
    <section className="plate" aria-labelledby={`adj-${a.adjudicationId}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 id={`adj-${a.adjudicationId}`}>{title}{a.superseded ? " (superseded)" : ""}</h2>
        <OutcomeBadge outcome={a.outcome} />
      </div>
      {a.superseded ? <p className="banner">This decision was superseded by a correction after an Application Challenge. It is preserved for the record and never deleted.</p> : null}
      <p><strong>{o?.text ?? a.outcome}.</strong> {o?.explain}</p>
      <div className="grid auto">
        <div className="kv"><dt>Product match</dt><dd><TriBadge v={a.productMatch} /></dd></div>
        <div className="kv"><dt>Warranty version match</dt><dd><TriBadge v={a.warrantyVersionMatch} /></dd></div>
        <div className="kv"><dt>Coverage window</dt><dd><TriBadge v={a.coverageWindow} /></dd></div>
        <div className="kv"><dt>Source authority</dt><dd><TriBadge v={a.sourceAuthority} /></dd></div>
        <div className="kv"><dt>Evidence sufficiency</dt><dd>{a.evidenceSufficiency === "SUFFICIENT" ? <Badge tone="ok" glyph="✔">Sufficient</Badge> : a.evidenceSufficiency === "INSUFFICIENT" ? <Badge tone="wait" glyph="◐">Insufficient</Badge> : <Badge tone="wait" glyph="◌">Unavailable</Badge>}</dd></div>
        <div className="kv"><dt>Adjudicated</dt><dd><Seal at={a.adjudicatedAt} provenance="protocol" /></dd></div>
      </div>
      <h3>Covered clauses established</h3>
      <div>{a.coveredClauseIds.length ? a.coveredClauseIds.map((id) => <Sticker key={id} id={id} text={text(id)?.text} kind="COVERED" />) : <span className="muted">None established.</span>}</div>
      <h3>Exclusions established</h3>
      <div>{a.exclusionClauseIds.length ? a.exclusionClauseIds.map((id) => <Sticker key={id} id={id} text={text(id)?.text} kind="EXCLUDED" />) : <span className="muted">None established. An exclusion applies only if evidence affirmatively establishes it.</span>}</div>
      <h3>Evidence</h3>
      <p className="small">Relied on: {a.evidenceIdsRelied.length ? a.evidenceIdsRelied.map((id) => `#${id}`).join(", ") : "none"}. Considered: {a.evidenceIdsConsidered.length ? a.evidenceIdsConsidered.map((id) => `#${id}`).join(", ") : "none"}.</p>
      <h3>Bounded rationale</h3>
      <blockquote className="wrap" style={{ margin: 0, borderLeft: "4px solid var(--copper)", paddingLeft: 12 }}>{a.rationale}</blockquote>
      <p className="hint">Rationale is explanatory text. Validators compare the structured findings above, never the prose.</p>
      <p className="small"><strong>How it was decided:</strong> {PATH[a.decisionPath] ?? a.decisionPath}</p>
    </section>
  );
}

export function FinalDecisionView({ f }: { f: FinalDecision }) {
  const source: Record<string, string> = { NO_CONTEST: "Manufacturer accepted (no contest)", ADJUDICATION: "Original adjudication, no challenge", ADJUDICATION_AFTER_CHALLENGE: "Original adjudication stands after an Application Challenge", CHALLENGE_CORRECTED: "Corrected decision after an Application Challenge" };
  const basis: Record<string, string> = { NO_CONTEST: "No-contest remedy row", COVERED: "COVERED remedy row", POLICY_RULE_FOR_HOLDER: "Frozen policy: evidence gaps rule for the holder", POLICY_BLOCK: "Frozen policy: blocked (no payment)", NON_PAYABLE: "Non-payable outcome" };
  return (
    <section className="plate metal" aria-labelledby="final-h">
      <div className="row" style={{ justifyContent: "space-between" }}><h2 id="final-h">Final application decision</h2><OutcomeBadge outcome={f.finalOutcome} /></div>
      <div className="grid auto">
        <div className="kv"><dt>Source of decision</dt><dd>{source[f.source] ?? f.source}</dd></div>
        <div className="kv"><dt>Remedy basis</dt><dd>{basis[f.remedyBasis] ?? f.remedyBasis}</dd></div>
        <div className="kv"><dt>Deterministic remedy</dt><dd>{f.remedyKind.replace(/_/g, " ")} · {formatGen(f.remedyAmount)} GEN</dd></div>
        <div className="kv"><dt>Settled amount</dt><dd>{f.settledAt ? `${formatGen(f.settledAmount)} GEN` : "Not settled yet"}{f.capped ? " (capped by the warranty maximum)" : ""}</dd></div>
        <div className="kv"><dt>Claimable now</dt><dd>{formatGen(f.claimable)} GEN</dd></div>
        <div className="kv"><dt>Withdrawn</dt><dd>{f.withdrawnAt ? `${formatGen(f.withdrawnAmount)} GEN` : "Not withdrawn"}</dd></div>
        <div className="kv"><dt>Recipient</dt><dd className="mono wrap">{f.recipient}</dd></div>
        <div className="kv"><dt>Finalized</dt><dd><Seal at={f.finalizedAt} provenance="protocol" /></dd></div>
      </div>
      <p className="hint">The remedy comes only from the terms frozen before the dispute. Application finality is separate from GenLayer Protocol Finality, which must be verified before each irreversible step.</p>
      <p><Link className="btn small secondary" to={`/receipt/${f.claimId}`}>Open Resolution Receipt</Link></p>
    </section>
  );
}
