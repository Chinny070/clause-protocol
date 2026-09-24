# Cancellation policy - HUMAN DECISION REQUIRED BEFORE DEPLOYMENT

**Status: not changed, not chosen.** This document only lays out the two options.

## Current behaviour (audited in the release candidate)
`cancel_warranty(warranty_id)` (`contracts/clause_protocol.py`): callable by the warranty's **manufacturer or holder**; requires the passport to be ACTIVE (not yet expired) and **every claim on the warranty to be SETTLED**; then sets the passport CANCELLED and releases the remaining reservation. A CANCELLED warranty cannot receive new claims (`file_claim` rejects it). There is no holder consent, no notice period, and the constitution's `expiry_cancellation_rules` text is informational only (the contract does not enforce it).

Related protections that already exist: cancellation is impossible while any claim is unsettled (so a filed claim cannot be cancelled away); the reservation is released only through the same guarded path; the frontend shows a "Not irrevocable" notice on every ACTIVE passport and a red "cancelled" banner afterwards.

## Option A - retain current behaviour
- **What it permits:** a manufacturer can unilaterally end a holder's coverage at any moment before a claim is filed (for example after a product has failed but before the holder files), and recover the reserved capacity. The holder can also cancel (e.g. to end coverage they no longer want). Once any claim exists on the warranty, cancellation waits for it to settle.
- **Trust/product implications:** coverage is a revocable promise, not a guarantee. This undercuts the core thesis ("the rules don't get to change now") at the moment where the manufacturer has the most incentive: the frozen terms constrain how disputes are judged but not whether the promise still exists. It is disclosed prominently (passport, wizard, `/limits`), but a holder who does not check can be surprised. It could be acceptable for a pilot/demo with disclosure; it is a weak claim for production "warranty" positioning.
- **Work required:** none (release as audited).

## Option B - remove or restrict unilateral post-issuance cancellation
Variants (choose one or a combination; not chosen here):
- **B1 holder-only:** only the holder may cancel; the manufacturer cannot. Simplest.
- **B2 mutual consent:** cancellation needs both parties (two-step: propose + accept).
- **B3 manufacturer cancellation only after coverage ends / never:** effectively B1.
- **B4 notice period:** manufacturer may cancel only after a delay recorded on-chain (needs new storage and a rule for claims filed during the notice period).

**Contract changes:** `cancel_warranty` authorization (B1: holder only; B2/B4 new state, methods and rules); consequently a new contract source, a new SHA-256, and the frozen ABI changes for B2/B4 (new methods) or only behaviour for B1 (signature unchanged).
**Tests to update/add:** `tests/direct/test_authorization.py::test_manufacturer_can_cancel_warranty` (must become a rejection), `test_constitution_hardening.py` (sequence cancels as manufacturer), `test_stage45_freeze.py` (`cancel()` helper uses the manufacturer), `test_pool_accounting.py` / `test_invariants.py` cancel paths, plus new tests for the chosen rule; rerun the full regression, the mutation sweep, `genvm-lint`, and the ABI drift test.
**Interface/docs to update:** regenerate `docs/FRONTEND_CONTRACT_INTERFACE.md` (`scripts/gen_frontend_interface.py`), `docs/ECONOMIC_INVARIANTS.md`, `docs/STATE_MACHINES.md`, `docs/DATA_MODEL.md`, release docs, and the audited hash in `MANUAL_DEPLOYMENT.md`, `RELEASE_CANDIDATE_VERIFICATION.md` and `frontend/src/deploy/expected.ts` (a test enforces parity).
**Frontend to update:** `PassportPage` cancel button and permissions, the "Not irrevocable" notice, wizard note, `/limits` cancellation section, `docs/STAGE_5_PRODUCT_RISKS.md`, frontend tests that assert the notice and the cancel button; if the ABI changes (B2/B4), the builders and ABI-parity test.
**Effect on gates:** the StudioNet gate plan is unchanged; the audit and sweep must be repeated on the new hash.

## Decision needed
Retain (A) and deploy as audited, or authorize a contract change (B) and re-freeze. This assistant will not choose. Deployment should wait for the decision.
