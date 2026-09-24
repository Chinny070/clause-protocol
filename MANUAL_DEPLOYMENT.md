# CLAUSE - Manual StudioNet deployment (for the person deploying)

**Nothing in this repository deploys anything. You deploy, with your own wallet. You never give anyone your private key or seed phrase, and no step below asks for one.**

## The one file that gets deployed

| | |
|---|---|
| File | `contracts/clause_protocol.py` (in this repository) |
| **SHA-256** | **`07d7e4bfdbaeeba2d30129c00034cd728681ed99877286a16189005fbe7d847e`** |
| Size | 134,456 bytes, ASCII, LF line endings |
| Git | commit that contains this document; the file is byte-identical to its Stage 4.5 freeze blob (`5e7e7f3b…`) |
| Header | `# v0.1.0` and `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` |
| Constructor arguments | **none** (no arguments; `__init__(self)`) |
| Payable at deploy | no |

Check the hash yourself before deploying (any one of these; the output must equal the SHA-256 above, character for character):

```powershell
Get-FileHash contracts\clause_protocol.py -Algorithm SHA256
```
```bash
sha256sum contracts/clause_protocol.py
```

If the hash differs (for example your editor changed line endings), **stop and do not deploy**: get a fresh copy from Git (`git checkout -- contracts/clause_protocol.py`; `.gitattributes` forces LF).

## Target network (all four must match)

| | |
|---|---|
| Network | GenLayer **StudioNet** (stable) |
| Chain ID | **61999** (`0xf22f`) |
| RPC | `https://studio.genlayer.com/api` |
| Currency | GEN |

**Do NOT use** Studio Next, chain **61997**, any testnet (Asimov/Bradbury), localnet, or any release-candidate / "v2" tooling. If anything on screen shows a different chain ID, stop.

## Route 1 (recommended): the local deployer page in this repo - your wallet signs

Why this route: it uses the exact SDK generation that was audited (`genlayer-js` 1.1.8), embeds the audited file, **refuses to deploy unless the file's SHA-256 matches**, and signs with your browser wallet (no key ever leaves the wallet).

1. Open a terminal in the repository and run (first time only, once):
   ```bash
   cd frontend
   npm install
   ```
2. Start the deployer (it serves a page on your own computer only, `127.0.0.1:5174`, and opens it):
   ```bash
   npm run deploy:tool
   ```
3. On the page, section **1 · The exact file** must show **"Source matches the audited release candidate."** and the two SHA-256 lines must be identical to the hash at the top of this document. If not: stop.
4. Section **2**: click **Connect wallet** and approve the connection in your wallet. Then click **Switch to StudioNet (61999)** and approve the network switch/add. The page must show `Chain: 61999`.
5. Section **3**: click **Deploy CLAUSE to StudioNet**. Your wallet opens **one** transaction request. **Check it says network StudioNet / chain 61999**, then approve it. That is the only approval needed. (GenLayer's documentation describes StudioNet as gasless, so a zero GEN balance should not block deployment; I have not verified this on the live network.)
6. Watch the log. You should see, in order:
   - `Waiting for your wallet to approve the deployment...`
   - `Submitted. Transaction hash: 0x...`  (**this means the deployment was submitted**, not that it succeeded)
   - `Status: PENDING` / `PROPOSING` / `COMMITTING` / `REVEALING` ...
   - `Status: ACCEPTED` (validators agreed; not final yet)
   - `Status: FINALIZED (execution SUCCESS)`  ← **this is success**
7. Section **4 · Record these** appears. Copy and save, exactly:
   - **Deployment transaction hash** (`0x` + 64 hex characters)
   - **Contract address** (`0x` + 40 hex characters)
   - the line about deployed-source parity (it should say the hash MATCHES; if the network normalizes the source it may show a different hash - copy that line too, do not treat it as failure by itself)
8. If the address is not shown but status is `FINALIZED (execution SUCCESS)`, open **Raw receipt**, copy all of it, and also look the transaction hash up in the StudioNet explorer to read the contract address.
9. Send the hash and address back to the assistant. **That is all the assistant needs**; it then verifies everything read-only.

If the page ends at `UNDETERMINED`, `CANCELED`, a timeout, or `FINALIZED (execution ERROR)`: **nothing was deployed**. Do not retry blindly - send the log to the assistant.

## Route 2 (fallback): GenLayer Studio web page

If Route 1 fails for a wallet reason, you may deploy the same file through GenLayer's hosted Studio for **StudioNet** (chain 61999): paste the **entire** contents of `contracts/clause_protocol.py` unchanged, deploy with **no constructor arguments**, and approve only what your wallet shows. **I could not verify the Studio web UI steps from here** (its documentation was not retrievable), so follow its on-screen prompts and re-check the hash of what you pasted (Studio may display a different hash than the repo file because of line-ending normalization - record it). Use Route 1 whenever possible.

## Route 3 (NOT recommended): command line

The GenLayer CLI (`genlayer deploy --contract contracts/clause_protocol.py --rpc https://studio.genlayer.com/api`) manages keys in a local password-protected keystore. **Do not use it unless you already use it and understand where your key lives, and never paste a private key into a terminal.** I could not verify which SDK generation the current CLI targets, and this document forbids mixing RC/v2 tooling with stable StudioNet.

## What you must NOT do

- Do **not** paste a private key or seed phrase anywhere (terminal, web page, chat, this repository).
- Do **not** edit `contracts/clause_protocol.py` - even a trailing space changes the hash.
- Do **not** deploy twice "to be sure": each deployment creates a **different** contract address. The audited address is the first one that finalized successfully.
- Do **not** use Studio Next, chain 61997, a testnet, or a different browser wallet network.
- Do **not** fund the contract or create any warranty yet - the smoke test (`MANUAL_SMOKE_TEST.md`) comes after the assistant has verified the deployment read-only.
- Do **not** set the address in the frontend until the read-only verification passes.

## After you send the hash and address (assistant, read-only)

1. Read the deployment transaction from StudioNet: status `FINALIZED`, leader execution `SUCCESS`, sender = your address, target/creation = the contract address.
2. Fetch the deployed source (`getContractCode`) and compare its SHA-256 to `07d7e4bf…`; fetch the deployed schema and compare to the frozen interface (40 methods: 18 view, 22 write, 1 payable `fund_pool`).
3. Call the views `now()` and `list_program_ids()` (expected `[]`).
4. Only then: `VITE_CLAUSE_CONTRACT_ADDRESS=<address>` is set for the frontend build (the only configuration change; see `frontend/HOSTING.md`).
