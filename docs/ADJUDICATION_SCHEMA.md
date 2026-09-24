# CLAUSE — Adjudication Schema (Stage 0)

## Frozen minimum schema

```json
{
  "product_match": "PASS|FAIL|UNCLEAR",
  "warranty_version_match": "PASS|FAIL|UNCLEAR",
  "coverage_window": "PASS|FAIL|UNCLEAR",
  "covered_clause_ids": [],
  "exclusion_clause_ids": [],
  "evidence_sufficiency": "SUFFICIENT|INSUFFICIENT|UNAVAILABLE",
  "source_authority": "PASS|FAIL|UNCLEAR",
  "evidence_ids_relied_on": [],
  "outcome": "COVERED|NOT_COVERED|INSUFFICIENT_EVIDENCE|EVIDENCE_UNAVAILABLE|INVALID_CLAIM",
  "rationale": "bounded explanation"
}
```

This is byte-identical to both source documents and must not be extended in Stage 0 or Stage 1 without
the user's explicit sign-off — it is the one piece of shape both documents call "frozen" before coding.

## Core question the adjudicator answers

> Does the frozen admissible evidence establish that this product failure satisfies the frozen covered
> condition, after applying frozen exclusions and temporal rules?

Never: "how much should be paid." `outcome` plus the deterministic `RemedyRow` table
(`DATA_MODEL.md`/`ECONOMIC_INVARIANTS.md`) is the only bridge from semantics to money.

## Why `gl.vm.run_nondet_unsafe`, not `strict_eq` or the prompt_* convenience wrappers

Per `NETWORK_AND_SDK_VERIFICATION.md`, current docs frame hand-written `run_nondet_unsafe` leader/
validator functions as the default for production contracts, and explicitly warn that
`prompt_comparative`/`prompt_non_comparative` are convenience wrappers most contracts outgrow. The
Adjudication Schema is exactly the "Pattern 1: Partial Field Matching" case from that page: `rationale`
is free text (never compared), every other field is a bounded enum or a validated list of frozen IDs
(compared exactly).

```python
def leader_fn():
    facts = _load_frozen_evidence_facts(claim_id)          # from already-frozen EvidenceRecords only
    prompt = _build_adjudication_prompt(constitution, claim, facts)
    response = gl.nondet.exec_prompt(prompt, response_format="json")
    return _validate_adjudication_shape(response)            # fail-closed coercion, see below

def validator_fn(leader_result):
    if not isinstance(leader_result, gl.vm.Return):
        return _handle_leader_error(leader_result, leader_fn)
    validator_judgment = leader_fn()
    leader_judgment = leader_result.calldata
    # compare ONLY the structured decision fields; rationale text is never compared
    return _adjudications_structurally_agree(leader_judgment, validator_judgment)

result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
```

`_load_frozen_evidence_facts` reads only `EvidenceRecord.extracted_facts` for records with `frozen_at !=
0` and `eligibility == ELIGIBLE` and `evidence_id in claim.evidence_ids` — the adjudicator never sees
un-frozen or ineligible evidence, and never re-fetches the web itself (that already happened, and was
already committed, in the separate `freeze_evidence` transaction — see `EVIDENCE_ARCHITECTURE.md`).

## Fail-closed shape validation (`_validate_adjudication_shape`)

Before the leader's JSON is even usable as a candidate result, it is deterministically coerced:

- Every enum field must be exactly one of its allowed literals — anything else is a hard error
  (`[LLM_ERROR]` class, forces retry with a different leader), never silently coerced to a default.
- `covered_clause_ids` / `exclusion_clause_ids` / `evidence_ids_relied_on` must reference IDs that
  actually exist in the frozen Constitution / frozen EvidenceRecords for this claim — a hallucinated
  clause or evidence ID is a hard error, not filtered out silently. This is CLAUSE's specific answer to
  the "malformed model output / hallucinated IDs" security requirement.
