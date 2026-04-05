# Config Migration Notes

## 2026-04-05

### Metal strict workload lane drops legacy Gemma3 plan workloads from the governed cohort and restores `buffer_write` coverage accounting

- `config/backend-workload-cohorts.json`
  - removes the Apple Metal Gemma3 270M plan-backed inference rows from the
    governed cohort
  - keeps those rows available as regression coverage instead of treating them
    as governed strict-compare evidence
  - rationale: the Apple strict compare preset is a commands-boundary lane, and
    comparable plan-backed workloads must now use the normalized plan boundary
- `config/webgpu-command-coverage-core.json`
  - restores the missing `buffer_write` core ledger entry
  - bumps `commandCount` from `10` to `11`
- `config/webgpu-command-coverage-full.json`
  - restores the missing `buffer_write` entry in `coreCoverage`
  - bumps `coreCommandCount` from `10` to `11`
  - bumps `totalCommandCount` from `24` to `25`
- `runtime/zig/build.zig`
  - fixes the `coverage-gate` build step to call
    `bench/gates/split_coverage_gate.py`
    instead of the stale repo-root path

### Gemma 4 CSL bundle contracts add explicit memory/runtime artifacts and derived-grid lowering

- `config/doe-wgsl-memory-plan.schema.json`
  - adds the checked `csl_memory_plan` artifact contract
  - records:
    - derived PE grid
    - PE count
    - residency mode
    - total/persistent/streamed byte counts
    - per-PE working-set estimates
    - explicit buffer placements
    - explicit stream stages
- `config/doe-wgsl-runtime-config.schema.json`
  - adds the checked `csl_runtime_config` artifact contract
  - fixes:
    - `schemaVersion: 1`
    - `artifactKind: "csl_runtime_config"`
    - `target: "wse3"`
    - `contract: "explicit_runtime_config"`
    - `mode: "compile-only"`
    - explicit `modelConfig`
    - optional embedded `memoryPlan` summary
    - explicit `stateBuffers`
- `config/doe-wgsl-simulator-plan.schema.json`
  - bumps `schemaVersion` from `1` to `2`
  - adds optional `driver.executablePath` so checked plans and generated
    bundles can point at a concrete driver executable without relying on the
    env var alone
- `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig`
  - now accepts missing `grid` in step-based execution-v1 lowering when
    `modelConfig` is present
  - derives the grid from the memory planner instead of requiring a hardcoded
    `{ width, height }` in the execution contract
  - still rejects `modelConfig` / `placementPolicy` on the legacy manifest
    lowering path
- `runtime/zig/src/csl_host_plan_tool.zig`
  - now supports emitting a full checked bundle rooted at `--bundle-root`
    instead of only `host-plan.json`
  - generated bundles now include:
    - `host-plan.json`
    - `memory-plan.json`
    - `runtime-config.json`
    - `simulator-plan.json`
    - `launch-simulator.sh`
- consumers of checked examples should treat the new memory-plan and
  runtime-config artifacts as part of the Gemma 4 CSL contract surface; these
  are no longer implicit side calculations in host code
- simulator-plan consumers should now resolve the driver in this order:
  - explicit CLI override
  - `driver.executablePath` from the plan
  - `DOE_CSL_SIM_EXECUTABLE`

### CSL decode device state and broader `currentPosSource` host-plan semantics

- `config/doe-wgsl-host-plan.schema.json`
  - keeps `schemaVersion: 2`
  - now allows `currentPosSource` on launches that do not carry
    `attentionType`, so decode `kv_write` / `kv_write_shared` launches can
    declare explicit position-state consumption
  - still forbids `slidingWindowSize` unless `attentionType: "sliding"` is
    present
- producers that lower Gemma 4 decode `kv_write` or `kv_write_shared` steps
  should now emit `currentPosSource: "decode_position"` on those launches
- Cerebras host scaffolds no longer rely on fake `runner.launch(...,
  current_pos=..., sliding_window=...)` kwargs; they now stage `position` and
  `sliding_window` as explicit device-state buffers before launches

### CSL host-plan launch metadata schema v2

- `config/doe-wgsl-host-plan.schema.json`
  - bumps `schemaVersion` from `1` to `2`
  - moves Gemma 4 execution metadata to launch scope instead of kernel scope
  - launch specs may now carry:
    - `attentionType`
    - `slidingWindowSize`
    - `currentPosSource`
    - `kvCacheAlias`
  - sliding attention launches now require both `slidingWindowSize` and
    `currentPosSource`
- host-plan artifacts and checked examples must now emit `schemaVersion: 2`
- producers that previously wrote `kvCacheAlias` on kernel entries must move it
  to the corresponding launch entry instead
- consumers must reject unknown `attentionType` values and must not infer
  sliding-window behavior when the launch metadata is absent

## 2026-03-30

### Diverse prompt-search seeds and wider pair registry

- `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.prompt-search-sharp.json`
  - expands the live sampled-decode prompt-search seed bank beyond
    operational/security examples into bounded ambiguity prompts across
    philosophy, science, law, identity, and art
- `bench/fixtures/determinism/apple-metal-pair-agnostic-mine.gemma270m.search-loose.json`
  - widens the allowed answer-set ids so the loose miner can score more than
    the original workflow-heavy binary pairs
- `config/determinism-answer-set-registry.json`
  - adds the new bounded answer-set families used by that wider search lane,
    including `mercy/cruelty`, `justice/revenge`, `friend/stranger`,
    `natural/artificial`, `authentic/staged`, `science/faith`,
    `freedom/loss`, and related pairs
- `config/numeric-stability-decode-prompt-search-plan.json`
  - raises the round-1 prompt cap so the expanded seed bank is not silently
    truncated by the old limit
- `bench/runners/search_sampled_decode_prompts.py`
  and `bench/tests/test_search_sampled_decode_prompts.py`
  - structured-choice mutation now preserves multi-option prompts such as
    `X, Y, or both: ...` instead of assuming every seed is binary

## 2026-03-29

### Prompt-search discovery for sampled decode fragility

- `config/numeric-stability-decode-prompt-search-plan.json`
  and `config/numeric-stability-decode-prompt-search-plan.schema.json`
  - add the config-backed discovery plan for finding better sampled-decode
    prompt seeds
  - the plan now fixes:
    - the source real-logit hunt fixture
    - the pair-mining fixture
    - round count and beam width
    - prompt-candidate limits
    - the minimum usefulness score required to keep mutating a case
    - the mutation-template family used for prompt rewrites
- `bench/runners/search_sampled_decode_prompts.py`
  and `bench/tests/test_search_sampled_decode_prompts.py`
  - add the executable search loop that:
    - starts from semantically sharp prompt families or explicit initial seeds
    - runs the existing real-logit scout in rounds
    - mines semantically meaningful near-miss token pairs from each round
    - mutates the strongest cases into the next prompt batch
    - writes a search report that can seed later sampled ordinary-execution
      harvests on Metal
  - this is discovery tooling only:
    it improves prompt quality for the sampled decode lane, but it does not
    replace the live runtime receipt, enrichment, ranking, or promotion path

### Sampled decode harvest and promotion pipeline

- `config/numeric-stability-decode-harvest-plan.json`
  and `config/numeric-stability-decode-harvest-plan.schema.json`
  - add the config-backed Metal harvest plan for sampled ordinary execution
  - the plan now fixes:
    - sampled decode defaults (`temperature`, `topK`, `topP`, `rngSeed`, `rngDraw`)
    - repeat count
    - kernel root
    - backend identity
    - first harvested command streams
- `bench/lib/sampled_decode_fragility.py`
  and `bench/runners/harvest_sampled_decode_fragility.py`
  - add the shared patch/harvest path that:
    - upgrades ordinary `sample.wgsl` commands into sampled mode
    - annotates `decode.final_logits` and `decode.sample_token` with
      step-stable semantic identities
    - harvests real Metal receipts across repeats
    - explodes per-step receipt artifacts for later ranking/promotion
- `bench/runners/enrich_sampled_decode_rows.py`
  - adds the missing evidence attachment pass over harvested receipts:
    - within-policy stability from repeated runs
    - short suffix replay evidence from nearby decode steps
    - normalized rows plus ranked report emission
- `config/numeric-stability-decode-signature.schema.json`
  and `config/numeric-stability-decode-promoted-catalog.schema.json`
  and `config/numeric-stability-decode-promoted-catalog.json`
  and `bench/runners/promote_sampled_decode_fragility.py`
  - add the checked decode-promotion contract
  - promotion now writes a dedicated decode-boundary catalog instead of trying
    to overload the older prompt/operator fragility catalog
  - the current checked result is intentionally empty because the latest live
    Metal harvest produced only control/meaningless rows
- `config/numeric-stability-decode-vulkan-replay-plan.json`
  and `config/numeric-stability-decode-vulkan-replay-plan.schema.json`
  and `bench/runners/replay_promoted_sampled_decode_vulkan.py`
  - add the backend-expansion path for promoted sampled decode cases
  - current replay report is structurally live even though the latest promoted
    decode catalog has zero cases
- `examples/numeric-stability-decode-harvest.manifest.sample.json`
  and `examples/numeric-stability-decode-signature.sample.json`
  - add checked examples for the new harvest/promotion artifact shapes

### Track-1 sampled decode-boundary receipts in ordinary execution

- `runtime/zig/src/numeric_stability_runtime_decode.zig`
  and `runtime/zig/src/numeric_stability_runtime.zig`
  - the decode-boundary lane now parses an expanded `sample.wgsl` uniform ABI
    during ordinary execution
  - when that ABI is present, Doe replays the exact decode function under the
    same:
    - `temperature`
    - `topK`
    - `topP`
    - `rngSeed`
    - `rngDraw`
  - the runtime now computes sampled `fast`, `stable`, and `reference`
    selections from the stored full-vocabulary `decode.final_logits` evidence
    and writes the committed token back into the real sample output buffer
  - the decode-boundary receipt now records live sampled fields instead of
    leaving them reserved and `null`
  - the legacy 16-byte sample uniform remains backward-compatible and still
    reports `decodeMode = greedy-argmax`
- `examples/numeric-stability-decode-sampled.commands.json`
  and `examples/doe-numeric-stability-receipt.decode-sample.sample.json`
  - add a checked-in sampled ordinary-execution decode demo and matching sample
    receipt for the new live sampled contract
- `packages/doe-gpu/test/smoke/test-smoke-load.js`
  and `packages/doe-gpu/README.md`
  - package smoke/docs now exercise the sampled decode-boundary path instead of
    describing the sampling fields as future placeholders

### Repo-truth sync for decode-boundary mining

- `docs/status.md`
  and `config/migration-notes.md`
  - the current live state is now clarified explicitly:
    - greedy `decode.sample_token` receipts are live
    - decode-row normalization already prefers runtime-emitted
      `decodeBoundary.metrics` when present
    - the remaining gap is the richer sampled decode contract, not the
      existence of a decode-boundary receipt surface
  - this supersedes the earlier same-day planning wording that described
    `sample.token` receipt support as future work; that wording should now be
    read as sampled-decode-only

### Track-2 decode-row normalization over live greedy receipts

- `config/numeric-stability-decode-row.schema.json`
  and `examples/numeric-stability-decode-row.sample.json`
  - added the normalized decode-row contract consumed by the decode-fragility
    ranking runner
  - the row shape freezes:
    - selected-token triples
    - decode config fields
    - receipt-derived decode-local metrics
    - upstream disagreement state
    - suffix replay evidence
- `config/numeric-stability-decode-row-enrichment.schema.json`
  and `examples/numeric-stability-decode-row-enrichment.sample.json`
  - added the explicit enrichment sidecar for prompt text, decode step index,
    semantic-priority overrides, within-policy stability, and short suffix
    replay evidence
  - this keeps track 2 executable against live greedy receipts even before the
    sampled decode receipt grows richer prompt/token metadata on its own
- `bench/runners/normalize_decode_fragility_rows.py`
  and `bench/tests/test_normalize_decode_fragility_rows.py`
  - added the receipt consumer that converts live `decode.sample_token`
    receipts into rankable decode rows
  - it now preserves runtime-emitted decode-boundary metrics when present and
    falls back to local derivation only when needed:
    - top-1 margin
    - `top-k` boundary gap
    - `top-p` boundary gap
    - CDF proximity to the draw when present
    - selected-token change
    - live-selected-token match booleans
    - default `investigate` posture when suffix replay or within-policy
      stability evidence is still missing
- `bench/runners/rank_decode_fragility_states.py`
  and `bench/tests/test_rank_decode_fragility_states.py`
  - ranking now distinguishes:
    - hard reject reasons such as meaningless tokens or no selected-token
      change
    - `investigate` reasons such as missing suffix replay or incomplete
      within-policy stability evidence

### Track-1 decode-boundary receipts for greedy ordinary execution

- `runtime/zig/src/numeric_stability_runtime.zig`
  and `runtime/zig/src/numeric_stability_runtime_decode.zig`
  and `runtime/zig/src/numeric_stability_runtime_plan.zig`
  - Doe now persists a real `decode.sample_token` numeric-stability receipt
    during ordinary execution when the shipped greedy `sample.wgsl` path
    consumes an auto-detected `decode.final_logits` producer
  - the runtime stores the upstream `decode.final_logits` receipt state, then
    emits a decode-boundary row that carries:
    - full-vocabulary greedy coverage
    - the live selected token from the executed sample buffer
    - whether the live token matches the committed route selection
    - exact greedy replay metrics for `fast`, `stable`, and `reference`
    - whether the selected token changed across replayed policies
    - upstream receipt links back to `decode.final_logits`
  - the current live decode-boundary lane is greedy-only:
    `temperature`, `topK`, `topP`, `rngSeed`, and `rngDraw` are reserved and
    remain `null` until sampled decode support lands
- `config/numeric-stability-policy.json`
  - added the live auto-detect profile:
    `numeric-stability-auto-detect/decode-final-logits-v1`
  - ordinary execution can now bind a `decode.final_logits` producer into the
    downstream `decode.sample_token` receipt path without explicit
    command-local numeric-stability annotations
- `config/doe-numeric-stability-receipt.schema.json`
  and `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - numeric-stability receipts now have an optional `decodeBoundary` contract
    covering:
    - decode mode
    - logits coverage
    - decode config placeholders
    - surviving token set
    - live selected token
    - upstream receipt links
- `examples/numeric-stability-decode-greedy.commands.json`
  and `examples/doe-numeric-stability-receipt.decode-sample.sample.json`
  - add a checked-in ordinary-execution command stream and sample receipt for
    the new greedy decode-boundary lane
- `packages/doe-gpu/README.md`
  and `runtime/zig/README.md`
  and `docs/status.md`
  - docs now distinguish the live greedy decode-boundary receipt from the
    still-future full sampled decode contract

### Track-2 decode-fragility mining and promotion planning

- `config/numeric-stability-decode-fragility-plan.json`
  and `config/numeric-stability-decode-fragility-plan.schema.json`
  - added the planning contract for ranking decode-boundary fragility once the
    runtime emits real `sample.token` receipts
  - the plan now freezes:
    - the normalized mining input contract
    - replay predicates for greedy and sampling cases
    - weighted fragility signals
    - semantic-priority classes
    - strict promotion rules for `promotable`, `investigate`, and `reject`
- `config/numeric-stability-decode-fragility-report.schema.json`
  and `examples/numeric-stability-decode-fragility-report.sample.json`
  - add a schema-backed output contract for ranked decode-fragility reports
- `bench/runners/rank_decode_fragility_states.py`
  and `docs/numeric-stability-decode-fragility-plan.md`
  - add the track-2 ranking runner and its design memo
  - this runner is intentionally downstream of the receipt work:
    it ranks normalized decode-boundary rows, but it does not invent a new
    runtime receipt shape or claim that the full decode-boundary receipt is
    already live

### Track-3 decode validation and backend-promotion planning

- `config/numeric-stability-decode-validation-plan.json`
  and `config/numeric-stability-decode-validation-plan.schema.json`
  - added the planning contract for the decode-boundary semantics and backend
    validation lane
  - the plan now declares:
    - semantically sharp scenario buckets
    - meaningful-token classes
    - junk-token rejection rules
    - within-policy stability requirements
    - short suffix replay consequence requirements
    - Metal-first and Vulkan-second promotion stages
    - minimum decode-boundary demo set requirements
- `docs/numeric-stability-decode-validation-plan.md`
  - added the human-facing track-3 memo describing:
    - what a meaningful decode flip is
    - what should be rejected as junk
    - how suffix consequence should be judged
    - how cross-backend promotion should work
- Behavioral note:
  - these are planning-only surfaces
  - they do not add a live `sample.token` runtime receipt yet
  - they exist to give Track 1 and Track 2 a stable target for promotion and
    demo quality

### Ordinary-execution execution profiles and next-operator ranking

- `config/numeric-stability-policy.json`
  and `config/numeric-stability-policy.schema.json`
  - schema version is now `3`
  - the numeric-stability registry now declares ordinary-execution defaults
    explicitly instead of leaving them spread across helper code:
    - `defaultExecutionProfileId`
    - `executionProfiles`
  - added three named ordinary-execution profiles:
    - `numeric-stability/default-ordinary-execution-v1`
    - `numeric-stability/cautious-ordinary-execution-v1`
    - `numeric-stability/observe-only-ordinary-execution-v1`
  - added the observe-only routing policy:
    `numeric-stability/accept-fast-on-selected-token-disagreement-v1`
- `runtime/zig/src/numeric_stability_policy.zig`
  and `runtime/zig/src/numeric_stability_runtime.zig`
  and `runtime/zig/src/numeric_stability_runtime_plan.zig`
  and `runtime/zig/src/trace_numeric_stability.zig`
  and `runtime/zig/src/main.zig`
  and `runtime/zig/src/main_usage.zig`
  - ordinary execution now resolves a named execution profile from the shared
    registry and applies it to auto-detected operator families
  - explicit command-local annotations remain authoritative when present; the
    execution-profile layer governs the ordinary auto-detected path
  - trace-meta numeric-stability summaries now record:
    - `executionProfileId`
  - the native CLI now accepts:
    - `--numeric-stability-execution-profile`
- `config/trace-meta.schema.json`
  and `examples/doe-numeric-stability-trace-meta.sample.json`
  - the numeric-stability summary contract now includes
    `executionProfileId`
- `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  and `packages/doe-gpu/src/index.d.ts`
  and `packages/doe-gpu/src/vendor/doe-numeric-stability-policy.js`
  - ordinary package execution now accepts:
    - `executionProfileId`
  - the selected execution profile is now returned in the ordinary-execution
    result envelope
  - package policy mirrors now expose the ordinary-execution profile IDs for
    docs and sync tests
- `config/numeric-stability-auto-detection-plan.json`
  and `config/numeric-stability-operator-expansion-plan.json`
  and `docs/numeric-stability-auto-detection-plan.md`
  - the planning surfaces now match current repo truth:
    the live ordinary-execution trio is `matmul.logits`,
    `rmsnorm.output`, and `attention.output`
  - the next ranked operator opportunities now start with:
    - `softmax.denominator`
    - `layernorm.output`
    - followed by `mlp.output`, `residual.add`, and `task-head.score`

### Auto-detected ordinary execution and package ordinary-execution exposure for numeric stability

- `config/numeric-stability-policy.json`
  and `config/numeric-stability-policy.schema.json`
  - ordinary native numeric stability no longer depends on command-local
    `numericStability` annotations for the primary path
  - added config-backed auto-detect profiles for:
    - `matmul.logits`
    - `rmsnorm.output`
    - `attention.output`
  - route-decision metadata now also declares executable route effects:
    - `committedResultMode`
    - `downstreamAction`
- `runtime/zig/src/numeric_stability_policy.zig`
  and `runtime/zig/src/numeric_stability_runtime.zig`
  and `runtime/zig/src/numeric_stability_runtime_plan.zig`
  and `runtime/zig/src/numeric_stability_runtime_eval.zig`
  - native ordinary execution now resolves numeric-stability handling from the
    shared auto-detect profiles at runtime instead of requiring explicit
    annotations on the command stream
  - `prefer-stable` now rewrites the committed result buffer for supported
    operator families
  - `abstain` now stops downstream command execution in the current native
    ordinary-execution lane
  - receipts now bind runtime execution identity to:
    - executed kernel identity
    - layout fingerprint
    - adapter/driver profile
    - compiled plan hash
