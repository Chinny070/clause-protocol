# CLAUSE - Stage 3 Verification (Structured Semantic Warranty Adjudication)

## 1. Verdict: PASS WITH BLOCKERS

Contract-side adjudication logic is implemented and verified (direct mode with a mocked model, plus real
glsim runs of the deterministic and fail-closed paths). **No real model route exists in this
environment**, so genuine semantic leader/validator consensus, real-model injection resistance, real
render, and undetermined-consensus rollback are NOT verified. They are StudioNet gates (section 20).

## 2. Files changed / created
Modified: `contracts/clause_protocol.py`, `docs/{ADJUDICATION_SCHEMA,DATA_MODEL,STATE_MACHINES,TEST_MATRIX,THREAT_MODEL}.md`,
`tests/direct/helpers.py`, `tests/direct/test_constitution_hardening.py`.
Created: `docs/STAGE_3_ADJUDICATION_API_VERIFICATION.md`, `docs/STAGE_3_RUN_LOG.json` (generated),
`tests/direct/test_stage3_{adjudication,malformed_output,prompt_injection,validator_replay}.py`,
`tests/integration/test_real_adjudication.py`, this file.

## 3. Adjudication APIs verified
`gl.nondet.exec_prompt(prompt, response_format="json")` (returns dict), `gl.vm.run_nondet_unsafe(leader, validator)`,
`gl.vm.UserError` (`gl.UserError` from docs does not exist in the installed SDK). genvm-lint requires
`gl.nondet.*` calls in module-level functions. Detail: `docs/STAGE_3_ADJUDICATION_API_VERIFICATION.md`.

## 4. Exact prompt-input fields
governing_rules: `constitution_version, product_scope, coverage_calc, targeted_covered_clauses[{clause_id,text}], exclusion_clauses[{clause_id,text}]`.
claim_facts: `claim_id, registered_product_model, failure_date_asserted_by_claimant_unverified, coverage_start, coverage_end, protocol_determined{warranty_version_match, coverage_window}`.
evidence (max 10, ELIGIBLE+AVAILABLE+frozen): `evidence_id, category, submitted_by, source_host, retrieved_at, content`.
Never included (test-enforced): balances, capacity, remedy values, reservations, addresses, commitments, fingerprints, manufacturer response, behavior-policy fields, ineligible/failed evidence.

## 5. Structured output schema
Frozen 10-field schema stored unchanged in `Adjudication`. Model emits a strict 6-key subset
(`product_match, covered_clause_ids, exclusion_clause_ids, evidence_sufficiency, evidence_ids_relied_on, rationale`);
the contract derives the remaining fields. Not a schema change.

## 6. Deterministic validation / invariants
`_check_model_result`: strict JSON object, exact keys, enums, types, rationale 1..1000 chars (rejected, never truncated),
no duplicates, ids must be in the claim's targeted COVERED clauses / constitution EXCLUDED clauses / evidence shown,
coherence rules (SUFFICIENT needs relied evidence; INSUFFICIENT forbids clauses; covered clause needs product PASS + SUFFICIENT;
product FAIL forbids covered clause). No repair or coercion; only id lists are sorted.

## 7. Validator equivalence design
Equality of `_structural_key` = product_match, sorted covered ids, sorted exclusion ids, evidence_sufficiency, sorted relied ids.
Rationale never compared. Validators re-run the full checker on the leader's value; a validator whose own call fails votes False.
Leader/validator pair is one module-level function (no closure over loop/method state).

## 8. Outcome derivation
First match wins: version FAIL -> INVALID_CLAIM; window FAIL -> NOT_COVERED; UNAVAILABLE -> EVIDENCE_UNAVAILABLE;
INSUFFICIENT -> INSUFFICIENT_EVIDENCE; product FAIL -> NOT_COVERED, UNCLEAR -> INSUFFICIENT_EVIDENCE; established exclusion -> NOT_COVERED;
covered clause + all PASS + SUFFICIENT -> COVERED; else NOT_COVERED. The model never emits `outcome`.

