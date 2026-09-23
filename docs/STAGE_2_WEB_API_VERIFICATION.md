# CLAUSE — Stage 2 Web/Nondeterminism API Verification

Verified 2026-09-23 against two sources: (1) the live docs at docs.genlayer.com (same pass
used for Stage 0/1), and (2) the **installed Python SDK source** for CLAUSE's own pinned
runner, `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`, cached at
`~/.cache/gltest-direct/extracted/v0.3.0-rc7/py-lib-genlayer-std/.../genlayer/gl/nondet/web.py`
and `.../gl/vm.py`. Where the two disagreed, the installed source was treated as authoritative
(it is what actually executes) and the conflict is called out explicitly below, per the build
brief's "if official docs and installed APIs conflict, stop and report" instruction.

## CONFLICT FOUND AND RESOLVED: `Response.status`, not `Response.status_code`

**Docs prose** (Web Access feature page, and copied verbatim into
`docs/NETWORK_AND_SDK_VERIFICATION.md` at Stage 0) shows example code using
`response.status_code`. **The installed SDK source directly contradicts this:**

```python
@dataclasses.dataclass
class Response:
    status: int
    headers: dict[str, bytes]
    body: bytes | None
```

(`genlayer/gl/nondet/web.py`, both `get`/`post`/`request` return this exact dataclass). There
is no `status_code` attribute or property anywhere in this class. **Resolution: CLAUSE Stage 2
code uses `response.status`, verified directly against the installed source that will actually
execute under the pinned runner hash.** This corrects a Stage 0/1 documentation note that
speculated `.status_code` was the current truth based on docs prose alone — that note is left
in place in `docs/NETWORK_AND_SDK_VERIFICATION.md` with a pointer to this correction, per the
same "don't silently rewrite prior findings" practice used in the Stage 1 hardening pass.

## `gl.nondet.web.get` / `.request` / `.post` / `.head` / `.delete` / `.patch`

All are thin wrappers over one shared `request()`:

```python
def get(url: str, *, headers: dict[str, str | bytes] = {}) -> Response
def request(url: str, *, method: Literal['GET','POST','DELETE','HEAD','OPTIONS','PATCH'],
            body: str | bytes | None = None, headers: dict[str, str | bytes] = {}) -> Response
```

Called eagerly (no `.get()` needed) unless `.lazy(...)` is used explicitly — confirmed via the
`_lazy_api` decorator: the bare function name evaluates immediately and returns `Response`
directly; `.lazy(...)` returns a `Lazy[Response]` requiring `.get()`. CLAUSE Stage 2 never uses
`.lazy()` — all calls are eager, matching every official example.

`Response.body` is `bytes | None` — decode explicitly (`.decode('utf-8', errors='replace')`)
before treating as text; a `None` body (e.g. some error responses) must be handled, never
assumed present.

## `gl.nondet.web.render`

```python
def render(
    url: str,
    *,
    mode: Literal['html', 'text', 'screenshot'] = 'text',
    wait_after_loaded: str | None = None,
) -> str | Image
```

Confirmed exact mode literal set: **`'text'`, `'html'`, `'screenshot'`** — resolves Stage 0's
open item #1 (the docs examples only showed `'html'`/`'screenshot'`; the installed source
confirms `'text'` is real, is a valid literal, and is in fact the *default*). `'text'` and
`'html'` return `str`; `'screenshot'` returns a `genlayer.gl.nondet.Image` (raw bytes + a PIL
image) — CLAUSE Stage 2 never uses screenshot mode (no visual evidence in scope).

`wait_after_loaded` **is supported**, confirmed in source: an optional string like `"1000ms"`
or `"1s"`, defaulting to `"0ms"` if not passed (`wait_after_loaded or '0ms'` in the source).
Used only for genuinely JS-rendering-dependent pages, never as a default.

## `gl.vm.run_nondet_unsafe` / `gl.vm.run_nondet`

```python
def run_nondet_unsafe(leader_fn: Callable[[], T], validator_fn: Callable[[Result], bool], /) -> T
def run_nondet(leader_fn, validator_fn, /, *, compare_user_errors=..., compare_vm_errors=...) -> T
```

Both positional-only (`/`), both eager (return `T` directly, not `Lazy[T]`), confirmed
unchanged from Stage 1's verification. `run_nondet_unsafe` remains the documented default for
custom leader/validator patterns; `run_nondet` sandboxes the validator and auto-classifies its
errors. CLAUSE Stage 2's evidence-freeze equivalence check uses `run_nondet_unsafe`, consistent
with Stage 1's Adjudication-schema design already committed to this pattern.

