import { createAccount, createClient } from "genlayer-js";
import type { Address } from "../../src/config/contract";
import type { NetworkConfig } from "../../src/config/networks";
import { wrapSdkClient, type ClauseTransport, type SdkLike } from "../../src/contract/transport";

/** Throwaway-key transport for LOCAL SIMULATOR integration tests only. Lives in tests/ so no key generation ships in the app. */
export function createEphemeralTestTransport(network: NetworkConfig): { transport: ClauseTransport; address: Address } {
  const account = createAccount();
  const client = createClient({ chain: network.chain, account });
  return { transport: wrapSdkClient(client as unknown as SdkLike), address: account.address as Address };
}
