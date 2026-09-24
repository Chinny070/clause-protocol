import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../../src/App";
import { ClauseProvider, TxProvider, WalletProvider } from "../../src/app/context";
import type { Address, ContractConfig } from "../../src/config/contract";
import { STUDIONET } from "../../src/config/networks";
import type { Calldata, ClauseTransport, EIP1193Provider, RawTx } from "../../src/contract/transport";
import { ADDR, HASH, tx } from "./mock";

export const MFR = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" as Address;
export const HOLDER = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" as Address;
export const STRANGER = "0xcccccccccccccccccccccccccccccccccccccccc" as Address;
export const FP = "d".repeat(64);
export const ONE_GEN = 10n ** 18n;
export const NOW = 1_790_000_000;

export const CONFIGURED: ContractConfig = { status: "configured", address: ADDR, network: STUDIONET };

type Raw = Record<string, unknown>;

/** Mutable contract state, exposed to the frozen-ABI view functions exactly as the SDK would return it. */
export function makeState() {
  const s = {
    now: NOW,
    claimStatus: "DECIDED",
    claimExtra: {} as Raw,
    adjudication: {
      adjudication_id: 1, claim_id: 1, constitution_id: 1, adjudicated_at: NOW - 100, product_match: "PASS", warranty_version_match: "PASS", coverage_window: "PASS",
      covered_clause_ids: [] as string[], exclusion_clause_ids: [] as string[], evidence_sufficiency: "INSUFFICIENT", source_authority: "PASS",
      evidence_ids_relied_on: [1], evidence_ids_considered: [1, 2], outcome: "INSUFFICIENT_EVIDENCE", rationale: "The receipt does not show a defect.",
      decision_path: "SEMANTIC", challenge_window_closes_at: NOW + 1000, superseded: false,
    } as Raw,
    hasAdjudication: true,
    challenge: {} as Raw,
    final: {} as Raw,
    receipt: null as Raw | null,
    passportStatus: "ACTIVE",
    evidence: [
      { evidence_id: 1, claim_id: 1, submitter: HOLDER, original_url: "https://docs.example.com/receipt", category: "RECEIPT", host: "docs.example.com", retrieval_method: "GET", submitted_at: NOW - 500, eligibility: "ELIGIBLE", retrieval_status: "AVAILABLE", retrieved_at: NOW - 400, frozen_at: NOW - 400, extracted_content: "Receipt text", fingerprint: "ab".repeat(32), available: true },
      { evidence_id: 2, claim_id: 1, submitter: HOLDER, original_url: "https://docs.example.com/photo", category: "RECEIPT", host: "docs.example.com", retrieval_method: "GET", submitted_at: NOW - 490, eligibility: "ELIGIBLE", retrieval_status: "FETCH_FAILED", retrieved_at: NOW - 400, frozen_at: NOW - 400, extracted_content: "", fingerprint: "cd".repeat(32), available: false },
      { evidence_id: 3, claim_id: 1, submitter: MFR, original_url: "https://evil.example.net/x", category: "RECEIPT", host: "evil.example.net", retrieval_method: "GET", submitted_at: NOW - 480, eligibility: "INELIGIBLE", retrieval_status: "", retrieved_at: 0, frozen_at: 0, extracted_content: "", fingerprint: "", available: false },
    ] as Raw[],
  };
  const claim = (): Raw => ({
    claim_id: 1, warranty_id: 1, program_id: 1, holder: HOLDER, manufacturer: MFR, constitution_id: 1, constitution_fingerprint: FP, failure_asserted_at: NOW - 5000,
    targeted_clause_ids: ["C-001"], filed_at: NOW - 900, response_deadline: NOW - 800, manufacturer_response: "DISPUTE", responded_at: NOW - 850, evidence_frozen_at: NOW - 400,
    status: s.claimStatus, adjudication_id: s.hasAdjudication ? 1 : 0, ...s.claimExtra,
  });
  const passport = (): Raw => ({
    warranty_id: 1, program_id: 1, manufacturer: MFR, holder: HOLDER, product_model_id: "WIDGET-X-001", product_commitment: "0".repeat(64), registered_at: NOW - 9000,
    coverage_start: NOW - 8000, coverage_end: NOW + 100000, constitution_id: 1, constitution_version: "2026.1", constitution_fingerprint: FP,
    max_deterministic_remedy: (5n * ONE_GEN).toString(), reservation_id: 1, status: s.passportStatus,
  });
  const constitution = (): Raw => ({
    constitution_id: 1, program_id: 1, version: "2026.1", fingerprint: FP, product_scope: "Widget Model X", coverage_calc: "flat term",
    covered_clause_ids: ["C-001"], excluded_clause_ids: ["X-001"], acceptable_evidence_categories: ["RECEIPT"], source_eligibility_policy: "docs.example.com",
    claim_deadline_s: 2592000, manufacturer_response_period_s: 1209600, challenge_window_s: 604800, challenge_depth: 1,
    insufficient_evidence_behavior: "RULE_FOR_MANUFACTURER", unavailable_evidence_behavior: "RULE_FOR_MANUFACTURER", expiry_cancellation_rules: "Cancel while no claim is unsettled.",
    remedy_table: [{ outcome: "COVERED", clause_id: "C-001", remedy_kind: "FULL_REFUND", remedy_value: 0 }, { outcome: "ACCEPTED_NO_CONTEST", clause_id: "", remedy_kind: "FULL_REFUND", remedy_value: 0 }, { outcome: "NOT_COVERED", clause_id: "", remedy_kind: "NONE", remedy_value: 0 }],
    frozen_at: NOW - 9000, is_frozen: true,
  });
  const reads: Record<string, (a: Calldata[]) => unknown> = {
    now: () => s.now,
    list_program_ids: () => [1],
    get_program: () => ({ program_id: 1, manufacturer: MFR, name: "Acme Widgets", status: "ACTIVE", created_at: NOW - 10000 }),
    get_pool: () => ({ pool_id: 1, program_id: 1, manufacturer: MFR, total_balance: (10n * ONE_GEN).toString(), reserved_liability: (5n * ONE_GEN).toString(), available_balance: (5n * ONE_GEN).toString() }),
    list_passport_ids: () => [1],
    get_passport: (a) => (a[0] === 1 ? passport() : {}),
    get_constitution: (a) => (a[0] === 1 ? constitution() : {}),
    get_clauses: () => [{ clause_id: "C-001", kind: "COVERED", text: "Manufacturing defects are covered." }, { clause_id: "X-001", kind: "EXCLUDED", text: "Water damage is excluded." }],
    get_reservation: () => ({ reservation_id: 1, pool_id: 1, warranty_id: 1, amount: (5n * ONE_GEN).toString(), status: s.passportStatus === "CANCELLED" ? "RELEASED" : "ACTIVE", created_at: NOW - 9000, released_at: s.passportStatus === "CANCELLED" ? NOW - 50 : 0 }),
    list_claim_ids_for_warranty: () => [1],
    get_claim: (a) => (a[0] === 1 ? claim() : {}),
    list_evidence_ids_for_claim: () => s.evidence.map((e) => e.evidence_id),
    get_evidence: (a) => s.evidence.find((e) => e.evidence_id === a[0]) ?? {},
    get_adjudication: (a) => (s.hasAdjudication && a[0] === 1 ? s.adjudication : {}),
    get_challenge: () => s.challenge,
    get_challenge_for_claim: () => s.challenge,
    get_final_decision: () => s.final,
    get_resolution_receipt: (a) => (a[0] === 1 ? s.receipt ?? {} : {}),
  };
  return { s, reads };
}

