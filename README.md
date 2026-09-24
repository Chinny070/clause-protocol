# CLAUSE

**A warranty is only as good as who gets to interpret it.**

CLAUSE is a precommitted warranty adjudication protocol on GenLayer. The manufacturer writes the warranty up front; the terms freeze and are fingerprinted; evidence is retrieved independently through validator consensus; GenLayer validators decide structured findings; plain code derives the outcome and picks the remedy from a table frozen before any dispute; one Application Challenge is allowed; settlement is pull-payment.

| Part | Where | Status |
|---|---|---|
| Intelligent Contract (Python, GenVM) | `contracts/clause_protocol.py` | **Frozen** at commit `0b472ce` (Stage 4.5). 40 public methods. |
| Frozen ABI / lifecycle for clients | `docs/FRONTEND_CONTRACT_INTERFACE.md` | Generated from the contract, drift-tested |
| Frontend (no backend) | `frontend/` | Stage 5 |
| Stage reports | `STAGE_*.md`, `docs/` | history of what was verified and what was not |

Not yet done: StudioNet deployment (Stage 6). The frontend has **no contract address** configured until then and says so.

## Frontend - run, build, test

Requirements: Node 20+ (developed on Node 24), npm.

```bash
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173  (reads the configured contract; no wallet needed to browse)
npm run typecheck    # tsc -b --noEmit
npm run lint         # eslint (incl. jsx-a11y)
npm test             # 106 unit/component tests (mocked transport that implements the SDK interface)
npm run build        # production bundle in frontend/dist (static files; host anywhere)
```

Configuration (all optional; see `frontend/.env.example`):

| Variable | Meaning |
|---|---|
| `VITE_CLAUSE_CONTRACT_ADDRESS` | The canonical CLAUSE contract address on StudioNet. **Unset by design until Stage 6.** Missing/invalid values render an explicit "contract not configured / invalid" state; `undefined` never reaches the SDK. |
| `VITE_CLAUSE_NETWORK` | Development only: `localnet` targets a local simulator. Refused in production builds; production is locked to StudioNet (chain 61999). |

Target: stable GenLayer StudioNet (chain 61999, `https://studio.genlayer.com/api`, GEN), `genlayer-js` **1.1.8** pinned, injected EIP-1193 wallet. The app never asks for a private key.

### Contract integration test (local simulator only, no StudioNet, no user wallet)

Drives the real production adapter (call builders, transaction runner, decoders, finality verification, real `genlayer-js`) against the real contract on the local GenLayer simulator, using throwaway generated keys:

```bash
bash scripts/run_frontend_integration.sh        # starts a fresh glsim, deploys, runs the lifecycle, stops glsim
KEEP_GLSIM=1 bash scripts/run_frontend_integration.sh   # leaves it running; contract address in .scratch/local_address.txt
```

Then, for a local visual check: put `VITE_CLAUSE_NETWORK=localnet` and `VITE_CLAUSE_CONTRACT_ADDRESS=<that address>` in `frontend/.env.local` (git-ignored) and `npm run dev`. **Delete `.env.local` before a production build.**

## Contract - test and lint

```bash
python -m pytest tests/direct -q          # 626 direct-mode tests (model mocked; see STAGE_*_VERIFICATION.md)
genvm-lint lint contracts/clause_protocol.py
genvm-lint validate contracts/clause_protocol.py
genvm-lint schema contracts/clause_protocol.py
genvm-lint typecheck contracts/clause_protocol.py
python scripts/gen_frontend_interface.py --check     # ABI document in sync
bash scripts/run_real_web.sh tests/integration/test_real_settlement.py   # real local simulator, deterministic paths
```
(On Windows set `PYTHONUTF8=1` so `genvm-lint` can print its check marks.)

## What is and is not verified

Verified locally: the contract's deterministic behaviour, accounting, the frozen ABI, the frontend against the real contract on a local simulator. **Not verified anywhere yet (Stage 6 gates):** real-model adjudication and challenge review, real `web.render`, disagreement/undetermined rollback, real protocol timestamps, payable behaviour without the simulator shim, withdrawal-transfer finality, live StudioNet response shapes, injected-wallet signing. See `docs/STAGE_5_PRODUCT_RISKS.md` and `STAGE_5_VERIFICATION.md`.

## Important V1 limits

Maximum 10 adjudicable evidence records per claim (first-come); a warranty's maximum remedy is a lifetime cap shared by its claims (first-settled-first-served); unavailable evidence is not negative evidence; **warranties can be cancelled by the manufacturer or holder while no claim is unsettled** (flagged for release review). Full list: the app's `/limits` page.
