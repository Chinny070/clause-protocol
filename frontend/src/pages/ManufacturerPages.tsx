import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useWallet } from "../app/context";
import { listConstitutionsForProgram, listPrograms, listProgramClaims } from "../app/data";
import { useAsync } from "../app/useAsync";
import { calls } from "../contract/calls";
import type { ClauseReader } from "../contract/reader";
import type { Outcome, RemedyKind, RemedyRow } from "../contract/types";
import { draftToInput, remedyCompleteness, validateDraft, type Draft } from "../domain/constitutionDraft";
import { formatDate, formatGen, parseGen, sameAddress } from "../domain/format";
import { TxButton } from "../ui/actions";
import { Badge, ClaimStatusBadge, FrozenStamp, Gauge } from "../ui/kit";
import { AsyncBoundary, NeedsContract, NotFoundBox, idParam } from "./common";

function Connect({ what }: { what: string }) {
  const w = useWallet();
  return (
    <section className="plate" role="status">
      <h2>Connect a wallet to {what}</h2>
      <p>The manufacturer console sends transactions, so it needs an injected wallet on GenLayer StudioNet. Every page stays publicly readable without one. CLAUSE never asks for a private key.</p>
      {w.state.status === "unsupported" ? <p className="err">No injected wallet was detected in this browser.</p> : <button type="button" className="btn" onClick={() => void w.connect()}>Connect wallet</button>}
    </section>
  );
}

/* --------------------------------------------------------------------------------- manufacturer home */

function Home({ reader }: { reader: ClauseReader }) {
  const w = useWallet();
  const [name, setName] = useState("");
  const q = useAsync(() => listPrograms(reader), [reader]);
  const mine = (q.data ?? []).filter((p) => sameAddress(p.program.manufacturer, w.address));
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading programs">
      <div className="stack">
        <section className="plate petrol" aria-labelledby="mp-h">
          <h2 id="mp-h" style={{ color: "#fff" }}>Your warranty programs</h2>
          {!w.address ? <p>Connect a wallet to see programs you manage.</p> : mine.length === 0 ? <p>You have no warranty programs yet. Create one below.</p> : (
            <div className="grid auto">{mine.map(({ program, pool }) => (
              <div key={program.programId} className="plate" style={{ color: "var(--ink)" }}>
                <h3>{program.name}</h3><Badge tone={program.status === "ACTIVE" ? "ok" : "neutral"} glyph="●">{program.status}</Badge>
                {pool ? <p className="small">Capacity {formatGen(pool.totalBalance)} GEN · reserved {formatGen(pool.reservedLiability)} · available {formatGen(pool.availableBalance)}</p> : null}
                <Link className="btn small" to={`/manufacturer/program/${program.programId}`}>Open console</Link>
              </div>))}</div>
          )}
        </section>
        <section className="plate" aria-labelledby="np-h">
          <h2 id="np-h">Create a warranty program</h2>
          <p>A program owns one Warranty Capacity pool and any number of frozen terms versions. Creating it is cheap and reversible in spirit (you can retire it); freezing terms comes later.</p>
          <div className="field"><label htmlFor="pn">Program name</label><input id="pn" value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Widgets Extended Warranty" /></div>
          <TxButton spec={calls.createProgram(name.trim() || "x")} disabledReason={!w.ready ? "Connect a wallet on StudioNet." : name.trim() === "" ? "Enter a program name." : null}
            reread={() => listPrograms(reader)} onDone={q.reload} description={`Creates the program "${name.trim()}" with you as its manufacturer.`} />
        </section>
        <p className="small muted">All programs on this contract are publicly visible on <Link to="/explore">the explorer</Link>.</p>
      </div>
    </AsyncBoundary>
  );
}

export function Manufacturer() {
  const w = useWallet();
  return (
    <div className="stack">
      <h1 style={{ fontSize: "2rem" }}>Manufacturer console</h1>
      <NeedsContract what="Manufacturer console">{(reader) => (w.address ? <Home reader={reader} /> : <Connect what="manage programs" />)}</NeedsContract>
    </div>
  );
}

