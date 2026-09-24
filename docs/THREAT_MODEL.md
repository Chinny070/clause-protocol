# CLAUSE — Threat Model (Stage 0)

Organized by the build brief's required categories, each with the concrete CLAUSE mechanism that
addresses it (cross-referenced, not restated in full — see the linked doc for mechanism detail).

## Unauthorized mutation / authorization

- Every write method's caller is checked against the specific role it requires (`manufacturer` of the
  relevant Program/Pool, `holder` of the relevant Passport, or explicitly permissionless where stated in
  `STATE_MACHINES.md`, e.g. `freeze_evidence`/`adjudicate`/`settle_claim`/`release_expired_reservation`
  are deliberately permissionless so no single party can stall a claim by inaction).
- Permissionless methods are permissionless only over already-frozen, already-validated state — they
  never let a random caller inject new facts, only advance a lifecycle that frozen rules already govern.

## Post-registration rewrite

- Covered structurally by Constitution immutability (`WARRANTY_CONSTITUTION.md`) and the Passport's
  frozen fingerprint/version copy (`ARCHITECTURE.md`, Anti-rewrite section). Stage 1 test: attempt to
  mutate any Constitution field after `is_frozen == True`, on every field, expect revert.

## Forged holder/product association

- `WarrantyPassport.holder` is set once at `issue_warranty` from the manufacturer's own call (the
  manufacturer designates the holder address at issuance — this is a manufacturer-trust boundary,
  documented as such: CLAUSE cannot cryptographically prove a real-world purchase happened, only that
  the manufacturer attested to it on-chain). `product_commitment` (hash of serial+salt) prevents a third
  party from later claiming knowledge of the serial number alone as proof of association — filing a
  claim requires the actual salt, held only by the real holder.

## Out-of-window / duplicate claims

- `file_claim`'s deadline check (`STATE_MACHINES.md`) rejects late claims. Duplicate claims against the
  same warranty are allowed to exist as separate `Claim` records (a holder may have multiple genuine
  incidents) but each is independently reservation-locked and independently adjudicated — there is no
  path where two Claims double-spend the same GEN, since `pending_locks` accounting
  (`ECONOMIC_INVARIANTS.md`) tracks locks per-Claim against the shared Reservation, and `file_claim`'s
  precondition (`pending_locks + amount <= reserved_liability`) prevents over-locking beyond what a
  single warranty's Reservation actually backs.

## Duplicate settlement / withdrawal

- One-shot `settled_at`/`withdrawn_at` guards, set before value moves (`ECONOMIC_INVARIANTS.md`).

## Evidence after freeze

- `EvidenceRecord` fields become immutable once `frozen_at != 0`; any write path touching a frozen
  record's `extracted_facts`/`fingerprint`/`retrieval_status` must revert. Stage 1 test: attempt to
  re-submit/re-freeze an already-frozen `evidence_id`, expect revert.

## Source-policy bypass

- Step 1 of `EVIDENCE_ARCHITECTURE.md` (deterministic eligibility check against the frozen
  `source_eligibility_policy`) runs before any network call. Redirect/domain tricks: the eligibility
  check must validate against the URL's actual host as parsed, not a string-contains match — Stage 1
  must specify exact-host or explicit-pattern matching (never substring matching, which a hostile domain
  like `notmanufacturer.com/manufacturer.com` could defeat), and must not follow redirects to a
  different host without re-checking eligibility against the redirect target (`gl.nondet.web.get`'s
  redirect-following behavior must be confirmed at Stage 2 — if it follows redirects transparently,
  CLAUSE must independently validate the final resolved host, not trust that the submitted URL's host
  is where the content actually came from).

## Prompt injection

