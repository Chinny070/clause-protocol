# CLAUSE - Release candidate verification (Stage 6A)

**Verdict: DEPLOYMENT READY *pending one human decision*** (cancellation policy, `docs/CANCELLATION_POLICY_DECISION.md`). No contract defect blocks deployment. The contract has **not** been deployed.

## 1. The release candidate

| | |
|---|---|
| File | `contracts/clause_protocol.py` |
| **SHA-256** | **`07d7e4bfdbaeeba2d30129c00034cd728681ed99877286a16189005fbe7d847e`** |
| Size / encoding | 134,456 bytes, ASCII, LF |
| Git blob | `5e7e7f3bf3d6f70cd69c325385e409a89355d65a` - **identical at the Stage 4.5 freeze commit `0b472ce` and at the Stage 5 commit `5098a7b`** (`git rev-parse <commit>:contracts/clause_protocol.py`) |
| Changed since the freeze | **No.** Only the on-disk line endings of the working copy were normalized CRLF -> LF (see 3); the committed content is unchanged and no source line differs. |
| Header | `# v0.1.0` / `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` |
| Public methods | 40 = **18 view + 22 write** |
| Payable | 1: `fund_pool(program_id)` |
| Constructor | `__init__(self)` - **no arguments** |
| Frozen ABI doc | `docs/FRONTEND_CONTRACT_INTERFACE.md` (drift-tested) |

## 2. Regression (all run on the LF file; nothing skipped)

| Suite | Result |
|---|---|
| Contract direct tests (`pytest tests/direct`) | **626 passed** |
| Stage 2.5 real simulator - lifecycle (`test_real_web_lifecycle`) | passed (16 txs) |
| Stage 2.5 real simulator - undetermined experiment (`test_real_web_undetermined`) | **xfailed as designed** (the simulator cannot produce validator disagreement; this is Gate B) |
| Stage 2.5 response probe | passed |
| Stage 3 real simulator (`test_real_adjudication`) | passed (deterministic paths; semantic path fails closed - no model) |
| Stage 4 real simulator settlement (`test_real_settlement`) | passed |
| Stage 5 frontend <-> contract integration (`run_frontend_integration.sh`) | passed |
| `genvm-lint lint` | passed (3 checks) |
| `genvm-lint validate` | passed - 40 methods (18 view, 22 write) |
| `genvm-lint schema` | OK; constructor 0 params |
| `genvm-lint typecheck` | 0 errors, 0 warnings |
| ABI drift check (`gen_frontend_interface.py --check`) | in sync |
| Frontend `npm test` | **114 passed** (9 files, including the new deployer/source-parity tests) |
| Frontend `eslint`, `tsc` | clean |
| Frontend production build | succeeds (875 kB / 217 kB gzip; no address, no deployer, no dev network); `npm audit --omit=dev`: 0 vulnerabilities |
| Security mutation sweep | 16/18 guards killed, 2 redundant (see `docs/RELEASE_SECURITY_MATRIX.md`); audited file restored and re-hashed |

**Simulator limitations (reported separately, none hidden):** glsim has no model provider (no semantic adjudication / challenge review / remand); it cannot cause validator disagreement; it emulates `render` as GET; it needs a msg.value shim for payable calls; it does not track balances (so transfer emission is unverified); its clock and finality timing are not StudioNet's. These are exactly StudioNet gates A-H (`docs/STUDIONET_GATE_PLAN.md`).

## 3. Source parity (what will be deployed is what was audited)

- There is **one** deployable artifact: the file above. No "deployment version" exists.
- **Line-ending hazard found and fixed:** the Windows working copy had CRLF (SHA-256 `1e990046…`, 137,212 bytes) while Git stores LF (SHA-256 `07d7e4bf…`, 134,456 bytes); a user hashing a CRLF checkout would have seen a different hash. The file was converted to LF on disk; the Git blob is unchanged; the repo's existing `.gitattributes` (`*.py text eol=lf`) keeps every checkout LF. All results in section 2 were produced on the LF file (the 626-test run and every integration run happened after normalization).
- `frontend/src/deploy/expected.ts` pins the audited SHA-256 and byte count; `frontend/tests/deploy.test.ts` fails if the constant and the file diverge; the local deployer refuses to deploy anything else.
- After deployment: fetch the deployed source (`getContractCode`) and compare its SHA-256 (steps in `MANUAL_DEPLOYMENT.md`).