- `outcome` must be internally consistent with the other fields under a small deterministic rule table,
  checked in plain Python, not trusted from the LLM: e.g. `outcome == "COVERED"` requires
  `evidence_sufficiency == "SUFFICIENT"` and at least one entry in `covered_clause_ids` and
  `product_match/warranty_version_match/coverage_window` all `"PASS"`; `evidence_sufficiency ==
  "UNAVAILABLE"` forces `outcome == "EVIDENCE_UNAVAILABLE"` regardless of what the model additionally
  claimed. Any inconsistency is a hard error (same `[LLM_ERROR]`-class retry), not a "best guess"
  resolution — this is what makes the schema "deterministically validated before mutation" as both
  source documents require.

## Structural-agreement comparator (`_adjudications_structurally_agree`)

Compares every field **except** `rationale`, exactly (no numeric tolerance needed — every field here is
an enum or an ID list): `covered_clause_ids`/`exclusion_clause_ids`/`evidence_ids_relied_on` compared as
sets (order-independent, since two independent LLM passes may list IDs in different order but must agree
on membership). Any field mismatch is Disagree, which — per `run_nondet_unsafe` semantics
(`NETWORK_AND_SDK_VERIFICATION.md`) — triggers leader rotation and retry, never a partial/best-effort
accept.

## Counterfactual independence (never leaks into the prompt or the loaded facts)

`_build_adjudication_prompt` never includes: payout amount, pool balance, `available_balance`,
manufacturer or holder identity beyond what a covered clause genuinely requires (e.g. a clause requiring
"original purchaser" needs to know identity match, but never needs to know account balances), or any
other party's unrelated reputation. This is enforced structurally: the function that builds the prompt
receives only `(constitution_fields_needed_for_adjudication, claim_metadata_minus_financial_fields,
frozen_evidence_facts)` as its input type — it is never handed the `Claim`, `WarrantyPool`, or
`WarrantyPassport` objects wholesale, precisely so a future edit cannot accidentally wire in a
financially-tainted field.

## Insufficient/unavailable evidence is decided before the LLM call, where possible

If `freeze_evidence` already determined (Step 4/5, `EVIDENCE_ARCHITECTURE.md`) that no eligible evidence
exists for a category the Constitution's `insufficient_evidence_behavior` requires, the Claim routes to
`INSUFFICIENT_EVIDENCE`/`EVIDENCE_UNAVAILABLE` deterministically and `adjudicate` need not even run — a
cost and prompt-injection-surface reduction, and a stronger guarantee than trusting the LLM to notice
gaps itself.

## Stage 3 as-implemented (2026-09-24)

**The frozen 10-field schema above is unchanged and is exactly what is stored** (`Adjudication`
record, `get_adjudication`). What Stage 3 pins down is *who produces each field*:

| Stored field | Producer |
|---|---|
| `warranty_version_match` | **deterministic**: PASS iff passport, claim and constitution agree on `constitution_id` + fingerprint, else FAIL |
| `coverage_window` | **deterministic**: PASS iff `coverage_start <= failure_asserted_at <= coverage_end` (claimant-asserted date vs frozen passport window), else FAIL. Never UNCLEAR (a failure date always exists) |
| `evidence_sufficiency` = `UNAVAILABLE` | **deterministic**: eligible evidence exists but none is `AVAILABLE` |
| `evidence_sufficiency` = `INSUFFICIENT` (no admissible evidence) | **deterministic**: no `ELIGIBLE` evidence at all |
| `source_authority` | **deterministic**: PASS iff at least one evidence id is relied on (only `ELIGIBLE` evidence is ever shown, and relied ids are validated as a subset of those shown); else UNCLEAR. FAIL is reserved and currently unreachable because ineligible evidence never reaches adjudication |
| `product_match`, `covered_clause_ids`, `exclusion_clause_ids`, `evidence_sufficiency` (SUFFICIENT/INSUFFICIENT), `evidence_ids_relied_on`, `rationale` | **model** (validated) |
| `outcome` | **deterministic derivation** from the above; the model never emits it |

