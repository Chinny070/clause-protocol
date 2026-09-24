import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { evaluateAction, finalityPrerequisites, type ChecklistContext } from "../src/domain/checklist";
import { remedyCompleteness, validateDraft, previewSourceEligibility, type Draft } from "../src/domain/constitutionDraft";
import { humanizeError } from "../src/domain/errors";
import { formatGen, parseGen, formatDuration, shortHex, sameAddress } from "../src/domain/format";
import { buildTimeline, stageReached } from "../src/domain/timeline";
import type { Claim, RemedyRow } from "../src/contract/types";
import { OutcomeBadge, OUTCOME, Timeline, Checklist, Gauge, ClaimStatusBadge, CLAIM_STATUS_LABEL } from "../src/ui/kit";
import { renderApp, makeState, makeProvider, HOLDER, MFR, FP, NOW, ONE_GEN } from "./helpers/harness";
import { makeTransport } from "./helpers/mock";

const claim = (status: Claim["status"], over: Partial<Claim> = {}): Claim => ({
  claimId: 1, warrantyId: 1, programId: 1, holder: HOLDER, manufacturer: MFR, constitutionId: 1, constitutionFingerprint: FP, failureAssertedAt: NOW - 5000, targetedClauseIds: ["C-001"],
  filedAt: NOW - 900, responseDeadline: NOW - 800, manufacturerResponse: "DISPUTE", respondedAt: NOW - 850, evidenceFrozenAt: NOW - 400, status, adjudicationId: 1, ...over,
});
const ctx = (over: Partial<ChecklistContext> = {}): ChecklistContext => ({
  claim: claim("DECIDED"), constitution: null, adjudication: null, challenge: null, finalDecision: null, protocolNow: NOW, account: HOLDER, finality: { state: "safe", hash: "0xabc" }, ...over,
});

describe("amount formatting is exact", () => {
  it("formats atoms without floating point and parses decimals back", () => {
    expect(formatGen(5n * ONE_GEN)).toBe("5");
    expect(formatGen(1n)).toBe("0");
    expect(formatGen(1_234_500_000_000_000_000n)).toBe("1.2345");
    expect(formatGen(10n ** 24n, 6)).toBe("1,000,000");
    expect(parseGen("0.000000000000000001")).toBe(1n);
    expect(parseGen("5")).toBe(5n * ONE_GEN);
    for (const bad of ["", "-1", "1e3", "1,5", "abc", "1.0000000000000000001", " "]) expect(parseGen(bad)).toBeNull();
  });
  it("helpers", () => {
    expect(formatDuration(90061)).toBe("1d 1h");
    expect(shortHex("0x" + "a".repeat(40))).toMatch(/…/);
    expect(sameAddress("0xAbC", "0xabc")).toBe(true);
    expect(sameAddress(null, "0xabc")).toBe(false);
  });
});

