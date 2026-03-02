# Metal macOS Dawn-vs-Doe proof bundle runbook

This runbook is for final strict apples-to-apples Metal proof on Apple Silicon hosts where Dawn Metal is available.

## Preconditions

1. Host is macOS on Apple Silicon (`arm64`) with Metal capability.
2. Dawn binaries and `dawn_perf_tests` are present under `bench/vendor/dawn/out/Release`.
3. Zig runtime binary exists at `zig/zig-out/bin/doe-zig-runtime`.

## 1. Host preflight

```bash
python3 bench/preflight_metal_host.py
```

Expected: preflight reports Metal-capable host and exits `0`.

## 2. Strict local-metal comparable run

```bash
python3 bench/run_release_pipeline.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.comparable.json \
  --report bench/out/metal.macos.final.local.comparable.json \
  --workspace bench/out/runtime-comparisons.metal.macos.final.local.comparable \
  --with-local-metal-gates \
  --with-local-metal-preflight \
  --trace-semantic-parity-mode required \
  --with-claim-gate \
  --claim-require-comparison-status comparable \
  --claim-require-claim-status claimable \
  --claim-require-claimability-mode local \
  --claim-require-min-timed-samples 7 \
  --with-cycle-gate \
  --cycle-contract config/claim-cycle.active.json \
  --cycle-artifact-class claim
```

## 3. Strict local-metal release run

```bash
python3 bench/run_release_pipeline.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.release.json \
  --report bench/out/metal.macos.final.local.release.json \
  --workspace bench/out/runtime-comparisons.metal.macos.final.local.release \
  --with-local-metal-gates \
  --with-local-metal-preflight \
  --trace-semantic-parity-mode required \
  --with-claim-gate \
  --claim-require-comparison-status comparable \
  --claim-require-claim-status claimable \
  --claim-require-claimability-mode release \
  --claim-require-min-timed-samples 15 \
  --with-cycle-gate \
  --cycle-contract config/claim-cycle.active.json \
  --cycle-artifact-class claim
```

## 4. metal_doe_app lane strict run

```bash
python3 bench/run_release_pipeline.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.comparable.json \
  --report bench/out/metal.macos.final.metal_doe_app.comparable.json \
  --workspace bench/out/runtime-comparisons.metal.macos.final.metal_doe_app.comparable \
  --with-local-metal-gates \
  --with-local-metal-preflight \
  --local-metal-lane metal_doe_app \
  --trace-semantic-parity-mode required \
  --with-claim-gate \
  --claim-require-comparison-status comparable \
  --claim-require-claim-status claimable \
  --claim-require-claimability-mode local \
  --claim-require-min-timed-samples 7
```

## 5. Rollback proof

Baseline:

```bash
python3 bench/run_release_pipeline.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.comparable.json \
  --report bench/out/metal.macos.final.rollback.baseline.json \
  --workspace bench/out/runtime-comparisons.metal.macos.final.rollback.baseline \
  --with-local-metal-gates \
  --local-metal-lane metal_doe_app \
  --trace-semantic-parity-mode required
```

Rollback:

```bash
FAWN_BACKEND_SWITCH=force_dawn_delegate \
python3 bench/run_release_pipeline.py \
  --config bench/compare_dawn_vs_doe.config.local.metal.comparable.json \
  --report bench/out/metal.macos.final.rollback.force_dawn.json \
  --workspace bench/out/runtime-comparisons.metal.macos.final.rollback.force_dawn \
  --with-local-metal-gates \
  --local-metal-lane metal_doe_app \
  --trace-semantic-parity-mode required
```

Expected rollback evidence:

1. Baseline left backend selection is `doe_metal`.
2. Rollback left backend selection is `dawn_delegate`.
3. `bench/backend_selection_gate.py` fails under rollback for `metal_doe_app` lane as expected.

## 6. Required proof bundle artifacts

1. Comparable report JSON + workspace traces.
2. Release report JSON + workspace traces.
3. `metal_doe_app` comparable report JSON.
4. Baseline rollback report JSON.
5. Forced rollback report JSON.
6. Claim rehearsal artifacts emitted by release pipeline (`*.claim-rehearsal.*`).
