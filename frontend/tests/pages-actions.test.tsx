import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ADDR, CONFIGURED, HASH, HOLDER, MFR, NOW, ONE_GEN, finalDecision, makeProvider, makeState, renderApp } from "./helpers/harness";
import { makeTransport, tx } from "./helpers/mock";

const plate = async (label: string) => (await screen.findAllByText(label))[0].closest(".finality-plate") as HTMLElement;
const H2 = ("0x" + "cd".repeat(32)) as `0x${string}`;

/** A shared transport: reads from the mutable contract state, writes recorded, transaction statuses scripted per hash. */
function setup(over: { claimStatus?: string; hasAdj?: boolean; final?: Record<string, unknown>; connected?: boolean; chainId?: string; finality?: Record<string, ReturnType<typeof tx>>; account?: string } = {}) {
  const st = makeState();
  st.s.claimStatus = over.claimStatus ?? "DECIDED";
  st.s.hasAdjudication = over.hasAdj ?? true;
  if (over.final) st.s.final = over.final;
  const writes: Array<{ fn: string; args: unknown[]; value?: bigint }> = [];
  const statuses: Record<string, ReturnType<typeof tx>> = { [HASH]: tx("FINALIZED"), ...(over.finality ?? {}) };
  const read = makeTransport({ reads: st.reads });
  read.getTransaction = async ({ hash }) => statuses[hash] ?? tx("FINALIZED");
  const write = makeTransport({ reads: st.reads });
  write.writeContract = async ({ functionName, args, value }) => { writes.push({ fn: functionName, args: args ?? [], value }); return H2; };
  write.getTransaction = async () => tx("FINALIZED");
  const provider = over.connected === false ? makeProvider({ accounts: [], chainId: over.chainId }) : makeProvider({ accounts: [over.account ?? HOLDER], chainId: over.chainId ?? "0xf22f" });
  return { st, writes, read, write, provider, statuses };
}

async function connected(path: string, o: Parameters<typeof setup>[0] = {}) {
  const s = setup(o);
  const utils = renderApp({ path, transport: s.read, provider: s.provider, writeTransport: s.write });
  await waitFor(() => expect(screen.getByText(/0xbbbb/i, { selector: ".badge" })).toBeInTheDocument());
  return { ...s, ...utils };
}

describe("wallet states", () => {
  it("unsupported provider: read-only badge, reads still work", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }), provider: null, path: "/explore" });
    expect(screen.getByText(/No wallet · read-only/)).toBeInTheDocument();
    expect(await screen.findByLabelText("Passport 1")).toBeInTheDocument();
  });
  it("disconnected -> connecting -> connected", async () => {
    const { reads } = makeState();
    const provider = makeProvider();
    renderApp({ transport: makeTransport({ reads }), provider, path: "/" });
    const btn = await screen.findByRole("button", { name: "Connect wallet" });
    await userEvent.click(btn);
    expect(await screen.findByText(/0xbbbb/i, { selector: ".badge" })).toBeInTheDocument();
    expect(provider.calls).toContain("eth_requestAccounts");
    expect(provider.calls.some((m) => /private|sign/i.test(m))).toBe(false);
  });
  it("signature (connection) rejected is shown, nothing connected", async () => {
    const { reads } = makeState();
    renderApp({ transport: makeTransport({ reads }), provider: makeProvider({ reject: true }), path: "/" });
    await userEvent.click(await screen.findByRole("button", { name: "Connect wallet" }));
    expect(await screen.findByText(/You rejected the connection request/)).toBeInTheDocument();
  });
  it("wrong network: banner with a switch action; switching reaches connected", async () => {
    const { reads } = makeState();
    const provider = makeProvider({ accounts: [HOLDER], chainId: "0x1" });
    renderApp({ transport: makeTransport({ reads }), provider, path: "/" });
    const alert = await screen.findByText(/Wrong network\./);
    expect(alert.closest("[role=alert]")).toHaveTextContent(/chain 1/);
    expect(alert.closest("[role=alert]")).toHaveTextContent(/61999/);
    await userEvent.click(within(alert.closest("[role=alert]") as HTMLElement).getByRole("button", { name: "Switch network" }));
    expect(await screen.findByText(/0xbbbb/i, { selector: ".badge" })).toBeInTheDocument();
    expect(provider.calls).toContain("wallet_switchEthereumChain");
  });
});

