# CLAUSE - Stage 3.5 Hardening

Scope: three focused Stage 3 hardening changes. No Stage 4 work, no StudioNet deployment, no wallet/key.

## 1. Evidence cap (no silent truncation)
- `_MAX_ADJUDICABLE_EVIDENCE = 10` (replaces the old prompt-only `_MAX_EVIDENCE_IN_PROMPT`).
- Enforced in `submit_evidence`, before freeze: an ELIGIBLE record is rejected
  (`claim already has the maximum of 10 adjudicable evidence records`) if the claim already holds 10 eligible
  records. The count is recomputed from stored records on every call, so it spans all transactions, both
  parties, all categories and any ordering. Duplicate URLs are rejected earlier and consume nothing.
  Ineligible records can never be adjudicated, so they do not consume adjudicable capacity (otherwise a party
  could exhaust the cap with junk to block the other side).
- `adjudicate_claim` shows every eligible+available+frozen record (`shown.append(rec)`, no slicing) and
  asserts `len(shown) <= 10` as an invariant. `evidence_ids_considered` therefore equals the full set.
- Submissions after freeze are already rejected (Stage 2), so the frozen set is final.
- Proof: source guard test (no slicing, old constant gone); boundary tests at 9/10/11; mutation check -
  removing the cap check makes 5 tests fail.

## 2. Outcome derivation (first match wins)
| # | Condition | Outcome |
|---|---|---|
| 1 | version FAIL | INVALID_CLAIM |
| 2 | window FAIL | NOT_COVERED (affirmative: failure outside coverage window) |
| 3 | sufficiency UNAVAILABLE | EVIDENCE_UNAVAILABLE |
| 4 | sufficiency INSUFFICIENT | INSUFFICIENT_EVIDENCE |
| 5 | product FAIL | NOT_COVERED (affirmative: product mismatch) |
| 6 | product UNCLEAR | INSUFFICIENT_EVIDENCE |
| 7 | exclusion established | NOT_COVERED (affirmative: exclusion applies; beats a covered clause) |
| 8 | covered clause established AND product/window/version/source all PASS AND SUFFICIENT | COVERED |
| 9 | anything else | **INSUFFICIENT_EVIDENCE** (changed from NOT_COVERED) |

NOT_COVERED now arises only from rows 2, 5, 7. Absence of proof of coverage is never treated as a finding
that coverage fails. COVERED requires every positive condition and no established exclusion.
Two existing assertions that encoded the old catch-all (`test_clearly_not_covered_sufficient_evidence_but_no_covered_condition`,
one row of `test_outcome_derivation_table`) were updated to the new required behavior; nothing was removed or weakened otherwise.

## 3. source_authority semantics
- FAIL is intentionally unreachable: Stage 2 deterministically marks evidence INELIGIBLE (host/scheme policy)
  before any retrieval; adjudication skips ineligible records, and the checker rejects any model-relied id that was
  not shown. The model cannot promote or override eligibility.
- PASS: at least one shown (eligible, available, frozen) evidence id is relied on. UNCLEAR: nothing relied on
  (including all deterministic short-circuits). Since coverage needs SUFFICIENT evidence, which needs a relied id, COVERED
  always has PASS.
- FAIL stays in the frozen schema for forward compatibility (frozen, not altered); `_derive_outcome` treats a
  non-PASS source as unable to yield COVERED (falls to INSUFFICIENT_EVIDENCE).
- Tests: only-ineligible evidence -> no model call, UNCLEAR; model relying on an ineligible id -> rejected, claim stays
  EVIDENCE_FROZEN; ineligible ids/hosts absent from the prompt.

## 4. Tests added (`tests/direct/test_stage3_5_hardening.py`, 17)
Cap: 9 and 10 accepted and fully adjudicated; 11th rejected (both parties share cap); multi-tx/multi-party;
duplicates do not consume slots; category/URL-variant bypass; ineligible ordering; post-freeze; source guard.
Truth table: exhaustive 432 combinations vs independent oracle; COVERED iff all positive; NOT_COVERED only with an affirmative
reason; named cases. Source authority: 4 tests.

## 5. Results
`pytest tests/direct`: **303 passed** (286 prior + 17). `genvm-lint lint` passed; `validate` passed (29 methods);
`schema` OK; `typecheck` 0 errors / 0 warnings. (Windows needs `PYTHONUTF8=1` for lint output.)
The real-glsim integration test was not re-run this pass (its paths are deterministic and unaffected by the cap or table change; it needs `scripts/run_real_web.sh`).

## 6. Bugs found
The old catch-all mapped "sufficient evidence but nothing established" to NOT_COVERED. Also the prompt-only cap silently dropped records 11+.

## 7. Files changed
`contracts/clause_protocol.py`, `tests/direct/test_stage3_adjudication.py` (2 assertions), `tests/direct/test_stage3_5_hardening.py` (new),
`docs/ADJUDICATION_SCHEMA.md`, `docs/THREAT_MODEL.md`, this file.

## 8. Unresolved risks
One party can fill all 10 eligible slots before the other submits (first-come); per-party quotas would be a design change, not done.
StudioNet gates unchanged: real render, undetermined-consensus rollback, protocol timestamps, payable behavior without shim, real-model adjudication.

Stage 4 was not implemented. No StudioNet deployment was performed and no user wallet/private key was used.
