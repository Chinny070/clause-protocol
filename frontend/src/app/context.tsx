import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { loadContractConfig, type Address, type ContractConfig } from "../config/contract";
import { ClauseReader, ContractReadError, type ReadFailureKind } from "../contract/reader";
import { createReadTransport, createWalletTransport, type ClauseTransport, type EIP1193Provider } from "../contract/transport";
import type { CallSpec } from "../contract/calls";
import { runTransaction, type TxOutcome, type TxPhase } from "../tx/runner";
import { TxJournal } from "../tx/journal";
import { humanizeError } from "../domain/errors";
import { connectWallet, detectProvider, readWalletState, switchToNetwork, watchWallet, type WalletState } from "../wallet/wallet";

/* ------------------------------------------------------------------ contract / network health */

export type Health =
  | { state: "unconfigured" }
  | { state: "checking" }
  | { state: "ok"; programCount: number }
  | { state: "error"; kind: ReadFailureKind; message: string };

interface ClauseCtx {
  config: ContractConfig;
  reader: ClauseReader | null;
  readTransport: ClauseTransport | null;
  health: Health;
  refreshHealth: () => void;
  /** Protocol clock: last authoritative `now()` read plus local elapsed time (display only; the contract enforces). */
  protocolNow: () => number;
  journal: TxJournal;
}

const Ctx = createContext<ClauseCtx | null>(null);