- `config/doe-numeric-stability-receipt.schema.json`
  and `config/trace-meta.schema.json`
  - numeric-stability receipts now require execution identity and route-effect
    fields:
    - `executionIdentity`
    - `committedResultMode`
    - `downstreamAction`
    - `effectApplied`
  - trace-meta numeric-stability summaries now track:
    - `annotationCount`
    - `autoDetectCount`
    - `committedStableRewriteCount`
    - `downstreamStopCount`
- `bench/runners/exercise_in_path_numeric_stability.py`
  and `bench/tests/test_exercise_in_path_numeric_stability.py`
  - the in-path exercise runner now builds ordinary command streams with
    semantic metadata only; the runtime auto-detect profile is responsible for
    numeric-stability capture and routing
- `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  and `packages/doe-gpu/src/index.d.ts`
  - `createDoeRuntime()` now exposes:
    - `runOrdinaryExecution(...)`
    - `runNumericStabilityOrdinaryExecution(...)`
  - `gpu` now also exposes:
    - `ordinaryExecution(...)`
  - `gpu.numericStability.ordinaryExecution(...)` and
    `runNumericStabilityOrdinaryExecution(...)` remain supported as
    compatibility aliases
  - ordinary package execution can now consume the same in-path receipt
    contract without requiring callers to enter through a special
    `numericStability` namespace first

### A-track planning surfaces for semantic envelopes

- `config/numeric-stability-semantic-envelope.schema.json`
  and `examples/numeric-stability-semantic-envelope.sample.json`
  - added a canonical semantic-envelope artifact proposal for numeric
    stability cases
  - the artifact records:
    - source case references
    - semantic classes
    - evaluated numeric and decode views
    - reachable answers
    - envelope status:
      `singleton`, `split`, `outsider-dominated`
    - envelope metrics
- `config/numeric-stability-semantic-envelope-plan.json`
  and `config/numeric-stability-semantic-envelope-plan.schema.json`
  - added a schema-backed A-track plan covering:
    - legal combination families
    - non-combinatorial semantic-collapse algorithms
    - evaluation metrics
    - ranked experiments
  - ranked experiments now carry explicit source references with evidence
    stages:
    - `runtime-exercised`
    - `promoted`
    - `corpus-only`
- `docs/numeric-stability-semantic-envelope-plan.md`
  - added the A-track memo describing the semantic-envelope object,
    algorithms, metrics, ranked experiments, and novelty bar
- Behavioral note:
  - these surfaces are planning-only and do not change current live runtime
    behavior
  - the current live route taxonomy remains unchanged:
    `accept-fast`, `prefer-stable`, `abstain`

### B-track planning surfaces for numeric stability

- `config/numeric-stability-auto-detection-plan.json`
  and `config/numeric-stability-auto-detection-plan.schema.json`
  - added a schema-backed planning surface for the automatic fragility
    detection path from annotation-gated ordinary execution to auto-detected
    rerun
  - current planning-only signal set includes:
    - bounded margin
    - reference surprisal
    - outsider lead
    - fast/stable disagreement
    - first divergence
    - adjacent decode persistence
    - device/kernel identity
  - added planning-only bounded rerun budgets and suffix-replay escalation
    rules
- `config/numeric-stability-operator-expansion-plan.json`
  and `config/numeric-stability-operator-expansion-plan.schema.json`
  - added a schema-backed ranked operator-family expansion plan
  - current planning order is:
    - `rmsnorm.output`
    - `attention.output`
    - `softmax.denominator`
    - `layernorm.output`
- `docs/numeric-stability-auto-detection-plan.md`
  - added the runtime-first B-track memo covering:
    - automatic detection path
    - operator-family ranking
    - bounded capture and rerun design
    - checkpoint/suffix replay strategy
    - annotation-gated -> auto-detected migration
- Behavioral note:
  - these surfaces are planning-only and do not change current live runtime
    behavior
  - current live route taxonomy remains unchanged:
    `accept-fast`, `prefer-stable`, `abstain`

### Numeric-stability receipt provenance and in-path exercise hardening

- `runtime/zig/src/numeric_stability_runtime.zig`
  and `runtime/zig/src/main.zig`
  - native ordinary-execution numeric-stability now requires `--trace-meta`
    for annotated runs so the persisted receipt sidecar and the persisted
    trace-meta summary cannot drift apart
  - the in-path receipt no longer trusts annotation-supplied fast/stable
    policy IDs blindly:
    Doe now validates them against the executed `kernel_dispatch` contract
    before writing the live receipt
- `bench/runners/exercise_in_path_numeric_stability.py`
  and `bench/runners/exercise_runtime_numeric_stability.py`
  - in-path promotion now stages promoted-signature and catalog updates in
    temporary files and applies them only after the full run succeeds
  - JSON writes for the shared runtime-exercise helpers now use atomic
    file replacement instead of direct in-place writes

### Native ordinary-execution numeric stability for `matmul.logits`

- `config/numeric-stability-command-annotation.schema.json`
  and `examples/numeric-stability-command-annotation.sample.json`
  - added the schema-backed command-stream annotation for in-path
    numeric-stability evaluation during ordinary `kernel_dispatch` execution
  - the annotation records:
    - operator family and trigger/routing policy IDs
    - operand capture locations for hidden state, logits, and bounded row
      weights
    - candidate token metadata for the bounded slice
- `config/in-path-numeric-stability-exercise.json`
  and `config/in-path-numeric-stability-exercise.schema.json`
  and `bench/runners/exercise_in_path_numeric_stability.py`
  - added the config-backed native exercise lane for ordinary execution
  - the runner emits real command streams, trace artifacts, per-run receipts,
    and a manifest under `bench/out/apple-metal-in-path-numeric-stability/*`
  - the runner also updates checked-in promoted signatures and the promoted
    fragility catalog from native ordinary execution receipts instead of the
    earlier explicit bounded-slice service path
- `runtime/zig/src/numeric_stability_annotation.zig`
  and `runtime/zig/src/numeric_stability_runtime.zig`
  and `runtime/zig/src/command_json_raw.zig`
  and `runtime/zig/src/command_stream.zig`
  and `runtime/zig/src/main.zig`
  and `runtime/zig/src/main_usage.zig`
  - Doe now has a native ordinary-execution numeric-stability path for one
    operator family:
    annotated `matmul.logits` `kernel_dispatch`
  - the runtime:
    - parses `numericStability` command annotations
    - captures live ordinary-execution operands and fast logits from the real
      dispatch
    - computes stable and bounded exact-reference comparisons locally in Zig
    - validates the declared fast/stable policy IDs against the executed
      kernel contract before emitting the receipt
    - emits first-divergence receipts and trace-meta summary blocks on the
      same execution run
- Behavioral difference versus the prior surface:
  Doe numeric stability is no longer only an explicit bounded-slice runtime
  service for live route outcomes.
  Selected native `matmul.logits` cases can now reach
  `contractStage: runtime-exercised` through ordinary Doe execution, while the
  explicit bounded-slice service remains the package-visible helper surface.

### Live runtime numeric-stability exercise and abstain route

- `config/numeric-stability-policy.json`
  - registry version is now `2026-03-29-route-taxonomy-v2`
  - added an explicit abstaining routing policy:
    `numeric-stability/abstain-on-selected-token-disagreement-v1`
  - current route vocabulary remains unchanged:
    `accept-fast`, `prefer-stable`, `abstain`
- `config/runtime-numeric-stability-exercise.json`
  and `config/runtime-numeric-stability-exercise.schema.json`
  - added the config-backed runtime exercise plan for the live Zig
    numeric-stability service
  - the plan now chooses:
    - strict prompt cases that should stay `prefer-stable`
    - broad prompt cases that should `abstain`
    - a live runtime `accept-fast` control
- `bench/runners/exercise_runtime_numeric_stability.py`
  - added the runtime exercise runner that replays promoted prompt/control
    cases through `doe_numeric_stability`
  - the runner writes:
    - explicit request/result/receipt/trace-meta artifacts
    - a bounded-overhead manifest under
      `bench/out/apple-metal-runtime-numeric-stability/*`
  - the runner also updates checked-in fragility signatures and the promoted
    catalog from `promoted` to `runtime-exercised` when a live route outcome
    exists
- `config/promoted-fragility-catalog.json`
  and `config/promoted-fragility-catalog.schema.json`
  and `config/fragility-signatures/promoted/*.json`
  - promoted catalog entries can now record `routeOutcomeDecision`
  - the catalog summary now records `countsByRouteOutcome`
  - selected signatures now carry live `routeOutcome` data and
    `contractStage: runtime-exercised`
- `packages/doe-gpu/test/smoke/test-smoke-load.js`
  - the public package smoke path now exercises all three live route classes
    through the real helper surface:
    `prefer-stable`, `accept-fast`, and `abstain`

### Runtime numeric-stability service v1

- `config/doe-numeric-stability-receipt.schema.json`
  and `config/numeric-stability-service.schema.json`
  - added the first schema-backed runtime contracts for Doe numeric stability:
    - the explicit `doe_numeric_stability` service request/result envelope
    - the live per-event numeric-stability receipt
- `examples/numeric-stability-service.request.sample.json`
  and `examples/numeric-stability-service.result.sample.json`
  and `examples/doe-numeric-stability-receipt.sample.json`
  and `examples/doe-numeric-stability-trace-meta.sample.json`
  - added schema-valid samples for:
    - explicit module-runner request
    - service result
    - receipt row
    - trace-meta summary block
- `config/trace-meta.schema.json`
  - trace-meta now accepts an optional `numericStability` summary block with:
    - policy registry provenance
    - receipt path/count
    - route decision counts
    - first-divergence-present count
- `runtime/zig/src/numeric_stability_policy.zig`
  and `runtime/zig/src/trace_numeric_stability.zig`
  and `runtime/zig/src/full/modules/services/numeric_stability.zig`
  and `runtime/zig/src/module_runner.zig`
  - Doe now has a real Zig-owned numeric-stability path:
    - policy loading from the shared registry
    - explicit `matmul_logits_slice` service execution
    - per-event receipt emission
    - optional trace-meta summary emission
    - governed route evaluation using the shared trigger/routing policy
    - route-taxonomy and route-selection proof metadata copied from the shared
      registry into live receipts
- `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  and `packages/doe-gpu/src/vendor/doe-numeric-stability-policy.js`
  - the public package surface now exposes the first explicit numeric-stability
    helper:
    `gpu.numericStability.matmulLogitsSlice(...)`
  - `createDoeRuntime()` now also exposes:
    - `runModule(...)`
    - `runNumericStabilityMatmulLogitsSlice(...)`
- Behavioral difference versus the prior surface:
  Doe numeric stability is no longer only a bench/probe concept.
  The repo now has a live runtime/package bounded-slice v1 that can evaluate a
  declared `matmul.logits` slice under fast/stable/reference policies and emit
  a receipted route decision from the real Zig module-runner path.
  This explicit service still exists and remains the current package-facing
  helper surface even though native ordinary-execution rerun now also exists
  for annotated `matmul.logits` commands.

### Numeric-stability promotion contract hardening

- `config/numeric-stability-policy.json`
  and `config/numeric-stability-policy.schema.json`
  - schema version is now `2`.
  - the registry now carries:
    - `routeTaxonomyVersion`
    - `routeDecisionMetadata`
  - current route truth is still unchanged:
    `accept-fast`, `prefer-stable`, `abstain`
  - the new route-decision metadata records the current selection semantics and
    proof links for each supported route.
  - runtime/package receipts now copy:
    - `routeTaxonomyVersion`
    - route `selectionMode`
    - route `selectionProofLinks`
- `config/fragility-promotion-policy.json`
  and `config/fragility-promotion-policy.schema.json`
  - added the machine-readable promotion ladder for numeric fragility:
    discovery -> promoted -> runtime-candidate -> runtime-exercised
  - added explicit blocking versus advisory evidence for:
    - each contract stage
    - each corpus class
    - the novelty bar
- `config/promoted-fragility-catalog.json`
  and `config/promoted-fragility-catalog.schema.json`
  and `config/fragility-signatures/promoted/*.json`
  - added the checked-in promoted fragility catalog plus normalized promoted
    signatures.
  - promoted signatures intentionally keep `routeOutcome` unset until a real
    runtime-exercised receipt exists.
- `bench/runners/promote_numeric_fragility_signatures.py`
  - added the repo-level promotion tool that lifts the latest exported numeric
    fragility corpus into the checked-in promoted catalog surfaces.

### Fragility-signature contract planning

- `config/fragility-signature.schema.json`
  - added a canonical schema for normalized numeric-fragility cases.
  - the schema is discovery/promotion planning only; it does not change Doe
    runtime behavior.
  - it defines the stable case fields needed to graduate evidence from:
    - discovery
    - promoted
    - runtime-candidate
    - runtime-exercised
- `docs/numeric-stability-contract-roadmap.md`
  - added the planning contract for:
    - fragility corpus formalization
    - route taxonomy roadmap
    - proof roadmap
    - artifact graduation from discovery to runtime contract
  - current route truth remains unchanged:
    `accept-fast`, `prefer-stable`, `abstain`
  - `review-required` remains roadmap-only until a later explicit migration.

### Numeric-fragility corpus export

- `bench/runners/export_numeric_fragility_corpus.py`
  - added a repo-level export that normalizes the current Apple Metal
    numeric-stability evidence into one JSONL corpus plus a manifest.
  - the exported prompt rows now record:
    - bounded-answer pair probability
    - bounded-answer per-token surprisal
    - bounded-answer entropy and margin
    - global top-candidate context and outsider lead
    - explicit status when global reference-token surprisal is unavailable
  - the exported route contract is now split explicitly:
    - `routeExpectation` is hunt-derived and can remain hypothetical
    - `routeDecision` is reserved for realized rerun or policy outcomes
  - promoted prompt rows now use the promoted hunt report as
    `sourceArtifactPath`, with the earlier representative hunt artifact kept as
    `sourceSearchArtifactPath`
  - this is a bench/reporting contract only; it does not change Doe runtime
    behavior.

### Real LM-head slice hunt and ShaderF16 promotion path

- `runtime/zig/src/webgpu_ffi.zig`
  and `runtime/zig/src/dawn_plan_executor_support.zig`
  and `runtime/zig/src/dawn_plan_executor.zig`
  - Dawn-backed runtime lanes now explicitly request `ShaderF16` when the
    adapter advertises it.
  - this unblocks live promotion of `enable f16;` numeric-stability kernels on
    Apple Metal instead of leaving them stuck as search-only counterfactuals.
- `bench/executors/harvest-doppler-browser-logits.js`
  - the real browser harvest path can now optionally capture the stable real
    last-token embedding for prefill, not only the logits/topK receipt.
- `bench/runners/run_real_lm_head_slice_hunt.py`
  and `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.red-go-stop-answer.json`
  and `bench/fixtures/determinism/apple-metal-real-lm-head-slice-hunt.gemma270m.red-go-stop-answer.json`
  - added the first real LM-head slice promotion lane:
    harvest a real prompt embedding, read the real output rows from the model
    artifact, evaluate alternate accumulation policies, and promote the best
    case into reduction-order and selective-rerun receipts.
- Behavioral difference versus the prior surface:
  Doe can now promote a real explicit-choice prompt into a full numeric-
  governance receipt chain on Apple Metal:
  for the bounded `{ go, stop }` traffic-light prompt, the real exact-reference
  and f32 policies stay on ` go`, `f16accum` flips to ` stop`, and the
  selective rerun policy correctly prefers the stable serial path on both Doe
  and Dawn.

### Numeric-stability routing policy and selective stable-rerun probe

- `config/numeric-stability-policy.json`
  and `config/numeric-stability-policy.schema.json`
  - added the first versioned numeric-stability policy registry for the
    bench/runtime-governance lane.
  - the registry now also records:
    - `proofArtifactPath`
    - trigger-policy proof links
    - routing-policy proof links
  - the current registry defines:
    - one trigger policy:
      `numeric-instability/selected-token-disagreement-with-reference-improvement-v1`
    - one routing policy:
      `numeric-stability/prefer-stable-on-selected-token-disagreement-v1`
    - sensitive operator coverage for:
      `matmul.logits`, `attention.output`, and `rmsnorm.output`
  - these policies encode the current selective-correction rule:
    reroute onto the stable result only when a sensitive operator is the first
    divergence, the selected token changes, the stable rerun matches the exact
    reference, and the fast path does not.
- `bench/runners/run_selective_stable_rerun_probe.py`
  and `bench/fixtures/determinism/apple-metal-selective-stable-rerun-logit-flip.json`
  - added the first receipted selective stable-rerun probe over the operator-
    level logit-flip lane.
  - the probe now also copies the proof-linked contract into the live report:
    `proofArtifactPath`, trigger proof links, and route proof links.
  - the probe does not yet make package/native execution rerun a real operator
    in place; it evaluates the governance decision over a source report and
    records the first divergence, trigger checks, and final route.
- `bench/fixtures/determinism/apple-metal-selective-stable-rerun-attention-slice.json`
  - added the first clean real-operator-family negative control for the
    numeric-stability lane:
    the attention-style slice now routes `accept-fast` because no first
    divergence or selected-token change is observed on the live Apple Metal
    path.
- `bench/inference-pipeline/kernels/rmsnorm_serial_f32.wgsl`
  and `bench/fixtures/determinism/rmsnorm-slice-tree.commands.json`
  and `bench/fixtures/determinism/rmsnorm-slice-serial.commands.json`
  and `bench/fixtures/determinism/apple-metal-rmsnorm-slice-logit-flip.json`
  and `bench/fixtures/determinism/apple-metal-selective-stable-rerun-rmsnorm-slice.json`
  - added the first real `rmsnorm`-family numeric cliff lane:
    the same operator family plus the same downstream 2-row logits projection
    now produce different selected tokens under reduction-tree vs strict-
    serial accumulation on Apple Metal.
  - the paired rerun receipt shows the numeric-governance lane is not biased
    toward "stable" by default:
    `rmsnorm.output` is treated as a sensitive operator, the token changes,
    but the exact-reference path stays on tree/fast so the route correctly
    remains `accept-fast`.
- Behavioral difference versus the prior surface:
  Doe now has a versioned config-backed way to express the first
  "numeric instability detected -> prefer stable rerun" rule, now with
  proof-linked trigger/route contracts and an explicit negative-control lane,
  even though the actual live rerun still exists today as a bench probe rather
  than an ordinary runtime/package execution path.

## 2026-03-28

### Package-path determinism receipts and natural safe/unsafe supporting case

- `bench/executors/determinism-trace-meta.js`
  and `bench/executors/node-webgpu/determinism.js`
  and `bench/executors/node-webgpu/plan.js`
  and `bench/executors/node-webgpu/executor.js`
  and `bench/runners/run_package_determinism_receipt.py`
  - the ordinary Node/package executor now preserves semantic capture metadata,
    performs deterministic logits/token readbacks on the package lane, and can
    emit a schema-valid `trace_meta.determinism` block from those real captured
    bytes instead of helper-only receipts.
- `config/determinism-answer-set-registry.json`
  - added a tokenizer-aware `safety.safe_unsafe` bounded answer set alongside
    the existing `safety.not_safe` lane.
- `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.policy-breadth.json`
  and `bench/fixtures/determinism/apple-metal-sample-only-tie-break.pool-safe-unsafe.gemma270m.json`
  - new Apple Metal scout/support fixtures for the natural prompt
    `Leaving a toddler alone near a pool is safe or unsafe. It is`.
- Behavioral difference versus the prior surface:
  Doe can now emit real package-lane receipts for a fresh natural supporting
  bounded-choice case on Apple Metal:
  `stable-token` stays on the raw scalar greedy token, while `stable-choice`
  and `reviewed-choice` resolve the declared `{safe, unsafe}` ambiguity under
  the fixed `candidate-margin-band-v1` trigger with proof-linked receipts.

### Determinism policy registry and trace-meta alignment

- `config/determinism-policy.json`
  and `config/determinism-policy.schema.json`
  - Doe now has a versioned determinism policy registry for the three explicit
    post-logit boundaries:
    `stable-token`, `stable-choice`, and `reviewed-choice`.
  - the registry is now the source of truth for:
    policy IDs, base-rule IDs, evaluator IDs, candidate-set provenance values,
    and proof-link sets.
- `packages/doe-gpu/src/vendor/doe-determinism-policy.js`
  - the public package helper surface now consumes a checked-in mirror of that
    registry instead of hardcoded determinism proof/policy constants embedded
    directly in `doe-namespace.js`.
- `packages/doe-gpu/src/vendor/doe-namespace.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - determinism receipts now include:
    - `policyRegistryPath`
    - `policyRegistryVersion`
    - versioned policy IDs for all three modes
  - `stable-token` receipts now also expose an explicit `policyId` and
    `selectedBy=stable-token-policy`, keeping the three boundary receipts more
    structurally parallel.
- `config/doe-determinism-receipt.schema.json`
  - the schema now requires the policy-registry provenance fields above, and
    `stable-token` receipts now require `policyId` and `selectedBy`.
- `config/trace-meta.schema.json`
  and `examples/doe-determinism-trace-meta.sample.json`
  - trace-meta now accepts an optional `determinism` block carrying the same
    policy-registry IDs, evaluator provenance, trigger provenance, and proof
    theorem summary as the public determinism receipts.
- `bench/executors/determinism-trace-meta.js`
  and `bench/executors/run-doe-stable-{token,choice}.js`
  and `bench/executors/run-doe-reviewed-choice.js`
  - the repo-only determinism executors now emit adjacent zero-row
    `trace_meta` artifacts in addition to the existing report JSON files.
- `runtime/zig/src/trace_determinism.zig`
  and `runtime/zig/src/trace.zig`
  - the native Zig trace-summary contract now carries the same optional
    `determinism` block, so future native/runtime callers can emit the same
    boundary metadata without inventing a second trace contract.
- Behavioral difference versus the prior surface:
  determinism receipts and trace summaries are now tied back to an explicit
  versioned policy registry instead of helper-local constants, and the
  package-side determinism surfaces now align with the shared trace-meta
  contract that native/runtime lanes will use.

### Determinism policy productization: reviewed-choice and proof-linked receipts

- `packages/doe-gpu/src/vendor/doe-namespace.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - Doe determinism helpers now expose a third sibling surface:
    `gpu.determinism.reviewedChoice(...)`.
  - `stable-token` and `stable-choice` receipts now also include `proofLinks`.
- `config/doe-determinism-receipt.schema.json`
  - the determinism receipt contract now has three discriminated modes:
    `stable-token`, `stable-choice`, and `reviewed-choice`.
  - the schema now requires proof-link metadata for all three modes.
- `examples/doe-determinism-receipt.reviewed-choice.sample.json`
  and `config/schema-targets.json`
  - schema validation now covers a reviewed-choice sample receipt in addition
    to the existing stable-token and stable-choice samples.
- `pipeline/lean/Doe/Core/DeterminismPolicy.lean`
  and `pipeline/lean/Doe/DeterminismPolicy.lean`
  - Doe now has an explicit Lean theorem pack for policy-layer determinism:
    stable-token tie-break semantics, ambiguity-trigger semantics,
    fixed-priority comparator semantics, and reviewed-choice decision
    acceptance.
- `pipeline/lean/Doe/Extract.lean`
  and `pipeline/lean/lean_build_common.sh`
  - those determinism-policy theorems are now part of the extracted proof
    artifact surface.
- `bench/executors/run-doe-reviewed-choice.js`
  - new repo-only executor for generating reviewed-choice receipts from
    persisted logits.
- `bench/runners/run_sample_only_tie_break_probe.py`
  and `bench/fixtures/determinism/apple-metal-sample-only-tie-break.seatbelt-not-safe.gemma270m.json`
  - the sample-only probe can now emit `raw`, `stable-token`,
    `stable-choice`, and `reviewed-choice` side by side from the same logits.
- Behavioral difference versus the prior surface:
  Doe now has an explicit audited reviewed-decision lane above the deterministic
  sampler and deterministic bounded-policy lanes, with proof-linked receipts
  that distinguish:
  raw sampler behavior,
  deterministic tie-break behavior,
  deterministic bounded-policy behavior,
  and explicit reviewed ambiguity resolution.

### Determinism contract hardening: answer-set registry, trigger policies, and refreshed Apple receipts

- `config/determinism-answer-set-registry.json`
  and `config/determinism-answer-set-registry.schema.json`
  - Doe now has a tokenizer-aware bounded answer-set registry for determinism
    search and promotion work.
- `config/determinism-trigger-policy.json`
  and `config/determinism-trigger-policy.schema.json`
  - ambiguity trigger policies are now versioned config, not ad hoc runner
    choices.
- `bench/runners/determinism_search_helpers.py`
  - shared determinism helpers now load answer-set registries and trigger
    policies, evaluate trigger contracts, and emit stage-specific stability
    requirements.
- `bench/runners/run_pair_agnostic_pair_miner.py`
  - pair mining now requires `registryModelId` and `triggerPolicyId`, emits
    explicit discovery provenance (`discoveryMode`, `promotionBucket`,
    `mutationDepth`, `mutationType`), and scores/promotes against the
    configured trigger policy rather than numerically-close pairs alone.
- `bench/runners/run_semantic_pair_mutation_search.py`
  - mutation-assisted promotions now stay in a separate provenance lane and
    write structured negative-control groups by domain / answer-set / outcome.
- `packages/doe-gpu/src/vendor/doe-namespace.js`
  and `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - `stable-choice` receipts now expose `triggerPolicyId`,
    `candidateSetId`, and `candidateSetSource` so the bounded-policy decision
    contract is auditable end to end.
- `config/doe-determinism-receipt.schema.json`
  - the stable-choice receipt schema now requires the policy-provenance fields
    above.
- Behavioral difference versus the prior surface:
  refreshed Apple scout receipts can now honestly produce zero natural
  promotions if no registry-gated candidate set survives the stability and
  usefulness filters, and the seatbelt stable-choice demo no longer implies a
  natural ambiguous source state when only the forced exact-tie case
  differentiates.

### Determinism search funnel: pair-agnostic mining and shortlist mutation search

- `bench/fixtures/determinism/apple-metal-pair-agnostic-mine.gemma270m.json`
  - Doe now has an explicit mining-policy contract for discovering replayable
    semantic answer pairs from broad scout receipts instead of relying only on
    hand-declared pair fixtures.
- `bench/runners/run_pair_agnostic_pair_miner.py`
  - new repo-only determinism search stage:
    broad `run_real_logit_hunt.py` scout receipts can now be mined into
    provenance-rich pair cases with canonical token IDs, source report links,
    usefulness scores, and logits artifact references.
- `bench/runners/run_semantic_pair_hunt.py`
  - the semantic pair runner now supports `--mined-report` in addition to the
    original explicit `--source-report` + pair fixture path, so mined cases can
    be promoted into decode-state receipts without rewriting them into a manual
    pair list first.
- `bench/fixtures/determinism/apple-metal-semantic-pair-mutation-search.gemma270m.json`
  and `bench/runners/run_semantic_pair_mutation_search.py`
  - Doe now has a shortlist-only mutation stage that reruns a cheap scout on
    prompt variants and emits both:
    - a mutation-search report with explicit negative controls
    - a companion mined-pair report containing only improved cases
- Behavioral difference versus the prior surface:
  the determinism workflow is now an explicit funnel:
  broad scout -> pair-agnostic mined pairs -> decode-state promotion ->
  mutation search -> promoted mined cases.
  Negative controls are now artifacts, not discarded failed experiments.

### Doe stable-choice helper surface and determinism receipt schema

- `packages/doe-gpu/src/vendor/doe-namespace.js`
  - the bound Doe helper namespace now also exposes
    `gpu.determinism.stableChoice(...)`.
- `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - the public package helper contract now includes bounded candidate sets,
    ambiguity triggers (`exact-max-tie` and `candidate-margin-band`), and the
    `stable-choice` receipt payload.
- `config/doe-determinism-receipt.schema.json`
  - Doe now has a schema-gated determinism receipt contract covering both
    `stable-token` and `stable-choice`.
- `config/schema-targets.json`
  - schema validation now covers sample `stable-token` and `stable-choice`
    receipts.
- `bench/fixtures/determinism/apple-metal-sample-only-tie-break.seatbelt-not-safe.gemma270m.json`
  - the seatbelt semantic probe fixture now declares an optional
    `doeStableChoice` section so policy-governed ambiguity resolution is part
    of the explicit fixture methodology.
- `bench/runners/run_sample_only_tie_break_probe.py`
  - the sample-only probe now emits optional Doe stable-choice receipts per
    case using `bench/executors/run-doe-stable-choice.js`.
- Behavioral difference versus the prior surface:
  Doe now separates:
  raw GPU sampling, scalar `stable-token`, and bounded-policy `stable-choice`.
  `stable-choice` can now deterministically override the scalar greedy token
  when a documented candidate-set ambiguity trigger fires, while leaving the
  scalar `stable-token` contract unchanged.

### Doe stable-token helper surface and sample-only tie-break fixture contract

- `packages/doe-gpu/src/vendor/doe-namespace.js`
  - the bound Doe helper namespace now exposes `gpu.determinism.stableToken(...)`.
- Behavioral difference versus the prior surface:
  Doe now has an explicit scalar greedy-token helper with a documented
  `lowest-index-among-max` tie-break rule and a receipt payload
  (`mode`, `comparator`, `tieBreakRule`, logits digest, top candidates, and
  tied-max indices) instead of relying only on the raw GPU `sample.wgsl`
  reduction semantics.

- `bench/fixtures/determinism/apple-metal-sample-only-tie-break.gemma270m.json`
  - the sample-only tie-break fixture now declares a `doeStableToken` section
    so the Doe stable-token receipt path is part of the explicit fixture
    methodology rather than an implicit runner default.
- `bench/runners/run_sample_only_tie_break_probe.py`
  - the sample-only probe now emits Doe stable-token receipts per case using
    `bench/executors/run-doe-stable-token.js`.
- Behavioral difference versus the prior surface:
  sample-only tie-break reports can now distinguish:
  raw Doe/Dawn parity on the shared GPU sample kernel from Doe's explicit
  scalar stable-token helper result on the same logits.

### Apple package unsupported receipts and Apple runtime bundle gating

- `config/trace-meta.schema.json`
  - package trace-meta receipts may now include optional `unsupportedCode` and
    `unsupportedDetail` fields when an executor emits an explicit unsupported
    classification instead of a generic execution error.
- `config/package-execution-policy.json`
  - Apple host-scoped package execution policy now retires the Node/Dawn
    Gemma64 and Gemma1B IR-backed package rows on `mac.lan` instead of letting
    the compare surface oscillate between provider crashes and partial receipts.
- `config/schema-targets.json`
  - schema validation now covers the package execution policy contract.
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.compare-dev.json`
  - the Apple compare-dev runtime lane now excludes the plan-backed Gemma270M
    rows and the two staged-upload rows whose Dawn-side timing is still
    implausible on this host, so the Apple runtime gate bundle stays on the
    intended governed runtime receipt set.
- `bench/native_compare_modules/runner.py` and
  `bench/native_compare_modules/workload_validation.py`
  - upload workloads now default to `queueSyncMode=deferred` unless a workload
    explicitly overrides that mode, matching the Apple Metal timing/sync policy
    gate contract.

## 2026-03-27

### Apple package CLI direct execution and drop-in Apple gate fixes

- `bench/drop-in/dropin_symbol_gate.py` now uses macOS-appropriate `nm` modes
  for `.dylib` artifacts and normalizes underscore-prefixed exported symbols.
- Behavioral difference versus the prior surface:
  the drop-in symbol gate can now validate macOS dylibs instead of treating the
  host symbol-table format as a gate failure.

- `runtime/zig/src/doe_queue_submit_native.zig` now validates
  `wgpuQueueWriteBuffer` ranges before writing and delivers a validation error
  to the device error-scope stack when the write exceeds the buffer bounds.
- Behavioral difference versus the prior surface:
  the drop-in ABI path now reports the expected validation error for out-of-
  range queue writes instead of silently writing past the declared WebGPU range.

### Tint compilation reports now expose raw, startup-corrected, and warm Tint timings

- The Doe-vs-Tint compilation surfaces now keep raw Tint process-wall timings
  as the auditable source metric and also publish a derived startup-corrected
  view.
- The compiler compare can now also publish a real warm/in-process Tint view
  from Dawn's `tint_benchmark` target when the compare config provides:
  - `right.warmBinaryPath`
  - `tintBenchmarkInputsScriptPath`
- The correction method is explicit:
  subtract the Tint trivial-shader baseline `p50` from each raw Tint sample,
  then recompute `p50`/`p95`/`p99`.
- `bench/native_compare_modules/runner.py` adds the following fields to the
  right-side compilation result payload used by the compare harness for the
  raw/startup-corrected view:
  - `startupBaselineStatsMs`
  - `startupCorrectionMethod`
  - `startupCorrectedStatsMs`
- `bench/native-compare/compare_doe_vs_tint_compilation.py` now writes
  `schemaVersion: 3` records with:
  - raw Tint timings under `right`
  - startup-corrected Tint timings under `right.startupCorrected`
  - optional warm Tint timings under `right.warm`
  - raw deltas under `deltaPercent`
  - startup-corrected deltas under `startupCorrectedDeltaPercent`
  - warm deltas under `warmDeltaPercent`
- Added the first benchmark-corpus config for the real warm surface:
  - `bench/native-compare/compare_doe_vs_tint.benchmark-corpus.config.json`
- New optional config knobs for the warm surface:
  - `run.outStem`
  - `run.warmRepetitions`
  - `run.warmMinTime`
- Behavioral difference versus the prior surface:
  raw Tint timings are still published unchanged, startup-corrected timings are
  still a derived presentation layer, and the surface can now publish a real
  in-process Tint benchmark view instead of relying only on correction math.

### CTS subset command templates now accept repo-root placeholders

- `bench/tools/cts_baseline_generate.py` and `bench/runners/run_cts_subset.py`
  now render the following extra placeholders inside `commandTemplate`:
  - `repo_root`
  - `config_dir`
- `bench/fixtures/cts_subset.fawn-node.json` now uses the repo-root placeholder
  to pass an absolute provider path to the vendored CTS runner:
  `cts/fawn-node-gpu-provider.js`
- Behavioral difference versus the prior surface:
  the preferred CTS subset config no longer depends on a fragile relative
  require path inside the vendored CTS loader.

### Canonical compare taxonomy and generated expansion artifact

- Added a canonical compare-axis contract:
  - `config/compare-taxonomy.json`
  - `config/compare-taxonomy.schema.json`
- Added a generated expansion artifact plus row schema:
  - `config/generated/compare-taxonomy-expanded.jsonl`
  - `config/compare-taxonomy-expanded-row.schema.json`
- The taxonomy now defines the shared axis language for:
  - `platformLane`
  - `comparisonBoundary`
  - `runtimeHost`
  - `comparisonView`
  - `temperature`
  - `targetKind`
- Structural families and expanded rows now also carry:
  - `providerSet`
  - `providers`
- `providerPair` remains in expanded rows as a compatibility alias for older
  pair-shaped consumers.
- The generated expansion annotates the naive cartesian product with:
  - type-correct structural membership
  - theoretical concrete target ids
  - current promoted compare reachability
  - promoted compare profile ids
- `bench/tools/generate_compare_taxonomy.py` is the canonical generator and
  verify tool for the expansion artifact.
- Root `README.md`, `bench/README.md`, and `docs/benchmark-taxonomy.md` now
  link to `docs/compare-taxonomy.md` so the compare vocabulary is documented in
  one place instead of being inferred from several overlapping configs.

### Bun package rows in the IR-backed compare stack

- Added Bun package executor ids to the native-compare registry:
  - `doe_bun_package`
  - `bun_webgpu_package`
  - `doe_bun_package_prepared`
  - `bun_webgpu_package_prepared`
- Added Bun cold and prepared-session Gemma package configs alongside the
  existing Node package configs:
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.bun-package.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.bun-package.warm.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.bun-package.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.bun-package.warm.ir.json`
- `config/promoted-compare-catalog.json` and
  `config/promoted-compare-catalog.schema.json` now include an explicit
  `boundary`, `runtimeHost`, `temperature`, `comparisonView`, `providerSet`,
  and `providers` contract alongside the legacy `surface` / `mode` /
  `packageRuntime` aliases used by older pair runners.
- `schemaVersion` is now `3`.
- `bench/run_compare.py` keeps Node as the default package runtime for backward
  compatibility, and Bun rows are selected explicitly with
  `--package-runtime bun`.

### Node package failure containment and custom compare-catalog resolution

- `bench/executors/run-node-webgpu-plan.js` supervisor fallback now emits
  terminal trace artifacts even when the plan JSON cannot be parsed or
  normalized.
- Prepared-session unsupported/error artifacts from
  `bench/executors/node-webgpu/executor.js` now zero pre-boundary host totals
  consistently with the warm package boundary.
- `bench/run_compare.py` now resolves relative `configPath` values against the
  selected `--catalog` location for custom catalogs, while the default repo
  catalog continues to resolve against repo root.

### Promoted compare front-door catalog

- Added `config/promoted-compare-catalog.json` and
  `config/promoted-compare-catalog.schema.json` as the config-backed registry
  for promoted Doe-vs-Dawn compare surfaces.
- `schemaVersion` is now `2`.
- The catalog now maps the full front-door matrix onto existing
  `bench/native-compare/compare_dawn_vs_doe.config.*.json` files using explicit
  axes:
  - `backend`
  - `surface` = `native` | `direct` | `package`
  - `preset` for native command/delegate preset lanes
  - `workload` for direct and package workload rows
  - `mode` = `default` | `cold` | `warm`
- Native preset rows now cover the existing Metal, AMD Vulkan, and local D3D12
  compare presets without duplicating compare-runner logic.
- Direct/package rows remain config-backed wrappers over the existing Apple
  Metal direct-plan and Node package compare configs.
- `config/schema-targets.json` now validates the promoted compare catalog as a
  blocking schema target.

## 2026-03-26

### Node package submit-path trace-meta breakdown

- `config/trace-meta.schema.json` now accepts finer-grained package submit-path
  diagnostics inside `packageStepBreakdownNs`:
  - `submitCommandEncoderFinishTotalNs`
  - `submitQueueSubmitTotalNs`
  - `submitQueueWaitTotalNs`
  - `submitCommandPrepTotalNs`
  - `submitAddonCallTotalNs`
  - `submitAddonCommandReplayTotalNs`
  - `submitAddonQueueSubmitTotalNs`
  - `submitAddonFlushTotalNs`
  - `submitPostSubmitBookkeepingTotalNs`
  - `submitQueueFlushTotalNs`
  - `submitQueueFlushWaitCompletedTotalNs`
  - `submitQueueFlushDeferredCopyTotalNs`
  - `submitQueueFlushDeferredResolveTotalNs`
  - `submitQueueWaitBookkeepingTotalNs`
- The Node/Bun package executor still reports the same selected timing and
  workload-unit wall boundaries, but now splits the existing
  `executionSubmitWaitTotalNs` bucket into finish, submit, wait, and internal
  package-submit sub-costs so package submit-path tuning can target the
  retained boundary with explicit evidence.

### Node package-lane trace-meta boundary and setup diagnostics

- `config/trace-meta.schema.json` now accepts package-surface diagnostics for the
  Node WebGPU executor:
  - `workloadUnitWallSource`
  - `packagePreparedSession`
  - `packageSetupIncludedInSelectedTiming`
  - `packageSetupTotalNs`
  - `packageSetupBreakdownNs`
  - `packageStepBreakdownNs`
- The cold Node package lane keeps package setup inside selected timing, but now
  emits explicit package-setup and step-cost breakdowns in trace meta so the
  package boundary can be diagnosed without redefining the claim metric.
- The prepared-session Node package lane emits
  `workloadUnitWallSource=trace-meta-process-wall` and reports
  `processWallMs` from the executor’s internal prepared session, so
  workload-unit wall for that lane no longer includes fresh process startup and
  pre-timed package preparation.

### Prepared-session workload-unit wall boundary semantics

- `config/trace-meta.schema.json` now constrains `workloadUnitWallSource` to the
  explicit enum value `trace-meta-process-wall` instead of allowing arbitrary
  strings.
- Prepared-session Node package rows now keep the existing `host*TotalNs`
  invariant: those fields mean "outside selected timing but inside
  workload-unit wall". Pre-boundary setup costs are therefore zeroed for
  prepared-session rows instead of being reported through the existing
  host-overhead buckets.
- The compare runner now suppresses `cpu_time` for
  `workloadUnitWallSource=trace-meta-process-wall` rows unless the executor
  provides a matching inner-boundary CPU metric. The subprocess CPU sample
  remains available in the resource record, but it is no longer mixed into the
  warm prepared-session timing metric set.

### Trace-meta host-overhead totals for workload-unit wall diagnostics

- `config/trace-meta.schema.json` now accepts coarse sample-level host-overhead
  totals:
  - `hostInputReadTotalNs`
  - `hostInputParseTotalNs`
  - `hostWorkloadPrepareTotalNs`
  - `hostExecutorInitTotalNs`
  - `hostUploadPrewarmTotalNs`
  - `hostKernelPrewarmTotalNs`
  - `hostCommandOrchestrationTotalNs`
  - `hostArtifactFinalizeTotalNs`
- Doe direct runtime and the standalone Dawn plan executor now emit those totals
  in trace meta using once-per-sample phase timers around existing
  read/parse/init/prewarm/loop/finalize boundaries.
- Compare reports now synthesize
  `timingInterpretation.hostOverheadBreakdown` from those totals so
  workload-unit wall can be explained as:
  - selected timing
  - attributable coarse host overhead
  - remaining unattributed wall gap
- This is a diagnostic attribution layer only; it does not change comparability
  or claimability policy.

### Fine-grained artifact-finalize trace-meta totals

- `config/trace-meta.schema.json` now also accepts finer-grained artifact
  finalize diagnostics:
  - `hostArtifactTraceJsonlSerializeTotalNs`
  - `hostArtifactTraceJsonlWriteTotalNs`
  - `hostArtifactOperatorManifestFinalizeTotalNs`
- Doe direct-runtime trace meta can now distinguish JSONL serialization cost
  from JSONL file writeback and operator-manifest finalization, instead of
  reporting only one coarse `hostArtifactFinalizeTotalNs` bucket.
- This is a diagnostic contract only; it does not change timing scope,
  comparability, or claimability policy.

### Compare report workload-unit wall terminology

- `bench/native-compare/compare_dawn_vs_doe.py` now writes compare reports with
  `schemaVersion: 5`.
- The clearer external timing name is now:
  - per workload `timingInterpretation.workloadUnitWall`
  - optional top-level `overallWorkloadUnitWall`
- Legacy aliases remain during migration:
  - per workload `timingInterpretation.headlineProcessWall`
  - optional top-level `overallHeadlineProcessWall`
- Claimability metadata now reports:
  - `claimMetricField = timingInterpretation.workloadUnitWall.deltaPercent`
  - `claimMetricScope = workloadUnitWall`
- Behavioral difference versus the prior report surface:
  compare artifacts now distinguish the full timed workload-unit wall view from
  selected operation timing without implying that the metric is a generic
  end-user session-latency number. Warm-session timing remains a separate future
  benchmark scope rather than something inferred from workload-unit wall.

## 2026-03-24

### Workload origin taxonomy split

- Replaced the old binary inferred workload provenance model
  (`dawn_derived` / `doe_specific`) with explicit authored/generated origins:
  - `dawn_benchmark`
  - `dawn_autodiscovered`
  - `doe_contract_with_dawn_mapping`
  - `doe_specific`
- `bench/generate_backend_workloads.py` now infers `dawn_autodiscovered` from
  `dawnFilter="@autodiscover"` and `dawn_benchmark` from non-autodiscovered
  Dawn filter mappings, while allowing explicit authored overrides for
  Doe-authored comparable contracts that still run against Dawn.
- The canonical backend workload catalog now explicitly marks the copy/dispatch
  contract rows that use Dawn only as a delegate host process as
  `workloadOrigin="doe_contract_with_dawn_mapping"`.
- Generated backend workload files now carry per-row `workloadOrigin` so
  provenance can be queried without reconstructing catalog inference.

### Tooling surface contract and npm CLI boundary

- Added a schema-backed tooling surface manifest:
  - `config/tool-surfaces.schema.json`
  - `config/tool-surfaces.json`
- `config/schema-targets.json` now validates the tooling surface contract as a
  blocking schema target.
- `packages/doe-gpu/package.json` no longer publishes `doe-gpu-bench` or
  `doe-gpu-compare` as npm CLI binaries, and the npm tarball no longer includes
  the old `bin/` or `scripts/` package-side operator files.
- Public package docs now treat compare/release workflows as repo-only operator
  tooling documented in `docs/internal-tooling.md`, not as npm-shipped product
  CLIs.

## 2026-03-22

### doe-gpu semantic operator bundle contract

- `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js` exposes
  `writeSemanticOperatorBundle(options)`, and `createDoeRuntime()` forwards the
  same helper on the package/runtime tooling surface.
- New schema: `config/semantic-operator-bundle.schema.json`
- New sample payload: `examples/semantic-operator-bundle.sample.json`
- The bundle is a package-side artifact contract for Doe-native diagnose flows:
  it links a semantic operator timeline to provider identity, report anchor,
  divergence summary, and lightweight run summary metadata.
- This contract is distinct from the lower-level Doe-native runtime artifacts in
  `operator-execution-record.schema.json` and `operator-repro-bundle.schema.json`.
  The package bundle is the join-layer that higher-level tools can attach to a
  user-facing diagnose result.

### Semantic operator trace rows, operator manifests, and structural repro bundles

- `config/trace.schema.json` now accepts optional semantic operator fields on
  runtime trace rows:
  - `semanticOpId`
  - `semanticStage`
  - `semanticPhase`
  - `semanticTokenIndex`
  - `semanticLayerIndex`
  - `semanticExecutionPlanHash`
- `config/trace.schema.json` also now accepts the execution-side provenance
  fields required to join a semantic operator to Doe runtime facts:
  - `executionBackendLane`
  - `executionSelectionPolicyHash`
  - `executionShaderArtifactManifestPath`
  - `executionShaderArtifactManifestHash`
  - `executionAdapterOrdinal`
  - `executionQueueFamilyIndex`
  - `executionPresentCapable`
- `config/trace-meta.schema.json` now records semantic/operator artifact summary
  state:
  - `semanticTracingEnabled`
  - `semanticOpRowCount`
  - `semanticCaptureCount`
  - `semanticReproCount`
  - `operatorRecordManifestPath`
  - `operatorRecordManifestHash`
- New artifact schemas define the Doe-native operator debugging contracts:
  - `config/operator-execution-record.schema.json`
  - `config/operator-repro-bundle.schema.json`
- `runtime/zig/src/main.zig` now accepts semantic and capture metadata in the
  command stream, emits semantic trace rows when present, writes a per-run
  operator manifest adjacent to the trace anchor (`<trace-meta-or-jsonl>.operators.json`),
  and emits one-command structural repro bundles
  (`.opNNNN.repro.commands.json` / `.opNNNN.repro.meta.json`).
- Buffer capture is Doe-native only. Vulkan and Metal support targeted
  `captureBufferHandle` / `captureOffset` / `captureSize` readback today;
  D3D12 and Dawn-delegate paths fail explicitly as `UnsupportedFeature`.

### Coverage ledger axis rename and generated surface views

- Renamed the canonical coverage ledgers to make their axes explicit:
  - `config/webgpu-core-coverage.json` ->
    `config/webgpu-command-coverage-core.json`
  - `config/webgpu-full-coverage.json` ->
    `config/webgpu-command-coverage-full.json`
  - `config/webgpu-spec-coverage.json` ->
    `config/webgpu-capability-inventory.json`
  - `config/webgpu-chromium-coverage.json` ->
    `config/webgpu-integration-chromium.json`
- Matching schema files were renamed in lockstep and `config/schema-targets.json`
  now validates the new canonical names.
- `bench/schema_gate.py` now accepts JSONL data targets directly, so
  `config/webgpu-spec-index.jsonl` is validated through the registry instead of
  pointing at the stale non-existent `.json` path.
- Added generated per-surface convenience reports under `config/generated/`:
  - `webgpu-surface-compute.json`
  - `webgpu-surface-headless.json`
  - `webgpu-surface-chromium.json`
- These generated surface reports are views only. The canonical source of truth
  remains axis-based: command coverage, capability inventory, spec index, and
  Chromium integration overlay stay separate.

### Upload path policy: allow fast_mapped under staged_copy_only

- `staged_copy_only` previously forced all uploads through the staged-copy
  path (host-visible src buffer, device-local dst buffer, vkCmdCopyBuffer,
  submit+fence wait). Dawn's Vulkan `WriteBuffer` detects host-visible+coherent
  destination buffers and performs a direct memcpy with zero GPU work.
- The `classify_upload_path` function in `vk_upload.zig` now allows the
  `fast_mapped` path (direct memcpy to a persistently-mapped host-visible
  buffer) even under `staged_copy_only`, matching Dawn's actual behavior.
- This eliminates the structural work asymmetry on `upload_write_buffer_1kb`
  that violated CLAUDE.md rules 7 (Dawn apples-to-apples), 10 (structural
  work equivalence), and 11 (timing-scope completeness).
- No schema version bump required: the `uploadPathPolicy` enum values are
  unchanged; only the runtime classification semantics are corrected.
- Config lane notes updated to reflect the corrected semantics.

## 2026-03-21

### External texture native implementation

- Metal and Vulkan external texture rows in `webgpu-spec-index.jsonl` promoted
  from `out_of_scope` to `implemented`: `GPUExternalTexture`,
  `GPUExternalTextureDescriptor` (source, colorSpace, label),
  `GPUExternalTextureBindingLayout`, `GPUBindGroupLayoutEntry.externalTexture`,
  `GPUDevice.importExternalTexture`.
- New runtime file: `doe_external_texture_native.zig` with `DoeExternalTexture`
  handle, ref-counted lifecycle, and C ABI descriptor parsing.
- WGSL `texture_external` type added to IR, sema, and all emitters (MSL, SPIR-V, HLSL).
- `textureSampleBaseClampToEdge` builtin recognized in sema and lowered across backends.
- Dropin proc table routes `wgpuDeviceCreateExternalTexture` to Doe via `resolveLocalProc`.

## 2026-03-20

### D3D12 spec index reconciliation pass

- Promoted the D3D12 render-pass attachment-extra rows that are now
  source-backed in the checked-in native execution path:
  `GPURenderPassColorAttachment.depthSlice`,
  `GPURenderPassColorAttachment.resolveTarget`,
  `GPURenderPassDepthStencilAttachment.depthReadOnly`, and
  `GPURenderPassDepthStencilAttachment.stencilReadOnly` now track as
  `implemented`.
- Ordered D3D12 queue submission now consumes render-pass attachment-view
  metadata instead of preserving those fields only on the native handle:
  `doe_queue_submit_native.zig` imports the D3D12 render-pass recorder, the
  recorder creates per-view RTV/DSV descriptors, applies read-only depth /
  stencil DSV flags, and emits MSAA resolves through
  `ResolveSubresource`.
- The D3D12 ledger currently stands at 520 `implemented`, 39 `partial`,
  264 `unreviewed`, 8 `blocked`, and 57 rows with no explicit D3D12 cell yet.
- The eight blocked D3D12 feature-publication rows remain explicit and
  intentional: `texture-compression-bc-sliced-3d`,
  `texture-compression-etc2`, `texture-compression-astc`,
  `texture-compression-astc-sliced-3d`, `float32-blendable`,
  `texture-formats-tier1`, `texture-formats-tier2`, and
  `texture-component-swizzle`. The current D3D12 caps / format code does not
  source-back those rows repo-locally, so they remain blocked rather than
  silently promoted.

### macOS package GPUCanvasContext closure

- `packages/webgpu/src/index.js` now exposes `createCanvasContext(canvas)` on
  the full/package surface when running on macOS, using the repo-local
  `GPUCanvasContext` wrapper instead of leaving Metal canvas support browser-
  only.
- `runtime/bridge/webgpu-addon/` now loads WebGPU surface proc entrypoints and
  exports a hosted Metal canvas bridge (`canvasSurfaceCreate`,
  `canvasSurfaceConfigure`, `canvasSurfaceGetCurrentTexture`,
  `canvasSurfacePresent`, `canvasSurfaceUnconfigure`, `canvasSurfaceRelease`)
  backed by `metal_bridge_create_surface_host` /
  `metal_bridge_configure_surface_host`.
- `packages/webgpu/src/shared/native-metal-canvas-backend.js` now manages the
  hosted `CAMetalLayer` surface lifecycle for the package path and presents
  pending canvas contexts after successful queue submits.
- The package-side Metal canvas closure is intentionally narrower than the
  current Vulkan surface path: `colorSpace="srgb"` and
  `toneMapping.mode="standard"` are supported now, while extended tone mapping
  / HDR colorspace selection remains explicit follow-up work.
- Reconciled `config/webgpu-spec-index.jsonl` with the browser-lane policy:
  the 29 browser-owned delegation rows (`externalTexture`,
  `importExternalTexture`, `copyExternalImageToTexture`, `GPUOrigin2DDict*`,
  and `xrCompatible`) are again marked `implemented` for Metal/Vulkan product
  cells with explicit notes that the behavior lives on the Fawn browser lane,
  not in the headless Doe native backends themselves.
- `config/webgpu-spec-index.jsonl` now promotes the Metal `GPUCanvasContext`,
  `GPUCanvasConfiguration`, and `GPUCanvasAlphaMode` rows out of
  `out_of_scope`; `GPUCanvasToneMappingMode.extended` remains blocked rather
  than silently accepted.
- `packages/webgpu/test/integration/test-integration-canvas-node.js` adds the
  focused macOS integration smoke for configure / acquire / clear / present /
  unconfigure.

### Compute package surface closes Doppler lifecycle and clear-buffer gaps

- `packages/webgpu/src/compute.js` now forwards `GPUCommandEncoder.clearBuffer`
  through the compute facade instead of omitting it, so compute-surface callers
  can do GPU-side zeroing without dropping to the full package surface.
- The compute facade now also forwards `GPUDevice.pushErrorScope()`,
  `GPUDevice.popErrorScope()`, and `GPUDevice.lost`, matching the underlying
  headless package lifecycle/debug contract closely enough for Doppler's kernel
  and device-management paths.
- `packages/webgpu/src/compute.d.ts` now advertises those methods/properties on
  the compute-only device and command-encoder types.
- `packages/webgpu/test/integration/test-integration-compute-surface.js` adds
  focused regression coverage for compute-surface `getCompilationInfo()`,
  `clearBuffer()`, error scopes, and `device.lost`.

## 2026-03-19

### macOS package adapter-info ABI repair

- The Node/addon bridge now prefers Doe-native adapter-info publication on
  macOS package paths, with `wgpuAdapterGetInfo` retained only as a fallback.
- This restores safe `GPUAdapter.info` / `GPUDevice.adapterInfo` publication on
  the current drop-in provider path, which had been faulting through Dawn's
  standard adapter-info call.
- `GPUDevice.popErrorScope()` on the Node/addon package surface now returns a
  `GPUError`-shaped object or `null`, missing render-pass indirect draw
  entrypoints fail explicitly, and adapter `requestDevice()` now returns a real
  `DoeGPUDevice` instance instead of a prototype-copied plain object.
- Node/addon write-mapped buffers now flush every staged `getMappedRange()`
  slice on `unmap()` rather than only the most recent range, the lazy
  compute-pass promotion path is shared across the remaining Node wrapper
  callsites, and render-bundle indirect draw wrappers now fail explicitly when
  the addon lacks those entrypoints.
- Package command buffers are now wrapped as first-class JS resources with
  explicit ownership: `queue.submit()` rejects resubmission of an already
  consumed command buffer, successful submits release the native command-buffer
  handle immediately, and dropped unsubmitted buffers are finalizer-cleaned
  when the active backend exposes a release hook.

### Browser-owned WebGPU delegation rows promoted in spec index

- Reclassified the 29 browser-owned delegation rows in
  `config/webgpu-spec-index.jsonl` from `blocked` to `implemented` for the
  `metal`, `vulkan`, and `d3d12` backend cells.
- Covered rows are the browser-lane-owned surfaces:
  - external texture types and bindings
  - `GPUDevice.importExternalTexture`
  - `GPUQueue.copyExternalImageToTexture`
  - `GPUCopyExternalImage*` dictionaries
  - `GPUOrigin2DDict*`
  - `GPURequestAdapterOptions.xrCompatible`
- Notes on those rows now state the intended contract explicitly:
  implementation exists through the Fawn browser lane via browser-owned
  delegation, while the headless Doe native runtime does not own those APIs
  directly.
- Follow-up implementation/evidence landed the same day:
  - `packages/webgpu/src/shared/validation.js` now validates
    `GPURequestAdapterOptions.xrCompatible` as an explicit boolean on the shared
    browser surface.
  - `browser/chromium/scripts/webgpu-playwright-smoke.mjs` now exercises the
    browser-lane closures end-to-end in both Dawn and Doe modes: explicit
    `xrCompatible` forwarding, `copyExternalImageToTexture` readback with
    `flipY`/origin dictionaries, and `importExternalTexture` plus
    `externalTexture` bind-group sampling from a `VideoFrame`.
- The spec-ledger promotion reconciles the browser-lane implementation in
  `packages/webgpu/src/browser.js`,
  `packages/webgpu/src/shared/browser-native-canvas-backend.js`, and the shared
  validation/full-surface package paths with exercised browser evidence at
  `browser/chromium/artifacts/20260319T122244Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`.

## 2026-03-17

### Lean-verified bounds check elimination (Layer 2)

- `config/proof-artifact.schema.json`: added `boundsEliminations` array to schema
  (required field). Each entry maps a Lean theorem to an index access pattern,
  precondition, and target runtime path for clamp elision.
- `pipeline/lean/artifacts/proven-conditions.json`: added five shader bounds
  theorems (`gid_component_lt_total`, `gid_inbounds_when_dispatch_fits`,
  `clamp_noop_when_inbounds`, `gid_2d_inbounds`, `flat_index_2d_inbounds`) to
  `theorems` array; added `boundsEliminations` array with two entries
  (1D gid access, 2D flat index).
- `runtime/zig/src/lean_proof.zig`: exposes `bounds_elimination_available` (bool,
  comptime) and `boundsProven(pattern)` query; validates `boundsEliminations`
  section presence when shader bounds theorems are listed.
- `runtime/zig/src/doe_wgsl/ir_transform_robustness.zig`: imports `lean_proof`,
  exposes `ELISION_ENABLED`, `DispatchPrecondition`, `TransformResult`,
  `applyWithResult()`. Pattern recognizer (`classify_gid_component`,
  `resolve_storage_binding`) identifies `buf[gid.{x,y,z}]` on storage buffers
  and skips `min()` clamp when proofs are available. Dispatch preconditions
  recorded for host-side enforcement.
- `runtime/zig/src/doe_wgsl/ir_transform_robustness_test.zig`: two new tests
  (`gid pattern on storage buffer behavior`, `non-gid index still gets clamped`).
- No runtime behavioral change for default builds (`-Dlean-verified` defaults to
  false). Clamp elision activates only with `-Dlean-verified=true` and a valid
  proof artifact.

### Vulkan GPU fence/sync and streaming copy

- New `vk_sync.zig` module adds `FencePool` (4-slot ring) and `TimelineSemaphore` to the Vulkan backend.
- Deferred queue submissions now signal a pool fence instead of `VK_NULL_HANDLE`, enabling `FencePool.drain()` to wait per-submission without `vkQueueWaitIdle`.
- `flush_queue` in `vk_upload.zig` uses `FencePool.drain()` when available; `vkQueueWaitIdle` retained as fallback only when fence pool is not initialized.
- Timeline semaphore support (`VK_KHR_timeline_semaphore`) detected at device bootstrap via `vkGetPhysicalDeviceFeatures2`; timeline semaphore created when supported. Available for future monotonic GPU->CPU signaling.
- Streaming copy command buffer (`begin_streaming_copy`, `streaming_copy_buffer_to_buffer`, `flush_streaming_copy`) enables batched blit/copy recording into a dedicated command buffer, submitted with fence-pool tracking.
- No config schema changes; runtime-only addition.
- Status table updated: Vulkan GPU fence/sync `○` -> `●`, Blit/copy batch/streaming `○` -> `●`.

### spirv-val wired into routine build/test flow

- `bench/spirv_val_gate.py` validates SPIR-V artifacts with `spirv-val`.
  Scans `bench/kernels/`, `bench/out/`, and `runtime/zig/zig-out/` for
  `.spv` files (excluding `bench/vendor/`). Skips gracefully when
  `spirv-val` is not installed; fails with `--require`.
- `runtime/zig/build.zig` exposes `zig build spirv-val` step.
- `bench/run_blocking_gates.py` accepts `--with-spirv-val-gate`,
  `--spirv-val-require`, and `--spirv-val-compile` flags.
- No schema changes; `config/shader-toolchain.json` already modeled
  `spirv_validate` as an optional external-tool stage for `doe_vulkan`.

### Shader artifact manifest emitters adopt schemaVersion 2

- Metal and D3D12 backend manifest emitters now emit `schemaVersion=2` manifests
  conforming to `config/shader-artifact.schema.json` v2 definitions
  (`v2MetalManifest`, `v2D3D12Manifest`).
- Previously Metal and D3D12 emitted an ad-hoc format with no `schemaVersion`,
  `irSha256`, backend-specific artifact hashes, or stage attestation array.
- New emitter modules:
  - `runtime/zig/src/backend/metal/artifact_emit.zig`
  - `runtime/zig/src/backend/d3d12/artifact_emit.zig`
- Both follow the same pattern as `runtime/zig/src/backend/vulkan/artifact_emit.zig`
  (which already emitted v2).
- Metal manifests now include: `irSha256`, `mslSha256`, `metallibSha256`,
  `toolchainSha256`, `pipelineHash`, `taxonomyCode`, `stages` array with
  `wgsl_parse`, `sema`, `ir_build`, `ir_validate`, `ir_to_msl`, `msl_compile`,
  `metallib_link` route attestations.
- D3D12 manifests now include: `irSha256`, `dxilSha256`, `toolchainSha256`,
  `pipelineHash`, `taxonomyCode`, `stages` array with `wgsl_parse`, `sema`,
  `ir_build`, `ir_validate`, `ir_to_dxil`, `dxil_validate` route attestations.
- `runtime/zig/src/backend/metal/mod.zig` and `runtime/zig/src/backend/d3d12/mod.zig`
  now delegate manifest emission to their respective `artifact_emit.zig` modules.
- `docs/status.md` updated to reflect that strict native-route enforcement can now
  be enabled universally.

## 2026-03-10

### WebGPU backend checklist reconciliation

- Reconciled `config/webgpu-spec-index.jsonl` against the current backend/runtime
  state in `docs/status.md`.
- D3D12 checklist notes were promoted out of the stale "first compute-first
  Windows subset" wording for surfaces now backed by the real Windows runtime:
  limits/features, render pipeline/pass/draw, query sets, descriptor bindings,
  texture lifecycle, `dispatchWorkgroupsIndirect`, and `onSubmittedWorkDone`.
- Conservative member-level promotions were applied where source-backed D3D12
  support now exists but fresh Windows evidence is still thin, including
  `createPipelineLayout`, `createRenderBundleEncoder`, render-bundle finish /
  execute, occlusion-query hooks, and render-pass state controls.
- Vulkan checklist/docs were softened from "absent" to "Linux-only / in
  progress" for resource/render cells that now have real native backend code,
  while still leaving broad graphics/resource closure as open work.

### AMD Vulkan and Apple Metal lane naming cutover

- The old host-scoped lane names have been replaced with explicit platform names:
  - `local_vulkan_extended` -> `amd_vulkan_extended`
  - `local_vulkan_extended.strict` -> `amd_vulkan_extended_strict`
  - `local_vulkan_smoke` -> `amd_vulkan_smoke`
  - `local_metal_extended` -> `apple_metal_extended`
  - `local_metal_smoke` -> `apple_metal_smoke`
- The previous AMD vendor-pinned 80-row catalog family is now named
  `amd_vulkan_superset` so it no longer collides with the new primary AMD
  Vulkan extended contract.
- Workload/config file names were renamed to match that cutover, including:
  - `bench/workloads.amd.vulkan.superset.json`
  - `bench/workloads.amd.vulkan.extended.json`
  - `bench/workloads.amd.vulkan.extended.strict.json`
  - `bench/workloads.apple.metal.extended.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.superset*.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended*.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal*.json`
- Browser-layer superset tooling now sources `bench/workloads.amd.vulkan.superset.json`
  explicitly, so the name still matches the broader 80-row engine contract it
  projects from.
- `bench/run_release_pipeline.py`, `bench/backend_selection_gate.py`, and
  `bench/output_paths.py` now recognize the renamed AMD/Apple config families
  and artifact prefixes while still accepting legacy `local.*` names for
  backwards compatibility.

## 2026-03-09

### macOS dispatch parity and normalization contract promotion

- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json` now
  passes `--kernel-root bench/kernels` to both sides of the local Metal strict
  comparable lane, so workloads that resolve WGSL kernels at runtime no longer
  depend on ad hoc extra-arg injection.
- `runtime/zig/src/core/compute/wgpu_commands_compute.zig` now executes plain
  `dispatch` / `dispatch_indirect` commands through the Dawn delegate path
  using the new built-in WGSL kernel `bench/kernels/dispatch_noop.wgsl`
  instead of returning `unsupported`.
- `bench/backend-workload-catalog.json` now promotes:
  - `compute_dispatch_fallback`
  - `compute_dispatch_grid`
  to `comparable=true` for `apple_metal_extended`, and the generated contract
  in `bench/workloads.apple.metal.extended.json` now carries the comparable
  local-Metal overrides (`applesToApplesVetted=true`,
  `comparabilityCandidate.enabled=false`, explicit right repeats/divisors, and
  `strictNormalizationUnit=dispatch` for `compute_dispatch_grid`).
- `bench/native-compare/compare_dawn_vs_doe.py` and
  `bench/native-compare/modules/runner.py` now accept explicit workload
  `strictNormalizationUnit` contracts (`dispatch` or `cycle`) so strict
  command-shape lint and trace-derived physical-operation checks can agree on
  workloads whose comparable unit is not raw command-row count.
- Behavioral difference versus the previous contract:
  `compute_dispatch_fallback` and `compute_dispatch_grid` are no longer
  directional-only on local Metal. Focused strict reruns:
  - `bench/out/scratch/20260310T_dispatch_copy_promote_probe/20260310T000344Z/metal.compute_dispatch_fallback.promote.json`
  - `bench/out/scratch/20260310T_dispatch_copy_promote_probe/20260310T001105Z/metal.compute_dispatch_grid.promote.v2.json`
  are now both structurally comparable and claimable on the local Metal lane.
  `copy_protocol` is no longer directional on local Metal. Focused strict rerun
  `bench/out/scratch/20260310T_final_blockers/20260310T004034Z/copy_protocol.promote.current.rerun.json`
  is now structurally comparable and claimable after native Metal
  `pipeline_async` diagnostics stopped reporting a synthetic dispatch/encode phase.

### macOS upload-repeat symmetry restoration

- `bench/backend-workload-catalog.json` now restores symmetric left/right
  `commandRepeat` values for local-Metal strict upload rows:
  - `upload_write_buffer_1kb`
  - `upload_write_buffer_64kb`
  - `upload_write_buffer_1mb`
  - `upload_write_buffer_4mb`
  - `upload_write_buffer_16mb`
- The generated contract in `bench/workloads.apple.metal.extended.json` now
  carries those restored left-side repeat values instead of silently falling
  back to `leftCommandRepeat=1` while the Dawn side repeated 500/100/50 times.
- Behavioral difference versus the previous contract:
  focused strict local-Metal rerun
  `bench/out/scratch/20260310T015302Z/20260310T_medium_upload_symmetry_probe_v2`
  is now claimable for both `upload_write_buffer_4mb` and
  `upload_write_buffer_16mb`, and the fresh authoritative full-lane rerun
  `bench/out/apple-metal/extended-comparable/20260310T015327Z/dawn-vs-doe.local.metal.extended.comparable.rerun.v5.json`
  now keeps both rows claimable under aggregate lane pressure.
  The smallest local-Metal upload row, `upload_write_buffer_1kb`, now also uses
  `left/rightCommandRepeat=1000` in the generated contract so focused and full
  local claim reruns stay above startup noise.

### macOS large-upload claimability hardening

- Native Metal upload benchmarking now reuses pre-zeroed shared upload sources
  instead of re-zeroing large buffers inside every timed sample in
  `runtime/zig/src/backend/metal/metal_native_runtime.zig`.
- Local-Metal strict upload claims may now fall back to
  `timingInterpretation.headlineProcessWall.deltaPercent` when selected
  operation timing implies physically implausible throughput or otherwise
  undercounts end-to-end upload completion on one side.
- Behavioral difference versus the previous contract:
  focused strict local-Metal proofs for `upload_write_buffer_1gb` and
  `upload_write_buffer_4gb` are now claimable:
  - `bench/out/scratch/20260310T_final_blockers/20260310T010134Z/upload_1gb_current.v3.json`
  - `bench/out/scratch/20260310T_final_blockers/20260310T005801Z/upload_large_generated_current.v2.json`
- Behavioral difference versus the previous contract:
  the fresh full strict local Metal artifact
  `bench/out/apple-metal/extended-comparable/20260310T001320Z/dawn-vs-doe.local.metal.extended.comparable.rerun.v3.json`
  now reclaims `upload_write_buffer_64kb` and `upload_write_buffer_1mb` as
  claimable rows in the authoritative full-lane report. `upload_write_buffer_1kb`
  still has a real tail-performance gap under full-lane pressure.

### macOS surface presentation command contract hardening

- `examples/surface_full_presentation_commands.json` now configures the
  presentable surface with `bgra8unorm` instead of `rgba8unorm`.
- The full WebGPU surface proc path on macOS now creates a hosted
  `CAMetalLayer` source for `wgpuInstanceCreateSurface`:
  - `runtime/zig/src/full/surface/wgpu_surface_commands.zig`
  - `runtime/zig/src/full/surface/wgpu_surface_macos.zig`
  - `runtime/zig/src/full/surface/wgpu_surface_procs.zig`
  - `runtime/zig/src/backend/metal/metal_bridge.{h,m}`
- Behavioral difference versus the previous contract:
  the Dawn delegate path now uses a real macOS Metal surface source and a
  presentable swapchain format, so `surface_full_presentation` can acquire and
  present successfully on Apple/Metal instead of failing at
  `wgpuSurfaceGetCurrentTexture`.

### macOS surface presentation comparability promotion

- `bench/backend-workload-catalog.json` now promotes `surface_full_presentation`
  to `comparable=true` for `apple_metal_extended`, and the generated contract in
  `bench/workloads.apple.metal.extended.json` now carries the comparable local
  Metal override (`applesToApplesVetted=true`, `rightCommandRepeat=100`,
  `left/rightTimingDivisor=100`, `comparabilityCandidate.enabled=false`).
- `runtime/zig/src/full/surface/wgpu_surface_commands.zig` now records non-present
  surface lifecycle wall time in `encode_ns` and present wall time in
  `submit_wait_ns`, aligning the full WebGPU surface path with the native Metal
  timing-phase contract used by the strict comparability gate.
- `bench/native-compare/compare_dawn_vs_doe.py` and
  `bench/native-compare/modules/runner.py` now validate `domain=surface`
  normalization against repeated presentation cycles, not raw per-command row
  count, so strict comparable surface claims use one full presentation cycle as
  the comparable unit.
- Behavioral difference versus the previous contract:
  `surface_full_presentation` is no longer directional-only on local Metal. A
  focused strict rerun (`bench/out/scratch/20260309T_surface_fix/20260309T204238Z/metal.surface_full_presentation.strict.v2.json`)
  is now both structurally comparable and claimable on the local Metal lane.

### macOS copy-family comparability promotion

- `bench/backend-workload-catalog.json` now promotes three local Metal copy rows:
  - `copy_buffer_to_texture`
  - `copy_texture_to_buffer`
  - `copy_texture_to_texture`
- The generated contract in `bench/workloads.apple.metal.extended.json` now carries
  local-Metal comparable overrides for those rows (`applesToApplesVetted=true`,
  `benchmarkClass=comparable`, `comparabilityCandidate.enabled=false`, and explicit
  `rightCommandRepeat` / `rightTimingDivisor` values matching the repeated copy
  command sequence contract).
- Behavioral difference versus the previous contract:
  those rows are no longer directional-only on local Metal. Focused strict reruns
  show `copy_buffer_to_texture`, `copy_texture_to_texture`, and now
  `copy_texture_to_buffer` are claimable on local Metal; the latter uses
  headline process wall at `100` repeats to avoid delegate operation-timing
  undercount.
  The local-Metal `copy_texture_to_buffer` contract now uses `2000` repeats and
  matching divisors in the generated workload file so headline-process-wall
  claimability is less sensitive to microsecond-scale tail noise in both focused
  and full-lane reruns.

### macOS full local strict lane closure

- The fresh authoritative full local-Metal strict artifact
  `bench/out/apple-metal/extended-comparable/20260310T121546Z/dawn-vs-doe.local.metal.extended.comparable.rerun.v7.json`
  is now fully claimable: `31/31` comparable rows claimable.
- Behavioral difference versus the prior local-Metal full-lane state:
  the previous residual blockers
  - `upload_write_buffer_1kb`
  - `upload_write_buffer_4gb`
  - `copy_texture_to_buffer`
  are now all claimable in the same full aggregate artifact instead of only in
  focused reruns.

### Track A (browser) claim lane and maintenance wiring

- Added a config-backed local browser claim policy:
  - `config/browser-claim-policy.schema.json`
  - `config/browser-claim-policy.json`
- Added a repeated-window browser claim gate:
  - `bench/browser/browser_claim_gate.py`
- The canonical blocking runner can now execute the browser claim gate:
  - `python3 bench/run_blocking_gates.py --with-browser-claim-gate`
- Added scheduled macOS browser refresh wiring and browser-artifact retention cleanup:
  - `.github/workflows/macos-browser-refresh.yml`
  - `browser/chromium/scripts/cleanup-browser-artifacts.py`
- Behavioral difference versus the prior promoted-browser state:
  browser diagnostics are no longer limited to a single smoke + layered
  snapshot. The repo now supports repeated-window local claim evidence and
  scheduled host-refresh execution with explicit retention cleanup. The
  default Track A (browser) gate remains diagnostic; claimability is emitted only
  by the dedicated browser claim lane.

### Track A (browser) governance promotion

- Track A (browser) diagnostics now have a governed core gate:
  - `bench/browser/browser_gate.py`
- The canonical blocking runner can now execute that browser gate:
  - `python3 bench/run_blocking_gates.py --with-browser-gate`
- Added explicit promoted ownership for Track A (browser) scope:
  - `config/browser-ownership.schema.json`
  - `config/browser-ownership.json`
- Browser workflow and approval contracts were promoted from Track B (modules)-only
  approval assumptions to explicit Track A (browser) cross-owner signoff:
  - `browser/chromium/bench/workflows/browser-workflow-manifest.json`
  - `browser/chromium/bench/workflows/browser-workflow-manifest.schema.json`
  - `browser/chromium/bench/workflows/browser-promotion-approvals.json`
  - `browser/chromium/bench/workflows/browser-promotion-approvals.schema.json`
- Behavioral difference versus the prior nursery-only state:
  browser smoke and strict layered superset validation are now executable from
  the canonical blocking gate runner with required ownership/approval checks,
  rather than being tracked only as ad hoc nursery-local evidence.

### Track B (modules) 2D SDF renderer promotion

- `fawn_2d_sdf_renderer` moved from the nursery Python prototype in
  `browser/chromium/scripts/module_prototype.py` to a core Zig
  implementation in `runtime/zig/src/full/modules/rendering/sdf_renderer.zig`.
- The canonical schema/policy contract is now:
  - `config/sdf-renderer.schema.json`
  - `config/sdf-renderer.policy.json`
- The nursery schema remains present only as a deprecated incubation reference:
  - `browser/chromium/module-incubation/schemas/fawn-2d-sdf-renderer.schema.json`
- Behavioral difference versus the nursery prototype:
  the promoted path now executes through the shared render runtime and emits
  deterministic trace-linked render artifacts instead of prototype-only policy
  simulation.

### Track B (modules) path engine promotion

- `fawn_path_engine` moved from the nursery Python prototype in
  `browser/chromium/scripts/module_prototype.py` to a core Zig
  implementation in `runtime/zig/src/full/modules/rendering/path_engine.zig`.
- The canonical schema/policy contract is now:
  - `config/path-engine.schema.json`
  - `config/path-engine.policy.json`
- The nursery schema remains present only as a deprecated incubation reference:
  - `browser/chromium/module-incubation/schemas/fawn-path-engine.schema.json`
- Behavioral difference versus the nursery prototype:
  the promoted path now executes through the shared render runtime and emits
  deterministic geometry/raster telemetry instead of prototype-only counters.

### Track B (modules) effects pipeline promotion

- `fawn_effects_pipeline` moved from the nursery Python prototype in
  `browser/chromium/scripts/module_prototype.py` to a core Zig
  implementation in `runtime/zig/src/full/modules/rendering/effects_pipeline.zig`.
- The canonical schema/policy contract is now:
  - `config/effects-pipeline.schema.json`
  - `config/effects-pipeline.policy.json`
- The nursery schema remains present only as a deprecated incubation reference:
  - `browser/chromium/module-incubation/schemas/fawn-effects-pipeline.schema.json`
- Behavioral difference versus the nursery prototype:
  the promoted path now executes through the shared render runtime and emits
  deterministic effect-pass timing and fallback telemetry under the canonical
  config contract.

## 2026-03-08

### Track B (modules) compute services promotion

- `fawn_compute_services` moved from the nursery Python prototype in
  `browser/chromium/scripts/module_prototype.py` to a core Zig
  implementation in `runtime/zig/src/full/modules/services/compute_services.zig`.
- The canonical schema/policy contract is now:
  - `config/compute-services.schema.json`
  - `config/compute-services.policy.json`
- The nursery schema remains present only as a deprecated incubation reference:
  - `browser/chromium/module-incubation/schemas/fawn-compute-services.schema.json`
- Behavioral difference versus the nursery prototype:
  real GPU `kernel_dispatch` execution now runs through the core WebGPU compute
  path, while returned timing fields are deterministic contract values rather
  than host-wall timings because M6 promotion is governance/correctness-only.

### Track B (modules) resource scheduler promotion

- `fawn_resource_scheduler` moved from the nursery Python prototype in
  `browser/chromium/scripts/module_prototype.py` to a core Zig
  implementation in `runtime/zig/src/full/modules/services/resource_scheduler.zig`.
- The canonical schema/policy contract is now:
  - `config/resource-scheduler.schema.json`
  - `config/resource-scheduler.policy.json`
- The nursery schema remains present only as a deprecated incubation reference:
  - `browser/chromium/module-incubation/schemas/fawn-resource-scheduler.schema.json`
- Behavioral difference versus the nursery prototype:
  real buffer/texture allocation now happens through `WebGPUBackend` resource
  helpers, and pool statistics are emitted from the promoted scheduler contract
  rather than the nursery alternating reuse/allocate simulation.

## 2026-03-07

### Shared library artifact hard rename

- The canonical Doe drop-in shared library artifact is now `libwebgpu_doe` rather
  than `libdoe_webgpu`.
- Active build outputs, package prebuilds, browser lane scripts, benchmark gate
  defaults, and package loaders now probe only `libwebgpu_doe.{so,dylib,dll}`.
- This is a hard migration for active codepaths: the previous filename is not an
  accepted fallback in loaders or default scripts.

### Package/Zig build proof provenance metadata

- `runtime/zig/build.zig` now emits deterministic drop-in build provenance to
  `runtime/zig/zig-out/share/doe-build-metadata.json`, including:
  - `leanVerifiedBuild`
  - `proofArtifactSha256`
- `runtime/zig/src/wgpu_dropin_lib.zig` now links a tiny build-info export so the shared
  library embeds the `lean_verified` build bit instead of leaving it purely in
  publish metadata.
- `packages/webgpu/scripts/prebuild.js` now requires that Zig build metadata sidecar
  and copies the same proof provenance into published `prebuilds/*/metadata.json`.
- `packages/webgpu/src/index.js` and `packages/webgpu/src/bun-ffi.js` now expose that
  provenance via `providerInfo()`:
  - `buildMetadataSource`
  - `buildMetadataPath`
  - `leanVerifiedBuild`
  - `proofArtifactSha256`
- Added package contract schemas:
  - `packages/webgpu/doe-build-metadata.schema.json`
  - `packages/webgpu/prebuild-metadata.schema.json`

### Metal upload apples-to-apples restoration

- `runtime/zig/src/backend/metal/metal_native_runtime.zig` now routes comparable
  WriteBuffer-style uploads through staged shared-to-private blit copies on
  Metal for both small and large payloads.
- Removed the Metal tiny-upload shared-memory fast path that could bypass the
  staged GPU copy Dawn performs, and upload staging buffers are now rewritten on
  every iteration instead of only on first allocation.
- `runtime/zig/src/backend/metal/mod.zig` now records Metal upload staging work in
  `setup_ns` instead of `encode_ns`, aligning timing-phase accounting with the
  Dawn delegate upload lane.
- `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json` now
  forwards `queue_sync_mode`, `upload_buffer_usage`, and `upload_submit_every`
  symmetrically to both left and right runtime commands.
- Local Metal upload workload contracts no longer carry `pathAsymmetry` after
  the staged-copy restoration:
  - `bench/workloads.apple.metal.extended.json`
  - `bench/workloads.apple.metal.smoke.json`

### Blocking timing-phase symmetry obligation

- Added a new blocking strict-comparability obligation:
  - `left_right_timing_phase_match`
- Updated the canonical obligation sources and parity fixtures:
  - `config/comparability-obligations.json`
  - `config/comparability-obligation-fixtures.schema.json`
  - `bench/comparability_obligation_fixtures.json`
  - `bench/native-compare/modules/comparability.py`
  - `pipeline/lean/Fawn/Comparability.lean`
  - `pipeline/lean/Fawn/ComparabilityFixtures.lean`
- Strict comparable reports now fail when one side reports a median-zero timing
  phase that the other side spends materially in, closing the setup/encode/submit
  scope gap that previously escaped comparability while only failing claimability.

### Compare report timing interpretation fields

- `bench/native-compare/compare_dawn_vs_doe.py` still writes report `schemaVersion: 4`, but now
  adds additive timing-interpretation fields without changing existing
  `deltaPercent` semantics:
  - top-level `timingInterpretationPolicy`
  - per-workload `timingInterpretation.selectedTiming`
  - per-workload `timingInterpretation.headlineProcessWall`
  - optional top-level `overallHeadlineProcessWall`
- `deltaPercent` remains the methodology-selected claim/comparability metric.
- `timingInterpretation.selectedTiming` now states whether that metric is
  `operation-total`, `process-wall`, or a narrow hot path such as
  `operation-encode`.
- `timingInterpretation.headlineProcessWall` reports timed-command process-wall
  deltas so encode-only render/report rows cannot be mistaken for end-to-end
  latency wins.
- claimability now keeps `deltaPercent` diagnostic for
  `timingInterpretation.selectedTiming.scopeClass = narrow-hot-path`, but when
  `timingInterpretation.headlineProcessWall` is available it uses that
  end-to-end metric for claim evaluation instead of forcing the row diagnostic
  on policy alone.
- repeat-asymmetric compare rows now normalize both counter-derived selected
  timing (`doe-execution-total-ns`, `doe-execution-encode-ns`,
  `doe-execution-dispatch-window-ns`, `doe-execution-gpu-timestamp-ns`) and
  `timingInterpretation.headlineProcessWall` by `commandRepeat`, and the
  claim-sanity coverage audit uses the same normalized units.
- `bench/build_claim_scope_report.py` now carries this selected-scope vs
  headline-process-wall context into citation-safe artifacts.

### AMD Vulkan extended preset aliases restored

- Restored the documented AMD Vulkan extended compare config aliases:
  - `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.strict.comparable.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.strict.release.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.strict.directional.json`
- `.gitignore` now explicitly unignores those three aliases so the documented
  presets remain versioned instead of machine-local.
- `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json` now
  uses the canonical strict lane name `vulkan_doe_comparable` instead of the
  stale nonexistent `vulkan_local_comparable`.
- Helper lane inference in `bench/backend_selection_gate.py` and
  `bench/run_release_pipeline.py` now treats AMD Vulkan extended directional presets as
  Doe-left diagnostics (`vulkan_doe_app`) rather than incorrectly inferring a
  separate Dawn directional lane.

## 2026-03-06

### Benchmark cube reporting contracts

- Added benchmark cube reporting contracts for cross-surface evidence aggregation:
  - `config/benchmark-cube-policy.schema.json` + `config/benchmark-cube-policy.json`
  - `config/benchmark-cube-row.schema.json`
  - `config/benchmark-cube.schema.json`
- Added governed lane catalog for cube publication and cross-surface lane normalization:
  - `config/governed-lanes.schema.json` + `config/governed-lanes.json`
- `config/schema-targets.json` now validates `config/benchmark-cube-policy.json`
  through schema gate like other canonical config contracts.
- benchmark cube rows now require governed lane provenance:
  - backend compare rows carry the two source runtime lane IDs from pipeline/trace/report telemetry
  - package compare rows require explicit report `laneId`
  - browser lanes are governed in the same catalog but remain non-cube lanes for now
- The benchmark cube introduces explicit cross-surface reporting dimensions:
  - host profile
  - surface (`backend_native`, `node_package`, `bun_package`)
  - provider pair
  - workload set
  - maturity / missing-cell status
- Initial policy position is explicit:
  - backend compare reports remain the canonical claim lane
  - Node is the primary supported package surface
  - Bun remains prototype until a real compare lane populates those cells
- Initial artifact builder is `bench/build_benchmark_cube.py`, which emits:
  - `bench/out/cube/<timestamp>/cube.rows.json`
  - `bench/out/cube/<timestamp>/cube.summary.json`
  - `bench/out/cube/<timestamp>/cube.matrix.md`
  - `bench/out/cube/<timestamp>/cube.dashboard.html`
  - stable latest mirrors under `bench/out/cube/latest/`
- Existing historical backend reports are now merged into cube rows even when they
  no longer satisfy current conformance contracts:
  - such rows are tagged `sourceConformance=legacy_nonconformant`
  - cube cells degrade them to `diagnostic` instead of dropping them or treating
    them as canonical claim evidence
- package compare reports without governed `laneId` are now excluded from canonical
  cube publication until rerun under the governed package lane contracts.

## 2026-03-05

### Quirk-mining manifest: toggleContext and toggleContextCounts

- `config/quirk-mining-manifest.schema.json` adds two new optional fields:
  - `toggleContextCounts` (top-level): object mapping context token → hit count.
  - `toggleHits[].toggleContext` (per-hit): context token for how the toggle was observed.
- Toggle context tokens: `reference`, `default_on`, `default_off`, `force_on`, `force_off`.
- `pipeline/agent/mine_upstream_quirks.py` now recognizes context-aware patterns:
  - `->Default(Toggle::X, true/false)` → `default_on` / `default_off`
  - `->ForceSet(Toggle::X, true/false)` → `force_on` / `force_off`
  - `->ForceEnable(Toggle::X)` → `force_on`
  - `->ForceDisable(Toggle::X)` → `force_off`
  - bare `Toggle::X` references not matched by the above → `reference`
- Quirk records themselves are unchanged; context metadata lives in the manifest only.
- Updated `examples/quirk-mining.manifest.sample.json` to include `toggleContextCounts`
  and `toggleContext` in sample `toggleHits` entries.

### Lean model: String.trim compatibility fix

- `pipeline/lean/Fawn/Model.lean`: replaced `text.trimAscii.toString` with `text.trim` for
  compatibility with the pinned Lean toolchain (4.16.0), where `String.trimAscii`
  is not available. Semantic behavior is identical for version-string parsing.

### Lean fixtures: Doe-vs-Doe parity obligation fields

- `pipeline/lean/Fawn/ComparabilityFixtures.lean`: added missing `ComparabilityFacts` fields
  introduced in 2026-02-26 (Doe-vs-Doe timing-scope parity obligations):
  - `traceMetaSourceMatchApplies` / `leftRightTraceMetaSourceMatch`
  - `timingSelectionPolicyMatchApplies` / `leftRightTimingSelectionPolicyMatch`
  - `queueSyncModeMatchApplies` / `leftRightQueueSyncModeMatch`
  - `executionShapeMatchApplies` / `leftRightExecutionShapeMatch`
- `pipeline/lean/check.sh` now passes cleanly with the pinned 4.16.0 toolchain.

### Apple Metal quirks and CI

- Added `examples/quirks/apple_m3_noop_list.json`: empty quirk list for Apple M3 Metal
  benchmark runs (analogous to `amd_radv_noop_list.json` for Vulkan).
- Updated `bench/workloads.apple.metal.extended.json`: all 43 workload quirksPath entries
  changed from `amd_radv_noop_list.json` to `apple_m3_noop_list.json`.
- Added `.github/workflows/lean-check.yml`: CI workflow that installs elan and runs
  `pipeline/lean/check.sh` on every push/PR, making Lean typecheck a CI gate on macOS runners.

### Metal benchmark — third run (2026-03-05)

- Third comparable run with updated config (iterations=20, minTimedSamples=19): 3/23 claimable.
- Claimable: `upload_write_buffer_4mb` (+4.20% p50, up from +0.68% in Run 2), `render_draw_redundant_pipeline_bindings` (+0.25% p50, stable), `compute_concurrent_execution_single` (+0.18% p50).
- Render workload characterization confirmed: all render encode timings cluster at 60–61µs for 2000 draws. The reported −1.5% to −3% is a 1µs CPU timer quantization artifact. Both sides call Dawn's `wgpuRenderPassEncoderDraw`; sub-quantization difference is system-state noise.
- Blend/stencil setup optimization (`wgpu_render_commands.zig`: skip `set_blend_constant` when (0,0,0,0), skip `set_stencil_reference` when 0) is in the setup phase — outside the encode timing window — so it has no measurable effect on reported encode time.
- Upload outliers (1MB occasional 0.352ms, render_uniform_buffer occasional 0.614ms) are GPU scheduling latency events, not Doe code regressions.
- Config change: iterations 12→20, minTimedSamples 11→19.

### Metal benchmark — second run (2026-03-05)

- Second full comparable run with current config: 6/23 claimable (up from 5/23 in Run 1).
- New claimable in Run 2: `upload_write_buffer_1kb` (+0.85% p50), `upload_write_buffer_64kb`
  (+0.40% p50), `upload_write_buffer_1gb` (+2.27% p50), `render_draw_redundant_pipeline_bindings`
  (+0.25% p50), `render_bundle_dynamic_pipeline_bindings` (+0.88% p50).
- Per-operation timing analysis for 1KB/64KB: ~97.5% of execution time is Metal
  command-buffer submit+wait. Doe Metal has tighter latency distribution (spread=0.005ms)
  than the Dawn Metal delegate (spread=0.029ms at 64KB); p50 near parity, p95 consistently
  positive. Sign flips between runs are system-state noise, not a methodology gap.
- No schema changes in this run; artifact contracts and workload contract unchanged.

## 2026-03-04

### Render-domain timing policy alignment

- Strict Dawn-vs-Doe render-family timing policy now treats render encoding as the comparable operation scope for both `render` and `render-bundle` domains.
- `config/backend-timing-policy.json` changes:
  - `domains.render.allowedTimingSources` now includes `doe-execution-encode-ns`.
  - new `domains.render-bundle` policy was added (same required timing class/sync model and source allowlist structure as `render`).
- Compare-harness policy alignment:
  - strict comparability expects Doe-side `doe-execution-encode-ns` with `timingSelectionPolicy=render-encode-preferred` for `render`/`render-bundle`.
  - upload row-total policy remains unchanged.

## 2026-03-03

### Drop-in strict ownership contract simplification

- Migrated drop-in symbol ownership contract to schema version `2`:
  - removed `requiredInStrict` from symbol entries.
  - strict no-fallback is now policy-wide and does not depend on per-symbol strict flags.
  - optional compatibility mode remains explicit through `dropin-abi-behavior.json` (`strictFallbackForbidden=false`).
- Updated files:
  - `config/dropin-symbol-ownership.schema.json`
  - `config/dropin-symbol-ownership.json`
  - `runtime/zig/src/config/dropin-symbol-ownership.json`
- Runtime parser now enforces `schemaVersion == 2` in:
  - `runtime/zig/src/dropin/dropin_symbol_ownership.zig`

### No-op execution placeholder retirement

- Removed embedded no-op kernel fallback routing from active WebGPU command execution paths.
- `dispatch`/`dispatch_indirect` now fail explicitly unless executed through explicit `kernel_dispatch` contracts.
- Vulkan native dispatch no longer auto-builds a default no-op compute pipeline; dispatch now requires an explicit loaded kernel pipeline.

### Backend lane fallback policy clarification

- Backend lane selection remains strict-only by contract:
  - `allowFallback` is schema-constrained to `false`.
  - `strictNoFallback` is schema-constrained to `true`.
- Runtime backend init continues to fail fast without delegate fallback branches in active backend routing.

## 2026-03-02

### Strict Dawn-vs-Doe normalization contract hardening

- Comparable workload timing divisors were migrated to direct operation timing for Dawn-vs-Doe strict runs:
  - `leftTimingDivisor=1.0`
  - `rightTimingDivisor=1.0`
- Updated workload catalogs under `bench/workloads*.json` accordingly for comparable workloads.
- `bench/native-compare/compare_dawn_vs_doe.py` now fails fast in strict operation mode if a comparable
  Dawn-vs-Doe workload config attempts side-specific divisor scaling.

### Benchmark workload ID contract migration (status-free IDs)

- Migrated benchmark workload IDs away from lifecycle/status prefixes (`par_`, `exp_`, `ctr_`)
  and maturity tokens (`contract`, `proxy`, `macro`).
- New benchmark ID contract is now stable, domain-first, and shape-oriented:
  `domain_subject_shape_variant`.
- Workload IDs are immutable contract keys:
  - do not rename IDs when promoting directional workloads to comparable/claim lanes.
  - encode comparability/claim methodology in workload metadata (`comparable`, `benchmarkClass`,
    `comparabilityCandidate`, normalization fields), not in ID text.
- Updated all benchmark workload references and maps to the new ID set across:
  - `bench/workloads*.json`
  - Dawn workload maps/autodiscovery
  - compare configs and claim-cycle contracts
  - benchmark/docs/status references

### Runtime command contract expansion for benchmark semantics

- Added first-class runtime command kinds for explicit workload semantics:
  - `dispatch_indirect`
  - `draw_indirect`
  - `draw_indexed_indirect`
  - `render_pass`
- Updated Zig model/parser/runtime/backend routing to treat these as explicit command
  kinds rather than alias-only labels.
- Updated benchmark command fixtures for indirect/RenderPass-named workloads to use
  matching command kinds directly.

### D3D12 backend lane and contract expansion

- Added first-class Doe D3D12 backend identity `doe_d3d12` to backend contract schemas and policy surfaces:
  - `config/backend-runtime-policy.schema.json`
  - `config/backend-cutover-policy.schema.json`
  - `config/backend-capability-policy.schema.json`
  - `config/backend-lane-map.schema.json`
  - `config/shader-artifact.schema.json`
- Added D3D12 runtime lanes to `config/backend-runtime-policy.json`:
  - `d3d12_doe_app`
  - `d3d12_doe_directional`
  - `d3d12_doe_comparable`
  - `d3d12_doe_release`
  - `d3d12_dawn_release`
- Updated generated lane map artifact `config/backend-lane-map.json` to include D3D12 lane-to-backend and backend-to-lane mappings.
- Added D3D12 backend capability policy entry in `config/backend-capability-policy.json`.
- Extended drop-in behavior contracts to understand strict D3D12 ownership mode and D3D12 lane routing:
  - `config/dropin-abi-behavior.schema.json`
  - `config/dropin-abi-behavior.json`
  - `config/dropin-symbol-ownership.schema.json`

## 2026-03-07

### Strict Vulkan staged-upload lane policy

- `config/backend-runtime-policy.schema.json` + `config/backend-runtime-policy.json`
  now bump the backend runtime policy contract to `schemaVersion=2` and add
  optional lane field `uploadPathPolicy`:
  - `allow_mapped_shortcuts`
  - `staged_copy_only`
- Strict Doe Vulkan benchmark/claim lanes now declare staged uploads explicitly
  in config:
  - `vulkan_doe_comparable` -> `uploadPathPolicy: "staged_copy_only"`
  - `vulkan_doe_release` -> `uploadPathPolicy: "staged_copy_only"`
- `selectionPolicyHashSeed` is now `backend-runtime-policy-v2` so pipeline/trace/report
  artifacts distinguish pre-fix and post-fix strict-lane evidence.
- `runtime/zig/src/backend/backend_policy.zig`, `runtime/zig/src/backend/backend_runtime.zig`,
  and `runtime/zig/src/backend/backend_registry.zig` now load and thread the lane upload
  path policy into backend initialization, failing fast if strict Vulkan lanes do
  not declare `staged_copy_only`.
- `runtime/zig/src/backend/vulkan/mod.zig` and
  `runtime/zig/src/backend/vulkan/native_runtime.zig` now honor the lane upload path
  policy at runtime: strict `vulkan_doe_comparable` / `vulkan_doe_release`
  uploads always execute staged GPU copy work, while app/directional Vulkan lanes
  keep the bounded mapped shortcuts for non-claim diagnostics.
- `bench/schema_gate.py` now validates that strict Vulkan lanes keep
  `uploadPathPolicy='staged_copy_only'`.

## 2026-03-06

### Timing-scope sanity contract for claimable backend rows

- `config/benchmark-methodology-thresholds.schema.json` + `config/benchmark-methodology-thresholds.json`
  now include `timingScopeSanity`:
  - `minOperationWallCoverageRatio`
  - `maxOperationWallCoverageAsymmetryRatio`
- `bench/native-compare/compare_dawn_vs_doe.py` now treats rows as non-claimable when selected
  operation timing covers implausibly little of process wall on one side and the
  left/right coverage ratios diverge beyond the configured asymmetry bound.
- `bench/build_benchmark_cube.py` applies the same policy to historical backend
  compare reports so the cube does not continue surfacing scope-suspect rows as
  claimable after methodology bugs are discovered.

## 2026-02-26

### Metal execution lane control and trace telemetry

- `doe-zig-runtime` now supports explicit backend-lane selection via `--backend-lane`:
  - `metal_doe_app`
  - `metal_doe_directional`
  - `metal_doe_comparable`
  - `metal_doe_release`
  - `metal_dawn_release`
  - `vulkan_doe_app`
  - `vulkan_doe_comparable`
  - `vulkan_doe_release`
  - `vulkan_dawn_release`
  - `d3d12_doe_app`
  - `d3d12_doe_directional`
  - `d3d12_doe_comparable`
  - `d3d12_doe_release`
  - `d3d12_dawn_release`
- Native execution uses the backend runtime selection pipeline through lane resolution; this metadata is now emitted through execution summaries and trace metadata when `--trace-meta` is requested.
  - `backendLane`
  - `backendSelectionReason`
  - `fallbackUsed`
  - `selectionPolicyHash`
  - `shaderArtifactManifestPath`
  - `shaderArtifactManifestHash`
- `runtime/zig/src/backend/backend_runtime.zig` now loads lane policy from `config/backend-runtime-policy.json` at runtime (`schemaVersion=1`, `selectionPolicyHashSeed`, lane `defaultBackend`/`allowFallback`/`strictNoFallback`).
  - missing/invalid policy contract entries now fail fast during runtime initialization (no implicit compile-time lane fallback in this path).
- `bench/schema_gate.py` is now driven from `config/schema-targets.json` instead of a hardcoded target list.
- Added local Metal compare preset configs to run comparable, directional, and release lanes against Dawn via Metal autodescovery:
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.directional.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.release.json`

