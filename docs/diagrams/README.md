# Doppler → Doe → CSL slide deck

A 17-slide structural argument for why the Doppler-authoring + Doe-lowering +
CSL-execution stack composes with Cerebras spatial compute, and why
operator-graph IRs (ONNX, MLIR-as-graph, lazy-traced PyTorch) do not.

## Central thesis

> **Doe's lowering preserves the body shape spatial compute needs, and the
> orchestration preserves the identity shape distribution needs.**

This is a structural-property claim, not a performance claim. The deck does
not assert "Doe is faster"; it asserts "Doe's lowering surface is
correct-by-construction across backends, including spatial compute, in a
way operator-graph IRs are not."

## Snapshot assumption

The deck is written as if every component of the simfabric + WebGPU evidence
chain is in hand: TSIR coverage complete, WebGPU references frozen, 31B
program bundle in tree, decode mechanism exercised including kv_write /
kv_read, smoke ladder L1-L61 receipts landed, bundle ready to circulate.
**The single outstanding gate is execution on Cerebras hardware (R2-10).**
Slides 13, 15, 16, and 17 carry this distinction explicitly; everything
else is structural and unaffected by the hardware leg.

## Per-slide format

Every slide file follows the same five-section shape:

- **Goals** — one or two sentences on the slide's role in the deck.
- **What it shows** — bullet list of the slide's actual content.
- **What it might look like** — visual layout + illustrations to draw.
- **What it doesn't claim** — discipline guard rails specific to the slide.
- **Source artifacts to cite** — repo paths or hash-pinned references that
  ground the slide in observable evidence.

The "doesn't claim" section is mandatory, not decorative. It exists so the
deck stays inside what the receipts back.

## Deck index

| # | Title | File |
|---|---|---|
| 01 | Cover — Two preservation properties, one author identity | [`01-cover.md`](01-cover.md) |
| 02 | The problem — Spatial compute needs exposed axes | [`02-problem.md`](02-problem.md) |
| 03 | The stack at a glance | [`03-stack-overview.md`](03-stack-overview.md) |
| 04 | Hardware primer — three execution models | [`04-hardware-primer.md`](04-hardware-primer.md) |
| 05 | TSIR semantic function — the body-preserving IR | [`05-tsir-semantic-function.md`](05-tsir-semantic-function.md) |
| 06 | HostPlan — the identity-preserving orchestration | [`06-hostplan-identity.md`](06-hostplan-identity.md) |
| 07 | Walkthrough: rms_norm | [`07-walkthrough-rmsnorm.md`](07-walkthrough-rmsnorm.md) |
| 08 | Walkthrough: fused_gemv | [`08-walkthrough-fused-gemv.md`](08-walkthrough-fused-gemv.md) |
| 09 | Walkthrough: kv_write | [`09-walkthrough-kv-write.md`](09-walkthrough-kv-write.md) |
| 10 | Walkthrough: attention_decode | [`10-walkthrough-attention-decode.md`](10-walkthrough-attention-decode.md) |
| 11 | JS orchestration → HostPlan | [`11-js-to-hostplan.md`](11-js-to-hostplan.md) |
| 12 | HostPlan → per-PE programs | [`12-hostplan-to-per-pe.md`](12-hostplan-to-per-pe.md) |
| 13 | The bundle — one artifact, three execution surfaces | [`13-bundle-distribution.md`](13-bundle-distribution.md) |
| 14 | Why ONNX-shaped pipelines hit a wall | [`14-onnx-comparison.md`](14-onnx-comparison.md) |
| 15 | Where the analogy breaks down (honesty) | [`15-honesty-limits.md`](15-honesty-limits.md) |
| 16 | Evidence ledger — receipt-backed claims today | [`16-evidence-ledger.md`](16-evidence-ledger.md) |
| 17 | Forward path — smoke-shape to hardware parity | [`17-forward-path.md`](17-forward-path.md) |

## Visual vocabulary

Established in slide 04 and reused throughout. Each icon is a stable visual
reference; later slides do not redefine them.

| Icon | Represents | First used |
|---|---|---|
| Browser tab containing a workgroup grid | WebGPU / SIMT execution | Slide 04 |
| Rectangular PE grid with explicit fabric routes | CSL on a PE tile | Slide 04 |
| Wafer outline with highlighted ROI rectangle | Cerebras WSE3 hardware | Slide 04 |
| Four-slot box (axes / bindings / reduction / op) | TSIR semantic function | Slide 05 |
| Vertical launch list with hash badge | HostPlan with content-addressable identity | Slide 06 |
| Tarball with three arrows to execution surfaces | Bundle distribution | Slide 13 |

## Persistent examples

The deck threads two consistent example sets:

- **Macro example:** Gemma 3 1B prefill+decode (the running model program).
  Used in the orchestration and bundle slides.
- **Per-kernel examples:** rms_norm (slide 07), fused_gemv (slide 08),
  kv_write (slide 09), attention_decode (slide 10). Each uses a real TSIR
  fixture under `runtime/zig/tests/tsir/real/<kernel>/` as its source.

Slides 07–10 use the same four-pane layout (WGSL / TSIR / CSL / PE-grid)
for visual continuity. Slides 11–12 reuse the HostPlan icon from slide 06.
Slides 14–15 reuse the operator-graph stack from slide 02 for direct
comparison.

## Format target (when slides are produced)

Per the parent ticket, the standard tier is interactive HTML following the
`docs/onboarding-view.{html,css,js}` pattern, with side-by-side code panels
for the four-pane walkthroughs and a clickable PE-grid component. The
markdown files in this directory are the source-of-truth narrative the HTML
build consumes; do not duplicate visual content into the HTML build script.
