import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { STUDIONET } from "../src/config/networks";
import type { ContractConfig } from "../src/config/contract";
import { ADDR, CONFIGURED, FP, HOLDER, MFR, NOW, ONE_GEN, finalDecision, makeState, renderApp } from "./helpers/harness";
import { makeTransport } from "./helpers/mock";

const notConfigured: ContractConfig = { status: "not-configured", reason: "No canonical CLAUSE contract address has been configured for this build (VITE_CLAUSE_CONTRACT_ADDRESS is unset).", network: STUDIONET };

describe("contract configuration states", () => {
  it("not configured: explains itself, reads nothing, invents no address", async () => {
    const t = makeTransport({ reads: {} });
    renderApp({ config: notConfigured, transport: t, path: "/explore" });
    expect(await screen.findByText(/Contract not configured/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing to read/i)).toBeInTheDocument();
    expect(t.calls.reads).toEqual([]);
  });
  it("invalid address is shown as an error, not silently ignored", () => {
    renderApp({ config: { status: "invalid", reason: "The configured contract address is not a valid non-zero EVM address.", raw: "0x123", network: STUDIONET } });
    expect(screen.getByRole("alert")).toHaveTextContent(/Invalid contract address/i);
  });
  it("network configuration errors are shown", () => {
    renderApp({ config: { status: "network-error", reason: "localnet is a development-only target" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/Network configuration error/i);
  });
  it("RPC unavailable is distinguished from a contract read failure", async () => {
    const down = makeTransport({ reads: { now: () => { throw new Error("TypeError: Failed to fetch"); } } });
    renderApp({ transport: down });
    expect(await screen.findByText(/RPC unavailable/i)).toBeInTheDocument();
    const bad = makeTransport({ reads: { now: () => { throw new Error("contract not found"); } } });
    renderApp({ transport: bad });
    expect(await screen.findByText(/Contract read failed/i)).toBeInTheDocument();
  });
  it("a valid configured contract shows the live program count on the landing page", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }) });
    expect(await screen.findByText(/Live on .*1 warranty program/i)).toBeInTheDocument();
  });
});

describe("landing page (no wallet)", () => {
  it("states the thesis, both CTAs, the lifecycle and the trust comparison", () => {
    renderApp({ config: notConfigured });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/THE PRODUCT BROKE\.\s*THE RULES DON'T GET TO CHANGE NOW\./i);
    expect(screen.getByRole("link", { name: "Explore warranties" })).toHaveAttribute("href", "/explore");
    expect(screen.getByRole("link", { name: "Register a warranty" })).toHaveAttribute("href", "/manufacturer");
    for (const s of ["Terms frozen", "Product registered", "Claim filed", "Evidence frozen", "GenLayer decision", "Challenge", "Final remedy"]) expect(screen.getAllByText(s).length).toBeGreaterThan(0);
    expect(screen.getByText("Manufacturer interprets terms")).toBeInTheDocument();
    expect(screen.getByText("Validator consensus")).toBeInTheDocument();
    expect(screen.getAllByText(/Application Challenge/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/GenLayer Protocol Finality/).length).toBeGreaterThan(0);
  });
});

describe("public warranty explorer + passport", () => {
  it("lists passports from the contract and opens a passport with frozen terms and the fingerprint", async () => {
    const { reads } = makeState();
    const t = makeTransport({ reads });
    renderApp({ transport: t, path: "/explore" });
    const card = await screen.findByLabelText("Passport 1");
    expect(within(card).getByText(/WIDGET-X-001/)).toBeInTheDocument();
    expect(card).toHaveTextContent(FP);
    expect(within(card).getByText("Frozen")).toBeInTheDocument();
  });
  it("passport page: FROZEN TERMS, fingerprint, clauses, exclusions, remedy table, capacity, issued-warranty commitment notice", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }), path: "/passport/1" });
    expect(await screen.findByLabelText("Warranty passport 1")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /frozen terms/i }).length).toBeGreaterThan(0);
    expect(screen.getByText(/cannot be silently rewritten after issuance/i)).toBeInTheDocument();
    expect(screen.getAllByText(FP).length).toBeGreaterThan(0);
    expect(screen.getByText(/Manufacturing defects are covered/)).toBeInTheDocument();
    expect(screen.getByText(/Water damage is excluded/)).toBeInTheDocument();
    expect(screen.getByText(/Precommitted remedy table/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Full refund \(warranty maximum\)/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/5 GEN/, { selector: "dd" }).length).toBeGreaterThan(0);
    expect(screen.getByText(/ISSUED WARRANTY — TERMS FROZEN/)).toBeInTheDocument();
    expect(screen.getByText(/the manufacturer cannot cancel, shorten or rewrite it/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/not irrevocable|manufacturer or the holder cancel/i);
    expect(screen.getByText(/Warranty capacity/i)).toBeInTheDocument();
  });
  it("cancellation status and history are surfaced on a cancelled passport", async () => {
    const st = makeState();
    st.s.passportStatus = "CANCELLED";
    renderApp({ transport: makeTransport({ reads: st.reads }), path: "/passport/1" });
    expect(await screen.findByText(/This warranty was cancelled by its holder/)).toBeInTheDocument();
    expect(screen.getByText(/capacity was released at/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Cancelled/i).length).toBeGreaterThan(0);
  });
  it("unknown ids show not-found, not an error", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }), path: "/passport/99" });
    expect(await screen.findByText(/not found/i)).toBeInTheDocument();
  });
});

