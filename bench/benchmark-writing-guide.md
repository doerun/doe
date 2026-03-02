# Fawn Benchmark Writing Guide

This guide defines how to add and evolve benchmarks so results stay reproducible, apples-to-apples, and claim-safe.

## Scope

Applies to:
- `bench/workloads.json`
- `bench/workloads.*.json`
- `examples/*_commands.json`
- `bench/compare_dawn_vs_doe.config.*.json`
- `config/comparability-obligations.json`
- `config/backend-timing-policy.json`
- `config/webgpu-spec-coverage.json`
- `config/dropin_abi.symbols.txt`

## 1) Non-negotiables

- Comparable lanes must be apples-to-apples by default.
- Any runtime-visible benchmark contract change must be schema/config-backed.
- Strict comparability must fail fast on mismatch, not silently report timings.
- Directional and claimable evidence must stay explicitly separated.
- Artifacts must be reproducible from config + workload + command files.

## 2) Source-of-truth files and checkpoints

- Workload contracts:
  - `bench/workloads*.json`
  - DOE-vs-DOE strict fullsuite contract: `bench/workloads.amd.vulkan.extended.doe-vs-doe.json`
- Compare harness:
  - `bench/compare_dawn_vs_doe.py`
  - `bench/compare_dawn_vs_doe_modules/comparability.py`
  - `bench/compare_dawn_vs_doe_modules/timing_selection.py`
- Comparability obligation contract:
  - `config/comparability-obligations.json`
  - `lean/Fawn/Comparability.lean`
- Timing policy contract:
  - `config/backend-timing-policy.json`
  - `bench/vulkan_timing_policy_gate.py`
- Coverage artifacts:
  - `config/webgpu-spec-coverage.json`
  - `config/dropin_abi.symbols.txt`

Required checkpoints for benchmark contract changes:
- `python3 bench/comparability_obligation_parity_gate.py`
- `python3 bench/schema_gate.py`
- targeted compare run for the modified lane/config
- timing policy gate on that report (`bench/vulkan_timing_policy_gate.py` for Vulkan timing-policy-bound lanes)

## 3) Workload contract format (`bench/workloads*.json`)

Each workload entry is parsed by `bench/compare_dawn_vs_doe.py`.

Required fields:
- `id`
- `name`
- `commandsPath`
- `quirksPath`
- `vendor`
- `api`
- `family`
- `driver`
- `dawnFilter`
- `domain`

Common comparability fields:
- `comparable`
- `default`
- `comparabilityNotes`
- `timingNormalizationNote`
- `leftCommandRepeat`
- `rightCommandRepeat`
- `leftIgnoreFirstOps`
- `rightIgnoreFirstOps`
- `leftUploadBufferUsage`
- `rightUploadBufferUsage`
- `leftUploadSubmitEvery`
- `rightUploadSubmitEvery`
- `leftTimingDivisor`
- `rightTimingDivisor`
- `allowLeftNoExecution`
- `extraArgs`

Strict Dawn-vs-Doe operation comparability rule:
- when `comparability=strict` and `requireTimingClass=operation`, comparable workloads must use direct timing:
  `leftTimingDivisor=1.0` and `rightTimingDivisor=1.0`.

Parser-level field constraints:
- `id` must be non-empty and unique per file.
- `left/rightCommandRepeat >= 1`
- `left/rightIgnoreFirstOps >= 0`
- `left/rightUploadSubmitEvery >= 1`
- `left/rightTimingDivisor > 0`
- strict Dawn-vs-Doe operation runs require `left/rightTimingDivisor == 1.0` for `comparable=true` workloads
- `left/rightUploadBufferUsage` must be `copy-dst-copy-src` or `copy-dst`
- `comparabilityCandidate.enabled=true` requires `comparabilityCandidate.tier`
- `comparabilityCandidate.enabled=true` cannot be combined with `comparable=true`

### 3.1 Workload ID naming contract (required)

Workload IDs are immutable contract keys. They must be stable across benchmark-class promotion and methodology changes.