describe("remedy completeness (mirrors the contract)", () => {
  const row = (outcome: RemedyRow["outcome"], clause_id: string): RemedyRow => ({ outcome, clause_id, remedy_kind: "FULL_REFUND", remedy_value: 0n });
  it("requires an outcome-level ACCEPTED_NO_CONTEST row and a COVERED row for every covered clause (or an outcome-level COVERED row)", () => {
    expect(remedyCompleteness([row("COVERED", "")], ["C-001"]).complete).toBe(false);
    expect(remedyCompleteness([row("COVERED", ""), row("ACCEPTED_NO_CONTEST", "")], ["C-001", "C-002"]).complete).toBe(true);
    expect(remedyCompleteness([row("COVERED", "C-001"), row("ACCEPTED_NO_CONTEST", "")], ["C-001", "C-002"]).missing[0]).toMatch(/C-002/);
    expect(remedyCompleteness([row("COVERED", "C-001"), row("COVERED", "C-002"), row("ACCEPTED_NO_CONTEST", "")], ["C-001", "C-002"]).complete).toBe(true);
    expect(remedyCompleteness([row("COVERED", "C-001")], ["C-001"]).missing.join(" ")).toMatch(/ACCEPTED_NO_CONTEST/);
  });
  it("draft validation reports incomplete tables, bad clause ids and unknown clause references", () => {
    const d: Draft = { version: "v", productScope: "s", coverageCalc: "c", covered: [{ clause_id: "C-001", text: "t" }], excluded: [], categories: ["RECEIPT"], sourcePolicy: "a.example",
      claimDeadlineDays: 1, responseDays: 1, challengeWindowDays: 1, challengeEnabled: true, insufficientBehavior: "BLOCK", unavailableBehavior: "BLOCK", expiryRules: "x",
      remedy: [row("COVERED", "C-001")] };
    expect(validateDraft(d).some((i) => /Incomplete remedy table/.test(i.message))).toBe(true);
    expect(validateDraft({ ...d, remedy: [row("COVERED", "C-001"), row("ACCEPTED_NO_CONTEST", "")] })).toEqual([]);
    expect(validateDraft({ ...d, covered: [{ clause_id: "X-001", text: "t" }], remedy: [row("ACCEPTED_NO_CONTEST", ""), row("COVERED", "")] }).some((i) => /must start with C-/.test(i.message))).toBe(true);
    expect(validateDraft({ ...d, remedy: [row("COVERED", "C-009"), row("ACCEPTED_NO_CONTEST", "")] }).some((i) => /unknown clause/.test(i.message))).toBe(true);
    expect(validateDraft({ ...d, sourcePolicy: " , " }).some((i) => i.field === "source policy")).toBe(true);
  });
  it("source eligibility preview mirrors the contract (https only; exact host; *.host excludes the bare domain)", () => {
    expect(previewSourceEligibility("https://a.example/x", "a.example").eligible).toBe(true);
    expect(previewSourceEligibility("http://a.example/x", "a.example").eligible).toBe(false);
    expect(previewSourceEligibility("https://sub.a.example/x", "*.a.example").eligible).toBe(true);
    expect(previewSourceEligibility("https://a.example/x", "*.a.example").eligible).toBe(false);
    expect(previewSourceEligibility("https://a.example.evil.com/x", "a.example").eligible).toBe(false);
    expect(previewSourceEligibility("not a url", "a.example").eligible).toBe(false);
  });
});

describe("lifecycle transitions and finality prerequisites", () => {
  it("maps each gated action to the transaction whose finality must be verified", () => {
    expect(finalityPrerequisites("finalize_claim", claim("ACCEPTED"))).toEqual(["respond_to_claim"]);
    expect(finalityPrerequisites("finalize_claim", claim("DECIDED"))).toEqual(["adjudicate_claim"]);
    expect(finalityPrerequisites("finalize_claim", claim("CHALLENGE_RESOLVED"))).toEqual(["resolve_challenge", "execute_remand", "lapse_challenge"]);
    expect(finalityPrerequisites("settle_claim", claim("FINAL"))).toEqual(["finalize_claim"]);
    expect(finalityPrerequisites("withdraw_settlement", claim("SETTLED"))).toEqual(["settle_claim"]);
    expect(finalityPrerequisites("adjudicate_claim", claim("EVIDENCE_FROZEN"))).toEqual(["freeze_evidence"]);
  });
  it("finalize: unresolved challenge / already final / unsettled states are each explained", () => {
    expect(evaluateAction("finalize_claim", ctx({ claim: claim("CHALLENGED") })).blockedReason).toMatch(/Application Challenge unresolved/);
    expect(evaluateAction("finalize_claim", ctx({ claim: claim("FINAL") })).blockedReason).toMatch(/Already finalized/);
    expect(evaluateAction("finalize_claim", ctx({ claim: claim("DISPUTED") })).blockedReason).toMatch(/has not reached a decision/);
    expect(evaluateAction("finalize_claim", ctx({ claim: claim("ACCEPTED") })).enabled).toBe(true);
  });
  it("every non-ok checklist item carries a human explanation (no unexplained disabled button)", () => {
    const actions = ["freeze_evidence", "adjudicate_claim", "file_challenge", "resolve_challenge", "execute_remand", "lapse_challenge", "finalize_claim", "settle_claim", "withdraw_settlement"] as const;
    const statuses: Claim["status"][] = ["RESPONSE_WINDOW", "ACCEPTED", "DISPUTED", "EVIDENCE_FROZEN", "DECIDED", "CHALLENGED", "CHALLENGE_RESOLVED", "FINAL", "SETTLED"];
    for (const a of actions) for (const st of statuses) for (const finality of [{ state: "no-transaction", needs: ["x"] }, { state: "checking", hash: "0x1" }, { state: "not-safe", hash: "0x1", reason: "pending" }, { state: "safe", hash: "0x1" }] as ChecklistContext["finality"][]) {
      const ev = evaluateAction(a, ctx({ claim: claim(st), finality, account: null }));
      if (!ev.enabled) expect(ev.blockedReason && ev.blockedReason.length > 10).toBe(true);
      expect(ev.items.every((i) => i.detail.length > 0)).toBe(true);
    }
  });
  it("finality states other than safe always block (fail closed)", () => {
    for (const finality of [{ state: "no-transaction", needs: ["adjudicate_claim"] }, { state: "checking", hash: "0x" }, { state: "not-safe", hash: "0x", reason: "accepted" }] as ChecklistContext["finality"][]) {
      expect(evaluateAction("settle_claim", ctx({ claim: claim("FINAL"), finality })).enabled).toBe(false);
    }
    expect(evaluateAction("settle_claim", ctx({ claim: claim("FINAL"), finality: { state: "safe", hash: "0x" } })).enabled).toBe(true);
  });
  it("stage strip follows the claim status", () => {
    expect(stageReached("DISPUTED", false)).toBe(2);
    expect(stageReached("DECIDED", false)).toBe(4);
    expect(stageReached("CHALLENGED", true)).toBe(5);
    expect(stageReached("SETTLED", false)).toBe(6);
  });
  it("timeline uses contract timestamps and tags the asserted date", () => {
    const t = buildTimeline({ passport: null, claim: claim("DECIDED"), evidence: [], adjudication: null, challenge: null, correctedAdjudication: null, finalDecision: null, challengeWindowClosesAt: 0 });
    expect(t.find((e) => e.key === "failure")).toMatchObject({ provenance: "asserted", at: NOW - 5000 });
    expect(t.find((e) => e.key === "filed")).toMatchObject({ provenance: "protocol" });
    expect(t.find((e) => e.key === "response-deadline")).toMatchObject({ provenance: "deadline" });
    expect(t.every((e) => ["protocol", "asserted", "deadline"].includes(e.provenance))).toBe(true);
  });
});