export function ClauseProvider({ children, config: configOverride, transport: transportOverride }: { children: ReactNode; config?: ContractConfig; transport?: ClauseTransport }) {
  const config = useMemo(() => configOverride ?? loadContractConfig(), [configOverride]);
  const readTransport = useMemo(() => {
    if (transportOverride) return transportOverride;
    return config.status === "configured" ? createReadTransport(config.network) : null;
  }, [config, transportOverride]);
  const reader = useMemo(() => (config.status === "configured" && readTransport ? new ClauseReader(readTransport, config.address) : null), [config, readTransport]);
  const journal = useMemo(() => new TxJournal(undefined, config.status === "configured" ? config.address.toLowerCase() : "unconfigured"), [config]);
  const [health, setHealth] = useState<Health>(config.status === "configured" ? { state: "checking" } : { state: "unconfigured" });
  const clock = useRef({ base: 0, at: 0 });

  const refreshHealth = useCallback(() => {
    if (!reader) { setHealth({ state: "unconfigured" }); return; }
    setHealth({ state: "checking" });
    reader.healthCheck().then(
      (h) => { clock.current = { base: h.protocolNow, at: Date.now() }; setHealth({ state: "ok", programCount: h.programCount }); },
      (e: unknown) => {
        const kind: ReadFailureKind = e instanceof ContractReadError ? e.kind : "contract-read-failed";
        setHealth({ state: "error", kind, message: e instanceof Error ? e.message : String(e) });
      },
    );
  }, [reader]);
  useEffect(() => { refreshHealth(); }, [refreshHealth]);

  const protocolNow = useCallback(() => (clock.current.at === 0 ? Math.floor(Date.now() / 1000) : clock.current.base + Math.floor((Date.now() - clock.current.at) / 1000)), []);
  const value = useMemo(() => ({ config, reader, readTransport, health, refreshHealth, protocolNow, journal }), [config, reader, readTransport, health, refreshHealth, protocolNow, journal]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useClause(): ClauseCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useClause must be used inside <ClauseProvider>");
  return v;
}

/* ------------------------------------------------------------------ wallet */

interface WalletCtx {
  state: WalletState;
  address: Address | null;
  ready: boolean; // connected AND on the target network
  connect: () => Promise<void>;
  switchNetwork: () => Promise<void>;
  transport: ClauseTransport | null;
  provider: EIP1193Provider | null;
}
const WCtx = createContext<WalletCtx | null>(null);

export function WalletProvider({ children, provider: providerOverride, transportFactory }: {
  children: ReactNode; provider?: EIP1193Provider | null; transportFactory?: (address: Address) => ClauseTransport;
}) {
  const { config } = useClause();
  const provider = useMemo(() => (providerOverride !== undefined ? providerOverride : detectProvider()), [providerOverride]);
  const [state, setState] = useState<WalletState>(provider ? { status: "disconnected" } : { status: "unsupported" });
  const network = config.status === "network-error" ? null : config.network;

  const refresh = useCallback(async () => {
    if (!network) return;
    const s = await readWalletState(provider, network);
    setState((prev) => (prev.status === "rejected" && s.status === "disconnected" ? prev : s));
  }, [provider, network]);
  useEffect(() => { void refresh(); return watchWallet(provider as never, () => void refresh()); }, [provider, refresh]);

  const connect = useCallback(async () => {
    if (!network) return;
    setState({ status: "connecting" });
    setState(await connectWallet(provider, network));
  }, [provider, network]);

  const switchNetwork = useCallback(async () => {
    if (!network) return;
    const r = await switchToNetwork(provider, network);
    if (!r.ok) setState(r.rejected ? { status: "rejected", message: "You rejected the network switch in your wallet." } : { status: "error", message: r.message });
    else await refresh();
  }, [provider, network, refresh]);

  const address = state.status === "connected" || state.status === "wrong-network" ? state.address : null;
  const transport = useMemo(() => {
    if (state.status !== "connected" || !network) return null;
    if (transportFactory) return transportFactory(state.address);
    return provider ? createWalletTransport(network, state.address, provider) : null;
  }, [state, network, provider, transportFactory]);

  const value = useMemo<WalletCtx>(() => ({ state, address, ready: state.status === "connected", connect, switchNetwork, transport, provider }), [state, address, connect, switchNetwork, transport, provider]);
  return <WCtx.Provider value={value}>{children}</WCtx.Provider>;
}

export function useWallet(): WalletCtx {
  const v = useContext(WCtx);
  if (!v) throw new Error("useWallet must be used inside <WalletProvider>");
  return v;
}

/* ------------------------------------------------------------------ transactions */

export interface RunRequest<T> { spec: CallSpec; claimId?: number; reread?: () => Promise<T>; onConfirmed?: (data: T | undefined) => void }

interface TxCtx {
  phase: TxPhase;
  label: string;
  outcome: TxOutcome<unknown> | null;
  run: <T>(req: RunRequest<T>) => Promise<TxOutcome<T>>;
  dismiss: () => void;
}
const TCtx = createContext<TxCtx | null>(null);

export function TxProvider({ children, pollMs }: { children: ReactNode; pollMs?: number }) {
  const { config, journal } = useClause();
  const wallet = useWallet();
  const [phase, setPhase] = useState<TxPhase>({ phase: "idle" });
  const [label, setLabel] = useState("");
  const [outcome, setOutcome] = useState<TxOutcome<unknown> | null>(null);
  const busy = useRef(false);

  const run = useCallback(async <T,>(req: RunRequest<T>): Promise<TxOutcome<T>> => {
    setOutcome(null);
    setLabel(req.spec.label);
    if (config.status !== "configured") {
      const error = humanizeError("contract not configured");
      const out: TxOutcome<T> = { ok: false, reason: "submit-failed", error: { ...error, kind: "contract-unavailable", title: "Contract not configured", message: "No canonical CLAUSE contract address is configured, so no transaction can be sent." } };
      setPhase({ phase: "failed", error: out.error }); setOutcome(out); return out;
    }
    if (!wallet.transport) {
      const wrong = wallet.state.status === "wrong-network";
      const error = { kind: wrong ? "wrong-chain" as const : "unauthorized" as const, title: wrong ? "Wrong network" : "Wallet not connected", technical: wallet.state.status,
        message: wrong ? "Switch your wallet to GenLayer StudioNet (chain 61999) before sending." : "Connect a wallet to send this transaction." };
      const out: TxOutcome<T> = { ok: false, reason: "submit-failed", error };
      setPhase({ phase: "failed", error }); setOutcome(out); return out;
    }
    if (busy.current) {
      const error = { kind: "unknown" as const, title: "Another transaction is in progress", message: "Wait for the current transaction to finish first.", technical: "busy" };
      return { ok: false, reason: "submit-failed", error };
    }
    busy.current = true;
    try {
      const out = await runTransaction<T>(wallet.transport, config.address, req.spec, {
        pollMs,
        reread: req.reread,
        onPhase: (p) => {
          setPhase(p);
          if (p.phase === "submitted" && req.claimId !== undefined) journal.record(req.claimId, req.spec.functionName, p.hash);
        },
      });
      setOutcome(out);
      if (out.ok) req.onConfirmed?.(out.data);
      return out;
    } finally { busy.current = false; }
  }, [config, wallet.transport, wallet.state.status, journal, pollMs]);

  const dismiss = useCallback(() => { setPhase({ phase: "idle" }); setOutcome(null); }, []);
  const value = useMemo(() => ({ phase, label, outcome, run, dismiss }), [phase, label, outcome, run, dismiss]);
  return <TCtx.Provider value={value}>{children}</TCtx.Provider>;
}

export function useTx(): TxCtx {
  const v = useContext(TCtx);
  if (!v) throw new Error("useTx must be used inside <TxProvider>");
  return v;
}
