import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listAllPassports } from "../app/data";
import { useAsync } from "../app/useAsync";
import { formatDate, formatGen } from "../domain/format";
import { PassportStatusBadge, FrozenStamp } from "../ui/kit";
import { AsyncBoundary, NeedsContract } from "./common";
import type { ClauseReader } from "../contract/reader";

function List({ reader }: { reader: ClauseReader }) {
  const q = useAsync(() => listAllPassports(reader), [reader]);
  const [status, setStatus] = useState("ALL");
  const [text, setText] = useState("");
  const rows = useMemo(() => (q.data ?? []).filter((r) =>
    (status === "ALL" || r.passport.status === status) &&
    (text.trim() === "" || `${r.passport.warrantyId} ${r.passport.productModelId} ${r.program?.name ?? ""} ${r.passport.manufacturer}`.toLowerCase().includes(text.trim().toLowerCase()))), [q.data, status, text]);
  return (
    <AsyncBoundary loading={q.loading} error={q.error} what="Reading warranties">
      <div className="row noprint" style={{ marginBottom: 12 }}>
        <div className="field" style={{ flex: "1 1 220px", marginBottom: 0 }}>
          <label htmlFor="q">Search by passport id, product or manufacturer</label>
          <input id="q" value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="field" style={{ flex: "0 1 200px", marginBottom: 0 }}>
          <label htmlFor="st">Coverage status</label>
          <select id="st" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="ALL">All</option><option value="ACTIVE">Active</option><option value="EXPIRED">Ended</option><option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>
      {rows.length === 0 ? <p className="muted" role="status">{(q.data ?? []).length === 0 ? "No warranties have been issued on this contract yet." : "No warranties match your filters."}</p> : null}
      <div className="grid auto">
        {rows.map(({ passport: p, program, claimCount }) => (
          <article key={p.warrantyId} className="passport" aria-label={`Passport ${p.warrantyId}`}>
            <header className="passport-head"><h3>№ {String(p.warrantyId).padStart(5, "0")} · {p.productModelId}</h3><PassportStatusBadge status={p.status} /></header>
            <div className="passport-body" style={{ paddingBottom: 6 }}>
              <dl className="kv"><dt>Program</dt><dd>{program?.name ?? `#${p.programId}`}</dd></dl>
              <dl className="kv"><dt>Coverage</dt><dd>{formatDate(p.coverageStart)} → {formatDate(p.coverageEnd)}</dd></dl>
              <dl className="kv"><dt>Max remedy</dt><dd>{formatGen(p.maxDeterministicRemedy)} GEN</dd></dl>
              <dl className="kv"><dt>Terms</dt><dd>{p.constitutionVersion} <FrozenStamp text="Frozen" /></dd></dl>
              <dl className="kv"><dt>Claims</dt><dd>{claimCount}</dd></dl>
            </div>
            <div className="passport-foot"><div className="wrap">fp {p.constitutionFingerprint}</div><div style={{ marginTop: 8 }}><Link className="btn small" to={`/passport/${p.warrantyId}`}>Open passport</Link></div></div>
          </article>
        ))}
      </div>
    </AsyncBoundary>
  );
}

export function Explore() {
  return (
    <div className="stack">
      <h1 style={{ fontSize: "2rem" }}>Warranty explorer</h1>
      <p className="muted">Every issued Warranty Passport, read live from the CLAUSE contract. No wallet required.</p>
      <NeedsContract what="Warranty explorer">{(reader) => <List reader={reader} />}</NeedsContract>
    </div>
  );
}
