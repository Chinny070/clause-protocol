# Stage 5 - product risks for the Stage 6 release review

The contract was frozen at `0b472ce` (Stage 6A.1 changed only cancellation authorization); the frontend surfaces these behaviours honestly and does not paper over them.

## 1. Warranty cancellation - RESOLVED in Stage 6A.1

**Policy (V1):** issuance creates the warranty commitment. `cancel_warranty` is callable **only by the warranty's holder** (while ACTIVE and every claim is SETTLED). The manufacturer cannot cancel, shorten, rewrite or invalidate an issued warranty at any time (immediately after issuance, after an asserted failure, or during the claim grace period). Pausing or retiring a program stops *future* issuance only; existing warranties remain governed by their frozen terms.

**What the frontend does:** every ACTIVE passport shows "ISSUED WARRANTY - TERMS FROZEN"; only the holder sees the cancel control; program pause/retire descriptions state "Retiring a program stops future issuance. Existing warranties remain governed by their frozen terms."; `/limits` states the policy. The former "Not irrevocable" notice was removed.

Evidence: `tests/direct/test_stage6a1_cancellation.py`, `docs/CANCELLATION_POLICY_DECISION.md`.

## 2. Protocol finality cannot be verified on-chain
The contract cannot read transaction finality and does not store transaction hashes. The frontend verifies `Finalized` + successful execution from the network before finalize/settle/withdraw (fail closed) and needs a hash: from this browser's journal (`localStorage`, may be empty/blocked) or pasted by the user. A public visitor who did not send the earlier step must paste its hash to proceed. **Gate:** confirm on StudioNet that an indexer/explorer can supply hashes per claim, or accept the paste flow.

## 3. Evidence limits and fairness
Maximum 10 adjudicable records per claim, first-come; either party can consume all slots before the other submits. Ineligible URLs cost no slot. Surfaced in the claim form, the Evidence Locker and `/limits`.

## 4. Overlapping claims
A warranty's maximum remedy is a lifetime cap across its claims, paid first-settled-first-served; later claims can be capped, possibly to 0 (`capped` is shown on the final decision and receipt).

## 5. Unavailable / insufficient evidence
Neither is treated as negative evidence; what follows is the frozen policy (rule for holder / manufacturer / block). The UI keeps INSUFFICIENT_EVIDENCE and EVIDENCE_UNAVAILABLE visually and linguistically distinct from NOT_COVERED.

## 6. Semantic steps depend on real models (StudioNet gates)
`adjudicate_claim`, semantic `resolve_challenge` and `execute_remand` were never exercised with a real model (none exists in the simulator). `freeze_evidence` for `*_RENDERED` categories depends on genuine `web.render`. The UI presents these as ordinary transactions that can fail or end undetermined, with retry.

## 7. Unverified StudioNet behaviours the UI depends on
`getTransaction` shape on StudioNet; wallet signing; timestamp source; payable behaviour without the simulator shim; transfer emission timing (the withdrawal transfer's finality gating). The app fails closed on unknown shapes.

## 8. Frontend-specific
- Amount inputs are exact (no floating point); a bundle of ~860 kB (211 kB gzip) is acceptable for V1.
- Explorer scans programs -> passports -> claims sequentially with bounded concurrency; a very large deployment needs an indexer (Stage 6+).
- `localStorage` journal is a convenience only.
- Constitution enumeration scans ids 1..200 until the first unknown id (no list method exists in the frozen ABI).
