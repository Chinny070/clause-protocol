# CLAUSE — Economic Invariants (Stage 0)

## The four pool numbers and what they mean

`total_balance` — everything the manufacturer has ever deposited via `fund_pool`, minus everything ever
withdrawn.
`reserved_liability` — sum of every `ACTIVE` Reservation's `amount` (one Reservation per issued, still-
active Passport, created at `issue_warranty`, released at expiry/cancellation, consumed at settlement).
`pending_locks` — subset of `reserved_liability`: the portion additionally locked against a specific
**open Claim** right now (`file_claim` locks; `settle_claim`/claim-terminal states unlock).
`available_balance` — always `total_balance - reserved_liability`, never stored independently; it is
computed, not tracked, so it cannot drift out of sync.

## Core conservation invariant (checked, not just asserted)

At every point in the contract's history:

```
total_balance == sum(withdrawable-to-manufacturer amount not yet withdrawn)
              +  sum(ACTIVE Reservation.amount)
              +  sum(amount already paid out to holders via settle_claim, historically)  [not tracked as a live balance, but every unit is accounted for at the moment it leaves]
```

More usefully as a live per-mutation check: every method that changes `total_balance`,
`reserved_liability`, or `pending_locks` re-derives `available_balance` and asserts it is `>= 0` before
returning — a negative `available_balance` is a hard contract bug and must revert the whole transaction,
never clamp to zero silently.

## Registration fails when capacity is insufficient

`issue_warranty` (`STATE_MACHINES.md`) requires `available_balance >= max_deterministic_remedy` computed
*before* creating the Reservation, in the same transaction. There is no path where a Passport is issued
against undercapitalized pool — this makes "manufacturer pool drain via over-issuance" structurally
impossible rather than merely discouraged.

## Manufacturer cannot withdraw reserved/pending funds

`withdraw_pool` checks against `available_balance`, which by definition excludes `reserved_liability`
(and therefore excludes `pending_locks`, a subset of it). No separate "pending" check is needed — the
subset relationship makes the single `available_balance` check sufficient. Reviewed explicitly against
Protocol Court's live-discovered StudioNet finding that *inbound* payable value can survive a reverted
call (see `THREAT_MODEL.md`) — `fund_pool`'s own payable path is deliberately trivial (unconditional
credit, no business-rule branch that could revert after value arrives) specifically to avoid replicating
that failure mode on the deposit side.

## Expiry releases reservation under frozen rules

`release_expired_reservation` is permissionless specifically so an expired warranty's capacity returns
to `available_balance` without requiring manufacturer action — a manufacturer has no incentive to run
this themselves (it only reduces their own withdrawable headroom's apparent conservatism, not increases
it, since `available_balance` was already computed correctly; but it *does* let them withdraw that
now-freed capacity), so permissionless cleanup avoids capacity getting stuck behind manufacturer
inaction. Cannot run while any Claim referencing that Reservation is still open (checked against
`Claim.status` not being terminal).

## Final covered claims settle once; withdrawals occur once

`Claim.settled_at` and `Claim.withdrawn_at` (`DATA_MODEL.md`) are zero-initialized `u64` fields used as
one-shot guards: `settle_claim` requires `settled_at == 0`, sets it as its first state-changing line
(before any GEN moves) so a re-entrant or retried call cannot double-settle even under the "inbound value
survives revert" style failure mode — the guard is set deterministically regardless of whether the
subsequent transfer succeeds, and a failed transfer after the guard is set is treated as a stuck-fund
incident to be manually resolved (flagged, not silently retried) rather than an invitation to unset the
guard and retry, which would reopen the double-settlement window. Same one-shot pattern for `withdraw`.

## A valid finalized claim is never starved by a later withdrawal

Because `withdraw_pool` can only ever spend `available_balance`, and a FILED-through-FINAL Claim's
backing Reservation stays `ACTIVE` (and its `pending_locks` portion stays locked) for the Claim's entire
lifetime, there is no sequence of manufacturer withdrawals that can reduce the GEN backing an
already-issued, not-yet-settled warranty below `max_deterministic_remedy`. This is the concrete
mechanism satisfying the design spec's "must not be starved" requirement — not a promise, a
structural consequence of the reservation model.

