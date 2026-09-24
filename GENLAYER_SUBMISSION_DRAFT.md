# CLAUSE - GenLayer submission draft (NOT SUBMITTED)

Fill the placeholders only after deployment and after the read-only verification passes. Do not submit anything with an unverified claim.

## Project
- **Name:** CLAUSE
- **One-liner:** Warranty terms that freeze before the dispute: independent evidence, GenLayer validator consensus, and a remedy chosen only from a table committed in advance.
- **Website:** `<WEBSITE URL - placeholder until the frontend is published and checked>`
- **Contract address (StudioNet, chain 61999):** `<CONTRACT ADDRESS - placeholder>`
- **Explorer address:** `<STUDIONET EXPLORER URL FOR THE CONTRACT - placeholder>`
- **Deployment transaction:** `<DEPLOY TX HASH - placeholder>`
- **Source SHA-256 of the deployed file:** `07d7e4bfdbaeeba2d30129c00034cd728681ed99877286a16189005fbe7d847e`
- **Repository / source:** `<REPO URL - placeholder>` (`contracts/clause_protocol.py`)

## Full description
A warranty is only as good as who gets to interpret it. In a traditional warranty the manufacturer writes the terms, interprets them, and decides whether to pay. CLAUSE splits those roles on GenLayer.

1. **Terms freeze.** The manufacturer defines covered clauses, exclusions, an evidence source policy, deadlines and a precommitted remedy table. The terms are canonicalized and fingerprinted, and freeze the moment the first warranty is issued against them. The contract refuses a remedy table that would leave any payable outcome without a remedy.
2. **Capacity is reserved.** Each Warranty Passport reserves its maximum remedy from the manufacturer's pool up front, so a later withdrawal cannot starve a valid claim.
3. **Evidence is independent.** Only https sources allowed by the frozen policy are retrieved, through validator consensus, then frozen with fingerprints (maximum 10 records per claim). Unavailable evidence is never treated as proof against either party.
4. **GenLayer validators decide structured findings**, not prose: product match, warranty version, coverage window, established clauses and exclusions, evidence sufficiency. Plain code derives the outcome and picks the remedy from the frozen table; no model chooses an amount, percentage or recipient.
5. **One Application Challenge** (a bounded, deterministic-first review of a specific error - distinct from GenLayer's protocol appeal) can correct a decision; history is never deleted.
6. **Settlement is pull-payment**, gated by protocol finality, and a public **Resolution Receipt** shows the whole chain from frozen terms to withdrawal.

**Honest limits (V1):** 10 evidence records per claim (first-come); a warranty's maximum remedy is shared by its claims; warranties can be cancelled by the manufacturer or holder while no claim is unsettled (disclosed in the app).

## Tags
`genlayer` `intelligent-contract` `warranty` `insurance` `dispute-resolution` `optimistic-democracy` `web-evidence` `real-world-assets` `studionet`

## How to try it (no wallet needed to read)
1. Open `<WEBSITE URL>` and click **Explore warranties**.
2. Open a **Warranty Passport**: read the frozen clauses and the fingerprint.
3. Open its **claim**: Evidence Locker (fingerprints), structured adjudication, Application Challenge history, timeline.
4. Open the **Resolution Receipt**.
5. To transact: connect a wallet on StudioNet (61999) and follow **Manufacturer** (create program, fund, author terms, issue) and **My warranties** (file claim, add evidence).

## Steward-verifiable outcome (externally checkable, no trust in this project)
For the demo claim `<CLAIM ID>` on contract `<CONTRACT ADDRESS>` a steward can verify, using only public StudioNet data (explorer or `readContract`/`getTransaction`):
1. **Source parity:** the deployed source hashes to `07d7e4bf…847e`, equal to the audited repository file.
2. **Frozen terms:** `get_passport(<ID>).constitution_fingerprint == get_constitution(<ID>).fingerprint == get_claim(<CLAIM ID>).constitution_fingerprint`, and `get_constitution(...).is_frozen == true` with `frozen_at` earlier than the claim's `filed_at`.
3. **Independent evidence:** each frozen evidence record's `fingerprint` and `retrieved_at`/`frozen_at`, from a host permitted by the frozen `source_eligibility_policy`; re-fetching the URL shows the same bounded content.
4. **Validator consensus:** the adjudication transaction `<ADJUDICATION TX HASH>` is `FINALIZED`, its leader execution is `SUCCESS`, and the validators' votes are recorded in the receipt (`getTransaction(...).consensus_data`); `get_adjudication(<ID>).decision_path == "SEMANTIC"`.
5. **Precommitted remedy:** `get_final_decision(<CLAIM ID>).remedy_amount` equals the amount the frozen `remedy_table` row yields for the final outcome (FULL_REFUND = the passport's `max_deterministic_remedy`), independent of the model's text.
6. **Real value movement:** the settle/withdraw transactions `<TX HASHES>` are `FINALIZED`; the holder's balance increased by exactly `withdrawn_amount` and the contract's balance decreased by the same amount (`eth_getBalance` before/after).

## Demo-video checklist (do not record until the smoke test has passed)
- [ ] Landing page: the thesis and the "traditional vs CLAUSE" comparison (10 s)
- [ ] Explore a public passport with no wallet: FROZEN TERMS, fingerprint, clauses (20 s)
- [ ] Manufacturer: create terms, remedy-completeness check, FROZEN review screen (30 s)
- [ ] Holder: file a claim, submit evidence, see the Evidence Locker freeze (30 s)
- [ ] Adjudication: structured findings, INSUFFICIENT vs NOT_COVERED wording (20 s)
- [ ] Application Challenge (labelled distinctly from protocol finality) (20 s)
- [ ] GenLayer Protocol Finality checklist enabling settle, then withdraw (20 s)
- [ ] Resolution Receipt and the steward verification calls above (30 s)
- [ ] Show the V1 limits page (10 s)
- [ ] No private keys, seed phrases or unrelated wallets visible; StudioNet chain 61999 visible in the wallet
