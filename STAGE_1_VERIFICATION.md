# CLAUSE — Stage 1 Verification Report (Deterministic Foundation)

## 1. Verdict

**PASS.** All 72 direct-mode tests pass, `genvm-lint lint`/`validate`/`schema` are clean, and
`typecheck` reports 0 errors / 0 warnings (informational `reportOptionalMemberAccess` notices
only, explained in §8). No production frontend, no evidence/adjudication/challenge/settlement
code, no deployment, no wallet/private key use.

**Update, hardening pass (2026-09-23): still PASS, now 116 tests.** See §15 for the four
hardening items (constitution-immutability testing strengthened to be schema-derived rather
than a hand-maintained name list; canonical-JSON invariants audited, documented, and actually
implemented rather than assumed; the u32-vs-u64 TreeMap-key decision independently
re-verified with a correction to which `genvm-lint` subcommand is responsible; and the
timestamp trust boundary formally audited and tested).

## 2. Repository isolation verification

- Repository root: `C:/Users/USERpc/clauseproduct` (confirmed via `git rev-parse
  --show-toplevel`, run *inside* `clauseproduct/` — a fresh `git init`, not a subdirectory of
  the pre-existing home-directory repo).
- Current branch: `master`.
- Git status at isolation time: clean after two commits (`b47daad` docs, `2f088e7`
  `.gitattributes`); this session added Stage 1 files (contract, tests, `pyproject.toml`,
  updated `docs/DATA_MODEL.md`), all now committed — see §13.
- Configured remotes: **none** (`git remote -v` returns empty). No remote was invented, per
  instruction.
- Verified isolation from the unrelated parent repo: `C:\Users\USERpc` (root repo, remote
  `github.com/Chinny070/contradiction-protocol.git`) sees `clauseproduct/` as a single opaque
  untracked entry (`?? clauseproduct/`) because `clauseproduct/.git` makes it a distinct
  repository boundary — the parent repo cannot descend into it, so `git add`/`git commit` run
  from the parent can never absorb CLAUSE's file contents; at most it could create a gitlink
  (submodule-style) reference, which this session never did. The parent repository was not
  modified, deleted, or committed to at any point.

## 3. Files created/changed this session

New:
- `contracts/clause_protocol.py` (764 lines) — the Stage 1 Intelligent Contract.
- `tests/conftest.py` — two Windows-only gltest-direct compatibility shims, reused verbatim
  from this workspace's own prior GenLayer projects (see §9).
- `tests/direct/helpers.py`, `tests/direct/test_smoke.py`, `test_authorization.py`,
  `test_constitution.py`, `test_passport.py`, `test_pool_accounting.py`, `test_temporal.py`,
  `test_invariants.py` — 72 tests total.
