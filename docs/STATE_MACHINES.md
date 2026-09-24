# CLAUSE — State Machines (Stage 0)

For every transition: caller, preconditions, state changes, timestamp changes, financial effect,
failure behavior, terminal behavior.

## WarrantyProgram

`ACTIVE <-> PAUSED -> RETIRED` (RETIRED terminal). Manufacturer-only. Pausing blocks new
`issue_warranty` calls but never touches existing Passports/Claims. Not the focus of Stage 0 — modeled
for completeness, detailed transitions deferred to Stage 1.

## WarrantyPassport

`ACTIVE -> EXPIRED` (automatic, derived from `coverage_end` at read time or on next relevant write —
never requires a dedicated "expire" transaction that could be forgotten) and `ACTIVE -> CANCELLED`
(explicit, holder- or manufacturer-initiated per the Constitution's `expiry_cancellation_rules`).

- **issue_warranty** — caller: manufacturer of the Program. Preconditions: Program ACTIVE; Constitution
  exists under this Program; pool `available_balance >= max_deterministic_remedy`. State changes: creates
  Passport (status ACTIVE), creates Reservation (ACTIVE, amount = `max_deterministic_remedy`), increments
  pool `reserved_liability`, sets Constitution `is_frozen = True` if not already. Timestamp: sets
  `registered_at`. Financial effect: reserves but does not move GEN — GEN was already deposited via
  `fund_pool`. Failure: reverts on insufficient available balance, inactive Program, or Constitution
  belonging to a different Program. Terminal: none, this is the entry transition.
- **cancel_warranty** — caller: the warranty's holder ONLY (V1 policy: the manufacturer cannot cancel an issued warranty; pause/retire of a Program stops future issuance only). Preconditions: no unsettled
  Claim referencing this warranty. State: Passport -> CANCELLED, Reservation -> RELEASED, pool
  `reserved_liability -= amount`. Terminal.

## WarrantyPool / Reservation

- **fund_pool** — caller: manufacturer, payable. State: `total_balance += gl.message.value`. No
  precondition beyond value > 0.
- **withdraw_pool** — caller: manufacturer. Precondition: `amount <= available_balance` (i.e. never
  touches `reserved_liability`). State: `total_balance -= amount`, emits GEN to manufacturer. Failure:
  reverts if amount exceeds available balance — this is the enforcement point for "a valid finalized
  claim must not be starved by a later withdrawal," since a Reservation already removed its amount from
  `available_balance` the moment `issue_warranty` ran, long before any Claim exists.
- **release_expired_reservation** — callable by anyone (permissionless cleanup), precondition: linked
  Passport is EXPIRED or CANCELLED and no OPEN Claim references it. State: Reservation -> RELEASED, pool
  `reserved_liability -= amount`. Terminal for that Reservation.
- **consume_reservation** (internal, called from settlement) — Reservation -> CONSUMED,
  `reserved_liability -= amount`, `pending_locks -= amount` if it had been locked, GEN moves per
  `RemedyRow`. Never callable directly.

## Claim (the primary lifecycle)

```
FILED -> RESPONSE_WINDOW -> EVIDENCE_FROZEN -> ADJUDICATING -> DECIDED -> CHALLENGE_WINDOW -> FINAL -> SETTLED
```

Explicit alternative terminal/near-terminal states: `ACCEPTED_NO_CONTEST`, `INSUFFICIENT_EVIDENCE`,
`EVIDENCE_UNAVAILABLE`, `INVALID_CLAIM`, `CANCELLED`, `EXPIRED`.

- **file_claim** — caller: holder (or anyone authorized by the Passport, V1: holder only). Preconditions:
  Passport ACTIVE, `now <= coverage_end + constitution.claim_deadline_s` (exact deadline anchor is a
  Stage 1 decision — anchored to `coverage_end` by default per the spec's "claim deadline" field, not to
  `failure_asserted_at` since that is claimant-asserted, not authoritative), pool `pending_locks +
  amount <= reserved_liability` for this warranty's own Reservation (i.e. lock never exceeds what was
  already reserved for this specific warranty). State: Claim created (FILED), immediately advances to
  RESPONSE_WINDOW in the same transaction (no manufacturer action needed to start their own clock),
  `response_deadline = now + manufacturer_response_period_s`, pool `pending_locks += amount`. Financial
  effect: locks (does not move) GEN. Failure: reverts on expired/inactive Passport, missing warranty, or
  deadline passed -> caller should see `INVALID_CLAIM` as a view-level classification, not a silent
  revert-only failure (Stage 1 to decide exact revert-vs-INVALID_CLAIM UX, frozen principle: never leave
  ambiguity about why a claim did not file).