describe("claim page: evidence locker", () => {
  it("shows every evidence record with distinct AVAILABLE / FETCH_FAILED / INELIGIBLE / FROZEN states and honest explanations", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }), path: "/claim/1" });
    const ev1 = await screen.findByLabelText("Evidence 1");
    expect(within(ev1).getByText("Available")).toBeInTheDocument();
    expect(within(ev1).getByText("Frozen")).toBeInTheDocument();
    expect(ev1).toHaveTextContent("https://docs.example.com/receipt");
    expect(ev1).toHaveTextContent(/Fingerprint/);
    const ev2 = screen.getByLabelText("Evidence 2");
    expect(within(ev2).getByText("Fetch failed")).toBeInTheDocument();
    expect(ev2).toHaveTextContent(/does NOT mean the claim is false/);
    expect(ev2).toHaveTextContent(/not treated as proof against either party/);
    const ev3 = screen.getByLabelText("Evidence 3");
    expect(within(ev3).getByText("Ineligible source")).toBeInTheDocument();
    expect(within(ev3).getByText("Not frozen")).toBeInTheDocument();
    expect(screen.getByText(/2 \/ 10/)).toBeInTheDocument();
    expect(screen.getAllByText(/Maximum 10 adjudicable evidence records per claim/).length).toBeGreaterThan(0);
  });
});

describe("claim page: structured adjudication", () => {
  it("renders each frozen schema field and keeps INSUFFICIENT_EVIDENCE distinct from NOT_COVERED", async () => {
    const st = makeState();
    renderApp({ transport: makeTransport({ reads: st.reads }), path: "/claim/1" });
    const adj = await screen.findByRole("region", { name: /Original adjudication/i });
    for (const label of ["Product match", "Warranty version match", "Coverage window", "Source authority", "Evidence sufficiency"]) expect(within(adj).getByText(label)).toBeInTheDocument();
    expect(within(adj).getByText("Insufficient evidence")).toBeInTheDocument();
    expect(within(adj).getByText(/This is NOT a finding that the claim is false/)).toBeInTheDocument();
    expect(within(adj).queryByText(/Not covered/)).toBeNull();
    expect(within(adj).getByText(/Relied on: #1/)).toBeInTheDocument();
    expect(within(adj).getByText(/The receipt does not show a defect\./)).toBeInTheDocument();
    expect(within(adj).getByText(/Validators compare the structured findings above, never the prose/)).toBeInTheDocument();
  });
  it("NOT_COVERED, EVIDENCE_UNAVAILABLE and INVALID_CLAIM each have their own wording", async () => {
    for (const [outcome, text] of [["NOT_COVERED", "Not covered"], ["EVIDENCE_UNAVAILABLE", "Evidence unavailable"], ["INVALID_CLAIM", "Invalid claim"]] as const) {
      const st = makeState();
      st.s.adjudication = { ...st.s.adjudication, outcome };
      const { unmount } = renderApp({ transport: makeTransport({ reads: st.reads }), path: "/claim/1" });
      const adj = await screen.findByRole("region", { name: /Original adjudication/i });
      expect(within(adj).getAllByText(text).length).toBeGreaterThan(0);
      unmount();
    }
  });
  it("shows the diagnostic timeline with provenance tags and the claimant-asserted date marked unverified", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }), path: "/claim/1" });
    const tl = await screen.findByRole("list", { name: /Diagnostic timeline/i });
    expect(within(tl).getByText(/Failure date asserted by claimant/)).toBeInTheDocument();
    expect(within(tl).getAllByText("Claimant-asserted").length).toBeGreaterThan(0);
    expect(within(tl).getAllByText("Protocol time").length).toBeGreaterThan(0);
    expect(within(tl).getAllByText("Deadline").length).toBeGreaterThan(0);
    expect(within(tl).getByText(/Application Challenge window opened/)).toBeInTheDocument();
  });
});

describe("Application Challenge history is visible publicly", () => {
  it("shows ground, explanation, result and never calls it an appeal", async () => {
    const st = makeState();
    st.s.claimStatus = "CHALLENGE_RESOLVED";
    st.s.challenge = { challenge_id: 1, claim_id: 1, adjudication_id: 1, challenger: HOLDER, ground: "WRONG_CLAUSE", explanation: "C-001 covers this failure.", citation: { evidence_ids: [], clause_ids: ["C-001"], constitution_id: 0, timestamp_field: "" },
      filed_at: NOW - 50, status: "RESOLVED", result: "UPHELD", resolution_path: "SEMANTIC", resolution_reason: "No material error.", remand_issue: "", corrected_adjudication_id: 0, resolved_at: NOW - 10 };
    renderApp({ transport: makeTransport({ reads: st.reads }), path: "/claim/1" });
    const c = await screen.findByRole("region", { name: /Application Challenge/i });
    expect(c).toHaveTextContent("Wrong clause");
    expect(c).toHaveTextContent(/Upheld/);
    expect(c).toHaveTextContent(/not a GenLayer Protocol Appeal/);
    expect(c).toHaveTextContent("C-001 covers this failure.");
    expect(document.body.textContent).not.toMatch(/\bfile an appeal\b/i);
  });
});