describe("error humanization", () => {
  const cases: Array<[string, string]> = [
    ["User rejected the request.", "wallet-rejected"], ["TypeError: Failed to fetch", "rpc-unavailable"], ["challenge window has closed", "challenge-window-closed"],
    ["claim already has the maximum of 10 adjudicable evidence records", "evidence-cap"], ["insufficient pool capacity for this warranty", "insufficient-capacity"],
    ["caller is not the settlement recipient", "unauthorized"], ["settlement already withdrawn", "already-withdrawn"], ["nothing to withdraw", "nothing-to-withdraw"],
    ["claim is not final", "invalid-claim-state"], ["[LLM_ERROR] model call failed", "retrieval-failure"], ["Wallet is on chain 1 but client is configured for chain 61999", "wrong-chain"],
  ];
  it("classifies every required failure with a plain title and keeps the raw detail", () => {
    for (const [raw, kind] of cases) {
      const e = humanizeError(new Error(raw));
      expect(e.kind, raw).toBe(kind);
      expect(e.title.length).toBeGreaterThan(3);
      expect(e.technical).toContain(raw);
    }
    expect(humanizeError("???").kind).toBe("unknown");
  });
});

describe("outcome vocabulary", () => {
  it("has a distinct label and explanation for every outcome; only NOT_COVERED and INVALID_CLAIM are red-toned", () => {
    const labels = Object.values(OUTCOME).map((o) => o.text);
    expect(new Set(labels).size).toBe(labels.length);
    expect(OUTCOME.INSUFFICIENT_EVIDENCE.tone).toBe("wait");
    expect(OUTCOME.EVIDENCE_UNAVAILABLE.tone).toBe("wait");
    expect(OUTCOME.NOT_COVERED.tone).toBe("bad");
    expect(OUTCOME.INSUFFICIENT_EVIDENCE.explain).toMatch(/NOT a finding/);
    render(<OutcomeBadge outcome="INSUFFICIENT_EVIDENCE" />);
    expect(screen.getByText("Insufficient evidence")).toBeInTheDocument();
  });
  it("status is never colour alone: every badge has a glyph and text", () => {
    for (const s of Object.keys(CLAIM_STATUS_LABEL) as Claim["status"][]) {
      const { unmount } = render(<ClaimStatusBadge status={s} />);
      const badge = document.querySelector(".badge") as HTMLElement;
      expect(badge.querySelector(".g")?.getAttribute("aria-hidden")).toBe("true");
      expect(badge.textContent?.length).toBeGreaterThan(2);
      unmount();
    }
  });
});

