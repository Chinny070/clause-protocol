import { localnet, studionet } from "genlayer-js/chains";

/** The ONLY production target: stable GenLayer StudioNet (chain 61999). Values are taken from the SDK chain object. */
export const STUDIONET = {
  key: "studionet" as const,
  chain: studionet,
  chainId: studionet.id,
  chainIdHex: `0x${studionet.id.toString(16)}`,
  name: studionet.name,
  rpcUrl: studionet.rpcUrls.default.http[0],
  currencySymbol: studionet.nativeCurrency.symbol,
};

/** Development/integration only. Never selectable in a production build (see resolveNetwork). */
export const LOCALNET = {
  key: "localnet" as const,
  chain: localnet,
  chainId: localnet.id,
  chainIdHex: `0x${localnet.id.toString(16)}`,
  name: localnet.name,
  rpcUrl: localnet.rpcUrls.default.http[0],
  currencySymbol: localnet.nativeCurrency.symbol,
};

export type NetworkKey = "studionet" | "localnet";
export type NetworkConfig = typeof STUDIONET | typeof LOCALNET;

export type NetworkResolution =
  | { ok: true; network: NetworkConfig }
  | { ok: false; reason: string };

/**
 * Chooses the target network. Production builds are locked to StudioNet: a request for anything else is
 * refused (there is no hidden mock/dev mode in production).
 */
export function resolveNetwork(requested: string | undefined, isProduction: boolean): NetworkResolution {
  const want = (requested ?? "").trim().toLowerCase();
  if (want === "" || want === "studionet") return { ok: true, network: STUDIONET };
  if (want === "localnet") {
    if (isProduction) return { ok: false, reason: "localnet is a development-only target and is refused in production builds" };
    return { ok: true, network: LOCALNET };
  }
  return { ok: false, reason: `unknown network "${requested}" (only studionet is supported)` };
}
