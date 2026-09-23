# CLAUSE — Evidence Architecture (Stage 0)

Mandatory pipeline (from both source documents, unchanged):

```
URL/reference -> source eligibility -> GenLayer validator retrieval/render -> bounded stable
extraction -> equivalence/semantic validation -> separate committed evidence-freeze transaction ->
adjudication
```

The frontend submits a URL and category metadata only. It never scrapes, never decides eligibility,
never extracts facts. All of that happens inside the Intelligent Contract via GenVM non-deterministic
blocks — confirmed as the only supported pattern in `NETWORK_AND_SDK_VERIFICATION.md`.

## Step 1 — Source eligibility (deterministic, no GenVM nondet needed)

A submitted URL is checked against the frozen `source_eligibility_policy` (host/path allowlist or
pattern, plus the declared `category` must be in `acceptable_evidence_categories`) before any network
call happens. This is plain deterministic Python — no leader/validator split required, since eligibility
is a pure function of the URL string and the frozen Constitution. Ineligible submissions are recorded
(`eligibility = INELIGIBLE`) but never reach retrieval. This is also the first prompt-injection
defense layer: an ineligible domain is rejected before its content is ever fetched or shown to an LLM.

## Step 2 — Retrieval (non-deterministic, inside the IC)

- Static/stable resources: `gl.nondet.web.get(url)`.
- JS-rendered pages needing readable text: `gl.nondet.web.render(url, mode=...)` — the exact mode
  literal for "readable text" must be re-confirmed against the installed package at Stage 2
  (`NETWORK_AND_SDK_VERIFICATION.md` open item 1); HTML mode (`mode='html'`) only when DOM structure is
  genuinely required by the extraction step.
- `gl.get_webpage` does not exist and must never be used or invented (confirmed absent from current
  docs, consistent with every other GenLayer project in this workspace).
- Fetched content is treated as **untrusted data**, never instructions — any text resembling directives
  to the model ("ignore previous instructions", "the warranty is approved") is inert data to be
  extracted from or ignored, never executed as a prompt.
- 404/timeout/render failure produces an explicit `retrieval_status` (see enum in `DATA_MODEL.md`:
  `AVAILABLE | UNAVAILABLE | INVALID_SOURCE | FETCH_FAILED | RENDER_FAILED | INSUFFICIENT |
  CONFLICTING`) — it never proves or disproves coverage by itself; it only feeds the Constitution's
  `unavailable_evidence_behavior`.

## Step 3 — Bounded stable extraction (the consensus artifact)

Per the Equivalence Principle page's explicit guidance ("Always extract before comparing... whatever
data the leader returns has to be stored on-chain"), retrieval and extraction happen in the *same*
non-deterministic block: fetch → LLM/deterministic extraction → return a small structured fact set. The
raw page body is never itself the thing compared or stored — only `extracted_facts` (a bounded JSON
string of stable fields relevant to the claim: e.g. product model mentioned, incident description,
dates present, any explicit coverage-relevant statement) is stored. `fingerprint` hashes
`extracted_facts`, not the volatile raw page, since re-fetching the same live URL later is expected to
differ from what was frozen.

## Step 4 — Equivalence / semantic validation of the extraction itself

This is a `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` block (the now-recommended default pattern,
per `NETWORK_AND_SDK_VERIFICATION.md`), not `strict_eq` over the raw page and not the higher-level
`prompt_comparative`/`prompt_non_comparative` convenience wrappers, since evidence extraction is neither
purely objective/canonicalizable nor a case where "the validator shouldn't produce a second answer."
Pattern, adapted from the two-tier design already proven in this workspace (Protocol Court Tier 1):

```python
def leader_fn():
    res = gl.nondet.web.get(url)  # or .render(...)
    if res.status_code >= 400:
        raise gl.vm.UserError(f"[EXTERNAL] fetch failed: {res.status_code}")
    facts = _extract_stable_facts(res.body)     # deterministic parse, or one exec_prompt call
    return facts                                 # small bounded dict, JSON-serializable

def validator_fn(leader_result):
    if not isinstance(leader_result, gl.vm.Return):
        return _handle_leader_error(leader_result, leader_fn)   # [EXPECTED]/[EXTERNAL]/[TRANSIENT] classes
    validator_facts = leader_fn()
    # compare only the fields the claim actually needs, never the whole raw body
    return _facts_materially_agree(leader_result.calldata, validator_facts)
```

`_facts_materially_agree` is a hand-written comparator, per-field (exact match on stable identifiers,
tolerance-free on booleans/enums extracted, no comparison at all on free-text commentary the extractor
might have added). This directly follows the docs' "Partial Field Matching" pattern and its explicit
warning against "leader-output-only validation" (a validator that only checks JSON shape/enum
membership without independently re-deriving the facts is insecure and is banned from this design).

Error classification follows the docs' named prefixes: `[EXPECTED]` (e.g. ineligible source — already
filtered in Step 1, but defensive), `[EXTERNAL]` (4xx/5xx), `[TRANSIENT]` (timeouts — both leader and
validator hitting `[TRANSIENT]` is treated as agreement, matching the docs' example, so a genuinely
flaky-but-real source doesn't force endless leader rotation), `[LLM_ERROR]` (always disagree, forces
retry).

## Step 5 — Evidence freeze (separate committed transaction)

`freeze_evidence` (see `STATE_MACHINES.md`) is its own transaction, never merged into `adjudicate`. This
is a repeated, hard-won lesson across every prior GenLayer project in this workspace (Treasury Trial,
Protocol Court): merging retrieval/extraction commitment with the adjudication step makes it impossible
to reason about "what evidence did the adjudicator actually see," and makes a failed adjudication
ambiguous about whether evidence or judgment failed. After freeze, `EvidenceRecord.extracted_facts` and
`.fingerprint` are immutable; `adjudicate` may only read frozen records for that claim.

## Provenance is explicit, not assumed

`EvidenceRecord.submitter` is always recorded. Claimant-authored evidence is not automatically
independent proof — the Constitution's `acceptable_evidence_categories` and `source_eligibility_policy`
are the only gate on what counts as authoritative; a claimant submitting their own blog post as evidence
is eligible or not purely by policy, and the UI must visibly distinguish holder-submitted vs
manufacturer-submitted vs (future) third-party-submitted evidence in the Evidence Locker view.

## After every consensus-critical write

Per the docs' Finality guidance (`NETWORK_AND_SDK_VERIFICATION.md`): after `freeze_evidence` or
`adjudicate` returns, the frontend must inspect the actual consensus/execution result (not just that a
tx hash was returned) and reread authoritative contract state before showing the user any new status —
an Accepted receipt can still contain a `UserError`, and only Finalized + a successful execution result
is trustworthy for UI purposes.

## Duplicate / oversized / disallowed sources

Duplicate `original_url` + `claim_id` submissions are allowed to exist (permissionless submission) but
`freeze_evidence` deduplicates by `fingerprint` when selecting which frozen records to cite, so a
resubmission of the identical source cannot inflate apparent corroboration. Oversized responses are
bounded at the extraction step (Step 3) — extraction never returns more than a small fixed set of
fields; the raw oversized body is discarded after extraction, never stored. Disallowed sources are
caught at Step 1 and never reach retrieval, which is also the primary defense against a URL crafted to
serve a resource-exhausting response.
