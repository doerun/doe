# 15 — Where the analogy breaks down

## Goals

The discipline page paired with slide 14. State explicitly what TSIR
does *not* do. Without this slide, the deck reads as overclaim. With
it, the deck reads as a structural-property argument with known limits.
This slide is non-negotiable for evidence-discipline reasons.

## What it shows

A bulleted list of explicit non-claims, each one a sentence:

- **TSIR does not replace performance tuning.** Backends still differ
  in achieved throughput. The IR contract is correctness-of-shape,
  not equal-speed-across-backends.
- **Adding a kernel is not free.** New body ops require: (a) interpreter
  coverage in `reference_interpreter.zig`, (b) per-backend emitter
  branches, (c) fixture coverage under `runtime/zig/tests/tsir/real/`.
- **Spatial compute is not made fast by TSIR.** The IR makes the
  lowering correct; achieved performance on Cerebras WSE depends on
  PE-grid sizing, fabric collective choices, and SDK version, none
  of which TSIR controls.
- **The bundle pipeline is not yet end-to-end demonstrated against
  hardware.** Two surfaces (WebGPU, simfabric) have receipts in hand;
  the hardware surface (R2-10) is the single outstanding gate, blocked
  on coordination (bundle circulation or endpoint access), not on
  engineering.

Caption: "The deck makes a shape claim, not a performance claim, not
a coverage claim, and not a demonstrated-end-to-end claim."

## What it might look like

Single column of stacked claim/non-claim pairs. Each pair: the claim
text in normal weight on the left, the bounded scope text in italic
on the right. No diagrams; intentionally text-only to anchor the
deck's discipline. Top of slide carries a small "honest scope" badge.

### Visual spec (per design tokens)

- **Layout pattern:** `text-list-discipline`.
- **Top of slide — "honest scope" badge:** small rounded-rectangle
  pill (~140×32), `red.dim` fill, `red.opaque` stroke 1 px,
  `red.opaque` text *"HONEST SCOPE"* in sans-serif 700, 11 px,
  letter-spaced. Visually distinct from the rest of the slide so a
  reader's eye lands on it first.
- **Body — stacked claim/non-claim rows:**
  - Each row is a two-column layout (~640 px left, ~640 px right,
    24 px gap).
  - Left column (the bounded claim): sans-serif 600, `neutral.body`,
    14 px, with a leading `red.opaque` warning-glyph (a small
    triangle or `!` in a circle, 14×14).
  - Right column (the scope text): sans-serif 400, italic,
    `neutral.body`, 14 px.
  - Rows separated by `neutral.line` 1 px horizontal rules with 24
    px vertical padding.
- **Caption strip at slide bottom:** italic 12 px, `neutral.body`,
  *"The deck makes a shape claim, not a performance claim, not a
  coverage claim, and not a demonstrated-end-to-end claim."*
- **Persistent elements reused:** none — this slide is intentionally
  text-only.

## What it doesn't claim

This slide *is* the "what it doesn't claim" slide. Meta: the slide's
own non-claim is that this list is exhaustive — there will be other
limits not enumerated here. Future revisions should append, not
delete.

## Source artifacts to cite

- `docs/cerebras-evidence-bundle.md` `CLAIM_SCOPE.md` section — the
  parent discipline document this slide is one expression of.
- `bench/gates/claim_discipline_gate.py` — the automated gate that
  enforces claim-discipline language across the repo.
- `docs/cerebras-north-star.md` R1-1, R1-2 — the open TSIR migration
  rows backing the "not every kernel is in TSIR yet" non-claim.