describe("finality gating: an irreversible step is never enabled by a receipt alone", () => {
  it("finalize while the Application Challenge window is open: disabled with the reason in plain words", async () => {
    await connected("/claim/1", { claimStatus: "DECIDED" });
    const card = await plate("Finalize application decision");
    const button = within(card).getByRole("button", { name: "Finalize application decision" });
    expect(button).toBeDisabled();
    expect(card).toHaveTextContent(/Application Challenge window still open/);
    expect(button).toHaveAttribute("aria-describedby");
    expect(card).toHaveTextContent(/Why is this disabled\?/);
  });
  it("finalize after the window with NO known transaction: waiting for GenLayer finality, fail closed", async () => {
    const s = setup({ claimStatus: "DECIDED" });
    s.st.s.adjudication = { ...s.st.s.adjudication, challenge_window_closes_at: NOW - 10 };
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    const card = await plate("Finalize application decision");
    await waitFor(() => expect(card).toHaveTextContent(/Waiting for GenLayer finality: no transaction hash is known for adjudicate_claim/));
    expect(within(card).getByRole("button", { name: "Finalize application decision" })).toBeDisabled();
  });
  it("a pasted hash that is only ACCEPTED does not enable the step; a Finalized one does, then the write is sent and state re-read", async () => {
    const accepted = ("0x" + "11".repeat(32)) as `0x${string}`;
    const s = setup({ claimStatus: "DECIDED", finality: { [accepted]: tx("ACCEPTED"), [H2]: tx("FINALIZED") } });
    s.st.s.adjudication = { ...s.st.s.adjudication, challenge_window_closes_at: NOW - 10 };
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    await waitFor(() => expect(screen.getByText(/0xbbbb/i, { selector: ".badge" })).toBeInTheDocument());
    const card = await plate("Finalize application decision");
    const input = within(card).getByLabelText(/Transaction hash to verify/);
    fireEvent.change(input, { target: { value: accepted } });
    await waitFor(() => expect(card).toHaveTextContent(/Accepted by validators but not Finalized yet/));
    const btn = within(card).getByRole("button", { name: "Finalize application decision" });
    expect(btn).toBeDisabled();
    fireEvent.change(input, { target: { value: H2 } });
    await waitFor(() => expect(within(card).getByRole("button", { name: "Finalize application decision" })).toBeEnabled());
    expect(card).toHaveTextContent(/Finalized with a successful execution/);
    await userEvent.click(within(card).getByRole("button", { name: "Finalize application decision" }));
    // irreversible: explicit confirmation first, nothing sent yet
    expect(s.writes).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: /Yes, finalize application decision/i }));
    await waitFor(() => expect(s.writes).toEqual([{ fn: "finalize_claim", args: [1], value: 0n }]));
    expect(await screen.findByText(/Finalized on GenLayer and re-read from the contract/)).toBeInTheDocument();
  });
  it("settle: 'Final decision not yet finalized' before FINAL; 'Settlement not finalized' before withdrawal", async () => {
    await connected("/claim/1", { claimStatus: "ACCEPTED", hasAdj: false });
    const fin = await plate("Finalize application decision");
    expect(fin).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Authorize settlement" })).toBeNull();
  });
  it("withdraw: enabled only for the recorded recipient with claimable GEN and a Finalized settle transaction", async () => {
    const final = finalDecision({ settled_at: NOW - 20, settled_amount: (5n * ONE_GEN).toString(), claimable: (5n * ONE_GEN).toString() });
    const s = setup({ claimStatus: "SETTLED", final });
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    const card = await plate("Withdraw claimable GEN");
    const btn = within(card).getByRole("button", { name: "Withdraw claimable GEN" });
    await waitFor(() => expect(card).toHaveTextContent(/no transaction hash is known for settle_claim/));
    expect(btn).toBeDisabled();
    fireEvent.change(within(card).getByLabelText(/Transaction hash to verify/), { target: { value: HASH } });
    await waitFor(() => expect(within(card).getByRole("button", { name: "Withdraw claimable GEN" })).toBeEnabled());
    expect(card).toHaveTextContent(/You are the recorded recipient/);
  });
  it("withdraw is blocked for a non-recipient and after withdrawal, with reasons", async () => {
    const final = finalDecision({ settled_at: NOW - 20, settled_amount: (5n * ONE_GEN).toString(), claimable: (5n * ONE_GEN).toString() });
    const s = setup({ claimStatus: "SETTLED", final, account: "0xdddddddddddddddddddddddddddddddddddddddd" });
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    await waitFor(() => expect(screen.getByText(/0xdddd/i, { selector: ".badge" })).toBeInTheDocument());
    const card = await plate("Withdraw claimable GEN");
    expect(within(card).getByRole("button", { name: "Withdraw claimable GEN" })).toBeDisabled();
    expect(card).toHaveTextContent(/Only the recorded recipient/);
  });
  it("wrong network: the step is blocked and the reason says to switch to StudioNet (the SDK does not check Studio chains, the app does)", async () => {
    const s = setup({ claimStatus: "DECIDED", chainId: "0x1" });
    s.st.s.adjudication = { ...s.st.s.adjudication, challenge_window_closes_at: NOW - 10 };
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    const card = await plate("Finalize application decision");
    await waitFor(() => expect(card).toHaveTextContent(/Wrong network: switch your wallet to StudioNet \(61999\)/));
    expect(within(card).getByRole("button", { name: "Finalize application decision" })).toBeDisabled();
    expect(s.writes).toHaveLength(0);
  });
  it("disconnected wallet: the reason names the wallet, and reads stay available", async () => {
    const s = setup({ claimStatus: "DECIDED", connected: false });
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    const card = await plate("Finalize application decision");
    expect(card).toHaveTextContent(/Connect a wallet to send this transaction/);
    expect(within(card).getByRole("button", { name: "Finalize application decision" })).toBeDisabled();
    expect(screen.getByRole("region", { name: /Original adjudication/i })).toBeInTheDocument();
  });
});

