import { isAddress } from "viem";
import { resolveNetwork, type NetworkConfig } from "./networks";

export type Address = `0x${string}`;

export type ContractConfig =
  | { status: "not-configured"; reason: string; network: NetworkConfig }
  | { status: "invalid"; reason: string; raw: string; network: NetworkConfig }
  | { status: "network-error"; reason: string }
  | { status: "configured"; address: Address; network: NetworkConfig };

const ZERO = /^0x0{40}$/i;

/**
 * The single, typed source of the canonical CLAUSE contract address. An address only ever leaves this module as a
 * validated `configured` value; every other state is explicit so `undefined` can never reach an SDK call.
 */
export function readContractConfig(env: { VITE_CLAUSE_CONTRACT_ADDRESS?: string; VITE_CLAUSE_NETWORK?: string }, isProduction: boolean): ContractConfig {
  const net = resolveNetwork(env.VITE_CLAUSE_NETWORK, isProduction);
  if (!net.ok) return { status: "network-error", reason: net.reason };
  const raw = (env.VITE_CLAUSE_CONTRACT_ADDRESS ?? "").trim();
  if (raw === "") {
    return {
      status: "not-configured",
      reason: "No canonical CLAUSE contract address has been configured for this build (VITE_CLAUSE_CONTRACT_ADDRESS is unset).",
      network: net.network,
    };
  }
  if (!isAddress(raw, { strict: false }) || ZERO.test(raw)) {
    return { status: "invalid", reason: "The configured contract address is not a valid non-zero EVM address.", raw, network: net.network };
  }
  return { status: "configured", address: raw as Address, network: net.network };
}

export function loadContractConfig(): ContractConfig {
  return readContractConfig(import.meta.env as Record<string, string | undefined>, import.meta.env.PROD);
}