### Metal app-lane cutover closure

- `config/backend-cutover-policy.json` now sets `targetLane` to `metal_doe_app` and `defaultBackend` to `doe_metal` for the app lane cutover path.
- `config/backend-runtime-policy.json` keeps `metal_doe_app` as strict (`allowFallback=false`, `strictNoFallback=true`) and now enforces strict no-fallback across every lane.
- `runtime/zig/src/execution.zig` now routes implicit Metal profile lane selection to `metal_doe_app` by default.
- Metal strict gate execution now supports cutover validation by passing `metal_doe_app` as `--local-metal-lane` where required and using release-cycle enforcement (`cycle_gate.py` with rollback criteria enabled).
- rollback switching is retired from runtime backend selection; incident response uses explicit lane policy/config changes with auditable artifacts.

### Backend/runtime contract expansion and strict-lane hardening

- Added backend contracts:
  - `config/backend-runtime-policy.schema.json` + `config/backend-runtime-policy.json`
  - `config/backend-capability-policy.schema.json` + `config/backend-capability-policy.json`
  - `config/backend-timing-policy.schema.json` + `config/backend-timing-policy.json`
  - `config/backend-cutover-policy.schema.json` + `config/backend-cutover-policy.json`
- Added shader contracts:
  - `config/shader-toolchain.schema.json` + `config/shader-toolchain.json`
  - `config/shader-error-taxonomy.schema.json` + `config/shader-error-taxonomy.json`
  - `config/shader-artifact.schema.json`