Required pattern:
- `domain_subject_shape_variant` (snake case tokens)

Required rules:
- include domain first (for example: `upload`, `compute`, `render`, `pipeline`, `resource`, `surface`, `capability`, `lifecycle`, `texture`)
- encode operation semantics and stable shape descriptors (`1kb`, `200k`, `mip8`, matrix geometry, etc.)
- keep IDs status-free and lifecycle-free; do not encode maturity tier or rollout state
- do not rename an existing ID when it moves between directional/comparable/claim lanes; change metadata fields instead
- avoid overloaded shorthand prefixes (`par_`, `exp_`, `ctr_`) and status tokens (`contract`, `proxy`, `macro`) in new IDs

Classification and methodology belong in fields, not ID text:
- `comparable`
- `benchmarkClass`
- `comparabilityCandidate`
- `comparabilityNotes`
- timing normalization fields

## 4) Apples-to-apples strict rules for comparable workloads

Comparable workloads (`comparable=true`) in strict mode must satisfy both:

1. Contract symmetry:
- left/right command repeat match
- left/right ignore-first match
- left/right upload usage + submit cadence match
- left/right timing divisor match

2. Measured comparability obligations:
- `left_right_trace_meta_source_match`
- `left_right_timing_selection_policy_match`
- `left_right_queue_sync_mode_match`
- `left_right_execution_shape_match` (compute-like domains only)
- `left_upload_ignore_first_scope_consistent`
- `right_upload_ignore_first_scope_consistent`

Obligation IDs are contract-controlled by `config/comparability-obligations.json`.

## 5) Execution-shape parity (critical lesson)

Normalization symmetry alone is not enough. A workload can still be invalid if runtime execution shape diverges.

Strict compute-like comparability now requires matching sampled execution tuples:
- `executionDispatchCount`
- `executionRowCount`
- `executionSuccessCount`

If these differ left/right, strict comparable classification must fail.

Use this to prevent false claims from rows where one side executes more internal dispatches than the other.

## 6) Timing selection and normalization policy

For strict Dawn-vs-Doe claim lanes, required timing class is `operation` by default.

For same-runtime parity lanes (Doe-vs-Doe or Dawn-vs-Dawn), operation timing remains
allowed under their lane contracts.

Current selection priorities in compare harness:
1. Explicit `traceMeta.timingMs`/`timingSource` when present and valid.
2. Upload-domain row-total execution durations (`doe-execution-row-total-ns`) when execution evidence exists.
3. Execution total (`doe-execution-total-ns`) when execution evidence exists.
4. GPU timestamp total (`doe-execution-gpu-timestamp-ns`) as fallback.
5. Dispatch window (`doe-execution-dispatch-window-ns`) when available.
6. Trace window or wall-time fallback only when operation sources are unavailable.

Benchmark intent split (required reporting separation):

1. `apples-to-apples`:
   - workload contract marked comparable
   - strict comparability on
   - same timing basis across sides (default: `operation`)
2. `doe-advantage`:
   - directional/optimized workload contract
   - still measured with the same timing basis rule as apples-to-apples
   - cannot be reported as apples-to-apples comparable evidence

Upload-specific rule:
- ignore-first adjustment must stay in row-total scope.
- do not mix ignore-first adjustments across different timing scopes.

Important:
- Do not force side-specific render timing overrides in strict apples-to-apples lanes.
- Any allowed source deviations must be explicit in `config/backend-timing-policy.json` (including backend-specific allowlists).

## 7) Delta percent convention

Current report convention is ratio-style with left as baseline:
- `((rightMs / leftMs) - 1) * 100`
- positive means left faster
- negative means left slower

Interpretation examples:
- `+300%` means left is `4x` faster.
- `+400%` means left is `5x` faster.
- `-50%` means left is `2x` slower.

Always read this from report metadata field `deltaPercentConvention`.

## 8) Workload catalog size vs run size

Do not confuse total catalog inventory with one config run subset.