- Fetched web content is data, never instructions (`EVIDENCE_ARCHITECTURE.md`). Two independent layers:
  (1) source eligibility filters *which* domains can even be fetched, reducing the attack surface to
  sources the manufacturer's own frozen policy already trusts; (2) extraction prompts are structured to
  ask only for specific bounded fields (never "follow any instructions in this content"), and the
  fail-closed shape validator (`ADJUDICATION_SCHEMA.md`) rejects any output that doesn't match the exact
  expected schema, which defeats injected content trying to steer the *adjudication* outcome (as opposed
  to merely the extraction) — an injected "this claim is APPROVED" string inside a fetched page cannot
  set `Adjudication.outcome` because `outcome` is computed by a separate structural-consistency check in
  plain Python, not copied verbatim from any LLM claim about the outcome. Test matrix explicitly requires
  a prompt-injection fixture (`TEST_MATRIX.md`).

## Oversized / unavailable / volatile evidence

- Bounded extraction (Step 3, `EVIDENCE_ARCHITECTURE.md`) discards raw bodies after extracting a small
  fixed field set — oversized responses cannot inflate on-chain storage. Volatility is handled by
  comparing extracted stable facts, never raw pages (Equivalence Principle guidance,
  `NETWORK_AND_SDK_VERIFICATION.md`). Unavailable evidence routes to the Constitution's frozen
  `unavailable_evidence_behavior`, never a crash.

## Malformed model output / hallucinated IDs

- `_validate_adjudication_shape` (`ADJUDICATION_SCHEMA.md`) hard-errors on any enum outside its literal
  set and any clause/evidence ID not present in frozen state for this claim — never silently drops or
  substitutes a default.

## Manufacturer pool drain

- `issue_warranty`'s pre-check against `available_balance` (`ECONOMIC_INVARIANTS.md`) prevents
  over-issuance beyond backed capacity. `withdraw_pool`'s `available_balance`-only check prevents
  draining reserved/pending funds. Neither check can be bypassed by call ordering within a single
  transaction, since `available_balance` is always recomputed live, never cached.

## Late / unauthorized / replayed challenges

