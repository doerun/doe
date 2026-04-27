# Qwen 3.6 27B simfabric-cell drivers

Tracked source for the small-shape end-to-end simfabric runs of 10
Qwen 3.6 27B kernels: `rmsnorm`, `rope_partial`, `residual`, `silu`,
`embed`, `tiled` (SUMMA matmul), `kv_write`, `gemv` (Q4_K dequant +
GEMV), `sample`, and `attn_decode`. The 11th compile-target kernel,
`attn_prefill`, is the cslc `linker_pe_memory_overflow` blocker
(`causalAttentionPrefill` in the smoke config) — it never compiles,
so it is not a simfabric cell.

Each cell is a triple of `<kernel>_layout(_patched).csl`,
`<kernel>_pe_program.csl`, and `<kernel>_run.py` (cs_python driver).
The driver compiles the cell via `cslc`, runs it under simfabric,
verifies parity vs a host-computed reference, and writes a per-kernel
receipt under `bench/out/r3-2-27b-qwen-<kernel>-simfabric-cell/`
(regeneration output, gitignored).

`bench/tools/synthesize_qwen_3_6_27b_simfabric_cells_summary_receipt.py`
aggregates the per-cell receipts into a single summary at
`bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json`.

## Layout patches

`rmsnorm`, `residual`, and `silu` ship `*_layout_patched.csl` because
the manifest-shape host plan
(`runtime/zig/src/doe_wgsl/emit_csl_layout.zig`) deliberately does
**not** forward `hidden_size` / `chunk_size` from `layout.csl` to
`pe_program.csl`. At manifest hidden_dim=5120 the per-PE buffers
(60 KB) overflow the WSE-3 per-PE 38 KB working budget; the broader
R3-2 single-PE-reduction → fabric-shard redesign closes that gap.
For the small-shape canary the per-PE buffers fit comfortably, so the
layout is patched here to forward the param. See the `notWhat` block
in each receipt for the full rationale.

The other seven kernels do not need a layout patch — their layouts
already forward all per-PE shape params (the manifest-shape per-PE
buffers fit within budget for those kernels).

## Kernel-emit gaps surfaced by these cells

Three cells carry typed WGSL→CSL emit gaps:

- **`sample`** — index-reduction gap. The kernel reduces the running
  max VALUE across PEs but unconditionally writes the LAST PE's
  `local_max_idx` as the output token; the global argmax INDEX is
  not propagated. The canary works around this by constructing
  logits so the global max lives in PE (width-1)'s chunk.

- **`gemv`** at width≥3 — middle-PE routing gap. The layout sets
  `rx={WEST}, tx={EAST}` for middle PEs (pure pass-through). Wavelets
  flow through but are not delivered to the PE's RAMP, so middle PEs'
  recv DSDs block forever. The last PE accumulates only PE 0's
  contribution + its own. The canary uses width=2 (no middle PEs) to
  validate the rest of the kernel; closing the gap requires the
  layout to set `tx={EAST, RAMP}` (or equivalent) for middle PEs.

- **`attn_decode`** — task-activation gap. `task reduce_recv` is
  bound to `reduce_task_id` but never activated; the
  `@fmovs(&incoming, reduce_in)` call is missing the
  `.activate = reduce_task_id` annotation that the sample kernel's
  `@mov32` uses correctly. Any simfabric launch hangs at memcpy_d2h
  with the recorded stall signature. The cell driver writes a
  typed-blocker receipt without launching.

`silu` additionally carries an emit stand-in: the kernel currently
emits as a passthrough (`output[idx] = input[idx] * 1.0`) rather than
real SiLU; the cell verifies dispatch shape against the same
passthrough host reference.

## Regenerating the receipts

```sh
SDK=/home/x/cerebras-sdk-2.10.0
CELLS=$PWD/bench/runners/csl-runners/qwen-3-6-27b-cells
OUT=$PWD/bench/out

for kernel in rmsnorm rope_partial residual silu embed tiled kv_write gemv sample attn_decode; do
  case "$kernel" in
    rmsnorm)      params="width:4,hidden_size:128" ;;
    rope_partial) params="width:4,head_dim:8,num_pairs:2" ;;
    residual)     params="width:4,height:1,chunk_size:128" ;;
    silu)         params="width:4,height:1,chunk_size:128" ;;
    embed)        params="width:2,height:1,hidden_size:16,hidden_per_pe:16,rows_per_pe:8,num_tokens:2,tokens_per_chunk:2" ;;
    tiled)        params="P:2,Mt:4,Kt:4,Nt:4" ;;
    kv_write)     params="width:4,height:1,head_dim:8,max_seq_len:8,slots_per_pe:8" ;;
    gemv)         params="width:2,height:1,out_dim:4,out_dim_per_pe:4,in_dim_per_pe:512,num_blocks_per_row:2" ;;
    sample)       params="width:4,chunk_size:64" ;;
    attn_decode)  params="width:4,head_dim:8,kv_chunk:4" ;;
  esac
  layout="$CELLS/${kernel}_layout_patched.csl"
  [[ -f "$layout" ]] || layout="$CELLS/${kernel}_layout.csl"
  cell_out="$OUT/r3-2-27b-qwen-${kernel//_/-}-simfabric-cell"
  mkdir -p "$cell_out"
  cp "$layout" "$cell_out/layout.csl"
  cp "$CELLS/${kernel}_pe_program.csl" "$cell_out/pe_program.csl"
  cp "$CELLS/${kernel}_run.py" "$cell_out/run.py"
  cd "$cell_out"
  $SDK/cslc layout.csl --arch=wse3 --fabric-dims=11,5 --fabric-offsets=4,1 \
    --params="$params" --memcpy --channels=1 -o compiled
  $SDK/cs_python run.py --name compiled --out-receipt receipt.json
  cd -
done

python3 bench/tools/synthesize_qwen_3_6_27b_simfabric_cells_summary_receipt.py
```

attn_decode does not actually launch — its driver writes the typed-
blocker receipt directly. All other cells parity-pass at float32 ULP
(max_abs_diff ≤ 1e-5) against their host-computed references.

## What this validates

- The per-kernel CSL emitted by Doe's manifest-shape host plan
  compiles cleanly via cslc 2.10.0 for 10 of the 11 compile targets
  (the 11th, `attn_prefill`, is the named per-PE-residency blocker).
- For the seven kernels without WGSL→CSL emit gaps (rmsnorm,
  rope_partial, residual, embed, tiled, kv_write, gemv at width=2),
  the kernel arithmetic matches the canonical formulation within
  float32 precision under simfabric execution.
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
- Real SiLU arithmetic (silu kernel emits as passthrough stand-in;
  tracked in `scopeRestrictions.swigluFfnFusedGate`).
- Sample kernel's correct global-argmax behavior (index-reduction gap).
- gemv's correct multi-PE reduction at width≥3 (middle-PE routing gap).
- attn_decode's softmax-attention output (task-activation gap; the
  cell never launches under simfabric until the gap is closed).
- The kernels Doe lists as named blockers in the smoke config's
  `scopeRestrictions`: linear-attention layers, mrope-interleaved
  3D rotary, causal attention prefill, attentionOutputGate
  (`sigmoid_gated`), and SwiGLU FFN fused gate (`silu_gated`).
