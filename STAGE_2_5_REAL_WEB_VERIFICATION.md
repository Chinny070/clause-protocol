# CLAUSE — Stage 2.5 Real-Web Verification (official local simulator, no mocks)

## 1. Verdict

**PASS WITH BLOCKERS.**

Closed: the real `gl.nondet.web.get` path, end to end, through the official local GenLayer
simulator with **no mocks** — deploy → setup → claim → dispute → evidence → real HTTPS
retrieval by leader *and* five independently-fetching validators → consensus → committed
freeze → authoritative reread → independent fingerprint match → real 404 handling →
post-freeze immutability. Also closed: the empirical `Response` field question.

Not closed (become explicit **StudioNet release gates**, §12): (a) genuine `render(mode="text")`
verification — glsim cannot perform browser rendering; (b) "failed/undetermined consensus
leaves no frozen state" — glsim demonstrably does not model that rollback faithfully.

One real contract bug was found by this exercise and fixed (§11).

## 2. Environment and versions

| Item | Value |
|---|---|
| Runtime | `glsim` — GenLayer's official lightweight local network simulator, bundled with `genlayer-test` |
| `genlayer-test` (ships glsim, gltest) | 0.29.2 |
| `genlayer-py` | 0.16.3 |
| GenVM Python SDK (pinned runner) | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`, SDK cache dir `v0.3.0-rc7` |
| `genvm-lint` | 0.11.1rc2 |
| Python / OS | 3.12.10 / Windows 11 |
| Chain ID reported by glsim | `0xeec7` = 61127 (documented Localnet ID) |
| Validators | 5, `--no-browser` (httpx for web access; Playwright is **not** installed) |
| Accounts | gltest's built-in dev accounts (ephemeral, local-only). No user wallet, no private key of the user's, no StudioNet. |

## 3. Exact commands

```bash
# one real-runtime test, on a FRESH simulator process (see §10 for why)
scripts/run_real_web.sh tests/integration/test_response_probe.py
scripts/run_real_web.sh tests/integration/test_real_web_lifecycle.py
scripts/run_real_web.sh tests/integration/test_real_web_undetermined.py

# default (direct-mode) suite; integration tests are excluded via norecursedirs
PYTHONIOENCODING=utf-8 python -m pytest tests/ -q
```

`scripts/run_real_web.sh` kills any simulator on :4000, starts
`python scripts/glsim_with_msg_value.py --port 4000 --validators 5 --no-browser -v`, waits for
`eth_chainId`, runs the pytest target, and kills the simulator again.
`scripts/glsim_with_msg_value.py` is stock glsim plus **one labelled shim** (§10.1) and one
**diagnostic-only** logging wrapper (§10.4).

## 4. Public URLs used

| URL | Why | Expected |
|---|---|---|
| `https://example.org/` | IANA-maintained static reference page; byte-stable (verified: identical MD5 across repeated requests) | 200, 559 bytes, "Example Domain" |
| `https://example.org/stage25-missing-page` | Same host, nonexistent path | 404 (real) |
| `https://not-allowed.example/page` | Not in the constitution's source policy | Recorded `INELIGIBLE`, never fetched |
| `https://httpbin.org/uuid` | Returns a different UUID on every request — a genuinely volatile source | Validators must disagree |

The constitution's `source_eligibility_policy` was `example.org` (and `example.org,httpbin.org`
for the volatile-source test).

## 5. Setup data (all through normal contract preconditions — nothing bypassed)

manufacturer = gltest account 0, holder = account 1 → `create_program("Acme Real-Web Fixture")`
→ `create_constitution` (covered clause `C-001`, exclusion `X-001`, categories
`["RECEIPT","PAGE_RENDERED"]`, policy `example.org`) → `fund_pool` 3×10¹⁵ atto (real payable
call, see §10.1) → `issue_warranty` (max remedy 10¹⁵, coverage `now`…`now+1y`) → holder
`file_claim` → manufacturer `respond_to_claim("DISPUTE")` → holder `submit_evidence` ×3.
Contract address (this run): `0x00dd556e9b80d039bdd9c6f3f268b76a0d9f2005`.

## 6. Response API — what the real runtime actually returns

