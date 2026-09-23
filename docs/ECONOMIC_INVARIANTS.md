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
