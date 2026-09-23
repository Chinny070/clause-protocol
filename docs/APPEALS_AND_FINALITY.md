# CLAUSE — Application Appeal vs Protocol Finality (Stage 0)

Two entirely separate mechanisms, never conflated:

1. **Application-level Challenge** — a CLAUSE contract method, reviewing a specific alleged defect in a
   specific `Adjudication`, over the same frozen evidence, bounded to V1's one challenge round.
2. **GenLayer protocol appeal/finality** — the chain-level Optimistic Democracy mechanism
   (`client.appealTransaction`/`appeal_transaction` on the `adjudicate` transaction itself), external to
   CLAUSE's own code, wallet-driven, and governed entirely by GenLayer's consensus rules
   (`NETWORK_AND_SDK_VERIFICATION.md`).

Money stays protected (no `settle_claim`) until **both** requirements are satisfied: the application
Challenge window has closed with no open Challenge (or the last Challenge resolved UPHELD/INVALID/a
settled REVERSED correction), **and** the underlying GenLayer transaction for the deciding Adjudication
has itself reached protocol Finality, not merely Accepted (`STATE_MACHINES.md`, `finalize_claim`).

## Application-level Challenge

Allowed V1 grounds, each requiring a specific citation (an `evidence_id` or `clause_id`, never a bare
argument):

- `IGNORED_EVIDENCE` — cites a frozen `evidence_id` not present in the Adjudication's
  `evidence_ids_relied_on`.
- `WRONG_WARRANTY_VERSION` — cites the `constitution_id` the challenger believes should have governed.
- `WRONG_CLAUSE` — cites the specific `clause_id` misapplied.
- `EXCLUSION_MISAPPLIED` — cites the specific `X-*` clause id.
- `TEMPORAL_ERROR` — cites which timestamp field (`STATE_MACHINES.md`/`DATA_MODEL.md`'s nine-timestamp
  taxonomy) was misread.
- `SOURCE_AUTHORITY_ERROR` — cites the `evidence_id` whose eligibility/authority is disputed.
- `PRODUCT_MATCH_ERROR` — disputes `product_match`, citing the relevant `evidence_id`.

Appellate question:

> Does the identified challenge establish a material error in the original adjudication under the frozen
> Warranty Constitution and frozen evidence record?

Results: `UPHELD` (defect not confirmed, original Adjudication stands untouched — no new Adjudication
record created at all), `REVERSED` (defect confirmed, a new Adjudication is created correcting only the
named dimension, every other field carried forward unchanged, original marked `superseded = True`),
`REMAND` (narrow — re-triggers one bounded corrective adjudication step scoped to the named defect only,
never a full re-litigation, and never exceeding `challenge_depth`), `INVALID_CHALLENGE` (malformed
ground/citation, e.g. citing an `evidence_id` that does not exist or was never frozen for this claim, or
a `REMAND` attempt that would exceed `challenge_depth`).

## Resolution mechanics (targeted appellate review, not full re-adjudication)

Following the pattern this workspace already proved out on Protocol Court (a deliberate refinement over
an earlier, more expensive "full re-adjudication" design): `resolve_challenge` builds a targeted review
prompt from the original Adjudication (including its `rationale`) plus the same frozen evidence/
Constitution/claim plus the Challenge's own `ground`/`citation`/`argument`, asking only whether *that
specific* alleged defect is real — never asking the model to re-decide the whole claim from scratch.
Judgment schema (internal, not the public Adjudication schema): `{decision: DEFECT_CONFIRMED |
DEFECT_NOT_CONFIRMED, corrected_field: <one of the frozen schema's field names> | "NONE", corrected_value:
<matching type> | "UNCHANGED", reasoning}`, with the same `gl.vm.run_nondet_unsafe` two-tier structure
and structural-field-only comparison as the primary Adjudication (`ADJUDICATION_SCHEMA.md`). Fail-closed
against two incoherent shapes: `DEFECT_NOT_CONFIRMED` with a non-`"NONE"` `corrected_field` (smuggled
correction), and `DEFECT_CONFIRMED` with `corrected_field == "NONE"` (confirmed but nothing actually
changed) — both are hard errors, not silently accepted.

## Ordering and abuse resistance

Only one open Challenge per Claim at a time in V1 (`challenge_depth = 1` means at most one Challenge
total per Claim, not one-at-a-time-forever) — this removes the "resolve oldest-first" complexity needed
in multi-challenge designs, at the cost of being stricter than Protocol Court's V1. A rejected or
resolved Challenge does not reopen the window; late, unauthorized (non-party — V1: holder or
manufacturer of the specific Claim only, permissionless-view but permissioned-file), or replayed
Challenge attempts (a second `file_challenge` once one already exists for the Claim) revert.

## GenLayer protocol finality (separate, external)

`finalize_claim` never itself calls `appealTransaction`/`appeal_transaction` — that is a wallet action a
party takes directly against the GenLayer chain if they want to contest consensus itself (a completely
different failure mode than an application Challenge: "the committee got the facts/rules wrong" vs "the
committee's own consensus process should be redone"). CLAUSE's `finalize_claim` only *reads* whether the
relevant transaction has reached Finalized status via `gen_getTransactionStatus`/
`gen_getTransactionLifecycle` (`NETWORK_AND_SDK_VERIFICATION.md`) and gates on that read — it never
assumes Accepted is sufficient, and it never builds its own competing "application-level protocol
appeal," which the design spec and this workspace's prior AgentCourt build both explicitly warn against
inventing.
