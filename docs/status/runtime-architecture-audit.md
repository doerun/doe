# Runtime architecture audit

## Current boundary

The [architecture](../architecture.md), applicable component charters, and
[source-layout manifest](../../runtime/zig/source-layout.json) own implementation
boundaries. The [generated source map](../../runtime/zig/src/README.md) and
[reachability report](../../runtime/zig/reports/architecture/reachability-views.json)
classify source and consumers. Import and size checks establish structural
constraints, not complete code review, optimal organization, or hardware support.

The canonical-command migration is complete. Native WebGPU objects and drop-in
FFI retain their separately governed execution paths. Keep forbidden legacy
imports guarded and module-incubation results distinct from physical execution.
An exact consumer audit is required before removing an apparently unused module
or compatibility facade.

## Current work selection

The [attachment admission checkpoint](../../reports/maintenance/20260928-attachment-admission/README.md)
rejects incompatible ordinary Vulkan pass/pipeline layouts before publication.
Native objects own validation; recorded leases and queue preflight preserve
caller-release and explicit-destruction distinctions. Unsupported attachment
topologies fail explicitly. Backend command-oriented admission and surface
synchronization remain separate obligations.

The [render recording checkpoint](../../reports/maintenance/20260928-render-recording/README.md)
now gives the live draw recorder typed borrowed dependencies. Allocation, image
transitions and completion remain with the render owner. Public indexed draws
also consume the native adapter's buffer identity correctly. Physical query and
pixel checks and injected completion failures cover this boundary; broader setup,
command-oriented attachment admission and surface synchronization remain open.

The [production query checkpoint](../../reports/maintenance/20260928-production-query/README.md)
repairs pool type, reset placement, and logical visibility across native draws.
Public recording, resolve/readback, pixel oracles, query reuse and caller release
pass on physical Vulkan. Validation layers are unavailable; this is scoped
correctness evidence, not release qualification. The compiler ownership
batch is now closed with its separately retained evidence; completed bundle and
build-recipe repairs remain closed.


[`config/zig-review-plan.json`](../../config/zig-review-plan.json) is the sole
schedule for bounded Zig quality batches. Display it with
`python3 runtime/zig/tools/review_log.py --next`. The
[review ledger](../../runtime/zig/reviews/README.md) owns findings and completion
rules; its [log](../../runtime/zig/reviews/log.json) is append-only and its
[queue](../../runtime/zig/reviews/queue.tsv) is coverage inventory. Historical
"next file" instructions do not override the plan. Guidance changes reopen
coverage under existing hashes; never renew reviews without examination.

The [render ownership evidence](../../reports/maintenance/20260927-quality-planning/README.md)
supports retained index storage and safe failed-wait retirement. Surface synchronization and command-oriented attachment admission remain open.
The [bundle rejection evidence](../../reports/maintenance/20260928-render-rejection/README.md)
supports typed failure, no partial submission, native cleanup, and subsequent
rendering in the standalone replay helper. That helper has no current production
caller; its correction does not qualify ordinary native WebGPU bundle execution. The plan selects the next repair and its stopping condition.
The [compiler and allocation ownership evidence](../../reports/maintenance/20260927-implementation-quality/README.md)
supports explicit compiler requests/diagnostics, IR loop eligibility, and a typed
completed-allocation cache. The [SPIR-V ownership checkpoint](../../reports/maintenance/20260928-spirv-ownership/README.md)
now owns cache storage and invalidation explicitly and keeps reference queries in
IR, with preserved selected artifacts and scoped cost observations. These
checkpoints grant no whole-file, directory, application performance, or release
qualification. Subsequent interface work must identify its actual consumer,
complete execution path and observable consequence before selecting a change.

## Open obligations and evidence owners

These findings remain obligations until an explicit disposition supersedes them.
They do not independently schedule another batch. Reconfirm older findings against
current source before implementing a correction.

