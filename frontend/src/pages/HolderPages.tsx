import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useClause, useWallet } from "../app/context";
import { listAllPassports, loadPassportBundle, mapLimit } from "../app/data";
import { useAsync } from "../app/useAsync";
import { calls } from "../contract/calls";
import type { ClauseReader } from "../contract/reader";
import type { Claim, FinalDecision } from "../contract/types";
import { formatDate, formatGen, formatUtc, sameAddress } from "../domain/format";
import { TxButton } from "../ui/actions";
import { Badge, ClaimStatusBadge, Sticker } from "../ui/kit";
import { PassportCard } from "../ui/passport";
import { AsyncBoundary, NeedsContract, NotFoundBox, idParam } from "./common";

function ConnectPrompt({ what }: { what: string }) {
  const w = useWallet();
  return (
    <section className="plate" role="status">
      <h2>Connect a wallet to see {what}</h2>
      <p>Everything on CLAUSE is publicly readable without a wallet. To see the warranties issued to <em>your</em> address, connect an injected wallet on GenLayer StudioNet. CLAUSE never asks for a private key.</p>
      {w.state.status === "unsupported" ? <p className="err">No injected wallet was detected in this browser. You can still <Link to="/explore">browse every warranty</Link>.</p> : <button type="button" className="btn" onClick={() => void w.connect()}>Connect wallet</button>}
    </section>
  );
}

