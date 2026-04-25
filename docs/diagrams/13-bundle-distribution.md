# 13 — The bundle: "One artifact, three execution surfaces"

## Goals

Crystallize the distribution claim that motivates content-addressable
identity. A single bundle artifact (manifest + execution graph + weight
shards + tokenized prompt + HostPlan) drives execution across browser
WebGPU, simfabric, and Cerebras hardware, producing comparable receipts.

## What it shows

- A bundle tarball icon at the center-top, labeled with its
  identity-chain hashes (`manifestSha256`, `executionGraphSha256`,
  `programBundleId`, `weightSetSha256`).
- Three arrows fanning down to three execution-surface icons (reused
  from slide 04): browser WebGPU, simfabric, WSE3 hardware.
- Below each surface, a receipt icon labeled with what it produces:
  `doe-webgpu-transcript`, `doe-csl-int4ple-transcript`,
  `cerebras-hardware-receipt`.
- A horizontal "comparable receipts" band at the bottom indicating
  the parity-bind tooling consumes any pair.

## What it might look like

Top-down hierarchical diagram. Center top: tarball icon with hash
labels. Three arrows fanning to three columns; each column has the
hardware icon followed by its receipt icon and a small caption
("WebGPU 8-decode-step transcript", "Simfabric bounded prefill+decode",
"Hardware full transcript"). Bottom band: "parity-bind: any pair →
parity verdict" with the bind-tool icon.

### Visual spec (per design tokens)

- **Layout pattern:** `radial-distribution`.
- **Center-top hero — bundle tarball (large-block, ~280×200):**
  cylinder shape (rounded-rectangle 16 px corner with shading bands
  to suggest 3D), `accent.gold` fill, `neutral.body` strokes. Hash
  labels around the cylinder in monospace 11 px:
  - `manifestSha256: 6644e3be…`
  - `executionGraphSha256: 7b8152f8…`
  - `programBundleId: gemma-4-31b-it-…`
  - `weightSetSha256: …`
- **Three radiating arrows:** thick (4 px) bands fanning down from
  the bundle. Each arrow tinted to match its destination column:
  - left arrow → `blue.preserve` (WebGPU)
  - middle arrow → `blue.preserve` fading to `purple.spatial`
    (simfabric — half blue, half purple to indicate it bridges)
  - right arrow → `purple.spatial` (hardware)
- **Three execution-surface columns (medium-block each, equal
  width):**
  - **Left — WebGPU:** browser-tab + workgroup-grid icon (slide 04).
    Below: receipt icon (small rounded-rectangle labeled
    `decode_transcript.json`). Caption: *"WebGPU 8-decode-step
    transcript."*
  - **Middle — simfabric:** PE-grid icon (slide 04). Below: receipt
    icon labeled `cslTranscript`. Caption: *"Simfabric bounded
    prefill+decode."*
  - **Right — hardware:** wafer outline icon (slide 04). Below:
    receipt icon labeled `hardware-receipt`, **rendered with
    `red.dim` outline and a `red.dim` "PENDING" overlay** —
    visual cue that this is the single outstanding gate.
    Caption: *"Hardware full transcript (R2-10 — outstanding)."*
- **Bottom band — parity-bind:** thin horizontal strip at slide
  bottom. Bind-tool icon (a small two-input merge symbol, two
  arrows joining into one, `blue.preserve`) labeled *"parity-bind:
  any pair → parity verdict"*. Connecting lines from the three
  receipt icons up-and-down to the bind tool.
- **Persistent elements reused:** browser-tab + workgroup grid (04),
  PE-grid (04), wafer outline (04). Bundle tarball is **defined
  here** and referenced by slide 17.

## What it doesn't claim

- Not all three surfaces produce identical numerical output across
  every kernel. WebGPU non-determinism across adapters is documented
  (`feedback_webgpu_non_determinism.md`); the deck doesn't paper over
  this.
- The hardware-receipt icon represents the **single outstanding gate**
  in the deck's snapshot: WebGPU and simfabric surfaces have receipts
  in hand; the hardware surface is unblocked once path (b) — Cerebras-
  assisted bundle run — or path (a) — endpoint access — completes.
- The bundle's CLAIM_SCOPE explicitly distinguishes "claimable today"
  from "structurally enabled but blocked." This slide does not
  promote anything past CLAIM_SCOPE's bar.

## Source artifacts to cite

- `docs/cerebras-evidence-bundle.md` — bundle governance, CLAIM_SCOPE,
  and CEREBRAS_ASK that this slide visualizes.
- `docs/cerebras-evidence-bundle-pointer.md` — the auto-generated
  pointer to the latest packed bundle and its sha values.
- `bench/tools/pack_cerebras_validation_archive.py` — the packer
  whose output the diagram represents.
- `bench/tools/bind_shared_execution_parity.py` — the parity-bind
  tool referenced in the bottom band.
