# 01 — Cover: "Two preservation properties, one author identity"

## Goals

Open the deck with the central thesis in a single readable sentence.
Establish that the argument is structural-property, not marketing.

## What it shows

- Title: **"Two preservation properties, one author identity"**
- Subtitle: Doppler authoring (JS + WGSL) → Doe lowering (TSIR) → CSL
  execution (Cerebras WSE)
- A small visual-key row previewing the six icons defined in slide 04.

## What it might look like

Centered title text on a neutral background. Below the subtitle, a thin
horizontal row of six small icons (browser tab, workgroup grid, TSIR
semantic-function box, PE grid, wafer outline, hash badge), each labeled
with one word. No diagrams in the slide body; the icons are the only
visual content.

### Visual spec (per design tokens)

- **Layout pattern:** `cover-card`.
- **Background:** `neutral.bg`.
- **Title:** sans-serif 700, `neutral.body`, centered, ~64 px line.
- **Subtitle:** sans-serif 500, `neutral.body`, centered, ~28 px line, ~120 px below title.
- **Icon-key row:** 6 small icons (32×32), centered, 48 px gaps. Order left-to-right and color tokens:
  1. Browser tab — `blue.preserve`
  2. Workgroup grid — `blue.preserve`
  3. TSIR semantic-function box — `blue.preserve`
  4. PE grid (hexagons) — `purple.spatial`
  5. Wafer outline — `purple.spatial`
  6. Hash badge — `accent.gold`
- **Persistent elements reused:** all six icons from slide 04 / 05 / 06 / 13, at small-icon size.

## What it doesn't claim

- No performance comparison.
- No "novel" / "first" / "best" framing.
- No specific Cerebras vendor positioning beyond naming WSE as the target.
- No claim that all of the deck's downstream walkthroughs are executable
  end-to-end today (that's slide 16's job).

## Source artifacts to cite

- This deck's `README.md` (immediately preceding file).
- `docs/cerebras-north-star.md` for the broader proof-chain claim that
  this deck visualizes one structural slice of.