## 9. Exclusion handling
An exclusion counts only if the model lists it as established by evidence. Existence in the constitution is not proof of application;
absence of proof of an exclusion does not create coverage (needs an affirmative covered clause). Established exclusion beats covered clause. Both lists stored.

## 10. Temporal / source-authority handling
Window: deterministic, claimant-asserted failure date vs frozen passport window (never UNCLEAR). Version: deterministic (constitution id + fingerprint).
Source authority: PASS iff at least one evidence id relied on, else UNCLEAR; FAIL is reserved and currently unreachable (ineligible evidence never reaches adjudication).
Deterministic failures skip the model call entirely.

## 11. Prompt-injection defenses
Evidence is placed in a JSON-string data slot after the rules, cannot forge section headers; instructions forbid obeying evidence and browsing;
no web call during adjudication; strict output checker rejects extra keys such as `outcome`/`payout`; outcome derived in Python; deterministic facts computed outside the model.
11 injection tests. Real-model resistance unproven (gate).

## 12. Claim-state transition
EVIDENCE_FROZEN -> DECIDED on accepted adjudication; immutable Adjudication record with `challenge_window_closes_at`, `decision_path`, `evidence_ids_considered`.
No money moves, no reservation change.

## 13. Malformed-output results
37 tests pass: 33 malformed shapes each rejected with the checker's `[LLM_ERROR]`, provider failure, rationale bound, sort-only normalization. Claim remains EVIDENCE_FROZEN with no Adjudication stored.

## 14. Validator-replay results
21 tests pass (agree; rationale-only difference; each structural change; tampered leader; leader error; validator-model failure; two-claim closure isolation).
Mutation check: a deliberately injected shared-state bug made the isolation test fail; contract restored.

## 15. glsim semantic-consensus result
**Not achieved.** glsim's live LLM handler supports only `openai:*`/`anthropic:*` with API keys; none available. Real runs: deterministic paths succeed with
5-validator agreement; the semantic path fails closed (glsim returned a provider error as a string, rejected as non-dict; nothing stored). Log: `docs/STAGE_3_RUN_LOG.json`.
Mocked tests are not presented as live.

## 16. Test / lint / typecheck results
`pytest tests/direct`: **286 passed** (Stage 1/2/2.5 regression + 29 + 37 + 11 + 21 Stage 3). `genvm-lint lint` passed (3 checks), `validate` 29 methods (14 view, 15 write),
`schema` OK, `typecheck` 0 errors 0 warnings. (Note: on Windows, lint needs `PYTHONUTF8=1`, else its checkmark crashes the console.)

## 17. Bugs / fixes
Nested nondet helper failed lint reachability -> moved to module-level `_model_call`. Test-side fixes (prompt word "missing", string newline). Malformed-output tests tightened to check the real rejection reason.
Doc count fix (injection tests 11).

## 18. Architecture deviations
None to Stages 1-2.5. Model emits a 6-key subset with contract-derived remainder (documented). `file_claim` duplicate allow-list now includes DECIDED.

## 19. Unresolved risks
Evidence cap of 10 in the prompt; DECIDED does not block new claims; `source_authority` FAIL unreachable; real-model behavior/injection unproven; glsim rollback unreliable (atomicity achieved structurally by writing state only after consensus returns).

## 20. Outstanding StudioNet gates (CLAUSE is not release-ready until proven)
1. Genuine `web.render(..., mode="text")`.
2. Validator-disagreement / undetermined-consensus rollback.
3. Protocol timestamp behavior.
4. Payable/value behavior without the glsim shim.
5. Genuine semantic adjudication with a real model (incl. real-model injection test).

## 21. Proposed Stage 4 scope (proposal only, not started)
Challenge and finality: one bounded challenge inside `challenge_window_closes_at`, deterministic resolution using stored `evidence_ids_considered`/`decision_path`,
finality gating, then deterministic settlement/withdrawal from the RemedyRow table.

## 22. Git status / commit
See the commit message on branch `master` of the isolated repo (hash reported in the final message); `.scratch/` is gitignored.

## 23.
No settlement, payout, withdrawal, application appeal, or production frontend was implemented.

## 24.
No StudioNet deployment was performed and no user wallet/private key was used.
