# Doe code agent

## Git workflow: direct to main

- Work and commit directly on the owning repository's `main` branch, then push
  directly to its existing `origin/main` remote branch.
- Do not create feature/task branches, branch-backed worktrees, or GitHub pull
  requests. Do not use a branch/PR workflow unless the user explicitly requests it.
- If the checkout is on another branch, preserve its work and move the task to
  `main` safely; never discard changes to switch branches.
- Stage only task-related changes, run the applicable checks, and integrate remote
  updates without overwriting unrelated work. Never force-push `main`.
- Report the pushed commit or the concrete blocker. A local commit is not a push.

## Scope

This file is the source of truth for Doe work only.
Do not apply `dream/AGENTS.md` or `doppler/AGENTS.md` as process for this project.
It is acceptable to reuse selected technical principles from those files, as listed here, when directly useful.

Repository mission and durable goals live in [`GOALS.md`](GOALS.md). Component
authority and invariants live in the applicable [`CATSCAN.md`](CATSCAN.md)
chain. This file enforces discovery and working protocol; it does not redefine
component goals.

## Component intent

Before modifying a file, read every `CATSCAN.md` from the project root to the
target directory, in order. For work spanning directories, read the union of
the applicable chains. Use `rg --files -g CATSCAN.md` and
[`docs/component-index.md`](docs/component-index.md) to discover the chain.

Treat `Target`, `Authority`, `Scope`, `Contracts`, `Invariants`, `Acceptance`, and `Non-goals` as
implementation constraints. A child `CATSCAN.md` may narrow its parent but may
not contradict it, broaden its authority, or weaken an invariant. Existing code
does not overrule a charter; code may itself have drifted.

If requested work changes a component boundary, identify the conflict and
update the affected `CATSCAN.md` with the implementation. Do not silently work
around it. Explicit user direction may change intent, but the corresponding
charter and acceptance evidence must change in the same work. Do not rewrite a
charter to excuse a failing implementation, test, or receipt.

Novel implementations are welcome. `CATSCAN.md` constrains outcomes and
authority, not internal algorithms. Do not add a charter to a utility folder or
mechanical subdivision that can inherit its nearest parent.

Agent handoffs for component-changing work must state:

```text
Component: <name>
Intent: preserved | changed
Acceptance evidence: <commands/artifacts>
Boundary effects: <none or named components>
```

## Tooling surface contract

Canonical public/internal/archive tooling separation is defined in:

- `config/tool-surfaces.json`
- `docs/internal-tooling.md`

Default assumptions:

- only `packages/doe-gpu/` exports and docs are the public npm package contract
- `bench/`, `browser/chromium/`, `pipeline/`, top-level `scripts/`, and
  contributor tooling under `runtime/zig/` are repo-only unless the tooling
  manifest marks them `audience=public`
- legacy npm names `@simulatte/webgpu` and `@simulatte/webgpu-doe` redirect to
  `doe-gpu`
- `pipeline/dawn-research/` is a Gerrit CL analysis pipeline (research surface; see
  `pipeline/agent/README.md`) referenced by `config/tool-surfaces.json`
- `docs/archive/nursery/` retains archive navigation; current CI does not consume
  executable surfaces there. Chromium integration lives in `browser/chromium/`, and CTS
  provider tooling lives in `bench/cts/`. Use `config/tool-surfaces.json` and
  current workflow paths when classifying a surface.

Do not infer public product commitments from repo-only tools, scripts, or
historical docs.

## Mandatory reading

Before changing Doe behavior, read:

- `GOALS.md`
- the applicable root-to-target `CATSCAN.md` chain
- `docs/thesis.md`
- `docs/architecture.md`
- `docs/process.md`
- `docs/status.md`
- `docs/upgrade-policy.md`
- `docs/licensing.md`
- `pipeline/agent/README.md`
- `pipeline/lean/README.md`
- `runtime/zig/README.md`
- `runtime/zig/STYLE.md`
- `bench/README.md`
- `pipeline/trace/README.md`

If a change affects runtime-visible behavior and any mandatory doc above has not been read in the current task, stop and read it before editing code.

For Dawn-vs-Doe performance work, also read:

- `SKILLS.md`
- `docs/performance-strategy.md`

For any Cerebras lane work (Doppler → Doe → Cerebras), start at
`docs/cerebras.md`. That is the single front door — progress snapshot,
source-code locations, reproduce/build/verify commands, hardware runbook
pointer, and rationale all in one page. The bundle packer and
claim-discipline gate depend on `docs/cerebras-evidence-bundle.md` and
`docs/hardware-validation-appendix.md`; do not delete or rename those.

