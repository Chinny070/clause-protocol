# CLAUSE - Release candidate verification (Stage 6A.1)

**Verdict: DEPLOYMENT READY for manual StudioNet deployment.** The human cancellation-policy decision is implemented and re-audited. The contract has **not** been deployed.

> **SUPERSEDED - DO NOT DEPLOY:** the Stage 6A candidate `07d7e4bfdbaeeba2d30129c00034cd728681ed99877286a16189005fbe7d847e` (blob `5e7e7f3bf3d6f70cd69c325385e409a89355d65a`, 134,456 bytes) allowed a manufacturer to cancel an issued warranty. It must never be deployed. The only deployable file is the one below.

## 1. The release candidate

| | |
|---|---|
| File | `contracts/clause_protocol.py` |
| **SHA-256** | **`2cae6e200ee82b747ebe89bf3e423768fca545ada840348a8f104d9053c07851`** |
| Size / encoding | 134,577 bytes, ASCII, LF (`git ls-files --eol`: `i/lf w/lf attr/text eol=lf`) |
| Git blob | `0e6442369d4b44ed9c25908cc3a18dfcdb6c530f` |
| Change vs Stage 6A | one guard in `cancel_warranty` (3 lines added, 5 removed): the caller must be the passport's holder; the manufacturer branch is removed |
| Public methods | 40 = 18 view + 22 write; 1 payable (`fund_pool`); constructor takes no arguments |

## 2. Cancellation policy (implemented)
Issuance creates the warranty commitment. The manufacturer cannot cancel, shorten, rewrite or invalidate an issued Warranty Passport. `pause_program` / `retire_program` stop future issuance only. The holder may cancel their own passport while ACTIVE and with every claim SETTLED; cancellation releases the unconsumed reservation. Proof: `tests/direct/test_stage6a1_cancellation.py` (15 tests: manufacturer rejected immediately after issuance, after an asserted failure before claim filing, in the claim grace period, after pause, after retire; holder rules; reservation/grace protections; pause/retire still block issuance; existing passports continue under frozen terms).
Observed, unchanged pre-existing behaviour: a warranty whose reservation was fully consumed by settlement cannot be cancelled by its holder (release reverts).

## 3. Regression (all on the final LF bytes)

| Suite | Result |
|---|---|
| `pytest tests/direct` | **641 passed** (626 previous + 15 new; 3 existing tests re-pointed from manufacturer to holder as sender) |
| Real simulator: lifecycle / adjudication / settlement / response probe | passed / passed / passed / passed |
| Real simulator: undetermined experiment | **xfailed as designed** (Gate B) |
| Frontend <-> contract integration (`run_frontend_integration.sh`) | passed |
| `genvm-lint` lint / validate / schema | passed (3 checks) / 40 methods (18 view, 22 write) / constructor 0 params |
| `genvm-lint typecheck` | 0 errors, 0 warnings |
| ABI drift (`gen_frontend_interface.py --check`) | in sync |
| Frontend `vitest` | **119 passed** (9 files) |
| Frontend eslint, tsc | clean |
| Production build | succeeds (875.67 kB / 216.72 kB gzip; no `.env.local`); `npm audit --omit=dev`: 0 vulnerabilities |
| Security mutation sweep | **17/19 guards killed** (new: holder-only cancellation **killed**); 2 survivors are the known redundant defence-in-depth guards (evidence freeze, single adjudication); see `docs/RELEASE_MUTATION_SWEEP.json` |

No unrelated behaviour changed: the contract diff touches only the `cancel_warranty` authorization; the whole prior suite passes unchanged apart from three sender re-points.

## 4. Source parity
One deployable artifact. `frontend/src/deploy/expected.ts` pins `2cae6e200ee82b747ebe89bf3e423768fca545ada840348a8f104d9053c07851` / 134,577 bytes; `frontend/tests/deploy.test.ts` and the local deployer refuse anything else. `.gitattributes` (`*.py text eol=lf`) keeps LF. After deployment compare `getContractCode` SHA-256 (`MANUAL_DEPLOYMENT.md`).

## 5. Manual deployment, gates, finality, hosting, security
Unchanged from Stage 6A: `MANUAL_DEPLOYMENT.md` (local wallet-authorized deployer, now pinned to the new hash), `MANUAL_SMOKE_TEST.md`, StudioNet gates A-H in `docs/STUDIONET_GATE_PLAN.md` (not executed), `docs/FINALITY_HASH_DISCOVERY.md`, `docs/RELEASE_SECURITY_MATRIX.md` (updated for this hash). The deployer wallet-signing path was never exercised with a real wallet.

## 6. Files changed in Stage 6A.1
`contracts/clause_protocol.py`; tests (`test_authorization`, `test_stage45_freeze`, `test_stage4_economics`, new `test_stage6a1_cancellation`); frontend (`PassportPage`, `Limits`, `ManufacturerPages`, `deploy/expected.ts`, three test files); `scripts/security_mutation_sweep.py`; docs (interface, cancellation policy, economic invariants, state machines, Stage 5 risks, security matrix, mutation sweep JSON, run logs); `MANUAL_DEPLOYMENT.md`, `MANUAL_SMOKE_TEST.md`, `GENLAYER_SUBMISSION_DRAFT.md`, `README.md`, this file.

The contract has NOT been deployed to StudioNet. No user wallet/private key/seed phrase was accessed or used.
