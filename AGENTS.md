# Fawn Code Agent

## Scope

This file is the source of truth for Fawn work only.  
Do not apply `dream/AGENTS.md` or `reploid/doppler/AGENTS.md` as process for this project.  
It is acceptable to reuse selected technical principles from those files, as listed here, when directly useful.

## Prime Directive

The objective of `fawn/` is to build a full, performance-first, maintainable replacement for Dawn in Lean + Zig: lean correctness proof support, Zig runtime execution, lighter binaries, easier development, and materially better per-command performance without sacrificing stage discipline.

Build `fawn/` as a machine-driven WebGPU runtime engineering program for quirk ingestion, verification, specialization, and benchmarking with explicit contracts.

- deterministic, schema-first behavior
- reproducible artifacts for audit and replay
- config-driven control, not hidden switches
- speed-first progress with explicit hard/advisory gates

## Mandatory Reading

Before changing Fawn behavior, read:

- `fawn/thesis.md`
- `fawn/architecture.md`
- `fawn/process.md`
- `fawn/status.md`
- `fawn/upgrade-policy.md`
- `fawn/agent/README.md`
- `fawn/lean/README.md`
- `fawn/zig/README.md`
- `fawn/bench/README.md`
- `fawn/trace/README.md`

If a change affects runtime-visible behavior and any mandatory doc above has not been read in the current task, stop and read it before editing code.

For Dawn-vs-Fawn performance work, also read:

- `fawn/performance-strategy.md`

## Core Principles (adopted)

1. Config as code
- controls and thresholds live in `fawn/config/*.json`
- deterministic defaults and tunables come from config/schema, not ad-hoc code branches

2. Explicit over implicit
- behavior must be explainable from inputs, schema, and artifact contracts
- no hidden heuristics and no undocumented fallback modes in runtime paths

3. Contracts first
- change contracts via `fawn/config/*schema*.json` and migration notes
- update schemas when runtime-visible behavior changes

4. No silent capability branching
- unsupported capabilities fail with explicit, actionable errors
- do not auto-switch to hidden behavior not declared in contracts

5. Reproducibility
- every quality decision should emit artifacts required by gates in `fawn/process.md`
- benchmark and trace artifacts must include traceability fields (module/op hash chain)

## Fawn Non-negotiables

1. No undocumented manual toggles in runtime
- any production behavior change must be reflected in versioned config.

2. Placeholder discipline
- placeholders are allowed only for benchmark/gate bootstrap thresholds when explicitly flagged in config and tracked in `fawn/status.md` and gate policy.
- runtime behavior placeholders are not allowed in `fawn/zig` execution paths; implement fully or fail with explicit unsupported taxonomy.

3. Schema discipline
- never add fields that are not represented by a schema or migration entry.

4. Artifact discipline
- all artifact inputs and outputs for a stage must be versioned and hash-linked where appropriate.

5. Gate discipline
- blocking in v0: schema, correctness, trace
- advisory in v0: verification, performance
- release only when blocking gates are green.

6. Dawn apples-to-apples discipline
- all Dawn-vs-Fawn performance claims must be apples-to-apples by default.
- strict comparability is required for claimable results; directional runs must be explicitly labeled non-comparable.
- benchmark methodology knobs that affect comparability must be explicit in config/workload contracts, never hidden in code.
- fail fast on comparability mismatch instead of reporting timings.

7. Incumbent development discipline
- performance development against Dawn must preserve matched workload semantics: backend/adapter constraints, operation shape, repeat accounting, and timing unit normalization.
- if methodology differs from Dawn, the report and docs must state the deviation explicitly.

8. Contract update discipline
- runtime-visible field changes require schema updates and migration notes in the same change.
- process/gate docs and status tracking must be updated in the same change when behavior or contracts change.

## Stage discipline (must preserve order)

1. Mine
2. Normalize
3. Verify
4. Bind
5. Gate
6. Benchmark
7. Release