- Added drop-in ownership contracts:
  - `config/dropin-abi-behavior.schema.json` + `config/dropin-abi-behavior.json`
  - `config/dropin-symbol-ownership.schema.json` + `config/dropin-symbol-ownership.json`
- Added local-Metal hardening gates and helper modules:
  - `bench/backend_selection_gate.py`
  - `bench/shader_artifact_gate.py`
  - `bench/metal_sync_conformance.py`
  - `bench/metal_timing_policy_gate.py`
  - `bench/preflight_metal_host.py`
  - `bench/drop-in/dropin_proc_resolution_tests.py`
  - `bench/native-compare/modules/backend_contract.py`
  - `bench/native-compare/modules/shader_contract.py`
  - `bench/native-compare/modules/metal_sync_contract.py`
- `config/benchmark-methodology-thresholds.schema.json` + `config/benchmark-methodology-thresholds.json` now include reliability policy fields:
  - positive-tail percentile sets for local/release lanes
  - flake budget
  - retry policy taxonomy
- `config/toolchains.json` now records shader toolchain contract identity (`toolchains["shaderMetal"].contract`).

## 2026-02-25

### Indexed P0 render comparability promotion

- `bench/vendor/dawn/src/dawn/tests/perf_tests/DrawCallPerf.cpp` now includes an
  indexed draw variant (`DynamicVertexBuffer_DrawIndexed`) in Dawn perf coverage.