## Deterministic settlement, never semantic

`settle_claim` reads `Claim.final_outcome` (already fixed, from the FINAL Adjudication or its Challenge
correction) and looks up the matching `RemedyRow` in the frozen Constitution's `remedy_table` — plain
Python, no LLM call, no non-deterministic block. The semantic layer (`ADJUDICATION_SCHEMA.md`) never
sees `available_balance`, `total_balance`, or any `RemedyRow.remedy_value` (Counterfactual Independence,
enforced structurally as described in `ADJUDICATION_SCHEMA.md`).

## Accounting conservation — Stage 1 test obligation

Stage 1's test suite must include a property-style test that, after any sequence of
`fund_pool`/`issue_warranty`/`file_claim`/`settle_claim`/`withdraw_pool`/`release_expired_reservation`
calls, `total_balance - reserved_liability == available_balance` holds exactly, and that the sum of all
GEN ever observed leaving the contract (settlements + manufacturer withdrawals) plus current
`total_balance` equals the sum of all GEN ever deposited via `fund_pool`. This is the concrete form of
"prove accounting conservation" from the build brief.


---

## Stage 4 as-implemented: reservation -> settlement -> claimable -> withdrawal

### The accounting model actually implemented

Stage 2 did not implement per-claim `pending_locks`; the frozen Stage 1 accounting is `total_balance`,
`reserved_liability`, and one `Reservation` per warranty. Stage 4 keeps that model and adds no pool fields:

