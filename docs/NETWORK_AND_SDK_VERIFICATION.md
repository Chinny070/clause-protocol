# Network & SDK Verification

Verified live against `docs.genlayer.com` on 2026-09-23. This is the gating document —
every other Stage 0 doc assumes these facts and nothing older.

## Network constants (confirmed against `/developers/networks`)

| Setting | Studionet (target) | Studio dev (NEVER use) |
|---|---|---|
| RPC | `https://studio.genlayer.com/api` | `https://studio-dev.genlayer.com/api` |
| Chain ID | `61999` | `61997` |
| Currency | GEN | GEN |
| Persistence | Temporary (Studio-hosted) | Temporary, resets expected |
| Fee model | Gasless (no `FeesDistribution` requirement observed on this line) | Fee-funded, v0.6 RC lifecycle |

Matches the design spec's hard boundary exactly: stable `studionet`/61999/`https://studio.genlayer.com/api`.
Confirmed distinct from `studio-dev` (61997) even if an alias like `studio-next.genlayer.com` is enabled in
the browser — CLAUSE must not point at the RC RPC or mix RC tooling (`genlayer-js` v2.0 RC, `genlayer-py`
v0.19 RC, CLI v0.40 RC) into the stable build.

## Consensus v0.6 migration (`/developers/consensus-v06-migration`) — read, not adopted yet

The v0.6 release family (fee-funded transactions, `getAppealCharge`/`appealTransaction` with an explicit
bond+work charge, ECVRF randomness, tribunals) is the **release-candidate line** (Studio v0.123 RC / chain
61997). Stage 0 targets stable Studionet, which this migration note explicitly treats as the pre-v0.6
baseline. **Decision:** CLAUSE Stage 1+ builds against stable Studionet's current appeal/fee model, not the
RC lifecycle, until the user explicitly asks to track the RC. Re-check this page immediately before Stage 4
(appeals/finality/settlement) in case Studionet has been promoted to v0.6 by then — this is a real drift
risk given the note's own "promoted to Studionet" language.

## Storage types (confirmed against `/developers/intelligent-contracts/features/storage`)

- `DynArray[T]` not `list[T]`; `TreeMap[K, V]` not `dict[K, V]`; sized ints (`u32`, `u256`, `i64`) not `int`;
  `bigint` only for arbitrary precision; all generics fully specified.
- Custom structs via `@allow_storage @dataclass`.
- Storage is zero-initialized (relevant to Warranty/Claim default-state safety — no field can be
  accidentally read as "valid" before being explicitly set).
- Explicit caveat from the docs: "reading storage directly in non-deterministic blocks" is not yet
  supported — confirms the Stage 1 pattern of copying needed storage fields into plain local variables
  *before* entering a `gl.vm.run_nondet_unsafe` block, never referencing `self.x` inside `leader_fn`/`validator_fn`.

## Value transfers (confirmed against `/developers/intelligent-contracts/features/value-transfers`)

- GEN is native, 1 GEN = 10^18 wei, `u256` for amounts.
- `@gl.public.write.payable` + `gl.message.value: u256` to receive.
- IC→IC value: `other.emit_transfer(value=u256(n), on='finalized')` or `.emit(value=..., on=...).method()`.
- IC→EOA/EVM: via `@gl.evm.contract_interface` ghost-contract pattern, always executes on finalization.
- **Critical for the Warranty Pool:** "If the child transaction fails, the value is not automatically
  returned to the sender" (outbound) — matches this workspace's independently-observed StudioNet finding
  that *inbound* payable value also survives a reverted call (see Threat Model, and Protocol Court's
  live `FILING_BOND_MISMATCH` incident). Both directions of "value stuck despite logical failure" must be
  designed against, not assumed away.
- **Studio-specific:** balances are simulated in a local DB, no ghost contract/EVM layer — `self.balance`
  in Studio round-trips are not evidence of real ghost-contract custody behavior on a live chain layer.

## Web access (confirmed against `/developers/intelligent-contracts/features/web-access`)

- `gl.nondet.web.get(url)`, `gl.nondet.web.request(url, method=, body=)`, `gl.nondet.web.render(url,
  mode='html'|'screenshot')` (a `mode='text'` variant is referenced elsewhere in the doc set for
  JS-rendered readable pages — reverify the exact literal at Stage 2 implementation time).
- Response now exposes **`.status_code`** and `.body: bytes`. **This is a drift from earlier
  verifications in this workspace** (prior sessions on other GenLayer projects here recorded `.status`,
  not `.status_code`, as of August 2026) — treat `.status_code` as current truth for CLAUSE, and re-grep
  the installed `genlayer` package at Stage 2 to confirm the exact attribute before writing evidence-fetch
  code. This is exactly the kind of silent API drift Stage 0 verification exists to catch.