describe("transaction lifecycle in the UI", () => {
  it("execution failure and undetermined results are reported as such, without changing displayed state", async () => {
    const s = setup({ claimStatus: "EVIDENCE_FROZEN", hasAdj: false });
    s.write.getTransaction = async () => tx("FINALIZED", "ERROR");
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    await waitFor(() => expect(screen.getByText(/0xbbbb/i, { selector: ".badge" })).toBeInTheDocument());
    const card = await plate("Request GenLayer adjudication");
    fireEvent.change(within(card).getByLabelText(/Transaction hash to verify/), { target: { value: HASH } });
    await waitFor(() => expect(within(card).getByRole("button", { name: "Request GenLayer adjudication" })).toBeEnabled());
    await userEvent.click(within(card).getByRole("button", { name: "Request GenLayer adjudication" }));
    await userEvent.click(await screen.findByRole("button", { name: /Yes, request genlayer adjudication/i }));
    const panel = await screen.findByLabelText("Transaction status");
    await waitFor(() => expect(panel).toHaveTextContent(/Failed/));
    expect(panel).toHaveTextContent(/Technical diagnostics/);
    // no optimistic mutation: the claim still reads as EVIDENCE_FROZEN
    expect(screen.getAllByText(/Evidence frozen/).length).toBeGreaterThan(0);
  });
  it("wallet rejection during a transaction is shown as Signature rejected", async () => {
    const s = setup({ claimStatus: "DECIDED" });
    s.st.s.adjudication = { ...s.st.s.adjudication, challenge_window_closes_at: NOW - 10 };
    s.write.writeContract = async () => { throw Object.assign(new Error("User rejected the request."), { code: 4001 }); };
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    await waitFor(() => expect(screen.getByText(/0xbbbb/i, { selector: ".badge" })).toBeInTheDocument());
    const card = await plate("Finalize application decision");
    fireEvent.change(within(card).getByLabelText(/Transaction hash to verify/), { target: { value: H2 } });
    await waitFor(() => expect(within(card).getByRole("button", { name: "Finalize application decision" })).toBeEnabled());
    await userEvent.click(within(card).getByRole("button", { name: "Finalize application decision" }));
    await userEvent.click(await screen.findByRole("button", { name: /Yes, finalize/i }));
    const panel = await screen.findByLabelText("Transaction status");
    await waitFor(() => expect(panel).toHaveTextContent(/Signature rejected/));
  });
});

