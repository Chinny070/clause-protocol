# CLAUSE — Data Model (Stage 0)

Storage-compatible shapes for a single Intelligent Contract, per the verified type rules in
`NETWORK_AND_SDK_VERIFICATION.md`: `DynArray[T]` not `list`, `TreeMap[K,V]` not `dict`, sized ints
(`u32`/`u64`/`u256`) not `int`, `@allow_storage @dataclass` for nested structs, storage is
zero-initialized so every enum needs an explicit "unset" member that is never a valid terminal value.

## WarrantyProgram

```
@allow_storage @dataclass
class WarrantyProgram:
    program_id: u64
    manufacturer: Address
    name: str
    active_constitution_id: u64          # points at the currently issuable Constitution
    pool_id: u64
    created_at: u64                      # on-chain timestamp
    status: str                          # ACTIVE | PAUSED | RETIRED
```

`active_constitution_id` can be repointed by the manufacturer to a *new* Constitution for future
issuances (`terms-change/correction policy`) — this never touches Constitutions already bound to issued
Passports (see Anti-rewrite, `ARCHITECTURE.md`).

## WarrantyConstitution (immutable once referenced by an issued Passport)

```
@allow_storage @dataclass
class WarrantyConstitution:
    constitution_id: u64
    program_id: u64
    version: str
    fingerprint: bytes                        # content hash of the frozen rule set below
    product_scope: str
    coverage_calc: str                        # deterministic description, not free text at runtime
    covered_clause_ids: DynArray[str]          # "C-*"
    excluded_clause_ids: DynArray[str]         # "X-*"
    acceptable_evidence_categories: DynArray[str]
    source_eligibility_policy: str             # authoritative host/path/URL rules, serialized
    claim_deadline_s: u64                      # relative to coverage window or failure date, defined below
    manufacturer_response_period_s: u64
    challenge_window_s: u64
    challenge_depth: u32                       # max challenge rounds, V1 = 1
    insufficient_evidence_behavior: str        # e.g. INSUFFICIENT_EVIDENCE | RULE_FOR_HOLDER | RULE_FOR_MANUFACTURER
    unavailable_evidence_behavior: str
    expiry_cancellation_rules: str
    remedy_table: DynArray[RemedyRow]          # deterministic; see below
    frozen_at: u64
    is_frozen: bool                            # true once any Passport references it; enforced in code
```

```
@allow_storage @dataclass
class Clause:
    clause_id: str                # "C-001" or "X-001"
    constitution_id: u64
    kind: str                     # COVERED | EXCLUDED
    text: str
```

```
@allow_storage @dataclass
class RemedyRow:
    outcome: str                  # matches Adjudication.outcome
    clause_id: str                # which covered clause this row prices, "" if outcome-level
    remedy_kind: str              # FULL_REFUND | REPAIR_CREDIT | PARTIAL_BPS | NONE
    remedy_value: u256            # atoms, or basis points if remedy_kind == PARTIAL_BPS
```

Enforcement rule: any write path that would mutate a `WarrantyConstitution` with `is_frozen == True`
must revert. `is_frozen` flips to `True` inside `issue_warranty`, in the same transaction that creates
the first `WarrantyPassport` against it — never as a separate step a manufacturer could skip.

## WarrantyPassport

```
@allow_storage @dataclass
class WarrantyPassport:
    warranty_id: u64
    program_id: u64
    manufacturer: Address
    holder: Address
    product_model_id: str
    product_commitment: bytes             # hash of serial/product identity; raw serial never stored on-chain
    registered_at: u64                    # on-chain timestamp, authoritative
    coverage_start: u64                   # asserted, distinct from registered_at
    coverage_end: u64
    constitution_id: u64
    constitution_version: str             # denormalized for cheap display; constitution_id is authoritative
    constitution_fingerprint: bytes       # frozen at registration, anti-rewrite anchor
    source_policy_snapshot: str           # frozen authoritative-source rules at registration time
    max_deterministic_remedy: u256
    pool_id: u64
    reservation_id: u64                   # links to the WarrantyPool reservation backing this warranty
    status: str                           # ACTIVE | EXPIRED | CANCELLED
```

`product_commitment` is a privacy-preserving commitment (hash of serial + salt), never the raw serial —
per the spec's privacy-preserving requirement. The salt is held off-chain by the holder; CLAUSE never
needs to reveal it, only to let a holder prove match during a claim by resubmitting serial+salt for
re-hashing client-side before a claim references it.

## WarrantyPool

```
@allow_storage @dataclass
class WarrantyPool:
    pool_id: u64
    manufacturer: Address
    total_balance: u256
    reserved_liability: u256      # sum of active reservations
    pending_locks: u256           # sum of amounts locked against open Claims (subset of reserved_liability)
    available_balance: u256       # invariant: total_balance - reserved_liability, checked every mutation
```

```
@allow_storage @dataclass
class Reservation:
    reservation_id: u64
    pool_id: u64
    warranty_id: u64
    amount: u256                  # == max_deterministic_remedy at issuance
    status: str                   # ACTIVE | RELEASED | CONSUMED
    created_at: u64
    released_at: u64
```

