# Qwen 3.6 27B simfabric-cell drivers

Tracked source for the small-shape end-to-end simfabric runs of three
Qwen 3.6 27B kernels: `rmsnorm`, `rope_partial`, `residual`.

Each cell is a triple of `<kernel>_layout(_patched).csl`,
`<kernel>_pe_program.csl`, and `<kernel>_run.py` (cs_python driver).
The driver compiles the cell via `cslc`, runs it under simfabric,
verifies parity vs a host-computed reference, and writes a per-kernel
receipt under `bench/out/r3-2-27b-qwen-<kernel>-simfabric-cell/`
(regeneration output, gitignored).

## Layout patches

`rmsnorm` and `residual` ship `*_layout_patched.csl` because the
manifest-shape host plan (`runtime/zig/src/doe_wgsl/emit_csl_layout.zig`)
deliberately does **not** forward `hidden_size` / `chunk_size` from
`layout.csl` to `pe_program.csl`. At manifest hidden_dim=5120 the
`[hidden_size]f32 × 3` per-PE buffers (60 KB) overflow the WSE-3
per-PE 38 KB working budget; the broader R3-2 single-PE-reduction →
fabric-shard redesign closes that gap. For the small-shape canary
(hidden=128) the per-PE buffers fit comfortably, so the layout is
patched here to forward the param so `cslc --params=...` flows
through to `pe_program`. See the `notWhat` block in each receipt for
the full rationale.

`rope_partial` does not need a patch — its layout already forwards
`head_dim` and `num_pairs` via `@set_tile_code` because the kernel's
manifest-shape per-PE buffers (head_dim=256, plus two
`num_pairs=32` cos/sin tables) fit within the per-PE budget.

## Regenerating the receipts

```sh
SDK=/home/x/cerebras-sdk-2.10.0
CELLS=$PWD/bench/runners/csl-runners/qwen-3-6-27b-cells
OUT=$PWD/bench/out

for kernel in rmsnorm rope_partial residual; do
  case "$kernel" in
    rmsnorm)      params="width:4,hidden_size:128" ;;
    rope_partial) params="width:4,head_dim:8,num_pairs:2" ;;
    residual)     params="width:4,height:1,chunk_size:128" ;;
  esac
  layout="$CELLS/${kernel}_layout_patched.csl"
  [[ -f "$layout" ]] || layout="$CELLS/${kernel}_layout.csl"
  cell_out="$OUT/r3-2-27b-qwen-${kernel/_/-}-simfabric-cell"
  mkdir -p "$cell_out"
  cp "$layout" "$cell_out/layout.csl"
  cp "$CELLS/${kernel}_pe_program.csl" "$cell_out/pe_program.csl"
  cp "$CELLS/${kernel}_run.py" "$cell_out/run.py"
  cd "$cell_out"
  $SDK/cslc layout.csl --fabric-dims=11,3 --fabric-offsets=4,1 \
    --params="$params" --memcpy --channels=1 -o compiled
  $SDK/cs_python run.py --name compiled --out-receipt receipt.json
  cd -
done
```

All three cells parity-pass at float32 ULP (max_abs_diff ≤ 1e-6,
max_rel_diff ≤ 4e-7) against their host-computed references.

## What this validates

- The per-kernel CSL emitted by Doe's manifest-shape host plan is
  arithmetically correct: each kernel matches the canonical
  formulation within float32 precision under simfabric execution.
- The `partialRotaryFactor` wiring delta from
  `runtime/zig/src/csl_host_plan_tool.zig`'s `compileParamsForPattern`
  rope branch flows through the layout → pe_program forwarding chain
  end-to-end (rope_partial cell).
- The deliberate non-forwarding of `hidden_size`/`chunk_size` at
  manifest scale is documented in-place — the patches here are
  small-shape-only and not a Doe-side change.

## What this does NOT validate

- Manifest-shape compilation/execution (the per-PE-residency blocker
  is real at hidden=5120; the small-shape canary cannot speak to it).
- Multi-kernel chains (each cell is single-kernel only; the analog
  of Gemma's `r3-1-31b-multi-token-decode` 2-step chain is a separate
  follow-up).
- Hardware execution (simfabric only).
- The kernels Doe lists as named blockers in the smoke config's
  `scopeRestrictions`: linear-attention layers, mrope-interleaved
  3D rotary, causal attention prefill, attentionOutputGate
  (`sigmoid_gated`), and SwiGLU FFN fused gate (`silu_gated`).