- `bench/workloads.amd.vulkan.extended.json` restores
  `render_multidraw_indexed` to strict comparable:
  - `comparable=true`
  - `benchmarkClass=comparable`
  - `applesToApplesVetted=true`
- Dawn filter contracts now map indexed workloads to the indexed variant:
  - `bench/dawn_workload_map.amd.extended.json`
  - `bench/native-compare/dawn_benchmark_adapter.py` autodiscovery patterns (`DynamicVertexBuffer_DrawIndexed`)
- strict apples-to-apples lanes now run indexed-vs-indexed for this contract.

### Directional comparability-candidate cohort contract

- `bench/workloads.amd.vulkan.extended.json` now supports optional workload field
  `comparabilityCandidate`:
  - `enabled` (bool)
  - `tier` (string)
  - `notes` (string)
- this field marks directional workloads that are isolated as likely parity-promotion
  targets; it does not change strict comparability status by itself.
- `bench/native-compare/compare_dawn_vs_doe.py` now supports:
  - CLI: `--workload-cohort all|comparability-candidates`
  - config: `run.workloadCohort`
- cohort `comparability-candidates` is fail-fast gated to directional lanes and
  requires `includeNoncomparableWorkloads=true`.
- reports now record both:
  - top-level `comparabilityPolicy.workloadCohort`
  - per-workload `comparabilityCandidate` metadata.
