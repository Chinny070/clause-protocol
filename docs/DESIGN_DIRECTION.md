# CLAUSE — Design Direction (Stage 0)

Source: the user's DESIGN.md collection at `getdesign.md` (catalog browsed live 2026-09-23, 550+
entries). Selection made against CLAUSE's own brief direction — **industrial product-registration
graphics + thermal warranty receipts + inspection stamps + translucent diagnostic plastic** — not against
generic visual appeal, and deliberately not reusing HashiCorp (already the Protocol Court pick in this
workspace) or any generic dark crypto-dashboard template.

## Selected template: Nintendo (2001)

Catalog description: "Y2K 'console chrome' web. Brushed-periwinkle metal panels, amber nav on a dotted
carbon bar, outlined Arial-Black box-art type."

**Why this is the strongest fit, not just an available one:** the spec's own signature motif —
"translucent diagnostic plastic" — is not an abstract metaphor for CLAUSE, it is literally the material
language of the era Nintendo (2001) draws from (iMac G3, Game Boy Color, the whole translucent-plastic
consumer-electronics wave). CLAUSE is a warranty protocol *for physical products*; a design system built
from the actual visual vocabulary of warranted consumer hardware from that period is a closer semantic
match than any purely financial/crypto/enterprise template in the catalog (HashiCorp, IBM, Coinbase,
etc.) — those read as "blockchain app," this reads as "the product you bought." The brushed-metal panel
+ dotted carbon bar + outlined box-art type also directly supports two other named motifs: inspection
strips (dotted/perforated bar treatment) and diagnostic timelines (panel-based module layout is a natural
fit for a step-by-step claim lifecycle).

## Adaptation, not reuse

The original Nintendo (2001) palette (periwinkle/amber/carbon) is **replaced entirely** with CLAUSE's own
frozen palette — nothing from the source's color values carries over, only its structural/material
language:

- **Oxidized copper** — primary structural accent (panel edges, seals, frame lines) — reads as
  "inspected metal," reinforcing the industrial-inspection register.
- **Antifreeze mint** — secondary accent for ACTIVE/covered/positive states.
- **Warranty-paper ivory** — primary background/surface, evoking thermal-receipt paper stock rather than
  a dark "app" canvas — deliberately *not* a dark-mode-first crypto aesthetic.
- **Laser red** — reserved exclusively for FROZEN TERMS stamps, exclusions, and NOT_COVERED states — a
  scarce, high-signal color per this workspace's own repeated lesson (Protocol Court reserved its gold
  accent "ONLY for finality/authority moments") that a single accent overused loses meaning.
  - **Bruised plum** — Challenge/dispute-in-progress states.
- **Safety-label yellow** — RESPONSE_WINDOW/pending-deadline countdown states, inspection-stamp
  borders.
- **Deep petroleum blue** — manufacturer-facing surfaces (Create Program, Fund Pool, Claims Inbox),
  distinguishing manufacturer chrome from holder-facing warranty-paper-ivory surfaces at a glance.

## Signature motifs, applied where

- **Warranty Passport** — rendered as a physical passport/inspection-tag card: brushed-panel frame
  (from the source template's material language), FROZEN TERMS stamp overlay in laser red once issued.
- **Clause stickers** — small rounded-corner label chips (covered = mint border, excluded = red border),
  echoing box-art badge treatment from the source.
- **Evidence inspection strips** — dotted/perforated horizontal dividers (adapted from the source's
  dotted carbon nav bar) separating each EvidenceRecord in the Locker.
- **Timestamp seals** — circular stamp graphics on every on-chain timestamp specifically (never on
  claimant-asserted or source-published dates, reinforcing the provenance-tagging rule in
  `FRONTEND_INFORMATION_ARCHITECTURE.md`).
- **Diagnostic timeline** — the Claim Timeline screen as a horizontal panel-segmented strip, one segment
  per state-machine stage, active segment lit in antifreeze mint.
- **FROZEN TERMS stamp** — laser red, angled, applied to the Constitution display the instant
  `is_frozen == True`.
- **Resolution Receipt** — literally thermal-receipt-styled: narrow column, ivory ground, monospace
  totals block for remedy amount, perforated top edge.
- **Pool-capacity gauge** — a physical gauge/dial graphic (reserved vs available), petroleum-blue face.
- **Challenge/finality indicators** — two visually distinct badge families so a viewer never confuses
  "application Challenge resolved" with "GenLayer protocol Finalized" (`APPEALS_AND_FINALITY.md`'s core
  distinction) — plum badge for Challenge status, mint/ivory seal badge for protocol Finality.

## What this explicitly is not

Not a dark, glass, gradient-heavy "Web3 dashboard" (the look this workspace has already used for
AgentCourt/Continuum/Protocol Court's obsidian-glass systems) — CLAUSE's register is light-ground,
paper/plastic/metal materiality, deliberately closer to a physical consumer-product warranty card than to
a trading terminal. This is a Stage 0 direction only; exact component library/CSS implementation is a
Stage 5 decision.
