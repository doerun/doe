# 05 — TSIR semantic function: "The body-preserving IR"

## Goals

Define the central object of the deck. Show the four slots that every
TSIR semantic function carries and how those slots are what later
slides' walkthroughs hang off.

## What it shows

- One large TSIR semantic-function box in the center of the slide,
  expanded into four labeled slots:
  - **Axes** — named iteration variables with bounds (e.g., `d` ∈
    `[0, hidden_size)`).
  - **Bindings** — buffer slots tagged with semantic roles (e.g.,
    `key_cache: read_write` with role `key_cache`).
  - **Reduction** — reduction structure (axis being reduced, operator).
  - **Body op** — the tag identifying the kernel family (`rms_norm`,
    `kv_write`, `fused_gemv`, etc.).
- A small inset showing the actual rms_norm semantic function as JSON,
  taken from the live TSIR fixture.
- A caption: "One semantic function, N backends. Backends differ in
  memory access; arithmetic is contract-identical."

## What it might look like

A single bordered rectangle dominates the slide; inside, four
horizontal bands, each band a slot with its label on the left and the
slot's content (axes list, bindings list, reduction object, body-op
tag) on the right. A smaller code panel sits below the box showing the
JSON form of the same fixture for ground-truth anchoring. Reuse this
box icon (4-slot rectangle) as the visual shorthand for "TSIR semantic
function" throughout the deck.

### Visual spec (per design tokens)

- **Layout pattern:** `hero-box-with-inset`.
- **Hero TSIR semantic-function box (large-block, 800×500 centered):**
  sharp-corner rectangle, `blue.preserve` stroke 3 px, `neutral.bg`
  fill. Internal layout: 4 horizontal bands separated by `neutral.line`
  1px. Each band is 110 px tall with a 160-px-wide left label region
  and the rest for content.
  - Band 1 — **axes:** label `axes` (sans-serif 600, `blue.preserve`).
    Content: `d ∈ [0, hidden_size)` shown as a small circle (`blue.dim`)
    labeled `d` followed by the bound text in monospace.
  - Band 2 — **bindings:** label `bindings`. Content: 3 stacked
    rounded-rectangle pills, one per binding (`input` read,
    `scale` read, `output` write). Each pill is `blue.dim` fill,
    `blue.preserve` stroke. Role tags shown in monospace italic.
  - Band 3 — **reduction:** label `reduction`. Content: a small
    arrow icon labeled `axis: d, op: sum`.
  - Band 4 — **body op:** label `body op`. Content: a diamond shape
    (80×80, `blue.preserve` fill, `neutral.bg` text) labeled
    `rms_norm` in monospace.
- **Inset code panel (medium-block, 480×220 below hero):**
  monospace, `neutral.body` text on `neutral.bg` with 1 px
  `neutral.line` border. Shows the rms_norm semantic function as
  pretty-printed JSON.
- **Caption strip below inset:** italic, `neutral.body`, *"One semantic
  function, N backends. Backends differ in memory access; arithmetic
  is contract-identical."*
- **Persistent elements defined here:** the 4-slot TSIR
  semantic-function box and the body-op diamond. Both are referenced
  by slides 02, 03, 07-10.

## What it doesn't claim

- Not every kernel maps to a TSIR semantic function today. The
  semantic-function shape covers a specific family (currently:
  `rms_norm`, `gather`, `fused_gemv`, `residual_add`, `gelu_gated`,
  `kv_write`, `kv_read`, plus `attention_scores` in typed-rejection
  phase). Adding a kernel requires a new body-op tag and interpreter
  coverage.
- The "arithmetic is contract-identical" claim is an emitter-contract
  statement, not a numeric-parity assertion across backends. Numeric
  parity at runtime is verified separately by the parity-bind tooling.

## Source artifacts to cite

- `runtime/zig/src/tsir/schema.zig` — `SemanticFunction`, `BufferBinding`,
  `IterationAxis`, `ReductionInfo`, `Body` types.
- `runtime/zig/tests/tsir/real/rmsnorm/` — the real fixture used in the
  inset code panel.
- `runtime/zig/src/tsir/emit_kernel_body.zig` — the multi-backend
  emitter that consumes this shape.
- `docs/status/tsir.md` — for the current covered-body-op list and the
  in-flight ones.
