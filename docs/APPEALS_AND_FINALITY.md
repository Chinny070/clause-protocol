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


---

## Stage 4 as-implemented (2026-09-24): Application Challenge, application finality, protocol-finality boundary

### Terminology (used consistently in code, docs, and the Stage 5 frontend)

- **Application Challenge** - a CLAUSE contract mechanism (`file_challenge`, `resolve_challenge`, `execute_remand`,
  `lapse_challenge`). It challenges a stored CLAUSE `Adjudication` under narrow grounds. State names: `CHALLENGED`,
  `CHALLENGE_RESOLVED`; challenge statuses `OPEN`, `REMAND_PENDING`, `RESOLVED`.
- **Application finality** - CLAUSE's own `FINAL` state, reached by `finalize_claim`.
- **GenLayer Protocol Appeal / Finality** - the underlying network's Optimistic Democracy mechanism for a
  *transaction* (Accepted -> appeal window -> Finalized). CLAUSE never calls it, never simulates it, and never
  uses the word "appeal" for its own challenge.

### Lifecycle

```
ACCEPTED (manufacturer ACCEPT) ------------------------------------------------\
DECIDED --(no challenge, window closed | challenge_depth == 0)-----------------> FINAL -> SETTLED -> (withdrawn)
DECIDED -> CHALLENGED -> CHALLENGE_RESOLVED ---------------------------------/
              \-(REMAND)-> CHALLENGED [REMAND_PENDING] -> execute_remand -> CHALLENGE_RESOLVED
              \-(unresolved for one frozen window)-> lapse_challenge -> CHALLENGE_RESOLVED (original stands)
```

### One challenge, bounded

At most **one** challenge per claim, ever (`challenge_id_by_claim`); a challenge of a challenge does not exist; the
corrected adjudication a challenge produces carries `challenge_window_closes_at = 0` and can never be challenged.
A constitution with frozen `challenge_depth == 0` disables challenges entirely (and removes the window wait).

Who: the claim's holder or manufacturer (checked against the claim). Unrelated accounts revert.

Window (protocol timestamps only): opens when the adjudication is recorded (`adjudicated_at`), closes at
`challenge_window_closes_at = adjudicated_at + constitution.challenge_window_s` (frozen at adjudication time).
`opens <= now <= closes` is allowed; `now > closes` reverts; a claim with no adjudication yet reverts.

### Grounds and citations (exact frozen names)

Filing takes `(claim_id, ground, explanation, citation)`. `citation` must have EXACTLY the keys
`evidence_ids, clause_ids, constitution_id, timestamp_field`, and each ground admits only its own citation kind:

| Ground | Required citation | Everything else |
|---|---|---|
| `IGNORED_EVIDENCE` | >=1 evidence id | empty |
| `WRONG_WARRANTY_VERSION` | `constitution_id` > 0 | empty |
| `WRONG_CLAUSE` | >=1 clause id | empty |
| `EXCLUSION_MISAPPLIED` | >=1 clause id | empty |
| `TEMPORAL_ERROR` | `timestamp_field` in {failure_asserted_at, coverage_start, coverage_end, filed_at, adjudicated_at, evidence_frozen_at} | empty |
| `SOURCE_AUTHORITY_ERROR` | >=1 evidence id | empty |
| `PRODUCT_MATCH_ERROR` | >=1 evidence id | empty |

Cited evidence must already belong to THIS claim and be frozen (or be an ineligible record recorded before freeze, so
a challenger may dispute its ineligibility). Nothing new can be introduced: evidence submission is closed after freeze,
a citation carries no URLs, and the explanation (<=1000 chars) is inert data - resolution never browses. Structural
errors (unknown ground, malformed/foreign/nonexistent citation) **revert at filing and consume nothing**; only a
well-formed challenge consumes the one round.

### Deterministic vs semantic resolution

| Ground | Resolution | Detail |
|---|---|---|
| `WRONG_WARRANTY_VERSION` | deterministic | cited id != governing constitution -> `INVALID_CHALLENGE` (the constitution is frozen at issuance); else recompute the version predicate: differs from stored -> `REVERSED`, same -> `UPHELD` |
| `TEMPORAL_ERROR` | deterministic | recompute the coverage window from frozen timestamps: differs -> `REVERSED`, same -> `UPHELD` |
| `SOURCE_AUTHORITY_ERROR` | deterministic | any cited record ineligible under the frozen source policy -> `INVALID_CHALLENGE` (eligibility can never be overridden); all eligible -> `UPHELD` |
| `IGNORED_EVIDENCE` | gated, then semantic | cited evidence must be in the original `evidence_ids_considered`, usable, and NOT already relied on, else `INVALID_CHALLENGE` |
| `WRONG_CLAUSE` | gated, then semantic | cited clause must be a COVERED clause the claim targeted, else `INVALID_CHALLENGE` |
| `EXCLUSION_MISAPPLIED` | gated, then semantic | cited clause must be an exclusion, else `INVALID_CHALLENGE` |
| `PRODUCT_MATCH_ERROR` | gated, then semantic | cited evidence must be considered and usable, else `INVALID_CHALLENGE` |

If the original decision was itself deterministic (`decision_path != SEMANTIC`) a semantic ground never reaches the
model: `UPHELD` (deterministic decision cannot be altered by a semantic ground) or `INVALID_CHALLENGE` (nothing
adjudicable to review). Only the four gated grounds can call the model.

### Result semantics (the model never emits a result)

