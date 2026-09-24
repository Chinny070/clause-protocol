# CLAUSE - Stage 4.5 Contract Freeze Pass

Scope: three narrow hardening items + ABI inventory. No frontend, no new challenge rounds, no new evidence architecture, no new settlement model, no StudioNet deployment, no wallet/key.

## 1. Remedy-table completeness (payable deadlocks eliminated)

**Problem.** Stage 4 failed closed at `finalize_claim` when a payable outcome had no matching remedy row. A frozen constitution cannot be amended, so an issued warranty could
be stuck forever.

**Invariant (precise).** A remedy table is *complete* for a constitution with covered clauses `C` iff:
1. an outcome-level row `(ACCEPTED_NO_CONTEST, "")` exists (a manufacturer may ACCEPT any claim, so this outcome is always reachable); and
2. `(COVERED, "")` exists, **or** `(COVERED, c)` exists for **every** `c` in `C`.

Why this is sufficient: the payable final states are (a) ACCEPTED_NO_CONTEST; (b) COVERED, whose established clauses are a non-empty subset of the claim's targeted clauses, which are a
subset of `C` (enforced by `file_claim` and by the Stage 3/4 model-output checkers, including every REVERSED and REMAND correction); (c) INSUFFICIENT_EVIDENCE / EVIDENCE_UNAVAILABLE
under a frozen `RULE_FOR_HOLDER` policy, which price the claim's targeted clauses (again a non-empty subset of `C`). `_select_remedy` resolves each clause by its specific row, else the
outcome-level `COVERED` row, so condition 2 guarantees every subset resolves. Rows for non-payable outcomes (NOT_COVERED, INVALID_CLAIM, BLOCK / RULE_FOR_MANUFACTURER gaps) are never
required because they pay zero by rule. Amount validity (`<= frozen max`) is guaranteed arithmetically by `_remedy_amount`, so no per-warranty check is needed at freeze time.

**Enforcement.** `_check_remedy_completeness` runs inside `create_constitution` after the structural table validation, i.e. before the constitution exists and therefore before any Warranty
Passport can bind to it. Error: `remedy_table incomplete: ...`. No post-freeze mutation mechanism was added. `_select_remedy`'s Stage 4 fail-closed raise is retained as defence in depth
but is now unreachable for issued warranties.

**Tests** (`test_stage45_freeze.py`): exhaustive over all 32 subsets of {C-001, C-002, C-003, (COVERED,""), (ACCEPTED,"")} rows against an independent oracle (accepted iff complete; every
accepted table resolves all 7 non-empty clause subsets x {COVERED, RULE_FOR_HOLDER insufficient, RULE_FOR_HOLDER unavailable} + ACCEPTED, within the max); a rejected constitution is not stored
and cannot be issued against; end-to-end for three table shapes (outcome-level only / per-clause only / mixed) every clause subset x {covered, insufficient, unavailable, accepted} finalizes and settles
without failing closed; REVERSED and REMAND-corrected outcomes resolve to rows. The Stage 4 test that provoked the deadlock now asserts creation is refused. A mutation check (completeness call
removed) makes the exhaustive test fail.

## 2. Grace-window reservation invariant (retained, formalized)

`release_expired_reservation` and `cancel_warranty` never release capacity while a valid claim can still be filed or any claim on the warranty is economically unresolved:
- every claim on the warranty must be `SETTLED` (stored status) - covers RESPONSE_WINDOW, ACCEPTED, DISPUTED, EVIDENCE_FROZEN, DECIDED, CHALLENGED, CHALLENGE_RESOLVED and FINAL-unsettled;
- an EXPIRED warranty additionally requires `now > coverage_end + claim_deadline_s` (the exact instant `file_claim` stops accepting claims, `<=`, so the two boundaries coincide);
- a CANCELLED warranty cannot receive new claims, so it needs only the first condition; `cancel_warranty` itself requires no unsettled claim.
Documented in `ECONOMIC_INVARIANTS.md`, `STATE_MACHINES.md`, `DATA_MODEL.md`. Tests: coverage running / grace open / exact boundary (blocked) / +1s (allowed); a claim can still be filed at the exact
boundary while release is blocked and is rejected one second later; every unsettled claim state blocks release even 40 days after grace (7 parametrized states); FINAL-unsettled payable keeps its
capacity and still pays in full; SETTLED allows release of the remainder without touching claimable; two claims with one unresolved blocks; `cancel_warranty` blocked in 4 states, allowed once settled.
Mutation check (grace condition removed) fails the boundary test.

