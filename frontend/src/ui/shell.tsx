import { NavLink, Link, Outlet } from "react-router-dom";
import { useClause, useTx, useWallet } from "../app/context";
import { shortHex } from "../domain/format";
import { STUDIONET } from "../config/networks";
import { Copyable } from "./kit";
import type { TxPhase } from "../tx/runner";

export function ConnectionBanner() {
  const { config, health, refreshHealth } = useClause();
  const w = useWallet();
  const items: JSX.Element[] = [];
  if (config.status === "not-configured") {
    items.push(
      <div key="cfg" className="banner" role="status">
        <strong>Contract not configured.</strong> {config.reason} Public pages will explain what they would show; nothing is read from a made-up address.
        The canonical StudioNet address is inserted at deployment time (Stage 6) via <code>VITE_CLAUSE_CONTRACT_ADDRESS</code>.
      </div>,
    );
  } else if (config.status === "invalid") {
    items.push(<div key="cfg" className="banner bad" role="alert"><strong>Invalid contract address.</strong> {config.reason} Configured value: <code className="wrap">{config.raw}</code></div>);
  } else if (config.status === "network-error") {
    items.push(<div key="cfg" className="banner bad" role="alert"><strong>Network configuration error.</strong> {config.reason}</div>);
  } else if (health.state === "checking") {
    items.push(<div key="h" className="banner" role="status">Checking the CLAUSE contract on {config.network.name}…</div>);
  } else if (health.state === "error") {
    const label = health.kind === "rpc-unavailable" ? "RPC unavailable" : health.kind === "malformed" ? "Unexpected contract response" : "Contract read failed";
    items.push(
      <div key="h" className="banner bad" role="alert">
        <strong>{label}.</strong>{" "}
        {health.kind === "rpc-unavailable" ? `The ${config.network.name} RPC endpoint could not be reached.` : "The configured address did not answer like a CLAUSE contract."}{" "}
        <button type="button" className="btn small secondary" onClick={refreshHealth}>Retry</button>
        <details><summary>Technical diagnostics</summary><pre className="diag">{health.message}</pre></details>
      </div>,
    );
  }
  if (w.state.status === "wrong-network" && config.status !== "network-error") {
    items.push(
      <div key="wn" className="banner bad" role="alert">
        <strong>Wrong network.</strong> Your wallet is on chain {w.state.chainId}; CLAUSE needs {config.status === "configured" ? config.network.name : STUDIONET.name} ({config.status === "configured" ? config.network.chainId : STUDIONET.chainId}).{" "}
        <button type="button" className="btn small" onClick={() => void w.switchNetwork()}>Switch network</button>
      </div>,
    );
  }
  return <>{items}</>;
}

export function WalletButton() {
  const w = useWallet();
  const s = w.state;
  if (s.status === "unsupported") return <span className="badge neutral" title="Install an EIP-1193 wallet to send transactions. Reading is always available.">No wallet · read-only</span>;
  if (s.status === "connecting") return <button type="button" className="btn small" disabled>Connecting…</button>;
  if (s.status === "connected") return <span className="badge ok"><span className="g" aria-hidden="true">●</span>{shortHex(s.address)}</span>;
  if (s.status === "wrong-network") return <button type="button" className="btn small warn" onClick={() => void w.switchNetwork()}>Wrong network — switch</button>;
  return (
    <span className="row">
      <button type="button" className="btn small" onClick={() => void w.connect()}>Connect wallet</button>
      {s.status === "rejected" ? <span className="small" role="status">{s.message}</span> : null}
      {s.status === "error" ? <span className="small err" role="alert">{s.message}</span> : null}
    </span>
  );
}

const NAV = [["/", "Home", true], ["/explore", "Warranties"], ["/holder", "My warranties"], ["/manufacturer", "Manufacturer"], ["/limits", "V1 limits"]] as const;

