# Fawn

Fawn is a machine-driven WebGPU runtime engineering program.

Zero-tape here means zero human bureaucracy for recurring decisions, not zero config files.

- correctness by deterministic validators first, proofs where ROI is high
- performance by specialization and benchmark ratchets
- operations by config-as-code and reproducible traces

## Quickstart

Run commands from the repo parent (the directory that contains `fawn/`) so path examples resolve as written.

1. Build the Zig runtime:

```bash
(cd fawn/zig && zig build)
```

2. Run a native execution trace:

```bash
fawn/zig/zig-out/bin/fawn-zig-runtime \
  --commands fawn/examples/upload_1kb_commands.json \
  --quirks fawn/examples/quirks/intel_gen12_temp_buffer_list.json \
  --vendor intel \
  --api vulkan \
  --family gen12 \
  --driver 31.0.101 \
  --backend native \
  --execute \
  --trace \
  --trace-meta fawn/bench/out/quickstart.meta.json
```

3. Run a benchmark harness command:

```bash
python3 fawn/bench/run_bench.py --help
python3 fawn/bench/compare_dawn_vs_fawn.py --help
```

## Canonical docs

- `fawn/thesis.md`
- `fawn/architecture.md`
- `fawn/process.md`
- `fawn/upgrade-policy.md`
- `fawn/status.md`
- `fawn/performance-strategy.md` (read before making or interpreting Dawn-vs-Fawn performance claims)

## Standalone scope

Fawn is self-contained:

1. its own quirk ingestion
2. its own verification boundary
3. its own benchmark and replay harness
4. its own release metadata and gate policy

Dawn and wgpu are comparison baselines, not dependencies.

## Config-as-code (required)

All runtime and engineering controls are declared in `fawn/config/`:
- `modules.json` maps module boundaries (agent, lean, zig, bench, trace).
- `gates.json` defines blocking/advisory gate policy and thresholds.
- `benchmarks.json` defines metric matrix and incumbent comparison baselines.
- `toolchains.json` pins Lean and Zig versions and upgrade cadence.
- `tracing.json` defines trace capture and replay controls.
- `quirks.schema.json` defines the quirk data contract.
- `run-metadata.schema.json` defines reproducible run/build metadata.

No undocumented manual toggles. If behavior changes, config changes in git.

## Why Fawn exists: quirks as data and proof

Driver quirks are where GPU runtime correctness and performance regressions usually hide.
Fawn's thesis is that this logic should be:

1. explicit in schema-validated records
2. verified by Lean where policy requires
3. bound into deterministic artifacts
4. minimized in hot-path Zig execution

### Real quirk example: Intel Gen12 D3D12 shader model 6.6

In Dawn, this class of quirk is handled in backend C++ toggle setup with vendor/device/driver branching.
Example location:
- `fawn/bench/vendor/dawn/src/dawn/native/d3d12/PhysicalDeviceD3D12.cpp:628`
- `fawn/bench/vendor/dawn/src/dawn/native/d3d12/PhysicalDeviceD3D12.cpp:636`

In that path, Dawn checks Intel Gen12 + driver range and then defaults/forces a toggle
(`D3D12DontUseShaderModel66OrHigher`) in imperative backend code.

In Fawn, the same intent is represented as a quirk record:

```json
{
  "schemaVersion": 1,
  "quirkId": "d3d12.intel.gen12.disable_sm66_pre_32_0_101_5762",
  "scope": "driver_toggle",
  "match": {
    "vendor": "intel",
    "api": "d3d12",
    "deviceFamily": "gen12",
    "driverRange": "<32.0.101.5762"
  },
  "action": {
    "kind": "toggle",
    "params": {
      "toggle": "d3d12_dont_use_shader_model_66_or_higher"
    }
  },
  "safetyClass": "high",
  "verificationMode": "lean_required",
  "proofLevel": "proven",
  "provenance": {
    "sourceRepo": "dawn",
    "sourcePath": "src/dawn/native/d3d12/PhysicalDeviceD3D12.cpp",
    "sourceCommit": "<commit>",
    "observedAt": "2026-02-19T00:00:00Z"
  }
}
```

Lean then evaluates the policy obligation for this quirk (from `verificationMode` + `safetyClass`)
using the same bridge contract used by runtime metadata:

```lean
-- from Fawn.Bridge policy model:
-- lean_required => required proof level is proven
example :
  Fawn.Bridge.requiredProofFromPolicy
    Fawn.Model.VerificationMode.lean_required
    Fawn.Model.SafetyClass.high
  = some Fawn.Model.ProofLevel.proven := rfl
```

### Real non-quirk example: command invariant elimination

Lean value is not limited to driver quirks.
Fawn can also prove command-shape invariants and remove redundant hot-path checks.

Current code already shows this pattern:

1. Parser enforces non-zero dispatch dimensions and repeat count.
Parser references: `fawn/zig/src/command_json.zig:369`, `fawn/zig/src/command_json.zig:579`.
2. Execution still carries defensive checks for the same shape constraints.
Execution references: `fawn/zig/src/wgpu_commands.zig:215`, `fawn/zig/src/wgpu_commands.zig:229`, `fawn/zig/src/wgpu_commands.zig:235`.

