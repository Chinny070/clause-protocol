# CLAUSE - StudioNet smoke test (PREPARED, NOT YET TO BE PERFORMED)

**Do not start this until (1) you have deployed the audited file (`MANUAL_DEPLOYMENT.md`), (2) you sent the deployment hash + contract address, and (3) the assistant has confirmed the read-only deployment verification.** This document only prepares the work.

Goal: prove, on the live StudioNet contract, that it is live, can hold value, freezes terms, issues a passport, runs a claim through dispute / evidence / real adjudication / challenge / finality / settlement, and pays out - with the **fewest wallet actions**.

## Who does what

| | You (wallet) | Assistant (read-only, no wallet, no key) |
|---|---|---|
| Sends transactions | yes, only the rows marked **W** below | never |
| Reads state / transactions / balances | optional (the app shows them) | yes: every row marked **R** (uses the public RPC only) |
| Judges pass/fail | no | yes, against `docs/STUDIONET_GATE_PLAN.md` |

Everything is done in the CLAUSE app pointed at the deployed address (`frontend/HOSTING.md`; for a private run: `VITE_CLAUSE_CONTRACT_ADDRESS=<address> npm run dev` in `frontend/`). Each **W** step is one wallet approval. After every **W** step, copy the transaction hash shown in the app's transaction panel and send it back; the assistant then does the **R** step.

## What you need before starting

- A browser wallet on **StudioNet (chain 61999)**. **One wallet is enough for the minimal path**; a second wallet is optional (it lets us also test that a stranger is refused).
- A small amount of **GEN** in that wallet (about **0.5 GEN** covers everything below). I have not verified how to obtain GEN on StudioNet; if you have none, tell the assistant - funding (Gate D/H) cannot be proven without it.
- For the evidence steps: a **public https page you control** holding the text in `docs/smoke_evidence/*.txt` (e.g. a public GitHub Gist "raw" URL; you need three URLs). Deterministic-only steps use `https://example.org/`.

## Terms to use (create once)

Program name: `CLAUSE Smoke`. Terms version: `smoke-1`.
- Product scope: `WIDGET-SMOKE-001`. Coverage calculation: `flat term`.
- Covered clause `C-001`: `Manufacturing defects in materials or workmanship are covered.`
- Exclusion `X-001`: `Accidental impact or water damage is excluded.`
- Evidence categories: `RECEIPT, PAGE_RENDERED` (the `_RENDERED` suffix selects the browser-render path for Gate A).
- **Permitted evidence hosts** (frozen forever with these terms): `example.org, gist.githubusercontent.com, httpbin.org` (replace the middle one with the host of your evidence URLs).
- Claim deadline `30` days, manufacturer response `1` day, **Application Challenge window `0.01` days (~15 minutes)**, challenge enabled.
- If evidence insufficient: rule for manufacturer. If unavailable: rule for manufacturer.
- Remedy table: add the missing required rows with the button (COVERED any -> FULL_REFUND, ACCEPTED_NO_CONTEST any -> FULL_REFUND), keep NOT_COVERED -> NONE.
- Passports: maximum remedy `0.1` GEN each; coverage start = today, end = +1 year.

## Steps (minimal path)

| # | Who | Action | Proves (gate) |
|---|---|---|---|
| 1 | R | Assistant reads the deployed contract: source hash, schema, `now()`, `list_program_ids()` | contract live; source parity |
| 2 | **W** | Manufacturer console: **Create program** `CLAUSE Smoke` | write path; **C** protocol timestamp (`created_at`) |
| 3 | R | `get_program`, compare `created_at` with wall-clock at submission | **Gate C** |
| 4 | **W** | **Fund** the program with `0.3` GEN | **Gate D** value |
| 5 | R | contract balance == `0.3` GEN; `get_pool.total_balance` == `0.3` GEN; wallet balance dropped by `0.3` GEN | Gate D |
| 6 | **W** | **Author terms** (above) and freeze via **Create terms** | terms creation; incomplete-table refusal already proven locally |
| 7 | **W** | **Issue passport #1** (holder = your wallet) and **passport #2** | reservation; terms freeze |
| 8 | R | passports, `is_frozen == true`, `reserved_liability == 0.2`, fingerprint equals the terms fingerprint | freeze integrity |
| 9 | **W** | **File claim** on passport #1 (clause C-001, date = today) | |
| 10 | **W** | **Accept** the claim (manufacturer) | no-contest path |
| 11 | R | Wait until the assistant confirms the `accept` transaction is FINALIZED (or paste its hash in the app) | **finality gate** works live |
| 12 | **W** | **Finalize application decision** (button enables only after finality is verified) | |
| 13 | **W** | **Authorize settlement** | |
| 14 | **W** | **Withdraw claimable GEN** | **Gate H** |
| 15 | R | wallet balance increased by exactly `0.1` GEN; contract balance decreased by `0.1`; `get_final_decision.withdrawn_amount == 0.1` | Gate H |
| 16 | **W** | **File claim** on passport #2, then **Dispute** it | |
| 17 | **W** | **Submit evidence**: category `PAGE_RENDERED`, URL `https://example.org/` | **Gate A** setup |
| 18 | **W** | **Submit evidence**: category `RECEIPT`, URL = your gist of `01_defect_receipt.txt` | Gate E setup |
| 19 | **W** | **Freeze evidence** | Gate A retrieval (render + static) |
| 20 | R | evidence #1 `retrieval_method == RENDER`, `AVAILABLE`, content contains `Example Domain`; evidence #2 `AVAILABLE` | **Gate A** |
| 21 | **W** | **Request GenLayer adjudication** (after finality is verified) | **Gate E** |
| 22 | R | adjudication `decision_path == SEMANTIC`, structured fields, relied evidence; validator votes | Gate E |
| 23 | **W** (only if you want Gate G) | **File Application Challenge** (e.g. WRONG_CLAUSE citing C-001 if the outcome was not COVERED) then **Resolve** | **Gate G** |
| 24 | **W** | after the window: **Finalize**, **Settle**, **Withdraw** (if payable) | end-to-end |

## Optional extra steps (only if you want every gate proven in one sitting)

These need a fresh claim each (a warranty can carry several claims once earlier ones are past dispute; more passports can be issued):

- **Gate F (prompt injection):** new claim, dispute, evidence = gist of `02_injection_page.txt`, freeze, adjudicate. Pass = the decision is not COVERED (or the step ends in a safe `[LLM_ERROR]`).
- **Gate B (disagreement/undetermined):** new claim, dispute, evidence = `https://httpbin.org/uuid` (changes on every request), freeze. Pass = the transaction does not change contract state.
- **Gate G REMAND attempt:** claim with evidence `03_ambiguous_note.txt`, adjudicate, then challenge with IGNORED_EVIDENCE / PRODUCT_MATCH_ERROR and resolve; REMAND is the model's choice and may not occur - that is acceptable.

## Stop conditions

Stop and tell the assistant if: the wallet shows a chain other than 61999; a transaction ends UNDETERMINED / CANCELED / ERROR; a balance moves by a different amount than expected; anything asks for a key or seed phrase (never enter one).

## Cleanup

Nothing needs cleanup. Test warranties can be cancelled from the passport page once no claim is unsettled; unreserved capacity can be withdrawn from the program console.