function MyWarranties({ reader }: { reader: ClauseReader }) {
  const w = useWallet();
  const q = useAsync(async () => {
    if (!w.address) return null;
    const all = await listAllPassports(reader);
    const mine = all.filter((r) => sameAddress(r.passport.holder, w.address));
    const claims = await mapLimit(mine, 4, async (r) => {
      const ids = await reader.listClaimIdsForWarranty(r.passport.warrantyId);
      const list = (await mapLimit(ids, 4, (id) => reader.getClaim(id))).filter((c): c is Claim => c !== null);
      const finals = await mapLimit(list, 4, (c) => reader.getFinalDecision(c.claimId));
      return { warrantyId: r.passport.warrantyId, claims: list.map((c, i) => ({ claim: c, final: finals[i] as FinalDecision | null })) };
    });
    return { mine, claims };
  }, [reader, w.address]);
  if (!w.address) return <ConnectPrompt what="your warranties" />;
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Finding your warranties">
      {!q.data || q.data.mine.length === 0 ? <p className="muted" role="status">No warranties were issued to {w.address}.</p> : (
        <div className="stack">
          {q.data.mine.map((r) => {
            const cl = q.data!.claims.find((c) => c.warrantyId === r.passport.warrantyId)?.claims ?? [];
            return (
              <div key={r.passport.warrantyId} className="stack">
                <PassportCard passport={r.passport} program={r.program} claimCount={r.claimCount} />
                {cl.map(({ claim, final }) => (
                  <div key={claim.claimId} className="plate row" style={{ justifyContent: "space-between" }}>
                    <span>Claim #{claim.claimId} <ClaimStatusBadge status={claim.status} />{final && final.claimable > 0n ? <> <Badge tone="ok" glyph="◆">{formatGen(final.claimable)} GEN claimable</Badge></> : null}</span>
                    <Link className="btn small" to={`/claim/${claim.claimId}`}>{final && final.claimable > 0n ? "Withdraw" : "Open"}</Link>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </AsyncBoundary>
  );
}

export function Holder() {
  return (
    <div className="stack">
      <h1 style={{ fontSize: "2rem" }}>My warranties</h1>
      <NeedsContract what="My warranties">{(reader) => <MyWarranties reader={reader} />}</NeedsContract>
    </div>
  );
}

/** Guided claim form. Evidence is submitted on the claim page once the manufacturer disputes (or the response window closes). */
function ClaimForm({ reader, id }: { reader: ClauseReader; id: number }) {
  const wallet = useWallet();
  const { protocolNow } = useClause();
  const nav = useNavigate();
  const q = useAsync(() => loadPassportBundle(reader, id), [reader, id]);
  const [picked, setPicked] = useState<string[]>([]);
  const [date, setDate] = useState("");
  const b = q.data;
  const asserted = useMemo(() => (/^\d{4}-\d{2}-\d{2}$/.test(date) ? Math.floor(Date.parse(date + "T12:00:00Z") / 1000) : 0), [date]);
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading passport">
      {!b || !b.constitution ? <NotFoundBox what="Warranty passport" /> : (() => {
        const c = b.constitution;
        const now = protocolNow();
        const deadline = b.passport.coverageEnd + c.claimDeadlineS;
        const isHolder = sameAddress(wallet.address, b.passport.holder);
        const covered = b.clauses.filter((x) => x.kind === "COVERED");
        const excluded = b.clauses.filter((x) => x.kind === "EXCLUDED");
        const open = b.passport.status !== "CANCELLED" && now >= b.passport.coverageStart && now <= deadline;
        const insideWindow = asserted >= b.passport.coverageStart && asserted <= b.passport.coverageEnd;
        const reason = !open ? "Claims can no longer be filed for this warranty." : !wallet.ready ? "Connect a wallet on StudioNet." : !isHolder ? "Only the warranty holder can file a claim." : picked.length === 0 ? "Choose at least one covered clause." : asserted === 0 ? "Enter the date the failure occurred." : null;
        return (
          <div className="stack">
            <h1 style={{ fontSize: "2rem" }}>File a claim</h1>
            <PassportCard passport={b.passport} program={b.program} constitution={c} claimCount={b.claims.length} link={false} />
            <section className="plate" aria-labelledby="cf-h">
              <h2 id="cf-h">Your claim</h2>
              <p><strong>Product:</strong> {b.passport.productModelId}. <strong>Coverage:</strong> {formatDate(b.passport.coverageStart)} → {formatDate(b.passport.coverageEnd)} ({b.passport.status.toLowerCase()}). <strong>Claim deadline:</strong> {formatUtc(deadline)}.</p>
              <fieldset><legend>Which covered clause(s) does the failure fall under?</legend>
                {covered.map((cl) => (
                  <label key={cl.clauseId} className="check"><input type="checkbox" checked={picked.includes(cl.clauseId)} onChange={(e) => setPicked(e.target.checked ? [...picked, cl.clauseId] : picked.filter((x) => x !== cl.clauseId))} />
                    <span><Sticker id={cl.clauseId} text={cl.text} kind="COVERED" picked={picked.includes(cl.clauseId)} /></span></label>
                ))}
              </fieldset>
              <h3>Exclusions that may apply</h3>
              <div>{excluded.length ? excluded.map((x) => <Sticker key={x.clauseId} id={x.clauseId} text={x.text} kind="EXCLUDED" />) : <span className="muted">No exclusions.</span>}</div>
              <div className="field" style={{ marginTop: 14 }}><label htmlFor="fd">Date the failure occurred (asserted by you)</label>
                <input id="fd" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
                <p className="hint"><strong>Claimant-asserted, not verified.</strong> The protocol uses it only to check that the failure falls inside the coverage window; it is never used for deadlines.</p>
                {asserted !== 0 && !insideWindow ? <p className="err" role="status">This date is outside the coverage window. You may still file, but the claim will be decided NOT COVERED on the coverage window.</p> : null}</div>
              <h3>Evidence rules</h3>
              <ul>
                <li>Eligible sources: <code className="wrap">{c.sourceEligibilityPolicy}</code> (https only). Categories: {c.acceptableEvidenceCategories.join(", ")}.</li>
                <li><strong>Maximum 10 adjudicable evidence records per claim.</strong> Slots are first-come; ineligible URLs use no slot but are never adjudicated.</li>
                <li>Evidence is submitted on the claim page after you file, once the manufacturer disputes or its {c.manufacturerResponsePeriodS / 86400}-day response window closes (silence counts as a dispute).</li>
                <li>If the manufacturer accepts, no evidence or adjudication is needed.</li>
              </ul>
              <TxButton spec={calls.fileClaim(id, picked.length ? picked : ["C-001"], asserted || 1)} disabledReason={reason}
                reread={async () => { const ids = await reader.listClaimIdsForWarranty(id); return ids[ids.length - 1] ?? null; }}
                onDone={() => { void reader.listClaimIdsForWarranty(id).then((ids) => { if (ids.length) nav(`/claim/${ids[ids.length - 1]}`); }); }}
                description={`Files a claim against ${picked.join(", ") || "the chosen clauses"} with the failure asserted on ${date || "the chosen date"}.`} />
            </section>
          </div>
        );
      })()}
    </AsyncBoundary>
  );
}

export function FileClaimPage() {
  const { id } = useParams();
  const n = idParam(id);
  if (n === null) return <NotFoundBox what="Warranty passport" />;
  return <NeedsContract what="File a claim">{(reader) => <ClaimForm reader={reader} id={n} />}</NeedsContract>;
}