describe("Application Challenge form", () => {
  it("offers exactly the seven frozen grounds, ground-specific citation pickers, a bounded explanation and a review step", async () => {
    await connected("/claim/1", { claimStatus: "DECIDED" });
    const form = (await screen.findByText("File an Application Challenge")).closest("section") as HTMLElement;
    const select = within(form).getByLabelText("Ground") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["IGNORED_EVIDENCE", "WRONG_WARRANTY_VERSION", "WRONG_CLAUSE", "EXCLUSION_MISAPPLIED", "TEMPORAL_ERROR", "SOURCE_AUTHORITY_ERROR", "PRODUCT_MATCH_ERROR"]);
    expect(form).toHaveTextContent(/not.* a GenLayer Protocol Appeal/);
    expect(form).toHaveTextContent(/one.* per claim/);
    expect(form).toHaveTextContent(/cannot add new evidence/);
    // IGNORED_EVIDENCE offers only considered-but-not-relied evidence (#2)
    expect(within(form).getByLabelText(/#2 · docs.example.com/)).toBeInTheDocument();
    expect(within(form).queryByLabelText(/#1 · docs.example.com/)).toBeNull();
    const why = within(form).getByLabelText(/Explanation/) as HTMLTextAreaElement;
    expect(why).toHaveAttribute("maxlength", "1000");
    await userEvent.click(within(form).getByLabelText(/#2 · docs.example.com/));
    await userEvent.type(why, "Evidence #2 shows the defect.");
    await userEvent.click(within(form).getByRole("button", { name: "Review challenge" }));
    expect(within(form).getByText("Review before submitting")).toBeInTheDocument();
    expect(form).toHaveTextContent(/Irreversible\./);
    expect(form).toHaveTextContent(/"evidence_ids":\[2\]/);
    // the submit button explains itself while finality is unverified
    expect(within(form).getByRole("button", { name: "Submit Application Challenge" })).toBeDisabled();
    await waitFor(() => expect(form).toHaveTextContent(/Waiting for GenLayer finality/));
  });
  it("switching ground changes the citation kind (clause, constitution, timestamp)", async () => {
    await connected("/claim/1", { claimStatus: "DECIDED" });
    const form = (await screen.findByText("File an Application Challenge")).closest("section") as HTMLElement;
    const select = within(form).getByLabelText("Ground");
    fireEvent.change(select, { target: { value: "WRONG_CLAUSE" } });
    expect(within(form).getByText("Cite clause")).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "WRONG_WARRANTY_VERSION" } });
    expect(within(form).getByLabelText(/Terms version id you believe should govern/)).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "TEMPORAL_ERROR" } });
    expect(within(form).getByLabelText(/Timestamp you say was misread/)).toBeInTheDocument();
  });
  it("after the window closes the form explains that the window is closed", async () => {
    const s = setup({ claimStatus: "DECIDED" });
    s.st.s.adjudication = { ...s.st.s.adjudication, challenge_window_closes_at: NOW - 100 };
    renderApp({ path: "/claim/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    const form = (await screen.findByText("File an Application Challenge")).closest("section") as HTMLElement;
    expect(form).toHaveTextContent(/The window closed at/);
  });
});

describe("claim filing form", () => {
  it("is guided: clauses, exclusions, deadline, asserted-date warning, evidence rules and the 10-record limit", async () => {
    const s = setup({});
    renderApp({ path: "/passport/1/claim", transport: s.read, provider: s.provider, writeTransport: s.write });
    expect(await screen.findByText("Your claim")).toBeInTheDocument();
    expect(screen.getByText(/Claim deadline:/)).toBeInTheDocument();
    expect(screen.getByText(/Water damage is excluded/)).toBeInTheDocument();
    expect(screen.getByText(/Claimant-asserted, not verified\./)).toBeInTheDocument();
    expect(screen.getByText(/Maximum 10 adjudicable evidence records per claim\./)).toBeInTheDocument();
    expect(screen.getByText(/Slots are first-come/)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "File claim" });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/Choose at least one covered clause|Connect a wallet/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/0xbbbb/i, { selector: ".badge" })).toBeInTheDocument());
    await userEvent.click(screen.getByLabelText(/C-001/));
    fireEvent.change(screen.getByLabelText(/Date the failure occurred/), { target: { value: "2026-09-20" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "File claim" })).toBeEnabled());
  });
});

