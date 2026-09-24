# CLAUSE - Stage 5 Verification (Production Frontend)

## 1. Verdict: PASS WITH BLOCKERS
The complete frontend is built against the frozen contract interface, verified against the **real contract on a local simulator** with the real `genlayer-js` 1.1.8, and covered by 107 component/unit tests. Blockers are Stage 6 gates: nothing here touched StudioNet, an injected wallet, a real model or real `web.render`.

## 2. Stack
Vite 6.4 + React 18.3 + TypeScript 5.7 + react-router 7.18 (hash routes) + `genlayer-js` **1.1.8 (exact pin)** + viem 2.x; Vitest 3.2 + Testing Library; ESLint 9 (+ jsx-a11y). No backend, database or scraper. `npm audit --omit=dev`: **0 vulnerabilities** (react-router upgraded 6 -> 7 to clear two advisories); the only remaining advisory is a moderate dev-tooling one in `@vitest/mocker` (test runner only, not shipped).

## 3. Design reference
Reinspected getdesign.md's Nintendo (2001) DESIGN.md: brushed-metal panels, beveled hardware plates, amber signals on a dotted carbon bar, outlined Arial-Black box-art type. Adapted, not copied: the structural material language (metal/plastic plates, dotted bar -> perforated evidence strips and the dotted petroleum nav, outlined display type -> outlined hero) rebuilt in CLAUSE's own palette (oxidized copper, antifreeze mint, warranty-paper ivory, laser red, bruised plum, safety-label yellow, deep petroleum blue) on a light paper ground. Signature motifs implemented: Warranty Passport, clause stickers, evidence inspection strips, timestamp seals (with provenance), diagnostic timeline + stage strip, FROZEN TERMS stamp, thermal Resolution Receipt, capacity gauge, and two visually separate families for Application Challenge (plum) and GenLayer Protocol Finality (mint/petroleum double border).

## 4. Routes
`/` landing · `/explore` warranty explorer · `/passport/:id` · `/passport/:id/claim` guided claim form · `/claim/:id` (timeline, Evidence Locker, adjudication, Application Challenge, finality steps) · `/receipt/:id` · `/holder` · `/manufacturer` · `/manufacturer/program/:id` (Warranty Capacity + inbox) · `/manufacturer/program/:id/terms/new` (authoring wizard + FROZEN review) · `/manufacturer/program/:id/issue` · `/program/:id` (public pool transparency) · `/limits` (V1 limits) · 404.

## 5. Public, no-wallet experience
Landing, explorer, passports (frozen terms, fingerprint, clauses, exclusions, remedy table, capacity, cancellation status), claims (Evidence Locker, structured adjudication, Application Challenge history, timeline), pool transparency and Resolution Receipts (shareable, printable) all read with a read-only client; a test asserts no account/sign request is made while browsing.

## 6. Manufacturer flow
Create program; fund capacity (payable, exact GEN parsing); withdraw unreserved capacity; guided terms authoring (clauses, exclusions, source policy, categories, deadlines, challenge enable/window, evidence-gap behaviours, remedy table) with live **remedy-completeness** verification and one-click "add the missing required rows"; review screen with `FROZEN TERMS - THIS VERSION CANNOT BE SILENTLY REWRITTEN AFTER ISSUANCE` and an explicit acknowledgement; issue a passport (SHA-256 product commitment, capacity preview); pause/resume/retire; claims inbox; accept / dispute a claim; submit evidence; file Application Challenge; freeze / adjudicate / resolve steps; inspect settlement.

## 7. Holder flow
Connect; My warranties (passports, claims, claimable GEN); open passport; guided claim (choose covered clauses, exclusions shown, claimant-asserted failure date clearly marked unverified, claim deadline, evidence rules, "Maximum 10 adjudicable evidence records" and slots); evidence submission with eligibility preview; follow timeline; inspect adjudication; file Application Challenge; inspect final decision; finality-gated finalize/settle/withdraw.

## 8. Evidence Locker
Per record: id, URL, host, category, submitter (holder/manufacturer labelled), eligibility, retrieval method, submitted/retrieved/frozen seals, availability, fingerprint, frozen state, bounded extracted content. AVAILABLE / FETCH_FAILED (/RENDER_FAILED/INSUFFICIENT) / INELIGIBLE / FROZEN are distinct by glyph + text + border style, with the explanation "does NOT mean the claim is false ... not treated as proof against either party".