export function finalDecision(over: Raw = {}): Raw {
  return { claim_id: 1, source: "ADJUDICATION", adjudication_id: 1, challenge_id: 0, final_outcome: "COVERED", established_clause_ids: ["C-001"], remedy_basis: "COVERED", remedy_kind: "FULL_REFUND",
    remedy_value: 0, remedy_amount: (5n * ONE_GEN).toString(), recipient: HOLDER, finalized_at: NOW - 60, settled_at: 0, settled_amount: 0, capped: false, claimable: 0, withdrawn_at: 0, withdrawn_amount: 0, ...over };
}

export interface FakeProvider extends EIP1193Provider { calls: string[]; chainId: string; accounts: string[]; on: (e: string, h: () => void) => void; removeListener: () => void; emit: (e: string) => void }
export function makeProvider(o: { accounts?: string[]; chainId?: string; reject?: boolean } = {}): FakeProvider {
  const listeners: Record<string, Array<() => void>> = {};
  const p: FakeProvider = {
    calls: [], chainId: o.chainId ?? "0xf22f", accounts: o.accounts ?? [],
    async request({ method, params }) {
      p.calls.push(method);
      if (method === "eth_accounts") return p.accounts;
      if (method === "eth_requestAccounts") {
        if (o.reject) throw Object.assign(new Error("User rejected the request."), { code: 4001 });
        p.accounts = [HOLDER];
        return p.accounts;
      }
      if (method === "eth_chainId") return p.chainId;
      if (method === "wallet_switchEthereumChain") { p.chainId = (params as Array<{ chainId: string }>)[0].chainId; p.emit("chainChanged"); return null; }
      throw new Error("unsupported " + method);
    },
    on(e, h) { (listeners[e] ??= []).push(h); },
    removeListener() { /* no-op */ },
    emit(e) { (listeners[e] ?? []).forEach((h) => h()); },
  };
  return p;
}

export interface RenderOpts {
  path?: string;
  config?: ContractConfig;
  transport?: ClauseTransport;
  provider?: EIP1193Provider | null;
  writeTransport?: ClauseTransport;
}

export function renderApp(o: RenderOpts = {}) {
  return render(
    <ClauseProvider config={o.config ?? CONFIGURED} transport={o.transport}>
      <WalletProvider provider={o.provider ?? null} transportFactory={o.writeTransport ? () => o.writeTransport as ClauseTransport : undefined}>
        <TxProvider pollMs={1}>
          <MemoryRouter initialEntries={[o.path ?? "/"]}><AppRoutes /></MemoryRouter>
        </TxProvider>
      </WalletProvider>
    </ClauseProvider>,
  );
}

export { ADDR, HASH, tx };
export type { RawTx };