- `pyproject.toml` — pytest config (`testpaths = ["tests"]`).
- `.gitignore`, `.gitattributes` (repository-isolation housekeeping, described in the prior
  turn's response).

Changed:
- `docs/DATA_MODEL.md` — one callout block added at the top recording two implementation
  deviations discovered while linting real code against the installed SDK (§8). No other
  Stage 0 document was altered; no frozen architecture decision was reversed.

Unmodified: every other Stage 0 doc, `STAGE_0_AUDIT.md`.

## 4. Contract architecture implemented

Single Intelligent Contract, `ClauseProtocol` (`contracts/clause_protocol.py`), covering
exactly the Stage 1 scope: `WarrantyProgram`, `WarrantyConstitution`, `ClauseRecord` (Stage
0's `Clause`, renamed to avoid a Python name collision with the contract's own domain name),
`WarrantyPassport`, `WarrantyPool`, `Reservation`. 19 public methods (10 write, 9 view), 0
`gl.nondet.*` calls, 0 LLM calls, no `Claim`/`EvidenceRecord`/`Adjudication`/`Challenge`/
`ResolutionReceipt` types or methods exist anywhere in the file.

Every write method enforces its authorization boundary at the top of the method body before
any state read/write (manufacturer-only: program lifecycle, constitution creation, pool
withdrawal, issuance; holder-or-manufacturer: cancellation; permissionless-by-design:
`fund_pool`, `release_expired_reservation`, matching docs/STATE_MACHINES.md's explicit
rationale that these must never be stallable by a single party's inaction).

## 5. Pool/reservation model implemented

`WarrantyPool` tracks `total_balance` and `reserved_liability` only; `available_balance` is
never stored, always computed live as `total_balance - reserved_liability` (docs/
ECONOMIC_INVARIANTS.md's "computed, not tracked" rule). `pending_locks` (the Claim-level
subset of `reserved_liability`) is explicitly **not** implemented in Stage 1, correctly, since
no `Claim` exists yet to lock against — this is not an omission, it is Stage 1's scope
boundary working as designed. `fund_pool` is payable and unconditional-credit-first
(deliberately, to avoid replicating the "inbound value survives a reverted call" StudioNet
finding recorded in docs/THREAT_MODEL.md). `withdraw_pool` checks only against the live
`available_balance` and reverts on any amount exceeding it, structurally preventing withdrawal
of reserved funds regardless of call ordering. `issue_warranty` pre-checks
`max_deterministic_remedy <= available_balance` before creating any reservation, in the same
transaction — over-issuance beyond backed capacity is structurally impossible, not just
checked. `release_expired_reservation` and `cancel_warranty` both route through one shared
`_release_reservation` helper with a `RESERVATION_ACTIVE`-only guard, making double-release
of the same reservation impossible (proven in `test_invariants.py` and
`test_pool_accounting.py`).

## 6. Timestamp model implemented

`gl.message_raw["datetime"]` (confirmed live against the installed `py-genlayer` SDK source at
`genlayer/_internal/msg.py` to be an **ISO datetime string, not a unix integer** — see
docs/NETWORK_AND_SDK_VERIFICATION.md) is parsed once, in one function (`_parse_iso_datetime`),
to the `u64` unix-second epoch every other Stage 1 timestamp field is stored as. All Stage 1
timestamps (`registered_at`, `created_at`, `frozen_at`, `released_at`, `coverage_start`,
`coverage_end`) are protocol timestamps derived this way — never Python's `datetime.now()`
(which would read host wall-clock, not the consensus-visible transaction time). `now()` is
exposed as a public view so the future frontend can display server-observed protocol time.
`WarrantyPassport.status` is never mutated to `EXPIRED` by a background process; it is derived
at read time (`_effective_status`) by comparing `_now() >= coverage_end`, exactly matching
docs/STATE_MACHINES.md's "automatic ... derived at read time" rule, and is proven not to
regress a terminal `CANCELLED` status back toward `EXPIRED` (`test_cancelled_status_survives_
past_expiry`).

## 7. Constitution immutability protections

`WarrantyConstitution.is_frozen` flips to `True` inside `issue_warranty`, in the same
transaction that creates the first `WarrantyPassport` against it — never a separate, skippable
step. There is no write method anywhere in the contract's schema that takes an existing
`constitution_id` and mutates that record's own fields (`create_constitution` only ever
inserts a brand-new record); this is proven both by direct assertion
(`test_creating_another_constitution_never_mutates_the_first`,
`test_clauses_immutable_after_freeze`) and by schema introspection
(`test_retroactive_constitution_change_has_no_code_path`). The `fingerprint` field is a SHA-256
content hash over the full canonical-JSON-serialized frozen field set (not a subset), proven
by `test_fingerprint_reflects_full_frozen_field_set` to change whenever any frozen field
changes. `(program_id, version)` uniqueness is enforced at creation time (docs/
WARRANTY_CONSTITUTION.md's "Versioning is explicit, not inferred").

## 8. Complete test/lint results

Reproducible commands (run from `C:\Users\USERpc\clauseproduct`):

```bash
PYTHONIOENCODING=utf-8 genvm-lint lint contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 genvm-lint validate contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 genvm-lint schema contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 genvm-lint typecheck contracts/clause_protocol.py
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v
```

Results (this session, 2026-09-23):

- `genvm-lint lint`: **✓ Lint passed (3 checks)**.
- `genvm-lint validate`: **✓ Validation passed** — Contract: ClauseProtocol, Methods: 19 (9
  view, 10 write). One informational note: a newer runner than the pinned
  `1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` is available — intentionally not
  adopted mid-stage; re-evaluate before Stage 2 per docs/NETWORK_AND_SDK_VERIFICATION.md's
  standing re-verification practice.
- `genvm-lint schema`: matches §4's method inventory exactly, constructor takes 0 params.
- `genvm-lint typecheck`: **0 error(s), 0 warning(s)**. 23 informational
  `reportOptionalMemberAccess` notices remain, all on the pattern `x = self.foo.get(id);
  _require(x is not None, ...); x.some_field` — pyright's static analysis cannot see through
  the runtime `_require` call to narrow `Optional[T]` to `T`, so it flags every subsequent
  attribute access even though the contract already reverts one line earlier if `x` were
  `None`. This is a static-analysis limitation of the linter, not a real code path (every one
  of these lines is also exercised by a passing test that would fail on an actual `None`
  dereference), and the linter itself reports it as 0 errors/0 warnings, not a failure.
- Direct-mode test suite: **72 passed, 0 failed, 0 skipped** in ~88s
  (`tests/direct/test_smoke.py` [1], `test_authorization.py` [9], `test_constitution.py` [14],
  `test_passport.py` [13], `test_pool_accounting.py` [13], `test_temporal.py` [11],
  `test_invariants.py` [11]).

No critical test was skipped or left failing, per the build brief's explicit stop condition.

## 9. Discovered bugs and fixes (this session)

1. **genvm-lint's TreeMap-key Comparable check rejects `u64`.** Discovered when the first
   `lint` run failed with `TreeMap key for 'programs' must be Comparable (str, Address, u32,
   etc.), got 'u64'` on every `TreeMap[u64, ...]` field. Fixed by switching every entity ID
   field/type (`program_id`, `constitution_id`, `warranty_id`, `reservation_id`, and the four
   `next_*_id` counters) from `u64` to `u32`, keeping all genuine time/duration fields as
   `u64`. Recorded as Stage 1 implementation note #1 in `docs/DATA_MODEL.md`. No security or
   trust impact — u32's 4.29 billion range is not a practical constraint for Stage 1, and this
   is an ID-width choice, not a policy or authorization change.
2. **genvm-lint forbids `@staticmethod` on contract-adjacent methods** (matches this
   workspace's own previously-recorded finding, `[[genlayer_studio_init_annotation_gotcha]]`-
   adjacent). `_validate_clause_list`/`_validate_remedy_table` were originally `@staticmethod`
   members of `ClauseProtocol`; moved to plain module-level functions (they need no contract
   state) and call sites updated. No behavior change, purely a lint-compliance restructuring.
3. **Test helper timestamp bug (not a contract bug), caught before it could mask a false
   pass:** the first draft of `tests/direct/helpers.py::issue()` defaulted `coverage_start=0,
   coverage_end=ONE_YEAR` (epoch-zero-relative), which would have made every freshly issued
   test warranty already read as `EXPIRED` against the real current epoch time returned by
   `_now()`. Caught during test authoring (before any test run) and fixed to anchor both
   values off `contract.now()` at issuance time.

No bugs were found in the actual pool/reservation/immutability/authorization business logic
itself during this pass — all 72 tests passed on the first full run once the above three
tooling/test-authoring issues were fixed.

## 10. Deviations from Stage 0

Both deviations below are additive/representational only — no frozen behavior, invariant, or
authorization rule from Stage 0 was weakened, reversed, or silently changed. Both are recorded
in `docs/DATA_MODEL.md` as well as here, per the build brief's requirement.

**Deviation #1 — entity ID width: `u64` (as sketched) -> `u32` (as implemented).**
- *Original design:* `docs/DATA_MODEL.md` sketched `program_id`, `constitution_id`,
  `warranty_id`, `reservation_id` (and their TreeMap keys) as `u64`.
- *Discovered issue:* `genvm-lint validate` rejects `u64` as a `TreeMap` key type on the
  currently installed/pinned SDK (§9, item 1).
- *Change made:* every entity ID field and its TreeMap key use `u32` instead. Time/duration
  fields are unaffected and remain `u64`.
- *Reason:* the sketched types in a Stage 0 doc are a design intent, not something verified
  against the installed toolchain — this is exactly the kind of drift Stage 1's "reverify
  before coding" instruction exists to catch, and it was caught by running the actual linter
  against actual code rather than assumed compatible.
- *Security/trust impact:* none identified. u32 provides 4,294,967,295 possible IDs per entity
  type, vastly more than any plausible Stage 1-4 usage; no authorization, financial, or
  evidentiary logic depends on ID width.

**Deviation #2 — nested list/struct fields stored as validated JSON strings, not literal
nested `DynArray`/`TreeMap` collections.**
- *Original design:* `docs/DATA_MODEL.md` sketched `covered_clause_ids: DynArray[str]`,
  `remedy_table: DynArray[RemedyRow]`, etc., as literal nested storage collections on the
  `WarrantyConstitution` dataclass.
- *Discovered issue:* none specific to CLAUSE — this is a proactive choice, not a forced fix.
  This workspace's own prior GenLayer projects (Protocol Court, Treasury Trial) independently
  converged on "flat `@allow_storage @dataclass` + JSON-string fields for nested/list data" as
  the pattern with the most real-world mileage in this toolchain, versus deeply nested
  `DynArray[struct]`/struct-valued collections, which those projects treated as higher-risk
  and generally avoided.
- *Change made:* `covered_clause_ids_json`, `excluded_clause_ids_json`,
  `acceptable_evidence_categories_json`, and `remedy_table_json` are canonical-JSON strings,
  validated for exact shape (enum membership, cross-references to known clause IDs, numeric
  bounds) inside `create_constitution` before being stored — never trusted as free-form JSON
  at read time.
- *Reason:* proactively lower implementation risk by reusing a pattern already proven across
  multiple real deployments in this workspace, rather than being the first CLAUSE-specific
  code to exercise a less-tested nested-collection shape.
- *Security/trust impact:* none identified. Every JSON payload is validated exhaustively at
  write time (the same validation the sketched typed shape would have gotten "for free" from
  the type system is instead enforced explicitly in `_validate_clause_list`/
  `_validate_remedy_table`), and the fingerprint hashes the same logical field set either way.

## 11. Unresolved risks / blockers

Carried forward from `docs/NETWORK_AND_SDK_VERIFICATION.md` and `docs/THREAT_MODEL.md`,
unchanged by this stage (Stage 1 did not need `gl.nondet.web.*`, so none of these were
re-tested this session):

1. `gl.nondet.web.render` mode literals and `Response.status_code` still need confirmation
   against the installed package immediately before Stage 2 evidence-fetch code is written.
2. Whether stable Studionet has been promoted to the v0.6 fee-funded lifecycle needs
   re-checking before Stage 4.
3. The "inbound payable value survives a reverted call" StudioNet risk is mitigated by design
   in `fund_pool` (unconditional-credit-first) but remains **unverified live** — Stage 1's
   direct-mode tests cannot exercise real StudioNet consensus/value-transfer behavior at all
   (matches this workspace's standing, previously-documented limitation of the gltest direct
   runner). A future live-network verification pass (not this session, no deployment
   performed) is still required before this risk can be closed.
4. `withdraw_pool`'s real value transfer via `_EOA(...).emit_transfer(value=...)` is exercised
   correctly in direct-mode tests (the mock accepts and does not error), but direct-mode does
   not model real ghost-contract/ ­EVM-layer custody at all (confirmed in
   docs/NETWORK_AND_SDK_VERIFICATION.md: "Studio: balances are simulated in a local database.
   There is no EVM layer or ghost contracts in Studio" — and direct-mode is a further
   simplification below even that). This is the same standing "native GEN custody is
   integration/live-test only" caveat this workspace has recorded on every prior GEN-bearing
   contract; it is not a Stage 1 defect, just an untested-until-live boundary.

No new risks were introduced by Stage 1's own logic that are not already covered above or in
`docs/THREAT_MODEL.md`.

## 12. Proposed Stage 2 scope

Per the build brief and `docs/EVIDENCE_ARCHITECTURE.md`/`docs/STATE_MACHINES.md`: `Claim`
storage and its non-adjudication lifecycle (`file_claim`, `respond_to_claim`,
`expire_response_window`), `EvidenceRecord` storage and the deterministic Step 1
(source-eligibility) + real Step 2/3 (`gl.nondet.web.get`/`render` retrieval + bounded
extraction, re-verified against the installed SDK immediately before writing that code, per
open items #1 above) + Step 4 (`gl.vm.run_nondet_unsafe` leader/validator equivalence over
extracted facts) + Step 5 (`freeze_evidence` as its own committed transaction). Explicitly
**not** Stage 2: `Adjudication`/semantic verdicts (Stage 3), `Challenge`/appeals (Stage 4),
settlement (Stage 4), frontend (Stage 5), deployment. `pending_locks` pool accounting (the
Claim-level subset of `reserved_liability`) becomes real in Stage 2 once `Claim` exists to
lock against.

## 13. Git status and commit

```
$ git -C C:\Users\USERpc\clauseproduct log --oneline
f701299 feat: implement CLAUSE Stage 1 deterministic foundation
2f088e7 chore: pin LF line endings for contract source
b47daad docs: Stage 0 architecture freeze for CLAUSE
```

Branch: `master`. Remotes: none. Commit `f701299` includes this report itself, the contract,
and all test files (13 files changed, 2363 insertions). Working tree is clean after this
commit.

## 15. Stage 1 Hardening Pass (addendum, 2026-09-23)

Performed after an independent read-only audit of the original Stage 1 report and source.
Architecture and contract scope are unchanged - no evidence retrieval, nondeterministic
execution, adjudication, appeals, settlement, frontend code, or deployment was added. All four
requested items below, plus the optional dead-code cleanup.

### Item 1 — Constitution immutability testing, schema-derived

The original `test_retroactive_constitution_change_has_no_code_path` (still present, kept as
a defense-in-depth check) tested absence of mutation methods against a hand-maintained
forbidden-name set - a real weakness, since a method with a different name could in principle
still exist and mutate a constitution without ever appearing on that list.

New file `tests/direct/test_constitution_hardening.py` fixes this by deriving the write-method
inventory from the contract's own authoritative ABI schema (`genvm-lint schema --json`, the
same introspection GenVM itself uses) rather than a hand-maintained list:

- `test_write_method_inventory_matches_expected_set` asserts the schema's exact write-method
  set equals `{create_program, pause_program, resume_program, retire_program,
  create_constitution, fund_pool, withdraw_pool, issue_warranty, cancel_warranty,
  release_expired_reservation}` - 10 methods, matching `genvm-lint validate`'s own count. If a
  future stage adds/renames/removes a write method, this test fails immediately, forcing the
  audit below to be extended before anyone can trust its coverage claim again.
- `test_every_non_constitution_write_method_leaves_frozen_constitution_untouched` exercises
  every one of those 10 methods (all of them except `create_constitution` itself, which is the
  one method allowed to touch constitution storage, by inserting new records only) in a
  realistic sequence against a single frozen constitution, asserting full-dict equality
  (`get_constitution(...) == snapshot`) after every single call - this proves field-level
  semantic equality of all 15 frozen fields (`fingerprint` compared as its exact hex string,
  i.e. byte-for-byte) after each one, not a spot-checked subset.
- `test_retire_program_does_not_touch_constitution` isolates the one genuinely terminal write
  method (retiring forecloses further issuance) as its own minimal repro.
- `test_frozen_at_and_fingerprint_survive_repeated_issuance_byte_for_byte` directly targets the
  two fields most at risk of a subtle re-write bug (a timestamp and a hash), proving a second
  issuance against an already-frozen constitution changes neither, even when real protocol
  time has moved on between the two issuances (`direct_vm.warp`).

**Finding:** no mutation path exists beyond what Stage 1 already claimed - the original claim
was correct, but was resting on weaker evidence (a name blocklist) than it should have. It now
rests on the contract's own schema plus exhaustive behavioral proof across every real write
method.

### Item 2 — Canonical JSON invariants

**What "canonical JSON" means in CLAUSE, now explicit** (documented in `_canonical_json`'s
docstring in `contracts/clause_protocol.py`, Stage 1 hardening pass): a serialization is
canonical here iff two semantically-equivalent inputs always produce byte-identical output.
That requires two independent things: (a) object keys sorted and whitespace-free
(`json.dumps(sort_keys=True, separators=(",", ":"))` - this is what the *original* Stage 1
code actually did), and (b) any array whose element order carries no meaning (an unordered ID
set, or a table keyed by a unique tuple) normalized to one canonical order *before* it reaches
`_canonical_json`.

**Audit finding: the original implementation only did (a), not (b), and was mislabeled.**
`covered_clause_ids`, `excluded_clause_ids`, `acceptable_evidence_categories`, and
`remedy_table` were stored in raw submission order. Two constitutions with an identical
clause set or remedy table submitted in a different order would validate identically but
produce different stored list order (and, had `program_id`/`version` matched, a different
fingerprint) - not actually canonical, despite the name. This is now fixed, not just
relabeled: `_validate_clause_list` returns clause IDs lexicographically sorted;
`acceptable_evidence_categories` is deduplicated and sorted; `_validate_remedy_table` returns
rows sorted by `(outcome, clause_id, remedy_kind, remedy_value)`. `_canonical_json`'s
docstring was rewritten to state this precisely, including which fields are intentionally
*not* reordered (free text with meaningful order, e.g. `product_scope`, clause `text`).

**Confirmation for later stages:** because every array that matters for equality is now
canonicalized before storage, Stage 2+ code can compare two `fingerprint` values, or two
`json.loads(...)` results, with plain `==`, and never needs to re-parse or tolerate
reordering/whitespace differences in raw JSON text. `test_fingerprint_is_order_independent_
for_fixed_program_and_version` (new) proves this from first principles - it recomputes the
expected fingerprint independently using stdlib `json`/`hashlib` only (no CLAUSE helper
functions), confirming the on-chain value matches exactly.

**New hardening tightened beyond pure canonicalization**, all in the same audit pass since
they were adjacent gaps found while reading the two validators: exact-key-set enforcement
(rejects missing or unexpected keys in clause/remedy rows, previously silently tolerated via
`.get()` with defaults), non-empty requirements for `covered_clauses`/`remedy_table`/
`acceptable_evidence_categories` (a warranty covering nothing, or with no remedy definitions,
was previously accepted), a wrong-clause-kind guard (a `COVERED` remedy row can no longer cite
an `X-*` clause and vice versa; the four procedural outcomes must be outcome-level), a
duplicate-`(outcome, clause_id)`-pair guard, and finite size caps (`_MAX_CLAUSES_PER_KIND=50`,
`_MAX_REMEDY_ROWS=50`, `_MAX_EVIDENCE_CATEGORIES=20`, `_MAX_SHORT_LEN=200`,
`_MAX_TEXT_LEN=4000`) to bound storage growth from a single write.

New file `tests/direct/test_canonical_json_hardening.py` (33 tests) covers: malformed
top-level types, wrong element types, missing/unexpected keys, forbidden duplicates (evidence
category, remedy `(outcome, clause_id)` pair), nonexistent clause references, wrong-clause-kind
(both directions plus procedural-outcome-with-clause_id), empty required collections (and the
one deliberately-still-optional exception, `excluded_clauses`), negative/non-integer/bool
numeric values, oversized input (count and length caps), and four order-independence /
canonical-representation tests (clause order, evidence-category order, dict key order, and the
from-first-principles fingerprint recomputation).

**Security/behavior impact of the fix:** none of this weakens anything - it only makes
previously-accepted-but-under-specified inputs either rejected (stricter validation) or
normalized (order-independent storage). No previously-rejected input is now accepted.

### Item 3 — Independent verification of the u32 decision

An isolated, temporary two-file experiment was created **outside the CLAUSE repository**
(under the session scratchpad, never touching `contracts/clause_protocol.py`): two minimal
single-method contracts, `TreeMapKeyProbeU64` (a `TreeMap[u64, str]` field) and
`TreeMapKeyProbeU32` (a `TreeMap[u32, str]` field), otherwise byte-identical. Both were run
through the same two `genvm-lint` subcommands used to gate Stage 1.

**Exact results:**

```
$ genvm-lint validate probe_u64_key.py
✓ Validation passed  (Contract: TreeMapKeyProbeU64, Methods: 2)

$ genvm-lint validate probe_u32_key.py
✓ Validation passed  (Contract: TreeMapKeyProbeU32, Methods: 2)

$ genvm-lint lint probe_u64_key.py
✗ Lint failed
  line 7: TreeMap key for 'data' must be Comparable (str, Address, u32, etc.), got 'u64'

$ genvm-lint lint probe_u32_key.py
✓ Lint passed (3 checks)
```

**Correction to the original Stage 1 report:** §9 item 1 and §10 Deviation #1 both stated that
`genvm-lint validate` rejects `u64` TreeMap keys. That is **incorrect** and is corrected here
by this independent probe: `validate` passes a `u64`-keyed `TreeMap` without complaint on both
probes. It is specifically `genvm-lint lint` that performs the Comparable-key check and
rejects `u64` (accepting `u32`). The original Stage 1 pass happened to run `lint` before
`validate` and attributed the failure to the wrong subcommand when summarizing; the underlying
engineering decision (use `u32` for entity IDs) was correct and remains unchanged, but the
attribution in the written record was wrong until this correction. §9 and §10 of this document
are left as originally written, with this note as the authoritative correction, rather than
silently edited, per the instruction not to silently change prior findings.

### Item 4 — Timestamp trust boundary audit

New file `tests/direct/test_timestamp_trust_boundary.py` (7 tests). Confirmed: every
protocol-controlled timestamp field (`WarrantyProgram.created_at`, `WarrantyConstitution.
frozen_at`, `WarrantyPassport.registered_at`, `Reservation.created_at`/`released_at`) is
written exclusively via `_now()`, which reads only `gl.message_raw["datetime"]` - confirmed
schema-side by `test_no_write_method_accepts_a_protocol_timestamp_parameter`, which derives
the complete write-method parameter list from `genvm-lint schema --json` and asserts none of
them contain a parameter named anything timestamp-shaped (`registered_at`, `created_at`,
`frozen_at`, `released_at`, `now`, `datetime`, `timestamp`). There is structurally no argument
through which a caller could set or override any of these fields.

`coverage_start`/`coverage_end` are the one deliberate, documented exception: manufacturer-
asserted warranty terms, not protocol timestamps, per the nine-timestamp taxonomy in
`docs/ARCHITECTURE.md`/`docs/DATA_MODEL.md`. `test_registered_at_is_independent_of_caller_
supplied_coverage_dates` proves the two are never conflated - a warranty issued with a
coverage window 50 years in the future still records `registered_at` as the actual current
protocol time, not anything derived from the caller-supplied window.
`test_registered_at_matches_protocol_time_exactly`, `test_frozen_at_matches_protocol_time_at_
the_freeze_moment`, `test_program_created_at_matches_protocol_time`, and
`test_reservation_created_and_released_at_match_protocol_time` each pin a warped protocol time
and confirm the stored field equals it exactly (not merely "close to" or "after").
`test_now_is_read_live_not_cached_across_calls` confirms `_now()` is re-read on every call
rather than cached from deploy time.

**Caveat, stated plainly:** `direct_vm.warp()` is the gltest-direct harness's way of
*simulating* the GenVM runtime's control over `gl.message_raw["datetime"]` for test purposes.
It is not equivalent to a caller-facing lever - no public method parameter maps to it (per the
schema-derived test above) - but the simulation itself is only as trustworthy as the harness;
final confirmation that a real GenVM/Studio caller has no way to influence this field remains
a live-network verification item, not something direct-mode testing can close on its own (same
category of caveat as the native-GEN-custody items already listed in §11).

### Optional cleanup performed

`dataclasses.field` (unused import), `_PROGRAM_STATUSES`, and `_CLAUSE_KINDS` (both unused
module-level tuples) removed. Confirmed unused by grep before removal; no behavior change;
`genvm-lint lint`/`validate`/`schema`/`typecheck` results are identical before and after
(same method count, same 23 informational typecheck notices).

### Hardening pass test/lint results

- `genvm-lint lint`: ✓ Lint passed (3 checks) - unchanged.
- `genvm-lint validate`: ✓ Validation passed - Contract: ClauseProtocol, Methods: 19 (9 view,
  10 write) - unchanged.
- `genvm-lint schema`: identical 19-method inventory - unchanged.
- `genvm-lint typecheck`: 0 errors, 0 warnings, same 23 informational
  `reportOptionalMemberAccess` notices (line numbers shifted by the docstring/validator
  insertions, substance unchanged) - unchanged in kind.
- Full suite: **116 passed, 0 failed, 0 skipped** (72 original + 33
  `test_canonical_json_hardening.py` + 4 `test_constitution_hardening.py` + 7
  `test_timestamp_trust_boundary.py`).

### Files changed in this hardening pass

- `contracts/clause_protocol.py` — canonical-JSON documentation/implementation, stricter
  `_validate_clause_list`/`_validate_remedy_table` (exact key sets, wrong-clause-kind guard,
  duplicate-pair guard, non-empty requirements, size caps), evidence-category
  validation/canonicalization in `create_constitution`, removed unused `field` import and two
  unused constant tuples.
- `tests/direct/test_constitution_hardening.py` (new).
- `tests/direct/test_canonical_json_hardening.py` (new).
- `tests/direct/test_timestamp_trust_boundary.py` (new).
- `STAGE_1_VERIFICATION.md` (this addendum).

Temporary probe files (`probe_u64_key.py`, `probe_u32_key.py`) were created and run outside
the repository (session scratchpad) and are not part of this commit, per the instruction not
to alter the production contract to perform the u32 check.

## 16. Required statement

**No deployment was performed and no user wallet/private key was used.**
