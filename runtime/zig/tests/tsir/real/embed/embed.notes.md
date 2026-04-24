# Real-kernel embed fixture (Gemma 4 E2B)

Scope: Move 4 of the re-scoped TSIR plan. First non-bootstrap kernel
through the TSIR pipeline. See `docs/tsir-lowering-plan.md` Step 9.

## Target dimensions

Gemma 4 E2B `gemma-4-e2b-it-q4k-ehf16-af32-int4ple`:

- `num_tokens`: 32 (prefill window the benchmark exercises)
- `hidden_size`: 1536
- `vocab_size`: 262144
- `embeddings` element: `f32` after dequant-to-activation; table is
  `f32` at this point in the graph after upstream dequant

Per-PE budget on WSE-3 (target descriptor `wse3`): ~63 KiB, practical
working budget ~48 KiB after program, stack, and fabric receive
windows.

## Why this kernel, first

The WS4 status shard
(`docs/status/cerebras-csl.md`) characterizes `embed` as one of four
manifest-scale CSL blockers. The legacy emit_csl_gather.zig header
documents the 2D-grid-plus-chunked-tokens fix but the host runner
wiring for chunked dispatch is not landed. Under the re-scoped plan,
the fix is expressed as residency decisions in a TSIR realization,
not as local logic in the legacy emitter.

## What's the same as bootstrap gather

The body recovery is identical: indices[t] → table[indices[t], h] →
output[t, h]. Semantic identity uses `body.op = gather` with the same
binding and axis roles the bootstrap catalog already covers. The
frontend does not need a new pattern; what changes is the realization
shape at manifest-scale dimensions.

## What's different at manifest scale

At num_tokens=32, hidden_size=1536, vocab_size=262144:

- `output` is 32 × 1536 × 4 = **192 KiB** unsharded. Does not fit the
  per-PE budget. WS4's characterization of a 192 KiB per-PE output
  overflow matches what the legacy CSL plan produced when it left
  `output` pe_replicated. TSIR's realization pe_slices `output` on
  the token axis (axis 0) with shards=8, giving 4 tokens per PE
  (24 KiB per PE). Output fits.
- `embeddings` is 262144 × 1536 × 4 = **1.5 GiB** total. Does not fit
  any per-PE slab and is too large to pe_slice usefully across a
  fixed PE grid without tiny shards. Must be fabric_streamed. The
  chunk_bytes parameter picks a slice size that keeps the live table
  slice plus the output slice under working budget.
- `indices` and `u` uniform are O(num_tokens) bytes, host_copied per
  launch.

At this design point there is no WS4-style overflow. The TSIR path
expresses the fix as explicit residency decisions; the planner picks
shard and chunk parameters from the target descriptor's budget and
the semantic axis bounds.

## What this fixture does NOT land

- **Frontend IR recovery.** The `embed.tsir-semantic.json` is the
  expected output. The frontend code that takes Doppler's
  `gather.wgsl` IR module and produces this JSON is the
  `frontend.zig` extension work; not in this fixture. (The bootstrap
  `gather` frontend covers the pattern; at manifest scale the
  semantic shape is identical, so the frontend extension is expected
  to be small — the work is testing it against the real WGSL, not
  writing new recovery logic.)
- **Planner residency selection.** The `embed.tsir-realization.*.json`
  files are hand-sketched. The planner code that computes those
  shard/chunk values from the target descriptor's per-PE budget is
  the `planner.zig` extension work; not in this fixture.
- **CSL emitter body at manifest scale.** The bootstrap
  `emit_kernel_body.zig` gather body emits the single-PE loop for a
  pe_replicated table. At manifest scale the body additionally needs
  the fabric-streamed table read. The emitter extension is
  straightforward (fabric_streamed bindings already have residency
  metadata) but the code change is not in this fixture.
- **Parity receipt.** The receipt lands when the planner produces
  this realization from the semantic, the emitter produces a program
  from the realization, simfabric executes it, and the output hash
  matches the Doppler reference transcript's per-kernel probe for
  this embed operation. None of those pieces are in this fixture
  alone.

## What this fixture DOES land

- A pinned WGSL snapshot for the production embed path, independent
  of the bootstrap snapshot. Later frontend and emitter work runs
  against this specific input.
- Hand-sketched TSIR semantic and realization JSON that names the
  target residency shape so the planner and emitter extensions have
  a concrete goal, not a prose description.
- `embed.notes.md` (this file) documenting the per-PE budget math and
  the planning decision rules, so the follow-on engineer can verify
  their planner output matches the intended shape.
- A fixture path the convert-orchestrator
  (`bench/tools/doe_tsir_convert_lowering.py`) can route to when it
  encounters the `doe.tsir.real.embed` kernel ref, with a typed
  rejection that points at the specific code gaps until the
  frontend/planner/emitter wiring lands.

## Validation plan (future work)

1. Extend `frontend.zig` gather recovery to accept the production
   Doppler gather.wgsl binding/axis layout (binding 0 = uniform,
   binding 1 = indices, binding 2 = table, binding 3 = output —
   different from bootstrap's binding ordering).
2. Run the frontend against this WGSL. Output must match
   `embed.tsir-semantic.json`.
3. Extend `planner.zig` to pick shard and chunk parameters from the
   wse3 target descriptor's `per_pe_working_budget` when the semantic
   's aggregate tensor byte counts exceed that budget. Output must
   match `embed.tsir-realization.wse3.json` for wse3 and the
   equivalent for webgpu-generic.
4. Extend `emit_kernel_body.zig` gather body to handle
   `fabric_streamed` on the table binding (pe_sliced output already
   works in bootstrap).
5. Execute under `doe_parity.py --kernel embed --doppler-transcript <t> --doppler-kernel-probe-hash <h>`
   where the probe hash comes from a future Doppler-side per-kernel
   capture tool. Receipt compares backend output to that hash.