## Current work selection

Vulkan is the current engineering focus. Work proceeds in bounded batches.
Switching to Metal requires an explicit prioritization decision and handoff;
D3D12 remains deferred. Existing regression checks do not constitute parallel
optimization campaigns. The pinned ONNX Vulkan integration and local isolated
installation already have evidence; start at `docs/onnx-vulkan-installation.md`.
Prioritize independent installation, one real consumer requirement, and retained
use. Correctness, packaging, and independently useful engineering do not require
customer payment. Compiler adoption is independent of runtime adoption; select
new compiler opportunities explicitly and keep closed browser experiments closed.

## Core principles (adopted)

1. Config as code
- controls and thresholds live in `config/*.json`
- deterministic defaults and tunables come from config/schema, not ad-hoc code branches

2. Explicit over implicit
- behavior must be explainable from inputs, schema, and artifact contracts
- no hidden heuristics and no undocumented fallback modes in runtime paths

3. Contracts first
- change contracts via `config/*schema*.json` and migration notes
- update schemas when runtime-visible behavior changes

4. No silent capability branching
- unsupported capabilities fail with explicit, actionable errors
- do not auto-switch to hidden behavior not declared in contracts

5. Reproducibility
- every quality decision should emit artifacts required by gates in `docs/process.md`
- benchmark and trace artifacts must include traceability fields (module/op hash chain)

## Intent-First Operations

- Treat Doe intent as source-preserving compiler/runtime evidence, not package copy or benchmark prose.
- If the user asks whether a Doe claim is true, inspect the current artifacts, gates, raw benchmark rows, browser smoke outputs, and source files before answering.
- For publish-readiness or stale-claim questions, inspect `reports/claim-index.json` and every referenced sidecar before answering.
- When a Dawn-vs-Doe comparison is distrusted, fix or harden the benchmark fairness gate before changing README/docs language.
- Do not answer that Doe beats Dawn from `claimStatus` alone; verify same work, same timing scope, non-missing dispatch/readback work, and raw timing sign.
- For Doe-vs-Dawn performance questions, answer row by row with: row id, backend, comparator, p50 sign, p95 sign, claim status, artifact path, and caveat.
- If the user asks for a browser proof path, distinguish npm package status from a Chromium/Fawn browser artifact and report the exact build/output state.
- For publish readiness, split the answer into: npm package, native runtime evidence, browser/Fawn artifact, docs/charts, and npm auth.
- Do not frame publish work as blocked before checking local package files, release artifacts, claim index rows, sidecars, docs/charts, and auth state.
- When the user says a diagnostic release row must be claimable, treat it as a failing release criterion: identify the measured loss or tail-stability cause, patch or rerun, then update the claim index from artifacts.
- If the user asks for real browser/demo benchmarks, inventory existing particle/WebGPU HTML demos, verify whether they run in Fawn, and name the benchmark harness needed before discussing evidence boundaries.
- Public claims must point to artifact paths or release files. Prose must not substitute for missing evidence.
- If a result looks suspicious, say so directly and treat it as a harness or methodology problem until the artifact proves otherwise.

## Non-negotiables

1. No undocumented manual toggles in runtime
- any production behavior change must be reflected in versioned config.

2. Placeholder discipline
- placeholders are allowed only for benchmark/gate bootstrap thresholds when explicitly flagged in config and tracked in the status log (`docs/status.md` front door plus the relevant live topical shard under `docs/status/*.md`) and gate policy.
- runtime behavior placeholders are not allowed in `zig` execution paths; implement fully or fail with explicit unsupported taxonomy.

3. Schema discipline
- never add fields that are not represented by a schema or migration entry.

4. Artifact discipline
- all artifact inputs and outputs for a stage must be versioned and hash-linked where appropriate.

5. Synthetic runtime-state ban
- no backend file may implement fake/synthetic runtime-state behavior, including any `*_runtime_state.zig` module; backend timing and capability behavior must be native or explicit unsupported behavior.
- any native/runtime module import or file matching that pattern is a hard rejection in `runtime/zig/tools/check_core_import_fence.py`.

6. Gate discipline
- blocking in v0: schema, correctness, trace, verification
- advisory in v0: performance
- release only when blocking gates are green.

