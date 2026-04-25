# 16 — Evidence ledger: receipt-backed claims today

## Goals

Make the "claimable today" set explicit and grounded in repo paths.
Without this slide, the structural argument from slides 02-14 floats
above the actual artifacts. This slide ties each part of the deck to
a file or sha that backs it.

## What it shows

A single ledger of receipts in hand, every row pointing at a real
artifact in the repo. The deck's snapshot assumption: every row in
this ledger is filled; the only outstanding gate is the hardware row
on slide 17.

### Receipts in hand today

| Claim referenced in deck | Backing artifact (path / sha) |
|---|---|
| TSIR real-pipeline-v0 fixtures (per-kernel WGSL → semantic → realization) | `runtime/zig/tests/tsir/real/{rmsnorm,fused_gemv,embed,lm_head_gemv,attention_head256_f16kv,attention_head512_f16kv}/` (6 kernels, all `frontendVersion="frontend-real-pipeline-v0"`) |
| TSIR emitter coverage on those fixtures | `runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig` + `bench/fixtures/tsir-real-entries/*.json` (manifest entries with non-sentinel digests for both `webgpu-generic` and `wse3` backends) |
| TSIR host-side parity oracle (algorithm-exact) | `runtime/zig/src/tsir/reference_interpreter.zig` covers `fused_gemv`, `rms_norm`, `gather`, `identity`, `simple_reduction`, `residual_add`, `gelu_gated` (7 of 11 transcript bodyOps) |
| Gemma 3 1B WebGPU 8-decode reference, post-B1/B2 | `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-export-real/decode_transcript.json` |
| Gemma 3 1B bundle-derived reference (schema-valid) | `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-export-bundle-derived/doppler_int4ple_reference_export.json` |
| Gemma 4 31B program bundle (real-weight) | Lane A1 output under tonight's batch dir |
| Gemma 4 31B WebGPU prefill+8-decode reference | Lane A2 output under tonight's batch dir (~8 min wallclock, `stopReason=max-tokens`) |
| Gemma 4 31B L1 layer-block dry receipt | `bench/out/r3-1-31b-l1-dry/trace.json` (passed=True, max-abs-err=0) |
| Gemma 4 31B L61 chained smoke receipt | `bench/out/r3-1-31b-l61-smoke/trace.json` (61 layers chained, max-abs-err=0, ~6.6 min wallclock) |
| Gemma 4 31B smoke ladder (L1, L2, L4, L8, L16, L32, L61) | Tonight's overnight batch under `bench/out/overnight/<utc>/cells/csl-31b-L*/` (independent receipts, all `passed=True`) |
| HostPlan content-addressable identity | `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/host-plan.json` |
| Checkpoint/resume v1 with strict identity validation | `bench/runners/csl-runners/int4ple_checkpoint.py` + 8 tests in `bench/tests/test_int4ple_checkpoint.py` |
| Singularity-wrapper env-forwarding fix | `runtime/zig/tools/cs_python_singularity.sh` (`SINGULARITYENV_*` hoisting + in-container python override) + `runtime/zig/tools/csl_sdk_driver.py` (singularity-preferred discovery) |
| Bundle CLAIM_SCOPE today | `docs/cerebras-evidence-bundle.md` + `docs/cerebras-evidence-bundle-pointer.md` |

### Structurally enabled but not yet executed

These claims have the IR / emitter / runner support landed today, but
no receipt yet exercises them end-to-end. Slides 09 (kv_write), 10
(attention_decode), and 17 (forward path) reference these honestly.

