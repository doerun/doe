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

## 5) Execution-shape parity (critical — applies to ALL domains)

Normalization symmetry alone is not enough. A workload can still be invalid if runtime execution shape diverges.

Strict comparability for ALL domains (compute, render, upload, resource, pipeline, texture) requires matching sampled execution tuples:
- `executionDispatchCount`
- `executionRowCount`
- `executionSuccessCount`

If these differ left/right, strict comparable classification must fail.

This is not optional for non-compute domains. A render workload where LEFT dispatches 500 draws and RIGHT dispatches 0 is not comparable regardless of what `comparable: true` says in the workload contract.

## 5.1) Structural work equivalence (blocking for comparable)

Beyond dispatch count matching, both sides must perform structurally equivalent GPU operations:

1. **Execution completeness**: both sides must execute all commands in the workload. If one side returns `unsupported` or skips execution, the comparison is invalid.

2. **Timing-phase symmetry**: both sides must report non-trivial timing in the same phases (setup_ns, encode_ns, submit_wait_ns). Violations:
   - LEFT setup_ns=0 across all rows AND RIGHT setup_ns>0 → instrumentation gap, not genuine zero cost.
   - LEFT submit_wait_ns=0 across all rows AND RIGHT submit_wait_ns>0 → LEFT is not measuring GPU submission. The "speed win" is a scope mismatch.
   - RIGHT encode_ns=0 across all rows AND LEFT encode_ns>0 → different timing phases dominate on each side.

3. **Hardware-path equivalence**: if one side takes a hardware-specific shortcut (e.g. Apple Silicon UMA shared-memory memset that skips staging+copy) that bypasses operations the other side performs, the delta measures architectural path choice, not implementation quality. Such workloads must:
   - set `"pathAsymmetry": true` in the workload contract
   - include a transferability caveat in `comparabilityNotes`
   - fail strict Dawn-vs-Doe comparability/claimability gates until structural equivalence is restored
   - not be presented as general "faster" claims

4. **Zero-phase anomaly detection**: if one side reports an entire timing phase as identically zero across ALL workloads in a run, treat this as a systemic instrumentation gap. Audit the timing instrumentation before accepting any claimable results from that run.

## 5.2) Structural equivalence audit checklist

Before accepting claimable results from any run:

1. For each workload, verify LEFT and RIGHT dispatch counts match.
2. For each workload, verify both sides report non-zero values in the same timing phases.
3. Flag any workload where one side's total is dominated by a phase the other side reports as zero.
4. Flag any workload where the speed delta comes primarily from setup or submit_wait that only one side measures.
5. For upload workloads on UMA hardware, verify both sides use the same transfer path (staging+copy vs shared-memory memset). If paths differ, mark `pathAsymmetry: true` and treat the workload as non-comparable for strict claim lanes.
6. Reject any "X/Y claimable" summary that has not passed per-workload structural equivalence checks.

## 6) Timing selection and normalization policy

For strict Dawn-vs-Doe claim lanes, required timing class is `operation` by default.

For same-runtime parity lanes (Doe-vs-Doe or Dawn-vs-Dawn), operation timing remains
allowed under their lane contracts.

Current selection priorities in compare harness:
1. Explicit `traceMeta.timingMs`/`timingSource` when present, valid, and compatible with domain timing policy.
2. Upload-domain row-total execution durations (`doe-execution-row-total-ns`) when execution evidence exists.
3. Render/render-bundle encode totals (`doe-execution-encode-ns`) when execution evidence exists.
4. Execution total (`doe-execution-total-ns`) when execution evidence exists.
5. GPU timestamp total (`doe-execution-gpu-timestamp-ns`) as fallback.
6. Dispatch window (`doe-execution-dispatch-window-ns`) when available.
7. Trace window or wall-time fallback only when operation sources are unavailable.

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
- Claiming speed when one side reports 0 dispatches while the other dispatches (broken comparison, not a speed win).
- Claiming speed from zero-phase asymmetry (LEFT submit_wait=0 while RIGHT submit_wait=40ms means LEFT didn't measure GPU submission, not that it was faster).
- Treating universally-zero setup_ns on one side as genuine zero cost when the other side reports material setup. This is an instrumentation gap.
- Presenting hardware-path shortcuts (UMA memset vs staging+copy) as general speed claims without transferability caveats.
- Accepting aggregate "N/N claimable" without per-workload timing-phase audit. The metadata can pass while the actual work performed is structurally different.
- Applying execution-shape parity only to compute domains. Render, upload, resource, and pipeline workloads need the same checks.

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