Full accounting rules and the conservation proof are in `ECONOMIC_INVARIANTS.md`.

## Claim

```
@allow_storage @dataclass
class Claim:
    claim_id: u64
    warranty_id: u64
    filed_by: Address
    filed_at: u64
    failure_asserted_at: u64          # claimant assertion, NOT authoritative
    description: str
    status: str                       # see STATE_MACHINES.md for the full enum + transitions
    response_deadline: u64
    manufacturer_response: str        # "" | ACCEPT_NO_CONTEST | DISPUTE
    dispute_clause_ids: DynArray[str] # clauses the manufacturer disputes under, if DISPUTE
    evidence_ids: DynArray[u64]
    evidence_frozen_at: u64           # 0 until the separate freeze transaction runs
    adjudication_id: u64              # 0 until adjudicated
    challenge_ids: DynArray[u64]
    final_outcome: str                # "" until FINAL
    settlement_amount: u256
    settled_at: u64
    withdrawn_at: u64
```

## EvidenceRecord

```
@allow_storage @dataclass
class EvidenceRecord:
    evidence_id: u64
    claim_id: u64
    submitter: Address
    original_url: str
    category: str                     # must be in the Constitution's acceptable_evidence_categories
    source_metadata: str              # host, retrieval method, declared content-type
    submitted_at: u64
    eligibility: str                  # PENDING | ELIGIBLE | INELIGIBLE
    retrieval_status: str             # AVAILABLE | UNAVAILABLE | INVALID_SOURCE | FETCH_FAILED | RENDER_FAILED | INSUFFICIENT | CONFLICTING
    retrieved_at: u64
    frozen_at: u64                    # 0 until frozen; immutable fields below are only trustworthy after this
    extracted_facts: str              # bounded, stable JSON string — never the raw page body
    fingerprint: bytes                # hash of extracted_facts, not of the volatile raw page
    available: bool
```

Full retrieval/freeze pipeline and equivalence strategy in `EVIDENCE_ARCHITECTURE.md`.

## Adjudication

Exact schema (validated, not just typed) is in `ADJUDICATION_SCHEMA.md`. Storage shape:

```
@allow_storage @dataclass
class Adjudication:
    adjudication_id: u64
    claim_id: u64
    constitution_id: u64             # denormalized, frozen reference
    adjudicated_at: u64
    product_match: str
    warranty_version_match: str
    coverage_window: str
    covered_clause_ids: DynArray[str]
    exclusion_clause_ids: DynArray[str]
    evidence_sufficiency: str
    source_authority: str
    evidence_ids_relied_on: DynArray[u64]
    outcome: str
    rationale: str
    superseded: bool                 # true if a later Challenge produced a corrected Adjudication
```

## Challenge

```
@allow_storage @dataclass
class Challenge:
    challenge_id: u64
    claim_id: u64
    adjudication_id: u64             # the specific Adjudication being challenged
    filed_by: Address
    filed_at: u64
    ground: str                      # one of the fixed V1 grounds, see APPEALS_AND_FINALITY.md
    citation: str                    # required specific evidence_id / clause_id reference
    argument: str
    result: str                      # "" | UPHELD | REVERSED | REMAND | INVALID_CHALLENGE
    resolved_at: u64
    corrected_adjudication_id: u64   # 0 unless result == REVERSED and a corrected Adjudication was created
```

## ResolutionReceipt

```
@allow_storage @dataclass
class ResolutionReceipt:
    receipt_id: u64
    claim_id: u64
    warranty_id: u64
    constitution_id: u64
    constitution_version: str
    relevant_clause_ids: DynArray[str]
    evidence_ids: DynArray[u64]
    filed_at: u64
    evidence_frozen_at: u64
    adjudicated_at: u64
    initial_outcome: str
    challenge_ids: DynArray[u64]
    final_outcome: str
    remedy_kind: str
    remedy_amount: u256
    finalized_at: u64
    settled_at: u64
    withdrawn_at: u64
    protocol_tx_refs: DynArray[str]   # GenLayer tx hashes for filing/freeze/adjudicate/challenge/settle
```

## Top-level contract storage

```
class Clause_(gl.Contract):
    programs: TreeMap[u64, WarrantyProgram]
    constitutions: TreeMap[u64, WarrantyConstitution]
    clauses: TreeMap[str, Clause]              # keyed by "constitution_id:clause_id" composite string
    passports: TreeMap[u64, WarrantyPassport]
    pools: TreeMap[u64, WarrantyPool]
    reservations: TreeMap[u64, Reservation]
    claims: TreeMap[u64, Claim]
    evidence: TreeMap[u64, EvidenceRecord]
    adjudications: TreeMap[u64, Adjudication]
    challenges: TreeMap[u64, Challenge]
    receipts: TreeMap[u64, ResolutionReceipt]
    next_*_id: u64   # one monotonic counter per entity type
```

(`Clause_` used here only to avoid colliding with the `Clause` struct name; the actual contract class name
is a Stage 1 decision, not frozen here.)