| Claim | What's missing |
|---|---|
| `kv_write` / `kv_read` exercised in any Doe receipt | Truncated 31B prefill+decode at `--max-layers 1` is plumbed through Lane A3 but blocked on a residual-symbol-mismatch in `emit_csl_semantic_ops.emitResidualPe` (HostPlan expects `input`/`residual`, TSIR-migrated emitter exports `a`/`b`). One receipt would close the row; until then, slide 09's CSL emission and PE grid panes carry the claim, not an executed receipt. |
| `kv_write` real-pipeline-v0 TSIR fixture | No fixture exists at `runtime/zig/tests/tsir/real/kv_write/` or in `bootstrap/`. Slide 09's WGSL + TSIR panes carry "fixture pending real-pipeline-v0 promotion" captions until a frontend-derived fixture lands. |
| `sample` / `attn_decode` / hand-maintained kernels in TSIR | `runtime/zig/src/doe_wgsl/emit_csl_*.zig` for tiled, attn_head256, attn_decode, rope, fused_ffn, sample remain hand-maintained. R1-1 / R1-2 in `docs/cerebras-north-star.md` track the migration. |
| Doe CSL bundle-gate green from current HEAD | The 2026-04-22 packed bundle is `passed 31/31`. A re-run from current HEAD lands `failed: 17/32` (split: paint-flow gates fixable by the singularity wrapper above; stale-fixture gates needing Doe-side regen of `gemma-3-1b-doe-csl-hostplan/{host-plan,doppler-program-bundle}.json`). |

## What it might look like

Single-page ledger table with two columns. Header band at the top
labeled "What today's receipts back." Footer: a one-line pointer to
slide 17 for the single outstanding gate (Cerebras hardware execution).

### Visual spec (per design tokens)

- **Layout pattern:** `text-list-discipline`.
- **Top of slide — header band:** full-width strip (~80 px tall),
  `blue.preserve` fill, `neutral.bg` text. Sans-serif 700, 22 px,
  *"What today's receipts back."*
- **Receipts-in-hand table:**
  - Two columns: claim (~560 px left) and backing artifact
    (~960 px right, monospace 12 px for paths).
  - Each row 56 px tall with 16 px vertical padding.
  - Row separators: `neutral.line` 1 px horizontal rules.
  - Claim column: sans-serif 500, `neutral.body`, 14 px.
  - Artifact column: monospace 12 px, `neutral.body`. File paths
    in `blue.preserve` if they're TSIR/Doe artifacts; receipt
    paths in `purple.spatial` if they're simfabric/hardware
    artifacts; `accent.gold` for hash values.
- **Sub-header — "Structurally enabled but not yet executed":**
  full-width strip (~64 px tall), `red.dim` fill, `red.opaque`
  text. Sans-serif 700, 18 px.
- **Structurally-enabled table:**
  - Same two-column shape as above.
  - Claim column: same.
  - Right column ("what's missing"): sans-serif 400, `neutral.body`,
    italic 13 px, with leading `red.opaque` warning-glyph for visual
    emphasis on the gap.
- **Footer:** italic 12 px, `neutral.body`, *"For the single
  outstanding gate, see slide 17 (forward path)."*
- **Persistent elements reused:** none — this slide is intentionally
  text-and-table only.

## What it doesn't claim

- The ledger is a snapshot. Receipts referenced by Lane A2 / A3 and
  the overnight smoke ladder cells assume tonight's sweep lands clean;
  the slide should be regenerated against actual `done.json` paths
  when the batch finishes.
- Sha values pinned in the ledger are reference-date values. The deck
  is point-in-time; if circulated externally, the ledger should be
  regenerated against current repo state before send.
- Hardware-side receipts are explicitly excluded from this ledger —
  they live on slide 17 as the single outstanding gate.
- The ledger is curated. Other artifacts exist; this list pins the
  ones the deck's slides specifically cite.

## Source artifacts to cite

- Each row's right column *is* a citation; the slide's job is to
  consolidate them.
- `docs/cerebras-evidence-bundle.md` `CLAIM_SCOPE.md` section — the
  parent discipline document this slide is one expression of.
- `bench/tools/summarize_cerebras_evidence_archive.sh` — the existing
  tool for regenerating the ledger against a packed bundle.
