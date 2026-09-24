# Finality-hash discovery (Stage 5 limitation, investigated in Stage 6A)

**Problem.** Before finalize / settle / withdraw the app must verify GenLayer Protocol Finality of the transaction that produced the state it depends on. The frozen contract stores no transaction hashes, so a visitor who did not send that transaction has no hash to check.

## What was investigated (genlayer-js 1.1.8, read from the installed package; contract frozen)

| Candidate | Finding |
|---|---|
| Contract views | No view exposes any transaction hash (`get_claim`, `get_adjudication`, `get_final_decision`, `get_resolution_receipt` carry ids and protocol timestamps only). |
| SDK methods that take a **contract/account** and return its transactions | **None.** The client exposes `getTransaction`, `getTransactionReceipt`, `getTransactionCount` (an account nonce, not a list), `getTriggeredTransactionIds`, `debugTraceTransaction`, `getBlock*`, `getLogs`, `getContractCode/Schema` - but no "transactions for address" call. RPC names present in the SDK: `gen_call`, `gen_getContractCode`, `gen_getContractSchema(ForCode)`, `gen_dbg_traceTransaction`, `sim_cancelTransaction`, `sim_fundAccount`, `eth_getTransactionCount`. |
| `getTriggeredTransactionIds({hash})` | Requires a starting hash and returns transactions **triggered by** that one (emitted messages); on Studio chains it reads `triggered_transactions` from `getTransaction`. It cannot start from a claim. |
| Block/log scanning (`getLogs`, `getBlock`) | Present as generic viem actions, but I could not verify that StudioNet serves CLAUSE transactions through them (the local simulator does not model this), and scanning is not a reliable, bounded design. **Not relied on.** |
| Hash derivable from state | No: contract state does not contain it. |

**Conclusion: with the frozen contract and stable StudioNet / genlayer-js 1.1.8 there is no verified, reliable way to recover the relevant transaction hash from contract or network data.** I did not invent an API. (An external indexer or the StudioNet explorer's per-address transaction list may exist; neither was verified.)

## Safest UX (already implemented in Stage 5)

1. Transactions sent from this browser are journaled (`localStorage`, keyed by contract + claim + function) and verified automatically.
2. For a step someone else sent, the user pastes that transaction's hash into the "Transaction hash to verify" field of the relevant step; the app verifies it live from the network. Public explorer pages show which step's hash is needed ("no transaction hash is known for adjudicate_claim").
3. **Fail closed:** without a verified Finalized + successful hash the irreversible step stays disabled with the reason spelled out. Nothing is inferred from application state.

## Possible improvements (need a decision; none is required for deployment)

- **Shareable verification links** (frontend only, no contract change): a claim link carrying `?tx-adjudicate=0x…` pre-fills the hash so the party who sent the step can hand the next person a link.
- **Explorer-assisted lookup** (after StudioNet gates): if the StudioNet explorer offers a per-address or per-contract transaction list, add an optional lookup that still verifies each candidate hash through `getTransaction` and only trusts `FINALIZED` + `SUCCESS` + matching function name/args.
- **Contract change (would reopen the freeze):** store the deciding transaction hash, or emit an event with it, at each state transition. Not recommended for this release.
