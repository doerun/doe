# CSL layer-block self-check

Reference for the in-loop pipeline that takes the generated E2B layer-block
kernel from CSL source through to a model receipt with a parity-contract
verdict. The parity-contract gate consumes the artifacts described here; this
doc is the single place to look when something diverges.

## Goal

Keep `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json` honest as
the E2B layer-block evidence strengthens. The self-check below proves the
kernel / runner / numpy-reference triangle is self-consistent and, when the
BF16-derived weight slices and parity verdict are present, promotes the narrow
L1 tier to `executionStatus=real_weight_layer_block_success`.

That tier is intentionally narrower than full E2B execution. It proves one
real-weight layer-block smoke contract plus the synthetic governed lane; it
does not prove full manifest-shape Doe/CSL runtime execution or Cerebras
hardware execution.

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

## Core contract: `C0..C5`

The self-check script also carries later guardrails for evidence bundles, demo
surfaces, SDK 2.10 syntax, manifest-shape oracle presence, and claim
discipline. The table below is the core layer-block loop.

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
`P3` keeps the synthetic simfabric path separate from numpy-only diagnostics.
The stronger real-weight promotion is governed by the receipt's
`realWeightEvidence` block: fixture hash, weights audit, weight-set hash, and
the WebGPU-vs-CSL parity verdict for the BF16-derived L1 smoke slice.

## What is still blocked

The current promoted tier is `real_weight_layer_block_success`, not full
`simulator_success` for E2B. The remaining blockers are:

1. **`cs_python` on PATH for fresh simulator regeneration.** The generated runner imports
   `cerebras.sdk.runtime.sdkruntimepybind` at module top, so it cannot
   regenerate live traces without the Cerebras SDK Python interpreter. Hosts
   without the SDK must stay in the explicit blocked diagnostic path.

2. **Full manifest-shape runtime execution.** The CPU/Numpy oracle now executes
   the raw BF16 E2B text stack at upstream tensor dimensions, but Doe CSL has
   not yet executed that full manifest-shape graph.

3. **Hardware receipt.** WSE/WSC execution remains pending until a
   `hardware_success` receipt exists.

Once Doe CSL executes the full manifest-shape graph and the hardware lane has
matching receipts, the model receipt can move beyond the narrow L1
real-weight smoke tier.

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