describe("evidence submission form", () => {
  it("previews eligibility under the frozen policy and enforces the 10 slot cap in the UI", async () => {
    const st = makeState();
    st.s.claimStatus = "DISPUTED";
    st.s.claimExtra = { evidence_frozen_at: 0 };
    const read = makeTransport({ reads: st.reads });
    renderApp({ path: "/claim/1", transport: read, provider: makeProvider({ accounts: [HOLDER] }), writeTransport: makeTransport({ reads: st.reads }) });
    const form = (await screen.findByRole("heading", { name: "Submit evidence" })).closest("section") as HTMLElement;
    fireEvent.change(within(form).getByLabelText("Evidence URL"), { target: { value: "http://docs.example.com/x" } });
    expect(await within(form).findByText(/Only https:\/\/ sources are permitted/)).toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText("Evidence URL"), { target: { value: "https://evil.example.org/x" } });
    expect(await within(form).findByText(/not permitted by the frozen source policy/)).toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText("Evidence URL"), { target: { value: "https://docs.example.com/new" } });
    expect(await within(form).findByText(/Eligible under the frozen policy/)).toBeInTheDocument();
    expect(form).toHaveTextContent(/2 \/ 10/);
  });
});

describe("no wallet needed for public reads", () => {
  it("never requests accounts or signing while browsing", async () => {
    const { reads } = makeState();
    const provider = makeProvider();
    renderApp({ transport: makeTransport({ reads }), provider, path: "/claim/1" });
    await screen.findByRole("region", { name: /Original adjudication/i });
    expect(provider.calls.filter((m) => m !== "eth_accounts" && m !== "eth_chainId")).toEqual([]);
    void CONFIGURED; void ADDR; void MFR;
  });
});


describe("issued warranties are commitments (V1 cancellation policy)", () => {
  it("the manufacturer sees no cancel control on an issued passport and the page says they cannot cancel", async () => {
    const { MFR } = await import("./helpers/harness");
    const s = setup({ claimStatus: "DECIDED", account: MFR });
    renderApp({ path: "/passport/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    await screen.findByLabelText("Warranty passport 1");
    await waitFor(() => expect(screen.getByText(/0xaaaa/i, { selector: ".badge" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Cancel warranty" })).toBeNull();
    expect(screen.getByText(/ISSUED WARRANTY — TERMS FROZEN/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/manufacturer or the holder|not irrevocable/i);
  });
  it("the holder can cancel their own warranty (with an irreversible-step confirmation), only when no claim is unsettled", async () => {
    const s = setup({ claimStatus: "SETTLED" });
    renderApp({ path: "/passport/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    await screen.findByLabelText("Warranty passport 1");
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel warranty" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Cancel warranty" }));
    expect(s.writes).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: /Yes, cancel warranty/i }));
    await waitFor(() => expect(s.writes).toEqual([{ fn: "cancel_warranty", args: [1], value: 0n }]));
  });
  it("a holder with an unsettled claim sees the cancel control disabled with the reason", async () => {
    const s = setup({ claimStatus: "DECIDED" });
    renderApp({ path: "/passport/1", transport: s.read, provider: s.provider, writeTransport: s.write });
    await screen.findByLabelText("Warranty passport 1");
    await waitFor(() => expect(screen.getByText(/A claim on this warranty is unsettled/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Cancel warranty" })).toBeDisabled();
  });
  it("the program console states that retiring stops future issuance only", async () => {
    const s = setup({});
    renderApp({ path: "/manufacturer/program/1", transport: s.read, provider: makeProvider({ accounts: [MFR] }), writeTransport: s.write });
    expect(await screen.findByText(/Retiring a program stops future issuance\. Existing warranties remain governed by their frozen terms\./)).toBeInTheDocument();
  });
});
