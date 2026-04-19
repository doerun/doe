# CSL layer-block self-check

Reference for the in-loop pipeline that takes the generated E2B layer-block
kernel from CSL source through to a model receipt with a parity-contract
verdict. The parity-contract gate consumes the artifacts described here; this
doc is the single place to look when something diverges.

## Goal

Flip `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json`'s
`executionStatus` from `not_attempted` to `simulator_success`, honestly. The
self-check below is the in-repo half of that contract: it proves the kernel /
runner / numpy-reference triangle is bit-exact and self-consistent. The other
half (an actual `cs_python` simfabric run with real Gemma-4 weights) gates the
final flip and lives outside this loop.

## Artifact graph

```
  bench/out/streaming-executor/e2b-layer-block-source/
      transformer_layer_shape.csl                       (LIVE CSL kernel)
                              │
                              ▼
  bench/runners/csl-runners/_e2b_layer_block_compute.py (canonical numpy ref;
                              │                          single source of truth
                              │                          imported by both
                              │                          consumers below)
            ┌─────────────────┴─────────────────┐
            ▼                                    ▼
  bench/runners/csl-runners/         bench/tools/
      e2b_layer_block_smoke.py           emit_e2b_layer_block_synthetic_trace.py
      (generated SDK runner;             (numpy-only; emits a
       requires cs_python on PATH)        doe_streaming_executor_trace
            │                              for the gate to consume now)
            ▼                              ▼
  bench/out/streaming-executor/      bench/out/streaming-executor/
      e2b-layer-block-smoke-trace.json   e2b-layer-block-synthetic-trace.json
            │                              │
            └──────────────┬───────────────┘
                           ▼
              bench/tools/compare_runner_vs_synthetic.py
                           ▼
  bench/out/streaming-executor/
      e2b-layer-block-cross-runtime-parity-check.json
                           │
                           ▼
              bench/tools/build_model_runtime_receipt.py
                           ▼
  bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json
      (binds synthetic + parity by path/sha; downstream consumers
       see the gate verdict at one canonical pointer)
```

`bench/tools/e2b_layer_block_self_check.py` runs every regen step in order and
asserts the contract below. `bench/tools/test_e2b_layer_block_compute.py` is
the golden-value unit test that gates STEP 0.

## Contract: `C0..C5`

| ID | Where | What it asserts | Failure means |
|----|-------|-----------------|---------------|
| C0 | STEP 0 of self-check | `compute_layer_block` is bit-exact at every sentinel index of every fixture (zeros / ones / varying-wts) in the unit test | Either a kernel/numpy-reference change is intentional (regen goldens via `PRINT_GOLDENS=1`) or unintentional drift (revert the change) |
| C1 | post-STEP 4 | live kernel sha equals the synthetic trace's `kernelSourceSha256InTrace` | Synthetic trace is stale; rerun STEP 2 |
| C2 | post-STEP 4 | the regenerated receipt validates against `config/doe-model-runtime-receipt.schema.json` | Receipt generator emitted a field outside the schema enum or missed a required key; check `streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence` first |
| C3 | post-STEP 4 | `receipt.layerBlockKernelEvidence.syntheticTrace.exists == True` AND `.sha256` matches the on-disk synthetic trace | The receipt and the synthetic trace disagree about which file is current; rerun the self-check |
| C4 | post-STEP 4 | `receipt.layerBlockKernelEvidence.crossRuntimeParityCheck.exists == True` AND `.promotionEligible` field is present | STEP 3 didn't run or wrote a malformed parity-check artifact |
| C5 | post-STEP 4 | `bench/runners/csl-runners/e2b_layer_block_smoke.py` exists and parses as Python | The TEMPLATE in `bench/tools/generate_e2b_layer_block_runner.py` produced invalid Python (e.g. missing format placeholder, unbalanced brace) |

## Failure-mode triage

When the self-check exits non-zero, the error message points at the failed
step or contract. The mapping from step/contract to bug class:

- **STEP 0 fails** → kernel/numpy-reference drift. Look at
  `bench/runners/csl-runners/_e2b_layer_block_compute.py` first; the rope
  table and poly_c1 helpers are the most-likely culprits because they carry
  hardcoded f32 literals.
