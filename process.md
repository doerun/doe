# Fawn Process

## 1. Pipeline: Mine -> Normalize -> Verify -> Bind -> Gate

1. Intake
- pull upstream sources
- extract candidate driver/workaround deltas

2. Normalize
- convert deltas into structured quirk records
- validate schema

3. Verify
- apply deterministic guards for all quirks
- apply Lean obligations from `verificationMode` policy:
  - `guard_only`: no Lean proof requirement
  - `lean_preferred`: Lean preferred, not required in v0
  - `lean_required`: proof requirement is blocking (`proofLevel=proven`)
- optional safety-class overrides may be configured in `gates.json`; in v0 they are empty

4. Bind
- generate runtime config inputs and optional validator artifacts
- build specialization targets
- apply proof-driven elimination: when Lean discharges a runtime condition, hoist it into artifacts/config and remove the corresponding runtime branch.

5. Gate
- run correctness + trace gates (blocking in v0)
- run verification + performance gates (advisory in v0)
- run replay hard gate from comparison report artifacts:
  `python3 fawn/bench/trace_gate.py --report fawn/bench/out/dawn-vs-fawn.json`
  CI must run without `--skip-missing` and fail hard if any sample is missing or fails replay checks.
- run release claimability hard gate from comparison report artifacts:
  `python3 fawn/bench/claim_gate.py --report fawn/bench/out/dawn-vs-fawn.json --require-claimability-mode release --require-claim-status claimable --require-comparison-status comparable --require-min-timed-samples 15`
  CI must fail hard if report claim metadata is not explicit release mode claimable/comparable.
- for strict Dawn-vs-Fawn upload comparability, fail fast if the executed `fawn-zig-runtime` binary does not expose/validate upload knobs or appears older than key upload/runtime Zig sources.

6. Benchmark
- run self-contained benchmark matrix
- publish deltas against Dawn/wgpu baselines
- generate post-benchmark visualization artifacts from comparison reports
- include distribution diagnostics in benchmark reporting (ECDF overlays, KS/p-value, Wasserstein, superiority probability, and bootstrap CI summaries)
- for claimable "faster" statements, require reliability checks in addition to comparability:
  minimum timed-sample floor and positive tail deltas (not median-only wins)
- run claim-mode (`--claimability local|release`) for benchmark artifacts that will be used in performance claims

7. Release
- commit only when blocking gates are green
- mandatory release precondition in CI: gate scripts must fail hard when replay or release-claimability checks fail.

## 2. Gate Policy (v0)

v0 is speed-first. Blocking vs advisory:

1. Schema gate: blocking
2. Correctness gate: blocking
3. Trace gate: blocking
4. Verification gate: advisory globally, but per-quirk proof obligation is blocking when `verificationMode=lean_required`
5. Performance gate: advisory (ratchet report)

This keeps process weight aligned with v0 maturity.

### Verification obligation precedence

1. `verificationMode` is the primary selector for Lean obligation.
2. `safetyClass` can impose stricter requirements only if `requireProofLevelForSafetyClass` is non-empty.
3. If both apply, the stricter `proofLevel` requirement wins.

### Zig-first, then Lean-eliminate rule

1. Runtime/hot-path behavior should land in Zig first with deterministic trace evidence.
2. Lean proofs may eliminate runtime checks by moving decisions to bind/build artifacts.
3. Elimination requires deleting the runtime branch, not leaving placeholder behavior.
4. If proof is unavailable, keep explicit Zig behavior and benchmark it.

## 3. Benchmark Matrix (Self-Contained)

Benchmark categories:
1. command encode overhead
2. validation overhead
3. submit latency (`p50`, `p95`, `p99`)
4. allocation churn

Each benchmark run must emit reproducible metadata from `run-metadata.schema.json`.
Matrix definition comes from `fawn/config/benchmarks.json`.
Performance ratchet uses `submit_latency_p95_ms` in `gates.json`.

## 4. Why This Still Counts as "Zero-Tape"

Fawn removes recurring human bureaucracy, not machine-readable controls.

- no recurring committee approval loops for routine decisions
- policies are explicit in config and executed automatically
- human escalation is reserved for policy exceptions

## 5. Debug/Trace Standard

Tracing is binary and deterministic:
- fixed ring buffer settings from `fawn/config/tracing.json`
- required event fields: `module`, `opCode`, `seq`, `timestampMonoNs`, `hashes`
- crash artifact: binary dump + metadata JSON
- replay tool must reproduce module sequence and hash chain

## 6. Thresholds and Placeholder Policy

Some thresholds in `gates.json` are bootstrap placeholders.

Rules:
1. placeholders must be marked explicitly in config
2. placeholders are non-blocking in v0
3. thresholds become blocking only after baseline stabilization window
4. placeholder policy applies to thresholds/reports only; runtime execution paths must be explicit implementations or explicit unsupported errors

## 7. Toolchain Upgrade Mechanism

Toolchains are pinned in `toolchains.json`.

Upgrade flow:
1. open dedicated upgrade branch
2. bump toolchain config
3. run blocking + advisory gates
4. compare delta reports
5. merge only if blocking gates pass
