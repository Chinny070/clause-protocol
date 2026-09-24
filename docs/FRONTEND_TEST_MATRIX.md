# Frontend test matrix (Stage 5)

`cd frontend && npm test` runs 106 tests in 8 files (jsdom + Testing Library; the contract is a **mock transport implementing the exact genlayer-js subset the app uses**). `npm run test:integration` (via `scripts/run_frontend_integration.sh`) runs 1 lifecycle test against the **real contract on a local simulator** with the real SDK.

| Required area (brief §29) | Tests |
|---|---|
| Contract adapter | `reader.test.ts` (typed views, error classes, evidence fan-out), `abi-parity.test.ts` (22 write builders vs the frozen interface document: names, order, arity, payable-only `fund_pool`; argument validation; citation keys) |
| State decoding | `decode.test.ts` (number / decimal-string / bigint amounts, `{}` -> null, malformed shapes throw), integration test (real decoded data incl. a 1e18 remedy value) |
| Lifecycle transitions | `domain.test.tsx` (finality prerequisites per action, per-status explanations, stage strip, timeline provenance) |
| Wallet states | `pages-actions.test.tsx`: unsupported, disconnected -> connecting -> connected, rejected, wrong network + switch; no key/sign methods ever requested |
| Wrong network | wallet test + banner (`chain 1` vs `61999`); `runTransaction` blocked when not on the target chain (TxProvider) |
| Transaction failure / undetermined | `tx.test.ts` (rejected, FINALIZED+ERROR, unverifiable result, UNDETERMINED, CANCELED, timeout, stuck ACCEPTED, transient read errors, reread failure), UI failure + rejection panels |
| Finality gating | `tx.test.ts` (only FINALIZED+SUCCESS is safe), `domain.test.tsx` (every action x status x finality state: non-ok items always explained; non-safe finality always blocks), `pages-actions.test.tsx` (no hash -> disabled with reason; ACCEPTED hash -> disabled; Finalized hash -> enabled -> explicit confirmation -> exact write -> reread) |
| Authoritative reread | `tx.test.ts` (reread only after finality; failed reread surfaced; no data invented), UI success message only after reread |
| Evidence states | `pages-public.test.tsx` (AVAILABLE / FETCH_FAILED / INELIGIBLE / frozen, explanations, slots 2/10) |
| Claim forms | `pages-actions.test.tsx` (guided form, asserted-date warning, 10-record limit, deadline), evidence submit preview (https only, host policy, slots) |
| Challenge forms | seven frozen grounds, ground-specific citation pickers, 1,000-char bound, review step, "not a GenLayer Protocol Appeal", window-closed explanation, finality item |
| Remedy / settlement display | passport remedy table, final decision view, receipt (remedy, settled, capped, withdrawn) |
| Withdrawal states | recipient only, claimable > 0, finalized settle tx, non-recipient / already-withdrawn reasons, integration: already-withdrawn and nothing-to-withdraw errors from the real contract |
| Public explorer | listing, passport page (FROZEN TERMS, fingerprint, clauses, exclusions, remedy table, capacity, cancellation status), not-found |
| Resolution Receipt | full receipt render with no wallet, superseded/corrected decisions, fingerprints |
| Mobile rendering | CSS contract tests (tables collapse to cards, grids stack, identifiers wrap, 44px targets) + **real-browser overflow check at 375px** over 14 routes (no horizontal scroll; recorded in `STAGE_5_VERIFICATION.md`) |
| Accessibility | skip link, landmarks, single h1, named controls, labelled form controls, badges always glyph+text, timeline/checklist expose state in text, reduced-motion (every animation inside `prefers-reduced-motion: no-preference`), visible focus |
| Release hygiene | static guards: no hard-coded addresses, no key handling, no mock/demo switch, no backend/DB deps, no Studio-Next/RC/61997 references, `genlayer-js` pinned to 1.1.8; config tests (not configured / invalid / network error / production refuses localnet) |
| Contract integration | `tests/integration/adapter.integration.test.ts` |

Known gaps: no visual-regression or automated screen-reader run; contrast is by palette design (not measured by an automated tool); wallet signing against StudioNet is untested (no wallet used).