## 3. Audit of the `corrections` challenge representation (Stage 0 `corrected_field/corrected_value` -> `corrections`)

Result: **PASSES; retained; deviation formally documented.**
- *Bounded*: at most 5 keys (the semantic fields), every value is a list of ids that must be members of small frozen sets (targeted clauses, exclusions, shown evidence, max 10) with duplicates rejected, or a 3/2-value enum;
  reasoning <= 1000, remand issue <= 500. 500-element and 1000-element lists are rejected.
- *Exact-key validated*: the model object must have exactly `decision, corrections, remand_issue, reasoning`; `corrections` keys must be within the ground's allow-list
  (WRONG_CLAUSE -> covered_clause_ids; EXCLUSION_MISAPPLIED -> exclusion_clause_ids; PRODUCT_MATCH_ERROR -> product_match; IGNORED_EVIDENCE -> the five semantic fields).
- *Canonical*: accepted corrections are re-emitted from the merged, normalized (sorted) result, so order/format differences vanish (tested: unsorted leader vs sorted validator agree; a genuinely different set disagrees).
- *Cannot change out-of-set fields, payout/remedy, constitution, evidence*: 25 forbidden keys (outcome, remedy_*, payout, recipient, constitution_id, warranty_version_match, coverage_window, source_authority,
  evidence_ids_considered, decision_path, rationale, superseded, timestamps, remedy_table, evidence/url(s), settled_amount, claimable, "", padded keys) are rejected for two grounds; every non-allowed semantic field is rejected
  per ground. The corrected `Adjudication` copies constitution, version, window and considered evidence from the original; `outcome`/`source_authority` are re-derived by plain code; the adjudication record carries no economics; remedy
  still comes only from the frozen table (a reasoning string demanding a payout changes nothing). Relying on evidence the original never considered is rejected.
- *Validator-compatible*: equivalence key = `decision` + normalized `corrections`; prose excluded; validators re-check the leader's value.
- *Deterministic derivation*: same corrections on two independent claims give identical corrected findings/outcome/path; duplicate JSON keys collapse to one value before validation.
- *Coherence*: covered+product FAIL, covered+INSUFFICIENT, SUFFICIENT+no evidence, UNAVAILABLE, unshown/duplicate/bool/string evidence ids, exclusion-as-covered are all rejected.
Deviation (retained): one `corrections` object replaces the single-field `corrected_field/corrected_value`, because IGNORED_EVIDENCE legitimately needs several coherent field changes; the added expressiveness is bounded by the per-ground allow-list
and the same Stage 3 checker.

## 4. Contract / ABI freeze

`docs/FRONTEND_CONTRACT_INTERFACE.md` created: encoding conventions, caller roles, lifecycle, exact timing rules, protocol-finality checklist, value flow, enumerations, limits, read models, error messages, and a **generated** ABI inventory
(40 public methods: 18 view + 22 write, 1 payable) produced by `scripts/gen_frontend_interface.py` from the contract AST. `test_stage45_interface_sync.py` fails if the contract ABI and the document diverge.

## 5. Results
`pytest tests/direct`: 626 passed (510 prior + 116 new). lint, validate (40 methods: 18 view + 22 write), schema, typecheck (0 errors, 0 warnings) all clean. Real glsim deterministic tests re-run (settlement, adjudication, lifecycle, undetermined-xfail as before) after adding the completeness row to their fixtures.

## Remaining V1 limitations
Overlapping-claim payouts are first-settled-first-served; the 10-evidence cap is first-come; a manufacturer may cancel a warranty unilaterally while no claim is unsettled (voiding future coverage) - a product-policy decision left for a later version;
an unresolvable challenge waits one extra window before lapsing; IGNORED_EVIDENCE can alter several fields; `source_authority = FAIL` is unreachable.

## Remaining StudioNet gates
Genuine `web.render`; disagreement/undetermined rollback; real protocol timestamps; real payable behaviour without the shim; real-model adjudication; real-model injection resistance; real-model challenge review/remand;
withdrawal transfer only after finalization and real balance movement.

The CLAUSE contract interface is frozen for Stage 5.
No production frontend was implemented.
No StudioNet deployment was performed and no user wallet/private key was used.
