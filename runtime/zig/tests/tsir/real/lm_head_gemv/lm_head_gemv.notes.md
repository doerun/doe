# Real-kernel lm_head_gemv fixture (Gemma 3 1B Q4K decode)

Scope: second real-kernel TSIR fixture after `embed`. Covers the decode-phase
LM head GEMV. First non-gather real-kernel, first that exercises the
`fused_gemv` body op at manifest scale.

## Target dimensions

Gemma 3 1B `gemma-3-1b-it-q4k-ehf16-af32`, decode step:

- `M`: 1 (decode batch)
- `N`: 262144 (vocab_size)
- `K`: 1152 (hidden_size)
- `A` element: `f32` activation input vector, size K
- `B` element: `f16` weight matrix, logical shape [N, K] (SafeTensors row-major)
  or [K, N] (GGUF column-major); runtime picks via `u.transpose_b`
- `C` element: `f32` output logits, size N

Bound to WGSL entry `main_multicol` with Doppler-side overrides
`MULTICOL_COLS_PER_WG = 64`, `MULTICOL_THREADS_PER_COL = 4` (256 threads per
workgroup, 64 cols × 4 threads per col). See the binding in
`doppler/src/inference/config/conversion/gemma3/gemma-3-1b-it-q4k-ehf16-af32.json`
kernel ref `lm_head_gemv`, digest
`sha256:e41f94574d5ac54dd2710036da5d5acc643a483b79b2d74b86825efdaaa7438f`.

Per-PE budget on WSE-3 (target descriptor `wse3`): ~63 KiB, practical working
budget ~48 KiB after program, stack, and fabric receive windows.

## Why this kernel, next after embed

The Gemma 3 1B Cerebras path has two manifest-scale kernels that dominate
residency planning: the embedding-table gather (`embed`) and the LM head
GEMV (`lm_head_gemv`). The two exercise disjoint body ops (`gather` vs
`fused_gemv`) and disjoint residency patterns (fabric_streamed table + pe_sliced
output vs fabric_streamed matrix + pe_replicated vector + pe_sliced output),
so the pair together covers the dominant planner decisions for the non-attention
portion of the Gemma 3 decode path.

The bootstrap `fused_gemv` fixture exercises the body op at toy shape
(M, K, N small enough that everything fits pe_replicated or pe_sliced with
tiny shards). At Gemma 3 1B vocab scale the realization is qualitatively
different: the weight matrix cannot fit per-PE or pe_slice usefully, so the
realization forces fabric_streamed B with concrete chunk sizing.

## What's the same as bootstrap fused_gemv

The semantic body is identical: `y[n] = sum_k A[k] * B[n, k] * alpha` with
`body.op = fused_gemv`, binding roles `matrix`/`vector`/`output` and axis
roles `output`/`reduction`. The reduction contract stays the same: `sum`
over the k-axis, `accumulation=f32`, `associativity=strict_ordered` (lm_head
is the spec-critical tail of the graph so strict reduction order is the
correctness default), `nanInf=propagate`. Frontend recovery against this
WGSL does not need a new body pattern; what changes is the residency shape
at manifest scale.

## What's different at manifest scale

At N=262144, K=1152, M=1:

- `C` output is 262144 × 4 = **1 MiB** unsharded. Does not fit per-PE
  budget. Realization pe_slices `C` on the output-column axis (axis 0)
  with shards=256, giving 1024 cols per PE (4 KiB per PE). Output fits
  with headroom.
- `A` activation vector is 1152 × 4 = **4.5 KiB**. Fits per-PE with
  ample room; pe_replicated across the 256-wide row is the right call
  because every PE needs all of A for its column slice of C.
- `B` weight matrix is 262144 × 1152 × 2 = **~576 MiB** total. Does not
  fit any per-PE slab and cannot be pe_replicated. Must be
  fabric_streamed. chunkBytes=65536 matches the embed fixture's wse3
  convention; the exact chunk size is a planner-tunable parameter that
  trades fabric bandwidth against per-PE receive-window residency.
- `u` uniform is O(1) bytes, host_copied per launch; it does not
  participate in per-PE residency decisions.

The k-axis reduction stays PE-local because each PE owns all K elements
for its assigned 1024 output columns. Reduction tree is `linear` — no
fabric allreduce needed. This is the same reduction class the bootstrap
fused_gemv uses, at larger shape.

## Host I/O layout (WSE-3)

Following the GEMV multi-PE SDK tutorial contract:

- `A`: broadcast-tiled to all 256 PEs (each PE receives the full K=1152
  vector). ROI `(0, 0, 256, 1, 1152)` in WSE host memcpy terms, with
  `host_must_tile = true` to replicate A across the ROI.
- `B`: fabric_streamed via color 0. Host pre-splits B row-major along
  the N axis into 256 shards of 1024 × 1152 × 2 bytes = 2.25 MiB per
  shard, then streams each shard to the owning PE. The simulator plan
  emits concrete color/queue bindings; the realization only names
  `fabricColor=0` and `chunkBytes=65536` as the transport-layer
  parameters the planner consumed.