## 4. Manual deployment method prepared
`MANUAL_DEPLOYMENT.md`: Route 1 (recommended) is a **local wallet-authorized deployer page** (`npm run deploy:tool`) using the audited SDK generation (`genlayer-js` 1.1.8) against StudioNet 61999 only; the user's wallet signs; no key is ever requested; it blocks on hash mismatch and reports success only on FINALIZED + successful execution. Routes 2 (Studio web UI) and 3 (CLI) are documented as unverified fallbacks. **The deployer's wallet-signing path was not exercised with a real wallet or on StudioNet** (only against mocks and by loading the page); this is stated in the document.

## 5. Outstanding StudioNet gates
A real `web.render`; B validator disagreement / undetermined rollback; C protocol timestamps; D payable value without the shim; E real-model adjudication; F real-model prompt injection; G real-model Application Challenge (+REMAND); H finality-gated withdrawal with balance movement. Exact setup / transaction / expected result / authoritative read / pass / fail conditions: **`docs/STUDIONET_GATE_PLAN.md`** (not executed). The minimal-wallet-work procedure: `MANUAL_SMOKE_TEST.md`.

## 6. Cancellation policy - STOP FOR HUMAN DECISION
Current behaviour (unchanged): the manufacturer **or** the holder can cancel an ACTIVE warranty while no claim is unsettled; there is no consent or notice. **Option A** retain (release as audited; coverage is a revocable promise - disclosed in the app; weakest for production positioning). **Option B** restrict/remove (holder-only, mutual consent, or notice period; requires a contract change, new hash, updated tests/interface/frontend, re-audit). Full analysis: `docs/CANCELLATION_POLICY_DECISION.md`. **This assistant did not choose.**

## 7. Finality-hash discovery
No verified reliable way exists with the frozen contract + stable StudioNet / genlayer-js 1.1.8 to recover the deciding transaction hash from contract or network data (no per-contract transaction listing in the SDK; contract stores no hashes). Documented limitation and safest UX (journal + pasted hash, fail closed): `docs/FINALITY_HASH_DISCOVERY.md`.

## 8. Frontend release configuration
Exactly one canonical address source: `VITE_CLAUSE_CONTRACT_ADDRESS` read only in `frontend/src/config/contract.ts` (test-enforced; validated; never `undefined` into the SDK). No fake address exists anywhere (test-enforced). After deployment only that variable needs setting. Hosting preparation (`frontend/HOSTING.md`, `frontend/public/_headers`): prepared, **not live**; the bundle boots under the CSP locally.

## 9. Security audit
`docs/RELEASE_SECURITY_MATRIX.md`: 16 areas audited from source with an independent guard-by-guard mutation sweep. No blocking finding; no contract change.

## 10. Submission
`GENLAYER_SUBMISSION_DRAFT.md` prepared with placeholders; steward-verifiable outcome is a set of six public-data checks (source hash, frozen-terms fingerprints, evidence fingerprints, validator votes, remedy == frozen table row, real balance movement). Nothing submitted.

## 11. Files added / changed in Stage 6A
New: this file, `MANUAL_DEPLOYMENT.md`, `MANUAL_SMOKE_TEST.md`, `GENLAYER_SUBMISSION_DRAFT.md`, `docs/{STUDIONET_GATE_PLAN,RELEASE_SECURITY_MATRIX,CANCELLATION_POLICY_DECISION,FINALITY_HASH_DISCOVERY,RELEASE_MUTATION_SWEEP.json}`, `docs/smoke_evidence/*.txt`, `scripts/security_mutation_sweep.py`, `frontend/{deploy.html,vite.deploy.config.ts,HOSTING.md,public/_headers,src/deploy/*,tests/deploy.test.ts}`. Modified: `frontend/package.json` (script), `frontend/tsconfig.json`, `frontend/tests/domain.test.tsx` (guard tightened to API use), `.gitignore`. **`contracts/clause_protocol.py`: on-disk line endings normalized to LF only; content and Git blob unchanged.**

The contract has NOT been deployed to StudioNet. No user wallet/private key/seed phrase was accessed or used.
