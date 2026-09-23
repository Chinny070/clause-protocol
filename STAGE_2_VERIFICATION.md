# CLAUSE — Stage 2 Verification Report (Claims + Evidence Locker + Real GenLayer Web Retrieval)

## 1. Verdict

**PASS WITH BLOCKERS.** All 187 direct-mode tests pass, `genvm-lint lint`/`validate`/`schema`
are clean, `typecheck` reports 0 errors/0 warnings. The one blocker: a genuine
live-network (`glsim`) integration test — required by item 17 ("at least one later Stage 2
integration test must use real GenLayer web retrieval, not only a mocked wrapper") — was
**not completed** this session. See §12 and §15 for the honest account of what was and was not
achieved there. No Stage 3 semantic adjudication exists. No deployment was performed.

## 2. Files changed/created

New:
- `docs/STAGE_2_WEB_API_VERIFICATION.md`
- `tests/direct/test_stage2_smoke.py`, `test_stage2_claims.py`, `test_stage2_response.py`,
  `test_stage2_source_eligibility.py`, `test_stage2_evidence_retrieval.py`,
  `test_stage2_freeze_and_fingerprint.py`, `test_stage2_prompt_injection.py` (71 new tests).
- `STAGE_2_VERIFICATION.md` (this file).

Changed:
- `contracts/clause_protocol.py` — added `Claim`/`EvidenceRecord` dataclasses, 4 new write
  methods (`file_claim`, `respond_to_claim`, `submit_evidence`, `freeze_evidence`) and 4 new
  view methods (`get_claim`, `list_claim_ids_for_warranty`, `get_evidence`,
  `list_evidence_ids_for_claim`), plus module-level retrieval/eligibility helper functions.
  One Stage 1 line changed (see §14 — `file_claim`'s claimability check).
- `docs/DATA_MODEL.md`, `docs/EVIDENCE_ARCHITECTURE.md`, `docs/STATE_MACHINES.md`,
  `docs/TEST_MATRIX.md` — Stage 2 "as-implemented" addenda, Stage 0 sketches left in place.
- `tests/direct/helpers.py` — Stage 2 builder functions (`file_claim`, `respond`,
  `submit_evidence`, `freeze_evidence`, `create_constitution_stage2`).
- `tests/direct/test_constitution_hardening.py` — extended the schema-derived write-method
  audit (Stage 1 hardening pass) to cover the 4 new Stage 2 write methods.

Unmodified: every other Stage 0/1 doc, `STAGE_0_AUDIT.md`, `STAGE_1_VERIFICATION.md`.

## 3. Exact current GenLayer web APIs verified

Full detail in `docs/STAGE_2_WEB_API_VERIFICATION.md`. Headline finding: **the installed SDK's
`Response` dataclass has a field named `status`, not `status_code`** — this directly
contradicts docs.genlayer.com's prose example (which shows `.status_code`) and corrects a
Stage 0/1 note that had speculated `.status_code` was current based on docs alone. Resolved in
favor of the installed source (`genlayer/gl/nondet/web.py`, read directly), since that is what
actually executes under CLAUSE's pinned runner hash. Also confirmed: `render`'s mode literals
are exactly `'text'` (default) / `'html'` / `'screenshot'`; `wait_after_loaded` is supported;
`run_nondet_unsafe`/`run_nondet` signatures and eager-evaluation behavior are unchanged from
Stage 0/1; rollback/`Undetermined` semantics are unchanged (protocol-level, not locally
re-verifiable); no SDK-level enforcement of "web calls only inside a nondet block" was found,
so CLAUSE treats it as a hard convention rather than a runtime-enforced rule.

## 4. Claim lifecycle implemented

`Claim` binds: `claim_id`, `warranty_id`, `program_id`, `holder`, `manufacturer`,
`constitution_id` + `constitution_fingerprint` (captured immutably at filing — a later
constitution edit under the same program can never redirect an already-filed claim, proven by
`test_constitution_fingerprint_captured_immutably`), `failure_asserted_at` (claimant assertion,
never used in any deadline check), `targeted_clause_ids` (canonical-JSON, all must be `COVERED`
clauses on the governing constitution), `filed_at`, `response_deadline`,
`manufacturer_response`, `responded_at`, `evidence_frozen_at`, `status`. Lifecycle:
`RESPONSE_WINDOW -> {ACCEPTED | DISPUTED}` (explicit response, before deadline) or
`RESPONSE_WINDOW -> DISPUTED` (derived at read time once the deadline passes with no response —
silence does **not** grant a no-contest); `DISPUTED -> EVIDENCE_FROZEN` via `freeze_evidence`.
No semantic verdict field exists anywhere on `Claim` — Stage 3 scope only.

## 5. Manufacturer response mechanics

`respond_to_claim(claim_id, decision)`, `decision in {"ACCEPT", "DISPUTE"}`. Caller must equal
`claim.manufacturer` exactly; response is a strict one-shot (`manufacturer_response == ""`
guard, so a duplicate call — even the same decision twice — reverts, proving immutability, not
merely no-op); must be within `now <= response_deadline` (exact-deadline boundary tested and
succeeds; one second later reverts). `ACCEPT` sets `status = ACCEPTED` (Stage 2 does not
settle it — no GEN moves); `DISPUTE` sets `status = DISPUTED`, opening the door to evidence.

## 6. Source-eligibility implementation

A documented mini-DSL on `WarrantyConstitution.source_eligibility_policy`: comma-separated host
rules. Bare host = exact match only, never a subdomain, never a suffix/prefix lookalike
(`urllib.parse.urlsplit(...).hostname` is used for parsing, which structurally defeats
`manufacturer.example.attacker.example`-style attacks rather than relying on a hand-rolled
string check that could be gotten wrong). `"*.host"` = subdomains only, not the bare host.
Scheme fixed to `https` only (not yet per-constitution-configurable — a Stage 2
simplification, documented as such). Eligibility is decided once at `submit_evidence` time and
never reconsidered; an ineligible-but-well-formed submission is **recorded**, not reverted
(matches the original Stage 0 design intent exactly), while structurally malformed input
(empty/missing-scheme/oversized URL, unknown category, duplicate URL) does revert.

## 7. `get` vs `render` strategy

Deterministic, frozen at submission time, never re-derived: a category name ending in
`"_RENDERED"` uses `gl.nondet.web.render(url, mode="text")`; every other category uses
`gl.nondet.web.get(url)`. Stored on the `EvidenceRecord` itself so it cannot drift between
submission and freeze. No fallback switching between mechanisms exists — a category either
requires rendering or it doesn't, permanently, by naming convention.

## 8. Bounded evidence representation

`extracted_content` is `.strip()[:2000]` of the fetched body/rendered text — a fixed,
documented ceiling (`_MAX_EXTRACT_LEN`), never the raw page. No HTML parsing/boilerplate
stripping is performed (avoided a dependency on an HTML parser inside the GenVM sandbox);
`mode="text"` rendering already returns browser-extracted readable text for JS pages, and
static `get` responses are used as-is up to the cap. `original_url`, `category`,
`retrieval_status`, `host`, `retrieval_method`, and the fingerprint are preserved alongside.
No extraction step calls any LLM — see §9/§13.

## 9. Fingerprint definition

`sha256` over the Stage 1 canonical-JSON encoding of exactly six fields: `evidence_id`,
`claim_id`, `original_url` (as submitted, not re-normalized), `category`, `retrieval_status`,
`content`. Uses the same `_canonical_json`/`_fingerprint` helpers Stage 1 already committed to
— no separate, weaker encoding was introduced for evidence.
`test_fingerprint_recomputed_from_first_principles` independently rebuilds this exact
dict/hash using only stdlib `json`/`hashlib` (never calling any CLAUSE helper) and confirms it
matches the on-chain value.

## 10. Freeze/immutability guarantees

`freeze_evidence(claim_id)` is permissionless, processes every `ELIGIBLE` + not-yet-processed
(`retrieval_status == ""`) record for the claim in one transaction, and is guarded against
double-freeze at the claim level (`evidence_frozen_at == 0`). No write method anywhere in the
schema takes an `evidence_id` and mutates an already-processed record — proven both by the
Stage 1 hardening pass's schema-derived audit (extended this stage to cover the 4 new write
methods) and by direct snapshot-equality assertions after freeze. Evidence submitted after
freeze is rejected outright (`claim.evidence_frozen_at != 0` guard in `submit_evidence`).

## 11. Complete test/lint/typecheck results

```bash
PYTHONIOENCODING=utf-8 genvm-lint lint contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 genvm-lint validate contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 genvm-lint schema contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 genvm-lint typecheck contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 python -m pytest tests/ -q
```

- `lint`: ✓ Lint passed (3 checks).
- `validate`: ✓ Validation passed — Contract: ClauseProtocol, Methods: 27 (13 view, 14 write).
- `schema`: matches the 27-method inventory exactly.
- `typecheck`: 0 errors, 0 warnings (informational `reportOptionalMemberAccess` notices only,
  same class as Stage 1's — pyright cannot narrow `Optional[T]` through the `_require` helper).
- Full suite: **187 passed, 0 failed, 0 skipped.**

## 12. Real-web tests performed and results

**Mocked (gltest-direct `mock_web`), 42 tests across `test_stage2_evidence_retrieval.py`,
`test_stage2_source_eligibility.py`, `test_stage2_freeze_and_fingerprint.py`,
`test_stage2_prompt_injection.py`, `test_stage2_smoke.py`:** all pass, exercising both `GET`
and `render` code paths, both retrieval outcomes and eligibility outcomes, through the actual
`gl.nondet.web.get`/`render` -> `run_nondet_unsafe` call chain (not a hand-rolled
stand-in — the real SDK functions are called, only the underlying HTTP transport is mocked by
the test harness).

**Genuine live-network attempt:** `glsim` (GenLayer's official lightweight local network
simulator, bundled in this workspace's `genlayer-test` install) was started locally
(`python -m glsim --port 4021 --validators 3 --no-browser`) and confirmed healthy — a real
JSON-RPC call (`eth_chainId`) returned `0xeec7` (61127, the documented Localnet chain ID) from
`http://127.0.0.1:4021/api`. This is "official local tooling" per the build brief's own
framing (docs.genlayer.com's Networks page lists Localnet as "Requires GenLayer Studio or
GLSim"), not StudioNet, and used no wallet and no GEN. **However, a full scripted
deploy-and-exercise run against it (deploy `clause_protocol.py`, file a claim, submit a real
public URL as evidence, call `freeze_evidence`, confirm real retrieval) was not completed this
session** — assembling a correct `genlayer-py` client against `glsim`'s RPC shape (whose
bundled chain-preset object in `genlayer_py.chains.localnet` points at the wrong port/chain-id
combination for this simulator and needed a hand-built chain object) consumed more time than
remained in this session's budget, and was stopped rather than rushed or faked. `glsim` was
shut down cleanly afterward; nothing was left running.

**Item 18 (real-web smoke fixture):** proposed but not executed live — `https://docs.genlayer.com`
(the same domain already used throughout this stage's mocked tests as a stand-in) is the
intended fixture: stable, official GenLayer documentation, expected retrieval method `GET`,
expected extracted fact "the page returns a non-empty body" (this fixture proves the pipeline
works, not any warranty fact). This should be the first thing exercised once the `glsim`
integration gap above is closed.

## 13. Bugs discovered and fixes

1. **`file_claim`'s original claimability check (`_effective_status(passport) ==
   PASSPORT_ACTIVE`) contradicted the frozen `claim_deadline_s` grace window.** A passport
   reads `EXPIRED` the instant `now >= coverage_end`, but the whole point of
   `claim_deadline_s` is to let a holder file *after* coverage ends, within a grace period.
   Caught by `test_claim_at_exact_deadline_boundary_succeeds` failing on the very first run.
   Fixed: the check is now `passport.status != PASSPORT_CANCELLED` (the raw stored status, not
   the derived one) — only a genuinely cancelled warranty is unclaimable; the deadline is
   enforced separately and explicitly (`now <= coverage_end + claim_deadline_s`).
2. **`failure_asserted_at` had no type validation** — a caller could pass a non-integer and it
   would be stored uninspected (Stage 1's `u64` type hints are not runtime-enforced in
   direct-mode calls). Added an explicit `isinstance(int)` (excluding `bool`) check.
3. **Test-authoring bug (not a contract bug): two `direct_deploy()` calls inside one test
   function collide** on `gltest`'s SDK-level `__known_contract__` process global (not reset
   between deploys within a single test, only between test functions). Caught before it could
   mask a real result; fixed by restructuring the affected fingerprint-difference test to
   compare one live on-chain fingerprint against an independently-computed expected value
   instead of two live deploys.
4. **Test-authoring bug (not a contract bug): an attempted "leader-exception atomicity" test
   assumed `gl.nondet.web.get` raising would propagate out of `freeze_evidence`.** It does
   not — `_fetch_evidence_once`'s own try/except catches it and returns `UNAVAILABLE`, by
   design. Rewritten to test what is actually true (ordinary failures never escape as
   exceptions) rather than a scenario the code structurally prevents.

No bugs were found in the source-eligibility matching logic, the fingerprint definition, or
the freeze idempotency guards during this pass — all findings were in claimability-window
interaction and test-harness mechanics.

## 14. Stage 0/1 deviations

**One Stage 1 code line changed**, reported per the build brief's incompatibility-reporting
requirement even though it did not require stopping (the fix is additive/corrective, not a
redesign, and no Stage 1 test's expected behavior changed — all 116 Stage 1 tests still pass
unmodified):

1. *Exact incompatibility:* `file_claim` (new in Stage 2) needs to allow claims filed within
   the grace window after `coverage_end`, but a naive reuse of Stage 1's `_effective_status ==
   PASSPORT_ACTIVE` pattern (used correctly elsewhere, e.g. `issue_warranty`) would reject
   every such claim, since the passport already reads `EXPIRED` by then.
2. *Affected Stage 1 invariant:* none — `_effective_status`/`PASSPORT_EXPIRED` derivation
   itself is untouched; only `file_claim`'s own new precondition was written correctly instead
   of copy-pasted incorrectly.
3. *Change made:* `file_claim` checks `passport.status != PASSPORT_CANCELLED` (raw stored
   status) instead of `_effective_status(passport) == PASSPORT_ACTIVE`.
4. *Security/trust implications:* none identified — the timing window is still fully enforced
   by the explicit `claim_deadline_s` check; a cancelled warranty is still correctly
   unclaimable; an expired-and-past-grace warranty is still correctly unclaimable (via the
   deadline check, not the status check).
5. *Tests needing updating:* none in Stage 1 (no Stage 1 test exercised `file_claim`, since it
   didn't exist yet); Stage 2's own `test_claim_at_exact_deadline_boundary_succeeds` and
   `test_claim_against_cancelled_warranty_rejected`/`test_claim_against_expired_warranty_
   rejected` in `test_stage2_claims.py` cover the corrected behavior directly.

No other Stage 0/1 architecture, invariant, or test was touched.

## 15. Unresolved risks

1. **Live-network (`glsim` or StudioNet) verification of real web retrieval is still
   required** — this is the one blocker behind the "PASS WITH BLOCKERS" verdict. `glsim` was
   confirmed reachable; the scripted exercise against it was not completed. Recommended next
   step: finish a `genlayer-py`-based script against a manually-constructed `glsim` chain
   object (port 4021 or whatever port is used, chain ID 61127) before treating Stage 2's web
   pipeline as production-credible.
2. Carried forward, unchanged, from Stage 0/1: whether stable Studionet has been promoted to
   the v0.6 fee-funded lifecycle (irrelevant to Stage 2's non-payable methods, relevant again
   at Stage 4); native GEN custody/real consensus behavior remains untested beyond direct-mode
   simulation.
3. **Direct-mode cannot simulate a real leader/validator disagreement causing a transaction to
   revert** (confirmed by reading `gltest.direct.loader._patch_run_nondet_for_direct_mode`,
   documented in `docs/STAGE_2_WEB_API_VERIFICATION.md`) — Stage 2's equivalence-check logic
   (`validator_fn` in `freeze_evidence`) is exercised for its comparison *logic* only via
   `run_validator()`-style reasoning embedded in the test suite's assertions about what would
   disagree, not via an actual observed rollback. This is a standing tooling limitation, not a
   CLAUSE defect, and matches this workspace's own repeatedly-documented pattern.
4. `_MAX_EXTRACT_LEN=2000` and the host-DSL's https-only/no-per-constitution-scheme are
   Stage 2 simplifications, not frozen product decisions — worth revisiting once real evidence
   shapes are seen from a live network.

## 16. Whether live StudioNet verification is still required

**Not StudioNet specifically** — nothing in Stage 2 requires StudioNet, and none was used or
recommended. What **is** still required, per §12/§15 item 1, is a genuine local-network
(`glsim`) exercise of the real `gl.nondet.web.*` retrieval path end to end, which remains
incomplete. This can and should be done entirely locally, with no GEN and no user wallet,
before Stage 2's web-retrieval claim is fully closed out.

## 17. Proposed Stage 3 scope

Semantic claim adjudication only, per the build brief's own Stage 3 boundary: read frozen
`Claim` + all its frozen `EvidenceRecord`s (never re-fetch, never re-derive eligibility),
produce the frozen minimum Adjudication schema (`docs/ADJUDICATION_SCHEMA.md` — `product_match`
/ `warranty_version_match` / `coverage_window` / `covered_clause_ids` / `exclusion_clause_ids`
/ `evidence_sufficiency` / `source_authority` / `evidence_ids_relied_on` / `outcome` /
`rationale`) via `gl.vm.run_nondet_unsafe` with a hand-written validator doing structural-field
comparison only (never comparing `rationale` text), fail-closed shape validation before any
mutation, and explicit routing to `INSUFFICIENT_EVIDENCE`/`EVIDENCE_UNAVAILABLE` when no
eligible/available evidence exists for a claim — still **not** settlement, still not
appeals/challenges, still no frontend, still no deployment. The live-network gap in §15 item 1
should be closed before or alongside Stage 3, since Stage 3's adjudication reads the very
evidence that gap concerns.

## 18. Git status and commit hash

Branch `master`, no remotes, working tree clean after commit `850980a` ("feat: implement
CLAUSE Stage 2 - claims, evidence locker, real GenLayer web retrieval", 16 files changed, 2039
insertions). Preceding history: `ba1dd44`/`5cc7053` (Stage 1 hardening pass), `f701299`/
`2f088e7`/`b47daad` (Stage 1 / Stage 0).

## 19. Required statement

**No Stage 3 semantic claim adjudication was implemented.**

## 20. Required statement

**No production deployment was performed and no user wallet/private key was used.**