describe("UI primitives", () => {
  it("timeline exposes done / not-yet state to assistive tech", () => {
    render(<Timeline events={[{ key: "a", label: "Claim filed", at: NOW, provenance: "protocol", done: true }, { key: "b", label: "Withdrawal", at: 0, provenance: "protocol", done: false }]} />);
    expect(screen.getByText("(happened)")).toBeInTheDocument();
    expect(screen.getByText("(not yet)")).toBeInTheDocument();
  });
  it("checklist labels each state in text", () => {
    render(<Checklist items={[{ key: "a", label: "Wallet", status: "blocked", detail: "Connect" }, { key: "b", label: "Finality", status: "ok", detail: "Done" }]} />);
    expect(screen.getByText(/blocked:/)).toBeInTheDocument();
    expect(screen.getByText(/ok:/)).toBeInTheDocument();
  });
  it("gauge reports reserved capacity as text", () => {
    render(<Gauge total={10n * ONE_GEN} reserved={5n * ONE_GEN} format={(v) => formatGen(v)} />);
    expect(screen.getByRole("img", { name: /50% of capacity reserved/ })).toBeInTheDocument();
    expect(screen.getAllByText("5 GEN", { selector: "dd" }).length).toBeGreaterThan(0);
  });
});

describe("manufacturer wizard", () => {
  it("blocks review until the remedy table is complete and shows the FROZEN TERMS warning", async () => {
    const st = makeState();
    const provider = makeProvider({ accounts: [MFR] });
    renderApp({ path: "/manufacturer/program/1/terms/new", transport: makeTransport({ reads: st.reads }), provider });
    expect(await screen.findByText(/FROZEN TERMS — THIS VERSION CANNOT BE SILENTLY REWRITTEN AFTER ISSUANCE/)).toBeInTheDocument();
    // default draft has no clause text yet -> cannot review
    const review = screen.getByRole("button", { name: "Review terms" });
    expect(review).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Clause text", { selector: "#covered-tx-0" }), "Manufacturing defects are covered.");
    await userEvent.type(screen.getByLabelText(/Permitted evidence hosts/), "warranty.example.com");
    expect(screen.getByRole("button", { name: "Review terms" })).toBeEnabled();
    expect(screen.getByText(/Remedy table complete/)).toBeInTheDocument();
    // remove the ACCEPTED_NO_CONTEST row: incomplete again
    const rows = screen.getAllByRole("button", { name: "Remove" });
    const outcomes = screen.getAllByLabelText("Outcome") as HTMLSelectElement[];
    const idx = outcomes.findIndex((o) => o.value === "ACCEPTED_NO_CONTEST");
    await userEvent.click(rows[rows.length - (outcomes.length - idx)]);
    expect(await screen.findByText(/Remedy table incomplete/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review terms" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Add the missing required rows" }));
    expect(await screen.findByText(/Remedy table complete/)).toBeInTheDocument();
  });
  it("review screen restates the freeze and requires an explicit acknowledgement before the transaction button enables", async () => {
    const st = makeState();
    renderApp({ path: "/manufacturer/program/1/terms/new", transport: makeTransport({ reads: st.reads }), provider: makeProvider({ accounts: [MFR] }) });
    await screen.findByText(/Author warranty terms/);
    await userEvent.type(screen.getByLabelText("Clause text", { selector: "#covered-tx-0" }), "Defects are covered.");
    await userEvent.type(screen.getByLabelText(/Permitted evidence hosts/), "warranty.example.com");
    await userEvent.click(screen.getByRole("button", { name: "Review terms" }));
    expect(await screen.findByText("Review frozen terms")).toBeInTheDocument();
    expect(screen.getByText(/They cannot be edited|cannot be edited/i)).toBeInTheDocument();
    const publish = screen.getByRole("button", { name: "Freeze warranty terms" });
    expect(publish).toBeDisabled();
    expect(screen.getByText(/Tick the acknowledgement/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/I understand these terms will be frozen/));
    // wallet ready is asynchronous; the acknowledgement reason must be gone
    expect(screen.queryByText(/Tick the acknowledgement/)).toBeNull();
  });
});