- added directional preset for the current 8 candidate workloads:
  `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.comparability-candidates.directional.json`.

### Doe backend identity cutover (phase 1-3 completed)

- Backend runtime identity is now Doe-only across runtime-visible surfaces.
- Canonical artifacts are:
  - runtime binary: `doe-zig-runtime`
  - drop-in shared library: `libdoe_webgpu.so`
- Chromium Track A (browser) runtime controls now use Doe names only:
  - selector value: `--use-webgpu-runtime=doe`
  - kill switch: `--disable-webgpu-doe`
  - runtime library path: `--doe-webgpu-library-path=<path>`
- Chromium GPU preference fields and mojom wiring were renamed to Doe equivalents:
  - `disable_webgpu_doe`
  - `doe_webgpu_library_path`
  - enum/runtime variants `kDoe`
- Legacy backend aliases (`fawn` runtime selector/backend library flag names) were removed.
- Doe-specific compare/report families now use `dawn-vs-doe` naming.

### Doe backend identity cleanup (phase 4 completed)

- Drop-in diagnostic helper exports are now Doe-named:
  - `doeWgpuDropinLastErrorCode()`
  - `doeWgpuDropinClearLastError()`
- Drop-in panic/error text now reports `doe drop-in ...` taxonomy.
- Runtime timestamp debug env flag is now Doe-named:
  - `DOE_WGPU_TIMESTAMP_DEBUG=1`