7. Dawn apples-to-apples discipline
- declare either unchanged-application replacement or fixed-operation/shader experiment before freezing the workload; follow `docs/performance-strategy.md#comparison-classes`.
- equivalent application work does not require identical internal implementation work. Missing required execution invalidates a comparison; verified elimination of unnecessary work may constitute the advantage.
- unchanged-application replacement preserves application inputs, requested work, output/numerical requirements, validation obligations, and complete timing boundaries. Internal allocations, copies, submissions, caches, and generated programs may differ when those obligations remain equivalent.
- fixed-operation/shader experiments preserve the declared execution shape, effective paths, and cache/preparation controls needed to isolate the named transformation. Differences outside that treatment make the result diagnostic.
- strict comparability is required for claimable results; methodology and treatment must be explicit in versioned workload contracts and checked by fail-fast gates. Directional runs remain non-comparable.
- do not bypass existing gates using this prospective clarification. Existing frozen contracts, thresholds, and historical verdicts retain their meaning; a new comparison class needs matching executable checks before promotion.
- compute/pipeline operation-speed claims stay on selected operation timing. Workload-unit wall cannot rescue a failed selected-operation claim.
- host kernel/pipeline prewarm remains diagnostic overhead outside selected execution timing unless the contract declares a separate timing class; retain its cost and provenance. Do not hide preparation outside a complete-application boundary.
- if selected-operation timing and workload-unit wall disagree on claim sign, audit scope and retain both. Neither result establishes the other claim.
- observe effective readback paths, completion, and output visibility. Different mechanisms can qualify an application replacement when semantics and complete boundaries match; fixed-path operation experiments require the declared path parity.
- hardware-specific elimination such as shared-memory access replacing staging requires verified semantics and explicit hardware/transferability caveats. Record `pathAsymmetry` where required by the workload schema; it cannot become a general hardware claim.
- inspect raw `baselineStatsMs` and `comparisonStatsMs`, compute the speed ratio, and verify work and timing before accepting `claimStatus=claimable`.
- speedups at or above `reliability.suspiciousSpeedupRatio` in `config/benchmark-methodology-thresholds.json`, or near `+90%` under percent-of-comparison, trigger fairness audits. Check omitted work, hidden fallback, asymmetric warmup/precomputation, cache opportunities, and costs moved outside measurement.
- flag suspicious results immediately even if existing gates label them comparable.

8. Incumbent development discipline
- preserve application-level work, backend/adapter constraints, repeat accounting, and timing normalization. Match internal operation shape where the fixed-operation contract requires it.
- give controls equivalent application-level reuse opportunities, starting state, input history, and warmup. Disclose internal caching and preparation rather than requiring identical implementation strategies.
- reports must state every methodology deviation explicitly.

9. Contract update discipline
- runtime-visible field changes require schema updates and migration notes in the same change.
- process/gate docs and status tracking must be updated in the same change when behavior or contracts change.

10. Structural work equivalence discipline
- verify required execution for every domain against the declared comparison class, not just matching methodology metadata.
- unsupported results, omitted required commands, hidden fallback, or absent required completion/readback invalidate the comparison.
- fixed-operation experiments check declared dispatch/command counts and success counts. Application replacements may eliminate or combine internal work only with independent evidence of equivalent requested computation and lifecycle semantics.
- unexplained zero dispatches or an identically zero phase trigger an instrumentation/work audit. Keep results diagnostic until evidence distinguishes verified elimination from missing execution or observation.
- positive deltas from mismatched application requirements or undeclared experimental treatments are not speed claims.

11. Timing-scope completeness discipline
- both sides measure the same declared boundary and required completion. Encode-only cannot compare with setup+encode+submit+wait.
- corresponding internal phases need not cost equally or all exist; every required cost must be inside its declared boundary. Record and substantiate eliminated work rather than fabricating phase symmetry.
- render execution without required GPU completion is incomparable. Shared-memory upload replacing staging may qualify only under equivalent application semantics and explicit hardware scope.
- retain cold initialization, preparation, resident execution, and cleanup as declared. No asymmetric warmup, moved costs, or post-result choice of timing class.

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

- ingestion and policy should remain in `pipeline/agent/`, `pipeline/trace/`, and `bench/` tooling;
- proof-bound work belongs to `pipeline/lean/`;
- specialization work belongs to `runtime/zig/`;
- shared orchestration in `docs/process.md` and config files.

## Zig-first, Lean-eliminate policy

