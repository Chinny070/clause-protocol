import { Link, useParams } from "react-router-dom";
import { useClause, useWallet } from "../app/context";
import { loadPassportBundle } from "../app/data";
import { useAsync } from "../app/useAsync";
import { calls } from "../contract/calls";
import { formatUtc, sameAddress } from "../domain/format";
import { TxButton } from "../ui/actions";
import { Badge, ClaimStatusBadge, Gauge, Seal } from "../ui/kit";
import { FrozenTerms, PassportCard } from "../ui/passport";
import { formatGen } from "../domain/format";
import { AsyncBoundary, NeedsContract, NotFoundBox, idParam } from "./common";
import type { ClauseReader } from "../contract/reader";

function Body({ reader, id }: { reader: ClauseReader; id: number }) {
  const wallet = useWallet();
  const { protocolNow } = useClause();
  const q = useAsync(() => loadPassportBundle(reader, id), [reader, id]);
  const b = q.data;
  const isHolder = !!b && sameAddress(wallet.address, b.passport.holder);
  const isMfr = !!b && sameAddress(wallet.address, b.passport.manufacturer);
  const unsettled = b ? b.claims.filter((c) => c.status !== "SETTLED") : [];
  const now = protocolNow();
  const canCancel = !!b && b.passport.status === "ACTIVE" && unsettled.length === 0 && (isHolder || isMfr);
  const graceEnd = b && b.constitution ? b.passport.coverageEnd + b.constitution.claimDeadlineS : 0;
  const canFile = !!b && b.passport.status !== "CANCELLED" && now >= b.passport.coverageStart && (graceEnd === 0 || now <= graceEnd);
  const canRelease = !!b && b.reservation?.status === "ACTIVE" && (b.passport.status === "CANCELLED" || (b.passport.status === "EXPIRED" && now > graceEnd)) && unsettled.length === 0;

  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading passport">
      {!b ? <NotFoundBox what="Warranty passport" /> : (
        <div className="stack">
          <PassportCard passport={b.passport} program={b.program} constitution={b.constitution} claimCount={b.claims.length} reservation={b.reservation} link={false} animate />
          {b.passport.status === "ACTIVE" ? (
            <p className="banner" role="note"><strong>Not irrevocable.</strong> V1 lets the manufacturer or the holder cancel this warranty at any time while no claim is unsettled. A cancelled warranty stops covering new claims and releases its reserved capacity. Cancellation status is always shown on this passport.</p>
          ) : null}
          {b.passport.status === "CANCELLED" ? (
            <p className="banner bad" role="status"><strong>This warranty was cancelled.</strong> {b.reservation?.releasedAt ? <>Its capacity was released at {formatUtc(b.reservation.releasedAt)} (protocol time).</> : null} It no longer covers new claims.</p>
          ) : null}
          {b.constitution ? <FrozenTerms constitution={b.constitution} clauses={b.clauses} /> : null}
          {b.pool && b.program ? (
            <section className="plate petrol" aria-labelledby="cap-h"><h2 id="cap-h" style={{ color: "#fff" }}>Warranty capacity · {b.program.name}</h2>
              <Gauge total={b.pool.totalBalance} reserved={b.pool.reservedLiability} format={(v) => formatGen(v)} />
              <p className="small">This warranty's promise is protected by a reservation of up to {formatGen(b.passport.maxDeterministicRemedy)} GEN. It is a lifetime cap across all claims on this warranty, paid first-settled-first-served. <Link to={`/program/${b.passport.programId}`}>Open pool transparency</Link></p></section>
          ) : null}
          <section className="plate" aria-labelledby="claims-h">
            <h2 id="claims-h">Claim history</h2>
            {b.claims.length === 0 ? <p className="muted">No claims have been filed against this warranty.</p> : (
              <table className="plain"><thead><tr><th>Claim</th><th>Status</th><th>Filed</th><th /></tr></thead><tbody>
                {b.claims.map((c) => <tr key={c.claimId}><td data-th="Claim">#{c.claimId}</td><td data-th="Status"><ClaimStatusBadge status={c.status} /></td><td data-th="Filed"><Seal at={c.filedAt} provenance="protocol" /></td>
                  <td><Link className="btn small secondary" to={`/claim/${c.claimId}`}>Open</Link> {c.status === "FINAL" || c.status === "SETTLED" ? <Link className="btn small secondary" to={`/receipt/${c.claimId}`}>Receipt</Link> : null}</td></tr>)}
              </tbody></table>
            )}
            <div className="row noprint">
              {canFile ? <Link className="btn" to={`/passport/${b.passport.warrantyId}/claim`}>{isHolder ? "File a claim" : "File a claim (holder only)"}</Link> : <Badge tone="neutral" glyph="◌">Claims can no longer be filed</Badge>}
              {b.passport.status === "ACTIVE" ? <TxButton spec={calls.cancelWarranty(id)} variant="warn" onDone={q.reload} reread={() => loadPassportBundle(reader, id)}
                description="Cancels this warranty for good and releases its reserved capacity. This cannot be undone."
                disabledReason={!wallet.ready ? "Connect a wallet." : !canCancel ? (unsettled.length > 0 ? "A claim on this warranty is unsettled." : "Only this warranty's holder or manufacturer can cancel.") : null} /> : null}
              {canRelease ? <TxButton spec={calls.releaseExpiredReservation(id)} variant="secondary" onDone={q.reload} reread={() => loadPassportBundle(reader, id)} description="Releases the remaining reserved capacity of this ended warranty back to the pool." /> : null}
            </div>
          </section>
        </div>
      )}
    </AsyncBoundary>
  );
}

export function PassportPage() {
  const { id } = useParams();
  const n = idParam(id);
  if (n === null) return <NotFoundBox what="Warranty passport" />;
  return <NeedsContract what={`Warranty passport ${n}`}>{(reader) => <Body reader={reader} id={n} />}</NeedsContract>;
}