- **respond_to_claim** — caller: manufacturer. Preconditions: status RESPONSE_WINDOW, `now <=
  response_deadline`. Two branches:
  - `ACCEPT_NO_CONTEST`: State -> `ACCEPTED_NO_CONTEST` directly (skips EVIDENCE_FROZEN/ADJUDICATING/
    DECIDED entirely — "an accepted claim does not need semantic re-adjudication"). Then proceeds straight
    to settlement using the Constitution's remedy row for `ACCEPTED_NO_CONTEST` as if it were a terminal
    `outcome`.
  - `DISPUTE`: records `dispute_clause_ids` and optional counter-evidence submissions (as EvidenceRecords
    with `submitter = manufacturer`), stays in RESPONSE_WINDOW until the window closes or the holder/
    anyone triggers `close_response_window`.
- **expire_response_window** — callable by anyone once `now > response_deadline` with no response
  recorded. State -> RESPONSE_WINDOW closed, moves to EVIDENCE_FROZEN path (silence follows only the
  precommitted rule — the Constitution's silence behavior, e.g. treat as DISPUTE-by-default or
  ACCEPT-by-default, is a per-Constitution frozen field, never an invented runtime default).
- **freeze_evidence** — caller: anyone (permissionless), precondition: status is RESPONSE_WINDOW-closed
  or DISPUTE-recorded, all cited EvidenceRecords have `eligibility == ELIGIBLE`. This is its own
  transaction, separate from `adjudicate`, per this workspace's standing lesson from Treasury
  Trial/Protocol Court that evidence freeze and adjudication must be separately committed state
  boundaries. State: every referenced EvidenceRecord's mutable fields lock (`frozen_at` set,
  `extracted_facts`/`fingerprint` become immutable), Claim -> EVIDENCE_FROZEN, `evidence_frozen_at` set.
  Failure: if any required evidence category has zero ELIGIBLE records and the Constitution's
  `insufficient_evidence_behavior` fires, Claim instead -> `INSUFFICIENT_EVIDENCE` (terminal short of
  ADJUDICATING) or `EVIDENCE_UNAVAILABLE` if the failure is retrieval-side (see `EVIDENCE_ARCHITECTURE.md`
  for the exact eligibility/retrieval-status distinction driving this branch).
- **adjudicate** — caller: anyone (permissionless), precondition: status EVIDENCE_FROZEN. Enters
  ADJUDICATING for the duration of the GenVM non-deterministic block, then DECIDED on success. Creates
  one `Adjudication` record (see `ADJUDICATION_SCHEMA.md`). If GenVM consensus is undetermined
  (validators cannot agree), the transaction reverts entirely — Claim remains EVIDENCE_FROZEN, callable
  again by anyone (retryable, no state corruption per the "failed/undetermined consensus" security
  requirement).
- **open_challenge_window** — automatic, same transaction as DECIDED. `challenge_window` deadline set
  from `constitution.challenge_window_s`.