| Area | Remaining obligation | Retained owner or evidence |
| --- | --- | --- |
| Vulkan resources and completion | Review upload completion/retry, aggregate retention, sampler/presentation semantics, capability admission, error taxonomy, receipt accounting, and broad resource dependencies alongside the render findings above. | [Upload audit](../../bench/out/maintenance/20260923-vulkan-upload-audit/README.md), [Vulkan file conclusions](../../bench/out/maintenance/20260923-vulkan-audit/file-reviews.json), [port examination](../../bench/out/maintenance/20260920-vulkan-review/file-reviews.json) |
| Metal lifecycle and resources | Reentrant teardown, void encoder error boundaries, aggregate retention, binding/copy/query/render semantics, cache identity and native callback qualification need their own dispositions and physical acceptance. Host checks do not qualify Apple execution. | [Wait contract](../metal-command-waits.md), [notification checkpoint](../../bench/out/maintenance/20260920-metal-notification/README.md), [resource findings](../../bench/out/maintenance/20260920-zig-metal-sampler-resource/README.md), [port findings](../../bench/out/maintenance/20260920-zig-metal-ports-audit/README.md) |
| D3D12 and common backend paths | Native binding/copy/query/presentation and completion findings require current review; cross-compilation does not establish Windows execution or timestamp accuracy. | [Backend findings](../../bench/out/maintenance/20260919-zig-batch32/README.md), [timestamps](../../bench/out/maintenance/20260919-zig-d3d12-timestamps/README.md), [common backend](../../bench/out/maintenance/20260919-zig-common-audit/README.md) |
| Review completeness | Complete file, directory, relationship, and execution-path passes independently. Supporting caller edits, structural gates, and naming cleanup confer no automatic review credit. | [Review ledger](../../runtime/zig/reviews/README.md) |
| Build measurements | The stock leaf-backend recipe targets the current format owner. Keep the earlier failed recipe and scoped compiler replacement separate from the complete profile rerun; timing remains diagnostic. | [Recipe and full-profile evidence](../../reports/maintenance/20260928-render-rejection/README.md), [build measurement config](../../config/zig-build-measurements.json) |
| Recomposition and ABI | Symbol-scoped approval and source digests remain required. Physical AMD Vulkan, Windows D3D12, and browser promotion require receipts bound to the frozen release candidate. | [ABI approval](../../runtime/zig/reports/recomposition/abi-contract-approval.json), [backend status](runtime-backends-and-bench.md) |
| Further consolidation | Consumer-aware review remains for test-only compatibility aggregators, TSIR emitter identity/selection, backend artifact/timing, and module request parsing. Preserve platform-specific mechanics and require semantic tests before merging owners. | [Architecture reports](../../runtime/zig/reports/architecture/), [source layout](../../runtime/zig/source-layout.json) |

## Python sharding advisories

The canonical Zig size policy remains blocking through
`runtime/zig/source-layout.json`. The repository-level file-size gate now uses
that contract directly and treats Python files above the review threshold as
tracked architecture advisories. It ignores generated output, virtual
environments, vendored trees, and package installations rather than counting
them as Doe source.

The current advisory owners and next semantic split targets are:

- Browser-release evidence owner: receipt validation now belongs to
  `bench/browser/release/`, shared by claim admission and readiness reporting.
  Execution, comparison, proof-page, gallery, and artifact checks have narrow
  owners; the existing command and receipt contracts remain unchanged.
  Next split targets are claim admission, proof-surface inspection,
  runtime-frontier bundle validation, and their fixture-heavy tests. This covers
  `bench/gates/claim_index_browser_release.py`,
  `bench/gates/claim_index_browser_release_proof.py`,
  `bench/tools/check_browser_published_proof_surface.py`,
  `bench/tools/check_browser_release_artifact_bundle.py`, and the matching
  browser release/frontier tests.
- Replacement-readiness owner: split readiness report construction and tests
  into backend, package, browser, CTS, ecosystem, and claim-summary sections.
  This covers `bench/tools/build_dawn_replacement_readiness_report.py` and
  `bench/tests/test_dawn_replacement_readiness_report.py`.
- Benchmark orchestration owner: separate argument families from profile and
  gate assembly in `bench/runners/blocking_gates_args.py`; separate Tint
  compilation setup, execution, comparison, and receipt emission in
  `bench/native-compare/compare_doe_vs_tint_compilation.py` and
  `bench/tools/check_tint_compiler_frontier_bundle.py`.
- Benchmark comparability owner: extract package mode, plan identity, and
  readback-scope assessment from `bench/native_compare_modules/compare_assessment.py`
  into a focused package-assessment module. Preserve obligation IDs and strict
  failure behavior; the corresponding regression fixtures own acceptance.
- Ecosystem and Node evidence owner: split registry parsing, contract
  validation, and receipt projection in `bench/lib/ecosystem_registry.py`;
  split the Node executor tests by adapter identity, package execution,
  readback, and failure taxonomy.
- Cerebras runner owner: continue the already tracked splits of manifest
  probing, dense-tile materialization, transcript execution, layer-block
  smoke, scheduler readiness, and their fixture-heavy tests by launch,
  artifact, receipt, and timeout responsibility.

The live gate output is the source of truth for which files currently trigger
these advisories. A follow-up closes only when the named responsibility has
moved to a focused module and the original file falls below the review signal;
line-only sharding is not sufficient.

## History

The [previous architecture status snapshot](archive/2026-09-27-runtime-architecture-audit.md)
preserves implementation checkpoints, original next actions, command/snapshot
repairs, quirk preparation evidence, and earlier archive references. The
unfinished findings above remain live; moving their supporting narrative does
not close them.
