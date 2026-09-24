import { Link } from "react-router-dom";

/** V1 limitations, stated plainly. Linked from the footer and from the decision points where they matter. */
export function Limits() {
  return (
    <div className="stack">
      <h1 style={{ fontSize: "2rem" }}>V1 limits, stated plainly</h1>
      <p className="muted">CLAUSE V1 makes deliberate trade-offs. They are listed here so nobody discovers them at the moment of a dispute.</p>
      <section className="plate" aria-labelledby="l1"><h2 id="l1">Evidence</h2>
        <ul>
          <li><strong>Maximum 10 adjudicable evidence records per claim.</strong> Extra eligible submissions are rejected before they can enter the frozen set; nothing is silently truncated.</li>
          <li><strong>Evidence slots are first-come.</strong> Whichever party submits eligible evidence first uses the slots; a slot cannot be freed. Ineligible URLs use no slot but are never adjudicated.</li>
          <li><strong>Unavailable evidence is not negative evidence.</strong> A failed retrieval is never treated as proof against either party; the frozen terms decide what follows (rule for holder, for manufacturer, or block).</li>
          <li>Only https sources permitted by the frozen source policy are ever retrieved. Adjudication never browses.</li>
        </ul></section>
      <section className="plate" aria-labelledby="l2"><h2 id="l2">Money</h2>
        <ul>
          <li><strong>A warranty&apos;s maximum remedy is a lifetime cap across all its claims.</strong> Overlapping claims are settled first-settled, first-served; a later claim can be capped, possibly to zero.</li>
          <li>The remedy always comes from the precommitted table by plain code. Validators and models never choose an amount, a percentage or a recipient.</li>
          <li>Settlement authorizes a claimable amount; the holder then withdraws it (pull payment). Reserved capacity cannot be withdrawn by the manufacturer.</li>
        </ul></section>
      <section className="plate" aria-labelledby="l3"><h2 id="l3">Cancellation</h2>
        <p className="banner bad"><strong>Warranties are not irrevocable in V1.</strong> The manufacturer (or the holder) can cancel a warranty at any time while no claim on it is unsettled. A cancelled warranty stops covering new claims and its reserved capacity is released. Cancellation is always shown on the passport. This is flagged for release review.</p></section>
      <section className="plate" aria-labelledby="l4"><h2 id="l4">Challenges and finality</h2>
        <ul>
          <li><strong>Application Challenge</strong> is CLAUSE&apos;s own mechanism: one per claim, bounded grounds, only frozen evidence. It is not a GenLayer Protocol Appeal.</li>
          <li><strong>GenLayer Protocol Finality</strong> is the network confirming a transaction. The contract cannot check it, so this app verifies it before finalizing, settling or withdrawing, and fails closed when it is uncertain.</li>
          <li>The contract does not store transaction hashes. For a step sent from another browser you can paste its hash to verify it.</li>
        </ul></section>
      <p><Link className="btn" to="/explore">Explore warranties</Link></p>
    </div>
  );
}

export function NotFound() {
  return (
    <section className="plate" role="status"><h1 style={{ fontSize: "1.8rem" }}>Page not found</h1><p>That page does not exist.</p><Link className="btn" to="/">Back home</Link></section>
  );
}