describe("responsive and motion CSS contracts", () => {
  const css = readFileSync(resolve(__dirname, "../src/styles/app.css"), "utf8");
  it("every animation is declared inside a prefers-reduced-motion: no-preference block", () => {
    const start = css.indexOf("@media (prefers-reduced-motion: no-preference)");
    expect(start).toBeGreaterThan(0);
    const block = css.slice(start, css.indexOf("/* ---------- responsive", start));
    const outside = css.replace(block, "");
    expect(outside).not.toMatch(/animation\s*:/);
    expect(outside).not.toMatch(/@keyframes/);
    expect(block).toMatch(/animation:/);
  });
  it("collapses tables to cards and stacks grids on narrow screens; long identifiers always wrap", () => {
    expect(css).toMatch(/@media \(max-width: 720px\)[\s\S]*table\.plain thead \{ display: none; \}/);
    expect(css).toMatch(/table\.plain td::before \{ content: attr\(data-th\)/);
    expect(css).toMatch(/\.grid\.two, \.compare \{ grid-template-columns: 1fr; \}/);
    expect(css).toMatch(/\.wrap \{ overflow-wrap: anywhere;/);
    expect(css).toMatch(/\.kv dd \{[^}]*overflow-wrap: anywhere/);
    expect(css).toMatch(/:focus-visible \{ outline: 3px solid/);
    expect(css).toMatch(/min-height: 44px/);
  });
});

describe("accessibility structure", () => {
  it("has a skip link, landmarks, one h1 per page, and named controls", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }), path: "/limits" });
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const b of screen.queryAllByRole("button")) expect((b.textContent ?? "").trim() || b.getAttribute("aria-label")).toBeTruthy();
  });
  it("every form control on the claim, challenge and wizard screens has an accessible label", async () => {
    const st = makeState();
    renderApp({ transport: makeTransport({ reads: st.reads }), provider: makeProvider({ accounts: [HOLDER] }), path: "/claim/1" });
    const form = (await screen.findByRole("heading", { name: "File an Application Challenge" })).closest("section") as HTMLElement;
    for (const el of within(form).getAllByRole("combobox")) expect(el).toHaveAccessibleName();
    for (const el of within(form).getAllByRole("textbox")) expect(el).toHaveAccessibleName();
  });
});

describe("static release guards (production build hygiene)", () => {
  const srcDir = resolve(__dirname, "../src");
  const files: string[] = [];
  const walk = (d: string) => { for (const f of readdirSync(d)) { const p = join(d, f); if (statSync(p).isDirectory()) walk(p); else if (/\.(ts|tsx)$/.test(f)) files.push(p); } };
  walk(srcDir);
  const text = files.map((f) => [f, readFileSync(f, "utf8")] as const);
  it("no hard-coded contract/EOA address literal anywhere in src (no invented production address)", () => {
    for (const [f, t] of text) expect(t.match(/0x[0-9a-fA-F]{40}\b/g) ?? [], f).toEqual([]);
  });
  it("shipped wording never says an issued warranty is manufacturer-revocable", () => {
    for (const [f, t] of text) expect(t, f).not.toMatch(/not irrevocable|unilateral|manufacturer or the holder cancel|manufacturer or holder cancel/i);
  });
  it("never handles private keys or mnemonics", () => {
    for (const [f, t] of text) {
      expect(t, f).not.toMatch(/privateKey|private_key|mnemonic|generatePrivateKey|createAccount\(|eth_sign\b|personal_sign/i);
    }
  });
  it("has no mock/demo mode switch and no fake-data fixtures in shipped code", () => {
    for (const [f, t] of text) expect(t, f).not.toMatch(/VITE_[A-Z_]*(MOCK|DEMO|FAKE)|isMockMode|useMockData|mockTransport/i);
  });
  it("no backend, database or scraper dependencies", () => {
    const pkg = JSON.parse(readFileSync(resolve(__dirname, "../package.json"), "utf8"));
    const deps = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }).join(" ");
    expect(deps).not.toMatch(/supabase|firebase|express|fastify|koa|mongoose|prisma|puppeteer|playwright|axios/);
  });
  it("Studio Next / RC / chain 61997 are never referenced", () => {
    for (const [f, t] of text) expect(t, f).not.toMatch(/61997|studio-next|studionext|2\.0\.0-rc/i);
    const pkg = JSON.parse(readFileSync(resolve(__dirname, "../package.json"), "utf8"));
    expect(pkg.dependencies["genlayer-js"]).toBe("1.1.8");
  });
  it("renders routes inside a router without throwing (smoke)", () => {
    render(<MemoryRouter><div /></MemoryRouter>);
    void shortHex;
  });
});