## 9. Adjudication UI
Every frozen schema field is its own row (outcome, product match, warranty version match, coverage window, covered clauses, exclusions, evidence sufficiency, source authority, evidence relied on/considered, bounded rationale, decision path in plain words). INSUFFICIENT_EVIDENCE ("This is NOT a finding that the claim is false"), EVIDENCE_UNAVAILABLE, NOT_COVERED and INVALID_CLAIM each have distinct labels/tones/explanations; a test asserts they are never collapsed to "rejected".

## 10. Application Challenge UI
Uses the exact phrase everywhere; states it contests a material CLAUSE adjudication error, is not a GenLayer Protocol Appeal, cannot add evidence, one per claim; window shown from protocol time; the seven frozen grounds with per-ground blurbs and "decided deterministically / reviewed by validators"; ground-specific citation pickers (only frozen, eligible-for-that-ground evidence and clauses); 1,000-char bounded explanation; review screen; history display (ground, explanation, citation, result semantics, resolution path, corrected decision); resolve / remand / lapse steps.

## 11. GenLayer Protocol Finality UI
A separate component family. Before finalize / settle / withdraw (and adjudicate / challenge steps) the app verifies the prerequisite transaction live from GenLayer: only `FINALIZED` with a successful leader execution is "Safe to continue"; ACCEPTED, pending, undetermined, unknown or unreadable states block (fail closed). Hash source: this browser's journal or a hash the user pastes.

## 12. Finality checklist / explained disabled buttons
`domain/checklist.ts` produces per-action checklists (state, windows, recipient, claimable, wallet, finality). Every non-ok item has a plain explanation ("Application Challenge window still open", "Application Challenge unresolved", "Final decision not yet finalized", "Settlement not finalized", "Waiting for GenLayer finality ..."); the button carries `aria-describedby` to the reason. A test sweeps every action x claim status x finality state and asserts no blocked state is unexplained.

## 13. Resolution Receipt
Thermal-receipt treatment (perforated edges, monospace, dashed sections, barcode, FROZEN TERMS stamp, print animation): product/warranty, constitution fingerprint, claim, targeted clauses, evidence ids + fingerprints (ineligible counted), original adjudication (marked SUPERSEDED when corrected), Application Challenge, corrected adjudication, final decision, deterministic remedy, settlement (capped flag), withdrawal, timestamps, shareable link, print. No wallet required.

## 14. Wallet / network handling
States: unsupported, disconnected, connecting, connected, wrong network (banner + switch), rejected, error; contract states: not configured, invalid, network error, checking, RPC unavailable, contract read failed / unexpected response, OK. Standard EIP-3326/3085 (the SDK's snap-based `connect()` is deliberately not used; Studio chains skip the SDK's chain check so the app enforces it). No key is requested; a static test forbids key handling.

## 15. Transaction lifecycle
prepare -> wallet confirmation -> submitted (hash journaled + shown, copyable) -> consensus -> accepted -> **protocol finality (FINALIZED + successful execution)** -> authoritative contract reread -> UI update. A hash is never success; FINALIZED + ERROR/unknown is failure; undetermined / canceled / timeout / stuck-at-ACCEPTED are distinct outcomes; the panel (aria-live) shows each step and technical diagnostics; nothing is optimistically mutated.

## 16. Contract adapter / API
`src/contract/{calls,reader,decode,transport}.ts`: 22 write builders + 18 typed views mapped 1:1 to the frozen ABI (`abi-parity.test.ts` parses the frozen interface document); `ClauseTransport` = exact subset of the stable client (mock in unit tests, real client in production/integration); strict decoders normalize SDK numerics (small ints as numbers, >2^53 as decimal strings) to `bigint`.

## 17. Local contract integration result
`tests/integration/adapter.integration.test.ts` **passes** (rerun on a fresh simulator after the final code): deploy; health reads; create program; payable `fund_pool`; `create_constitution` with a `REPAIR_CREDIT` value of 1e18 (above 2^53) round-tripping exactly; the contract **refusing an incomplete remedy table** (FINALIZED-with-ERROR reported as a failure); two warranties; **no-contest lifecycle** accept -> finalize -> settle -> withdraw (wrong caller rejected, double withdraw rejected, receipt decodes); **dispute lifecycle** with real web retrieval, deterministic adjudication (window FAIL), Application Challenge (TEMPORAL_ERROR) resolved deterministically, finalize, zero settlement; finality verification of a real transaction hash; unknown ids decode to null. Uses throwaway generated keys on a local simulator; no StudioNet, no user wallet/key. Not exercised: real model, real render, injected-wallet signing (Stage 6).

