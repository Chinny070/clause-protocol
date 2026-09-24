# CLAUSE - Frontend Contract Interface (FROZEN for Stage 5)

**Status: frozen (Stage 4.5).** Stage 5 must build against this document, not against guesses about contract behaviour.
The section between the `GENERATED` markers is produced from `contracts/clause_protocol.py` by
`scripts/gen_frontend_interface.py` and is checked for drift by `tests/direct/test_stage45_interface_sync.py`; any change to the
public ABI must regenerate it and is, by definition, a contract-interface change requiring explicit approval.

Contract: `ClauseProtocol` (`contracts/clause_protocol.py`), single Intelligent Contract. Runner pinned in the contract header.

## 1. Encoding conventions

- Calldata: `u32`/`u64`/`u256` as integers; `str`; `list`; `dict` (only `file_challenge.citation`). `holder` (in `issue_warranty`) accepts a hex address.
  Amounts are in atoms (1 GEN = 10^18). `product_commitment_hex` is a 64-hex-char string.
- Reads return plain JSON-like dicts. Addresses are returned as `0x` hex strings (`as_hex`, checksummed - compare case-insensitively);
  hashes/fingerprints as lowercase hex (no `0x`); amounts as integers; booleans as booleans. **Unknown id -> `{}` (empty object), never an error.**
- All timestamps are Unix seconds from the protocol clock (`gl.message_raw["datetime"]`), **except `failure_asserted_at`, which is
  claimant-asserted and non-authoritative**. `now()` exposes protocol time.
- Ids are per-type counters starting at 1 (`program_id == pool_id`). `adjudication_id`/`challenge_id`/`evidence_id` are global counters, not per claim.
  `get_claim().adjudication_id == 0` means "not adjudicated yet".
- Write methods return `None` unless the generated section says otherwise (`create_*`, `issue_warranty`, `file_*`, `submit_evidence` return the new id;
  `adjudicate_claim` returns the adjudication id; `resolve_challenge` returns the result string; `execute_remand` returns the corrected adjudication id).

## 2. Who may call what

