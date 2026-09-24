import { Link } from "react-router-dom";
import type { Clause, Constitution, Passport, Program, Reservation } from "../contract/types";
import { formatDate, formatGen, formatUtc } from "../domain/format";
import { Badge, Copyable, FrozenStamp, PassportStatusBadge, Seal, Sticker } from "./kit";

/** The Warranty Passport: a physical product-registration card, not a dashboard tile. */
export function PassportCard({ passport, program, constitution, claimCount, reservation, link = true, animate = false }: {
  passport: Passport; program?: Program | null; constitution?: Constitution | null; claimCount?: number; reservation?: Reservation | null; link?: boolean; animate?: boolean;
}) {
  const clauseCount = constitution ? constitution.coveredClauseIds.length + constitution.excludedClauseIds.length : undefined;
  return (
    <article className="passport" aria-label={`Warranty passport ${passport.warrantyId}`}>
      <header className="passport-head">
        <h3>Warranty Passport № {String(passport.warrantyId).padStart(5, "0")}</h3>
        <span className="row"><PassportStatusBadge status={passport.status} /><FrozenStamp animate={animate} /></span>
      </header>
      <div className="passport-body">
        <dl className="kv"><dt>Product / model</dt><dd>{passport.productModelId}</dd></dl>
        <dl className="kv"><dt>Warranty program</dt><dd>{program?.name ?? `Program ${passport.programId}`}</dd></dl>
        <dl className="kv"><dt>Coverage window</dt><dd>{formatDate(passport.coverageStart)} → {formatDate(passport.coverageEnd)}</dd></dl>
        <dl className="kv"><dt>Maximum remedy</dt><dd>{formatGen(passport.maxDeterministicRemedy)} GEN</dd></dl>
        <dl className="kv"><dt>Manufacturer</dt><dd className="mono wrap">{passport.manufacturer}</dd></dl>
        <dl className="kv"><dt>Holder</dt><dd className="mono wrap">{passport.holder}</dd></dl>
        <dl className="kv"><dt>Terms version</dt><dd>{passport.constitutionVersion}</dd></dl>
        <dl className="kv"><dt>Clauses</dt><dd>{clauseCount ?? "—"}</dd></dl>
        <dl className="kv"><dt>Claim history</dt><dd>{claimCount === undefined ? "—" : claimCount === 0 ? "No claims" : `${claimCount} claim${claimCount === 1 ? "" : "s"}`}</dd></dl>
        <dl className="kv"><dt>Reservation</dt><dd>{reservation ? <>{reservation.status} · {formatGen(reservation.amount)} GEN still reserved</> : "—"}</dd></dl>
        <dl className="kv"><dt>Registered</dt><dd><Seal at={passport.registeredAt} provenance="protocol" label="Protocol time" /></dd></dl>
        {passport.status === "CANCELLED" ? (
          <dl className="kv"><dt>Cancellation</dt><dd><Badge tone="bad" glyph="✖">Cancelled</Badge>{reservation && reservation.releasedAt ? <> capacity released {formatUtc(reservation.releasedAt)}</> : null}</dd></dl>
        ) : null}
      </div>
      <div className="passport-foot">
        <div>FINGERPRINT (frozen terms):</div>
        <div className="wrap"><Copyable value={passport.constitutionFingerprint} label="constitution fingerprint" /></div>
        {link ? <div style={{ marginTop: 8 }}><Link className="btn small" to={`/passport/${passport.warrantyId}`}>Open passport</Link></div> : null}
      </div>
    </article>
  );
}

/** Frozen terms display: clauses, exclusions, source policy, deadlines and the remedy table. */
export function FrozenTerms({ constitution, clauses }: { constitution: Constitution; clauses: Clause[] }) {
  const covered = clauses.filter((c) => c.kind === "COVERED");
  const excluded = clauses.filter((c) => c.kind === "EXCLUDED");
  const day = 86400;
  return (
    <section className="plate metal" aria-labelledby="terms-h">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 id="terms-h">Frozen terms · {constitution.version}</h2>
        <FrozenStamp text={constitution.isFrozen ? "Frozen terms" : "Not yet frozen"} />
      </div>
      <p className="frozen-banner">This version cannot be silently rewritten after issuance. Any change is a new version with a new fingerprint.</p>
      <dl className="kv" style={{ margin: "12px 0" }}><dt>Constitution fingerprint</dt><dd><Copyable value={constitution.fingerprint} label="fingerprint" /></dd></dl>
      <p><strong>Product scope:</strong> {constitution.productScope}<br /><strong>Coverage:</strong> {constitution.coverageCalc}</p>
      <h3>Covered clauses</h3>
      <div>{covered.map((c) => <Sticker key={c.clauseId} id={c.clauseId} text={c.text} kind="COVERED" />)}</div>
      <h3>Exclusions</h3>
      <div>{excluded.length ? excluded.map((c) => <Sticker key={c.clauseId} id={c.clauseId} text={c.text} kind="EXCLUDED" />) : <span className="muted">No exclusions.</span>}</div>
      <div className="perf" />
      <div className="grid two">
        <dl className="kv"><dt>Evidence source policy</dt><dd className="mono wrap">{constitution.sourceEligibilityPolicy}</dd><dd className="hint">Only https sources on these hosts are eligible. <code>*.host</code> matches subdomains, not the bare domain.</dd></dl>
        <dl className="kv"><dt>Evidence categories</dt><dd>{constitution.acceptableEvidenceCategories.join(", ")}</dd></dl>
        <dl className="kv"><dt>Claim deadline</dt><dd>{constitution.claimDeadlineS / day} days after coverage ends</dd></dl>
        <dl className="kv"><dt>Manufacturer response period</dt><dd>{constitution.manufacturerResponsePeriodS / day} days</dd></dl>
        <dl className="kv"><dt>Application Challenge</dt><dd>{constitution.challengeDepth >= 1 ? `One challenge, ${constitution.challengeWindowS / day}-day window` : "Disabled by these terms"}</dd></dl>
        <dl className="kv"><dt>If evidence is insufficient</dt><dd>{constitution.insufficientEvidenceBehavior.replace(/_/g, " ")}</dd></dl>
        <dl className="kv"><dt>If evidence is unavailable</dt><dd>{constitution.unavailableEvidenceBehavior.replace(/_/g, " ")}</dd></dl>
        <dl className="kv"><dt>Cancellation rules</dt><dd>{constitution.expiryCancellationRules}</dd></dl>
      </div>
      <h3>Precommitted remedy table</h3>
      <table className="plain">
        <thead><tr><th>Outcome</th><th>Clause</th><th>Remedy</th></tr></thead>
        <tbody>
          {constitution.remedyTable.map((r) => (
            <tr key={`${r.outcome}|${r.clause_id}`}>
              <td data-th="Outcome">{r.outcome.replace(/_/g, " ")}</td>
              <td data-th="Clause">{r.clause_id || "any"}</td>
              <td data-th="Remedy">{r.remedy_kind === "NONE" ? "No payment" : r.remedy_kind === "FULL_REFUND" ? "Full refund (warranty maximum)" : r.remedy_kind === "PARTIAL_BPS" ? `${Number(r.remedy_value) / 100}% of maximum` : `Repair credit ${formatGen(r.remedy_value)} GEN (capped at maximum)`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">The remedy is chosen only from this table, by plain code. No validator or model ever chooses an amount.</p>
    </section>
  );
}