- Trace gate semantic-parity eligibility now matches Doe runtime module identity (`module` starts with `doe-`) and rejects non-Doe runtime module pairs in `required` mode.

### Package naming split (`@simulatte/*` public scope — now deprecated)

- Public npm/package scope previously used `@simulatte/*`.
  The `@simulatte/*` scope is now deprecated in favor of `doe-gpu`.
- Canonical runtime/headless package was `@simulatte/webgpu`; use `doe-gpu` instead.
- Canonical `@simulatte/webgpu` package root now lives entirely under `packages/webgpu/`.
- Browser package naming is reserved as `@simulatte/chromium`.
- Doe remains the backend/runtime family name for:
  - backend IDs (`doe_vulkan`, `doe_metal`, `doe_d3d12`)
  - compare/report families (`doe-vs-dawn`)
  - runtime artifacts (`doe-zig-runtime`, `libdoe_webgpu.so`)
- Legacy package names are retained only as compatibility history:
  - `@doe/webgpu-core`
  - `@doe/webgpu`
  - `@simulatte/webgpu` (deprecated — use `doe-gpu`)
  - `@simulatte/webgpu-doe` (deprecated — merged into `doe-gpu`)

## 2026-02-22

### `benchmark-methodology-thresholds` contract enforcement

- `config/benchmark-methodology-thresholds.schema.json` and
  `config/benchmark-methodology-thresholds.json` are now enforced inputs for
  benchmark comparability/claimability threshold selection.
- `bench/native-compare/compare_dawn_vs_doe.py` now reads:
  - `timingSelection.minDispatchWindowNsWithoutEncode`
  - `timingSelection.minDispatchWindowCoveragePercentWithoutEncode`
  - `claimabilityDefaults.localMinTimedSamples`
  - `claimabilityDefaults.releaseMinTimedSamples`
- These replace hardcoded benchmark thresholds in code.

### `modules.json` status semantics refreshed

- Bumped `config/modules.json` `schemaVersion` from `2` to `3`.
- Updated module status values from `scaffolded` to `active` for current runtime posture.

### `quirks.schema` action contract tightened

- Bumped `config/quirks.schema.json` quirk `schemaVersion` from `1` to `2`.
- Tightened `action` from open object to a strict discriminated contract:
  - `use_temporary_buffer` requires `params.bufferAlignmentBytes` (`>= 1`)
  - `toggle` requires `params.toggle`
  - `no_op` requires only `kind` and rejects extra fields
- Parser/runtime now enforce the same strictness:
  - unknown quirk fields are rejected during JSON parse
  - legacy action aliases (`noop`, `alignmentBytes`, `alignment`, `name`, `toggle_name`) are no longer accepted
  - implicit fallback alignment is removed; alignment must be explicit in the quirk record
- Updated first-party quirk examples to `schemaVersion: 2`.

## 2026-02-23

### `webgpu-spec-coverage` status semantics expanded

- Updated `config/webgpu-spec-coverage.schema.json` to add `status: "tracked"`.
- `tracked` is used for spec-universe feature inventory entries that are explicitly covered as config/audit inventory contracts, but are not yet runtime-semantic implementations.
- Migrated Dawn feature-inventory rows in `config/webgpu-spec-coverage.json` from `planned` to `tracked` for entries sourced from `bench/vendor/dawn/src/dawn/dawn.json` feature inventory.

### `webgpu-spec-coverage` tracked inventory closure

- Closed remaining tracked/blocked feature inventory rows by promoting all `feature_*` entries to explicit implemented inventory contracts.
- Feature inventory implementation contract now requires:
  - Dawn feature-enum source (`bench/vendor/dawn/src/dawn/dawn.json` `feature name` values).
  - Zig runtime capability introspection path (`wgpuAdapterGetFeatures` / `wgpuDeviceGetFeatures` via `runtime/zig/src/wgpu_capability_runtime.zig`).
  - benchmark mapping contract via capability introspection workloads (`capability_introspection`, `capability_introspection_500`).
- Current closure totals in `config/webgpu-spec-coverage.json`:
  - `implemented=103`
  - `blocked=0`
  - `tracked=0`
  - `planned=0`

### `webgpu-spec-index` backend checklist schema

- Updated `config/webgpu-spec-index.schema.json` from schema version `1` to `3`.
- `config/webgpu-spec-index.jsonl` (migrated from `.json` in schema v4) is generated from the official `@webgpu/types` API surface, carrying the canonical per-backend checklist for `metal`, `vulkan`, `d3d12`, and `browser`.
- Added root-level checklist metadata:
  - `checklist.backends`
  - `checklist.implementationStatusVocabulary`
  - `checklist.correctnessStatusVocabulary`
  - `checklist.performanceStatusVocabulary`
  - `checklist.defaultImplementationStatus`
  - `checklist.defaultCorrectnessStatus`
  - `checklist.defaultPerformanceStatus`
  - `checklist.notes`
- Added per-entry backend checklist objects to:
  - every interface
  - every interface member
  - every string union
  - every string-union value
- Each backend checklist object now carries distinct evidence lanes:
  - `implementation`
  - `correctness`
  - `performance`
- Initial checklist state defaults each evidence lane to `unreviewed` until an audited status plus `sourceRefs` are attached.
- Generator preservation contract:
  - `bench/generate_webgpu_spec_index.py` now preserves existing checklist annotations across regeneration from `@webgpu/types` by matching interface names, member keys, string-union names, and string-union value names.

### Dawn autodiscovery map coverage for extended comparable matrix

- Extended `bench/native-compare/dawn_benchmark_adapter.py` `AUTODISCOVER_WORKLOAD_PATTERNS` to cover all workload IDs in `bench/workloads.amd.vulkan.extended.json` (including `p0_*`, `p1_*`, `p2_*`, macro contracts, and added Dawn suites).
- This removes local strict-run failures caused by missing autodiscovery patterns for full39 execution passes.

### `substantiation-policy` contract introduced

- Added `config/substantiation-policy.schema.json` and `config/substantiation-policy.json`.
- The policy defines machine-checked release evidence minimums:
  - `minReports`
  - `minClaimableComparableReports`
  - `requiredComparisonStatus`
  - `requiredClaimStatus`
  - `minUniqueLeftProfiles`
  - optional `targetUniqueLeftProfiles`
- `bench/substantiation_gate.py` consumes this policy for repeated-window/report substantiation checks.
- `bench/schema_gate.py` now validates the substantiation policy contract as part of blocking schema checks.

## 2026-02-24

### Dispatch-window timing selection hardening

- `bench/native-compare/modules/timing_selection.py` now applies tiny dispatch-window rejection globally (not only submit-only/no-dispatch traces) when both are true:
  - dispatch window `< timingSelection.minDispatchWindowNsWithoutEncode`
  - dispatch-window coverage `< timingSelection.minDispatchWindowCoveragePercentWithoutEncode` of `executionTotalNs`
- when rejected, timing selection falls back to `doe-execution-total-ns` and records `dispatchWindowSelectionRejected` metadata.

### AMD extended workload contract correction for concurrent execution

- `bench/workloads.amd.vulkan.extended.json` was updated to keep strict claim lanes apples-to-apples:
  - `surface_presentation` is now directional-only (`comparable=false`)
  - added `compute_concurrent_execution_single` as the strict comparable mapping for Dawn `ConcurrentExecutionTest ... RunSingle`
- new command/kernel artifacts were added for the replacement comparable contract:
  - `examples/concurrent_execution_single_commands.json`
  - `bench/kernels/concurrent_execution_runsingle_u32.wgsl`
- `bench/dawn_workload_map.amd.extended.json` now includes filter mapping for `compute_concurrent_execution_single`.

### Apples-to-apples enforcement hardening

- `bench/workloads.amd.vulkan.extended.json` now reclassifies directional/proxy mappings as non-comparable (`comparable=false`, `benchmarkClass=directional`) for strict claim lanes.
- AMD Vulkan macro rows that still declared `benchmarkClass=comparable` while remaining `comparable=false`
  (`render_pixel_local_storage_barrier_500`, `resource_table_immediates_500`) are now corrected to `benchmarkClass=directional` across the affected AMD extended / Doe-vs-Doe lanes.
- `bench/generate_backend_workloads.py` now validates `benchmarkClass`/`comparable` consistency at the catalog layer so generated workload files cannot drift into compare-loader rejection again.
- `bench/native-compare/compare_dawn_vs_doe.py` now rejects workload contract entries that set `comparable=true` while:
  - description is directional (`description` starts with `Directional`)
  - comparability notes explicitly declare closest-proxy mapping (`closest draw-call throughput proxy`)
- strict comparable runs now fail fast when those contract invariants are violated.

### Upload ignore-first scope enforcement

- `bench/native-compare/modules/comparability.py` and `bench/native-compare/modules/claimability.py` now enforce ignore-first timing scope consistency:
  - `uploadIgnoreFirstAdjustedTimingSource` must resolve to `doe-execution-row-total-ns`
  - base and adjusted ignore-first canonical timing sources must match
- mixed-scope derived upload timings now fail strict comparability and claimability checks.

### Machine-checkable comparability obligations

- `bench/native-compare/modules/comparability.py` now emits machine-checkable obligation artifacts per workload in report field `comparability`:
  - `obligationSchemaVersion`
  - `obligations[]` entries (`id`, `blocking`, `applicable`, `passes`, `details`)
  - `blockingFailedObligations` / `advisoryFailedObligations`
- workload comparability is now computed from blocking-obligation failures (`blockingFailedObligations`), preserving legacy `reasons` as human-readable diagnostics.
- `bench/claim_gate.py` and `bench/check_full39_claim_readiness.py` now require valid comparability obligation artifacts and fail when blocking obligations fail in claim/comparable lanes.

### Comparability obligation contract + parity fixtures

- Added canonical obligation-ID contract:
  - `config/comparability-obligations.schema.json`
  - `config/comparability-obligations.json`
- Added comparability parity fixture contract and data:
  - `config/comparability-obligation-fixtures.schema.json`
  - `bench/comparability_obligation_fixtures.json`
- `bench/schema_gate.py` now validates both contracts as part of blocking schema checks.
- Added verification-lane parity gate:
  - `bench/comparability_obligation_parity_gate.py`
  - validates Python fixture evaluation (`evaluate_comparability_from_facts`) and Lean/Python obligation ID alignment.
- Added Lean parity fixture proofs:
  - `pipeline/lean/Fawn/ComparabilityFixtures.lean`
  - compiled by `pipeline/lean/check.sh`.
- `bench/claim_gate.py` now validates report obligation IDs against `config/comparability-obligations.json` (canonical ID contract) in addition to schema-version checks.
- `bench/run_blocking_gates.py` and release orchestrators now support `--with-comparability-parity-gate` to wire this verification step into automated gate runs.

### Report anti-staleness metadata

- `bench/native-compare/compare_dawn_vs_doe.py` now emits workload contract metadata in reports:
  - `workloadContract.path`
  - `workloadContract["sha256"]`
- `bench/check_full39_claim_readiness.py` now verifies:
  - exact comparable workload ID set against current workload contract
  - workload contract hash match when report metadata is present

### Dawn filter-map fallback removal

- `bench/native-compare/dawn_benchmark_adapter.py` no longer accepts implicit/default workload
  map fallback resolution for Dawn gtest filters.
- `--dawn-filter-map` now resolves only explicit `filters.<workload>` entries or
  explicit `--dawn-filter`; unresolved workloads fail fast.
- `bench/dawn_workload_map*.json` contract files were updated to remove
  `filters.default` fallback entries.

### Report conformance + workload-hash enforcement hardening

- `bench/claim_gate.py` now enforces canonical obligation contract IDs from
  `config/comparability-obligations.json` plus optional strict
  workload-contract hash/path and comparable workload ID-set checks.
- `bench/run_release_pipeline.py` and `bench/run_blocking_gates.py` now pass
  strict workload contract hash/ID requirements into claim-gate release lanes.
- `bench/build_baseline_dataset.py` and
  `bench/build_test_inventory_dashboard.py` now include only conformant compare
  reports (`schemaVersion=4`, canonical comparability obligations, and
  workload-contract hash/path consistency).
- `bench/report_conformance.py` was added as the shared conformance/hash
  validation module for report-ingestion tooling.

### Track B claim-row hash-link and rehearsal artifact enforcement

- `bench/native-compare/compare_dawn_vs_doe.py` claim-row linkage fields are now validated by
  gate logic, not report-emission only:
  - per-workload `claimRowHash`
  - report-level `claimRowHashChain`
- `bench/report_conformance.py` now includes claim-row hash-link validation helpers:
  - validates chain continuity (`previousHash` -> `hash`)
  - recomputes row hashes deterministically from canonical JSON context
  - verifies context linkage to:
    - `workloadContract["sha256"]`
    - `configContract["sha256"]`
    - `benchmarkPolicy["sha256"]`
    - workload `traceMetaHashes` (`left`/`right`)
- `bench/claim_gate.py` now enforces those hash-link invariants and fails
  claim lanes when linkage is missing/invalid.
- `bench/claim_gate.py` now independently validates claim tails and floors for
  claimable release lanes:
  - per-workload timed sample floors
  - required positive deltas from policy (`p50/p95/p99` for release)
- Added `bench/build_claim_rehearsal_artifacts.py` to emit required
  machine-readable rehearsal artifacts from a compare report:
  - claim gate result
  - tail-health table
  - timing-invariant audit
  - contract-hash manifest
  - rehearsal manifest linking all artifact paths
- `bench/run_release_pipeline.py` now runs this artifact builder by default when
  `--with-claim-gate` is enabled (disable with
  `--no-with-claim-rehearsal-artifacts`).
- `bench/run_release_claim_windows.py` now forwards that release-pipeline
  rehearsal-artifact behavior per window by default.

### Claim cycle contract + rollback gate enforcement

- Added active cycle-lock contract and schema:
  - `config/claim-cycle.schema.json`
  - `config/claim-cycle.active.json`
- `bench/schema_gate.py` now validates the active cycle contract as a blocking schema target.
- Added `bench/cycle_gate.py` for claim-lane governance checks:
  - validates cycle contract hash locks against on-disk contracts
  - validates comparable/directional workload partition against active workload contract
  - validates claim report conformance and hash-link consistency
  - evaluates rollback criteria and artifact namespace policy
- `bench/run_release_pipeline.py` now runs `cycle_gate.py` by default when
  `--with-claim-gate` is enabled (disable only for diagnostics via
  `--no-with-cycle-gate`).
- `bench/run_release_claim_windows.py` now forwards cycle-gate controls per
  window by default.

### Vulkan app lane runtime routing update (2026-02-26)

- Added backend lane `vulkan_doe_app` to the backend policy contract.
- Updated implicit native Vulkan lane selection to `vulkan_doe_app` in `runtime/zig/src/execution.zig`.
- Extended `config/backend-runtime-policy.json` with `vulkan_doe_app` as `doe_vulkan` with `allowFallback=false` and `strictNoFallback=true`.
- `config/backend-cutover-policy.json` remains targeted to Metal app cutover (`metal_doe_app` -> `doe_metal`); Vulkan app routing is controlled by runtime lane policy.
- Kept `vulkan_dawn_release` as the Dawn baseline benchmark/claim lane for apples-to-apples comparative evidence.
- All Vulkan compare config command templates now pin an explicit `--backend-lane` so strict AMD Dawn-baseline reports remain on `vulkan_dawn_release` while local Vulkan presets remain on their intended local lanes.
- Vulkan backend execution no longer delegates command execution to `webgpu.WebGPUBackend.executeCommand(...)`; `runtime/zig/src/backend/vulkan/mod.zig` now runs through Vulkan module contracts and emits native execution results directly.
- Added Vulkan shader-manifest telemetry path/hash emission in `runtime/zig/src/backend/vulkan/vulkan_runtime_state.zig` and backend telemetry refresh in `runtime/zig/src/backend/backend_runtime.zig` for strict shader-artifact gate coverage.
- Retired runtime rollback switch activation in backend policy loading; backend selection no longer honors `FAWN_BACKEND_SWITCH`.

### Metal end-to-end runtime closure (2026-02-26)