- **STEP 1 fails** → generator template broken. Often a brace `{}` accidentally
  introduced into a template comment / combineRule string.
- **STEP 2 fails** → numpy reference module no longer imports cleanly, or the
  manifest at `runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json` has a
  required field missing (rare).
- **STEP 3 fails** → `compare_runner_vs_synthetic.py` couldn't read one of its
  inputs; check that STEPS 1 and 2 actually wrote their outputs.
- **STEP 4 fails** → receipt schema violation; the schema file is at
  `config/doe-model-runtime-receipt.schema.json`.
- **C1 fails** → STEP 0 succeeded but STEP 2 wrote a stale synthetic trace.
  Almost always a `__pycache__` issue; `rm -rf bench/runners/csl-runners/__pycache__`.
- **C2 fails** → receipt produced a value outside an enum. The most-recent
  enum extension landed in `executionBlocker`; if a new value is needed,
  extend the schema first.
- **C3 / C4 fails** → receipt generator didn't pick up the trace. Confirm the
  trace files exist on disk, then rerun STEP 4.
- **C5 fails** → generator template syntax. Run
  `python3 bench/tools/generate_e2b_layer_block_runner.py` standalone and
  inspect the output; the runner is plain Python, no template substitution
  happens at runtime.

## Promotion preconditions (P1..P5)

`compare_runner_vs_synthetic.py` writes a verdict into the parity-check
artifact's `verdict.preconditionsMet` / `preconditionsMissing` lists.
`promotionEligible == True` requires all five:

- **P1**: runner trace exists and is readable
- **P2**: runner trace's `kernelSourceSha256` matches the LIVE kernel sha
  (no drift — stale runner traces from prior commits fail here)
- **P3**: runner `dataSource.kind` ∈ {`synthetic_seeded_rng`,
  `manifest_weights_with_seed_fallback`, `manifest_weights_only`} —
  i.e. NOT `numpy_only_no_simulator`
- **P4**: runner `executedRun.status == "succeeded"`
- **P5**: runner `numericalParity.perLayerMaxAbsErr` is non-empty AND
  every entry == 0 (bit-exact)

`P1, P2, P4, P5` are produced by an actual `cs_python` simfabric run.
`P3` upgrades from `synthetic_seeded_rng` to `manifest_weights_*` once a
real-weight loader populates `--weights-dir` with per-layer slice files.

## What's gating the actual flip

The self-check passing locally does NOT flip `executionStatus`. Two
prerequisites live outside this loop:

1. **`cs_python` on PATH.** The generated runner imports
   `cerebras.sdk.runtime.sdkruntimepybind` at module top, so it cannot
   execute without the Cerebras SDK Python interpreter. The receipt's
   `executionBlocker` field reflects this honestly:
   `cs_python_not_available_in_build_environment` /
   `full_transformer_layer_block_incomplete`.

2. **Real per-layer weight slices.** The runner's loader at
   `bench/runners/csl-runners/_e2b_layer_block_compute.py` does not currently
   accept real weights — it falls back to a per-layer-index seeded RNG when
   `--weights-dir/<weight_key>.f32` is missing. The synthetic-seed path
   exercises every other piece of the pipeline and produces a `succeeded`
   trace under `cs_python`; promoting to a publishable `simulator_success`
   requires real weights so the output matches a Doppler/numpy reference at
   the model level, not just the layer level.

Once `cs_python` runs the generated runner against weights from a Doppler
exporter, all five P_n preconditions can be met simultaneously, the parity-
check verdict flips to `promotionEligible: True`, and the model receipt's
`executionStatus` can flip to `simulator_success` honestly.

## How to run

```bash
# Full pipeline (~5s on this machine, dominated by synthetic regen).
python3 bench/tools/e2b_layer_block_self_check.py

# Just the unit test (~1s).
python3 bench/tools/test_e2b_layer_block_compute.py

# After an intentional kernel change, regenerate the goldens:
PRINT_GOLDENS=1 python3 bench/tools/test_e2b_layer_block_compute.py
# then update VARYING_GOLDEN_HEX in the test and re-run STEP 0.
```
