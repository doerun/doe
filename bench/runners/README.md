# bench/runners

Per-product, per-platform runner scripts that execute one workload (or one
sweep) and emit a typed receipt. Runners do not aggregate or compare; they
produce raw `.run.json` / receipt artifacts that downstream tools consume.

Notable contents:

- `csl-runners/` — Cerebras CSL per-kernel + per-cell runners
  (Gemma 4 31B layer-block, Qwen 3.6 27B per-kernel cells, attention canaries,
  manifest-shape probes). Drive `cs_python` / cslc through the Singularity
  wrapper at `runtime/zig/tools/cs_python_singularity.sh`.
- `gemma4_31b_af16_session_runtime.py` — the live HostPlan session driver for
  the `<bos>sky color is` parity target.
- `run_blocking_gates.py` — invokes every blocking gate from
  `config/gates.json`; CI front door.
- `publish_apple_runtime_release.py` — Apple Metal native runtime bundle
  packer.
- Determinism, numeric-stability, sampled-decode, render-node-slot helpers
  used across compares.

Outputs land under `bench/out/<lane>/...`; `bench/out/scratch/` is for
ephemeral / probe runs and is excluded from canonical inventory.

For the CLI front door (`run`, `compare`, `claim`), see
[`bench/README.md`](../README.md).