- `gl.get_webpage` **does not exist** — confirmed absent from current docs, consistent with every other
  GenLayer project in this workspace's independent findings. Never use or invent it.
- Docs explicitly warn: leaders and validators make independent web requests: extract only stable fields,
  or derive a summary status, before comparing — never `strict_eq` a raw fetched page.

## Equivalence principle (confirmed against `/developers/intelligent-contracts/equivalence-principle`)

This is the single most load-bearing page for CLAUSE's adjudication design, and it has evolved
significantly since prior projects here were built:

- **`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` is now the documented, recommended default** for
  custom leader/validator logic ("this is what production contracts do"), not a low-level fallback.
  `gl.vm.run_nondet` (sandboxed, catches validator exceptions, used internally by the convenience
  wrappers) is explicitly framed as secondary.
- `strict_eq` only for outputs that can be canonicalized to an exact match (e.g. `json.dumps(...,
  sort_keys=True)` over objective fields).
- `prompt_comparative` / `prompt_non_comparative` are now explicitly described as convenience wrappers
  that "most contracts outgrow quickly" — the docs steer new contracts toward hand-written
  `run_nondet_unsafe` validators from the start, which matches (and now supersedes) this workspace's
  earlier finding that the local `gltest` direct-mode harness couldn't mock the `ExecPromptTemplate` calls
  those wrappers issue.
- The validator's parameter is a `gl.vm.Result`: `gl.vm.Return[T]` (`.calldata`), `gl.vm.UserError`, or
  `gl.vm.VMError` — must type-check before use.
- Explicit, named anti-pattern: a validator that only checks the leader's output *shape* (enum membership,
  confidence range, non-empty string) is "leader-output-only validation" and is called out as insecure —
  directly relevant to CLAUSE's Adjudication Schema, which must be validated both for shape *and* by
  independent re-derivation, never shape alone.
- Named error-classification pattern (`[EXPECTED]` / `[EXTERNAL]` / `[TRANSIENT]` / `[LLM_ERROR]` prefixes)
  for handling leader errors inside a hand-written validator — adopted directly into CLAUSE's Evidence
  Architecture (see `EVIDENCE_ARCHITECTURE.md`).

## Finality and transaction status (confirmed against Finality / Transactions core-concept pages)

- Lifecycle: decided outcome (Accepted / Undetermined / ValidatorsTimeout / LeaderTimeout) → appeal window
  → `resolutionAction: "Finalize"` → anyone submits the finalization action → status becomes Finalized.
  Appeal-window duration is protocol-configured, not a fixed constant applications should hardcode.
- **Accepted is not final** and does not mean "execution succeeded" — only that the committee agreed on
  the receipt, which can itself contain a `UserError` or VM error. CLAUSE must gate settlement exclusively
  on Finalized + a successful execution result, never on Accepted alone.
- Query surface: `gen_getTransactionStatus` (lightweight polling), `gen_getTransactionLifecycle`
  (projection + available resolution actions), `gen_getTransactionReceipt` (full consensus receipt).
- On-acceptance emitted messages are not revoked by a later appeal; on-finalization messages only fire
  after finality. CLAUSE's settlement-moving messages must be finalization-gated.

## Frontend SDK (confirmed against Value Transfers / Interacting-with-Intelligent-Contracts pages)

- `genlayer-js`: `createClient({ chain, account })`, `createAccount()`, `client.writeContract({address,
  functionName, args, value})`, `client.estimateTransactionFeesForWrite(write)` (fee estimate — Studionet
  itself appears gasless per the network table, but the estimate call is part of the current stable
  write path and should be probed live at Stage 5, not assumed absent).
- Appeal surface on the stable line has not been independently re-confirmed this session beyond the v0.6
  migration note's description of the RC's `getAppealCharge`/`appealTransaction`; Stage 4 must re-verify
  the exact stable-line appeal call shape before wiring the frontend Challenge screens.

## Open items carried into Stage 1 scope

1. Confirm the exact `gl.nondet.web.render` mode literal set (`'text'` vs `'html'` vs `'screenshot'`) by
   reading the installed `genlayer` package source, not docs prose alone — the Web Access page's own
   examples only show `'html'` and `'screenshot'`.
2. Confirm `Response.status_code` against the installed package (drift risk noted above).
3. Re-confirm whether stable Studionet has been promoted to the v0.6 fee-funded lifecycle before Stage 4.
4. Confirm the current stable-line (non-RC) appeal call surface in `genlayer-js`/`genlayer-py` before any
   application-appeal-vs-protocol-appeal wiring.

**If documentation and installed APIs disagree at implementation time: document the disagreement and
stop, per the build brief — do not guess.**
