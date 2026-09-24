import { useEffect, useId, useMemo, useState } from "react";
import { useClause, useTx, useWallet } from "../app/context";
import { loadClaimBundle, type ClaimBundle } from "../app/data";
import type { CallSpec } from "../contract/calls";
import { evaluateAction, finalityPrerequisites, type ChecklistItem, type FinalityState, type GatedAction } from "../domain/checklist";
import { resolveFinality } from "../tx/finality";
import { isTxHash } from "../tx/journal";
import { Checklist, Copyable } from "./kit";

/** Live GenLayer Protocol Finality verification of the prerequisite transaction(s) for an action (fail closed). */
export function useFinality(action: GatedAction, claim: ClaimBundle["claim"]) {
  const { readTransport, journal } = useClause();
  const [manual, setManual] = useState("");
  const [tick, setTick] = useState(0);
  const claimId = claim.claimId;
  const prereq = useMemo(() => finalityPrerequisites(action, claim), [action, claim]);
  const manualHash = isTxHash(manual) ? (manual.trim() as `0x${string}`) : undefined;
  const [finality, setFinality] = useState<FinalityState>(prereq.length === 0 ? { state: "not-required" } : { state: "checking", hash: "…" });
  useEffect(() => {
    let live = true;
    if (prereq.length === 0) { setFinality({ state: "not-required" }); return; }
    if (!readTransport) { setFinality({ state: "no-transaction", needs: prereq }); return; }
    setFinality({ state: "checking", hash: manualHash ?? journal.find(claimId, prereq)?.hash ?? "…" });
    void resolveFinality(readTransport, journal, claimId, prereq, manualHash).then((f) => { if (live) setFinality(f); });
    return () => { live = false; };
  }, [readTransport, journal, claimId, prereq, manualHash, tick, claim.status]);
  return { finality, manual, setManual, manualHash, prereq, recheck: () => setTick((t) => t + 1) };
}

interface Props {
  action: GatedAction;
  bundle: ClaimBundle;
  spec: CallSpec;
  onDone: () => void;
  description: string;
  variant?: "primary" | "plum" | "warn";
}

/**
 * One irreversible-or-gated step. The button is only enabled when EVERY checklist item is ok, and the checklist is always
 * visible so a disabled button is never unexplained. GenLayer Protocol Finality of the prerequisite transaction is verified
 * live from the network (fail closed); a receipt or hash alone never enables anything.
 */