/* --------------------------------------------------------------------------------- program console / pool transparency */

function Console({ reader, id }: { reader: ClauseReader; id: number }) {
  const w = useWallet();
  const [fund, setFund] = useState("");
  const [wd, setWd] = useState("");
  const q = useAsync(async () => {
    const [program, pool, constitutions, passportIds, inbox] = await Promise.all([reader.getProgram(id), reader.getPool(id), listConstitutionsForProgram(reader, id), reader.listPassportIds(id), listProgramClaims(reader, id)]);
    const passports = await Promise.all(passportIds.map((pid) => reader.getPassport(pid)));
    return { program, pool, constitutions, passports: passports.filter((p) => p !== null), inbox };
  }, [reader, id]);
  const d = q.data;
  const isMfr = !!d?.program && sameAddress(d.program.manufacturer, w.address);
  const fundAtoms = parseGen(fund);
  const wdAtoms = parseGen(wd);
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading program">
      {!d || !d.program || !d.pool ? <NotFoundBox what="Program" /> : (
        <div className="stack">
          <h1 style={{ fontSize: "2rem" }}>{d.program.name}</h1>
          <p className="row"><Badge tone={d.program.status === "ACTIVE" ? "ok" : "neutral"} glyph="●">{d.program.status}</Badge><span className="mono wrap small">{d.program.manufacturer}</span>{isMfr ? <Badge tone="plum" glyph="★">You manage this program</Badge> : null}</p>
          <section className="plate petrol" aria-labelledby="cap-h"><h2 id="cap-h" style={{ color: "#fff" }}>Warranty Capacity</h2>
            <Gauge total={d.pool.totalBalance} reserved={d.pool.reservedLiability} format={(v) => formatGen(v)} />
            <p className="small">Reserved capacity is protected: the manufacturer cannot withdraw it, so an issued warranty cannot be starved by a later withdrawal. Value already settled to holders is held outside the pool until they withdraw it.</p></section>
          {isMfr ? (
            <section className="plate" aria-labelledby="mg-h"><h2 id="mg-h">Manage capacity</h2>
              <div className="grid two">
                <div><div className="field"><label htmlFor="fund">Add capacity (GEN)</label><input id="fund" inputMode="decimal" value={fund} onChange={(e) => setFund(e.target.value)} /></div>
                  <TxButton spec={calls.fundPool(id, fundAtoms ?? 1n)} disabledReason={!w.ready ? "Connect a wallet on StudioNet." : fundAtoms === null || fundAtoms <= 0n ? "Enter a positive amount, e.g. 5 or 0.25." : null}
                    reread={() => reader.getPool(id)} onDone={q.reload} description={`Sends ${fund || "?"} GEN into this program's capacity pool.`} /></div>
                <div><div className="field"><label htmlFor="wd">Withdraw unreserved (GEN)</label><input id="wd" inputMode="decimal" value={wd} onChange={(e) => setWd(e.target.value)} /><p className="hint">Only unreserved capacity ({formatGen(d.pool.availableBalance)} GEN) can be withdrawn.</p></div>
                  <TxButton variant="secondary" spec={calls.withdrawPool(id, wdAtoms ?? 1n)} disabledReason={!w.ready ? "Connect a wallet on StudioNet." : wdAtoms === null || wdAtoms <= 0n ? "Enter a positive amount." : wdAtoms > d.pool.availableBalance ? "That exceeds your unreserved capacity." : null}
                    reread={() => reader.getPool(id)} onDone={q.reload} description={`Withdraws ${wd || "?"} GEN of unreserved capacity to your wallet.`} /></div>
              </div>
            </section>
          ) : null}
          <section className="plate metal" aria-labelledby="tv-h"><h2 id="tv-h">Frozen terms versions</h2>
            {d.constitutions.length === 0 ? <p className="muted">No terms versions yet.</p> : d.constitutions.map((c) => (
              <div key={c.constitutionId} className="strip"><div className="row" style={{ justifyContent: "space-between" }}><strong>{c.version}</strong><FrozenStamp text={c.isFrozen ? "Frozen terms" : "Not yet frozen"} /></div>
                <p className="small">{c.coveredClauseIds.length} covered clause(s), {c.excludedClauseIds.length} exclusion(s). Terms id {c.constitutionId}.</p><p className="mono wrap small">{c.fingerprint}</p></div>
            ))}
            {isMfr ? <p><Link className="btn" to={`/manufacturer/program/${id}/terms/new`}>Author new terms</Link> <Link className="btn secondary" to={`/manufacturer/program/${id}/issue`}>Issue a warranty passport</Link></p> : null}
          </section>
          <section className="plate" aria-labelledby="pp-h"><h2 id="pp-h">Warranty passports ({d.passports.length})</h2>
            {d.passports.length === 0 ? <p className="muted">None issued.</p> : <table className="plain"><thead><tr><th>№</th><th>Product</th><th>Coverage</th><th>Status</th><th>Max remedy</th></tr></thead><tbody>
              {d.passports.map((p) => p && <tr key={p.warrantyId}><td data-th="№"><Link to={`/passport/${p.warrantyId}`}>{p.warrantyId}</Link></td><td data-th="Product">{p.productModelId}</td><td data-th="Coverage">{formatDate(p.coverageStart)} → {formatDate(p.coverageEnd)}</td><td data-th="Status">{p.status === "CANCELLED" ? <Badge tone="bad" glyph="✖">Cancelled</Badge> : p.status}</td><td data-th="Max remedy">{formatGen(p.maxDeterministicRemedy)} GEN</td></tr>)}</tbody></table>}
          </section>
          <section className="plate" aria-labelledby="ib-h"><h2 id="ib-h">Claims inbox ({d.inbox.length})</h2>
            {d.inbox.length === 0 ? <p className="muted">No claims yet.</p> : <table className="plain"><thead><tr><th>Claim</th><th>Warranty</th><th>Status</th><th /></tr></thead><tbody>
              {d.inbox.map(({ claim, passport }) => <tr key={claim.claimId}><td data-th="Claim">#{claim.claimId}</td><td data-th="Warranty">{passport.productModelId}</td><td data-th="Status"><ClaimStatusBadge status={claim.status} /></td>
                <td><Link className="btn small" to={`/claim/${claim.claimId}`}>{claim.status === "RESPONSE_WINDOW" && isMfr ? "Respond" : "Open"}</Link></td></tr>)}</tbody></table>}
          </section>
          {isMfr && d.program.status !== "RETIRED" ? (
            <section className="plate" aria-labelledby="ps-h"><h2 id="ps-h">Program status</h2>
              <p className="hint">Retiring a program stops future issuance. Existing warranties remain governed by their frozen terms.</p>
              <div className="row">
                {d.program.status === "ACTIVE" ? <TxButton variant="secondary" spec={calls.pauseProgram(id)} reread={() => reader.getProgram(id)} onDone={q.reload} description="Pauses NEW warranty issuance only. Existing warranties remain governed by their frozen terms; claims continue." /> : <TxButton variant="secondary" spec={calls.resumeProgram(id)} reread={() => reader.getProgram(id)} onDone={q.reload} description="Resumes warranty issuance." />}
                <TxButton variant="warn" spec={calls.retireProgram(id)} reread={() => reader.getProgram(id)} onDone={q.reload} description="Retires this program permanently: no new terms or warranties. Existing warranties remain governed by their frozen terms; claims continue." />
              </div></section>
          ) : null}
        </div>
      )}
    </AsyncBoundary>
  );
}