| Method | Caller |
|---|---|
| `create_program` | anyone (becomes the program's manufacturer) |
| `pause_program`, `resume_program`, `retire_program`, `create_constitution`, `withdraw_pool`, `issue_warranty` | the program's manufacturer |
| `fund_pool` (**payable**) | anyone (value must be > 0) |
| `cancel_warranty` | the warranty's holder or manufacturer |
| `release_expired_reservation` | anyone |
| `file_claim` | the warranty's holder |
| `respond_to_claim` | the claim's manufacturer |
| `submit_evidence`, `file_challenge` | the claim's holder or manufacturer |
| `freeze_evidence`, `adjudicate_claim`, `resolve_challenge`, `execute_remand`, `lapse_challenge`, `finalize_claim`, `settle_claim` | anyone (permissionless) |
| `withdraw_settlement` | the recorded recipient (the warranty holder) |

## 3. Claim lifecycle (stored `status`, as returned by `get_claim`)

```
RESPONSE_WINDOW --ACCEPT--> ACCEPTED ------------------------------------------------------------> FINAL
      |  (silence after response_deadline reads as DISPUTED)                                          ^
      +--DISPUTE--> DISPUTED --freeze_evidence--> EVIDENCE_FROZEN --adjudicate_claim--> DECIDED -----+ (no challenge, window closed, or challenge_depth == 0)
                                                                                          |           |
                                                                                 file_challenge       |
                                                                                          v           |
                                                                                     CHALLENGED --resolve/remand/lapse--> CHALLENGE_RESOLVED --+
FINAL --settle_claim--> SETTLED   (withdrawal is tracked on the final decision: withdrawn_at / claimable, not a claim status)
```
`get_claim().status` derives `DISPUTED` from `RESPONSE_WINDOW` once `now > response_deadline` with no response. Challenge sub-state lives on `get_challenge*`
(`OPEN`, `REMAND_PENDING`, `RESOLVED`). Prefer `get_resolution_receipt(claim_id)` for a single consistent read of everything below the claim.

## 4. Timing rules the UI must display exactly

| Rule | Definition |
|---|---|
| Claim deadline | `file_claim` allowed while `coverage_start <= now <= coverage_end + claim_deadline_s` (inclusive) |
| Response deadline | `respond_to_claim` allowed while `now <= response_deadline` (inclusive) |
| Challenge window | `adjudicated_at <= now <= challenge_window_closes_at` (inclusive), `closes = adjudicated_at + challenge_window_s`; not available when `challenge_depth == 0` |
| Challenge resolution period | resolve/remand allowed while `now <= filed_at + challenge_window_s`; `lapse_challenge` allowed once `now >` that |
| Finalize (DECIDED, no challenge) | requires `now > challenge_window_closes_at` (or `challenge_depth == 0`) |
| Reservation release (expired warranty) | requires `now > coverage_end + claim_deadline_s` AND every claim on the warranty `SETTLED`; a CANCELLED warranty needs only the second condition |

## 5. Protocol-finality checklist (the contract cannot enforce this - the frontend/operator must)

Before submitting each transaction, confirm via `gen_getTransactionStatus`/`gen_getTransactionLifecycle` that the transaction(s) producing the state it
depends on are **Finalized with a successful execution result** (not merely Accepted): `respond_to_claim` (no-contest) or `adjudicate_claim` /
`resolve_challenge` / `execute_remand` / `lapse_challenge` -> before `finalize_claim`; `finalize_claim` -> before `settle_claim`; `settle_claim` -> before
`withdraw_settlement`. After every write, re-read authoritative state (`get_claim`, `get_final_decision`, `get_resolution_receipt`); never trust a bare tx hash.
Application terminology: **Application Challenge** (CLAUSE) is distinct from **GenLayer Protocol Appeal/Finality** (the network).

## 6. Value flow the UI can show

`fund_pool` -> `pool.total_balance`. `issue_warranty` -> `pool.reserved_liability += max_deterministic_remedy` (reservation). `settle_claim` (payable) ->
`pool.total_balance -= x`, `pool.reserved_liability -= x`, `final_decision.claimable = x`. `withdraw_settlement` -> `claimable` -> 0, `withdrawn_amount = x`, transfer emitted.
`available_balance = total_balance - reserved_liability` (claimable funds are outside the pool). `Reservation.amount` = amount still reserved (passport keeps the original max).
`final_decision.capped == true` means the warranty's frozen maximum limited the payout (`settled_amount < remedy_amount`).

## 7. Values not covered by the constants below

- `adjudication.decision_path`: `DETERMINISTIC_PREDICATE`, `DETERMINISTIC_NO_ADMISSIBLE_EVIDENCE`, `DETERMINISTIC_EVIDENCE_UNAVAILABLE`, `SEMANTIC`, `CHALLENGE_CORRECTION`, `REMAND_CORRECTION`.
- `adjudication.evidence_sufficiency`: `SUFFICIENT`, `INSUFFICIENT`, `UNAVAILABLE`; `source_authority`: `PASS`, `UNCLEAR` (`FAIL` is reserved and unreachable).
- `challenge.resolution_path`: `""`, `DETERMINISTIC`, `SEMANTIC`, `REMAND_REVIEW`, `LAPSED`.
- `final_decision.source`: `NO_CONTEST`, `ADJUDICATION`, `ADJUDICATION_AFTER_CHALLENGE`, `CHALLENGE_CORRECTED`.
- `final_decision.remedy_basis`: `NO_CONTEST`, `COVERED`, `POLICY_RULE_FOR_HOLDER`, `POLICY_BLOCK`, `NON_PAYABLE`.
- `submitted_by` / evidence `retrieval_status` etc: see the enumerations below.

## 8. Errors

Every failure is a `gl.vm.UserError` with a plain-English message (the transaction's leader execution result is `ERROR`; state is unchanged). The generated section lists the
messages per write method. Semantic-step failures (`adjudicate_claim`, `freeze_evidence`, `resolve_challenge`, `execute_remand`) whose model output is unusable carry the prefix
`[LLM_ERROR]`; they are retryable and leave no partial state. A *revert is not a decision*: show it as "transaction failed", never as a claim outcome.

## 9. Frozen design decisions the UI must not contradict

- **Remedy-table completeness** (Stage 4.5): a constitution is rejected at creation unless an outcome-level `ACCEPTED_NO_CONTEST` row exists and every covered clause resolves to a
  `COVERED` row (clause-specific, or an outcome-level `COVERED` row). So no issued warranty can reach a payable final state without a remedy.
- **Challenge `corrections` representation** (Stage 4 deviation, audited and retained in Stage 4.5): see `STAGE_4_5_CONTRACT_FREEZE.md`.
- One Application Challenge per claim; one remand step; corrections are final and never challengeable.
- The warranty's `max_deterministic_remedy` is a lifetime cap across all its claims; settlement order decides who is capped.
- A manufacturer may cancel a warranty unilaterally while no claim is unsettled (documented V1 limitation).

## 10. Public read models Stage 5 should use

`get_program`, `list_program_ids`, `get_pool`, `get_constitution`, `get_clauses`, `get_passport`, `list_passport_ids`, `get_reservation`, `get_claim`,
`list_claim_ids_for_warranty`, `get_evidence`, `list_evidence_ids_for_claim`, `get_adjudication`, `get_challenge`, `get_challenge_for_claim`, `get_final_decision`,
**`get_resolution_receipt`** (the Resolution Receipt: warranty, claim, evidence ids+fingerprints, original adjudication, challenge, corrected adjudication, final decision), `now`.

## 11. Generated ABI inventory

<!-- BEGIN GENERATED -->
Method counts: **40 public methods = 18 view + 22 write** (1 payable: `fund_pool`).

### Write methods

#### `create_program(name: str) -> u32`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `program name must not be empty`

#### `pause_program(program_id: u32) -> None`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown program`
  - `caller is not this program's manufacturer`
  - `program is not ACTIVE`

#### `resume_program(program_id: u32) -> None`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown program`
  - `caller is not this program's manufacturer`
  - `program is not PAUSED`

#### `retire_program(program_id: u32) -> None`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown program`
  - `caller is not this program's manufacturer`
  - `program is already RETIRED`

#### `create_constitution(program_id: u32, version: str, product_scope: str, coverage_calc: str, covered_clauses: list, excluded_clauses: list, acceptable_evidence_categories: list, source_eligibility_policy: str, claim_deadline_s: u64, manufacturer_response_period_s: u64, challenge_window_s: u64, challenge_depth: u32, insufficient_evidence_behavior: str, unavailable_evidence_behavior: str, expiry_cancellation_rules: str, remedy_table: list) -> u32`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown program`
  - `caller is not this program's manufacturer`
  - `program is RETIRED`
  - `version must not be empty`
  - `challenge_depth exceeds V1 maximum of 1`
  - `duplicate clause_id across covered/excluded`
  - `acceptable_evidence_categories must be a list`
  - `at least one acceptable evidence category is required`
  - `too many evidence categories (max {...})`
  - `evidence category must be a non-empty string within length limits`
  - `duplicate evidence category`
  - `a constitution with this version already exists for this program`

#### `fund_pool(program_id: u32) -> None`
- kind: write.payable
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown program`
  - `unknown pool`
  - `send some GEN to fund the pool`

#### `withdraw_pool(program_id: u32, amount: u256) -> None`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown program`
  - `caller is not this program's manufacturer`
  - `unknown pool`
  - `amount must be greater than 0`
  - `amount exceeds available (unreserved) balance`
  - `accounting invariant violated`

#### `issue_warranty(program_id: u32, constitution_id: u32, holder: untyped, product_model_id: str, product_commitment_hex: str, coverage_start: u64, coverage_end: u64, max_deterministic_remedy: u256) -> u32`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown program`
  - `caller is not this program's manufacturer`
  - `unknown pool`
  - `program is not ACTIVE`
  - `unknown constitution`
  - `constitution does not belong to this program`
  - `product_model_id must not be empty`
  - `coverage_start must be before coverage_end`
  - `coverage duration implausibly large (overflow guard)`
  - `max_deterministic_remedy must be greater than 0`
  - `max_deterministic_remedy exceeds sanity ceiling`
  - `insufficient pool capacity for this warranty`

#### `cancel_warranty(warranty_id: u32) -> None`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `warranty has an unsettled claim`
  - `unknown reservation`
  - `reservation is not ACTIVE (already released or consumed)`
  - `unknown pool for reservation`
  - `accounting invariant violated`
  - `unknown warranty`
  - `caller is neither the holder nor the manufacturer of this warranty`
  - `warranty is not ACTIVE`

#### `release_expired_reservation(warranty_id: u32) -> None`
- kind: write
- note: Permissionless cleanup - anyone may release capacity for an already expired/cancelled warranty (docs/ECONOMIC_INVARIANTS.md).
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `warranty has an unsettled claim`
  - `unknown reservation`
  - `reservation is not ACTIVE (already released or consumed)`
  - `unknown pool for reservation`
  - `accounting invariant violated`
  - `unknown warranty`
  - `warranty is not expired or cancelled`
  - `claim deadline grace window has not elapsed`

#### `file_claim(warranty_id: u32, targeted_clause_ids: list, failure_asserted_at: u64) -> u32`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `failure_asserted_at must be an integer timestamp`
  - `unknown warranty`
  - `caller is not this warranty's holder`
  - `warranty is cancelled`
  - `unknown governing constitution`
  - `claim filed before coverage_start`
  - `claim filed after the frozen claim deadline`
  - `targeted_clause_ids must be a list`
  - `at least one targeted covered clause is required`
  - `targeted clause_id must be a string`
  - `duplicate targeted clause_id`
  - `targeted clause_id does not exist on the governing constitution`
  - `targeted clause_id must be a COVERED clause, not an exclusion`
  - `an unresolved claim already exists for this warranty`

#### `respond_to_claim(claim_id: u32, decision: str) -> None`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `caller is not this claim's manufacturer`
  - `manufacturer has already responded (responses are immutable)`
  - `response window has closed`

#### `submit_evidence(claim_id: u32, original_url: str, category: str) -> u32`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `caller is neither the holder nor the manufacturer of this claim`
  - `claim is not in a state that accepts evidence`
  - `evidence for this claim is already frozen`
  - `category must be a non-empty string`
  - `category is not one of this constitution's acceptable_evidence_categories`
  - `original_url must not be empty`
  - `original_url exceeds the maximum length ({...})`
  - `original_url is malformed: missing scheme or host`
  - `duplicate evidence URL for this claim`
  - `claim already has the maximum of {...} adjudicable evidence records`

#### `freeze_evidence(claim_id: u32) -> None`
- kind: write
- note: Retrieval + extraction + equivalence + commit, as ONE transaction covering every ELIGIBLE, not-yet-processed evidence record for this claim - but still a transaction entirely separate from, and prior to, any Stage 3 adjudication call. This is the architectural boundary item 12 requires: Claim -> Evidence submission -> Retrieval -> Frozen Evidence -> STOP.
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `claim is not in a state ready for evidence freeze`
  - `evidence for this claim is already frozen`

#### `adjudicate_claim(claim_id: u32) -> u32`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `claim is not in the frozen-evidence state`
  - `claim has already been adjudicated`
  - `unknown warranty`
  - `unknown governing constitution`
  - `invariant violated: more adjudicable evidence than the V1 cap`

#### `file_challenge(claim_id: u32, ground: str, explanation: str, citation: dict) -> u32`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `caller is neither the holder nor the manufacturer of this claim`
  - `citation must be an object`
  - `citation must have exactly the keys evidence_ids, clause_ids, constitution_id, timestamp_field`
  - `evidence_ids must be a short list`
  - `clause_ids must be a short list`
  - `constitution_id must be a non-negative integer`
  - `timestamp_field must be a string`
  - `timestamp_field is not a recognised timestamp`
  - `evidence_ids citation does not match the ground`
  - `clause_ids citation does not match the ground`
  - `constitution_id citation does not match the ground`
  - `timestamp_field citation does not match the ground`
  - `evidence id must be an integer`
  - `duplicate evidence id in citation`
  - `cited evidence does not belong to this claim's frozen record`
  - `cited evidence is not part of the frozen record`
  - `clause id must be a string`
  - `duplicate clause id in citation`
  - `cited clause does not exist on the governing constitution`
  - `claim is not awaiting a possible challenge (no adjudication yet, or already past challenge)`
  - `this claim already has its one application challenge`
  - `the frozen constitution disables application challenges (challenge_depth == 0)`
  - `claim has no adjudication to challenge`
  - `challenge window has not opened`
  - `challenge window has closed`
  - `explanation must be non-empty and within the length bound`

#### `resolve_challenge(claim_id: u32) -> str`
- kind: write
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `reviewed evidence is not part of the frozen adjudicable record`
  - `claim has no open application challenge`
  - `claim has no application challenge`
  - `challenge is not awaiting resolution`
  - `challenge resolution period has lapsed; call lapse_challenge`

#### `execute_remand(claim_id: u32) -> u32`
- kind: write
- note: The single bounded corrective step after a REMAND result. Permissionless; runs at most once (the challenge leaves REMAND_PENDING); the corrected adjudication is final and never challengeable.
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `reviewed evidence is not part of the frozen adjudicable record`
  - `claim has no pending remand`
  - `claim has no application challenge`
  - `challenge has no pending remand`
  - `challenge resolution period has lapsed; call lapse_challenge`

#### `lapse_challenge(claim_id: u32) -> None`
- kind: write
- note: Liveness guard: a challenge that cannot be resolved within one further frozen challenge window (e.g. persistent malformed model output) lapses; the challenger bears the burden and the original adjudication stands. Permissionless.
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `claim has no unresolved challenge`
  - `claim has no application challenge`
  - `challenge is already resolved`
  - `challenge resolution period has not elapsed`

#### `finalize_claim(claim_id: u32) -> None`
- kind: write
- note: APPLICATION finality only. It does NOT and cannot verify GenLayer protocol finality of the deciding transactions (a contract cannot introspect it); operators/frontends MUST confirm the deciding transactions are Finalized before calling (docs/APPEALS_AND_FINALITY.md). Money never moves here - see settle_claim / withdraw_settlement.
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `claim is already finalized`
  - `claim has a challenge`
  - `application challenge window is still open`
  - `challenge is not resolved`
  - `authoritative adjudication is superseded`
  - `claim has an unresolved application challenge`
  - `claim is not in a finalizable state`

#### `settle_claim(claim_id: u32) -> None`
- kind: write
- note: Settlement AUTHORIZATION: converts the final deterministic remedy into a claimable amount (pull payment). No GEN leaves the contract here. The warranty's frozen maximum is a lifetime cap: the amount is min(remedy, what remains reserved for this warranty).
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `claim is not final`
  - `claim has no final decision`
  - `claim is already settled`
  - `accounting invariant violated`

#### `withdraw_settlement(claim_id: u32) -> None`
- kind: write
- note: Pull payment by the recorded recipient. All state (one-shot guard, zeroed claimable) is written BEFORE the transfer is emitted; a re-entrant or repeated call sees nothing claimable.
- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):
  - `unknown claim`
  - `claim has no final decision`
  - `caller is not the settlement recipient`
  - `claim is not settled`
  - `settlement already withdrawn`
  - `nothing to withdraw`

### View methods

#### `get_program(program_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `program_id`
  - `manufacturer`
  - `name`
  - `status`
  - `created_at`

#### `list_program_ids() -> list`
- returns: json.loads(self.program_ids_json)

#### `get_constitution(constitution_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `constitution_id`
  - `program_id`
  - `version`
  - `fingerprint`
  - `product_scope`
  - `coverage_calc`
  - `covered_clause_ids`
  - `excluded_clause_ids`
  - `acceptable_evidence_categories`
  - `source_eligibility_policy`
  - `claim_deadline_s`
  - `manufacturer_response_period_s`
  - `challenge_window_s`
  - `challenge_depth`
  - `insufficient_evidence_behavior`
  - `unavailable_evidence_behavior`
  - `expiry_cancellation_rules`
  - `remedy_table`
  - `frozen_at`
  - `is_frozen`

#### `get_clauses(constitution_id: u32) -> list`
- returns: []

#### `get_pool(program_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `pool_id`
  - `program_id`
  - `manufacturer`
  - `total_balance`
  - `reserved_liability`
  - `available_balance`

#### `get_passport(warranty_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `warranty_id`
  - `program_id`
  - `manufacturer`
  - `holder`
  - `product_model_id`
  - `product_commitment`
  - `registered_at`
  - `coverage_start`
  - `coverage_end`
  - `constitution_id`
  - `constitution_version`
  - `constitution_fingerprint`
  - `max_deterministic_remedy`
  - `reservation_id`
  - `status`

#### `get_reservation(reservation_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `reservation_id`
  - `pool_id`
  - `warranty_id`
  - `amount`
  - `status`
  - `created_at`
  - `released_at`

#### `list_passport_ids(program_id: u32) -> list`
- returns: []

#### `now() -> u64`
- returns: _now()

#### `get_claim(claim_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `claim_id`
  - `warranty_id`
  - `program_id`
  - `holder`
  - `manufacturer`
  - `constitution_id`
  - `constitution_fingerprint`
  - `failure_asserted_at`
  - `targeted_clause_ids`
  - `filed_at`
  - `response_deadline`
  - `manufacturer_response`
  - `responded_at`
  - `evidence_frozen_at`
  - `status`
  - `adjudication_id`

#### `list_claim_ids_for_warranty(warranty_id: u32) -> list`
- returns: [] if ids_json is None else json.loads(ids_json)

#### `get_evidence(evidence_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `evidence_id`
  - `claim_id`
  - `submitter`
  - `original_url`
  - `category`
  - `host`
  - `retrieval_method`
  - `submitted_at`
  - `eligibility`
  - `retrieval_status`
  - `retrieved_at`
  - `frozen_at`
  - `extracted_content`
  - `fingerprint`
  - `available`

#### `list_evidence_ids_for_claim(claim_id: u32) -> list`
- returns: [] if ids_json is None else json.loads(ids_json)

#### `get_adjudication(adjudication_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `adjudication_id`
  - `claim_id`
  - `constitution_id`
  - `adjudicated_at`
  - `product_match`
  - `warranty_version_match`
  - `coverage_window`
  - `covered_clause_ids`
  - `exclusion_clause_ids`
  - `evidence_sufficiency`
  - `source_authority`
  - `evidence_ids_relied_on`
  - `evidence_ids_considered`
  - `outcome`
  - `rationale`
  - `decision_path`
  - `challenge_window_closes_at`
  - `superseded`

#### `get_challenge(challenge_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `challenge_id`
  - `claim_id`
  - `adjudication_id`
  - `challenger`
  - `ground`
  - `explanation`
  - `citation`
  - `filed_at`
  - `status`
  - `result`
  - `resolution_path`
  - `resolution_reason`
  - `remand_issue`
  - `corrected_adjudication_id`
  - `resolved_at`

#### `get_challenge_for_claim(claim_id: u32) -> dict`
- returns the same structure as `get_challenge` (empty object `{}` when none)

#### `get_final_decision(claim_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `claim_id`
  - `source`
  - `adjudication_id`
  - `challenge_id`
  - `final_outcome`
  - `established_clause_ids`
  - `remedy_basis`
  - `remedy_kind`
  - `remedy_value`
  - `remedy_amount`
  - `recipient`
  - `finalized_at`
  - `settled_at`
  - `settled_amount`
  - `capped`
  - `claimable`
  - `withdrawn_at`
  - `withdrawn_amount`

#### `get_resolution_receipt(claim_id: u32) -> dict`
- returns object with keys (empty object `{}` when the id is unknown):
  - `claim_id`
  - `claim_status`
  - `warranty`: object
    - `warranty_id`
    - `holder`
    - `manufacturer`
    - `product_model_id`
    - `coverage_start`
    - `coverage_end`
    - `max_deterministic_remedy`
    - `constitution_id`
    - `constitution_version`
    - `constitution_fingerprint`
  - `claim`: object
    - `targeted_clause_ids`
    - `filed_at`
    - `manufacturer_response`
    - `responded_at`
    - `evidence_frozen_at`
  - `evidence`
  - `ineligible_evidence_count`
  - `original_adjudication`
  - `challenge`
  - `corrected_adjudication`
  - `final_decision`

### Enumerations (module constants)

- **Program status**: `ACTIVE`, `PAUSED`, `RETIRED`
- **Passport status**: `ACTIVE`, `EXPIRED`, `CANCELLED`
- **Reservation status**: `ACTIVE`, `RELEASED`, `CONSUMED`
- **Clause kind**: `COVERED`, `EXCLUDED`
- **Remedy kind**: `FULL_REFUND`, `REPAIR_CREDIT`, `PARTIAL_BPS`, `NONE`
- **Claim status**: `RESPONSE_WINDOW`, `ACCEPTED`, `DISPUTED`, `EVIDENCE_FROZEN`, `DECIDED`, `CHALLENGED`, `CHALLENGE_RESOLVED`, `FINAL`, `SETTLED`
- **Manufacturer response**: `ACCEPT`, `DISPUTE`
- **Evidence eligibility**: `ELIGIBLE`, `INELIGIBLE`
- **Retrieval status**: `""` (pending), `AVAILABLE`, `UNAVAILABLE`, `FETCH_FAILED`, `RENDER_FAILED`, `INSUFFICIENT`
- **Challenge status**: `OPEN`, `REMAND_PENDING`, `RESOLVED`
- **Challenge result**: `UPHELD`, `REVERSED`, `REMAND`, `INVALID_CHALLENGE`
- **Outcomes (adjudication / final)**: `COVERED`, `NOT_COVERED`, `INSUFFICIENT_EVIDENCE`, `EVIDENCE_UNAVAILABLE`, `INVALID_CLAIM`, `ACCEPTED_NO_CONTEST`
- **Challenge grounds**: `IGNORED_EVIDENCE`, `WRONG_WARRANTY_VERSION`, `WRONG_CLAUSE`, `EXCLUSION_MISAPPLIED`, `TEMPORAL_ERROR`, `SOURCE_AUTHORITY_ERROR`, `PRODUCT_MATCH_ERROR`
- **Tri-state findings**: `PASS`, `FAIL`, `UNCLEAR`
- **Challenge model decisions**: `DEFECT_CONFIRMED`, `DEFECT_NOT_CONFIRMED`, `NEEDS_RECONSIDERATION`
- **Citation timestamp fields**: `failure_asserted_at`, `coverage_start`, `coverage_end`, `filed_at`, `adjudicated_at`, `evidence_frozen_at`
- **Evidence-gap behaviours**: `RULE_FOR_HOLDER`, `RULE_FOR_MANUFACTURER`, `BLOCK`

### Limits

- `_MAX_ADJUDICABLE_EVIDENCE` = 10
- `_MAX_CLAUSES_PER_KIND` = 50
- `_MAX_REMEDY_ROWS` = 50
- `_MAX_EVIDENCE_CATEGORIES` = 20
- `_MAX_SHORT_LEN` = 200
- `_MAX_TEXT_LEN` = 4000
- `_MAX_URL_LEN` = 500
- `_MAX_EXTRACT_LEN` = 2000
- `_MAX_RATIONALE_LEN` = 1000
- `_MAX_EXPLANATION_LEN` = 1000
- `_MAX_REMAND_ISSUE_LEN` = 500
- `_MAX_CITATIONS` = 10
- `_MAX_CHALLENGE_DEPTH` = 1
<!-- END GENERATED -->
