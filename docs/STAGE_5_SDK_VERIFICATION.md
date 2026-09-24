# Stage 5 - GenLayerJS SDK verification (stable StudioNet generation)

Verified 2026-09-24, independently of earlier stages, by installing the package and probing it (scripts kept out of the repo; results reproduced by `frontend/tests/integration/adapter.integration.test.ts`).

## Package selection

| Item | Finding |
|---|---|
| npm `genlayer-js` dist-tags | `latest` = **1.1.8** (stable), `rc` = 2.0.0-rc.1 |
| Chosen | **`genlayer-js@1.1.8`, pinned exactly** (`frontend/package.json`; a test fails if the range loosens). The RC (2.x) is Studio-Next-generation and is never installed or referenced. |
| Exports (`genlayer-js`) | `abi, buildGenVmPositionalArgs, chains, createAccount, createClient, decodeInputData, decodeLocalnetTransaction, decodeTransaction, formatStakingAmount, generatePrivateKey, parseStakingAmount, simplifyTransactionReceipt` |
| Exports (`genlayer-js/chains`) | `localnet, studionet, testnetAsimov, testnetBradbury` (no chain 61997 object exists in this generation) |
| Exports (`genlayer-js/types`) | `TransactionStatus` etc. |
| Peer/transitive | `viem ^2.29` (also a direct dependency for address validation) |

## Chain objects (from the SDK itself; asserted by `tests/config.test.ts`)

| Chain | id | RPC | currency | `isStudio` |
|---|---|---|---|---|
| `studionet` | **61999** (`0xf22f`) | `https://studio.genlayer.com/api` | GEN | yes |
| `localnet` (development/integration only) | 61127 (`0xeec7`) | `http://127.0.0.1:4000/api` | GEN | - |

Production builds are locked to StudioNet: `resolveNetwork` refuses any other target in a production build.

## Client API actually used

`createClient({ chain, account?, provider? })` then only:
- `readContract({ address, functionName, args })` - returns decoded plain objects/lists/numbers; **integers above 2^53 come back as decimal strings** (observed for 5 GEN = `"5000000000000000000"`), small integers as numbers, `{}` for unknown ids. The adapter (`decode.ts`) normalizes amounts to `bigint` and treats anything else as a `DecodeError` (fail closed). Unknown map/object shapes are never guessed.
- `writeContract({ address, functionName, args, value })` - `args` accept numbers, bigints, strings, arrays and plain objects (verified: the `citation` dict, remedy-table rows, and 5e18 `bigint` amounts all round-trip); `value` is a `bigint` (payable `fund_pool` verified against the simulator with the msg.value shim).
- `getTransaction({ hash })` - carries `status` (numeric), `statusName`/`status_name`, and `consensus_data.leader_receipt[0].execution_result`.
- `waitForTransactionReceipt({ hash, status, retries, interval })` - used by tooling; the app polls `getTransaction` for finer phases.

`TransactionStatus` order (1.1.8): UNINITIALIZED, PENDING, PROPOSING, COMMITTING, REVEALING, **ACCEPTED**, UNDETERMINED, **FINALIZED** (numeric 7), CANCELED, APPEAL_REVEALING, APPEAL_COMMITTING, READY_TO_FINALIZE, VALIDATORS_TIMEOUT, LEADER_TIMEOUT. The frontend maps these in `tx/status.ts`; only `FINALIZED` **with** leader execution result `SUCCESS` is "Safe to continue". A FINALIZED transaction whose leader result is `ERROR` (a contract `UserError`) or unknown is a failure (verified on the simulator: reverted calls finalize with `execution_result: "ERROR"`).

## Wallet integration facts (read from the SDK source)

- With `account` set to an **address string** and an injected provider, the SDK routes `eth_sendTransaction`, `eth_signTransaction`, `personal_sign`, `eth_signTypedData_v4`, `eth_accounts`, `eth_requestAccounts` to the provider (`config.provider` or `window.ethereum`); everything else goes to the RPC. CLAUSE passes the injected provider explicitly.
- **Studio chains skip the SDK's chain-match assertion** (`assertChainMatch` returns early for `isStudio`). CLAUSE therefore enforces the chain itself (`wallet/wallet.ts`): a wallet on the wrong chain cannot send, and the UI says why.
- **`client.connect()` is deliberately NOT used.** It requires the MetaMask GenLayer *snap* to be installed and calls `wallet_getSnaps` / `wallet_requestSnaps`. CLAUSE uses standard EIP-3326 `wallet_switchEthereumChain` with an EIP-3085 `wallet_addEthereumChain` fallback (chain params taken from the SDK chain object).
- No private key is ever requested. `createAccount`/`generatePrivateKey` are never imported by shipped code (a static test forbids it); the only key generation is in `tests/helpers/ephemeral.ts`, a throwaway signer for the local-simulator integration test.

## What was and was not verified

| Verified locally (glsim + real genlayer-js 1.1.8) | NOT verifiable here (Stage 6 gates) |
|---|---|
| deploy, read, write, payable write, dict/list/bigint args, decode of every read model, execution-error detection, status polling | StudioNet `getTransaction` response shape and field names on the live network |
| the full CLAUSE lifecycle through the production adapter (see `STAGE_5_VERIFICATION.md`) | injected-wallet `eth_sendTransaction` signing on StudioNet (no wallet was used) |
| numeric status mapping, FINALIZED vs execution result | real ACCEPTED -> FINALIZED timing and appeal-window behaviour |
| | how a wallet displays GenLayer transactions; RPC rate limits; CORS from a static host |

If any StudioNet response differs from this shape, the adapter fails closed (unknown status/result never enables an irreversible step).
