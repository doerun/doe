# 17 — Forward path: hardware verification

## Goals

Close the deck. Under the snapshot assumption (everything else
landed), this slide narrows to the single outstanding gate: Cerebras
hardware execution. Show the two coordination paths that unblock it
and what the resulting receipt closes.

## What it shows

A small DAG with three nodes:

1. **Today's evidence floor** — bundle with WebGPU + simfabric
   receipts in hand, 31B program bundle in tree, kv_write / kv_read
   exercised in the 31B truncated transcript, smoke ladder L1-L61
   complete. (Bottom node.)
2. **Hardware verification (R2-10)** — first executed Doe-CSL
   receipt on real hardware. Two parallel arrows feed it:
   - **Path b — Cerebras-assisted bundle run.** Send the packed
     bundle; Cerebras runs on their hardware; receipt returns.
   - **Path a — endpoint access.** DOE_CSL_CMADDR or WSC appliance;
     run the runner ourselves with `--cmaddr`.
   Either path alone suffices. (Middle.)
3. **R2-7 parity bind closure** — full-depth Gemma 3 1B Doe-CSL
   transcript, executed on hardware, bound against the frozen
   WebGPU reference. (Top.)

Arrow labels: 1 → 2 carries "send tarball" (path b) and "negotiate
access" (path a) on parallel arrows. 2 → 3 carries "execute + bind."

## What it might look like

Bottom-up DAG, three nodes. Node icons reuse the bundle (slide 13),
wafer (slide 04), and HostPlan (slide 06) shapes where applicable.
Arrows are labeled with the gating mechanism. No timeline annotations.
Footer: "Hardware execution is bound by coordination, not by
engineering. Compute time on hardware is minutes-to-hours; coordination
is days-to-weeks."

### Visual spec (per design tokens)

- **Layout pattern:** `bottom-up-dag`.
- **Bottom node — "today's evidence floor" (large-block, ~480×200,
  centered horizontally at slide bottom):** rounded-rectangle (corner
  radius 8 px), `blue.preserve` stroke 2 px, `neutral.bg` fill.
  Inside: bundle tarball icon (small, `accent.gold`) + 4 small
  receipt icons (`blue.preserve`) representing WebGPU + simfabric +
  smoke ladder + 31B program bundle. Label sans-serif 600,
  `neutral.body`, *"today's evidence floor."*
- **Middle node — "hardware verification (R2-10)" (large-block,
  ~480×200, centered vertically):** rounded-rectangle, `red.dim`
  stroke 2 px (the only `red.dim` stroke in the deck — flagging this
  node as the gate). Inside: wafer-outline icon (slide 04) at
  medium-icon size. Label sans-serif 600, *"hardware verification
  (R2-10)."* Sub-label italic 12 px, *"single outstanding gate."*
- **Top node — "R2-7 parity bind closure" (large-block, ~480×200,
  centered horizontally at slide top):** rounded-rectangle,
  `blue.preserve` stroke 2 px. Inside: bind-tool icon (the merge
  symbol from slide 13) joining two receipt icons. Label
  sans-serif 600, *"R2-7 parity bind closure."*
- **Arrows from bottom → middle:** two parallel arrows (one
  left-leaning, one right-leaning) both `blue.preserve` 4 px:
  - Left arrow labeled *"path b — send tarball"*, with bundle
    tarball icon (small) midway along the arrow.
  - Right arrow labeled *"path a — negotiate access"*, with a
    handshake-style icon (or just the text) midway.
- **Arrow from middle → top:** single `purple.spatial` 4 px arrow,
  label *"execute on hardware → bind transcripts"*.
- **Footer caption:** italic 12 px, `neutral.body`, *"Hardware
  execution is bound by coordination, not by engineering. Compute
  time on hardware is minutes-to-hours; coordination is
  days-to-weeks."*
- **Persistent elements reused:** bundle tarball (slide 13), wafer
  outline (slide 04), HostPlan strip styling (slide 06) for receipt
  icons.

## What it doesn't claim

- No predicted timeline. Both paths are coordination-bound, and the
  deck does not estimate days/weeks.
- Not asserting both paths are equally available. They are listed as
  alternatives because either, alone, suffices to feed node 2.
- Not asserting parity bind closure is the end of the proof chain.
  R2-9 (E2B parity), R3-2/R3-3 (31B residency + hardware receipt),
  R4-1 (perf baselines) extend beyond what this slide depicts.

## Source artifacts to cite

- `docs/cerebras-evidence-bundle.md` `CEREBRAS_ASK.md` section — the
  two-path framing this slide visualizes.
- `docs/cerebras-evidence-bundle-pointer.md` — the latest packed
  bundle that path (b) circulates.
- `docs/cerebras-north-star.md` R2-7, R2-9, R2-10, R3-3 — the rows
  downstream of this slide's terminal node.
- `bench/tools/bind_shared_execution_parity.py` — the parity-bind
  tool that produces node 3's verdict artifact.
- `docs/hardware-validation-appendix.md` — the external-facing
  outreach doc the bundle's CEREBRAS_ASK references.
