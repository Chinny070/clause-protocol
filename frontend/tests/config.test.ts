import { describe, expect, it } from "vitest";
import { readContractConfig } from "../src/config/contract";
import { LOCALNET, STUDIONET, resolveNetwork } from "../src/config/networks";

describe("network config", () => {
  it("targets stable StudioNet 61999 with the verified RPC and GEN", () => {
    expect(STUDIONET.chainId).toBe(61999);
    expect(STUDIONET.chainIdHex).toBe("0xf22f");
    expect(STUDIONET.rpcUrl).toBe("https://studio.genlayer.com/api");
    expect(STUDIONET.currencySymbol).toBe("GEN");
  });
  it("never targets Studio Next chain 61997", () => {
    expect(STUDIONET.chainId).not.toBe(61997);
    expect(LOCALNET.chainId).not.toBe(61997);
  });
  it("defaults to StudioNet and refuses localnet in production", () => {
    expect(resolveNetwork(undefined, true)).toMatchObject({ ok: true, network: { key: "studionet" } });
    expect(resolveNetwork("", true)).toMatchObject({ ok: true, network: { key: "studionet" } });
    expect(resolveNetwork("localnet", true).ok).toBe(false);
    expect(resolveNetwork("localnet", false)).toMatchObject({ ok: true, network: { key: "localnet" } });
    expect(resolveNetwork("mainnet", false).ok).toBe(false);
  });
});

describe("contract address config", () => {
  const good = "0x1111111111111111111111111111111111111111";
  it("reports not-configured when unset or blank, never an address", () => {
    for (const v of [undefined, "", "   "]) {
      const c = readContractConfig({ VITE_CLAUSE_CONTRACT_ADDRESS: v }, true);
      expect(c.status).toBe("not-configured");
      expect("address" in c).toBe(false);
    }
  });
  it("rejects malformed and zero addresses as invalid", () => {
    for (const v of ["0x123", "not-an-address", "0x" + "0".repeat(40), "0x" + "g".repeat(40), good + "00"]) {
      expect(readContractConfig({ VITE_CLAUSE_CONTRACT_ADDRESS: v }, true).status).toBe("invalid");
    }
  });
  it("accepts a valid address exactly once, typed", () => {
    const c = readContractConfig({ VITE_CLAUSE_CONTRACT_ADDRESS: ` ${good} ` }, true);
    expect(c).toMatchObject({ status: "configured", address: good });
  });
  it("surfaces a network error for a forbidden production network", () => {
    expect(readContractConfig({ VITE_CLAUSE_CONTRACT_ADDRESS: good, VITE_CLAUSE_NETWORK: "localnet" }, true).status).toBe("network-error");
  });
});