export function ProgramPage() {
  const { id } = useParams();
  const n = idParam(id);
  if (n === null) return <NotFoundBox what="Program" />;
  return <NeedsContract what="Program console">{(reader) => <Console reader={reader} id={n} />}</NeedsContract>;
}

/* --------------------------------------------------------------------------------- terms authoring wizard */

const OUTCOMES: Outcome[] = ["COVERED", "NOT_COVERED", "INSUFFICIENT_EVIDENCE", "EVIDENCE_UNAVAILABLE", "INVALID_CLAIM", "ACCEPTED_NO_CONTEST"];
const KINDS: RemedyKind[] = ["FULL_REFUND", "PARTIAL_BPS", "REPAIR_CREDIT", "NONE"];

const initialDraft = (): Draft => ({
  version: "2026.1", productScope: "", coverageCalc: "Flat term from the coverage start date.",
  covered: [{ clause_id: "C-001", text: "" }], excluded: [], categories: ["RECEIPT"], sourcePolicy: "",
  claimDeadlineDays: 30, responseDays: 14, challengeWindowDays: 7, challengeEnabled: true,
  insufficientBehavior: "RULE_FOR_MANUFACTURER", unavailableBehavior: "RULE_FOR_MANUFACTURER",
  expiryRules: "The holder may cancel their own warranty while no claim is unsettled. The manufacturer cannot cancel an issued warranty.",
  remedy: [
    { outcome: "COVERED", clause_id: "", remedy_kind: "FULL_REFUND", remedy_value: 0n },
    { outcome: "NOT_COVERED", clause_id: "", remedy_kind: "NONE", remedy_value: 0n },
    { outcome: "ACCEPTED_NO_CONTEST", clause_id: "", remedy_kind: "FULL_REFUND", remedy_value: 0n },
  ],
});

