import { createClient } from "genlayer-js";
import type { Address } from "../config/contract";
import type { NetworkConfig } from "../config/networks";

/** Values the stable GenLayerJS calldata encoder accepts (subset actually used by the CLAUSE ABI). */
export type Calldata = string | number | bigint | boolean | null | Calldata[] | { [key: string]: Calldata };

/** Minimal receipt/transaction shape read from genlayer-js 1.1.8 (snake_case leader receipt; numeric or named status). */
export interface RawTx {
  hash?: string;
  status?: number | string;
  status_name?: string;
  statusName?: string;
  txExecutionResultName?: string;
  consensus_data?: { leader_receipt?: Array<{ execution_result?: string; genvm_result?: { stderr?: string } }> };
  data?: { contract_address?: string };
}

/**
 * The exact subset of the stable genlayer-js client CLAUSE uses. Unit tests provide a mock implementing THIS interface;
 * production wraps the real SDK client (createSdkTransport) with identical method names and argument shapes.
 */
export interface ClauseTransport {
  readContract(args: { address: Address; functionName: string; args?: Calldata[] }): Promise<unknown>;
  writeContract(args: { address: Address; functionName: string; args?: Calldata[]; value?: bigint }): Promise<`0x${string}`>;
  waitForTransactionReceipt(args: { hash: `0x${string}`; status?: string; interval?: number; retries?: number }): Promise<RawTx>;
  getTransaction(args: { hash: `0x${string}` }): Promise<RawTx>;
}

export interface EIP1193Provider {
  request(args: { method: string; params?: unknown[] | object }): Promise<unknown>;
}

/** Read-only client (no account, no wallet): used for every public page. */
export function createReadTransport(network: NetworkConfig): ClauseTransport {
  const client = createClient({ chain: network.chain });
  return wrapSdkClient(client as unknown as SdkLike);
}

/** Wallet-backed client: the account is the connected ADDRESS; signing is delegated to the injected EIP-1193 provider. */
export function createWalletTransport(network: NetworkConfig, account: Address, provider: EIP1193Provider): ClauseTransport {
  const client = createClient({ chain: network.chain, account, provider: provider as never });
  return wrapSdkClient(client as unknown as SdkLike);
}

export interface SdkLike {
  readContract(a: { address: Address; functionName: string; args?: Calldata[] }): Promise<unknown>;
  writeContract(a: { address: Address; functionName: string; args?: Calldata[]; value?: bigint }): Promise<`0x${string}`>;
  waitForTransactionReceipt(a: { hash: `0x${string}`; status?: string; interval?: number; retries?: number }): Promise<RawTx>;
  getTransaction(a: { hash: `0x${string}` }): Promise<RawTx>;
}

export function wrapSdkClient(client: SdkLike): ClauseTransport {
  return {
    readContract: (a) => client.readContract(a),
    writeContract: (a) => client.writeContract({ ...a, value: a.value ?? 0n }),
    waitForTransactionReceipt: (a) => client.waitForTransactionReceipt(a),
    getTransaction: (a) => client.getTransaction(a),
  };
}