describe("Resolution Receipt (public, no wallet)", () => {
  it("renders the full receipt: fingerprints, clauses, evidence fingerprints, original + corrected decision, remedy, settlement, withdrawal", async () => {
    const st = makeState();
    st.s.receipt = {
      claim_id: 1, claim_status: "SETTLED",
      warranty: { warranty_id: 1, holder: HOLDER, manufacturer: MFR, product_model_id: "WIDGET-X-001", coverage_start: NOW - 8000, coverage_end: NOW + 100000, max_deterministic_remedy: (5n * ONE_GEN).toString(), constitution_id: 1, constitution_version: "2026.1", constitution_fingerprint: FP },
      claim: { targeted_clause_ids: ["C-001"], filed_at: NOW - 900, manufacturer_response: "DISPUTE", responded_at: NOW - 850, evidence_frozen_at: NOW - 400 },
      evidence: [{ evidence_id: 1, category: "RECEIPT", host: "docs.example.com", retrieval_status: "AVAILABLE", fingerprint: "ab".repeat(32), frozen_at: NOW - 400 }], ineligible_evidence_count: 1,
      original_adjudication: { ...st.s.adjudication, superseded: true },
      challenge: { challenge_id: 1, claim_id: 1, adjudication_id: 1, challenger: HOLDER, ground: "WRONG_CLAUSE", explanation: "x", citation: { evidence_ids: [], clause_ids: ["C-001"], constitution_id: 0, timestamp_field: "" }, filed_at: NOW - 50, status: "RESOLVED", result: "REVERSED", resolution_path: "SEMANTIC", resolution_reason: "r", remand_issue: "", corrected_adjudication_id: 2, resolved_at: NOW - 10 },
      corrected_adjudication: { ...st.s.adjudication, adjudication_id: 2, outcome: "COVERED", covered_clause_ids: ["C-001"], evidence_sufficiency: "SUFFICIENT", decision_path: "CHALLENGE_CORRECTION", superseded: false },
      final_decision: finalDecision({ source: "CHALLENGE_CORRECTED", adjudication_id: 2, challenge_id: 1, settled_at: NOW - 30, settled_amount: (5n * ONE_GEN).toString(), claimable: 0, withdrawn_at: NOW - 5, withdrawn_amount: (5n * ONE_GEN).toString() }),
    };
    renderApp({ transport: makeTransport({ reads: st.reads }), path: "/receipt/1" });
    const r = await screen.findByLabelText(/Resolution receipt for claim 1/i);
    expect(r).toHaveTextContent(FP);
    expect(r).toHaveTextContent("fp " + "ab".repeat(32));
    expect(r).toHaveTextContent("1 ineligible");
    expect(r).toHaveTextContent(/Original adjudication · SUPERSEDED/);
    expect(r).toHaveTextContent("Corrected adjudication");
    expect(r).toHaveTextContent("Application Challenge");
    expect(r).toHaveTextContent("REVERSED");
    expect(r).toHaveTextContent("REMEDY5 GEN");
    expect(r).toHaveTextContent(/Withdrawn5 GEN/);
    expect(r).toHaveTextContent(/verify the transactions before relying on this receipt/i);
    expect(screen.queryByRole("button", { name: /connect wallet/i })).toBeNull();
  });
  it("missing receipts show not-found", async () => {
    const st = makeState();
    renderApp({ transport: makeTransport({ reads: st.reads }), path: "/receipt/7" });
    expect(await screen.findByText(/not found/i)).toBeInTheDocument();
  });
});

describe("V1 limitations are discoverable", () => {
  it("documents the 10-record cap, first-come slots, capacity, unavailable evidence, and that issued warranties are commitments", () => {
    renderApp({ config: CONFIGURED, transport: makeTransport({ reads: makeState().reads }), path: "/limits" });
    expect(screen.getByText(/Maximum 10 adjudicable evidence records per claim/)).toBeInTheDocument();
    expect(screen.getByText(/Evidence slots are first-come/)).toBeInTheDocument();
    expect(screen.getByText(/first-settled, first-served/i)).toBeInTheDocument();
    expect(screen.getByText(/Unavailable evidence is not negative evidence/)).toBeInTheDocument();
    expect(screen.getByText(/The manufacturer cannot cancel, shorten or rewrite a warranty once it is issued/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/not irrevocable|unilateral/i);
    void ADDR; void NOW;
  });
});
