# Cancellation policy - DECIDED and IMPLEMENTED (Stage 6A.1)

**Decision (human, Stage 6A.1):** a manufacturer must NOT be able to unilaterally cancel an already-issued Warranty Passport. Issuance creates the warranty commitment. A manufacturer may pause or retire a warranty program for future issuance, but that never cancels, shortens, rewrites or invalidates an issued passport. The holder may cancel their own passport.

## Implementation (the only contract change)
`cancel_warranty(warranty_id)` now requires the caller to be the passport's **holder** (`caller is not this warranty's holder: only the holder can cancel an issued warranty`). Unchanged guards: passport ACTIVE (not expired), every claim on it SETTLED, then status CANCELLED and the remaining reservation released. `pause_program` / `retire_program` affect only `issue_warranty` and `create_constitution`; no code path lets a manufacturer alter an issued passport. The Constitution stays immutable once frozen.

## Proof
`tests/direct/test_stage6a1_cancellation.py` (manufacturer cannot cancel: just after issuance, after an asserted failure before claim filing, during the claim grace period, after pause, after retire; holder cancel rules; reservation/grace protections; pause/retire still block future issuance; existing passports proceed under frozen terms) plus the mutation sweep guard "cancellation: holder only". Frontend: only the holder sees the cancel control; passports show "ISSUED WARRANTY - TERMS FROZEN".

## Known, unchanged behaviour
A holder cannot cancel a warranty whose reservation was fully consumed by settlement (the release reverts); the warranty is then simply exhausted.

The old option analysis (retain / holder-only / consent / notice period) is superseded; holder-only was chosen.