- `UPHELD` - a well-formed challenge was evaluated; no *material* error found. Original adjudication stands, untouched.
- `REVERSED` - a material error was confirmed. A NEW `Adjudication` (path `CHALLENGE_CORRECTION`) is stored with the
  corrected finding(s), outcome re-derived deterministically; the original is marked `superseded = True` (never edited
  or deleted).
- `REMAND` - the reviewer found the issue cannot be resolved by a bounded correction and names exactly what needs
  reconsideration (<=500 chars). One bounded corrective step, `execute_remand`, re-runs the Stage 3 adjudicator
  (same fail-closed checker, same frozen evidence) once, with that issue passed as untrusted data. The result is final.
- `INVALID_CHALLENGE` - the challenge's premise is impossible under frozen rules (wrong clause kind, un-targeted
  clause, ineligible source, cited constitution != governing, evidence not adjudicable / already relied on), OR it
  lapsed unresolved. The original stands.

**Materiality** (deterministic, contract-side): a confirmed correction is `REVERSED` only if it changes the outcome, or
(for an outcome of `COVERED`) changes which covered clauses were established, since that selects the remedy row. A
confirmed but immaterial correction resolves `UPHELD`.

### Semantic challenge review

Input (`_build_challenge_prompt`): governing rules (constitution version/scope/calc, targeted covered clauses,
exclusion clauses), the ORIGINAL structured adjudication + its bounded rationale + protocol-determined version/window,
`ALLOWED_CORRECTION_FIELDS`, the challenge (ground, explanation - untrusted, citation), and the original's considered
evidence. Never: pool balances, capacity, remedy table/values, reservation data, addresses, commitments, fingerprints,
the manufacturer response, or policy-behavior fields (test-enforced).

Output (strict; exactly 4 keys): `decision` (`DEFECT_CONFIRMED | DEFECT_NOT_CONFIRMED | NEEDS_RECONSIDERATION`),
`corrections` (object), `remand_issue` (string), `reasoning` (<=1000). Fail-closed coherence: NOT_CONFIRMED carries no
correction/remand issue; NEEDS_RECONSIDERATION carries no correction and a non-empty bounded remand issue;
CONFIRMED carries >=1 correction whose keys are within the ground's allowed fields
(`WRONG_CLAUSE -> covered_clause_ids`, `EXCLUSION_MISAPPLIED -> exclusion_clause_ids`,
`PRODUCT_MATCH_ERROR -> product_match`, `IGNORED_EVIDENCE -> any of the five semantic fields`), each different from the
original, the merged result must pass the SAME Stage 3 checker (ids known, coherence), an `IGNORED_EVIDENCE`
correction must rely on the cited evidence, and a clause correction must concern the cited clause. Validator
equivalence = `decision` + normalized `corrections`; `reasoning`/`remand_issue` prose is never compared. Every validator
re-checks the leader's returned value. Nothing is written before the consensus block returns.

### Liveness: `lapse_challenge`

A challenge that cannot be resolved (persistently malformed model output, undetermined consensus) would otherwise
freeze the claim forever. After one further frozen challenge window (`filed_at + challenge_window_s`, exclusive)
anyone may call `lapse_challenge`: result `INVALID_CHALLENGE`, path `LAPSED`, original stands (the challenger bears
the burden). After that deadline `resolve_challenge`/`execute_remand` revert.

### Application finality (`finalize_claim`, permissionless)

`FINAL` is reached by exactly one of: `ACCEPTED` claim (no adjudication, no challenge, no window); `DECIDED` claim with no
challenge whose window has closed (or `challenge_depth == 0`); `CHALLENGE_RESOLVED` claim (authoritative adjudication =
the correction if one exists, else the original). An unresolved challenge, or a claim whose window merely expired while
challenged, cannot finalize. `finalize_claim` writes one immutable `FinalDecision` (source, authoritative adjudication
id, challenge id, final outcome, established clause ids, deterministic remedy), is one-shot, and moves NO money. History is
preserved: original adjudication, challenge, correction and final decision are all retained and exposed by
`get_resolution_receipt`.

### GenLayer protocol-finality boundary (what the contract can and cannot do)

A Python contract cannot introspect whether a given transaction is `Finalized`. Therefore:

1. Application finality (`finalize_claim`) is **not** protocol finality and never claims to be. Challenge-window expiry
   alone does not equal protocol finality.
2. Each irreversible step is its **own transaction**: `finalize_claim`, `settle_claim`, `withdraw_settlement`. Money moves
   only in the last one, and only as an emitted transfer.
3. **Operators / the Stage 5 frontend MUST verify, before submitting each of these transactions, that the transaction(s)
   that produced the state they depend on are `Finalized` with a successful execution result** (via
   `gen_getTransactionStatus` / `gen_getTransactionLifecycle`), never merely `Accepted`: the adjudication (or
   `resolve_challenge` / `execute_remand` / `lapse_challenge`, or `respond_to_claim` for no-contest) before
   `finalize_claim`; `finalize_claim` before `settle_claim`; `settle_claim` before `withdraw_settlement`.
4. The SDK documents value transfers as emitted `on='finalized'` by default; the pinned runtime's EVM-interface
   `emit_transfer` path passes no `on` argument, and this could not be verified locally (glsim does not track balances).
   **StudioNet gate:** confirm the withdrawal transfer is only executed after the withdrawal transaction is Finalized.
5. A protocol appeal that overturns the deciding transaction is outside CLAUSE's control; CLAUSE's contract state follows
   whatever the network finalizes.