export function GatedActionButton({ action, bundle, spec, onDone, description, variant = "primary" }: Props) {
  const { reader, protocolNow } = useClause();
  const wallet = useWallet();
  const tx = useTx();
  const reasonId = useId();
  const claimId = bundle.claim.claimId;
  const { finality, manual, setManual, manualHash, prereq, recheck } = useFinality(action, bundle.claim);
  const [confirming, setConfirming] = useState(false);

  const base = evaluateAction(action, {
    claim: bundle.claim, constitution: bundle.constitution, adjudication: bundle.adjudication, challenge: bundle.challenge,
    finalDecision: bundle.finalDecision, protocolNow: protocolNow(), account: wallet.address, finality,
  });
  const walletItem: ChecklistItem = {
    key: "wallet", label: "Wallet connected on GenLayer StudioNet", status: wallet.ready ? "ok" : "blocked",
    detail: wallet.ready ? "Ready to sign." : wallet.state.status === "wrong-network" ? "Wrong network: switch your wallet to StudioNet (61999)." : "Connect a wallet to send this transaction.",
  };
  const items = [...base.items, walletItem];
  const enabled = items.every((i) => i.status === "ok");
  const blocked = items.find((i) => i.status !== "ok");

  const go = async () => {
    setConfirming(false);
    await tx.run({ spec, claimId, reread: () => (reader ? loadClaimBundle(reader, claimId) : Promise.reject(new Error("no reader"))), onConfirmed: onDone });
  };
  const cls = variant === "plum" ? "btn plum" : variant === "warn" ? "btn warn" : "btn";

  return (
    <div className={variant === "plum" ? "challenge-plate" : "finality-plate"}>
      <p><strong>{spec.label}</strong> — {description}</p>
      {prereq.length > 0 ? (
        <details open={finality.state !== "safe"}>
          <summary>GenLayer Protocol Finality check</summary>
          <p className="small">Before this step the frontend verifies that <strong>{prereq.join(" / ")}</strong> is <em>Finalized</em> on GenLayer with a successful execution — not merely submitted or accepted. The contract cannot check this itself.</p>
          <div className="field">
            <label htmlFor={`${reasonId}-hash`}>Transaction hash to verify (optional)</label>
            <input id={`${reasonId}-hash`} value={manual} onChange={(e) => setManual(e.target.value)} placeholder="0x… (only needed if this browser did not send the earlier step)" spellCheck={false} />
            {manual !== "" && !manualHash ? <p className="err">Not a valid 66-character transaction hash.</p> : null}
          </div>
          <button type="button" className="btn small secondary" onClick={recheck}>Re-check finality</button>
        </details>
      ) : null}
      <Checklist items={items} />
      {!enabled && blocked ? <p id={reasonId} role="note" className="small"><strong>Why is this disabled?</strong> {blocked.detail}</p> : null}
      {confirming ? (
        <div className="banner bad" role="alertdialog" aria-label={`Confirm ${spec.label}`}>
          <p><strong>This step is irreversible.</strong> {description}{spec.value > 0n ? " It sends value." : ""} You will be asked to confirm in your wallet.</p>
          <div className="row"><button type="button" className={cls} onClick={() => void go()}>Yes, {spec.label.toLowerCase()}</button><button type="button" className="btn secondary" onClick={() => setConfirming(false)}>Cancel</button></div>
        </div>
      ) : (
        <p><button type="button" className={cls} disabled={!enabled} aria-describedby={!enabled ? reasonId : undefined}
          onClick={() => (spec.irreversible ? setConfirming(true) : void go())}>{spec.label}</button></p>
      )}
      {finality.state === "safe" ? <p className="small">Verified: <Copyable value={finality.hash} label="verified transaction hash" /></p> : null}
    </div>
  );
}

/** A simple (non finality-gated) transaction button with an explicit confirmation for irreversible steps. */
export function TxButton({ spec, description, reread, onDone, claimId, variant = "primary", disabledReason }: {
  spec: CallSpec; description: string; reread?: () => Promise<unknown>; onDone?: () => void; claimId?: number; variant?: "primary" | "plum" | "warn" | "secondary"; disabledReason?: string | null;
}) {
  const wallet = useWallet();
  const tx = useTx();
  const id = useId();
  const [confirming, setConfirming] = useState(false);
  const reason = disabledReason ?? (wallet.ready ? null : wallet.state.status === "wrong-network" ? "Wrong network: switch your wallet to StudioNet (61999)." : "Connect a wallet to send this transaction.");
  const cls = variant === "plum" ? "btn plum" : variant === "warn" ? "btn warn" : variant === "secondary" ? "btn secondary" : "btn";
  const go = async () => { setConfirming(false); await tx.run({ spec, claimId, reread, onConfirmed: () => onDone?.() }); };
  return (
    <div>
      {confirming ? (
        <div className="banner bad" role="alertdialog" aria-label={`Confirm ${spec.label}`}>
          <p><strong>Please confirm.</strong> {description}{spec.value > 0n ? " This sends GEN." : ""}</p>
          <div className="row"><button type="button" className={cls} onClick={() => void go()}>Yes, {spec.label.toLowerCase()}</button><button type="button" className="btn secondary" onClick={() => setConfirming(false)}>Cancel</button></div>
        </div>
      ) : (
        <button type="button" className={cls} disabled={reason !== null} aria-describedby={reason ? id : undefined} onClick={() => (spec.irreversible ? setConfirming(true) : void go())}>{spec.label}</button>
      )}
      {reason ? <p id={id} className="small" role="note"><strong>Why is this disabled?</strong> {reason}</p> : null}
    </div>
  );
}