- `C`: pe_sliced output gathered from all 256 PEs. D2H buffer size
  256 × 1024 × 4 bytes = 1 MiB. ROI `(0, 0, 256, 1, 1024)`.
- `u`: host_copied scalar uniform; fits in the uniform buffer, no ROI.

## What this fixture does NOT land

- **Frontend IR recovery.** `lm_head_gemv.tsir-semantic.json` is the
  expected output. The frontend code that takes Doppler's
  `matmul_gemv_subgroup.wgsl` `main_multicol` entry and produces this
  JSON is `frontend.zig` extension work; not in this fixture. The
  bootstrap `fused_gemv` frontend covers the pattern at toy shape; at
  manifest scale the semantic shape is identical (same body op, same
  axis roles, same binding roles), so the frontend extension is
  expected to be small — the new work is testing it against the real
  Doppler WGSL, whose binding order (u, A, B, C across four bindings)
  differs from the bootstrap's three-binding layout.
- **Planner residency selection.** `lm_head_gemv.tsir-realization.*.json`
  is hand-sketched. The planner code that computes shards=256,
  peGrid=256×1, and chunkBytes=65536 from the wse3 target descriptor's
  per-PE working budget and the semantic axis bounds is `planner.zig`
  extension work; not in this fixture.
- **CSL emitter body at manifest scale.** The bootstrap
  `emit_kernel_body.zig` fused_gemv body emits the single-PE loop for
  a pe_sliced matrix. At manifest scale the body additionally needs
  the fabric_streamed matrix read with receive-window chunking. The
  emitter extension follows the same pattern as the embed fixture's
  fabric_streamed table read; the code change is not in this fixture.
- **Parity receipt.** The receipt lands when the planner produces this
  realization from the semantic, the emitter produces a program from
  the realization, simfabric executes it, and the output hash matches
  the Doppler reference transcript's per-kernel probe for this
  lm_head_gemv operation. None of those pieces are in this fixture
  alone.

## What this fixture DOES land

- A pinned WGSL snapshot for the production lm_head GEMV path, targeting
  the `main_multicol` entry with the Doppler-side override values.
  Later frontend and emitter work runs against this specific input.
- Hand-sketched TSIR semantic and realization JSON that names the
  target residency shape (pe_sliced C, pe_replicated A, fabric_streamed
  B, linear reduction tree) so the planner and emitter extensions have
  a concrete goal, not a prose description.
- `lm_head_gemv.notes.md` documenting the per-PE budget math and the
  planning decision rules, so the follow-on engineer can verify their
  planner output matches the intended shape.
- A fixture path the convert-orchestrator
  (`bench/tools/doe_tsir_convert_lowering.py`) routes to when it
  encounters the `doe.tsir.real.lm_head_gemv` kernel ref, with a typed
  rejection that points at the specific code gaps until the
  frontend/planner/emitter wiring lands.

## Validation plan (future work)

1. Extend `frontend.zig` fused_gemv recovery to accept the production
   Doppler `main_multicol` entry binding/axis layout (binding 0 =
   uniform, binding 1 = A activation vector, binding 2 = B f16 weight
   matrix, binding 3 = C output — different from bootstrap's
   three-binding layout and the uniform binding).
2. Run the frontend against this WGSL. Output must match
   `lm_head_gemv.tsir-semantic.json` after the `sourceDigest` and
   `frontendVersion` fields are filled in by the real frontend.
3. Extend `planner.zig` to pick peGrid width, output shard count, and
   fabric chunk size from the wse3 target descriptor's
   `per_pe_working_budget` when the matrix binding's aggregate byte
   count exceeds any per-PE residency class. Output must match
   `lm_head_gemv.tsir-realization.wse3.json` for wse3 and the
   equivalent for webgpu-generic.
4. Extend `emit_kernel_body.zig` fused_gemv body to handle
   `fabric_streamed` on the matrix binding (pe_replicated vector and
   pe_sliced output already work in bootstrap). The receive-window
   chunking mirrors the embed fixture's fabric_streamed table read.
5. Execute under
   `doe_parity.py --kernel lm_head_gemv --doppler-transcript <t> --doppler-kernel-probe-hash <h>`
   where the probe hash comes from a future Doppler-side per-kernel
   capture of the lm_head_gemv output bytes during the Gemma 3 1B
   decode reference run. Receipt compares backend output to that hash
   and to the reference tokenization chain.

## B/D baseline pin

Per the workstream plan, this fixture lands on the contract/fixture lane
before the WGSL→SPIR-V emitter fixes in workstream B (B1 `.if_`
termination, B2 scalar/vector coercion) have merged. The digests in
this fixture are placeholder zeros; the real-frontend run that produces
them is expected to execute *after* B merges so the TSIR digest chain
is computed against the fixed emitter behavior. Regenerating the
digests post-B is intentional and is how the B↔D baseline pin avoids
hash churn during parallel work.
