# CLAUSE — Architecture (Stage 0 freeze)

## Thesis

A warranty is only as good as who gets to interpret it. CLAUSE is **Precommitted Warranty
Adjudication**: a manufacturer freezes coverage rules before any dispute exists; a customer holds an
immutable Warranty Passport bound to those frozen rules; a disputed claim is decided by GenLayer
validators reasoning over frozen, retrieved, admissible evidence against the frozen rules; a
deterministic remedy table — never the semantic layer — moves GEN.

## Two layers, strictly separated

**Truth layer** (non-deterministic, GenLayer-adjudicated): does the frozen admissible evidence establish
that the failure satisfies the frozen warranty conditions? Produces a structured verdict (see
`ADJUDICATION_SCHEMA.md`) — never a payout number.

**Money layer** (deterministic, plain Python): given the finalized structured verdict, what settlement
follows? Reads a precommitted remedy table; the semantic layer never sees pool balance, payout size, or
party preference (`ECONOMIC_INVARIANTS.md`, Counterfactual Independence).

## System shape

```
Browser frontend (Next.js, genlayer-js)
        |
        v
GenLayer Intelligent Contract (single contract, Python/GenVM)
        |
        +--> GenLayer validators (Optimistic Democracy consensus)
        +--> Public evidence sources (via gl.nondet.web.*, inside the IC only)
        |
        v
Injected wallet (holder / manufacturer signs writes)
```

No backend. No Supabase/Firebase/Fly.io. No centralized scraper. No hidden database. No private
adjudication server. Every consensus-critical read (evidence retrieval, semantic judgment) happens
inside the Intelligent Contract via GenVM's non-deterministic block primitives, never in the frontend.
The frontend's only job re: evidence is to submit a URL/reference and later render what the contract
already froze — it never decides admissibility or scrapes on the contract's behalf.

Target network is stable Studionet only (chain 61999, RPC `https://studio.genlayer.com/api`) — see
`NETWORK_AND_SDK_VERIFICATION.md` for the full verified network/API baseline this architecture assumes.

## Core objects (see `DATA_MODEL.md` for exact storage-compatible shapes)

`WarrantyProgram` → `WarrantyConstitution` (immutable once a warranty issues under it) → `Clause`
(covered `C-*` / excluded `X-*`) → `WarrantyPassport` (per-holder, frozen at registration) →
`WarrantyPool` (manufacturer-funded GEN, reservation-accounted) → `Claim` → `EvidenceRecord` (frozen,
immutable once adjudication begins) → `Adjudication` (the structured verdict) → `Challenge`
(application-level appeal, distinct from GenLayer protocol appeal) → `ResolutionReceipt` (public,
permanent).

## Why one contract, not several

A single Intelligent Contract holds Programs/Constitutions/Passports/Pool/Claims/Evidence/
Adjudications/Challenges/Receipts. This keeps evidence freeze, adjudication, and settlement inside one
consensus boundary — cross-contract calls are forbidden inside GenVM non-deterministic blocks (confirmed
across every prior GenLayer project in this workspace), so splitting adjudication logic across contracts
would force consensus-critical calls to cross a boundary GenVM does not support. Deferred extensions
(transferable warranties, recall notices, marketplace interoperability) are designed to be additive
fields/methods on the same contract, not separate contracts, until proven otherwise.

## Anti-rewrite protection

`WarrantyConstitution` fields are write-once at issuance time (see `DATA_MODEL.md`). The
`WarrantyPassport` stores the constitution's version/fingerprint and the authoritative source policy at
the moment of registration. A later edit to a manufacturer's public terms page cannot retroactively
change an issued warranty — the frontend must show governing version, freeze timestamp, authoritative
source, and any detected terms drift (comparing current source content against the frozen fingerprint,
computed as a read-only diagnostic, never used to mutate the frozen constitution).

## Time discipline

Nine distinct time facts are tracked and never conflated (full rules in `DATA_MODEL.md` /
`STATE_MACHINES.md`): on-chain registration/freeze timestamp, asserted purchase/coverage date, coverage
expiry, claimant-asserted failure date, source-published date, evidence submission/retrieval/freeze time,
response deadline/response time, adjudication time, challenge open/close/file/resolve time, and
finality/settlement/withdrawal time. A date printed on a webpage or photo is data, never a timestamp.

## Build-stage boundary (this document is Stage 0 only)

Stage 0 = this architecture freeze, docs only. No contract code, no frontend code, no deployment. See
`STAGE_0_AUDIT.md` for the completion report and the proposed Stage 1 scope.
