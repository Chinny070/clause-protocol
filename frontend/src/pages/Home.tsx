import { Link } from "react-router-dom";
import { useClause } from "../app/context";
import { STAGES } from "../domain/timeline";
import { FrozenStamp } from "../ui/kit";

function Chain({ items, bad = false }: { items: string[]; bad?: boolean }) {
  return (
    <div className={`chain${bad ? " bad" : ""}`} role="list">
      {items.map((t, i) => (
        <span key={t} style={{ display: "contents" }}>
          <span className="node" role="listitem">{t}</span>
          {i < items.length - 1 ? <span className="arrow" aria-hidden="true">→</span> : null}
        </span>
      ))}
    </div>
  );
}

export function Home() {
  const { health, config } = useClause();
  return (
    <>
      <section className="hero" aria-labelledby="hero-h">
        <p className="row"><FrozenStamp text="Frozen terms" animate /> <span className="muted small">precommitted warranty adjudication on GenLayer</span></p>
        <h1 id="hero-h">THE PRODUCT BROKE.<span className="l2">THE RULES DON&apos;T GET TO CHANGE NOW.</span></h1>
        <p className="lead">The manufacturer writes the warranty up front. The terms freeze. Evidence is retrieved independently, GenLayer validators adjudicate the dispute, and the remedy comes from rules that were frozen <em>before</em> anything broke.</p>
        <p className="row">
          <Link className="btn" to="/explore">Explore warranties</Link>
          <Link className="btn secondary" to="/manufacturer">Register a warranty</Link>
          <Link className="btn secondary" to="/limits">Read the V1 limits</Link>
        </p>
        {config.status === "configured" && health.state === "ok" ? <p className="small muted" role="status">Live on {config.network.name}: {health.programCount} warranty program{health.programCount === 1 ? "" : "s"} on the configured contract.</p> : null}
      </section>

      <section className="plate metal" aria-labelledby="how-h">
        <h2 id="how-h">How CLAUSE works</h2>
        <ol className="stages" aria-label="Lifecycle">
          {STAGES.map((s, i) => <li key={s} className={i === 0 ? "done" : ""}><span>{s}</span></li>)}
        </ol>
        <div className="grid three" style={{ marginTop: 18 }}>
          <div><h3>1 · Terms freeze</h3><p>Covered clauses, exclusions, evidence rules, deadlines and a precommitted remedy table are frozen and fingerprinted before the first warranty is issued.</p></div>
          <div><h3>2 · Evidence, independently</h3><p>Only sources allowed by the frozen policy are retrieved, through validator consensus, then frozen. Unavailable evidence is never treated as proof against either side.</p></div>
          <div><h3>3 · Decision, then remedy</h3><p>GenLayer validators decide structured findings. Plain code derives the outcome and picks the remedy from the frozen table. One Application Challenge is allowed.</p></div>
        </div>
      </section>

      <section className="grid two" style={{ marginTop: 20 }} aria-labelledby="why-h">
        <div className="plate">
          <h2 id="why-h">Why it exists</h2>
          <p>The traditional warranty problem:</p>
          <Chain bad items={["Manufacturer writes terms", "Manufacturer interprets terms", "Manufacturer decides whether it pays"]} />
          <p>The same party writes, judges and pays. Terms can drift and evidence can be dismissed.</p>
        </div>
        <div className="plate plastic">
          <h2>With CLAUSE</h2>
          <Chain items={["Manufacturer writes terms", "Terms freeze", "Independent evidence", "Validator consensus", "Precommitted remedy"]} />
          <p>The manufacturer keeps control of what they promise, and gives up control of how the promise is judged.</p>
        </div>
      </section>

      <section className="plate" style={{ marginTop: 20 }} aria-labelledby="rev-h">
        <h2 id="rev-h">Inspect it yourself — no wallet needed</h2>
        <ol>
          <li><Link to="/explore">Open a Warranty Passport</Link> and read its frozen clauses and fingerprint.</li>
          <li>Follow a claim: evidence locker, structured adjudication, Application Challenge history.</li>
          <li>Open the public <strong>Resolution Receipt</strong> and verify every fingerprint against the contract.</li>
        </ol>
        <p className="small muted">Two things are deliberately separate: an <strong>Application Challenge</strong> is CLAUSE&apos;s own one-time review of a decision; <strong>GenLayer Protocol Finality</strong> is the network confirming a transaction. CLAUSE never merges the two.</p>
      </section>
    </>
  );
}
