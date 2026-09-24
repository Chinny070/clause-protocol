import type { Address } from "../config/contract";
import type { NetworkConfig } from "../config/networks";
import type { EIP1193Provider } from "../contract/transport";

/** Every wallet state the UI can be in. No private key is ever requested or held: only an address and a provider. */
export type WalletState =
  | { status: "unsupported" }
  | { status: "disconnected" }
  | { status: "connecting" }
  | { status: "wrong-network"; address: Address; chainId: number }
  | { status: "connected"; address: Address; chainId: number }
  | { status: "rejected"; message: string }
  | { status: "error"; message: string };

export function detectProvider(win: object | undefined = typeof window !== "undefined" ? window : undefined): EIP1193Provider | null {
  const p = (win as { ethereum?: unknown } | undefined)?.ethereum as EIP1193Provider | undefined;
  return p && typeof p.request === "function" ? p : null;
}

export function chainIdFromHex(hex: unknown): number | null {
  if (typeof hex !== "string" || !/^0x[0-9a-fA-F]+$/.test(hex)) return null;
  const n = parseInt(hex, 16);
  return Number.isSafeInteger(n) ? n : null;
}

function isRejection(e: unknown): boolean {
  const err = e as { code?: number; message?: string } | undefined;
  return err?.code === 4001 || /user rejected|rejected the request|denied/i.test(err?.message ?? "");
}

function pickAddress(accounts: unknown): Address | null {
  if (Array.isArray(accounts) && typeof accounts[0] === "string" && /^0x[0-9a-fA-F]{40}$/.test(accounts[0])) return accounts[0] as Address;
  return null;
}

/** Reads the current wallet state WITHOUT prompting (eth_accounts). */
export async function readWalletState(provider: EIP1193Provider | null, network: NetworkConfig): Promise<WalletState> {
  if (!provider) return { status: "unsupported" };
  try {
    const address = pickAddress(await provider.request({ method: "eth_accounts" }));
    if (!address) return { status: "disconnected" };
    const chainId = chainIdFromHex(await provider.request({ method: "eth_chainId" }));
    if (chainId === null) return { status: "error", message: "The wallet returned an unreadable chain id." };
    return chainId === network.chainId ? { status: "connected", address, chainId } : { status: "wrong-network", address, chainId };
  } catch (e) {
    return { status: "error", message: e instanceof Error ? e.message : String(e) };
  }
}

/** Prompts the wallet for account access (eth_requestAccounts). */
export async function connectWallet(provider: EIP1193Provider | null, network: NetworkConfig): Promise<WalletState> {
  if (!provider) return { status: "unsupported" };
  try {
    const address = pickAddress(await provider.request({ method: "eth_requestAccounts" }));
    if (!address) return { status: "disconnected" };
    const chainId = chainIdFromHex(await provider.request({ method: "eth_chainId" }));
    if (chainId === null) return { status: "error", message: "The wallet returned an unreadable chain id." };
    return chainId === network.chainId ? { status: "connected", address, chainId } : { status: "wrong-network", address, chainId };
  } catch (e) {
    if (isRejection(e)) return { status: "rejected", message: "You rejected the connection request in your wallet." };
    return { status: "error", message: e instanceof Error ? e.message : String(e) };
  }
}

/**
 * Switches the wallet to the target GenLayer network, adding it first if unknown. Uses plain EIP-3326/3085 requests
 * (NOT the SDK's snap-based client.connect, which additionally requires a MetaMask snap install).
 */
export async function switchToNetwork(provider: EIP1193Provider | null, network: NetworkConfig): Promise<{ ok: true } | { ok: false; rejected: boolean; message: string }> {
  if (!provider) return { ok: false, rejected: false, message: "No injected wallet found." };
  try {
    await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: network.chainIdHex }] });
    return { ok: true };
  } catch (e) {
    const code = (e as { code?: number } | undefined)?.code;
    if (code === 4902 || code === -32603) {
      try {
        await provider.request({ method: "wallet_addEthereumChain", params: [{
          chainId: network.chainIdHex, chainName: network.name, rpcUrls: [network.rpcUrl],
          nativeCurrency: { name: network.currencySymbol, symbol: network.currencySymbol, decimals: 18 },
        }] });
        return { ok: true };
      } catch (e2) {
        return { ok: false, rejected: isRejection(e2), message: e2 instanceof Error ? e2.message : String(e2) };
      }
    }
    return { ok: false, rejected: isRejection(e), message: e instanceof Error ? e.message : String(e) };
  }
}

/** Subscribes to wallet account/chain changes; returns an unsubscribe function. */
export function watchWallet(provider: (EIP1193Provider & { on?: (e: string, h: (...a: unknown[]) => void) => void; removeListener?: (e: string, h: (...a: unknown[]) => void) => void }) | null, onChange: () => void): () => void {
  if (!provider?.on) return () => undefined;
  const h = () => onChange();
  provider.on("accountsChanged", h);
  provider.on("chainChanged", h);
  return () => { provider.removeListener?.("accountsChanged", h); provider.removeListener?.("chainChanged", h); };
}
