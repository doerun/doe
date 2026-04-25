# 06 — HostPlan: "The identity-preserving orchestration"

## Goals

Establish the orchestration counterpart to slide 05. Where TSIR
preserves body semantics across lowerings, HostPlan preserves
content-addressable identity across executions. Both are required for
the bundle pipeline to be credible.

## What it shows

- A vertical sequence of launch boxes (e.g., 8 visible, "..." between),
  each labeled with its `kernelName` (`embed`, `rmsnorm_prefill`,
  `tiled`, …). Bind-by-symbol arrows connect outputs of earlier
  launches to inputs of later launches.
- A hash-badge column running alongside, listing the identity-chain
  fields: `manifestSha256`, `executionGraphSha256`,
  `hostplanSha256`, `compileTargetHashes[*]`, `runnerVersion`.
- Caption: "Identity is the content-addressable hash chain.
  Re-emitting the same bundle yields the same HostPlan and therefore
  the same identity."

## What it might look like

Vertical strip down the center of the slide showing 8 stacked
rectangular launch boxes connected by arrows. To the right, a side
panel lists the identity fields with their sha placeholders. Below
the strip, a single line of small text: "PyTorch's traced graphs
aren't this — they depend on eager execution and don't carry a
stable identity hash." Reuse this vertical-launch icon as the
visual shorthand for "HostPlan" throughout the deck.

### Visual spec (per design tokens)

- **Layout pattern:** `hero-box-with-inset`.
- **Hero HostPlan vertical strip (centered, 240 px wide × 700 px
  tall):** 8 stacked rectangles (each 240×72, `blue.preserve` stroke
  2 px, `neutral.bg` fill, 16 px gap between). Labels in monospace
  `neutral.body` from top to bottom: `embed`, `rmsnorm_prefill`,
  `tiled`, `rope`, `attn_head256`, `gelu`, `residual`,
  `lm_head_gemv` (real Gemma 3 1B kernels). Connecting arrows
  (`blue.preserve`, 2 px) drop from each box to the next, labeled
  with the bound symbol (e.g., `activations`, `q_proj`, `attn_out`)
  in monospace 10 px italic.
- **Identity-hash side panel (right of strip, 320 px wide):** rows
  of `accent.gold` rounded-rectangle pills, each labeled with one
  identity field in monospace 12 px:
  - `manifestSha256: 6644e3be…`
  - `executionGraphSha256: 7b8152f8…`
  - `hostplanSha256: …`
  - `compileTargetHashes[embed]: …`
  - `compileTargetHashes[tiled]: …`
  - `runnerVersion: …`
  Pills aligned vertically with the launch boxes they correspond to
  (where applicable); free-floating for global identity fields.
- **Caption below strip:** italic, `neutral.body` 14 px, *"PyTorch's
  traced graphs aren't this — they depend on eager execution and
  don't carry a stable identity hash."*
- **Persistent elements defined here:** the HostPlan vertical strip
  and the identity hash badge. Both are referenced by slides 03,
  11, 12, 13, 17.

## What it doesn't claim

- HostPlans are not portable across model versions. A change to the
  manifest invalidates every downstream identity.
- The identity chain is content-addressable at the bundle level, not
  at the per-launch level. A runner upgrade that changes per-launch
  semantics is caught by `runnerVersion`, not by per-launch hashes.
- Not asserting that all backends produce identical receipts from the
  same HostPlan. Numeric-parity equivalence is a separate check; this
  slide is about identity, not output.

## Source artifacts to cite

- `bench/runners/csl-runners/int4ple_checkpoint.py` — the identity
  schema implementation, including the typed drift codes.
- `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/host-plan.json`
  — a real HostPlan instance the diagram can be rendered from.
- `docs/cerebras-evidence-bundle.md` — for the bundle-identity
  framing this slide is one component of.