- **file_challenge / resolve_challenge** — see `APPEALS_AND_FINALITY.md`. On resolution, Claim moves to
  FINAL either directly (challenge window expired with no challenge, or challenge UPHELD/INVALID) or
  after a REVERSED/REMAND correction produces a new Adjudication that itself opens one further (bounded,
  non-recursive per V1's one-challenge-round default) resolution path.
- **finalize_claim** — automatic once: challenge window closed with no open Challenge, AND the underlying
  GenLayer protocol transaction for the deciding Adjudication (or the correcting one) has itself reached
  GenLayer protocol Finality (see `NETWORK_AND_SDK_VERIFICATION.md` — Accepted is not final). Claim ->
  FINAL, `final_outcome` set, `ResolutionReceipt` created.
- **settle_claim** — caller: anyone (permissionless), precondition: status FINAL, not already settled.
  State: Claim -> SETTLED, `consume_reservation` runs, GEN moves per the matching `RemedyRow` for
  `final_outcome`/clause. Idempotency: a `settled_at != 0` guard makes double-settlement structurally
  impossible, not just discouraged.
- **withdraw** — caller: the settlement's GEN recipient (holder, on a covered outcome). Pull-model,
  single use, guarded by a `withdrawn_at` flag identical in spirit to `settled_at`.

Narrow remand: a `REMAND` Challenge result re-triggers exactly one bounded `adjudicate`-equivalent step
that must cite the specific defect named in the Challenge — never a full free re-litigation, and never
more than the Constitution's `challenge_depth` (V1 = 1) rounds total regardless of how many times REMAND
fires (a REMAND that would exceed `challenge_depth` instead resolves as `INVALID_CHALLENGE`).

## EvidenceRecord (nested inside Claim's lifecycle)

`submitted -> (eligibility check) -> ELIGIBLE|INELIGIBLE -> (retrieval, only if ELIGIBLE) ->
retrieval_status set -> (freeze_evidence) -> frozen (immutable)`. INELIGIBLE records are kept (never
deleted — permanent audit trail) but excluded from what `freeze_evidence` locks in as admissible.

## Adjudication / Challenge

Adjudication has no independent state machine beyond `superseded: bool`, flipped only when a Challenge
resolves REVERSED and produces a corrected Adjudication. Challenge: `OPEN -> {UPHELD, REVERSED, REMAND,
INVALID_CHALLENGE}`, all four terminal for that specific Challenge record (a REMAND's *follow-up*
adjudication step is a new Adjudication, not a reopening of the same Challenge).

## Stage 2 as-implemented: Claim and EvidenceRecord

Simpler than the original full sketch above, since Stage 2 stops at frozen evidence — no
`ADJUDICATING`/`DECIDED`/`CHALLENGE_WINDOW`/`FINAL`/`SETTLED` states exist yet:

```
RESPONSE_WINDOW -> ACCEPTED                       (respond_to_claim("ACCEPT"), before deadline)
RESPONSE_WINDOW -> DISPUTED                       (respond_to_claim("DISPUTE"), before deadline)
RESPONSE_WINDOW -> DISPUTED  (derived, read-time)  (now > response_deadline, no response — silence
                                                     defaults to DISPUTED, not ACCEPTED)
DISPUTED -> EVIDENCE_FROZEN                        (freeze_evidence, permissionless)
```

`ACCEPTED` and `EVIDENCE_FROZEN` are the two Stage-2-terminal states — `file_claim` only
allows a new claim against a warranty once every prior claim on it has reached one of these
two. Matches `file_claim`/`respond_to_claim`/`_effective_claim_status` in
`contracts/clause_protocol.py` exactly.

`EvidenceRecord`: `eligibility` is decided once, at `submit_evidence` time, and never
re-evaluated (`PENDING`-shaped only in the sense that `retrieval_status` starts `""` and is
set exactly once by `freeze_evidence`, guarded by `retrieval_status != ""` as the per-record
idempotency check — there is no separate stored `"PENDING"` string literal for eligibility
itself; `ELIGIBLE`/`INELIGIBLE` is immediate and final at submission).

```
submit_evidence -> eligibility decided immediately (ELIGIBLE | INELIGIBLE), retrieval_status = ""
  ELIGIBLE   --freeze_evidence--> retrieval_status in {AVAILABLE, UNAVAILABLE, FETCH_FAILED,
                                   RENDER_FAILED, INSUFFICIENT}, frozen_at set, immutable
  INELIGIBLE --freeze_evidence--> skipped unconditionally, retrieval_status stays "", frozen_at stays 0
```

No write method exists that takes an existing `claim_id` or `evidence_id` and mutates a
record's already-committed fields outside these two documented transitions each — proven in
`tests/direct/test_stage2_freeze_and_fingerprint.py` and the schema-derived audit in
`tests/direct/test_constitution_hardening.py` (extended in the Stage 2 pass to cover
`file_claim`/`respond_to_claim`/`submit_evidence`/`freeze_evidence` against the frozen
Constitution, and by direct assertion for `EvidenceRecord` post-freeze immutability).

## Stage 3 as-implemented: adjudication transition

```
EVIDENCE_FROZEN --adjudicate_claim (permissionless, once)--> DECIDED
```

`adjudicate_claim(claim_id)` preconditions: claim `EVIDENCE_FROZEN` and no existing adjudication.
State change (all writes strictly **after** any consensus block returns): new immutable
`Adjudication`; `adjudication_id_by_claim[claim_id]`; claim `status = DECIDED`. Timestamps:
`adjudicated_at = _now()`; `challenge_window_closes_at = adjudicated_at + challenge_window_s`
(stored as data only; no challenge mechanism exists until Stage 4). Financial effect: **none** - pool,
reservation and passport are untouched (test-enforced). Failure (malformed output, provider failure,
validator disagreement/consensus failure): the transaction reverts; no `Adjudication`, the claim stays
`EVIDENCE_FROZEN` and remains adjudicable. `DECIDED` is *not* terminal (Stage 4:
`CHALLENGE_WINDOW -> FINAL -> SETTLED`); like `ACCEPTED`/`EVIDENCE_FROZEN` it does not block filing a
new claim on the same warranty (preserves Stage 2 behaviour).


---

## Stage 4 as-implemented: from DECIDED to settled

Claim states added (stored `Claim.status`; the Stage 2 `Claim` struct is unchanged): `CHALLENGED`, `CHALLENGE_RESOLVED`,
`FINAL`, `SETTLED`. (Withdrawal is tracked on `FinalDecision`, not as a claim state.)

| From | Method | Guard | To |
|---|---|---|---|
| `DECIDED` | `file_challenge` (holder/manufacturer) | window open, no prior challenge, `challenge_depth >= 1`, valid ground+citation | `CHALLENGED` |
| `CHALLENGED` (OPEN) | `resolve_challenge` (anyone) | within `filed_at + challenge_window_s` | `CHALLENGE_RESOLVED` (UPHELD / REVERSED / INVALID) or stays `CHALLENGED` (REMAND_PENDING) |
| `CHALLENGED` (REMAND_PENDING) | `execute_remand` (anyone, once) | within the same deadline | `CHALLENGE_RESOLVED` |
| `CHALLENGED` | `lapse_challenge` (anyone) | `now > filed_at + challenge_window_s` | `CHALLENGE_RESOLVED` (INVALID, original stands) |
| `ACCEPTED` | `finalize_claim` (anyone) | none (no window) | `FINAL` |
| `DECIDED` | `finalize_claim` (anyone) | no challenge AND (`now > challenge_window_closes_at` or `challenge_depth == 0`) | `FINAL` |
| `CHALLENGE_RESOLVED` | `finalize_claim` (anyone) | none | `FINAL` |
| `FINAL` | `settle_claim` (anyone) | not settled | `SETTLED` |
| `SETTLED` | `withdraw_settlement` (recorded recipient) | `claimable > 0`, not withdrawn | (unchanged; `withdrawn_at` set) |

`file_claim` now also permits a new claim on a warranty whose earlier claims are in `CHALLENGED`, `CHALLENGE_RESOLVED`,
`FINAL` or `SETTLED` (only claims still in the response/dispute phase block it).

`cancel_warranty` and `release_expired_reservation` require every claim on the warranty to be `SETTLED`;
`release_expired_reservation` additionally waits out the claim-deadline grace window.

Failed/undetermined semantic steps (`resolve_challenge`, `execute_remand`) write nothing before the consensus block
returns, so they leave the claim and challenge exactly as they were (retryable until the lapse deadline).


---

## Stage 4.5: release/cancel preconditions (final)

`release_expired_reservation(warranty)`: passport EXPIRED (past `coverage_end`) and `now > coverage_end + claim_deadline_s`, or passport CANCELLED; and every claim on the warranty `SETTLED`; reservation `ACTIVE`.
`cancel_warranty(warranty)`: passport ACTIVE (not yet expired) and every claim on the warranty `SETTLED`; afterwards no new claim can be filed (CANCELLED), so the reservation may be released.
Blocked by any claim in RESPONSE_WINDOW, ACCEPTED, DISPUTED, EVIDENCE_FROZEN, DECIDED, CHALLENGED, CHALLENGE_RESOLVED or FINAL.