`validator_fn` receives a `Result = Return[T] | VMError | UserError` — must `isinstance()`
check before accessing `.calldata`, exactly as documented at Stage 0.

## Transaction rollback / consensus-failure behavior

Confirmed unchanged from Stage 0/1: per the Finality docs, if the leader/validator majority
cannot agree, GenVM rotates to a different leader and retries; if consensus still cannot be
reached the transaction becomes `Undetermined` and does not modify contract state. This is a
protocol-level guarantee, not something Stage 2's own code needs to (or can) implement — the
whole write transaction, including every state mutation after the `run_nondet_unsafe` call, is
atomic with respect to that call's outcome.

**Direct-mode test-harness limitation, confirmed by reading the installed `gltest` package
source (not assumed):** `gltest.direct.loader._patch_run_nondet_for_direct_mode` monkeypatches
both `gl.vm.run_nondet` and `gl.vm.run_nondet_unsafe` to **always run only `leader_fn` and
apply its result unconditionally** — the harness "skips the leader/validator consensus"
entirely (its own docstring's words). `validator_fn` is captured (alongside the leader's
result) into `direct_vm._captured_validators`, replayable after the fact via
`direct_vm.run_validator(leader_result=..., leader_error=...)`, but **this replay never
retroactively undoes the state mutation the write method already performed** — the state
change happened unconditionally as soon as `leader_fn()` returned. This means:

- Stage 2's tests **can** prove a validator's comparison *logic* is sound (would return
  `False`/disagree given tampered or adversarial data), using `run_validator()`.
- Stage 2's tests **cannot** prove, in direct-mode, that a real validator disagreement
  actually prevents/rolls back the state write — that guarantee is GenVM-protocol-level and is
  outside what any local tool in this workspace can exercise (matches this workspace's
  standing, repeatedly-documented "native GEN custody / real consensus behavior is
  integration/live-test only" caveat carried since Stage 0).
- What direct-mode *can* prove about atomicity: if `leader_fn` itself raises (a genuine
  fetch/parse failure, not a disagreement), the exception propagates out of the write method
  before any subsequent state-mutating line executes — ordinary Python control flow, verified
  by a passing test (`test_leader_exception_leaves_no_partial_evidence_state`).

## `gl.message_raw["datetime"]`

Unchanged from Stage 1's verification (`_internal/msg.py`): an ISO datetime string, parsed
once via `_parse_iso_datetime`/`_now()`. No new findings this stage.

## Restrictions on web access during a write transaction

No explicit runtime guard against calling `gl.nondet.web.*` outside a `run_nondet_unsafe`/
`run_nondet`/`eq_principle.*` wrapper is visible in the Python SDK layer itself
(`gl_call_generic` just issues the raw `gl_call` and blocks on the resulting fd; it does not
inspect calling context). Any such restriction, if enforced, lives in the GenVM WASM runtime,
not in this Python wrapper, and is not independently verifiable from local tooling. **CLAUSE
treats "only call `gl.nondet.*` from inside a leader_fn/validator_fn passed to
run_nondet_unsafe" as a hard convention regardless** — every official example without
exception follows this pattern, and Stage 1's Adjudication design already committed to it; no
Stage 2 code calls `gl.nondet.web.*` bare in a write-method body.

## Summary of what changed since Stage 0/1's verification

| Item | Stage 0/1 status | Stage 2 finding |
|---|---|---|
| `Response.status` field name | Suspected `.status_code` (docs prose) | **Confirmed `.status`** (installed source) — corrected |
| `render` mode literals | Unconfirmed which literals exist | Confirmed: `'text'` (default), `'html'`, `'screenshot'` |
| `wait_after_loaded` | Not checked | Confirmed supported, optional, default `'0ms'` |
| `run_nondet_unsafe` signature | Confirmed | Unchanged, re-confirmed |
| Rollback/undetermined semantics | Confirmed (protocol-level) | Unchanged; direct-mode's inability to simulate it now explicitly documented with source citations |
| `gl.message_raw["datetime"]` | Confirmed | Unchanged |
| Nondet-context restriction | Assumed by convention | Still by convention; no SDK-level enforcement found |

No blocking documentation/installed-API conflict remains unresolved. The one conflict found
(`status` vs `status_code`) is resolved in favor of the installed source, which is what
actually executes.