With a normalized-command contract in Verify/Bind (Lean-checked artifact input), the release
execution path can trust those invariants and delete these specific shape checks.
This is branch elimination for non-quirk logic, while preserving dynamic runtime safety checks
that must stay (device loss, queue timeout, map failure, missing symbols).

Illustrative theorem shape for a normalized command pack:

```lean
-- illustrative (planned theorem pack): normalized kernel dispatch is never zero-sized
theorem normalized_kernel_dispatch_nonzero
  (x y z repeat : Nat)
  (hx : 0 < x) (hy : 0 < y) (hz : 0 < z) (hr : 0 < repeat) :
  x ≠ 0 ∧ y ≠ 0 ∧ z ≠ 0 ∧ repeat ≠ 0 := by
  exact ⟨Nat.ne_of_gt hx, Nat.ne_of_gt hy, Nat.ne_of_gt hz, Nat.ne_of_gt hr⟩
```

### Lean vs Zig boundary

Lean is the policy and proof authority: it defines what decisions are valid and what obligations must hold before release.
Zig is the execution authority: it runs commands, owns backend lifecycle, emits deterministic traces, and handles dynamic failures explicitly.
Fawn's "lean-out" rule is to move static decisions into verified artifacts and keep only truly runtime-dependent checks in Zig.

### Lean responsibilities in Fawn

1. Define the formal policy model for runtime contracts in `fawn/lean/Fawn/Model.lean`.
2. Specify deterministic dispatch semantics and tie-break behavior as the reference oracle in `fawn/lean/Fawn/Runtime.lean`.
3. Encode proof obligation policy (`verificationMode` + optional `safetyClass` override) independent of Zig in `fawn/lean/Fawn/Bridge.lean`.
4. Prevent Zig policy drift by checking decision parity against the Lean reference (for example with `fawn/trace/compare_dispatch_traces.py` and replay checks).
5. Enable proof-driven branch elimination from hot-path Zig by moving static decisions into verified bind artifacts, then deleting equivalent runtime checks.
6. Provide auditable evidence for release gates through deterministic decision metadata, trace hash chains, and replay-validation workflows.

### Zig responsibilities in Fawn

1. Execute commands deterministically and apply selected quirk actions in the runtime path (`fawn/zig/src/runtime.zig`, `fawn/zig/src/wgpu_commands.zig`).
2. Own explicit native WebGPU runtime execution, resource setup, and submission lifecycle (`fawn/zig/src/webgpu_ffi.zig`, `fawn/zig/src/wgpu_resources.zig`).
3. Keep hot-path behavior branch-minimal by consuming bound profile/quirk decisions instead of ad-hoc policy branching.
4. Preserve explicit runtime safety handling for dynamic failures that cannot be proven away (device/queue/map/timeouts/symbol availability).
5. Emit deterministic trace rows and run summaries with hash-chain continuity for replay/gate verification (`fawn/zig/src/trace.zig`, `fawn/zig/src/replay.zig`).
6. Surface execution status and timing envelopes required by benchmark/gate tooling (`fawn/zig/src/execution.zig`, `fawn/zig/src/main.zig`).
7. Maintain behavioral parity with Lean-produced decisions and fail fast when parity/replay mismatches are detected.

### Why this is better in Fawn

1. Single-source-of-truth quirk behavior: schema record + hashable artifacts, not backend-local branch clusters.
2. Deterministic auditability: decision fields and hash-chain traces are emitted at runtime.
3. Proof-gated safety: `lean_required` can be made blocking by policy before release.
4. Lean-out path: once quirk and non-quirk static conditions are discharged in Verify/Bind, equivalent runtime Zig checks can be deleted.

### Where Dawn is still stronger today

1. Broader production quirk coverage across vendors/drivers from years of shipped backend behavior.
2. Deeper backend hardening for edge cases (device/driver/platform interactions under real workloads).
3. More mature performance telemetry paths in practice (including stable GPU timing behavior).

Fawn's advantage remains architectural: explicit contracts + proof boundary + branch-elimination workflow.
Fawn must continue closing coverage and parity gaps to exceed Dawn in practice.

## Current implementation status

Runtime (product outcomes) today:
- `fawn/zig/src` trace/replay-first runtime with deterministic matching, dispatch, and trace emission.
- Lean runtime contracts and proof-obligation metadata integration in dispatch traces.
- Deterministic trace schema with hash-chain replay hooks and session summaries (`--trace-meta`).

Developer flow (release-quality infrastructure) in progress:
- canonical docs and config-as-code layout are in place
- module scaffolds (`agent`, `lean`, `zig`, `bench`, `trace`) and example workload flow are implemented
- baseline benchmark/replay contracts and comparison scaffolding exist

Still incomplete for full release confidence:
- full upstream quirk mining automation
- Lean theorem packs with CI proof execution
- CI wiring for Lean artifact verification and replay
- full benchmark harness with measured GPU timings
- real replay event-equivalence engine
- baseline Dawn/wgpu dataset generation

## Operating contract (v0)

1. Mine quirk candidates into machine data.
2. Validate schema and deterministic invariants.
3. Apply guard logic for all quirks; apply Lean proofs only where policy requires.
4. Bind validated outputs into runtime config.
5. Run self-contained correctness + trace gates as blocking; verification + performance as advisory in v0.
6. Publish benchmark deltas against incumbent baselines (Dawn/wgpu) as reports.
7. Emit reproducible metadata and trace artifacts.
