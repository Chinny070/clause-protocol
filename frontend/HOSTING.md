# Hosting the CLAUSE frontend (prepared - NOT live)

The app is a static bundle (no server, no database). It becomes "live" only when someone actually publishes `frontend/dist` and it has been checked against the deployed contract. Nothing has been published.

## The only configuration after the contract is deployed

```
VITE_CLAUSE_CONTRACT_ADDRESS=<canonical StudioNet contract address>
```
Set it in the host's build environment (or a git-ignored `frontend/.env.production.local`). It is read in exactly one place (`src/config/contract.ts`; a test enforces this), validated (non-zero EVM address), and never passed to the SDK when missing. Leave `VITE_CLAUSE_NETWORK` **unset** (production is locked to StudioNet, chain 61999; `localnet` is refused in production builds).

## Build

```bash
cd frontend
npm ci
npm run typecheck && npm run lint && npm test
VITE_CLAUSE_CONTRACT_ADDRESS=0x... npm run build      # output: frontend/dist
```
Publish `frontend/dist` as static files. Routes are hash-based (`/#/claim/3`), so **no server rewrite rules are needed** and shared receipt links work on any static host. `public/_headers` (security headers + CSP restricting network access to `self` and `https://studio.genlayer.com`) is copied into `dist` and honoured by Netlify / Cloudflare Pages; other hosts need the equivalent headers configured. The bundle was checked to boot under this exact CSP locally (no violations, "contract not configured" state); **before relying on it, test a wallet connection and a read against StudioNet on the real host** (not verified).

## Before calling it live
1. The contract address passes the assistant's read-only verification.
2. The built site shows "Live on GenLayer StudioNet: N warranty programs" (not "Contract not configured").
3. Open a passport, a claim and a receipt with no wallet connected.
4. Only then update the submission draft's website field.