**Model-level output schema** (strict; exactly these 6 keys, no others): `product_match`
(PASS|FAIL|UNCLEAR), `covered_clause_ids` (subset of the claim's targeted COVERED clauses),
`exclusion_clause_ids` (subset of the constitution's EXCLUDED clauses), `evidence_sufficiency`
(SUFFICIENT|INSUFFICIENT; the model can never assert UNAVAILABLE), `evidence_ids_relied_on`
(subset of evidence shown), `rationale` (non-empty, at most 1000 chars). This is a strict *subset*
of the frozen schema, not a schema change; the omitted fields are derived by the contract.

**Coherence policy (violations are malformed output and revert):** SUFFICIENT requires at least one
relied evidence id; INSUFFICIENT forbids any covered/exclusion clause; a covered clause requires
product PASS and SUFFICIENT; product FAIL forbids a covered clause.

**Outcome derivation (first match wins):**
1. `warranty_version_match = FAIL` -> `INVALID_CLAIM`
2. `coverage_window = FAIL` -> `NOT_COVERED`
3. `evidence_sufficiency = UNAVAILABLE` -> `EVIDENCE_UNAVAILABLE`
4. `evidence_sufficiency = INSUFFICIENT` -> `INSUFFICIENT_EVIDENCE`
5. `product_match = FAIL` -> `NOT_COVERED`; `= UNCLEAR` -> `INSUFFICIENT_EVIDENCE`
6. any established exclusion -> `NOT_COVERED`
7. covered clause established AND product/window/version/source all PASS AND SUFFICIENT -> `COVERED`
8. otherwise (sufficient evidence, nothing covered established) -> `NOT_COVERED`

Rules 1-3 and the no-evidence cases are decided **without consulting the model at all**
(`decision_path` = `DETERMINISTIC_PREDICATE | DETERMINISTIC_NO_ADMISSIBLE_EVIDENCE |
DETERMINISTIC_EVIDENCE_UNAVAILABLE`; otherwise `SEMANTIC`).

**Burden/exclusion semantics:** an exclusion counts only if the model lists it as *established by
evidence* (prompt rule 5); merely existing in the constitution changes nothing. Coverage requires an
*affirmative* covered clause; absence of proof of an exclusion does not create coverage (rule 8). An
established exclusion defeats an established covered clause (rule 6 before 7), and both lists are
stored for Stage 4.

**Validator equivalence** = equality of `_structural_key`: `product_match`, sorted
`covered_clause_ids`, sorted `exclusion_clause_ids`, `evidence_sufficiency`, sorted
`evidence_ids_relied_on`. `rationale` is stored from the accepted leader result and is **never**
compared (two honest models will not phrase alike). `outcome` and the deterministic fields are pure
functions of compared inputs plus frozen state, so they cannot differ between honest nodes. Each
validator also re-runs the full fail-closed checker on the *leader's returned value* before comparing
(a malicious leader cannot smuggle an unchecked structure through consensus). A validator whose own
model call fails or is malformed votes `False`; it never raises.

**Exact prompt inputs** (`_build_adjudication_prompt`; asserted by tests). *governing_rules*:
`constitution_version`, `product_scope`, `coverage_calc`, `targeted_covered_clauses[{clause_id,text}]`,
`exclusion_clauses[{clause_id,text}]`. *claim_facts*: `claim_id`, `registered_product_model`,
`failure_date_asserted_by_claimant_unverified`, `coverage_start`, `coverage_end`,
`protocol_determined{warranty_version_match, coverage_window}`. *evidence* (at most 10; `ELIGIBLE` +
`AVAILABLE` + frozen only): `evidence_id`, `category`, `submitted_by` (HOLDER|MANUFACTURER),
`source_host`, `retrieved_at`, `content`. **Never in the prompt** (test-enforced): pool balances,
reserved/available capacity, remedy table/values, `max_deterministic_remedy`, reservation data,
addresses, `product_commitment`, fingerprints, the manufacturer response, the
`*_evidence_behavior` policy fields, and any ineligible/failed evidence.