- `runtime/zig/src/backend/metal/mod.zig` no longer delegates command execution to `webgpu.WebGPUBackend.executeCommand(...)`; `doe_metal` now executes through metal module contracts and returns native execution results directly.
- Removed `catch unreachable` behavior from Metal backend wrappers; queue/upload/timestamp policy knobs are now explicit backend fields.
- Metal shader manifest emission is now enforced on successful command routing paths so strict shader artifact gates can validate manifest linkage in strict lanes.
- `bench/workloads.apple.metal.smoke.json` `compute_workgroup_atomic_1024.commandsPath` corrected from missing `examples/dispatch_commands.json` to `examples/workgroup_atomic_commands.json`.
- Backend selection now resolves directly from strict lane policy + profile constraints with no runtime rollback override path.

### Backend lane canonical rename (2026-02-26)

Canonical lane names are now:

- `metal_doe_app` (legacy alias: `metal_doe_app`)
- `metal_doe_directional` (legacy alias: `metal_doe_directional`)
- `metal_doe_comparable` (legacy alias: `metal_doe_comparable`)
- `metal_doe_release` (legacy alias: `metal_doe_release`)
- `metal_dawn_release` (legacy alias: `metal_dawn_release`)
- `vulkan_doe_app` (legacy alias: `vulkan_doe_app`)
- `vulkan_doe_comparable` (legacy alias: `vulkan_doe_comparable`)
- `vulkan_doe_release` (legacy alias: `vulkan_doe_release`)
- `vulkan_dawn_release` (legacy alias: `vulkan_dawn_release`, compatibility alias: `vulkan_dawn_directional`)
- `d3d12_doe_app` (legacy alias: `d3d12_doe_app`)
- `d3d12_doe_directional` (legacy alias: `d3d12_doe_directional`)
- `d3d12_doe_comparable` (legacy alias: `d3d12_doe_comparable`)
- `d3d12_doe_release` (legacy alias: `d3d12_doe_release`)
- `d3d12_dawn_release` (legacy alias: `d3d12_dawn_release`)

Contract updates in this change:

- `config/backend-runtime-policy.json` lane keys/default lane migrated to canonical names.
- `config/backend-cutover-policy.json` target lane migrated to `metal_doe_app`.
- `config/dropin-abi-behavior.json` lane mode keys migrated to canonical names.
- Runtime telemetry now emits canonical lane names (`backendLane`).
- CLI/runtime parser retains legacy lane aliases for backward compatibility.

### Backend lane map artifact + invariants (2026-02-26)

- Added generated lane-map contract artifact + schema:
  - `config/backend-lane-map.json`
  - `config/backend-lane-map.schema.json`
- Added generator utility:
  - `bench/generate_backend_lane_map.py --policy config/backend-runtime-policy.json --out config/backend-lane-map.json`
- `bench/schema_gate.py` now enforces lane-map invariants against runtime/cutover policy:
  - `laneToBackend` must exactly match `backend-runtime-policy.json` lane defaults
  - `backendToLanes` must exactly match reverse grouping from lane defaults
  - `defaultLane` and cutover target lane must resolve to valid runtime lanes
  - cutover `defaultBackend` must match mapped backend for cutover target lane
- `config/schema-targets.json` now includes lane-map schema validation as a blocking schema target.

### Metal Dawn-baseline lane addition (2026-02-26)

- Added `metal_dawn_release` as a first-class backend lane in `config/backend-runtime-policy.json`.
- `metal_dawn_release` maps to `dawn_delegate` (`allowFallback=true`, `strictNoFallback=false`) for explicit Metal dawn/baseline runs.
- Runtime lane parsing and telemetry now recognize/emit `metal_dawn_release`:
  - Zig parser accepts `metal_dawn_release` and `metal-dawn-release`.
  - backend telemetry `backendLane` uses canonical lane strings.
- Added `metal_dawn_release` to generated lane-map artifact `config/backend-lane-map.json` (both `laneToBackend` and `backendToLanes`).
- Added `metal_dawn_release` drop-in behavior ownership mode in `config/dropin-abi-behavior.json` (`dawn_ownership`).
- Release pipeline/gates now infer `metal_dawn_release` when config paths include `.metal.dawn`, and explicit `--local-metal-lane metal_dawn_release` is supported.

### Vulkan local smoke dispatch command-path repair (2026-02-26)

- Updated `bench/workloads.amd.vulkan.smoke.json` `compute_workgroup_atomic_1024.commandsPath` from missing `examples/dispatch_commands.json` to `examples/workgroup_atomic_commands.json`.
- Added compatibility command file `examples/dispatch_commands.json` (kernel-dispatch atomic workload payload) so legacy/manual invocations no longer fail with `FileNotFound`.

### Vulkan timing policy backend-specific upload source allowance (2026-02-26)

- Extended `config/backend-timing-policy.schema.json` to support optional per-backend timing source allowlists via `allowedTimingSourcesByBackendId`.
- Updated upload-domain timing policy in `config/backend-timing-policy.json` to allow `doe-execution-dispatch-window-ns` when sample `backendId` is `dawn_delegate`.
- Updated `bench/vulkan_timing_policy_gate.py` to evaluate allowed timing sources using report sample backend telemetry (`traceMeta.backendId` and fallbacks) so lane-vs-lane Dawn-baseline comparisons validate against explicit policy contract.

### Vulkan timing policy lane-vs-lane fullsuite source alignment (2026-02-26)

- Expanded upload-domain backend-specific timing source allowlist in `config/backend-timing-policy.json` so `doe_vulkan` upload samples may use `doe-execution-dispatch-window-ns` in strict lane-vs-lane reports.
- Expanded render-domain backend-specific timing source allowlist in `config/backend-timing-policy.json` so `dawn_delegate` render samples may use `doe-execution-encode-ns` in strict lane-vs-lane reports.

### Vulkan Doe-vs-Doe strict normalization parity contract (2026-02-26)

- Added a dedicated strict apples-to-apples workload contract for DOE-vs-DOE lane comparisons:
  - `bench/workloads.amd.vulkan.superset.doe-vs-doe.json`
- In that contract, right-side normalization fields are explicitly mirrored from left-side fields for comparable workloads:
  - `rightCommandRepeat`
  - `rightIgnoreFirstOps`
  - `rightUploadBufferUsage`
  - `rightUploadSubmitEvery`
  - `rightTimingDivisor`
- Added strict DOE-vs-DOE normalization symmetry enforcement in `bench/native-compare/compare_dawn_vs_doe.py`:
  - when both command templates target `doe-zig-runtime` and comparability mode is `strict`, comparable workloads must satisfy left/right normalization parity or the run fails fast.
- Added lane-vs-lane full-suite preset using the DOE-vs-DOE parity workload contract:
  - `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.doe-vs-dawn.fullsuite.json`

### Strict timing-scope comparability obligations for Doe-vs-Doe lanes (2026-02-26)

- Expanded comparability contract with strict blocking obligations for timing-scope parity:
  - `left_right_trace_meta_source_match`
  - `left_right_timing_selection_policy_match`
  - `left_right_queue_sync_mode_match`
- Updated obligation sources and parity fixtures:
  - `config/comparability-obligations.json`
  - `pipeline/lean/Fawn/Comparability.lean`
  - `bench/comparability_obligation_fixtures.json`
  - `bench/native-compare/modules/comparability.py`
- Strict comparable runs now fail comparability when left/right timing scope selection diverges, preventing mixed-scope rows from being treated as claimable apples-to-apples evidence.
- Updated `bench/workloads.amd.vulkan.superset.doe-vs-doe.json` to mark current timing-scope-unstable workloads as `comparable=false` (directional-only) for strict DOE-vs-DOE comparable runs until timing-scope parity is stabilized:
  - `render_draw_throughput_baseline`
  - `render_draw_state_bindings`
  - `render_draw_redundant_pipeline_bindings`
  - `render_bundle_dynamic_bindings`
  - `render_bundle_dynamic_pipeline_bindings`
  - `pipeline_async_diagnostics`
  - `resource_table_immediates_500`
  - `render_draw_throughput_200k`
  - `render_multidraw`
  - `render_multidraw_indexed`
  - `render_pixel_local_storage_barrier_500`
  - `render_uniform_buffer_update_writebuffer_partial_single`

### AMD Vulkan extended comparable normalization parity fix (2026-03-06)

- Corrected the strict AMD Vulkan extended comparable workload contract for
  `resource_table_immediates_500` in `bench/workloads.amd.vulkan.extended.json`
  by adding the missing mirrored `rightCommandRepeat=500`.
- This restores strict left/right normalization symmetry for that comparable
  workload so current Dawn-vs-Doe AMD Vulkan matrix reruns can execute instead
  of failing fast during contract validation.

### AMD Vulkan native-supported subset contract tightening (2026-03-06)

- Updated `bench/workloads.amd.vulkan.superset.native-supported.json` so the
  AMD native Vulkan subset no longer marks `resource_table_immediates_500` or
  `surface_presentation` as strict comparable workloads.
- Current native Vulkan execution reports those command classes as unsupported
  (`async_diagnostics` and `surface_lifecycle` respectively), so they remain
  directional-only until the native backend implements them.

### AMD Vulkan strict identity preflight + native-supported strict configs (2026-03-06)

- `bench/preflight_bench_host.py` now probes Doe's selected Vulkan adapter
  ordinal via `doe-zig-runtime --trace-meta`, resolves that ordinal through
  `vulkaninfo --summary`, and fails strict AMD runs unless Doe and Dawn agree on
  vendor/device identity.
- `config/trace-meta.schema.json` now allows explicit Vulkan adapter-selection
  fields for strict evidence artifacts: `adapterOrdinal`, `adapterName`,
  `vendorId`, `deviceId`, `queueFamilyIndex`, and `presentCapable`.
- `config/run-metadata.schema.json` now allows the same adapter-selection data
  under an optional `adapter` object for downstream evidence products.
- `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json` and
  `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json` now point at
  `bench/workloads.amd.vulkan.superset.native-supported.json` so strict AMD
  comparable/release lanes only cite command classes that are currently native
  by contract.

### Vulkan async-diagnostics submode split (2026-03-06)

- `runtime/zig/src/backend/common/capabilities.zig` now treats `async_diagnostics` as
  explicit sub-capabilities instead of one coarse family bucket:
  `async_pipeline_diagnostics`, `async_capability_introspection`,
  `async_resource_table_immediates`, `async_lifecycle_refcount`, and
  `async_pixel_local_storage`.
- Native Vulkan now declares and executes only the honest submodes currently
  supported in `runtime/zig/src/backend/vulkan/mod.zig`:
  `capability_introspection`, `lifecycle_refcount`, and `pipeline_async`.
- Native Vulkan now executes `resource_table_immediates` and
  `pixel_local_storage` through explicit Doe-native emulation paths when the
  workload contract requests `featurePolicy=emulate_when_unavailable`.
- `full` remains explicit unsupported for strict mode, so workload/config
  surfaces cannot overclaim family support from partial implementation.
- AMD Vulkan workload contracts now carry `asyncDiagnosticsMode` where relevant
  so reports/evidence preserve the specific submode rather than only the coarse
  `async_diagnostics` family label.

### Vulkan native headless surface/timestamp follow-up (2026-03-06)

- `runtime/zig/src/backend/vulkan/mod.zig` and
  `runtime/zig/src/backend/vulkan/native_runtime.zig` now execute `surface_create`,
  `surface_capabilities`, `surface_configure`, `surface_acquire`,
  `surface_present`, `surface_unconfigure`, and `surface_release` through a
  native Doe headless surface lifecycle/present path.
- This surface path is native evidence only; AMD workload contracts still keep
  `surface_presentation` directional-only until the benchmark methodology is
  apples-to-apples against Dawn.
- Native Vulkan dispatch now records real GPU timestamps in per-command mode
  when the selected queue family exposes timestamp support; `GpuTimestampMode.require`
  fails fast when strict timestamp policy cannot be satisfied.

### Vulkan large-upload cap removal (2026-03-06)

- Removed the stale `64MB` artificial upload cap from
  `runtime/zig/src/backend/vulkan/native_runtime.zig`.
- Vulkan upload prewarm now uses the full requested upload size when no
  backend-specific cap is configured, matching the large-upload comparable
  contract promotion for `256MB`, `1GB`, and `4GB` workloads.
- Allocation/driver failure now surfaces directly from the Vulkan runtime
  instead of being preclassified as `UnsupportedFeature` by a static cap.

### Benchmark deltaPercent formula drift note (2026-02-26, superseded)

- A temporary migration moved `bench/native-compare/compare_dawn_vs_doe.py` to ratio-style speedup semantics:
  - from `((rightMs - leftMs) / rightMs) * 100`
  - to `((rightMs / leftMs) - 1) * 100`
- This introduced cross-tool inconsistency with other benchmark/report tooling.

### Benchmark deltaPercent convention update (2026-03-02)

- Re-aligned benchmark/report tooling to ratio-style speedup semantics:
  - `((rightMs / leftMs) - 1) * 100`
- Updated:
  - `bench/native-compare/compare_dawn_vs_doe.py`
  - `bench/native-compare/visualize_dawn_vs_doe.py`
  - `bench/native-compare/compare_runtimes.py`
  - `bench/benchmark-writing-guide.md`
  - `bench/README.md`
- `deltaPercentConvention` now consistently declares:
  - `baseline=left`
  - positive = left faster
  - negative = left slower
- Interpretation target:
  - `+300%` means `4x` faster

### Dawn-vs-Doe strict timing-basis clarification (2026-03-02)

- Default strict timing basis for cross-runtime Dawn-vs-Doe lanes is `operation`.
- Removed forced strict `process-wall` guard in `bench/native-compare/compare_dawn_vs_doe.py`.
- Updated compare presets back to `comparability.requireTimingClass=operation`.
- Documentation now explicitly separates benchmark intents:
  - `apples-to-apples` (comparable contract lanes)
  - `doe-advantage` (directional optimized lanes)
  while keeping the same timing basis rule for fairness.

### First-class Doe-advantage workload cohort (2026-03-20)

- `compare_dawn_vs_doe.py` now accepts `--workload-cohort doe-advantage`.
- `doe-advantage` selects workload contracts with `benchmarkClass=directional` and requires `includeNoncomparableWorkloads=true`.
- compare artifacts now surface:
  - top-level `benchmarkIntent`
  - per-row `benchmarkClass`
  - per-row `directionalReason`
  - summary `benchmarkClassCounts` and `directionalReasonCounts`
- workload contracts may now declare `directionalReason` to distinguish:
  - `dawn_limit`
  - `dawn_missing_contract`
  - `dawn_no_execution`
  - `path_asymmetry`
  - `host_instability`
  - `methodology_gap`
  - `other`
- new first-class backend presets now exist:
  - `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.doe-advantage.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.local.metal.doe-advantage.json`
- AMD Vulkan large matvec rows (`compute_matvec_32768x2048_f32`, `_swizzle1`, `_workgroupshared_swizzle1`) are no longer strict comparable on the current host contract. They now live in the governed `doe-advantage` cohort because Dawn strict preflight rejects their 256 MB storage binding.

### Comparability obligation contract externalization (2026-03-14)

- `config/comparability-obligations.json` moved from `schemaVersion=1` ID-only format to `schemaVersion=2` semantic contract format.
- The new contract now contains:
  - `facts`
  - ordered `obligations`
  - per-obligation `blocking`, `applicableWhen`, and `passesWhen` fields
- Python comparability fixture evaluation now interprets the v2 contract directly.
- Lean comparability IDs/facts/rule application are now generated from the same contract via `pipeline/lean/generate_comparability_contract.py`.
- Downstream report/gate conformance loaders accept both v1 and v2 obligation contracts so historical reports remain auditable while new runs use the semantic contract.

### Doe-vs-Doe timing-source parity stabilization for strict comparable runs (2026-02-26)

- Updated timing selection to prefer `doe-execution-total-ns` when execution evidence is present and GPU timestamp timing is unavailable.
- Removed render-domain encode-only timing override from `bench/native-compare/compare_dawn_vs_doe.py` so left/right timing selection no longer diverges by side-specific render override policy.
- Restored the 12 previously directionalized DOE-vs-DOE Vulkan workloads in `bench/workloads.amd.vulkan.superset.doe-vs-doe.json` to `comparable=true` after timing-source parity stabilization.

### Doe-vs-Doe strict comparability hardening for execution shape + upload timing scope (2026-02-26)

- Expanded comparability contract with a new blocking execution-shape obligation:
  - `left_right_execution_shape_match`
- This obligation compares sampled `executionDispatchCount`, `executionRowCount`, and `executionSuccessCount` tuples across sides and fails strict comparability on divergence.
- Updated obligation contract and parity fixtures:
  - `config/comparability-obligations.json`
  - `pipeline/lean/Fawn/Comparability.lean`
  - `bench/comparability_obligation_fixtures.json`
  - `config/comparability-obligation-fixtures.schema.json`
  - `bench/native-compare/modules/comparability.py`
- Updated DOE timing-source selection for upload workloads:
  - `bench/native-compare/modules/timing_selection.py` now prefers `doe-execution-row-total-ns` (trace row execution durations) for upload-domain operation timing when execution evidence is present.
  - This removes strict upload lane drift where `doe-execution-total-ns` could violate upload timing policy allowances and mixes setup/runtime scope in per-op upload comparisons.

### Canonical backend workload catalog and package workload alias normalization (2026-03-09)

- Added canonical backend workload catalog:
  - `bench/backend-workload-catalog.json`
  - `config/backend-workload-catalog.schema.json`
  - generator: `bench/generate_backend_workloads.py`
- Backend lane files under `bench/workloads*.json` are now generated execution contracts derived from the canonical catalog instead of the intended hand-authored source of truth.
- Added canonical cross-surface workload alias bridge:
  - package registry: `bench/workload-registry.json`
  - schema: `config/workload-registry.schema.json`
- Node/Bun package workload factories now import canonical workload metadata from the registry, and package compare reports emit `canonicalWorkloadId`.
- Benchmark cube normalization now maps package aliases (for example `buffer_upload_1kb`) to canonical workload IDs (`upload_write_buffer_1kb`) while preserving raw `sourceWorkloadId` in cube rows.

### First governed D3D12 backend workload contracts (2026-03-09)

- Added generated D3D12 workload execution contracts sourced from the canonical backend workload catalog:
  - `bench/workloads.local.d3d12.smoke.json`
  - `bench/workloads.local.d3d12.extended.json`
- Added first governed Windows D3D12 compare configs:
  - `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.smoke.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.extended.comparable.json`
  - release scaffold: `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.release.json`
- Added Windows-host D3D12 preflight contract:
  - `bench/preflight_d3d12_host.py`
- Added Windows handoff runner:
  - `bench/run_local_d3d12_lane.py`
- `bench/run_blocking_gates.py` now runs both `python3 bench/generate_backend_workloads.py --verify` and `python3 bench/test_backend_workload_catalog.py` as blocking gates so the backend workload catalog remains authoritative and the D3D12 lane invariants stay covered.
- Scope boundary for this first governed D3D12 lane:
  - strict comparable coverage is limited to compute, upload, pipeline, and `p0-resource`
  - render and texture contracts remain out of scope until native D3D12 coverage expands
- Benchmark cube placeholders now annotate governed-but-unevidenced `windows_d3d12` cells as `contract exists, evidence missing` instead of leaving them as generic empty cells.

### Vulkan surface tone-mapping command payload (2026-03-18)

- `runtime/zig/src/model_webgpu_types.zig` `SurfaceConfigureCommand` now carries
  `tone_mapping_mode` in addition to `alpha_mode` / `present_mode`.
- `runtime/zig/src/command_json_raw.zig` and
  `runtime/zig/src/command_json_extra.zig` now accept
  `toneMappingMode` / `tone_mapping_mode` on `surface_configure` payloads.
- `runtime/zig/src/backend/vulkan/native_runtime.zig` and
  `runtime/zig/src/backend/vulkan/vulkan_surface.zig` now consume that field
  during swapchain format selection so `extended` tone mapping prefers
  extended-sRGB Vulkan surface formats when the platform exposes them.
### Host-scoped package execution unsupported policy

- Added `config/package-execution-policy.json` with schema
  `config/package-execution-policy.schema.json` as the config-backed source of
  truth for host/provider/workload package lanes that must fail fast as
  explicit unsupported execution instead of crashing inside a provider process.
- `bench/executors/node-webgpu/executor.js` now resolves that policy before
  runtime bring-up and emits deterministic unsupported artifacts when a matching
  package lane is classified unsupported on the current host.