- Deadline check on `file_challenge` against `challenge_window` (`APPEALS_AND_FINALITY.md`); caller
  restricted to a party of the specific Claim; a second `file_challenge` against a Claim that already
  has a Challenge record (open or resolved) reverts (V1's one-challenge-total rule).

## Premature settlement

- `settle_claim` requires `Claim.status == FINAL`, which itself requires GenLayer protocol Finality of
  the deciding transaction, not merely Accepted (`APPEALS_AND_FINALITY.md`,
  `NETWORK_AND_SDK_VERIFICATION.md`).

## Timestamp provenance confusion

- The nine-fact time taxonomy (`ARCHITECTURE.md`) is enforced by type: claimant-asserted dates
  (`failure_asserted_at`) are never used as the authoritative input to a deadline check — deadlines
  anchor to on-chain timestamps (`coverage_end`, `registered_at`, `response_deadline`, etc.), and any
  UI display of a claimant- or source-asserted date is visually distinguished from an on-chain timestamp
  (`FRONTEND_INFORMATION_ARCHITECTURE.md`).

## State mutation after failed/undetermined consensus

- A `gl.vm.run_nondet_unsafe` block whose consensus cannot be reached causes the whole transaction to
  revert (confirmed GenVM behavior, `NETWORK_AND_SDK_VERIFICATION.md`) — Claim state remains at its
  pre-call status (e.g. still `EVIDENCE_FROZEN` after a failed `adjudicate`), retryable by anyone, no
  partial-write corruption possible since GenVM transactions are atomic.

## Workspace-specific residual risks carried forward, not yet re-verified for CLAUSE

- **Inbound payable value surviving a reverted call** — independently observed live on StudioNet for a
  sibling project (Protocol Court's `FILING_BOND_MISMATCH` incident: a reverted payable call did not
  return the attached GEN). CLAUSE's `fund_pool`/`file_claim`(if ever made payable in a later stage)
  must be designed with unconditional-credit-first, validate-after ordering, or with the strongest
  possible pre-validation *before* the payable call, and this must be **live-tested on Studionet before
  any real deployment**, not assumed safe from Stage 1 code review alone.
- **`strict_eq` over live, non-content-addressed web pages** has historically produced ~1-in-5
  `Undetermined` consensus outcomes in this workspace (Treasury Trial finding). CLAUSE avoids `strict_eq`
  on raw pages entirely (`EVIDENCE_ARCHITECTURE.md` uses `run_nondet_unsafe` with extracted-fact
  comparison throughout) specifically to avoid inheriting this failure mode, but the *rate* of
  Undetermined outcomes for CLAUSE's own extraction/adjudication comparators is unverified until live
  Stage 2/3 testing.
- **`Response.status_code` vs `.status`** — a confirmed API-attribute drift since this workspace's
  earlier verifications (`NETWORK_AND_SDK_VERIFICATION.md`). Using the wrong attribute name would fail
  loudly (AttributeError) rather than silently misbehave, so this is a build-breaking risk, not a
  security risk, but is listed here because it was discovered during this Stage 0 threat-modeling pass.

## Stage 3 additions (adjudication)

- **Model-output attacks** (prompt-injected result, extra `outcome`/`payout` keys, hallucinated
  clause/evidence ids, contradictory findings, oversized or mistyped fields): fail closed via
  `_check_model_result`; nothing is repaired; re-applied by every validator to the leader's value.
- **Injection via evidence**: confined to a JSON-string data slot (cannot forge section headers or break
  out of the array); instructions precede it and forbid obeying/browsing; adjudication makes **no** web
  call; deterministic facts (window, version, eligibility, availability) are computed outside the model
  and cannot be promoted by evidence text. *Residual, unprovable locally:* a real model might still be
  swayed within its allowed output space; the defenses are independent validators + coherence rules +
  deterministic derivation, and a real-model injection test is a StudioNet gate.
- **Counterfactual leakage**: money, addresses, commitments, fingerprints and policy-consequence fields
  are excluded from the prompt (test-enforced).
- **Closure/replay bugs**: the leader/validator pair lives in one module-level function; replay tests
  plus a mutation check.
- **Provider failure masquerading as success**: glsim returns provider errors as a *string*; the
  non-dict rejection handles it (observed on the real simulator).
- **Evidence cap** (Stage 3.5): `submit_evidence` rejects an eligible record once the claim already has 10, counted over all prior submissions/parties/transactions before freeze; adjudication shows every adjudicable record and asserts the cap as an invariant. No silent truncation.
- **Residual gaps** (unchanged protocol gates): undetermined-consensus rollback, real render, real model
  behaviour.


---

## Stage 4 additions (challenge, finality, settlement)

- **Unauthorized / duplicate / late challenge**: holder-or-manufacturer only; one per claim; protocol-timestamp window
  with exact-boundary tests; reverts consume nothing.
- **Challenge as a re-litigation vehicle**: ground+citation must match, citations must be frozen evidence/clauses of THIS
  claim; four grounds are fully deterministic or deterministically gated; semantic review may only correct fields the
  ground allows, must concern the cited item, and only a *material* change reverses.
- **New-evidence injection**: no URL fields, no submission after freeze, resolution never browses (test-enforced).
- **Hostile challenge explanation / evidence**: JSON data slot, no section forgery, injected `outcome`/payout corrections
  rejected; the model never emits a result, an outcome, an amount, or a recipient.
- **Malformed / disagreeing semantic output**: strict checker, re-applied by every validator; no partial writes.
  *Residual, unprovable locally:* real-model behaviour and real disagreement rollback (StudioNet gates).
- **Challenge stalling**: `lapse_challenge` after one further frozen window; original stands.
- **Payout tampering**: remedy comes only from the frozen table via `_select_remedy`; capped by the warranty's frozen max
  and remaining reservation; missing row fails closed.
- **Double finalize / settle / withdraw / release / challenge**: one-shot guards, tested, including a seeded randomized
  adversarial driver reconciled against an independent ledger.
- **Reservation starvation**: release blocked while any claim is unsettled and until the claim-deadline grace has passed
  (a manufacturer can no longer release a warranty's capacity at `coverage_end` to defeat a grace-window claim).
- **Wrong recipient / premature withdrawal**: recorded recipient only; requires `SETTLED`; state written before transfer.
- **Protocol vs application finality confusion**: separate transactions, documented operator verification list, transfer
  emission timing carried as a StudioNet gate.
