import type { Adjudication, Challenge, Claim, Constitution, FinalDecision } from "../contract/types";
import { formatUtc, sameAddress } from "./format";

export type GatedAction =
  | "freeze_evidence" | "adjudicate_claim" | "file_challenge" | "resolve_challenge" | "execute_remand" | "lapse_challenge"
  | "finalize_claim" | "settle_claim" | "withdraw_settlement";

export type ItemStatus = "ok" | "blocked" | "checking" | "unverified";
export interface ChecklistItem { key: string; label: string; status: ItemStatus; detail: string }
export interface Evaluation { enabled: boolean; items: ChecklistItem[]; blockedReason: string | null }

/** GenLayer Protocol Finality verification state for the prerequisite transaction(s) of an action. */
export type FinalityState =
  | { state: "not-required" }
  | { state: "no-transaction"; needs: string[] }
  | { state: "checking"; hash: string }
  | { state: "safe"; hash: string }
  | { state: "not-safe"; hash: string; reason: string };

export interface ChecklistContext {
  claim: Claim;
  constitution: Constitution | null;
  adjudication: Adjudication | null;
  challenge: Challenge | null;
  finalDecision: FinalDecision | null;
  protocolNow: number;
  account: string | null;
  finality: FinalityState;
}

/** Transactions whose FINALITY must be verified (by the frontend) before an action. Contract cannot check this itself. */
export function finalityPrerequisites(action: GatedAction, claim: Claim): string[] {
  switch (action) {
    case "adjudicate_claim": return ["freeze_evidence"];
    case "file_challenge": return ["adjudicate_claim"];
    case "resolve_challenge": case "lapse_challenge": return ["file_challenge"];
    case "execute_remand": return ["resolve_challenge"];
    case "settle_claim": return ["finalize_claim"];
    case "withdraw_settlement": return ["settle_claim"];
    case "finalize_claim":
      if (claim.status === "ACCEPTED") return ["respond_to_claim"];
      if (claim.status === "DECIDED") return ["adjudicate_claim"];
      if (claim.status === "CHALLENGE_RESOLVED") return ["resolve_challenge", "execute_remand", "lapse_challenge"];
      return [];
    default: return [];
  }
}

function fin(ctx: ChecklistContext, label: string): ChecklistItem {
  const f = ctx.finality;
  switch (f.state) {
    case "not-required": return { key: "finality", label, status: "ok", detail: "No earlier transaction needs protocol finality." };
    case "no-transaction": return { key: "finality", label, status: "unverified",
      detail: `Waiting for GenLayer finality: no transaction hash is known for ${f.needs.join(" / ")}. Paste its hash under Protocol Finality to verify it (fails closed until then).` };
    case "checking": return { key: "finality", label, status: "checking", detail: `Checking transaction ${f.hash} on GenLayer…` };
    case "safe": return { key: "finality", label, status: "ok", detail: `Transaction ${f.hash} is Finalized with a successful execution.` };
    case "not-safe": return { key: "finality", label, status: "blocked", detail: `Waiting for GenLayer finality: ${f.reason}` };
  }
}

function item(key: string, label: string, ok: boolean, okDetail: string, blockedDetail: string): ChecklistItem {
  return { key, label, status: ok ? "ok" : "blocked", detail: ok ? okDetail : blockedDetail };
}