Do not bypass earlier stages to satisfy later-stage outcomes.

## Verification guidance

- verification mode governs whether Lean is advisory or blocking.
- map verification obligations to config (`verificationMode`, `safetyClass` where present) then execute.
- if a verification requirement is unmet for `lean_required`, the result is a blocking gate failure.

## Runtime boundaries

- ingestion and policy should remain in `agent/` and `bench/trace` tooling;
- proof-bound work belongs to `lean/`;
- specialization work belongs to `zig/`;
- shared orchestration in `process.md` and config files.

## Zig-First, Lean-Eliminate Policy

- for latency-critical runtime behavior and incumbent replacement paths, implement deterministic behavior in Zig first.
- then attempt proof-driven elimination: if Lean can discharge a runtime condition, remove that branch from runtime Zig paths and hoist it into verified artifacts/config.
- "leaning out" means deleting runtime logic, not moving hot-path execution into a runtime Lean interpreter.
- if a condition cannot be proven/hoisted yet, keep the explicit Zig implementation and measure it.

## Implementation style

- keep modules small, composable, and explicit in data flow
- avoid one-file catchall utilities
- prefer pure transforms for deterministic stages
- minimize inline commentary; use field names and namespaced constants for intent
- if adding selection logic, prefer rule-map data over branching ladders

## File size

- 777 lines max per source file; shard before exceeding this
- split by cohesive functionality, not by arbitrary line count
- group by feature (e.g. `pipeline_cache.zig`) not by type (e.g. `helpers.zig`)
- keep related code together; splitting a file must not scatter a single concern

## Constants and thresholds

- no bare magic numbers in runtime code; use named constants or config values
- centralize thresholds in config or module-level constants, not inline literals
- if a value appears in more than one place, it must have a single source of truth
- fallbacks must reference named constants or config getters, never bare literals

## Error handling

- fail fast on invalid inputs with descriptive messages
- unsupported operations return explicit taxonomy errors, not silent no-ops
- include actionable context: what was expected, what was received

## Comments

- comments explain why, not what
- do not add comments that restate the code
- do not add ad-hoc debug logging; use structured trace output

## Naming (Zig)

- snake_case for functions, variables, fields
- PascalCase for types and structs
- UPPER_SNAKE_CASE for comptime constants
- file names: snake_case.zig

## Naming (config/JSON)

- camelCase for JSON fields
- snake_case for workload/artifact identifiers
- kebab-case for file names

## Benchmark style

- benchmark output must conform to the trace-meta schema
- include traceability fields: module, hash chain, timing source, timing class
- warmup before timed runs; discard warmup from reported metrics
- use shared stats for percentiles and outlier filtering
- comparisons require matched workloads: same dispatch geometry, same repeat count, same sampling settings
- report deviations from baseline methodology explicitly in comparison notes
- regression thresholds belong in config, not hardcoded in harness code
- Dawn-vs-Fawn upload benchmarking must explicitly specify and report: first-op handling, upload buffer usage flags, submit cadence, and per-op normalization divisors.
- Dawn-vs-Fawn strict mode must fail when apples-to-apples requirements are not met.
- Claimable "faster" results require reliability checks in addition to strict comparability:
  minimum timed-sample floor and positive tails (`p50` + `p95`; include `p99` for release claims).
- Upload claim runs must use timing-source semantics that stay consistent with the measured operation scope.
  If timing-source and ignore-first adjustments mix scopes, classify the run as diagnostic.

## Completion checklist

For each change set, verify:

- schema updates and migration notes are consistent
- docs under `fawn/` reflect behavior
- gate expectations were updated or confirmed in `fawn/process.md`
- trace/replay outputs are consistent with the changed behavior
- if Dawn-vs-Fawn benchmarking changed, apples-to-apples methodology is documented and enforced by fail-fast checks
- `fawn/status.md` records remaining placeholders, temporary methodology choices, and follow-up work
