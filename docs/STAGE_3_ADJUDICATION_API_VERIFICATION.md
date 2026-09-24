# CLAUSE — Stage 3 Adjudication API Verification

Verified 2026-09-24 from three sources: (1) the **installed SDK source** for the pinned runner
`py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (cache `v0.3.0-rc7`);
(2) docs.genlayer.com ("Calling LLMs", "Equivalence Principle" pages, read live); (3) the
installed `gltest` direct-mode harness and `glsim` 0.29.2 source. Where docs and installed code
differ, installed code is authoritative (it is what executes). No older project's prompt wrapper
was reused.

## 1. `gl.nondet.exec_prompt` (installed source: `genlayer/gl/nondet/__init__.py`)

```python
def exec_prompt(prompt: str, *, response_format: Literal['text','json'] = 'text', images=None) -> str | dict
```

Eager (returns the value directly; `.lazy()` exists but is unused). Decoded through
`_decode_nondet`, which raises `NondetException` if the runtime returns an `error`. With
`response_format="json"` the return type is `dict`. **CLAUSE uses `response_format="json"`**, as the
docs recommend, and then treats *any* non-`dict` return as malformed.

Docs-vs-installed notes:
- Docs examples raise `gl.UserError`. **The installed SDK does not export `gl.UserError`** (it is
  `gl.vm.UserError`); CLAUSE uses `gl.vm.UserError`. (Same stale-docs class as the Stage 2
  `status_code` finding.)
- Docs suggest "key aliasing" and "JSON cleanup" (strip fences, trailing commas, coerce numbers).
  **CLAUSE deliberately does none of it**: repairing model output is a policy decision that would
  let a hostile or sloppy model steer the result. The only normalization is sorting id lists.
- The docs' own caveat applies: `response_format="json"` "guarantees a valid JSON object, however
  correspondence to the specified format depends on the underlying LLM" — hence the strict checker.

## 2. `gl.vm.run_nondet_unsafe` / validator semantics (installed source: `genlayer/gl/vm.py`)

Unchanged from Stage 0/2: `run_nondet_unsafe(leader_fn, validator_fn, /) -> T`, positional-only,
eager. `validator_fn` receives `Result = Return[T] | VMError | UserError` and must return `bool`;
an exception inside it "counts as Disagree (same as returning False)". The docs' guidance for
LLM calls: *if the model returns garbage, the validator should disagree (return False) rather than
agree on broken output, forcing rotation.* CLAUSE's validator does exactly that.

## 3. Validator replay semantics (the Stage 2.5 lesson)

- **gltest-direct** patches `run_nondet`/`run_nondet_unsafe` to run **only the leader** and apply
  its result unconditionally; `validator_fn` is captured and can be replayed with
  `direct_vm.run_validator(index=…, leader_result=…, leader_error=…)`. Captured validators
  **accumulate across contract calls** (freeze and adjudication calls both append) — tests must
  `clear_validators()` before the call under test to make `index` meaningful.
- **glsim** (`glsim/consensus.py`) runs the leader once, then runs every captured
  `validator_fn` per validator against the leader's stored result; a majority of `agree` finalizes;
  disagreement snapshots-restores and rotates (see §5 for the fidelity problem).
- Consequence for Stage 3: closures are never defined in loops/method bodies; the whole
  leader/validator pair lives in module-level `_adjudicate_via_consensus(prompt, ctx)` (own call
  scope) and calls module-level `_model_call`. `genvm-lint` additionally **requires** the
  `gl.nondet.*` call to be a module-level function reachable from the equivalence block — a
  nested local helper fails lint ("not reachable from equivalence principle block").

## 4. Model-provider behaviour

- **Direct mode:** `direct_vm.mock_llm(regex, reply)`; matching is `re.search` over the prompt,
  first registered pattern wins, mocks accumulate (`clear_mocks()` between phases). **A reply that is
  a JSON *string* is auto-parsed into a `dict`** by the harness before it reaches contract code; a
  non-JSON string stays a `str`. So malformed-output tests reach the contract as `str`/`list`/`dict`
  exactly as a real provider's failure modes would surface them. All Stage 3 direct tests use this
  mock and therefore **prove contract-side behaviour only**, never model behaviour.
- **glsim:** the live LLM handler (`glsim/live_io.py::create_llm_handler`) supports only
  `openai:*` and `anthropic:*`, needs `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, and **converts any
  provider error into a plain successful-looking string** (`{"ok": "live_io LLM error: …"}`).
  This environment has no such key (and no local model), so **no real model route exists here**.
  Empirically confirmed (`docs/STAGE_3_RUN_LOG.json`): an `exec_prompt(..., response_format="json")`
  through glsim returned a non-dict, and CLAUSE rejected it (`[LLM_ERROR] model output is not a
  JSON object`) — i.e. the "not a dict ⇒ fail closed" rule is load-bearing, not theoretical.
  No credentials were sought or used.

## 5. Validator disagreement / rollback

Protocol-level (docs): disagreement ⇒ rotation; still no agreement ⇒ `Undetermined`, state
unchanged. **Not locally verifiable**: Stage 2.5 showed glsim's rotation does not undo the rejected
leader's storage writes. Stage 3 mitigates by structure, not by trusting rollback: `adjudicate_claim`
performs **no state write before the consensus block returns** (all reads → consensus → validated
result → then commits), so a rejected/failed leader has nothing to leak. The one residual gap is
the same protocol gate as before (real rollback = StudioNet).

## 6. Malformed model output handling

Fail closed, no repair (see `_check_model_result`): non-`dict`, wrong/extra/missing keys, invalid
or wrong-case enums, wrong types (incl. `bool` as int), duplicate ids, unknown/non-targeted/
wrong-kind clauses, unshown evidence ids, empty/whitespace/oversized (>1000) rationale, and
logical contradictions all raise `UserError("[LLM_ERROR] …")`. Provider exceptions become
`[LLM_ERROR] model call failed`. Rationale is **rejected**, never truncated.

## 7. `gl.message_raw["datetime"]`

Unchanged (ISO string → `_now()`); used for `adjudicated_at` and `challenge_window_closes_at`. The
claimant-asserted failure date is never used as a protocol timestamp.

## 8. Findings summary

| Item | Result |
|---|---|
| `exec_prompt` signature / json mode | as documented; return is `dict`; strict non-dict rejection needed |
| `gl.UserError` (docs) | **absent in installed SDK**; `gl.vm.UserError` used |
| docs "key aliasing / JSON cleanup" | intentionally **not** adopted (fail-closed policy) |
| validator replay | direct mode: leader-only + `run_validator`; captured validators accumulate |
| lint constraint | nondet calls must be module-level functions reachable from run_nondet_* |
| glsim model | no provider available; provider errors surface as **strings** |
| rollback on disagreement | unverifiable locally (Stage 2.5); mitigated by write-after-consensus |