- for latency-critical runtime behavior and incumbent replacement paths, implement deterministic behavior in Zig first.
- then attempt proof-driven elimination: if Lean can discharge a runtime condition, remove that branch from runtime Zig paths and hoist it into verified artifacts/config.
- "leaning out" means deleting runtime logic, not moving hot-path execution into a runtime Lean interpreter.
- if a condition cannot be proven/hoisted yet, keep the explicit Zig implementation and measure it.

## Systematic Zig review

For systematic Zig cleanup, use [`runtime/zig/reviews/README.md`](runtime/zig/reviews/README.md)
and its append-only log. Begin with `python3 runtime/zig/tools/review_log.py --next`;
`config/zig-review-plan.json` owns the bounded active and ready batches, while
`queue.tsv` retains complete coverage rather than prescribing alphabetical work.
Review each file, directory organization, relationships
within directories, cross-directory boundaries, and complete execution paths as
separate passes. Existing module decisions and passing gates do not grant code
review credit. Partial inspection remains unfinished; higher-level completion
requires current lower-level reviews and its own findings and evidence.

Append findings, fixes, verification artifacts, and the next concrete action
before handing off a review. Regenerate and check the queue with
`python3 runtime/zig/tools/review_log.py --write` and `--check`. When checking a
committed change, pass `--base-ref` with its predecessor or an explicitly selected
baseline on `main` to enforce history preservation across the change. Source ownership policy remains in the
existing charter chain and architecture manifest.

## Implementation style

- keep modules small, composable, and explicit in data flow
- avoid one-file catchall utilities
- prefer pure transforms for deterministic stages
- minimize inline commentary; use field names and namespaced constants for intent
- if adding selection logic, prefer rule-map data over branching ladders

## Documentation drift prevention