function TermsWizard({ reader, programId }: { reader: ClauseReader; programId: number }) {
  const w = useWallet();
  const nav = useNavigate();
  const [d, setD] = useState<Draft>(initialDraft);
  const [review, setReview] = useState(false);
  const [ack, setAck] = useState(false);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));
  const issues = useMemo(() => validateDraft(d), [d]);
  const comp = remedyCompleteness(d.remedy, d.covered.map((c) => c.clause_id));
  const autoComplete = () => {
    const rows = [...d.remedy];
    const have = (o: string, c: string) => rows.some((r) => r.outcome === o && r.clause_id === c);
    if (!have("ACCEPTED_NO_CONTEST", "")) rows.push({ outcome: "ACCEPTED_NO_CONTEST", clause_id: "", remedy_kind: "FULL_REFUND", remedy_value: 0n });
    if (!have("COVERED", "") && d.covered.some((c) => !have("COVERED", c.clause_id))) rows.push({ outcome: "COVERED", clause_id: "", remedy_kind: "FULL_REFUND", remedy_value: 0n });
    set("remedy", rows);
  };
  const updateRow = (i: number, patch: Partial<RemedyRow>) => set("remedy", d.remedy.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const clauseIds = [...d.covered, ...d.excluded].map((c) => c.clause_id).filter(Boolean);

  const input = draftToInput(programId, d);
  if (review) {
    return (
      <div className="stack">
        <h1 style={{ fontSize: "2rem" }}>Review frozen terms</h1>
        <p className="frozen-banner">FROZEN TERMS — THIS VERSION CANNOT BE SILENTLY REWRITTEN AFTER ISSUANCE</p>
        <section className="plate metal">
          <p><strong>Version {d.version}.</strong> Once your first warranty is issued against it, these terms are frozen: they cannot be edited, and any change is a new version with a new fingerprint. Holders and validators are bound by exactly what you see here.</p>
          <div className="grid two">
            <div><h3>Covered clauses</h3><ul>{d.covered.map((c) => <li key={c.clause_id}><b className="mono">{c.clause_id}</b> {c.text}</li>)}</ul></div>
            <div><h3>Exclusions</h3><ul>{d.excluded.length ? d.excluded.map((c) => <li key={c.clause_id}><b className="mono">{c.clause_id}</b> {c.text}</li>) : <li>None</li>}</ul></div>
          </div>
          <p><strong>Evidence:</strong> {d.categories.join(", ")} from <code className="wrap">{d.sourcePolicy}</code> (https only). <strong>Timing:</strong> claims up to {d.claimDeadlineDays} days after coverage ends; manufacturer responds within {d.responseDays} days; {d.challengeEnabled ? `one Application Challenge, ${d.challengeWindowDays}-day window` : "Application Challenges disabled"}.</p>
          <p><strong>If evidence is insufficient:</strong> {d.insufficientBehavior.replace(/_/g, " ")}. <strong>If unavailable:</strong> {d.unavailableBehavior.replace(/_/g, " ")}.</p>
          <table className="plain"><thead><tr><th>Outcome</th><th>Clause</th><th>Remedy</th></tr></thead><tbody>{d.remedy.map((r, i) => <tr key={i}><td data-th="Outcome">{r.outcome}</td><td data-th="Clause">{r.clause_id || "any"}</td><td data-th="Remedy">{r.remedy_kind}{r.remedy_kind === "PARTIAL_BPS" ? ` ${r.remedy_value} bps` : r.remedy_kind === "REPAIR_CREDIT" ? ` ${formatGen(r.remedy_value)} GEN` : ""}</td></tr>)}</tbody></table>
          <p className="small">Remedy table completeness: {comp.complete ? "✔ every payable final state has a remedy row." : "✖ incomplete."} The contract re-checks this and refuses incomplete tables before any warranty can bind to them.</p>
          <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /><span>I understand these terms will be frozen and fingerprinted on GenLayer and cannot be rewritten after a warranty is issued.</span></label>
          <div className="row">
            <TxButton spec={calls.createConstitution(input)} disabledReason={!w.ready ? "Connect a wallet on StudioNet." : issues.length > 0 ? "Fix the issues in the form first." : !ack ? "Tick the acknowledgement to continue." : null}
              reread={() => listConstitutionsForProgram(reader, programId)} onDone={() => nav(`/manufacturer/program/${programId}`)} description="Publishes this terms version on GenLayer. It freezes the moment your first warranty is issued against it." />
            <button type="button" className="btn secondary" onClick={() => setReview(false)}>Back to editing</button>
          </div>
        </section>
      </div>
    );
  }
  return (
    <div className="stack">
      <h1 style={{ fontSize: "2rem" }}>Author warranty terms</h1>
      <p className="frozen-banner">FROZEN TERMS — THIS VERSION CANNOT BE SILENTLY REWRITTEN AFTER ISSUANCE</p>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); if (issues.length === 0) setReview(true); }}>
        <section className="plate"><h2>1 · Basics</h2>
          <div className="field"><label htmlFor="v">Version name</label><input id="v" value={d.version} onChange={(e) => set("version", e.target.value)} /></div>
          <div className="field"><label htmlFor="ps">Product scope</label><input id="ps" value={d.productScope} onChange={(e) => set("productScope", e.target.value)} placeholder="Widget Model X" /></div>
          <div className="field"><label htmlFor="cc">How coverage is calculated</label><input id="cc" value={d.coverageCalc} onChange={(e) => set("coverageCalc", e.target.value)} /></div></section>
        <section className="plate"><h2>2 · Clauses</h2>
          {(["covered", "excluded"] as const).map((kind) => (
            <fieldset key={kind}><legend>{kind === "covered" ? "Covered clauses (ids start with C-)" : "Exclusions (ids start with X-)"}</legend>
              {d[kind].map((c, i) => (
                <div key={i} className="grid two" style={{ marginBottom: 8 }}>
                  <div><label htmlFor={`${kind}-id-${i}`}>Clause id</label><input id={`${kind}-id-${i}`} value={c.clause_id} onChange={(e) => set(kind, d[kind].map((x, j) => (j === i ? { ...x, clause_id: e.target.value } : x)))} /></div>
                  <div><label htmlFor={`${kind}-tx-${i}`}>Clause text</label><textarea id={`${kind}-tx-${i}`} value={c.text} onChange={(e) => set(kind, d[kind].map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} /></div>
                  <button type="button" className="btn small secondary" onClick={() => set(kind, d[kind].filter((_, j) => j !== i))}>Remove</button>
                </div>
              ))}
              <button type="button" className="btn small secondary" onClick={() => set(kind, [...d[kind], { clause_id: `${kind === "covered" ? "C" : "X"}-${String(d[kind].length + 1).padStart(3, "0")}`, text: "" }])}>Add {kind === "covered" ? "covered clause" : "exclusion"}</button>
            </fieldset>
          ))}</section>
        <section className="plate"><h2>3 · Evidence rules</h2>
          <div className="field"><label htmlFor="sp">Permitted evidence hosts (comma separated)</label><input id="sp" value={d.sourcePolicy} onChange={(e) => set("sourcePolicy", e.target.value)} placeholder="warranty.example.com, *.support.example.com" />
            <p className="hint">https only. <code>*.host</code> matches subdomains but not the bare domain; list both if you want both.</p></div>
          <div className="field"><label htmlFor="cat">Evidence categories (comma separated)</label><input id="cat" value={d.categories.join(", ")} onChange={(e) => set("categories", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
            <p className="hint">A category ending in <code>_RENDERED</code> is retrieved with a browser render instead of a plain fetch (a StudioNet-gated capability).</p></div></section>
        <section className="plate"><h2>4 · Timing and gaps</h2>
          <div className="grid three">
            <div className="field"><label htmlFor="cd">Claim deadline (days after coverage ends)</label><input id="cd" type="number" min={0} value={d.claimDeadlineDays} onChange={(e) => set("claimDeadlineDays", Number(e.target.value))} /></div>
            <div className="field"><label htmlFor="rd">Manufacturer response (days)</label><input id="rd" type="number" min={0} value={d.responseDays} onChange={(e) => set("responseDays", Number(e.target.value))} /></div>
            <div className="field"><label htmlFor="cw">Application Challenge window (days)</label><input id="cw" type="number" min={0} value={d.challengeWindowDays} onChange={(e) => set("challengeWindowDays", Number(e.target.value))} /></div>
          </div>
          <label className="check"><input type="checkbox" checked={d.challengeEnabled} onChange={(e) => set("challengeEnabled", e.target.checked)} /><span>Allow one Application Challenge per claim</span></label>
          <div className="grid two">
            <div className="field"><label htmlFor="ie">If evidence is insufficient</label><select id="ie" value={d.insufficientBehavior} onChange={(e) => set("insufficientBehavior", e.target.value)}><option value="RULE_FOR_MANUFACTURER">Rule for the manufacturer (no payment)</option><option value="RULE_FOR_HOLDER">Rule for the holder (pay as covered)</option><option value="BLOCK">Block (no payment)</option></select></div>
            <div className="field"><label htmlFor="ue">If evidence is unavailable</label><select id="ue" value={d.unavailableBehavior} onChange={(e) => set("unavailableBehavior", e.target.value)}><option value="RULE_FOR_MANUFACTURER">Rule for the manufacturer (no payment)</option><option value="RULE_FOR_HOLDER">Rule for the holder (pay as covered)</option><option value="BLOCK">Block (no payment)</option></select></div>
          </div>
          <div className="field"><label htmlFor="er">Expiry / cancellation rules (text)</label><input id="er" value={d.expiryRules} onChange={(e) => set("expiryRules", e.target.value)} />
            <p className="hint">V1: once issued, a warranty is a commitment. The manufacturer cannot cancel it; only the holder can cancel their own. Retiring or pausing a program stops future issuance only.</p></div></section>
        <section className="plate"><h2>5 · Precommitted remedy table</h2>
          <p className="hint">Only COVERED and ACCEPTED_NO_CONTEST (and evidence gaps set to “rule for the holder”) can pay. The remedy comes from this table by plain code: FULL_REFUND pays the warranty maximum; PARTIAL_BPS is basis points of it; REPAIR_CREDIT is an amount capped at it.</p>
          {d.remedy.map((r, i) => (
            <div key={i} className="grid auto" style={{ marginBottom: 10, alignItems: "end" }}>
              <div><label htmlFor={`ro-${i}`}>Outcome</label><select id={`ro-${i}`} value={r.outcome} onChange={(e) => updateRow(i, { outcome: e.target.value as Outcome })}>{OUTCOMES.map((o) => <option key={o}>{o}</option>)}</select></div>
              <div><label htmlFor={`rc-${i}`}>Clause</label><select id={`rc-${i}`} value={r.clause_id} onChange={(e) => updateRow(i, { clause_id: e.target.value })}><option value="">any (outcome-level)</option>{clauseIds.map((c) => <option key={c}>{c}</option>)}</select></div>
              <div><label htmlFor={`rk-${i}`}>Remedy</label><select id={`rk-${i}`} value={r.remedy_kind} onChange={(e) => updateRow(i, { remedy_kind: e.target.value as RemedyKind, remedy_value: 0n })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></div>
              <div><label htmlFor={`rv-${i}`}>{r.remedy_kind === "PARTIAL_BPS" ? "Basis points (0-10000)" : r.remedy_kind === "REPAIR_CREDIT" ? "Amount (GEN)" : "Value"}</label>
                <input id={`rv-${i}`} disabled={r.remedy_kind === "FULL_REFUND" || r.remedy_kind === "NONE"} defaultValue={r.remedy_kind === "REPAIR_CREDIT" ? formatGen(r.remedy_value) : String(r.remedy_value)}
                  onChange={(e) => { if (r.remedy_kind === "REPAIR_CREDIT") { const v = parseGen(e.target.value); if (v !== null) updateRow(i, { remedy_value: v }); } else if (/^\d+$/.test(e.target.value)) updateRow(i, { remedy_value: BigInt(e.target.value) }); }} /></div>
              <button type="button" className="btn small secondary" onClick={() => set("remedy", d.remedy.filter((_, j) => j !== i))}>Remove</button>
            </div>
          ))}
          <div className="row"><button type="button" className="btn small secondary" onClick={() => set("remedy", [...d.remedy, { outcome: "COVERED", clause_id: "", remedy_kind: "FULL_REFUND", remedy_value: 0n }])}>Add row</button>
            {!comp.complete ? <button type="button" className="btn small" onClick={autoComplete}>Add the missing required rows</button> : null}</div>
          <div className={comp.complete ? "banner ok" : "banner bad"} role="status" style={{ marginTop: 12 }}>
            {comp.complete ? "✔ Remedy table complete: every payable final state has a frozen remedy." : <><strong>✖ Remedy table incomplete.</strong> The contract refuses it (a frozen warranty could otherwise get stuck):<ul>{comp.missing.map((m) => <li key={m}>{m}</li>)}</ul></>}
          </div></section>
        {issues.length > 0 ? <div className="banner bad" role="alert"><strong>Fix before review:</strong><ul>{issues.map((i, k) => <li key={k}>{i.field}: {i.message}</li>)}</ul></div> : null}
        <p><button type="submit" className="btn" disabled={issues.length > 0}>Review terms</button></p>
      </form>
    </div>
  );
}

export function TermsPage() {
  const { id } = useParams();
  const n = idParam(id);
  const w = useWallet();
  if (n === null) return <NotFoundBox what="Program" />;
  return <NeedsContract what="Author terms">{(reader) => (w.address ? <TermsWizard reader={reader} programId={n} /> : <Connect what="author terms" />)}</NeedsContract>;
}

/* --------------------------------------------------------------------------------- issue warranty */

async function commitment(serial: string, salt: string): Promise<string> {
  const data = new TextEncoder().encode(`${serial}|${salt}`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function Issue({ reader, programId }: { reader: ClauseReader; programId: number }) {
  const w = useWallet();
  const nav = useNavigate();
  const q = useAsync(async () => ({ pool: await reader.getPool(programId), program: await reader.getProgram(programId), cs: await listConstitutionsForProgram(reader, programId) }), [reader, programId]);
  const [cid, setCid] = useState("");
  const [holder, setHolder] = useState("");
  const [model, setModel] = useState("");
  const [serial, setSerial] = useState("");
  const [salt, setSalt] = useState("");
  const [hex, setHex] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [amount, setAmount] = useState("");
  const atoms = parseGen(amount);
  const ts = (d: string) => (/^\d{4}-\d{2}-\d{2}$/.test(d) ? Math.floor(Date.parse(d + "T00:00:00Z") / 1000) : 0);
  const avail = q.data?.pool?.availableBalance ?? 0n;
  const reason = !w.ready ? "Connect a wallet on StudioNet." : !cid ? "Choose the terms version." : !/^0x[0-9a-fA-F]{40}$/.test(holder) ? "Enter the holder's wallet address (0x…)." : model.trim() === "" ? "Enter the product model." : hex.length !== 64 ? "Generate the product commitment first." : !ts(start) || !ts(end) || ts(start) >= ts(end) ? "Enter a valid coverage start before end." : atoms === null || atoms <= 0n ? "Enter the maximum remedy in GEN." : atoms > avail ? `Insufficient capacity: only ${formatGen(avail)} GEN is unreserved (preview; the contract decides).` : null;
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading program">
      {!q.data?.program ? <NotFoundBox what="Program" /> : (
        <div className="stack">
          <h1 style={{ fontSize: "2rem" }}>Issue a warranty passport</h1>
          <p className="frozen-banner">Issuing freezes the chosen terms version. Its fingerprint is copied into the passport.</p>
          <section className="plate">
            <div className="field"><label htmlFor="c">Terms version</label><select id="c" value={cid} onChange={(e) => setCid(e.target.value)}><option value="">Select…</option>{q.data.cs.map((c) => <option key={c.constitutionId} value={c.constitutionId}>{c.version}{c.isFrozen ? " (frozen)" : ""}</option>)}</select></div>
            <div className="field"><label htmlFor="h">Holder wallet address</label><input id="h" value={holder} onChange={(e) => setHolder(e.target.value.trim())} placeholder="0x…" spellCheck={false} /></div>
            <div className="field"><label htmlFor="m">Product model</label><input id="m" value={model} onChange={(e) => setModel(e.target.value)} /></div>
            <fieldset><legend>Product identity commitment</legend>
              <p className="hint">The serial number is never stored on-chain: only a SHA-256 commitment of serial and a secret salt. Keep the salt; the holder needs it to prove the product later.</p>
              <div className="grid two"><div className="field"><label htmlFor="s">Serial number</label><input id="s" value={serial} onChange={(e) => setSerial(e.target.value)} /></div><div className="field"><label htmlFor="sa">Secret salt</label><input id="sa" value={salt} onChange={(e) => setSalt(e.target.value)} /></div></div>
              <button type="button" className="btn small secondary" disabled={serial === "" || salt === ""} onClick={() => void commitment(serial, salt).then(setHex)}>Generate commitment</button>
              {hex ? <p className="mono wrap small">{hex}</p> : null}</fieldset>
            <div className="grid two"><div className="field"><label htmlFor="cs">Coverage start (UTC date)</label><input id="cs" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></div><div className="field"><label htmlFor="ce">Coverage end (UTC date)</label><input id="ce" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></div></div>
            <div className="field"><label htmlFor="mr">Maximum remedy (GEN) — reserved from your capacity</label><input id="mr" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /><p className="hint">Unreserved capacity now: {formatGen(avail)} GEN. This is a preview; the contract enforces the real limit.</p></div>
            <TxButton spec={calls.issueWarranty({ programId, constitutionId: Number(cid) || 1, holder: holder || "0x", productModelId: model || "x", productCommitmentHex: hex || "0".repeat(64), coverageStart: ts(start) || 1, coverageEnd: ts(end) || 2, maxDeterministicRemedy: atoms ?? 1n })}
              disabledReason={reason} reread={() => reader.listPassportIds(programId)} onDone={() => nav(`/manufacturer/program/${programId}`)}
              description={`Issues a warranty to ${holder || "the holder"} for ${model || "the product"} and reserves up to ${amount || "?"} GEN. The terms version freezes now if it is not frozen already.`} />
          </section>
        </div>
      )}
    </AsyncBoundary>
  );
}

export function IssuePage() {
  const { id } = useParams();
  const n = idParam(id);
  const w = useWallet();
  if (n === null) return <NotFoundBox what="Program" />;
  return <NeedsContract what="Issue a warranty">{(reader) => (w.address ? <Issue reader={reader} programId={n} /> : <Connect what="issue a warranty" />)}</NeedsContract>;
}

