# CLAUSE — Frontend Information Architecture (Stage 0)

No frontend code exists yet. This freezes the page/route inventory and cross-cutting rules Stage 5
builds against.

## Cross-cutting rules (apply to every screen)

- Every write action shows its transaction lifecycle explicitly (submitted -> pending -> Accepted ->
  Finalized) and, after Finalized, re-reads and displays authoritative post-transaction contract state —
  never optimistically renders submitted values as confirmed (`TEST_MATRIX.md` §7,
  `NETWORK_AND_SDK_VERIFICATION.md`).
- Every timestamp is visually tagged with which of the nine time-facts it is (on-chain vs asserted vs
  source-published vs deadline) — never a bare date with no provenance indicator
  (`ARCHITECTURE.md`/`THREAT_MODEL.md`, timestamp provenance confusion).
- Every public page is fully readable with zero wallet connected. Wallet connection gates only the
  specific write action, never page access.
- `WarrantyPassport` display always surfaces governing constitution version, freeze timestamp,
  authoritative source, and any detected terms-drift indicator (`WARRANTY_CONSTITUTION.md`).
- Money-moving actions (settle/withdraw) are only ever enabled once the underlying state is genuinely
  FINAL/Finalized — a disabled-with-explanation state is shown otherwise, never a clickable action that
  would simply revert.

## Public (no wallet required)

- **Home** — protocol explanation, live aggregate stats (active warranties, claims, covered/not-covered
  counts, insufficient/unavailable-evidence counts, challenges/reversals/remands, total settled GEN — no
  invented subjective trust scores, per the design spec).
- **Warranty Explorer** — browse issued Programs/Constitutions/Passports.
- **Warranty Passport (detail)** — the full frozen record for one warranty, anti-rewrite indicators.
- **Claim Explorer** — browse Claims across the system, filterable by outcome/status.
- **Resolution Receipt (detail)** — the full public terminal record for one Claim.
- **Pool Transparency** — per-manufacturer pool balance/reserved/available (never per-holder financial
  detail beyond what's already public via Claims/Receipts).

## Holder (wallet required for writes, browsable without)

- **My Warranties** — the connected wallet's Passports.
- **File Claim** — description, failure-date assertion (visually marked non-authoritative), evidence
  submission (URL + category).
- **Evidence Locker** — per-claim submitted evidence, eligibility/retrieval status, frozen/unfrozen
  indicator, submitter identity.
- **Claim Timeline** — the full state-machine progress for one Claim, mapped to `STATE_MACHINES.md`'s
  lifecycle, plain-language labels for each state.
- **Challenge Decision** — file a Challenge (ground picker constrained to the fixed V1 grounds,
  mandatory citation field), or view an existing one's result.
- **Settlement/Withdrawal** — visible only once FINAL; shows remedy kind/amount before enabling
  withdrawal.

## Manufacturer (wallet required for writes, browsable without)

- **Create Program** — name, initial Constitution authoring (clauses, remedy table, deadlines, evidence
  categories, source policy) — an explicit "this becomes immutable once your first warranty issues"
  warning before the freezing action.
- **Fund Pool** — deposit GEN, live available/reserved balance.
- **Issue Warranty** — bind a Passport to a holder address + product identifier, shows the
  `available_balance` check result before submission (client-side preview only; the contract's own check
  is authoritative).
- **Claims Inbox** — Claims awaiting response, response-deadline countdown.
- **Respond/Counter-Evidence** — accept-no-contest or dispute + counter-evidence submission UI.
- **Challenge** — same Challenge Decision UI as holder, scoped to manufacturer-initiated Challenges.
- **Pool Capacity** — reserved/pending/available breakdown, per-Passport reservation drill-down.

## Deferred (not built until their build stage)

Frontend build itself is Stage 5, wired only against a schema verified live at that point — this
document is the frozen information architecture Stage 5 implements against, not a promise about exact
component structure, which is a Stage 5 decision.