Recorded in `docs/STAGE_2_5_RESPONSE_PROBE.json` (a probe contract run through the same
simulator; tx `…02` FINALIZED, 5/5 `agree`, leader `SUCCESS`):

| Question | Observed |
|---|---|
| Response type | `Response` from module `genlayer.gl.nondet.web` |
| Public attributes | exactly `body`, `headers`, `status` |
| `.status` present? | **Yes** — value `200`, type `int` |
| `.status_code` present? | **No** (`hasattr` → `False`) |
| Body | `bytes`, 559 bytes; decoded HTML "Example Domain" |
| Headers | dict, 12 entries |

This **empirically confirms the installed SDK source and refutes the docs prose**
(`.status_code`). CLAUSE's `response.status` is correct; no compatibility shim was added.

Additional empirical fact: a swallowed `AttributeError` in `_fetch_evidence_once` would have
silently become `UNAVAILABLE`. The real run shows `AVAILABLE` for a 200 and `FETCH_FAILED`
for a 404, which is only possible if `response.status` evaluated as an `int` — corroborating
the probe from the contract's own behaviour.

## 7. GET result (real, end to end)

`freeze_evidence` tx `0x…0b`: `status_name = FINALIZED`, votes
`{v0..v4: "agree"}` (5/5), leader `execution_result = SUCCESS`. Because glsim re-runs each
validator's `validator_fn` — which performs its **own** live `gl.nondet.web.get` — this is five
independent real retrievals agreeing with the leader's, not one. Zero `[diag]` disagreement
lines were logged in the passing run.

## 8. Authoritative EvidenceRecord reread

Read via `read_contract` (view calls), after the freeze tx finalized:

| Field | Evidence #1 (static) | Evidence #2 (real 404) | Evidence #3 (disallowed host) |
|---|---|---|---|
| claim_id / evidence_id | 1 / 1 | 1 / 2 | 1 / 3 |
| original_url | `https://example.org/` | `https://example.org/stage25-missing-page` | `https://not-allowed.example/page` |
| category / retrieval_method | `RECEIPT` / `GET` | `RECEIPT` / `GET` | `RECEIPT` / `GET` |
| eligibility | `ELIGIBLE` | `ELIGIBLE` | `INELIGIBLE` |
| retrieval_status / available | `AVAILABLE` / `true` | `FETCH_FAILED` / `false` | `""` / `false` |
| retrieved_at = frozen_at | 1790227022 | 1790227022 | 0 / 0 (never processed) |
| extracted_content | 558 chars, raw HTML of the page (≤ 2000 cap) | `""` | `""` |
| fingerprint | `020beabe…96321f` | `81dcb2e1…c4f` | `""` |

Claim after freeze: `status = EVIDENCE_FROZEN`, `evidence_frozen_at = 1790227022`. The claim
record contains no outcome/verdict field of any kind.

**Observation worth recording:** stored content for a GET of an HTML page is the raw HTML
(stripped and truncated to 2000 chars), because Stage 2 deliberately does no HTML extraction
(§8 of `STAGE_2_VERIFICATION.md`). It is bounded and inert, but not "readable text". Whether
Stage 3 needs a cleaner representation is a Stage 3 design question, not a Stage 2 defect.

## 9. Independent fingerprint

Recomputed **outside the contract** (`tests/integration/test_real_web_lifecycle.py::fingerprint`)
using only stdlib `json` + `hashlib`, from the values read back from chain:

`sha256(json.dumps({evidence_id, claim_id, original_url, category, retrieval_status, content},
sort_keys=True, separators=(",", ":")))`

Result: **equal to the stored fingerprint for evidence #1 and #2** (`020beabe…` and
`81dcb2e1…`) and for the glsim-emulated render-path record (§12). Asserted in the test, not eyeballed.

## 10. Immutability, failure path, consensus

**Immutability (real runtime):** after the freeze, tx `0c` (`freeze_evidence` again) and tx `0d`
(`submit_evidence` after freeze) both finalized with leader `execution_result = ERROR`
(`UserError: claim is not in a state ready for evidence freeze` / `…accepts evidence`). Rereading
the claim and all three evidence records afterward returned values **identical** to the
pre-attempt reads.