- `Reservation.amount` now means **the amount currently still reserved** for that warranty (initially
  `max_deterministic_remedy`, the warranty's frozen lifetime cap; the passport keeps the original).
- **Settlement** of a payable claim moves `payable` out of the pool in one step:
  `pool.total_balance -= payable`, `pool.reserved_liability -= payable`, `reservation.amount -= payable`,
  `FinalDecision.claimable += payable`. If the reservation reaches 0 it becomes `CONSUMED`.
- **Withdrawal** zeroes `claimable` and emits the transfer. Nothing else changes.

Conservation, checked independently in tests at every step (the test keeps its own ledger of deposits and of every
transfer captured off the VM):

```
deposited - emitted_transfers == sum(pool.total_balance) + sum(claimable outstanding)
sum(pool.reserved_liability)  == sum(Reservation.amount for ACTIVE reservations)
per warranty: Reservation.amount + sum(settled_amount of its claims) == max_deterministic_remedy   (ACTIVE|CONSUMED)
per warranty: sum(settled_amount) <= max_deterministic_remedy
per claim:    settled_amount <= remedy_amount;   withdrawn_amount <= settled_amount;   no value before settled_at
pool:         total_balance >= reserved_liability   (available_balance >= 0, never clamped)
```

`available_balance = total_balance - reserved_liability` is unchanged, and claimable funds are outside `total_balance`,
so `withdraw_pool` can never touch a holder's claimable amount (tested).

### Deterministic remedy (`_select_remedy`, plain Python, no model, no pool data)

Payable only for: `ACCEPTED_NO_CONTEST`; `COVERED`; and an evidence-gap outcome whose FROZEN policy is
`RULE_FOR_HOLDER` (`INSUFFICIENT_EVIDENCE` <- `insufficient_evidence_behavior`, `EVIDENCE_UNAVAILABLE` <-
`unavailable_evidence_behavior`). `NOT_COVERED` and `INVALID_CLAIM` pay zero regardless of table contents. `BLOCK` and
`RULE_FOR_MANUFACTURER` pay zero (`remedy_basis` = `POLICY_BLOCK` / `NON_PAYABLE`).

Row lookup: for each established clause (covered clause ids for `COVERED`; the claim's targeted clauses for
`RULE_FOR_HOLDER`), use the `(COVERED, clause_id)` row, else the outcome-level `(COVERED, "")` row; `ACCEPTED_NO_CONTEST`
uses `(ACCEPTED_NO_CONTEST, "")`. Several established clauses -> the **highest single row**, never a sum. **No matching
row on a payable outcome fails closed** (`finalize_claim` reverts; nothing stored).

Arithmetic (`_remedy_amount`): `FULL_REFUND` = the warranty's frozen max (`remedy_value` ignored);
`PARTIAL_BPS` = `floor(max * bps / 10000)`; `REPAIR_CREDIT` = `min(remedy_value, max)`; `NONE` = 0. The result never
exceeds the frozen max; no later rule increases it (`FinalDecision.remedy_amount` is immutable).

### Warranty capacity is a lifetime cap (overlapping claims)

A warranty may have several claims (a decision does NOT block later claims; only claims still in the response/dispute
phase do). Each claim's `remedy_amount` is computed independently and deterministically at finalize. At **settlement** the
payable is `min(remedy_amount, Reservation.amount)`: the first claims settled consume the frozen maximum; later ones are
capped (`FinalDecision.capped = true`, possibly to 0). Total paid on a warranty can therefore never exceed
`max_deterministic_remedy`, whatever the number of claims or their order. Order-of-settlement dependence is a documented,
deterministic consequence of "first settled, first served", not a race a party can widen.

### Reservation release

A partially used reservation keeps the unused remainder reserved for the rest of the warranty's life (further claims may
still be valid). It is released by the existing permissionless `release_expired_reservation`, which Stage 4 tightens
(both tightenings implement what `ECONOMIC_INVARIANTS.md` Stage 0 already required, "cannot run while any Claim ... is
still open", and protect the claim-deadline grace window that `file_claim` already grants):

1. every claim on the warranty must be `SETTLED` (also required by `cancel_warranty`);
2. an EXPIRED warranty may be released only after `now > coverage_end + claim_deadline_s` (a holder may still file during
   the grace window, so its capacity must stay reserved). A CANCELLED warranty may be released immediately (it can no
   longer be claimed).

A release never touches value already moved to `claimable`.

### One-shot guards (double-spend / double-settlement)

`finalize_claim` (one `FinalDecision` per claim), `settle_claim` (`settled_at` set first, status `FINAL -> SETTLED`),
`withdraw_settlement` (`withdrawn_at` and `claimable = 0` written **before** the transfer is emitted, so a repeated or
re-entrant call finds nothing to take), `file_challenge` (one per claim), `execute_remand` (challenge leaves
`REMAND_PENDING`), `_release_reservation` (requires `ACTIVE`).

### Pull payment

`settle_claim` only authorizes: it creates `claimable` for the recorded recipient (the warranty holder at finalize). The
recipient calls `withdraw_settlement`. No semantic code path transfers value; the model never sees or chooses an amount,
percentage, recipient, or pool figure. A failed transfer after the guard is set is a stuck-fund incident to be handled
manually, not an invitation to unset the guard (unchanged Stage 0 policy).


---

## Stage 4.5: remedy-table completeness and the reservation-release invariant (contract freeze)

**Remedy-table completeness** (enforced in `create_constitution`, before any passport can bind): the table must contain an outcome-level
`(ACCEPTED_NO_CONTEST, "")` row, and either an outcome-level `(COVERED, "")` row or a `(COVERED, c)` row for every covered clause `c`.
This makes every reachable payable final state (ACCEPTED_NO_CONTEST; COVERED and its REVERSED/REMAND corrections; RULE_FOR_HOLDER evidence-gap outcomes;
every non-empty covered-clause subset) resolve to a frozen row, so `finalize_claim` can never fail closed for an issued warranty. Non-payable outcomes need no row.
See `STAGE_4_5_CONTRACT_FREEZE.md`.

**Reservation-release invariant:** capacity is never released (by `release_expired_reservation` or `cancel_warranty`) while a valid claim can still be filed or any claim
on the warranty is not `SETTLED`. Expired warranties additionally wait for `now > coverage_end + claim_deadline_s`. This is a permanent invariant, not a Stage 4 patch.