## 18. Responsive / accessibility result
Real-browser check at 375x812 across 14 routes (/, /explore, passport, claim form, claims 1-2, receipts 1-2, /limits, /manufacturer, /holder, program console, terms wizard, issue): `scrollWidth == viewport width` on every route (no horizontal scroll, no clipped fingerprints/addresses/URLs/hashes/tables); the only flagged elements were the off-screen skip link and a stamp caught mid-animation. Tables collapse to labelled cards; timelines/strips reflow. Accessibility: skip link, landmarks, single h1, labelled controls, 44px targets, visible focus (3px plum), `aria-live` transaction status, status never colour-only (glyph + text), timeline/checklist state announced in text, reduced-motion support (all animation in a `prefers-reduced-motion: no-preference` block; tested). Not run: an automated contrast checker or screen reader (palette chosen for contrast, not measured).

## 19. Frontend tests / build
`npm test`: **107 passed** in 8 files. `npm run test:integration`: 1 passed. `tsc`: clean. `eslint` (typescript-eslint + react-hooks + jsx-a11y): clean. `vite build`: succeeds (875 kB JS / 217 kB gzip, 17.5 kB CSS); the bundle contains no contract address and no dev-network selection. Python contract suite untouched by this stage (626 passing at the freeze; `contracts/clause_protocol.py` is byte-identical to HEAD).

## 20. Bugs found and fixed
`remedy_value` overflowed a safe integer for large `REPAIR_CREDIT` values (now `bigint` end to end); the SDK returns >2^53 amounts as strings (decoder normalizes); the `FROZEN TERMS` stamp overlapped a passport field (moved into the header); ineligible evidence was not citable for `SOURCE_AUTHORITY_ERROR` in the form (candidate list fixed); test journal state leaked between tests (storage cleared); react-router 6 advisories (upgraded to 7); the dev-server ephemeral-key helper lived in `src` (moved to `tests/` so no key generation ships).

## 21. V1 limitations surfaced
Maximum 10 evidence records / first-come slots (claim form, Evidence Locker, /limits); lifetime warranty cap, first-settled-first-served (passport capacity note, receipt `capped`, /limits); unavailable evidence not negative (Evidence Locker, outcome copy); **unilateral cancellation** (every ACTIVE passport, cancelled banner, wizard note, /limits); unavailable/insufficient policy shown on the frozen terms.

## 22. Unresolved risks
See `docs/STAGE_5_PRODUCT_RISKS.md`: cancellation policy decision; finality-hash discovery (journal or paste); explorer scalability (no indexer, no list methods for constitutions); unverified StudioNet response shapes and wallet signing; semantic steps never run with a real model.

## 23. Stage 6 gates
1. Deploy to StudioNet and insert the canonical address via `VITE_CLAUSE_CONTRACT_ADDRESS`. 2. Verify the live `getTransaction`/receipt shape (status names, `consensus_data.leader_receipt[0].execution_result`). 3. Injected-wallet signing of every write on chain 61999 (and wrong-network handling with a real wallet). 4. Real ACCEPTED -> FINALIZED timing; confirm the finality gate behaves. 5. Real `web.render` for `*_RENDERED` categories. 6. Validator-disagreement / undetermined rollback observed live. 7. Real-model adjudication, real-model injection resistance, real-model challenge review / remand. 8. Real payable behaviour without the shim; withdrawal transfer emitted only after finality; real balance movement. 9. Protocol timestamp behaviour. 10. Decide the unilateral-cancellation policy. 11. Decide hash-discovery UX (indexer vs paste). 12. Hosting/CORS check of the static bundle against the StudioNet RPC.

## 24. Files
New: `frontend/**` (src, tests, configs, lockfile), `README.md`, `docs/{STAGE_5_SDK_VERIFICATION,STAGE_5_PRODUCT_RISKS,FRONTEND_ARCHITECTURE,FRONTEND_TEST_MATRIX}.md`, `scripts/run_frontend_integration.sh`, this file; `.gitignore` additions. Contract, contract tests and earlier docs unchanged.

## 25. Git
Committed on `master` (hash in the final message).

## 26.
contracts/clause_protocol.py was not modified.

## 27.
No StudioNet contract deployment was performed and no user wallet/private key was used.