export function Layout() {
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <div className="shell">
          <Link to="/" className="brand"><span className="brand-mark" aria-hidden="true" />CLAUSE</Link>
          <nav className="nav" aria-label="Primary">
            {NAV.map(([to, label, end]) => <NavLink key={to} to={to} end={Boolean(end)}>{label}</NavLink>)}
          </nav>
          <WalletButton />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <div className="shell">
          <ConnectionBanner />
          <Outlet />
        </div>
      </main>
      <footer className="footer">
        <div className="shell">
          <p><strong>CLAUSE</strong> — a warranty is only as good as who gets to interpret it. Terms freeze before the dispute; GenLayer validators adjudicate; the remedy comes from rules frozen in advance.</p>
          <p className="small">Target: GenLayer StudioNet (chain {STUDIONET.chainId}, {STUDIONET.currencySymbol}). Application Challenge is CLAUSE&apos;s own mechanism and is separate from GenLayer Protocol Appeal/Finality. <Link to="/limits">Read the V1 limitations</Link>.</p>
        </div>
      </footer>
      <TxPanel />
    </>
  );
}

function stepState(p: TxPhase): { steps: Array<[string, "done" | "now" | "todo" | "fail"]>; headline: string } {
  const order = ["Prepared", "Wallet confirmation", "Submitted", "Consensus", "Accepted by validators", "GenLayer Protocol Finality", "State re-read from contract"];
  const idx: Record<string, number> = { preparing: 0, "awaiting-wallet": 1, submitted: 2, consensus: 3, accepted: 4, finalized: 5, confirmed: 7 };
  const failed = p.phase === "failed" || p.phase === "wallet-rejected" || p.phase === "undetermined" || p.phase === "pending-unknown";
  const at = idx[p.phase] ?? (failed ? 3 : 0);
  const steps = order.map((label, i): [string, "done" | "now" | "todo" | "fail"] => {
    if (failed && i === Math.min(at, order.length - 1)) return [label, "fail"];
    if (i < at) return [label, "done"];
    if (i === at && !failed && p.phase !== "confirmed") return [label, "now"];
    return [label, "todo"];
  });
  const headline = { preparing: "Preparing…", "awaiting-wallet": "Waiting for your wallet…", submitted: "Submitted — waiting for consensus", consensus: "In consensus…",
    accepted: "Accepted — waiting for GenLayer Protocol Finality", finalized: "Finalized — re-reading contract state…", confirmed: "Confirmed", "wallet-rejected": "Signature rejected",
    failed: "Failed", undetermined: "Consensus undetermined", "pending-unknown": "Finality not confirmed yet", idle: "" }[p.phase];
  return { steps, headline };
}

export function TxPanel() {
  const { phase, label, outcome, dismiss } = useTx();
  if (phase.phase === "idle") return null;
  const { steps, headline } = stepState(phase);
  const hash = "hash" in phase ? phase.hash : undefined;
  const done = phase.phase === "confirmed" || phase.phase === "failed" || phase.phase === "wallet-rejected" || phase.phase === "undetermined" || phase.phase === "pending-unknown";
  const error = phase.phase === "failed" || phase.phase === "wallet-rejected" ? phase.error : outcome && !outcome.ok ? outcome.error : null;
  return (
    <div className="overlay">
      <section className="plate txpanel" aria-label="Transaction status">
        <h3>{label}</h3>
        <p role="status" aria-live="polite"><strong>{headline}</strong></p>
        <ol className="steps">{steps.map(([l, st]) => <li key={l} className={st}><span className="dot" aria-hidden="true" /><span>{l}<span className="sr-only"> — {st === "done" ? "done" : st === "now" ? "in progress" : st === "fail" ? "stopped here" : "waiting"}</span></span></li>)}</ol>
        {phase.phase === "confirmed" ? (
          <p className="banner ok">Finalized on GenLayer and re-read from the contract.{phase.rereadFailed ? " (The follow-up state read failed; reload the page to see current state.)" : ""}</p>
        ) : null}
        {phase.phase === "undetermined" ? <p className="banner">The validators did not agree. Nothing changed; you can retry.</p> : null}
        {phase.phase === "pending-unknown" ? <p className="banner">Finality was not confirmed in time. Nothing is assumed — track the hash below and re-check before continuing.</p> : null}
        {error ? <div className="banner bad" role="alert"><strong>{error.title}.</strong> {error.message}<details><summary>Technical diagnostics</summary><pre className="diag">{error.technical}</pre></details></div> : null}
        {hash ? <p className="small">Transaction hash: <Copyable value={hash} label="transaction hash" /></p> : null}
        {done ? <button type="button" className="btn secondary small" onClick={dismiss}>Dismiss</button> : null}
      </section>
    </div>
  );
}