**Unavailable ≠ NOT_COVERED:** the real 404 became `retrieval_status = FETCH_FAILED`,
`available = false`, empty content, its own fingerprint. The claim stayed `EVIDENCE_FROZEN`
with no outcome. Nothing in Stage 2 can produce `NOT_COVERED`.

**Consensus verified, not assumed:** for every one of the 17 transactions the test asserts
`status_name == FINALIZED`, all five votes `agree`, and the leader's `execution_result` is the
expected `SUCCESS`/`ERROR` — then confirms the effect with an authoritative view read. A tx
hash or an RPC success was never treated as proof.

**Failed/undetermined consensus — NOT verified (blocker).** Using `httpbin.org/uuid`, all five
validators **correctly disagreed** (logged `[diag] validator 0…4 … returned False`, each with a
different UUID than the leader's) — so CLAUSE's equivalence logic rejects unstable content as
designed. But glsim's rotation logic then failed to undo the rejected leader's storage writes:
the retry saw leaked state (`claim is not in a state ready…`, a deterministic error, all
validators trivially agree) and the transaction **finalized with the rejected leader's evidence
committed** (`EVIDENCE_FROZEN`, `AVAILABLE`, content = the leader's rejected UUID). This is a
simulator-fidelity limitation (probable mechanism, *not* confirmed by me: `restore_snapshot`
replaces `engine._storages` but the live contract instance keeps its reference to the mutated
storage). On real GenVM a rejected leader result is never committed, and the contract cannot
defend against a simulator that commits it. It is recorded as
`test_real_web_undetermined.py`, marked `xfail(strict=True)` so it is reproducible and fails
loudly the day the simulator is fixed. **Do not read this as "undetermined rollback works".**

## 11. Bugs discovered and fixes

1. **REAL CONTRACT BUG (fixed): late-binding closures in `freeze_evidence`.** `leader_fn` and
   `validator_fn` were defined inside the per-record loop and closed over the loop variables
   `url`/`method` by reference. A validator that runs after the loop finishes (as glsim's does)
   therefore re-fetched the **last** record's URL, disagreed with the leader on every earlier
   record, triggered a rotation, and — through the simulator issue above — produced a
   committed-but-error-reported transaction. `gltest-direct` never runs validators, so all 187
   direct-mode tests were blind to it. *Fix (smallest, within approved architecture, no
   redesign):* the per-record retrieval moved into module-level
   `_retrieve_via_consensus(url, method)`, which owns its own call scope and the
   `run_nondet_unsafe` call. (An intermediate factory-returning-closures version passed the new
   test but `genvm-lint` could not trace `gl.nondet.*` reachability through it; the final form
   passes lint.) *Regression test:* `tests/direct/test_stage2_validator_replay.py` replays
   every captured validator via `direct_vm.run_validator(index=i)`; **it failed before the fix
   (`validator #0 disagreed`) and passes after**. *Security/trust impact:* no exposure on a
   faithful runtime (cloudpickle snapshots closure values at call time), but the old code was
   incorrect under any replay-after-loop runtime; the fix removes the dependence on that
   subtlety. Fingerprint, state machine, eligibility, and storage layout are unchanged.
2. **Simulator: payable value not propagated (worked around in the launcher, contract
   untouched).** Stock glsim decodes the tx `value` but never sets `msg.value` when executing,
   so `gl.message.value` is 0 in every payable call. `fund_pool` therefore reverted
   (`send some GEN to fund the pool`) and issuance (which requires funded capacity) could not be
   reached legitimately. Fix: `scripts/glsim_with_msg_value.py` sets `vm.value` from the tx
   value around `call_from_calldata` and resets it to 0 afterward. Nothing else is patched;
   web, consensus, storage and execution are stock. *Trust impact:* the payable path was
   verified only **with** this shim; native-GEN custody remains an unverified-on-real-runtime
   item (already carried since Stage 0). It has no bearing on the web-evidence findings.
3. **Simulator: one contract load per process.** A second contract load in the same glsim
   process fails with `class is not marked for usage within storage, please, annotate it with
   @allow_storage`. Bisected: Stage 1 sources deploy fine; the full contract deploys fine on a
   fresh process and fails on the second load in the same process (reproduced 3×; also
   affects a byte-identical redeploy). Treated as simulator state pollution, **not** a contract
   defect; worked around by running each real scenario on a fresh process
   (`scripts/run_real_web.sh`). I did not root-cause the simulator internals.
4. **Test-authoring items:** `gltest` resolves contract paths relative to `contracts/`; its
   `Contract` wrapper exposes no methods against glsim (schema fetch unsupported), so the tests
   use `genlayer-py`'s `deploy_contract`/`write_contract`/`read_contract` directly.

## 12. RENDER — separate, and NOT verified

`gl.nondet.web.render(url, mode="text")` **was called through the real runtime** (probe tx
`…03`, and CLAUSE's `_RENDERED`-category path, claim 2, tx `…11`) and returned successfully,
FINALIZED, 5/5 agree. **It is not counted as verified**, because glsim does not implement
rendering: its `WebRender` handler ("Live handler fallback — do a GET, return body as text",
`gltest/direct/wasi_mock.py`) ignores `mode` and `wait_after_loaded` and returns the plain HTTP
body. Observed: the "rendered text" was the raw HTML `<!doctype html><html lang="en">…`, 559
chars — byte-identical to the `get` body. Playwright is not installed, and even with it glsim's
browser path is used for `GET`, not for `WebRender`. **Genuine render verification (a real
browser producing readable text, `wait_after_loaded`, JS-dependent pages) is a StudioNet
release gate.** The CLAUSE render-path record was nonetheless checked structurally
(`retrieval_method = RENDER`, fingerprint recomputes) — proving CLAUSE's plumbing, not GenVM's
renderer.

## 13. Remaining simulator/runtime limitations

1. `render` is emulated as `get` (§12).
2. Rotation after validator disagreement leaks the rejected leader's writes (§10) — the
   undetermined-rollback guarantee is unverifiable here.
3. `msg.value` not modelled without the shim; native-GEN custody unverified on a real runtime.
4. One contract load per simulator process.
5. Reverted transactions: glsim reports them as FINALIZED with a leader `ERROR`/`rollback`
   receipt (not as a distinct failed status); consumers must read `execution_result`, exactly
   as the Stage 0/1 docs already require.
6. `eq_outputs` is empty in receipts (glsim does not record equivalence-principle outputs), so
   per-validator votes cannot be attributed to a specific `run_nondet` inside a tx from the
   receipt alone; the `[diag]` log wrapper filled that gap for debugging.

## 14. Does StudioNet evidence verification remain a release gate?

**Yes — two items:** genuine `render(mode="text")` behaviour, and real
failed/undetermined-consensus rollback. GET, response fields, freeze commit, fingerprint,
immutability, and 404 handling are now verified on the official local runtime; a StudioNet pass
should re-run the same scenarios (the integration tests are runtime-agnostic apart from
`scripts/run_real_web.sh`) plus those two. StudioNet was **not** used and **no deployment** was
performed; stopping here for approval per the brief.

## 15. Files

New: `STAGE_2_5_REAL_WEB_VERIFICATION.md`; `docs/STAGE_2_5_RUN_LOG.json`,
`docs/STAGE_2_5_UNDETERMINED_LOG.json`, `docs/STAGE_2_5_RESPONSE_PROBE.json` (raw
observations); `scripts/run_real_web.sh`, `scripts/glsim_with_msg_value.py`;
`tests/integration/{rt.py,test_response_probe.py,test_real_web_lifecycle.py,
test_real_web_undetermined.py,probe_contracts/response_probe.py}`;
`tests/direct/test_stage2_validator_replay.py`.
Changed: `contracts/clause_protocol.py` (bug fix §11.1 only), `pyproject.toml`
(`norecursedirs = ["integration"]`), `.gitignore`, `docs/STAGE_2_WEB_API_VERIFICATION.md`
(empirical addendum), `STAGE_2_VERIFICATION.md` (closure addendum).

No Stage 1/2 architecture, storage layout, state machine, or fingerprint definition changed.

**No Stage 3 semantic adjudication was implemented.**

**No StudioNet deployment was performed and no user wallet/private key was used.**