- never embed counts, percentages, or benchmark results in prose; reference the artifact path
- structural claims ("Doe has a native DXIL emitter") are validated by CI against file existence
- when a doc needs a specific number, use the pattern: "See `path/to/artifact.json` for current count."
- `docs/status.md` is the concise status front door; live status details live in topical shards under `docs/status/*.md`, and dated append-only history lives in `docs/status/archive/*.md`
- new state goes at the top of the relevant topical shard; live shards are LOC-capped and must be split by subdomain before they grow past the cap, and old archive entries are not edited except for deliberate archive maintenance
- artifacts are the source of truth, not docs:
  - theorem count/categories: `pipeline/lean/artifacts/proven-conditions.json`
  - benchmark results: `bench/out/*/dawn-vs-doe.*.json`
  - browser smoke: `browser/chromium/artifacts/*/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
  - backends: `runtime/zig/src/backend/*/`
  - test status: `zig build test-wgsl` exit code
- prose describes what kind of thing exists, not how many; the artifact has the count

## Documentation style

- Markdown document titles and section headings use sentence case

## File size

- `runtime/zig/source-layout.json` is the source of truth for Zig source size policy
- 800 lines is an advisory architecture review signal
- handwritten production files above 1,200 lines require a cohesive-module justification in the architecture manifest
- handwritten production files above 1,500 lines fail the gate
- generated files use separately declared reproducible generation contracts
- split by named semantic responsibility, not by arbitrary line count
- group by feature (e.g. `pipeline_cache.zig`) not by type (e.g. `helpers.zig`)
- keep related code together; splitting a file must not scatter a single concern
- Python benchmark and tooling files must stay modular; when a file exceeds 1200 lines, add a tracked sharding follow-up in the relevant live topical shard with owner and next split target.

## Constants and thresholds

- inline `0`, `1`, simple indexing values, and language-level sentinels when
  they express local mechanics clearly
- name domain, ABI, policy, threshold, size, retry, and timing values
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

## No speculative engineering timelines

- Do not predict how long a coding, software-engineering, product-implementation, refactor, migration, launch, or similar work item will take. Avoid speculative delivery statements such as "1-2 weeks", "four months", or "a quick fix".
- Describe planned work through concrete deltas, dependencies, risks, and validation instead of calendar duration.
- This restriction does not apply to factual status for an already-running command, script, benchmark, training run, skill, deployment, or algorithm. You may report elapsed time, measured runtime, progress, and a grounded ETA when the active process exposes enough evidence.
- Do not invent an ETA for an active process. If it does not expose one, report its current phase, latest output, and whether it is still making progress.

## Style guides

Each language has a dedicated style guide. Read the relevant guide before
editing code in that surface:

- Zig: [`runtime/zig/STYLE.md`](runtime/zig/STYLE.md)
- JavaScript: [`packages/doe-gpu/STYLE.md`](packages/doe-gpu/STYLE.md)
- JSON/config: [`config/STYLE.md`](config/STYLE.md)
- Python: [`bench/STYLE.md`](bench/STYLE.md)
- Lean: [`pipeline/lean/STYLE.md`](pipeline/lean/STYLE.md)

## Benchmark style

- fairness is the first benchmark requirement; a faster number is not useful
  until the benchmark proves both sides did equivalent work
- benchmark output must conform to the trace-meta schema
- include traceability fields: module, hash chain, timing source, timing class
- warmup before timed runs; discard warmup from reported metrics
- use shared stats for percentiles and outlier filtering
- comparisons require equivalent requested work, repeat accounting, and sampling; fixed-operation experiments additionally preserve their declared dispatch geometry
- report deviations from baseline methodology explicitly in comparison notes
- regression thresholds belong in config, not hardcoded in harness code
- Dawn-vs-Doe upload benchmarking must explicitly specify and report: first-op handling, upload buffer usage flags, submit cadence, and per-op normalization divisors.
- Dawn-vs-Doe strict mode must fail when apples-to-apples requirements are not met.
- Claimable "faster" results require reliability checks in addition to strict comparability:
  minimum timed-sample floor and positive tails (`p50` + `p95`; include `p99` for release claims).
- Upload claim runs must use timing-source semantics that stay consistent with the measured operation scope.
  If timing-source and ignore-first adjustments mix scopes, classify the run as diagnostic.
- Before accepting a claimable result, verify work equivalence against the
  declared comparison class and observe actual execution, completion, and readback.
  Fixed-operation controls retain required path/dispatch parity; application
  replacements may demonstrate verified elimination under complete timing scopes.
- Treat implausibly large speedups as suspicious until audited. Before citing
  them, check for cache/prepared-session differences, skipped work, one-sided
  setup/upload/submit/readback cost, mismatched runtime paths, hidden fallback,
  stale artifacts, and timing-scope errors. If the cause is not proven fair,
  label the result diagnostic instead of claimable.
- Zero-phase anomaly: unexplained zero setup, encode, or submit_wait triggers an
  audit. Keep affected results diagnostic until verified elimination or complete
  instrumentation establishes that the declared obligations were met.

## Benchmark front doors

- first-time benchmark execution instructions live in `bench/README.md` under
  `First benchmark matrix`; use that matrix instead of inferring support from
  scattered config filenames
- prefer `python3 bench/cli.py compare` with promoted profiles when available;
  verify the current promoted matrix with `python3 bench/cli.py compare --list-promoted`
- current front-doored coverage is narrower than the full taxonomy:
  - backend native Doe-vs-Dawn is front-doored on `apple-metal`,
    `amd-vulkan`, and `local-d3d12`
  - plan compare is currently front-doored on `apple-metal` only
  - package compare is currently front-doored on `apple-metal`, `amd-vulkan`,
    and `local-d3d12` for Node/Bun cold and warm Gemma package lanes
  - AMD Vulkan Gemma270m package compares remain explicit config-backed files,
    not promoted `--surface package` profiles
  - local D3D12 package profiles are promoted contracts; claim evidence still
    requires a compatible Windows/D3D12 host
- do not assume every `platform x surface x runtimeHost` tuple named in the
  taxonomy is promoted or evidenced; check the promoted list or an explicit
  compare config path before benchmarking

## Completion checklist

For each change set, verify:

- schema updates and migration notes are consistent
- docs in this repo reflect behavior
- gate expectations were updated or confirmed in `docs/process.md`
- pipeline/trace/replay outputs are consistent with the changed behavior
- if Dawn-vs-Doe benchmarking changed, apples-to-apples methodology is documented and enforced by fail-fast checks
- if any workload is marked claimable, verify required work, timing completeness,
  declared fixed-operation controls or substantiated application-level elimination,
  hardware scope, and the fairness audit for any unusually large speedup
- the status log (`docs/status.md` plus the relevant topical shard) records remaining placeholders, temporary methodology choices, and follow-up work

## Pick the real fix

- when you find a correctness bug, the default is to fix it, not to relabel it
- do not use effort or scope framing ("non-trivial", "real engineering effort", "worth its own thread", "we'll address later") as cover for choosing a lesser fix
- do not propose "mark experimental", "add a TODO", or "rewrite the misleading comment" as a substitute for the actual engineering work when the underlying behavior is wrong
- if scope genuinely must be split, describe the concrete deltas and ask the user which path to take, do not pre-decide a smaller version