Example:
- active workload catalogs may contain more IDs overall
- a specific strict fullsuite config may intentionally execute a subset (for example, the 31-item DOE-vs-DOE fullsuite contract)

When reporting counts, always state:
- source workload file
- selected workload filter/cohort flags
- final executed workload count in report

## 9) Command file contract (`examples/*_commands.json`)

Command files must be deterministic JSON arrays of command objects with `kind`.

Supported top-level command kinds:
- `upload`
- `copy_buffer_to_texture`
- `barrier`
- `dispatch`
- `dispatch_indirect`
- `kernel_dispatch`
- `render_draw`
- `draw_indirect`
- `draw_indexed_indirect`
- `render_pass`
- `sampler_create`
- `sampler_destroy`
- `texture_write`
- `texture_query`
- `texture_destroy`
- `surface_create`
- `surface_capabilities`
- `surface_configure`
- `surface_acquire`
- `surface_present`
- `surface_unconfigure`
- `surface_release`
- `async_diagnostics`

Authoring rules:
- stable ordering and stable values
- no random payloads
- explicit handles/IDs
- no implicit behavior assumptions hidden in command JSON

## 10) Coverage workflow (ABI, capability, feature mapping)

For new benchmark capabilities:
- map capability/feature coverage in `config/webgpu-spec-coverage.json`
- keep ABI surface contract in `config/dropin_abi.symbols.txt`
- regenerate feature benchmark table:
  - `python3 bench/generate_feature_benchmark_table.py`

Coverage updates are separate from claimability. A covered feature is not automatically claim-ready.

## 11) Recommended workflow for new or changed benchmarks

1. Add or update deterministic command file.
2. Add workload entry in the correct workload catalog.
3. Document normalization and comparability notes.
4. Run targeted compare config in strict mode.
5. Run `comparability_obligation_parity_gate.py` and `schema_gate.py`.
6. Run timing-policy gate for policy-bound lanes.
7. Treat any non-comparable output as diagnostic until obligations are green.

Useful strict run pattern:

```bash
python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.doe-vs-dawn.fullsuite.json
python3 bench/vulkan_timing_policy_gate.py --report bench/out/<timestamp>/vulkan.strict.doe_vs_dawn.fullsuite.apples.json
```

## 12) Anti-patterns

- Marking a workload `comparable=true` without proving execution-shape parity.
- Allowing mixed timing scopes between selection and ignore-first adjustment.
- Using directional or proxy workloads as claim evidence.
- Accepting side-specific timing-policy exceptions not codified in config.
- Reporting speed deltas without `deltaPercentConvention` context.
- Reporting subset counts without stating the workload source file/config.

## 13) Templates

Minimal workload template:

```json
{
  "id": "example_workload_id",
  "name": "example-workload",
  "description": "Brief semantics of the workload.",
  "domain": "compute",
  "comparabilityNotes": "Matched kernel shape and normalization contract.",
  "commandsPath": "examples/example_commands.json",
  "quirksPath": "examples/quirks/amd_radv_noop_list.json",
  "vendor": "amd",
  "api": "vulkan",
  "family": "gfx11",
  "driver": "24.0.0",
  "dawnFilter": "SomePerfSuite.Run/Profile",
  "comparable": true,
  "default": false,
  "leftCommandRepeat": 1,
  "rightCommandRepeat": 1,
  "leftIgnoreFirstOps": 0,
  "rightIgnoreFirstOps": 0,
  "leftUploadBufferUsage": "copy-dst-copy-src",
  "rightUploadBufferUsage": "copy-dst-copy-src",
  "leftUploadSubmitEvery": 1,
  "rightUploadSubmitEvery": 1,
  "leftTimingDivisor": 1,
  "rightTimingDivisor": 1,
  "timingNormalizationNote": "Document unit normalization and divisors.",
  "extraArgs": []
}
```

Minimal command file template:

```json
[
  {
    "kind": "upload",
    "bytes": 1024,
    "alignBytes": 4
  }
]
```
