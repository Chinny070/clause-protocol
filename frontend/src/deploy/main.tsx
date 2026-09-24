import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import code from "../../../contracts/clause_protocol.py?raw";
import "../styles/app.css";
import { checkDeployedSource, checkSource, deployAndWatch, type DeployClient, type DeployResult, type SourceCheck } from "./deploy";
import { EXPECTED_CONTRACT_SHA256, EXPECTED_PATH } from "./expected";

/**
 * Local, wallet-authorized deployer for the audited CLAUSE release candidate.
 * - Uses the stable genlayer-js 1.1.8 client against StudioNet (chain 61999) only.
 * - The signer is YOUR injected wallet: this page never sees a private key or seed phrase and never asks for one.
 * - It refuses to deploy unless the embedded source hash equals the audited SHA-256.
 */
interface Eth { request(a: { method: string; params?: unknown[] }): Promise<unknown> }

function Deployer() {
  const eth = (window as unknown as { ethereum?: Eth }).ethereum;
  const [check, setCheck] = useState<SourceCheck | null>(null);
  const [account, setAccount] = useState<string | null>(null);
  const [chain, setChain] = useState<number | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<DeployResult | null>(null);
  const [parity, setParity] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const push = (l: string) => setLog((p) => [...p, l]);

  useEffect(() => { void checkSource(code).then(setCheck); }, []);

  const refresh = async () => {
    if (!eth) return;
    const c = parseInt(String(await eth.request({ method: "eth_chainId" })), 16);
    setChain(c);
  };
  const connect = async () => {
    if (!eth) return;
    const a = (await eth.request({ method: "eth_requestAccounts" })) as string[];
    setAccount(a[0] ?? null);
    await refresh();
  };
  const switchChain = async () => {
    if (!eth) return;
    try { await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: `0x${studionet.id.toString(16)}` }] }); }
    catch { await eth.request({ method: "wallet_addEthereumChain", params: [{ chainId: `0x${studionet.id.toString(16)}`, chainName: studionet.name, rpcUrls: [studionet.rpcUrls.default.http[0]], nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 } }] }); }
    await refresh();
  };

  const client = (): DeployClient => createClient({ chain: studionet, account: account as `0x${string}`, provider: eth as never }) as unknown as DeployClient;
  const ready = !!check?.ok && !!account && chain === studionet.id && !busy && !result;

  const deploy = async () => {
    setBusy(true);
    try {
      const c = client();
      const r = await deployAndWatch(c, code, push);
      setResult(r);
      if (r.contractAddress) { try { const p = await checkDeployedSource(c, r.contractAddress); setParity(p.matches ? "Deployed source hash MATCHES the audited hash." : `Deployed source hash ${p.sha256} differs from the audited hash (the network may normalize source; record it and compare manually).`); } catch (e) { setParity(`Could not fetch deployed source: ${e instanceof Error ? e.message : String(e)}`); } }
    } catch (e) { push(`Stopped: ${e instanceof Error ? e.message : String(e)}`); }
    setBusy(false);
  };

  return (
    <div className="shell" style={{ padding: "24px 16px" }}>
      <h1 style={{ fontSize: "2rem" }}>CLAUSE release-candidate deployer</h1>
      <p className="banner bad"><strong>Local tool.</strong> It deploys ONE audited file to GenLayer <strong>StudioNet</strong> (chain {studionet.id}) using YOUR wallet. It never asks for a private key or seed phrase. Deploying is irreversible.</p>
      <section className="plate">
        <h2>1 · The exact file</h2>
        <p>Path: <code>{EXPECTED_PATH}</code></p>
        <p>Audited SHA-256:<br /><code className="wrap">{EXPECTED_CONTRACT_SHA256}</code></p>
        <p>Embedded source SHA-256:<br /><code className="wrap">{check?.sha256 ?? "computing…"}</code> ({check?.bytes ?? "…"} bytes)</p>
        <p className={check?.ok ? "banner ok" : "banner bad"} role="status">{check ? check.reason : "Checking…"}</p>
      </section>
      <section className="plate" style={{ marginTop: 12 }}>
        <h2>2 · Your wallet and network</h2>
        {!eth ? <p className="err">No injected wallet found in this browser.</p> : (
          <>
            <p>Account: <code className="wrap">{account ?? "not connected"}</code> · Chain: {chain ?? "?"} {chain !== null && chain !== studionet.id ? <strong className="err">(wrong: need {studionet.id})</strong> : null}</p>
            <div className="row"><button type="button" className="btn" onClick={() => void connect()}>Connect wallet</button><button type="button" className="btn secondary" onClick={() => void switchChain()}>Switch to StudioNet ({studionet.id})</button></div>
          </>
        )}
      </section>
      <section className="plate" style={{ marginTop: 12 }}>
        <h2>3 · Deploy (constructor arguments: none)</h2>
        <p>Your wallet will ask you to approve ONE transaction. Approve it only if the network is StudioNet ({studionet.id}).</p>
        <button type="button" className="btn warn" disabled={!ready} onClick={() => void deploy()}>Deploy CLAUSE to StudioNet</button>
        {!ready && !result ? <p className="small"><strong>Why disabled?</strong> {!check?.ok ? "The source hash does not match." : !account ? "Connect your wallet." : chain !== studionet.id ? "Switch your wallet to StudioNet." : busy ? "Deploying…" : ""}</p> : null}
        <pre className="diag" aria-live="polite">{log.join("\n")}</pre>
      </section>
      {result ? (
        <section className="plate plastic" style={{ marginTop: 12 }}>
          <h2>4 · Record these</h2>
          <p>Deployment transaction hash:<br /><code className="wrap">{result.hash}</code></p>
          <p>Final status: <strong>{result.status}</strong> · execution: <strong>{result.executionResult}</strong></p>
          <p>Contract address:<br /><code className="wrap">{result.contractAddress ?? "not found automatically - copy it from the raw receipt below or from the StudioNet explorer using the hash"}</code></p>
          {parity ? <p>{parity}</p> : null}
          <details><summary>Raw receipt (copy this if the address is not shown)</summary><pre className="diag">{JSON.stringify(result.raw, (_k, v) => (typeof v === "bigint" ? v.toString() : v), 2)}</pre></details>
        </section>
      ) : null}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Deployer />);
