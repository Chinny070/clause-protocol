# CLAUSE frontend architecture (Stage 5)

Single-page application in `frontend/`: **Vite 6 + React 18 + TypeScript 5.7 + react-router 6 (hash routes) + genlayer-js 1.1.8 (pinned) + viem**. No backend, no database, no server-side adjudication, no scraper: every authoritative fact is read from the CLAUSE contract; the app is a static bundle.

## Layers

```
pages/            route screens (Home, Explore, PassportPage, ClaimPage, ReceiptPage, HolderPages, ManufacturerPages, Limits)
ui/               design-system components (kit, passport, evidence, decision, challenge, receipt, actions, shell)
app/              React contexts (ClauseProvider: config+reader+health, WalletProvider, TxProvider), data loaders, useAsync
domain/           pure logic: checklist (finality/window gating), timeline, constitutionDraft (mirrors contract validation), errors, format
contract/         the ADAPTER: calls.ts (typed builders), reader.ts (typed views), decode.ts (strict decoders), transport.ts (SDK boundary)
tx/               status.ts (SDK status -> class), runner.ts (write lifecycle), finality.ts (protocol finality), journal.ts
wallet/           wallet.ts (EIP-1193 state machine; no keys)
config/           contract.ts (the ONE address source), networks.ts (StudioNet only in production)
```

## Contract adapter (`src/contract`)
- `ClauseTransport` is the exact subset of the stable client used: `readContract`, `writeContract`, `getTransaction`, `waitForTransactionReceipt`. Production wraps a real `createClient` (read-only, or wallet-backed with the injected provider); unit tests provide a mock implementing the same interface, so the adapter surface is identical to the SDK.
- `calls.ts` builds each of the 22 write calls with the contract's own parameter names; `tests/abi-parity.test.ts` parses `docs/FRONTEND_CONTRACT_INTERFACE.md` and fails on any name/arity/payable drift. Builders validate arguments (safe integers, 64-hex commitments, non-empty strings) before anything is sent, and send only the four contract citation keys.
- `reader.ts` exposes the 18 views as typed methods. Errors are classified `rpc-unavailable | contract-read-failed | malformed`. `decode.ts` normalizes SDK numerics (numbers / decimal strings / bigint) and rejects anything malformed (`DecodeError`).

## Transaction lifecycle (`tx/runner.ts`)
prepare -> wallet confirmation -> submitted (hash journaled) -> consensus -> accepted -> **FINALIZED with successful leader execution** -> authoritative contract reread -> UI update. A hash is never success; FINALIZED + `ERROR`/unknown is failure; UNDETERMINED/CANCELED/timeouts are reported as such; a stuck ACCEPTED ends as `pending-unknown`; the reread runs only after finality and its data (not the leader value) is what the UI adopts. Nothing is optimistically mutated.

## GenLayer Protocol Finality vs Application Challenge
Two unrelated concepts with separate components and vocabulary: `challenge.tsx` (plum, "Application Challenge") and the `finality-plate` in `actions.tsx` (mint/petroleum, "GenLayer Protocol Finality"). `domain/checklist.ts` returns a per-action checklist (state, windows, recipient, wallet, finality); a button is enabled only if every item is `ok`, and the first non-ok item is the visible "Why is this disabled?" text. `tx/finality.ts` re-verifies the prerequisite transaction from the network on every check and fails closed on any doubt.

## Connection/health states
`ClauseProvider` derives: not configured, invalid address, network error, checking, RPC unavailable, contract read failed / unexpected response, or OK. `WalletProvider` derives: unsupported, disconnected, connecting, connected, wrong network, rejected, error. The wrong-network state blocks writes (the SDK does not check Studio chains).

## Design system
`styles/app.css`: ivory paper ground with dotted grain, brushed-metal and translucent-plastic plates, petroleum manufacturer chrome, copper frame lines, mint for positive, laser red reserved for FROZEN TERMS / exclusions / NOT_COVERED, plum for Application Challenge, yellow for pending. Signature components: Warranty Passport, clause stickers, evidence inspection strips, timestamp seals (with provenance: protocol / claimant-asserted / deadline), diagnostic timeline and stage strip, FROZEN TERMS stamp, thermal Resolution Receipt, capacity gauge. Motion (stamp, scan, receipt print, timeline light-up) exists only inside `@media (prefers-reduced-motion: no-preference)`.

## Configuration
`VITE_CLAUSE_CONTRACT_ADDRESS` (unset until Stage 6; validated, never `undefined` into the SDK) and dev-only `VITE_CLAUSE_NETWORK=localnet` (refused in production). `.env.example` documents both; `.env.local` is git-ignored.