/** Explains, item by item, why an irreversible action is or is not available. A disabled button always has a reason here. */
export function evaluateAction(action: GatedAction, ctx: ChecklistContext): Evaluation {
  const { claim: c } = ctx;
  const items: ChecklistItem[] = [];
  const s = c.status;
  const finLabel = "GenLayer Protocol Finality of the previous step";

  switch (action) {
    case "freeze_evidence":
      items.push(item("state", "Claim is in the dispute / evidence phase", s === "DISPUTED" || (s === "RESPONSE_WINDOW" && ctx.protocolNow > c.responseDeadline),
        "Evidence submission can be closed.", s === "RESPONSE_WINDOW" ? `The manufacturer response window is still open until ${formatUtc(c.responseDeadline)}.` : `Claim is ${s}; evidence can only be frozen while disputed.`));
      break;
    case "adjudicate_claim":
      items.push(item("state", "Evidence is frozen", s === "EVIDENCE_FROZEN", "Frozen evidence is ready for adjudication.", s === "DISPUTED" || s === "RESPONSE_WINDOW" ? "Evidence has not been frozen yet." : `Claim is ${s}; it has already been adjudicated or is not in an adjudicable state.`));
      items.push(fin(ctx, finLabel));
      break;
    case "file_challenge": {
      const a = ctx.adjudication;
      items.push(item("state", "Claim is decided and not yet challenged", s === "DECIDED", "An Application Challenge can be filed.",
        s === "CHALLENGED" || s === "CHALLENGE_RESOLVED" ? "This claim already used its one Application Challenge." : `Claim is ${s}; nothing to challenge yet, or the decision is already final.`));
      if (ctx.constitution) items.push(item("depth", "Application Challenges are enabled by the frozen terms", ctx.constitution.challengeDepth >= 1, "Enabled.", "The frozen terms disable Application Challenges."));
      if (a) items.push(item("window", "Application Challenge window is open", ctx.protocolNow <= a.challengeWindowClosesAt, `Open until ${formatUtc(a.challengeWindowClosesAt)}.`, `The window closed at ${formatUtc(a.challengeWindowClosesAt)}.`));
      items.push(item("party", "You are the holder or manufacturer of this claim", !!ctx.account && (sameAddress(ctx.account, c.holder) || sameAddress(ctx.account, c.manufacturer)), "Authorized.", "Only the claim's holder or manufacturer can file."));
      items.push(fin(ctx, finLabel));
      break;
    }
    case "resolve_challenge":
    case "execute_remand":
    case "lapse_challenge": {
      const ch = ctx.challenge;
      const want = action === "execute_remand" ? "REMAND_PENDING" : "OPEN";
      const open = !!ch && (action === "lapse_challenge" ? ch.status !== "RESOLVED" : ch.status === want);
      items.push(item("state", action === "execute_remand" ? "A remand review is pending" : "The Application Challenge is unresolved", s === "CHALLENGED" && open, "Ready.", "There is no matching unresolved Application Challenge."));
      if (ch && ctx.constitution) {
        const deadline = ch.filedAt + ctx.constitution.challengeWindowS;
        if (action === "lapse_challenge") items.push(item("time", "Resolution period has elapsed", ctx.protocolNow > deadline, "The resolution period has elapsed.", `Available after ${formatUtc(deadline)}.`));
        else items.push(item("time", "Resolution period is still running", ctx.protocolNow <= deadline, `Open until ${formatUtc(deadline)}.`, "The resolution period has lapsed; use lapse instead."));
      }
      items.push(fin(ctx, finLabel));
      break;
    }
    case "finalize_claim": {
      const finalizable = s === "ACCEPTED" || s === "DECIDED" || s === "CHALLENGE_RESOLVED";
      items.push(item("state", "Claim is ready for a final application decision", finalizable,
        "Ready.", s === "CHALLENGED" ? "Application Challenge unresolved." : s === "FINAL" || s === "SETTLED" ? "Already finalized." : `Claim is ${s}; it has not reached a decision yet.`));
      if (s === "DECIDED" && ctx.adjudication && ctx.constitution && ctx.constitution.challengeDepth >= 1) {
        items.push(item("window", "Application Challenge window has closed", ctx.protocolNow > ctx.adjudication.challengeWindowClosesAt,
          "The window closed with no challenge.", `Application Challenge window still open until ${formatUtc(ctx.adjudication.challengeWindowClosesAt)}.`));
      }
      items.push(fin(ctx, finLabel));
      break;
    }
    case "settle_claim":
      items.push(item("state", "Final decision recorded", s === "FINAL", "Ready to authorize settlement.", s === "SETTLED" ? "Already settled." : "Final decision not yet finalized."));
      items.push(fin(ctx, "GenLayer Protocol Finality of the finalize transaction"));
      break;
    case "withdraw_settlement": {
      const f = ctx.finalDecision;
      items.push(item("state", "Settlement authorized", s === "SETTLED", "Settled.", "Settlement not finalized: the claim is not SETTLED yet."));
      items.push(item("amount", "There is claimable GEN", !!f && f.claimable > 0n, "Claimable GEN is available.", f && f.withdrawnAt > 0 ? "Already withdrawn." : "No claimable settlement for this claim."));
      items.push(item("recipient", "You are the recorded recipient", !!f && !!ctx.account && sameAddress(ctx.account, f.recipient), "You are the recipient.", "Only the recorded recipient (the warranty holder) can withdraw."));
      items.push(fin(ctx, "GenLayer Protocol Finality of the settlement transaction"));
      break;
    }
  }

  const blocked = items.find((x) => x.status !== "ok");
  return { enabled: blocked === undefined, items, blockedReason: blocked ? blocked.detail : null };
}
