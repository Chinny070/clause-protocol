# CLAUSE - Stage 4 Verification (Application Challenge + Finality + Deterministic GEN Settlement)

## 1. Verdict: PASS WITH BLOCKERS
Contract lifecycle DECIDED -> challenge -> final -> settled -> withdrawn is implemented and verified in direct mode
(model MOCKED) plus deterministic paths on the real simulator. Blockers = StudioNet gates (section 22): no real model,
so semantic challenge review / remand / injection resistance are unproven live.

## 2. Files
Modified: `contracts/clause_protocol.py`, docs (`APPEALS_AND_FINALITY`, `ECONOMIC_INVARIANTS`, `STATE_MACHINES`,
`DATA_MODEL`, `TEST_MATRIX`, `THREAT_MODEL`), `tests/direct/{test_pool_accounting,test_timestamp_trust_boundary,test_constitution_hardening}.py`.
New: `tests/direct/{helpers4,test_stage4_challenge,test_stage4_pure_logic,test_stage4_lifecycle,test_stage4_economics}.py`,
`tests/integration/test_real_settlement.py`, `docs/STAGE_4_RUN_LOG.json` (generated), this file.

## 3-6. Challenge lifecycle, grounds, resolution, result semantics
See `docs/APPEALS_AND_FINALITY.md` (Stage 4 section). Summary: one challenge per claim (holder or manufacturer), protocol-timestamp
window, 7 frozen grounds with strict per-ground citations; WRONG_WARRANTY_VERSION / TEMPORAL_ERROR / SOURCE_AUTHORITY_ERROR fully
deterministic; IGNORED_EVIDENCE / WRONG_CLAUSE / EXCLUSION_MISAPPLIED / PRODUCT_MATCH_ERROR deterministically gated then semantic.
Model emits 4 keys only; UPHELD/REVERSED/REMAND/INVALID_CHALLENGE are derived by the contract (REVERSED only if material).
REMAND = one bounded `execute_remand` re-adjudication, final. `lapse_challenge` guarantees liveness.

## 7-8. Finality model and protocol boundary
Application `FINAL` via `finalize_claim`; separate transactions for finalize/settle/withdraw. The contract cannot introspect protocol
finality: operators/frontend must verify Finalized status before each step (checklist in APPEALS_AND_FINALITY.md).

## 9-13. Remedy, no-contest, accounting, withdrawal, double-spend
Remedy from the frozen table only (`_select_remedy`); payable only for ACCEPTED_NO_CONTEST, COVERED, or RULE_FOR_HOLDER gaps; missing row fails
closed; amount <= frozen max; warranty max is a lifetime cap enforced at settlement. Pull payment; state written before transfer; one-shot guards.
Details in `docs/ECONOMIC_INVARIANTS.md`.

## 14. Receipt
`get_resolution_receipt` (+ `get_challenge*`, `get_final_decision`): original -> challenge -> correction -> final -> settlement -> withdrawal.

## 15-17. Results
Lifecycles A-G pass (22). Economic invariants with an independent ledger and a seeded randomized driver (22, 6 seeds) pass. Challenge adversarial
suite (118): unauthorized, duplicate, boundaries, malformed ground/citation, foreign/nonexistent evidence, injection, 33 malformed model shapes,
provider failure, validator replay, lapse, settlement interplay. Pure logic (45). Mutation checks confirmed key guards are tested.

## 18. Tooling
`pytest tests/direct`: **510 passed** (303 prior + 207 new). `genvm-lint lint` passed; `validate` 40 methods (18 view, 22 write); `schema` OK;
`typecheck` 0 errors / 0 warnings. Real glsim `test_real_settlement.py` passed (30 txs, all validators agree): no-contest lifecycle, deterministic
dispute + challenge + zero settlement, one-shot guards. glsim does not track balances (holder/contract both 0), so actual transfer emission is unverified.

## 19. Bugs found/fixed
Challenge result re-validation failed on its own normalized shape (fixed: idempotent 4-key shape). Ineligible evidence could not be cited (relaxed for recorded
ineligible records). `challenge_depth == 0` was ignored (now disables challenges and the window wait). Stage 1 hole: reservation releasable at `coverage_end`,
defeating grace-window claims and releasable under open claims (fixed).

## 20. Deviations
Stage 1 `release_expired_reservation` / `cancel_warranty` tightened (grace + no unsettled claims); 5 prior tests' warp times shifted past the grace window (not
weakened; flagged). `Reservation.amount` now means remaining reserved. Stage 0 challenge schema (`corrected_field/value`) replaced by `corrections` dict. No other
Stage 1-3.5 change.

## 21. Unresolved risks
Missing remedy row for a payable outcome blocks finalization (fail closed; stuck until constitution authoring avoids it). First-settled-first-served on overlapping
claims. First-come 10-evidence cap (unchanged). Unresolvable challenge waits up to one extra window before lapse. IGNORED_EVIDENCE can alter several fields.

## 22. StudioNet gates (CLAUSE is not release-ready until proven)
1. Genuine `web.render(..., mode="text")`. 2. Disagreement/undetermined-consensus rollback. 3. Real protocol timestamps. 4. Real payable/value behaviour without the shim.
5. Real-model semantic adjudication. 6. Real-model prompt-injection resistance. 7. **New:** real-model challenge review and remand. 8. **New:** withdrawal transfer
emitted only after finalization / real balance movement.

## 23. Proposed Stage 5 (frontend, proposal only)
Read-model-driven UI: claim timeline and Resolution Receipt, challenge form with per-ground citation pickers, window countdown from protocol time, finality-checklist
gating (verify Finalized before finalize/settle/withdraw), holder withdrawal, manufacturer pool/warranty console; wrong-chain/rejected-signature/undetermined states;
strict "Application Challenge" vs "GenLayer Protocol Appeal" wording.

## 24. Git
Committed on `master` (hash in the final message).

## 25.
No production frontend was implemented.

## 26.
No StudioNet deployment was performed and no user wallet/private key was used.
