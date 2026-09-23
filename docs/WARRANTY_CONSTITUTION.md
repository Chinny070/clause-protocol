# CLAUSE — Warranty Constitution (Stage 0)

## What "immutable once issued" means precisely

A `WarrantyConstitution` is mutable (manufacturer can edit clauses, remedy table, deadlines, source
policy — anything) right up until the instant the **first** `WarrantyPassport` is issued against it
(`issue_warranty`, see `STATE_MACHINES.md`). At that exact transaction, `is_frozen` flips to `True` and
every subsequent write attempt against that `constitution_id` must revert. A manufacturer who wants
different terms creates a **new** Constitution under the same Program and repoints
`WarrantyProgram.active_constitution_id` at it — existing Passports keep citing their own frozen
`constitution_id`, never the Program's current one. This is the mechanism behind "terms-change/
correction policy": correction is versioning forward, never rewriting backward.

## Frozen fields (see `DATA_MODEL.md` for exact types)

Product/program scope; coverage calculation method; covered clauses (`C-*`) and exclusions (`X-*`);
acceptable evidence categories; source eligibility/authority rules; authoritative manufacturer terms
host/path/URL policy; claim deadline; manufacturer response period; adjudication trigger (permissionless
`adjudicate` once EVIDENCE_FROZEN); challenge window and allowed grounds; challenge depth;
insufficient/unavailable-evidence behavior; expiry/cancellation rules; deterministic remedy table;
terms-change/correction policy (i.e., which future Constitution, if any, a Program is allowed to
auto-migrate open — never applicable — issued Passports to; V1 answer is **none**, migration is
prospective-only).

## Fingerprint and anti-rewrite protection

`fingerprint: bytes` is a content hash of the full frozen rule set (all fields above, deterministically
serialized — canonical JSON with `sort_keys=True`, matching the `strict_eq` canonicalization pattern
confirmed in `NETWORK_AND_SDK_VERIFICATION.md`). The `WarrantyPassport` copies this fingerprint and the
`source_policy_snapshot` at registration. The frontend's "terms drift" indicator (Anti-rewrite section,
`ARCHITECTURE.md`) is computed by re-fetching the manufacturer's current public terms page (a read-only,
non-consensus-critical diagnostic call, or — if it needs to be trustworthy for a dispute — a genuine
`gl.nondet.web.get` call inside a view-adjacent write, itself subject to the same evidence-eligibility
rules as any other evidence) and comparing against the frozen fingerprint. Drift detection is advisory
UI only; it never mutates the frozen Constitution and is never itself admissible evidence unless
independently submitted and frozen through the normal Evidence Architecture pipeline.

## Insufficient/unavailable-evidence behavior is a per-Constitution choice, not a global default

Two Constitution fields — `insufficient_evidence_behavior` and `unavailable_evidence_behavior` — are
enums the manufacturer picks at authoring time (e.g. `RULE_FOR_HOLDER`, `RULE_FOR_MANUFACTURER`, or the
literal `INSUFFICIENT_EVIDENCE`/`EVIDENCE_UNAVAILABLE` claim states). CLAUSE's own contract code never
hardcodes "what happens when evidence is missing" — it always reads the frozen field. This directly
implements the design spec's rule that "silence follows only the precommitted constitution rule; it must
not invent an unstated default," extended from manufacturer silence to evidence gaps generally.

## Expiry/cancellation and remand are narrow by construction

`expiry_cancellation_rules` is a frozen string description in Stage 0 (exact structured shape — e.g.
grace periods, holder-initiated vs automatic — is a Stage 1 decision) but its *effects* are constrained
now: cancellation can only ever release a Reservation and close a Passport, never touch a Claim already
FILED. `challenge_depth` bounds remand recursion (see `STATE_MACHINES.md`) — a Constitution cannot
specify unbounded remand; Stage 1 should validate `challenge_depth <= 1` for V1 issuance and treat a
higher value as a future-extension field that reverts until the corresponding remand logic exists.

## Versioning is explicit, not inferred

`WarrantyConstitution.version: str` is manufacturer-supplied (e.g. semantic-ish "2026.1"), never derived
from `constitution_id` alone, so a manufacturer's own release naming survives on-chain and in the
Explorer/Passport UI (`FRONTEND_INFORMATION_ARCHITECTURE.md`). `version` and `constitution_id` must
always agree 1:1 (Stage 1 test: no two `constitution_id`s share a `(program_id, version)` pair).
