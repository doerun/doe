# Doe status: runtime backends and benchmark lanes

This is a live topical status shard. Follow the shared shard policy in
[`README.md`](README.md).

## 2026-05-27 — Browser derived artifacts reject duplicate IDs

Canvas/WebGPU fusion, GPU scheduler, WebGPU effect, and local-AI workload
checkers now reject duplicate IDs before building reference sets. Ambiguous
surface, node, work-class, pipeline, probe, and workload references can no
longer pass structural checks.

Touched:

- `browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py`
- `browser/chromium/scripts/check-browser-gpu-scheduler.py`
- `browser/chromium/scripts/check-browser-webgpu-effect-experiment.py`
- `browser/chromium/scripts/check-browser-local-ai-workloads.py`
- `bench/tests/test_browser_canvas_webgpu_fusion.py`
- `bench/tests/test_browser_gpu_scheduler.py`
- `bench/tests/test_browser_webgpu_effect_experiment.py`
- `bench/tests/test_browser_local_ai_workloads.py`
- `browser/chromium/contracts/browser-canvas-webgpu-fusion.contract.md`
- `browser/chromium/contracts/browser-gpu-scheduler.contract.md`
- `browser/chromium/contracts/browser-webgpu-effect-experiment.contract.md`
- `browser/chromium/contracts/browser-local-ai-workloads.contract.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py browser/chromium/scripts/check-browser-gpu-scheduler.py browser/chromium/scripts/check-browser-webgpu-effect-experiment.py browser/chromium/scripts/check-browser-local-ai-workloads.py bench/tests/test_browser_canvas_webgpu_fusion.py bench/tests/test_browser_gpu_scheduler.py bench/tests/test_browser_webgpu_effect_experiment.py bench/tests/test_browser_local_ai_workloads.py`
- `python3 browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py --probe examples/browser-canvas-webgpu-fusion.sample.json --json`
- `python3 browser/chromium/scripts/check-browser-gpu-scheduler.py --probe examples/browser-gpu-scheduler.sample.json --json`
- `python3 browser/chromium/scripts/check-browser-webgpu-effect-experiment.py --experiment examples/browser-webgpu-effect-experiment.sample.json --json`
- `python3 browser/chromium/scripts/check-browser-local-ai-workloads.py --workloads examples/browser-local-ai-workloads.sample.json --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_canvas_webgpu_fusion.py bench/tests/test_browser_gpu_scheduler.py bench/tests/test_browser_webgpu_effect_experiment.py bench/tests/test_browser_local_ai_workloads.py -q`

## 2026-05-27 — Browser projection manifests use repo-relative sources

The browser benchmark superset checker now rejects absolute or
parent-traversal `sourceWorkloadsPath` and `rulesPath` values in projection
manifests before hashing the referenced files. The projection-manifest schema
now carries the same repo-relative path boundary.

Touched:

- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `browser/chromium/bench/projection-manifest.schema.json`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `browser/chromium/bench/README.md`
- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `bench/README.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-benchmark-superset.py bench/tests/test_browser_benchmark_superset_checker.py`
- `python3 browser/chromium/scripts/check-browser-benchmark-superset.py --require-promotion-approvals --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_benchmark_superset_checker.py -q`

## 2026-05-27 — Browser workflow approvals require contract-owner coverage

Browser workflow governance now requires the workflow manifest and promotion
approval artifact to agree exactly on required promotion roles, including the
module-contract owner. The standalone workflow checker, promotion-approval
cross-check, and layered superset checker now reject manifests that drop a
required approval role while the approvals artifact still lists it.

Touched:

- `browser/chromium/scripts/check-browser-workflow-manifest.py`
- `browser/chromium/scripts/check-browser-promotion-approvals.py`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `browser/chromium/bench/workflows/browser-workflow-manifest.json`
- `browser/chromium/bench/workflows/browser-workflow-manifest.schema.json`
- `browser/chromium/bench/workflows/browser-promotion-approvals.schema.json`
- `bench/tests/test_browser_workflow_governance.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `browser/chromium/bench/README.md`
- `browser/chromium/chromium-bringup.md`
- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `bench/README.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-workflow-manifest.py browser/chromium/scripts/check-browser-promotion-approvals.py browser/chromium/scripts/check-browser-benchmark-superset.py bench/tests/test_browser_workflow_governance.py bench/tests/test_browser_benchmark_superset_checker.py`
- `python3 browser/chromium/scripts/check-browser-workflow-manifest.py --manifest browser/chromium/bench/workflows/browser-workflow-manifest.json --json`
- `python3 browser/chromium/scripts/check-browser-promotion-approvals.py --approvals browser/chromium/bench/workflows/browser-promotion-approvals.json --workflows browser/chromium/bench/workflows/browser-workflow-manifest.json --json`
- `python3 browser/chromium/scripts/check-browser-benchmark-superset.py --require-promotion-approvals --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_workflow_governance.py bench/tests/test_browser_benchmark_superset_checker.py -q`

## 2026-05-27 — Browser milestone evidence paths are repo-relative

The browser milestone checker now rejects absolute or parent-traversal evidence
paths before checking local files. Milestone governance can no longer use a
manifest evidence row to inspect paths outside the repo while reporting local
browser-lane evidence coverage.

Touched:

- `browser/chromium/scripts/check-browser-milestones.py`
- `bench/tests/test_browser_workflow_governance.py`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-milestones.py bench/tests/test_browser_workflow_governance.py`
- `python3 browser/chromium/scripts/check-browser-milestones.py --manifest browser/chromium/bench/workflows/browser-milestones.json --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_workflow_governance.py bench/tests/test_run_blocking_gates_wiring.py -q`

## 2026-05-27 — Browser unsupported taxonomy checker enforces row semantics

The browser unsupported/fallback reason taxonomy checker now validates reason
code shape, allowed categories, allowed capabilities, allowed statuses, unique
capability/status lists, category/status consistency, note presence, and the
boundary that non-visible reason codes remain diagnostic-only.

Touched:

- `bench/tools/check_browser_unsupported_reason_taxonomy.py`
- `bench/tests/test_browser_unsupported_reason_taxonomy.py`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/check_browser_unsupported_reason_taxonomy.py bench/tests/test_browser_unsupported_reason_taxonomy.py`
- `python3 bench/tools/check_browser_unsupported_reason_taxonomy.py --taxonomy config/browser-unsupported-reason-taxonomy.json --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_unsupported_reason_taxonomy.py bench/tests/test_browser_fallback_explanations.py -q`

## 2026-05-27 — Browser capture policy checker enforces artifact policy

The standalone browser capture policy checker now validates permission-gate
taxonomy, artifact data policy taxonomy, and developer visibility for replay
surfaces. Replay-capable developer-visible artifacts no longer rely on schema
validation alone for those policy fields.

Touched:

- `bench/tools/check_browser_capture_policy.py`
- `bench/tests/test_browser_capture_policy.py`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/check_browser_capture_policy.py bench/tests/test_browser_capture_policy.py`
- `python3 bench/tools/check_browser_capture_policy.py --policy config/browser-capture-policy.json --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_capture_policy.py -q`

## 2026-05-27 — Browser claim gate rejects unsafe patch manifest paths

The browser claim gate no longer resolves `patchIsolation.patchManifestPath`
with a raw `root / path` join. It now rejects absolute or parent-traversal
manifest paths from the fork-maintenance policy before invoking the Chromium
patch-manifest checker or recording claim-report metadata.

Touched:

- `bench/browser/browser_claim_gate.py`
- `bench/tests/test_browser_claim_gate.py`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/browser/browser_claim_gate.py bench/tests/test_browser_claim_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_claim_gate.py -q`

## 2026-05-27 — Browser release and map verifiers reject path escapes

Chromium integration overlay verification now rejects unsafe
`smokeTestArtifact` paths before loading the linked smoke report. Browser claim
promotion and release bundle verification now require referenced artifact paths
to resolve under `--verify-files-root` before hashing. Responsibility-map claim
bindings now reject absolute or parent-traversal paths before stale-reference
checks.

Touched:

- `bench/tools/check_webgpu_integration_chromium.py`
- `bench/tools/check_browser_claim_promotion_receipt.py`
- `bench/tools/check_browser_release_artifact_bundle.py`
- `bench/tools/check_browser_responsibility_map.py`
- `bench/tests/test_webgpu_integration_chromium_checker.py`
- `bench/tests/test_browser_claim_promotion_receipt.py`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `bench/tests/test_browser_responsibility_map.py`
- `bench/README.md`
- `docs/process.md`
- `browser/chromium/contracts/browser-responsibility-map.contract.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/check_webgpu_integration_chromium.py bench/tools/check_browser_claim_promotion_receipt.py bench/tools/check_browser_release_artifact_bundle.py bench/tools/check_browser_responsibility_map.py bench/tests/test_webgpu_integration_chromium_checker.py bench/tests/test_browser_claim_promotion_receipt.py bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_browser_responsibility_map.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_webgpu_integration_chromium_checker.py bench/tests/test_browser_claim_promotion_receipt.py bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_browser_responsibility_map.py -q`
- `python3 bench/tools/check_webgpu_integration_chromium.py --overlay config/webgpu-integration-chromium.json --verify-artifact-root . --json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/tools/check_browser_responsibility_map.py --map config/browser-responsibility-map.json --root . --json`

## 2026-05-27 — Native command graph replay verifies linked files

Native command graph receipts now emit repo-relative run-receipt and command
paths for repo-owned inputs. Replay checks gained `--verify-files-root`, which
rejects unsafe linked paths and verifies both linked file hashes before relying
on the command graph hash chain.

Touched:

- `bench/tools/build_native_command_graph_receipt.py`
- `bench/tools/replay_native_command_graph_receipt.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_native_command_graph_receipt.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `examples/native-command-graph-receipt.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/build_native_command_graph_receipt.py bench/tools/replay_native_command_graph_receipt.py bench/runners/run_blocking_gates.py bench/tests/test_native_command_graph_receipt.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 bench/tools/build_native_command_graph_receipt.py --run-receipt examples/run-receipt.sample.json --commands examples/kernel_dispatch_commands.json --out examples/native-command-graph-receipt.sample.json`
- `python3 bench/tools/replay_native_command_graph_receipt.py --receipt examples/native-command-graph-receipt.sample.json --verify-files-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_command_graph_receipt.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-27 — Native evidence verification rejects traversal

Native no-fallback report verification now rejects absolute or parent-traversal
`runReceiptPath` values before hashing run receipts. The no-fallback report
builder emits repo-relative paths for repo-owned receipts. Native backend
coverage verification now rejects unsafe `evidencePath` values before loading
covered-row evidence.

Touched:

- `bench/tools/build_native_no_fallback_report.py`
- `bench/tools/check_native_no_fallback_report.py`
- `bench/tools/check_native_backend_coverage_matrix.py`
- `bench/tests/test_native_no_fallback_report.py`
- `bench/tests/test_native_backend_coverage_matrix.py`
- `examples/native-no-fallback-report.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/build_native_no_fallback_report.py bench/tools/check_native_no_fallback_report.py bench/tools/check_native_backend_coverage_matrix.py bench/tests/test_native_no_fallback_report.py bench/tests/test_native_backend_coverage_matrix.py`
- `python3 bench/tools/build_native_no_fallback_report.py --run-receipt examples/run-receipt.sample.json --out examples/native-no-fallback-report.sample.json`
- `python3 bench/tools/check_native_no_fallback_report.py --report examples/native-no-fallback-report.sample.json --verify-files-root . --json`
- `python3 bench/tools/check_native_backend_coverage_matrix.py --matrix config/native-backend-coverage-matrix.json --verify-evidence-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_no_fallback_report.py bench/tests/test_native_backend_coverage_matrix.py bench/tests/test_native_pipeline_cache_receipts.py bench/tests/test_native_upload_path_receipts.py bench/tests/test_native_resource_reuse_receipts.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-27 — Browser media and fallback evidence paths reject traversal

Browser media-path probe and fallback-explanation checkers now reject absolute
or parent-traversal developer-visible evidence paths. Media probes also validate
media source paths with the same repo-relative path rule. The media capture
policy resolver now uses the supplied path text rather than an undefined local
name.

Touched:

- `browser/chromium/scripts/check-browser-media-path-probe.py`
- `browser/chromium/scripts/check-browser-fallback-explanations.py`
- `bench/tests/test_browser_media_path_probe.py`
- `bench/tests/test_browser_fallback_explanations.py`
- `browser/chromium/contracts/browser-media-path-probe.contract.md`
- `browser/chromium/contracts/browser-fallback-explanations.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-media-path-probe.py browser/chromium/scripts/check-browser-fallback-explanations.py bench/tests/test_browser_media_path_probe.py bench/tests/test_browser_fallback_explanations.py`
- `python3 browser/chromium/scripts/check-browser-media-path-probe.py --probe examples/browser-media-path-probe.sample.json --capture-policy-root . --runtime-identity-root . --json`
- `python3 browser/chromium/scripts/check-browser-fallback-explanations.py --explanations examples/browser-fallback-explanations.sample.json --taxonomy-root . --runtime-identity-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_media_path_probe.py bench/tests/test_browser_fallback_explanations.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/build_browser_release_artifact_bundle.py --bundle-id browser-release-diagnostic-sample-v1 --release-status diagnostic --browser-binary browser/chromium/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium --doe-runtime runtime/zig/zig-out/lib/libwebgpu_doe_full.dylib --shader-compiler runtime/zig/zig-out/bin/doe-zig-runtime --claim-report examples/browser-claim-report.sample.json --promotion-receipt examples/browser-claim-promotion-receipt.sample.json --out examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser CTS and recovery paths reject traversal

Browser CTS subset and recovery parity checkers now reject absolute or
parent-traversal artifact/evidence paths while still allowing diagnostic
repo-relative paths and smoke-report fragment anchors. The new failure code is
`unsafe_artifact_path`.

Touched:

- `browser/chromium/scripts/check-browser-cts-subset.py`
- `browser/chromium/scripts/check-browser-recovery-parity.py`
- `bench/tests/test_browser_cts_subset.py`
- `bench/tests/test_browser_recovery_parity.py`
- `browser/chromium/contracts/browser-cts-subset.contract.md`
- `browser/chromium/contracts/browser-recovery-parity.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-cts-subset.py browser/chromium/scripts/check-browser-recovery-parity.py bench/tests/test_browser_cts_subset.py bench/tests/test_browser_recovery_parity.py`
- `python3 browser/chromium/scripts/check-browser-cts-subset.py --subset examples/browser-cts-subset.sample.json --json`
- `python3 browser/chromium/scripts/check-browser-recovery-parity.py --parity examples/browser-recovery-parity.sample.json --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_cts_subset.py bench/tests/test_browser_recovery_parity.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/build_browser_release_artifact_bundle.py --bundle-id browser-release-diagnostic-sample-v1 --release-status diagnostic --browser-binary browser/chromium/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium --doe-runtime runtime/zig/zig-out/lib/libwebgpu_doe_full.dylib --shader-compiler runtime/zig/zig-out/bin/doe-zig-runtime --claim-report examples/browser-claim-report.sample.json --promotion-receipt examples/browser-claim-promotion-receipt.sample.json --out examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser pipeline cache source workload paths are repo-relative

Browser pipeline cache receipt validation now rejects unsafe
`sourceWorkloadsPath` values before loading the source local-AI workload
artifact. The checker reports `unsafe_source_workloads_path` for absolute or
parent-traversal paths and `invalid_source_workloads` for source files that do
not decode as JSON objects.

Touched:

- `browser/chromium/scripts/check-browser-pipeline-cache-receipts.py`
- `bench/tests/test_browser_pipeline_cache_receipts.py`
- `browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-pipeline-cache-receipts.py bench/tests/test_browser_pipeline_cache_receipts.py`
- `python3 browser/chromium/scripts/check-browser-pipeline-cache-receipts.py --receipts examples/browser-pipeline-cache-receipts.sample.json --verify-workloads-root . --runtime-identity-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_pipeline_cache_receipts.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/build_browser_release_artifact_bundle.py --bundle-id browser-release-diagnostic-sample-v1 --release-status diagnostic --browser-binary browser/chromium/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium --doe-runtime runtime/zig/zig-out/lib/libwebgpu_doe_full.dylib --shader-compiler runtime/zig/zig-out/bin/doe-zig-runtime --claim-report examples/browser-claim-report.sample.json --promotion-receipt examples/browser-claim-promotion-receipt.sample.json --out examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser artifact checkers reject schema-version drift

Standalone browser artifact checkers now reject wrong top-level
`schemaVersion` values before accepting nested rows. Pipeline cache receipts
also gained the same direct `artifactKind` guard as the other browser artifact
families, and flight-recorder replay rejects source schema drift as a fatal
replay failure.

Touched:

- `browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py`
- `browser/chromium/scripts/check-browser-cts-subset.py`
- `browser/chromium/scripts/check-browser-fallback-explanations.py`
- `browser/chromium/scripts/check-browser-gpu-scheduler.py`
- `browser/chromium/scripts/check-browser-local-ai-workloads.py`
- `browser/chromium/scripts/check-browser-media-path-probe.py`
- `browser/chromium/scripts/check-browser-pipeline-cache-receipts.py`
- `browser/chromium/scripts/check-browser-recovery-parity.py`
- `browser/chromium/scripts/check-browser-shader-links.py`
- `browser/chromium/scripts/check-browser-webgpu-effect-experiment.py`
- `browser/chromium/scripts/replay-browser-gpu-flight-recorder.py`
- `bench/tests/test_browser_checker_artifact_kind.py`
- `bench/tests/test_browser_gpu_flight_recorder_contract.py`
- browser artifact contract docs
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-media-path-probe.py browser/chromium/scripts/check-browser-webgpu-effect-experiment.py browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py browser/chromium/scripts/check-browser-gpu-scheduler.py browser/chromium/scripts/check-browser-local-ai-workloads.py browser/chromium/scripts/check-browser-fallback-explanations.py browser/chromium/scripts/check-browser-cts-subset.py browser/chromium/scripts/check-browser-recovery-parity.py browser/chromium/scripts/check-browser-pipeline-cache-receipts.py browser/chromium/scripts/check-browser-shader-links.py browser/chromium/scripts/replay-browser-gpu-flight-recorder.py bench/tests/test_browser_checker_artifact_kind.py bench/tests/test_browser_gpu_flight_recorder_contract.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_checker_artifact_kind.py bench/tests/test_browser_gpu_flight_recorder_contract.py bench/tests/test_browser_pipeline_cache_receipts.py bench/tests/test_browser_shader_links.py -q`
- `python3 bench/tools/build_browser_release_artifact_bundle.py --bundle-id browser-release-diagnostic-sample-v1 --release-status diagnostic --browser-binary browser/chromium/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium --doe-runtime runtime/zig/zig-out/lib/libwebgpu_doe_full.dylib --shader-compiler runtime/zig/zig-out/bin/doe-zig-runtime --claim-report examples/browser-claim-report.sample.json --promotion-receipt examples/browser-claim-promotion-receipt.sample.json --out examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser structural checkers reject wrong artifact kinds

Browser structural checkers for derived probes, CTS subset, and recovery parity
now reject mismatched top-level `artifactKind` values before accepting internal
rows. This prevents a payload from passing a checker only because its nested
shape happens to match another browser artifact family.

Touched:

- `browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py`
- `browser/chromium/scripts/check-browser-cts-subset.py`
- `browser/chromium/scripts/check-browser-fallback-explanations.py`
- `browser/chromium/scripts/check-browser-gpu-scheduler.py`
- `browser/chromium/scripts/check-browser-local-ai-workloads.py`
- `browser/chromium/scripts/check-browser-media-path-probe.py`
- `browser/chromium/scripts/check-browser-recovery-parity.py`
- `browser/chromium/scripts/check-browser-webgpu-effect-experiment.py`
- `bench/tests/test_browser_checker_artifact_kind.py`
- browser derived/CTS/recovery contract docs
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-media-path-probe.py browser/chromium/scripts/check-browser-webgpu-effect-experiment.py browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py browser/chromium/scripts/check-browser-gpu-scheduler.py browser/chromium/scripts/check-browser-local-ai-workloads.py browser/chromium/scripts/check-browser-fallback-explanations.py browser/chromium/scripts/check-browser-cts-subset.py browser/chromium/scripts/check-browser-recovery-parity.py bench/tests/test_browser_checker_artifact_kind.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_checker_artifact_kind.py bench/tests/test_browser_canvas_webgpu_fusion.py bench/tests/test_browser_cts_subset.py bench/tests/test_browser_fallback_explanations.py bench/tests/test_browser_gpu_scheduler.py bench/tests/test_browser_local_ai_workloads.py bench/tests/test_browser_media_path_probe.py bench/tests/test_browser_recovery_parity.py bench/tests/test_browser_webgpu_effect_experiment.py -q`
- `python3 bench/tools/build_browser_release_artifact_bundle.py --bundle-id browser-release-diagnostic-sample-v1 --release-status diagnostic --browser-binary browser/chromium/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium --doe-runtime runtime/zig/zig-out/lib/libwebgpu_doe_full.dylib --shader-compiler runtime/zig/zig-out/bin/doe-zig-runtime --claim-report examples/browser-claim-report.sample.json --promotion-receipt examples/browser-claim-promotion-receipt.sample.json --out examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser flight replay binds responsibility-map version

Browser GPU flight-recorder replay now resolves the capture's
`responsibilityMap.path` under an explicit `--responsibility-map-root` and
rejects unsafe paths, missing map files, invalid map JSON, and stale
`mapVersion` values before accepting a replay report.

Touched:

- `browser/chromium/scripts/replay-browser-gpu-flight-recorder.py`
- `bench/browser/browser_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_browser_gpu_flight_recorder_contract.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `browser/chromium/contracts/browser-gpu-flight-recorder.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/process.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/replay-browser-gpu-flight-recorder.py bench/browser/browser_gate.py bench/runners/run_blocking_gates.py bench/tests/test_browser_gpu_flight_recorder_contract.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --capture-policy config/browser-capture-policy.json --responsibility-map-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gpu_flight_recorder_contract.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/build_browser_release_artifact_bundle.py --bundle-id browser-release-diagnostic-sample-v1 --release-status diagnostic --browser-binary browser/chromium/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium --doe-runtime runtime/zig/zig-out/lib/libwebgpu_doe_full.dylib --shader-compiler runtime/zig/zig-out/bin/doe-zig-runtime --claim-report examples/browser-claim-report.sample.json --promotion-receipt examples/browser-claim-promotion-receipt.sample.json --out examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Derived browser artifacts verify runtime identity references

Derived browser artifact checkers now accept `--runtime-identity-root` and
resolve `runtimeIdentity.runtimeIdentityPath` before accepting selected runtime
or fallback state. The shared checker accepts both `browser_runtime_identity`
artifacts and source browser smoke reports, which keeps sample artifacts and
smoke-generated artifacts under the same identity-binding rule.

Touched:

- `browser/chromium/scripts/browser_runtime_identity_reference.py`
- `browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py`
- `browser/chromium/scripts/check-browser-media-path-probe.py`
- `browser/chromium/scripts/check-browser-gpu-scheduler.py`
- `browser/chromium/scripts/check-browser-webgpu-effect-experiment.py`
- `browser/chromium/scripts/check-browser-local-ai-workloads.py`
- `browser/chromium/scripts/check-browser-fallback-explanations.py`
- `browser/chromium/scripts/check-browser-pipeline-cache-receipts.py`
- `bench/browser/browser_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_browser_runtime_identity_reference.py`
- `bench/tests/test_browser_derived_runtime_identity_reference.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- browser derived artifact contract docs
- `examples/browser-release-artifact-bundle.sample.json`
- `bench/README.md`
- `docs/process.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/browser_runtime_identity_reference.py browser/chromium/scripts/check-browser-media-path-probe.py browser/chromium/scripts/check-browser-webgpu-effect-experiment.py browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py browser/chromium/scripts/check-browser-gpu-scheduler.py browser/chromium/scripts/check-browser-local-ai-workloads.py browser/chromium/scripts/check-browser-fallback-explanations.py browser/chromium/scripts/check-browser-pipeline-cache-receipts.py bench/browser/browser_gate.py bench/runners/run_blocking_gates.py bench/tests/test_browser_runtime_identity_reference.py bench/tests/test_browser_derived_runtime_identity_reference.py bench/tests/test_run_blocking_gates_wiring.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_runtime_identity_reference.py bench/tests/test_browser_derived_runtime_identity_reference.py bench/tests/test_browser_media_path_probe.py bench/tests/test_browser_local_ai_workloads.py bench/tests/test_browser_fallback_explanations.py bench/tests/test_browser_pipeline_cache_receipts.py bench/tests/test_run_blocking_gates_wiring.py -q`
- derived checker sample commands with `--runtime-identity-root .`
- `python3 bench/tools/build_browser_release_artifact_bundle.py --bundle-id browser-release-diagnostic-sample-v1 --release-status diagnostic --browser-binary browser/chromium/out/fawn_release_local/Fawn.app/Contents/MacOS/Chromium --doe-runtime runtime/zig/zig-out/lib/libwebgpu_doe_full.dylib --shader-compiler runtime/zig/zig-out/bin/doe-zig-runtime --claim-report examples/browser-claim-report.sample.json --promotion-receipt examples/browser-claim-promotion-receipt.sample.json --out examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`

## 2026-05-27 — Browser flight replay checks graph identity and ordering

Browser GPU flight-recorder replay now rejects duplicate command node IDs,
missing/invalid/duplicate submit IDs, ordering edges that point backward,
unknown shader/resource references, stale timing node references, and invalid
frame presentation nodes. The release bundle sample was regenerated because the
flight-recorder contract hash changed.

Touched:

- `browser/chromium/scripts/replay-browser-gpu-flight-recorder.py`
- `bench/tests/test_browser_gpu_flight_recorder_contract.py`
- `browser/chromium/contracts/browser-gpu-flight-recorder.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/process.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/replay-browser-gpu-flight-recorder.py bench/tests/test_browser_gpu_flight_recorder_contract.py`
- `python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --capture-policy config/browser-capture-policy.json --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gpu_flight_recorder_contract.py -q`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser shader links verify source flight-recorder rows

Browser shader-link validation now resolves `sourceFlightRecorderPath` with
`--verify-flight-recorder-root` and rejects missing, duplicate, extra, or
drifted shader rows before checking WGSL lowering receipts. The browser gate
and standalone blocking runner now pass the flight-recorder verification root,
and artifact identity coverage records the capture ID plus shader hash anchors.

Touched:

- `config/browser-shader-links.schema.json`
- `config/browser-artifact-identity-coverage.json`
- `browser/chromium/scripts/check-browser-shader-links.py`
- `bench/browser/browser_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_browser_shader_links.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `browser/chromium/contracts/browser-shader-links.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/process.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-shader-links.py bench/browser/browser_gate.py bench/runners/run_blocking_gates.py bench/tests/test_browser_shader_links.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 browser/chromium/scripts/check-browser-shader-links.py --links examples/browser-shader-links.sample.json --verify-flight-recorder-root . --verify-lowering-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_shader_links.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/check_browser_artifact_identity_coverage.py --coverage config/browser-artifact-identity-coverage.json --root . --json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser pipeline cache receipts verify source workload coverage

Browser pipeline cache receipts now record `sourceWorkloadsPath`, carry shader
source/IR/backend hashes on each receipt row, and can be checked against the
source local-AI workload artifact. The checker rejects missing, duplicate,
extra, or source-drifted workload receipts when `--verify-workloads-root` is
supplied. The browser gate and standalone blocking runner both pass that root.

Touched:

- `config/browser-pipeline-cache-receipts.schema.json`
- `examples/browser-pipeline-cache-receipts.sample.json`
- `browser/chromium/scripts/build-browser-pipeline-cache-receipts.py`
- `browser/chromium/scripts/check-browser-pipeline-cache-receipts.py`
- `bench/browser/browser_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_browser_pipeline_cache_receipts.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `config/browser-artifact-identity-coverage.json`
- `browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/process.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `bench/README.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-pipeline-cache-receipts.py browser/chromium/scripts/build-browser-pipeline-cache-receipts.py bench/browser/browser_gate.py bench/runners/run_blocking_gates.py bench/tests/test_browser_pipeline_cache_receipts.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 browser/chromium/scripts/check-browser-pipeline-cache-receipts.py --receipts examples/browser-pipeline-cache-receipts.sample.json --verify-workloads-root . --json`
- `python3 bench/tools/check_browser_artifact_identity_coverage.py --coverage config/browser-artifact-identity-coverage.json --root . --json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_pipeline_cache_receipts.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Local AI workload receipts hash shader IR and backend output

Browser local-AI workload rows now require shader IR and backend-output hashes
alongside the existing shader source hash and path anchors. The builder emits
those hashes from smoke-derived workload evidence, and the checker rejects rows
whose shader identity does not bind source, IR, and backend output.

Touched:

- `config/browser-local-ai-workloads.schema.json`
- `examples/browser-local-ai-workloads.sample.json`
- `browser/chromium/scripts/build-browser-local-ai-workloads.py`
- `browser/chromium/scripts/check-browser-local-ai-workloads.py`
- `bench/tests/test_browser_local_ai_workloads.py`
- `browser/chromium/contracts/browser-local-ai-workloads.contract.md`
- `examples/browser-release-artifact-bundle.sample.json`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-local-ai-workloads.py browser/chromium/scripts/build-browser-local-ai-workloads.py bench/tests/test_browser_local_ai_workloads.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_local_ai_workloads.py -q`
- `python3 browser/chromium/scripts/check-browser-local-ai-workloads.py --workloads examples/browser-local-ai-workloads.sample.json --json`
- `python3 browser/chromium/scripts/build-browser-local-ai-workloads.py --report examples/browser-smoke-report.sample.json --mode doe --out /tmp/browser-local-ai-workloads.verify.json && python3 browser/chromium/scripts/check-browser-local-ai-workloads.py --workloads /tmp/browser-local-ai-workloads.verify.json`
- `python3 bench/tools/check_browser_artifact_identity_coverage.py --coverage config/browser-artifact-identity-coverage.json --root . --json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser fallback explanations use governed reason codes

Browser unsupported and fallback reason codes now have a schema-backed taxonomy.
Fallback explanation artifacts carry the taxonomy path, the checker rejects
unknown reason codes and capability/status mismatches, and release bundles
hash-bind the taxonomy with the other browser policies. The smoke harness also
passes the taxonomy into the fallback-explanations builder.

Touched:

- `config/browser-unsupported-reason-taxonomy.schema.json`
- `config/browser-unsupported-reason-taxonomy.json`
- `config/browser-fallback-explanations.schema.json`
- `examples/browser-fallback-explanations.sample.json`
- `bench/tools/check_browser_unsupported_reason_taxonomy.py`
- `browser/chromium/scripts/build-browser-fallback-explanations.py`
- `browser/chromium/scripts/check-browser-fallback-explanations.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/browser/browser_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_browser_unsupported_reason_taxonomy.py`
- `bench/tests/test_browser_fallback_explanations.py`
- `bench/tools/build_browser_release_artifact_bundle.py`
- `bench/tools/check_browser_release_artifact_bundle.py`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `config/schema-targets.json`
- `config/browser-artifact-identity-coverage.json`
- `examples/browser-release-artifact-bundle.sample.json`
- `bench/README.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/check_browser_unsupported_reason_taxonomy.py browser/chromium/scripts/check-browser-fallback-explanations.py browser/chromium/scripts/build-browser-fallback-explanations.py bench/runners/run_blocking_gates.py bench/browser/browser_gate.py bench/tests/test_browser_unsupported_reason_taxonomy.py bench/tests/test_browser_fallback_explanations.py bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_run_blocking_gates_wiring.py`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_unsupported_reason_taxonomy.py bench/tests/test_browser_fallback_explanations.py bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/check_browser_unsupported_reason_taxonomy.py --taxonomy config/browser-unsupported-reason-taxonomy.json --json`
- `python3 browser/chromium/scripts/check-browser-fallback-explanations.py --explanations examples/browser-fallback-explanations.sample.json --taxonomy-root . --json`
- `python3 browser/chromium/scripts/build-browser-fallback-explanations.py --report examples/browser-smoke-report.sample.json --mode doe --taxonomy config/browser-unsupported-reason-taxonomy.json --out /tmp/browser-fallback-explanations.verify.json && python3 browser/chromium/scripts/check-browser-fallback-explanations.py --explanations /tmp/browser-fallback-explanations.verify.json --taxonomy-root .`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/tools/check_browser_artifact_identity_coverage.py --coverage config/browser-artifact-identity-coverage.json --root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser artifact identity coverage is gated

Browser evidence now has a schema-backed identity coverage manifest. The
checker validates that smoke reports, flight recorders, derived browser probes,
shader links, replay reports, CTS/recovery pairs, claim reports, promotion
receipts, and release bundles carry their declared identity anchors. Browser
release bundles now hash-bind this coverage manifest with the other browser
policies.

Touched:

- `config/browser-artifact-identity-coverage.schema.json`
- `config/browser-artifact-identity-coverage.json`
- `bench/tools/check_browser_artifact_identity_coverage.py`
- `bench/tests/test_browser_artifact_identity_coverage.py`
- `bench/tools/build_browser_release_artifact_bundle.py`
- `bench/tools/check_browser_release_artifact_bundle.py`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `config/schema-targets.json`
- `examples/browser-release-artifact-bundle.sample.json`
- `bench/README.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/check_browser_artifact_identity_coverage.py bench/tools/build_browser_release_artifact_bundle.py bench/tools/check_browser_release_artifact_bundle.py bench/runners/run_blocking_gates.py bench/tests/test_browser_artifact_identity_coverage.py bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_run_blocking_gates_wiring.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_artifact_identity_coverage.py bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/check_browser_artifact_identity_coverage.py --coverage config/browser-artifact-identity-coverage.json --root . --json`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_chromium_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-29 — Chromium source selector claims now require source markers

The browser lane no longer treats wrapper diagnostics as proof that Chromium
owns the Doe runtime seam. `check_chromium_source_checkout.py` now has a
`--require-runtime-selector` mode that requires the source checkout to expose
the runtime selector switches and typed fail-closed reason markers before
source-level selector ownership can be claimed. The Chromium integration overlay
now records the current state as `source_selector_required`; browser smoke
artifacts remain diagnostic until that source gate passes.

Current local diagnostic state: `blocked` because the external
`/Volumes/MACOS/fawn-browser` checkout is not mounted, leaving
`browser/chromium/src` as a dangling symlink.

Touched:

- `bench/tools/check_chromium_source_checkout.py`
- `config/chromium-source-checkout-check.schema.json`
- `examples/chromium-source-checkout-check.sample.json`
- `bench/runners/run_blocking_gates.py`
- `config/webgpu-integration-chromium.json`
- `config/webgpu-integration-chromium.schema.json`
- `bench/tools/check_webgpu_integration_chromium.py`
- `browser/chromium/chromium-bringup.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

## 2026-05-27 — Chromium source checkout has an explicit preflight gate

Chromium source-dependent seam work now has a schema-backed checkout readiness
report. The checker distinguishes repo-owned browser evidence work from
source-level Chromium patch work by validating the source root markers and
Chromium build tools. Diagnostic mode records the current blocker without
breaking source-free gates; the optional blocking-runner gate requires readiness
when source-level Chromium work is being claimed.

Current local diagnostic state: `blocked` because `browser/chromium/src` is not
present and `gclient`, `gn`, and `autoninja` are not on `PATH`.

Touched:

- `config/chromium-source-checkout-check.schema.json`
- `examples/chromium-source-checkout-check.sample.json`
- `bench/tools/check_chromium_source_checkout.py`
- `bench/tests/test_chromium_source_checkout.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `config/schema-targets.json`
- `bench/README.md`
- `browser/chromium/chromium-bringup.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/check_chromium_source_checkout.py bench/runners/run_blocking_gates.py bench/tests/test_chromium_source_checkout.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 bench/tools/check_chromium_source_checkout.py --source-root browser/chromium/src --root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_chromium_source_checkout.py bench/tests/test_chromium_patch_manifest.py bench/tests/test_chromium_fork_maintenance_policy.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/gates/schema_gate.py`

## 2026-05-27 — Media path probes bind browser capture policy

Browser media-path probe artifacts now reference the `media_path_probe` row in
`config/browser-capture-policy.json`. The checker validates that the referenced
policy row is origin scoped, secure-context/DevTools gated, hash-only for raw
page data, redacted/hash-only for artifacts, non-replayable, and developer
visible before accepting external-texture or media-copy diagnostics.

Touched:

- `config/browser-capture-policy.schema.json`
- `config/browser-capture-policy.json`
- `config/browser-media-path-probe.schema.json`
- `bench/tools/check_browser_capture_policy.py`
- `browser/chromium/scripts/build-browser-media-path-probe.py`
- `browser/chromium/scripts/check-browser-media-path-probe.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/browser/browser_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_browser_media_path_probe.py`
- `bench/tests/test_browser_capture_policy.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `browser/chromium/contracts/browser-media-path-probe.contract.md`
- `examples/browser-media-path-probe.sample.json`
- `examples/browser-release-artifact-bundle.sample.json`
- `bench/README.md`
- `docs/browser-lane.md`
- `docs/chromium-webgpu-task-list.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-media-path-probe.py browser/chromium/scripts/build-browser-media-path-probe.py bench/tools/check_browser_capture_policy.py bench/browser/browser_gate.py bench/runners/run_blocking_gates.py bench/tests/test_browser_media_path_probe.py bench/tests/test_browser_capture_policy.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py bench/tests/test_browser_release_artifact_bundle.py`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_media_path_probe.py bench/tests/test_browser_capture_policy.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py bench/tests/test_browser_release_artifact_bundle.py -q`
- `python3 bench/tools/check_browser_capture_policy.py --policy config/browser-capture-policy.json --json`
- `python3 browser/chromium/scripts/check-browser-media-path-probe.py --probe examples/browser-media-path-probe.sample.json --capture-policy-root . --json`
- `python3 browser/chromium/scripts/build-browser-media-path-probe.py --report examples/browser-smoke-report.sample.json --mode doe --capture-policy config/browser-capture-policy.json --out /tmp/browser-media-path-probe.verify.json && python3 browser/chromium/scripts/check-browser-media-path-probe.py --probe /tmp/browser-media-path-probe.verify.json --capture-policy-root .`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser release bundles bind Chromium patch manifest

Browser release artifact bundles now include `config/chromium-patch-manifest.json`
as a required policy artifact. The bundle checker rejects release evidence that
binds the fork-maintenance policy without the manifest that enumerates the
browser-owned Chromium integration delta.

Touched:

- `bench/tools/build_browser_release_artifact_bundle.py`
- `bench/tools/check_browser_release_artifact_bundle.py`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `examples/browser-release-artifact-bundle.sample.json`
- `bench/README.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/build_browser_release_artifact_bundle.py bench/tools/check_browser_release_artifact_bundle.py bench/tests/test_browser_release_artifact_bundle.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py -q`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root . --json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_browser_shader_links.py bench/tests/test_browser_gpu_flight_recorder_contract.py bench/tests/test_chromium_patch_manifest.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_wgsl_*.py bench/tests/test_native_*.py bench/tests/test_webgpu_integration_chromium_checker.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `git diff --check`

## 2026-05-27 — Browser shader links bind WGSL lowering receipts

Browser shader-link artifacts now carry the WGSL lowering receipt path and row
ID for each shader. The shader-link checker can verify those anchors against
`wgsl_lowering_link_receipt` rows, including source hash, IR hash, backend
target, and backend output hash equality.

Touched:

- `config/browser-gpu-flight-recorder.schema.json`
- `config/browser-shader-links.schema.json`
- `examples/browser-gpu-flight-recorder.sample.json`
- `examples/browser-shader-links.sample.json`
- `browser/chromium/scripts/build-browser-shader-links.py`
- `browser/chromium/scripts/check-browser-shader-links.py`
- `browser/chromium/contracts/browser-shader-links.contract.md`
- `bench/browser/browser_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_browser_gpu_flight_recorder_contract.py`
- `bench/tests/test_browser_shader_links.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `docs/chromium-webgpu-task-list.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/build-browser-shader-links.py browser/chromium/scripts/check-browser-shader-links.py bench/browser/browser_gate.py bench/runners/run_blocking_gates.py bench/tests/test_browser_shader_links.py bench/tests/test_browser_gpu_flight_recorder_contract.py bench/tests/test_run_blocking_gates_wiring.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_shader_links.py bench/tests/test_browser_gpu_flight_recorder_contract.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 browser/chromium/scripts/check-browser-shader-links.py --links examples/browser-shader-links.sample.json --verify-lowering-root . --json`
- `python3 browser/chromium/scripts/build-browser-shader-links.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --out /tmp/browser-shader-links.verify.json`
- `python3 browser/chromium/scripts/check-browser-shader-links.py --links /tmp/browser-shader-links.verify.json --verify-lowering-root .`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_wgsl_*.py bench/tests/test_native_*.py bench/tests/test_webgpu_integration_chromium_checker.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-27 — Chromium patch manifest gates fork isolation

Chromium fork policy now names a schema-backed patch manifest. The manifest
records repo-owned browser integration deltas, allowed patch roots, rollback
paths, evidence paths, and whether a row needs a Chromium source checkout.
`check_chromium_patch_manifest.py` validates those rows against the fork policy
and the promoted browser gate, repeated browser claim gate, and blocking runner
can all enforce the manifest.

Touched:

- `config/chromium-patch-manifest.schema.json`
- `config/chromium-patch-manifest.json`
- `config/chromium-fork-maintenance-policy.schema.json`
- `config/chromium-fork-maintenance-policy.json`
- `config/schema-targets.json`
- `bench/tools/check_chromium_patch_manifest.py`
- `bench/tools/check_chromium_fork_maintenance_policy.py`
- `bench/browser/browser_gate.py`
- `bench/browser/browser_claim_gate.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_chromium_patch_manifest.py`
- `bench/tests/test_chromium_fork_maintenance_policy.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `bench/README.md`
- `docs/process.md`
- `docs/status/runtime-backends-and-bench.md`

Verified:

- `python3 -m py_compile bench/tools/check_chromium_patch_manifest.py bench/tools/check_chromium_fork_maintenance_policy.py bench/tests/test_chromium_patch_manifest.py bench/tests/test_chromium_fork_maintenance_policy.py bench/browser/browser_gate.py bench/browser/browser_claim_gate.py bench/runners/run_blocking_gates.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 bench/tools/check_chromium_fork_maintenance_policy.py --policy config/chromium-fork-maintenance-policy.json --root . --json`
- `python3 bench/tools/check_chromium_patch_manifest.py --manifest config/chromium-patch-manifest.json --policy config/chromium-fork-maintenance-policy.json --root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_chromium_patch_manifest.py bench/tests/test_chromium_fork_maintenance_policy.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_browser_claim_gate.py bench/tests/test_browser_runtime_selector_policy.py bench/tests/test_browser_runtime_selector_mjs.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_wgsl_*.py bench/tests/test_native_*.py bench/tests/test_webgpu_integration_chromium_checker.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Blocking runner can gate standalone evidence artifacts

The canonical blocking runner can now call the standalone browser, WGSL, and
native artifact checkers through opt-in flags. Browser milestone, policy,
probe, promotion, release, and replay artifacts, WGSL corpus/diagnostic/
robustness/lowering evidence, and native upload/cache/reuse/command-graph/
no-fallback/coverage receipts can be promoted through `run_blocking_gates.py`
without a parallel gate path.

The browser smoke harness now normalizes path arguments before spawning
artifact builders, so relative `--out` and evidence paths work through the lane
wrappers even though builders run from the repo root. A local forced-Doe/both
smoke run produced and validated the browser task-ledger artifacts under
`browser/chromium/artifacts/20260526T223345Z/`.
The smoke report itself now has a standalone checker and opt-in blocking-runner
gate. It validates the diagnostic partition, strict-mode evidence, forced
runtime identity, hidden-fallback state, adapter/compiler identity, workload
identity, report hash, and mode-result hash chain without launching Chromium.
The sample smoke report is now covered by `config/browser-smoke-report.schema.json`
and the schema target registry.
Flight-recorder replay is now exposed as its own blocking-runner gate, so an
existing `browser_gpu_flight_recorder` artifact can be replayed against the
browser capture policy without running the full browser diagnostic gate.
Browser claim-promotion receipts are also exposed as a standalone
blocking-runner gate, so forced-Doe/no-hidden-fallback promotion evidence can be
checked without rerunning the browser claim window.
The browser milestone manifest is now registered with schema gate and exposed as
`--with-browser-milestones-gate`.
The browser promotion-approval and workflow manifests are now registered with
schema gate as well, so all browser workflow governance JSON under
`browser/chromium/bench/workflows/` is schema-checked.
Those governance manifests now also have standalone semantic checkers and
blocking-runner hooks for approval role coverage, approval state, workflow row
requirements, L2 claim scope, metric uniqueness, and L0-boundary claim language.
Browser runtime identity now has a standalone semantic checker and blocking
runner hook. The package identity producer only marks Doe active when Chromium
selector evidence explicitly reports `fallbackApplied=false` and
`hiddenFallbackAllowed=false`.
The Chromium integration overlay now has a semantic checker and blocking-runner
hook for required browser seam coverage, external-texture blocked state,
wire-protocol notes, and optional smoke-artifact linkage.
The overlay now points at an existing local smoke artifact so
`--verify-artifact-root .` exercises the linkage instead of only schema shape.
Browser claim policies now have a standalone semantic checker and blocking
runner hook. The release policy is schema-registered alongside the local policy.
Browser ownership now has a standalone semantic checker and blocking-runner hook
for promoted runtime-integration, compatibility, and methodology ownership.
Browser claim reports now have a schema-backed sample, and the browser
promotion/release sample artifacts have builder-computed hashes instead of
placeholder hashes. The promotion receipt sample verifies against repo files;
the release bundle sample verifies on this host against the local browser,
runtime, and compiler artifacts named in the bundle.
The native no-fallback and WGSL corpus materialization samples now also pass
their strict file-verification modes: the no-fallback report is generated from
the sample run receipt, and the WGSL corpus materialization receipt points at
tracked materialized WGSL files under `examples/`.
WGSL lowering-link and minimization receipts now have file-verification modes as
well. The lowering-link checker verifies source hashes and linked Doe receipt
paths; the minimization checker verifies source and candidate WGSL hashes.

Touched:

- `bench/runners/run_blocking_gates.py`
- `bench/tools/build_browser_claim_promotion_receipt.py`
- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `bench/tests/test_browser_runtime_identity_checker.py`
- `bench/tests/test_webgpu_integration_chromium_checker.py`
- `bench/tests/test_browser_claim_policy_checker.py`
- `bench/tests/test_browser_claim_promotion_receipt.py`
- `bench/tests/test_browser_ownership_checker.py`
- `bench/tests/test_browser_workflow_governance.py`
- `bench/tests/test_native_no_fallback_report.py`
- `bench/tests/test_wgsl_corpus_manifest.py`
- `bench/tests/test_wgsl_lowering_link_receipt.py`
- `bench/tests/test_wgsl_minimization_receipt.py`
- `bench/tools/check_webgpu_integration_chromium.py`
- `bench/tools/check_wgsl_lowering_link_receipt.py`
- `bench/tools/check_wgsl_minimization_receipt.py`
- `bench/tools/check_browser_claim_policy.py`
- `bench/tools/check_browser_ownership.py`
- `browser/chromium/scripts/check-browser-smoke-report.py`
- `browser/chromium/scripts/check-browser-runtime-identity.py`
- `browser/chromium/scripts/check-browser-promotion-approvals.py`
- `browser/chromium/scripts/check-browser-workflow-manifest.py`
- `config/browser-claim-report.schema.json`
- `config/browser-smoke-report.schema.json`
- `config/schema-targets.json`
- `examples/browser-claim-report.sample.json`
- `examples/browser-claim-promotion-receipt.sample.json`
- `examples/browser-release-artifact-bundle.sample.json`
- `examples/browser-smoke-report.sample.json`
- `examples/native-no-fallback-report.sample.json`
- `examples/wgsl-corpus-materialization.sample.json`
- `examples/wgsl-corpus-materialized/browser-wgsl-corpus-v0/`
- `examples/wgsl-lowering-link-receipt.sample.json`
- `examples/wgsl-minimization-receipt.sample.json`
- `examples/wgsl-minimize/invalid-missing-return/`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/chromium-bringup.md`
- `packages/doe-gpu/src/browser.js`
- `packages/doe-gpu/test/unit/browser-runtime-identity.test.js`
- `bench/README.md`
- `docs/process.md`

Verified:

- `python3 -m py_compile bench/browser/browser_gate.py browser/chromium/scripts/check-browser-smoke-report.py bench/runners/run_blocking_gates.py bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 -m py_compile browser/chromium/scripts/check-browser-runtime-identity.py bench/tests/test_browser_runtime_identity_checker.py`
- `python3 -m py_compile bench/tools/check_webgpu_integration_chromium.py bench/tests/test_webgpu_integration_chromium_checker.py`
- `python3 -m py_compile bench/tools/check_browser_claim_policy.py bench/tests/test_browser_claim_policy_checker.py`
- `python3 -m py_compile bench/tools/check_browser_ownership.py bench/tests/test_browser_ownership_checker.py`
- `python3 -m py_compile browser/chromium/scripts/check-browser-promotion-approvals.py browser/chromium/scripts/check-browser-workflow-manifest.py bench/tests/test_browser_workflow_governance.py`
- `python3 -m py_compile bench/tools/build_browser_claim_promotion_receipt.py bench/tools/build_browser_release_artifact_bundle.py bench/tests/test_browser_claim_promotion_receipt.py bench/tests/test_browser_release_artifact_bundle.py`
- `python3 -m py_compile bench/tools/build_native_no_fallback_report.py bench/tools/check_native_no_fallback_report.py bench/tools/materialize_wgsl_corpus_manifest.py bench/tools/check_wgsl_corpus_materialization.py bench/tests/test_native_no_fallback_report.py bench/tests/test_wgsl_corpus_manifest.py`
- `python3 -m py_compile bench/tools/check_wgsl_lowering_link_receipt.py bench/tools/check_wgsl_minimization_receipt.py bench/tests/test_wgsl_lowering_link_receipt.py bench/tests/test_wgsl_minimization_receipt.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_runtime_identity_checker.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_webgpu_integration_chromium_checker.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_claim_policy_checker.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_claim_promotion_receipt.py bench/tests/test_browser_release_artifact_bundle.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_no_fallback_report.py bench/tests/test_wgsl_corpus_manifest.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_lowering_link_receipt.py bench/tests/test_wgsl_minimization_receipt.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_ownership_checker.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_workflow_governance.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 browser/chromium/scripts/check-browser-runtime-identity.py --identity examples/browser-runtime-identity.sample.json`
- `python3 browser/chromium/scripts/check-browser-promotion-approvals.py --approvals browser/chromium/bench/workflows/browser-promotion-approvals.json`
- `python3 browser/chromium/scripts/check-browser-workflow-manifest.py --manifest browser/chromium/bench/workflows/browser-workflow-manifest.json`
- `python3 bench/tools/check_webgpu_integration_chromium.py --overlay config/webgpu-integration-chromium.json`
- `python3 bench/tools/check_webgpu_integration_chromium.py --overlay config/webgpu-integration-chromium.json --verify-artifact-root .`
- `python3 bench/tools/check_browser_claim_policy.py --policy config/browser-claim-policy.json`
- `python3 bench/tools/check_browser_claim_policy.py --policy config/browser-claim-policy.release.json`
- `python3 bench/tools/check_browser_claim_promotion_receipt.py --receipt examples/browser-claim-promotion-receipt.sample.json --verify-files-root .`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json --verify-files-root .`
- `python3 bench/tools/check_browser_ownership.py --ownership config/browser-ownership.json`
- `python3 bench/tools/check_native_no_fallback_report.py --report examples/native-no-fallback-report.sample.json --verify-files-root .`
- `python3 bench/tools/check_wgsl_corpus_materialization.py --receipt examples/wgsl-corpus-materialization.sample.json --verify-files-root .`
- `python3 bench/tools/check_wgsl_lowering_link_receipt.py --receipt examples/wgsl-lowering-link-receipt.sample.json --verify-files-root .`
- `python3 bench/tools/check_wgsl_minimization_receipt.py --receipt examples/wgsl-minimization-receipt.sample.json --verify-files-root .`
- `node packages/doe-gpu/test/unit/browser-runtime-identity.test.js`
- `python3 browser/chromium/scripts/check-browser-smoke-report.py --smoke-report examples/browser-smoke-report.sample.json`
- `python3 browser/chromium/scripts/check-browser-smoke-report.py --smoke-report browser/chromium/artifacts/20260526T223345Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
- `python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --capture-policy config/browser-capture-policy.json --out /tmp/browser-gpu-flight-replay.gate.json`
- `python3 bench/tools/check_browser_claim_promotion_receipt.py --receipt examples/browser-claim-promotion-receipt.sample.json`
- `python3 browser/chromium/scripts/check-browser-milestones.py --manifest browser/chromium/bench/workflows/browser-milestones.json`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_smoke_flight_recorder_flags.py bench/tests/test_browser_gate.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py bench/tests/test_wgsl_*.py bench/tests/test_native_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`
- `./scripts/run-smoke.sh --mode both --headless true --strict --out artifacts/20260526T223345Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json` with all optional browser artifact output flags enabled
- `python3 browser/chromium/scripts/check-browser-benchmark-superset.py`
- `python3 bench/tools/check_native_pipeline_cache_receipts.py --receipts examples/native-pipeline-cache-receipts.sample.json`

## 2026-05-26 — Native coverage matrix can verify evidence files

The native backend coverage matrix checker now accepts `--verify-evidence-root`
to resolve covered-row evidence paths, require the files to exist, and validate
that the referenced artifact kind matches the coverage class.

Touched:

- `bench/tools/check_native_backend_coverage_matrix.py`
- `bench/tests/test_native_backend_coverage_matrix.py`

Verified:

- `python3 -m py_compile bench/tools/check_native_backend_coverage_matrix.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_backend_coverage_matrix.py -q`
- `python3 bench/tools/check_native_backend_coverage_matrix.py --matrix config/native-backend-coverage-matrix.json --verify-evidence-root .`

## 2026-05-26 — Native command graph sample is replay-valid

The native command graph sample now carries the replay-computed row hash and
terminal trace hash. The native command graph test suite validates the sample
against the schema and replay checker so sample evidence cannot drift from the
hash-chain contract.

Touched:

- `examples/native-command-graph-receipt.sample.json`
- `bench/tests/test_native_command_graph_receipt.py`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_command_graph_receipt.py -q`
- `python3 bench/tools/replay_native_command_graph_receipt.py --receipt examples/native-command-graph-receipt.sample.json`
- `python3 bench/gates/schema_gate.py`

## 2026-05-26 — Native no-fallback reports have a standalone checker

Strict native no-fallback reports now have an independent checker. It validates
native Doe runtime identity, disabled fallback state, row/summary consistency,
failure mirroring, and can optionally verify source run-receipt hashes.

Touched:

- `bench/tools/check_native_no_fallback_report.py`
- `bench/tests/test_native_no_fallback_report.py`

Verified:

- `python3 -m py_compile bench/tools/check_native_no_fallback_report.py bench/tools/build_native_no_fallback_report.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_no_fallback_report.py -q`
- `python3 bench/tools/check_native_no_fallback_report.py --report examples/native-no-fallback-report.sample.json`

## 2026-05-26 — Browser release bundles bind promotion receipts

Browser release artifact bundles now carry `promotionReceipts` alongside claim
reports. The bundle builder hashes browser claim promotion receipts, the schema
requires them, and the checker rejects bundles without
`browser_claim_promotion_receipt` evidence. When file verification is enabled,
the checker also validates promotion receipts and requires them to cover every
bundled claim report hash.
Default release bundles now bind the active Track A browser contracts used by
the runtime selector, benchmark superset, claim methodology, responsibility
map, CTS subset, recovery parity, flight recorder, shader links, and
smoke-derived capability artifacts.

Touched:

- `bench/tools/build_browser_release_artifact_bundle.py`
- `bench/tools/check_browser_release_artifact_bundle.py`
- `config/browser-release-artifact-bundle.schema.json`
- `examples/browser-release-artifact-bundle.sample.json`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `bench/README.md`
- `browser/chromium/README.md`

Verified:

- `python3 -m py_compile bench/tools/build_browser_release_artifact_bundle.py bench/tools/check_browser_release_artifact_bundle.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py -q`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json`
- `python3 -m py_compile bench/tools/check_browser_release_artifact_bundle.py bench/tools/check_browser_claim_promotion_receipt.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py bench/tests/test_browser_claim_promotion_receipt.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py -q`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json && python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser gate validates flight recorder and shader links

The promoted browser diagnostic gate now asks smoke to emit a forced-Doe
`browser_gpu_flight_recorder` and paired `browser_shader_links` artifact. The
gate replays the flight recorder through the capture-policy-governed replay
checker, validates shader links with a standalone checker, and preserves the
new artifacts in repeated browser-claim windows.

Touched:

- `bench/browser/browser_gate.py`
- `bench/browser/browser_claim_gate.py`
- `browser/chromium/scripts/check-browser-shader-links.py`
- `bench/tests/test_browser_gate.py`
- `bench/tests/test_browser_claim_gate.py`
- `bench/tests/test_browser_shader_links.py`
- `docs/process.md`
- `browser/chromium/README.md`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-shader-links.py browser/chromium/scripts/replay-browser-gpu-flight-recorder.py bench/browser/browser_gate.py bench/browser/browser_claim_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_shader_links.py bench/tests/test_browser_gate.py bench/tests/test_browser_claim_gate.py bench/tests/test_browser_gpu_flight_recorder_contract.py -q`
- `python3 browser/chromium/scripts/check-browser-shader-links.py --links examples/browser-shader-links.sample.json && python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --capture-policy config/browser-capture-policy.json --out /tmp/browser-gpu-flight-replay.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser pipeline cache receipts have a standalone checker

Browser pipeline cache receipt validation now lives in
`check-browser-pipeline-cache-receipts.py`. The promoted browser gate calls the
same checker as standalone validation, so cache-state, creation-status, hidden
fallback, and fallback-reason failures are enforced consistently.

Touched:

- `browser/chromium/scripts/check-browser-pipeline-cache-receipts.py`
- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_pipeline_cache_receipts.py`
- `bench/tests/test_browser_gate.py`

Verified:

- `python3 -m py_compile browser/chromium/scripts/check-browser-pipeline-cache-receipts.py bench/browser/browser_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_pipeline_cache_receipts.py bench/tests/test_browser_gate.py -q`
- `python3 browser/chromium/scripts/check-browser-pipeline-cache-receipts.py --receipts examples/browser-pipeline-cache-receipts.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser release bundles bind capture policy

Browser release artifact bundle defaults and checks now include
`config/browser-capture-policy.json`. Release evidence therefore hash-binds the
origin-scope, raw-page-data, replay, and developer-visibility policy used by
browser capture artifacts.

Touched:

- `bench/tools/build_browser_release_artifact_bundle.py`
- `bench/tools/check_browser_release_artifact_bundle.py`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `examples/browser-release-artifact-bundle.sample.json`

Verified:

- `python3 -m py_compile bench/tools/build_browser_release_artifact_bundle.py bench/tools/check_browser_release_artifact_bundle.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py -q`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser claim windows preserve gate artifact maps

The repeated browser claim gate now preserves the full per-window browser-gate
artifact map in claim reports, including CTS subset, recovery parity, and
smoke-derived capability probe artifacts. Reused artifact roots discover the
same known artifact names when present so older windows remain readable while
new windows keep the richer evidence map.

Touched:

- `bench/browser/browser_claim_gate.py`
- `bench/tests/test_browser_claim_gate.py`

Verified:

- `python3 -m py_compile bench/browser/browser_claim_gate.py bench/tests/test_browser_claim_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_claim_gate.py bench/tests/test_browser_claim_promotion_receipt.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser gate emits capability probe artifacts

The promoted browser diagnostic gate now asks the smoke runner to emit the
smoke-derived browser capability artifacts and validates them before accepting
the gate report: canvas/WebGPU fusion, media-path probe, GPU scheduler, WebGPU
effect experiment, local AI workloads, pipeline cache receipts, and fallback
explanations. Gate output records each artifact path, hash, and per-artifact
ok status.

Touched:

- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `docs/process.md`

Verified:

- `python3 -m py_compile bench/browser/browser_gate.py browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py browser/chromium/scripts/check-browser-media-path-probe.py browser/chromium/scripts/check-browser-gpu-scheduler.py browser/chromium/scripts/check-browser-webgpu-effect-experiment.py browser/chromium/scripts/check-browser-local-ai-workloads.py browser/chromium/scripts/build-browser-pipeline-cache-receipts.py browser/chromium/scripts/check-browser-fallback-explanations.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_browser_canvas_webgpu_fusion.py bench/tests/test_browser_media_path_probe.py bench/tests/test_browser_gpu_scheduler.py bench/tests/test_browser_webgpu_effect_experiment.py bench/tests/test_browser_local_ai_workloads.py bench/tests/test_browser_pipeline_cache_receipts.py bench/tests/test_browser_fallback_explanations.py -q`
- `python3 browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py --probe examples/browser-canvas-webgpu-fusion.sample.json && python3 browser/chromium/scripts/check-browser-media-path-probe.py --probe examples/browser-media-path-probe.sample.json && python3 browser/chromium/scripts/check-browser-gpu-scheduler.py --probe examples/browser-gpu-scheduler.sample.json && python3 browser/chromium/scripts/check-browser-webgpu-effect-experiment.py --experiment examples/browser-webgpu-effect-experiment.sample.json && python3 browser/chromium/scripts/check-browser-local-ai-workloads.py --workloads examples/browser-local-ai-workloads.sample.json && python3 browser/chromium/scripts/build-browser-pipeline-cache-receipts.py --workloads examples/browser-local-ai-workloads.sample.json --out /tmp/browser-pipeline-cache-receipts.json && python3 browser/chromium/scripts/check-browser-fallback-explanations.py --explanations examples/browser-fallback-explanations.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser gate emits recovery parity evidence

The promoted browser diagnostic gate now asks the smoke runner to emit
`browser_recovery_parity` and validates it before accepting the gate report.
Gate output records the recovery parity path, recovery parity hash, and
`recoveryParityOk` status alongside smoke, CTS subset, and layered evidence.

Touched:

- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `docs/process.md`

Verified:

- `python3 -m py_compile bench/browser/browser_gate.py browser/chromium/scripts/check-browser-recovery-parity.py browser/chromium/scripts/build-browser-recovery-parity.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_browser_recovery_parity.py -q`
- `python3 browser/chromium/scripts/check-browser-recovery-parity.py --parity examples/browser-recovery-parity.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser gates enforce capture policy

The single-window browser gate now runs the browser capture-policy checker
before browser preflight. The repeated browser claim gate checks the same policy
before accepting new or reused windows and forwards the policy path to each
browser-gate window. Gate reports and claim reports record the policy path used
for origin scope, raw-page-data handling, replay permission, and developer
visibility.

Touched:

- `bench/browser/browser_gate.py`
- `bench/browser/browser_claim_gate.py`
- `docs/process.md`

Verified:

- `python3 -m py_compile bench/browser/browser_gate.py bench/browser/browser_claim_gate.py bench/tools/check_browser_capture_policy.py`
- `python3 bench/tools/check_browser_capture_policy.py --policy config/browser-capture-policy.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_capture_policy.py bench/tests/test_browser_gate.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser release bundles require claim policy binding

Browser release artifact bundle checks now require the browser claim policy
artifact in addition to runtime-selector and fork-maintenance policies. This
keeps a release bundle from hash-binding claim reports without also binding the
policy that made those reports promotable.

Touched:

- `bench/tools/check_browser_release_artifact_bundle.py`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `examples/browser-release-artifact-bundle.sample.json`

Verified:

- `python3 -m py_compile bench/tools/check_browser_release_artifact_bundle.py bench/tools/build_browser_release_artifact_bundle.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py -q`
- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `git diff --check`

## 2026-05-26 — Browser gates enforce fork maintenance policy

The single-window browser gate now runs the Chromium fork-maintenance policy
checker before browser preflight. The repeated browser claim gate checks the
same policy before accepting new or reused windows and forwards the policy path
to each browser-gate window. Gate reports and claim reports record the policy
path used for fork isolation, Dawn rollback, and release artifact requirements.

Touched:

- `bench/browser/browser_gate.py`
- `bench/browser/browser_claim_gate.py`
- `docs/process.md`

Verified:

- `python3 -m py_compile bench/browser/browser_gate.py bench/browser/browser_claim_gate.py bench/tools/check_chromium_fork_maintenance_policy.py`
- `python3 bench/tools/check_chromium_fork_maintenance_policy.py --policy config/chromium-fork-maintenance-policy.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_chromium_fork_maintenance_policy.py bench/tests/test_browser_gate.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser gate emits CTS subset evidence

The promoted browser diagnostic gate now asks the smoke runner to emit a paired
`browser_cts_subset` artifact and validates it before accepting the gate report.
Gate output records the CTS subset path, CTS subset hash, and `ctsSubsetOk`
status alongside smoke and layered evidence.

Touched:

- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `docs/process.md`
- `browser/chromium/README.md`

Verified:

- `python3 -m py_compile bench/browser/browser_gate.py browser/chromium/scripts/check-browser-cts-subset.py browser/chromium/scripts/build-browser-cts-subset.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_browser_cts_subset.py -q`
- `python3 browser/chromium/scripts/check-browser-cts-subset.py --subset examples/browser-cts-subset.sample.json`
- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `bash -n browser/chromium/scripts/run-with-lane-defaults.sh browser/chromium/scripts/run-smoke.sh browser/chromium/scripts/run-bench.sh`
- `git diff --check`

## 2026-05-26 — Browser superset wrapper accepts selector auto mode

The browser layered superset wrapper and checker now accept diagnostic
`--mode auto`. Auto-mode reports validate the selector decision as
`selectionMode=auto` with a concrete selected runtime, visible fallback reason
codes, and selected-runtime artifact identity. Lane wrappers no longer block
auto diagnostics when the Doe runtime artifact is absent; forced `doe` and
`both` paths still fail closed before execution.

Touched:

- `browser/chromium/scripts/run-with-lane-defaults.sh`
- `browser/chromium/scripts/run-browser-benchmark-superset.py`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `bench/tests/test_browser_doe_lib_defaults.py`
- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `browser/chromium/README.md`
- `bench/README.md`

Verified:

- `bash -n browser/chromium/scripts/run-with-lane-defaults.sh browser/chromium/scripts/run-bench.sh browser/chromium/scripts/run-smoke.sh`
- `python3 -m py_compile browser/chromium/scripts/run-browser-benchmark-superset.py browser/chromium/scripts/check-browser-benchmark-superset.py bench/browser/browser_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_benchmark_superset_checker.py bench/tests/test_browser_doe_lib_defaults.py -q`
- `python3 browser/chromium/scripts/run-browser-benchmark-superset.py --mode auto --doe-lib /tmp/does-not-exist-libwebgpu_doe_full.so --dry-run`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`
- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-runtime-selector-policy.py --policy config/browser-runtime-selector-policy.json`
- `git diff --check`

## 2026-05-26 — Browser auto selection supports profile denylist fallback

The shared browser runtime selector now normalizes a runtime profile, emits it
inside every `runtimeSelection`, and applies the policy denylist in diagnostic
`auto` mode. A denylisted profile selects Dawn with `profile_denylisted`.
Browser gate checks now require profile observability fields so selector
reports match the policy's required observability contract.

Touched:

- `browser/chromium/scripts/browser-runtime-selector.mjs`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `bench/browser/browser_gate.py`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `bench/tests/test_browser_runtime_selector_mjs.py`
- `bench/tests/test_browser_gate.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `browser/chromium/contracts/runtime-selector-and-fallback.contract.md`

Verified:

- `node --check browser/chromium/scripts/browser-runtime-selector.mjs browser/chromium/scripts/webgpu-playwright-smoke.mjs browser/chromium/scripts/webgpu-playwright-layered-bench.mjs browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `python3 -m py_compile bench/browser/browser_gate.py browser/chromium/scripts/check-browser-benchmark-superset.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`

## 2026-05-26 — Browser runners support policy-backed auto selection

The browser Playwright smoke, layered, and ORT diagnostic runners now accept
`--mode auto` and read `config/browser-runtime-selector-policy.json`. Auto mode
selects Dawn with `global_disable_active` when the configured kill switch is set,
selects Dawn with `runtime_artifact_missing` when the Doe runtime artifact is
absent, and selects Doe when the runtime artifact is available. Forced `dawn`
and `doe` modes keep fail-closed forced-mode semantics.

Touched:

- `browser/chromium/scripts/browser-runtime-selector.mjs`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `bench/tests/test_browser_runtime_selector_mjs.py`
- `browser/chromium/contracts/runtime-selector-and-fallback.contract.md`

Verified:

- `node --check browser/chromium/scripts/browser-runtime-selector.mjs browser/chromium/scripts/webgpu-playwright-smoke.mjs browser/chromium/scripts/webgpu-playwright-layered-bench.mjs browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_runtime_selector_mjs.py bench/tests/test_browser_smoke_flight_recorder_flags.py bench/tests/test_browser_ort_runtime_selection.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`

## 2026-05-26 — Browser reports expose workload identity

Browser smoke, layered, and ORT diagnostics now emit a top-level
`workloadIdentity` block. Smoke reports hash the smoke workload suite, layered
reports bind the source workload/projection/workflow manifests, and ORT reports
hash the selected task config. The browser gate and benchmark-superset checker
reject reports without workload identity.

Touched:

- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `bench/tests/test_browser_ort_runtime_selection.py`
- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `browser/chromium/contracts/browser-claim-methodology.contract.md`

Verified:

- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs browser/chromium/scripts/webgpu-playwright-layered-bench.mjs browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `python3 -m py_compile browser/chromium/scripts/check-browser-benchmark-superset.py bench/browser/browser_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`

## 2026-05-26 — Browser gates run the runtime selector policy check

The single-window browser gate now runs the runtime-selector policy checker
before browser preflight, and the repeated browser claim gate checks the same
policy before accepting new or reused windows. Gate reports and claim reports
record the runtime-selector policy path used for the run.

Touched:

- `bench/browser/browser_gate.py`
- `bench/browser/browser_claim_gate.py`
- `bench/README.md`
- `browser/chromium/README.md`
- `docs/process.md`

Verified:

- `python3 -m py_compile bench/browser/browser_gate.py bench/browser/browser_claim_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_*.py -q`

## 2026-05-26 — Browser mode evidence requires trace hash fields

Browser report gates now require per-mode trace hash fields. Smoke and layered
diagnostics already emitted mode hash chains; ORT browser diagnostics now emit
the same `previousHash`/`hash` chain and a report hash. The browser gate and
benchmark-superset checker reject mode evidence without trace hashes.

Touched:

- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `bench/tests/test_browser_ort_runtime_selection.py`
- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `browser/chromium/contracts/browser-claim-methodology.contract.md`

Verified:

- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs browser/chromium/scripts/webgpu-playwright-layered-bench.mjs browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `python3 -m py_compile browser/chromium/scripts/check-browser-benchmark-superset.py bench/browser/browser_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_browser_benchmark_superset_checker.py bench/tests/test_browser_ort_runtime_selection.py -q`

## 2026-05-26 — Browser reports bind shader compiler identity

Browser smoke, layered, and ORT diagnostics now emit
`shaderCompilerIdentity` per mode. Dawn mode binds the compiler surface to the
Dawn/Chromium runtime artifact hash, while Doe mode binds it to the Doe runtime
library hash. The browser gate and benchmark-superset checker reject reports
that omit shader-compiler identity.

Touched:

- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `bench/tests/test_browser_ort_runtime_selection.py`
- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `browser/chromium/contracts/browser-claim-methodology.contract.md`

Verified:

- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs browser/chromium/scripts/webgpu-playwright-layered-bench.mjs browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `python3 -m py_compile browser/chromium/scripts/check-browser-benchmark-superset.py bench/browser/browser_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_browser_benchmark_superset_checker.py bench/tests/test_browser_ort_runtime_selection.py -q`

## 2026-05-26 — Browser reports hash adapter identity

Browser smoke, layered, and ORT diagnostics now emit stable adapter identity
digests instead of relying on raw `adapterInfo` alone. The browser gate and
benchmark-superset checker reject an available adapter when the adapter identity
digest is missing, so browser-lane evidence identifies both the runtime
artifacts and the adapter surface used for the run.

Touched:

- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `bench/browser/browser_gate.py`
- `bench/tests/test_browser_gate.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`
- `bench/tests/test_browser_ort_runtime_selection.py`
- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `browser/chromium/contracts/browser-claim-methodology.contract.md`

Verified:

- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs browser/chromium/scripts/webgpu-playwright-layered-bench.mjs browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `python3 -m py_compile browser/chromium/scripts/check-browser-benchmark-superset.py bench/browser/browser_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py bench/tests/test_browser_benchmark_superset_checker.py bench/tests/test_browser_ort_runtime_selection.py -q`

## 2026-05-26 — Browser runtime identity records the Dawn fallback runtime

Browser runtime-selection evidence now names the Dawn fallback runtime
explicitly instead of relying on a generic runtime identity slot. Smoke,
layered, and ORT browser runners emit `artifactIdentity.dawnRuntimePath` and
`artifactIdentity.dawnRuntimeSha256`, while the browser gate and superset
checker reject reports that omit the Dawn fallback hash. The selector policy now
requires concrete browser executable, Doe runtime, Dawn fallback runtime,
fallback-state, and launch-argument observability fields.

Touched:

- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `browser/chromium/scripts/check-browser-runtime-selector-policy.py`
- `bench/browser/browser_gate.py`
- `config/browser-runtime-selector-policy.json`
- `config/browser-runtime-selector-policy.schema.json`
- `browser/chromium/contracts/runtime-selector-and-fallback.contract.md`
- `browser/chromium/contracts/browser-claim-methodology.contract.md`

Verified:

- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs browser/chromium/scripts/webgpu-playwright-layered-bench.mjs browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `python3 -m py_compile browser/chromium/scripts/check-browser-runtime-selector-policy.py browser/chromium/scripts/check-browser-benchmark-superset.py bench/browser/browser_gate.py`
- `python3 browser/chromium/scripts/check-browser-runtime-selector-policy.py --policy config/browser-runtime-selector-policy.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_runtime_selector_policy.py bench/tests/test_browser_gate.py bench/tests/test_browser_benchmark_superset_checker.py bench/tests/test_browser_ort_runtime_selection.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Browser responsibility map rejects stale claim bindings

The browser responsibility map now has a repo tool and gate wiring that enforce
the contract beyond schema shape. It checks required CPU/GPU entries, required
claim-candidate binding fields, claim-binding path existence, boundary endpoint
references, and scope-status values before a map can support browser claim
language. The single-window browser gate and repeated browser claim gate both
run the check, including repeated-claim reuse mode.

Touched:

- `bench/tools/check_browser_responsibility_map.py`
- `bench/browser/browser_gate.py`
- `bench/browser/browser_claim_gate.py`
- `bench/tests/test_browser_responsibility_map.py`
- `browser/chromium/contracts/browser-responsibility-map.contract.md`
- `bench/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `python3 -m py_compile bench/tools/check_browser_responsibility_map.py`
- `python3 -m py_compile bench/browser/browser_gate.py bench/browser/browser_claim_gate.py`
- `python3 bench/tools/check_browser_responsibility_map.py --map config/browser-responsibility-map.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_responsibility_map.py -q`

## 2026-05-26 — Browser flight recorder enforces capture policy at build time

The browser GPU flight-recorder builder now reads the browser capture policy
and normalizes unsafe component privacy input before emitting the artifact.
Origin-scope violations, raw page data, and explicit debug capture requests are
reported as typed `browser_policy` failures while the emitted privacy block
stays schema-valid and hash/redaction-only.
The browser flight replay report also records its capture-policy path and
rejects replay when the `flight_replay` surface is not developer-visible,
replay-enabled, and gated by secure-context DevTools opt-in.

Touched:

- `browser/chromium/scripts/build-browser-gpu-flight-recorder.py`
- `browser/chromium/scripts/replay-browser-gpu-flight-recorder.py`
- `browser/chromium/contracts/browser-gpu-flight-recorder.contract.md`
- `config/browser-gpu-flight-replay.schema.json`
- `examples/browser-gpu-flight-replay.sample.json`
- `bench/tests/test_browser_gpu_flight_recorder_contract.py`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gpu_flight_recorder_contract.py -q`
- `python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --capture-policy config/browser-capture-policy.json`

## 2026-05-26 — Browser release and claim promotion receipts are generated

Browser promotion evidence now has producers in addition to schemas and
checkers. The repeated browser claim gate writes a
`browser_claim_promotion_receipt` next to the claim report, so forced-Doe,
claim-policy pass, and hidden-fallback evidence are captured as a generated
artifact. Release bundle construction now has a deterministic builder that
hash-binds the browser binary, Doe runtime, shader compiler, contracts, claim
reports, and policies. Both checkers can verify referenced file hashes when
the artifact files are available.

Touched:

- `bench/tools/build_browser_claim_promotion_receipt.py`
- `bench/tools/build_browser_release_artifact_bundle.py`
- `bench/tools/check_browser_claim_promotion_receipt.py`
- `bench/tools/check_browser_release_artifact_bundle.py`
- `bench/browser/browser_claim_gate.py`
- `bench/tests/test_browser_claim_promotion_receipt.py`
- `bench/tests/test_browser_release_artifact_bundle.py`
- `browser/chromium/README.md`
- `docs/process.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `python3 -m py_compile bench/tools/build_browser_claim_promotion_receipt.py bench/tools/build_browser_release_artifact_bundle.py bench/browser/browser_claim_gate.py bench/tools/check_browser_claim_promotion_receipt.py bench/tools/check_browser_release_artifact_bundle.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_claim_promotion_receipt.py bench/tests/test_browser_release_artifact_bundle.py -q`

## 2026-05-26 — Browser smoke emits CTS subset diagnostics

The Playwright smoke lane can now materialize `browser_cts_subset` from paired
Dawn and forced-Doe mode results. The builder projects smoke evidence into the
declared CTS buckets as diagnostic browser-lane evidence; it does not replace
real CTS execution, but it keeps paired browser CTS artifacts schema-backed
while the browser CTS runner is still outside the repo lane.

Touched:

- `browser/chromium/scripts/build-browser-cts-subset.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_cts_subset.py`
- `bench/tests/test_browser_smoke_flight_recorder_flags.py`
- `browser/chromium/contracts/browser-cts-subset.contract.md`
- `browser/chromium/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_cts_subset.py bench/tests/test_browser_smoke_flight_recorder_flags.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-cts-subset.py --report <browser-smoke-both.json> --out <browser-cts-subset.json>`
- `python3 browser/chromium/scripts/check-browser-cts-subset.py --subset <browser-cts-subset.json>`

## 2026-05-26 — Browser smoke emits fallback explanations

The Playwright smoke lane can now materialize
`browser_fallback_explanations` from the selected mode result plus any
companion artifacts emitted in the same smoke run. Missing companion artifacts
become typed unsupported rows with developer actions that name the required
smoke flag, keeping fallback visibility explicit instead of implicit.

Touched:

- `browser/chromium/scripts/build-browser-fallback-explanations.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_fallback_explanations.py`
- `bench/tests/test_browser_smoke_flight_recorder_flags.py`
- `browser/chromium/contracts/browser-fallback-explanations.contract.md`
- `browser/chromium/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_fallback_explanations.py bench/tests/test_browser_smoke_flight_recorder_flags.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-fallback-explanations.py --report <browser-smoke.json> --mode doe --out <browser-fallback-explanations.json>`
- `python3 browser/chromium/scripts/check-browser-fallback-explanations.py --explanations <browser-fallback-explanations.json>`

## 2026-05-26 — Browser smoke can emit pipeline cache receipts

The Playwright smoke lane can now build `browser_pipeline_cache_receipts`
immediately after optional local-AI workload emission. The smoke CLI requires
`--pipeline-cache-receipts-out` to be paired with `--local-ai-workloads-out`,
so cache hit/miss and pipeline creation receipts stay anchored to the generated
workload artifact.

Touched:

- `browser/chromium/scripts/build-browser-pipeline-cache-receipts.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_smoke_flight_recorder_flags.py`
- `browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_smoke_flight_recorder_flags.py bench/tests/test_browser_pipeline_cache_receipts.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-pipeline-cache-receipts.py --workloads <browser-local-ai-workloads.json> --out <browser-pipeline-cache-receipts.json>`

## 2026-05-26 — Browser smoke can emit shader links from flight recorder output

The Playwright smoke lane can now build `browser_shader_links` immediately
after optional flight-recorder emission. The smoke CLI requires
`--shader-links-out` to be paired with `--flight-recorder-out`, so shader
provenance stays anchored to the generated capture artifact rather than a
detached path.

Touched:

- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_smoke_flight_recorder_flags.py`
- `browser/chromium/contracts/browser-shader-links.contract.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_smoke_flight_recorder_flags.py bench/tests/test_browser_shader_links.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-shader-links.py --flight-recorder <flight-recorder.json> --out <shader-links.json>`

## 2026-05-26 — Browser smoke emits local AI workload artifacts

The Playwright smoke lane can now materialize `browser_local_ai_workloads`
from selected mode results. The builder maps compute smoke evidence into the
required embedding, ranking, image transform, video transform, and model
inference rows, hashes model/shader/input/output identity, and preserves the
no-hidden-fallback contract for downstream cache receipts.

Touched:

- `browser/chromium/scripts/build-browser-local-ai-workloads.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_local_ai_workloads.py`
- `browser/chromium/contracts/browser-local-ai-workloads.contract.md`
- `browser/chromium/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_local_ai_workloads.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-local-ai-workloads.py --report <browser-smoke.json> --mode doe --out <browser-local-ai-workloads.json>`
- `python3 browser/chromium/scripts/check-browser-local-ai-workloads.py --workloads <browser-local-ai-workloads.json>`

## 2026-05-26 — Browser smoke emits WebGPU effect experiments

The Playwright smoke lane can now materialize a
`browser_webgpu_effect_experiment` from selected mode results. The builder uses
the render smoke output as a WebGPU-backed visual-effect probe, keeps layout,
accessibility, and security ownership explicitly browser-owned, and emits
typed diagnostic rows where smoke does not prove frame timing or browser
ownership boundaries.

Touched:

- `browser/chromium/scripts/build-browser-webgpu-effect-experiment.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_webgpu_effect_experiment.py`
- `browser/chromium/contracts/browser-webgpu-effect-experiment.contract.md`
- `browser/chromium/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_webgpu_effect_experiment.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-webgpu-effect-experiment.py --report <browser-smoke.json> --mode doe --out <browser-webgpu-effect-experiment.json>`
- `python3 browser/chromium/scripts/check-browser-webgpu-effect-experiment.py --experiment <browser-webgpu-effect-experiment.json>`

## 2026-05-26 — Browser smoke emits GPU scheduler probes

The Playwright smoke lane can now materialize a
`browser_gpu_scheduler_probe` from selected mode results. The builder binds the
required WebGPU, canvas, video, CSS effects, local AI, and compositor-adjacent
work classes, carries runtime identity, maps device-loss evidence, and keeps
unmeasured scheduling behavior as typed diagnostic rows.

Touched:

- `browser/chromium/scripts/build-browser-gpu-scheduler.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_gpu_scheduler.py`
- `browser/chromium/contracts/browser-gpu-scheduler.contract.md`
- `browser/chromium/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gpu_scheduler.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-gpu-scheduler.py --report <browser-smoke.json> --mode doe --out <browser-gpu-scheduler.json>`
- `python3 browser/chromium/scripts/check-browser-gpu-scheduler.py --probe <browser-gpu-scheduler.json>`

## 2026-05-26 — Browser ORT reports carry runtime selector identity

The browser ORT workload runner now emits the same runtime selector identity
surface as the smoke and layered browser lanes. Each mode result records forced
runtime mode, hidden-fallback denial, browser executable hash, Doe library hash
for forced Doe, selector version, and launch-argument hash.

Touched:

- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`
- `bench/tests/test_browser_ort_runtime_selection.py`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_ort_runtime_selection.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`

## 2026-05-26 — Browser smoke emits canvas/WebGPU fusion probes

The Playwright smoke lane can now materialize a
`browser_canvas_webgpu_fusion_probe` from selected mode results. The builder
binds canvas 2D, WebGPU render, image-filter, and presentation surfaces to a
visible graph, hashes the presentation output, carries timing scopes, and emits
per-surface fallback reasons.

Touched:

- `browser/chromium/scripts/build-browser-canvas-webgpu-fusion.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_canvas_webgpu_fusion.py`
- `browser/chromium/contracts/browser-canvas-webgpu-fusion.contract.md`
- `browser/chromium/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_canvas_webgpu_fusion.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-canvas-webgpu-fusion.py --report <browser-smoke.json> --mode doe --out <canvas-webgpu-fusion.json>`
- `python3 browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py --probe <canvas-webgpu-fusion.json>`

## 2026-05-26 — Browser smoke emits recovery parity artifacts

The Playwright smoke lane now records validation-error capture,
`device.lost` surface availability, and post-diagnostic compute recovery. A
new builder converts paired Dawn/Doe smoke output into a schema-backed
`browser_recovery_parity` artifact; crash and hang remain typed diagnostic rows
until a harness exercises those cases directly.

Touched:

- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/build-browser-recovery-parity.py`
- `bench/tests/test_browser_recovery_parity.py`
- `browser/chromium/contracts/browser-recovery-parity.contract.md`
- `browser/chromium/README.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_recovery_parity.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-recovery-parity.py --report <browser-smoke-both.json> --out <recovery-parity.json>`
- `python3 browser/chromium/scripts/check-browser-recovery-parity.py --parity <recovery-parity.json>`

## 2026-05-26 — Browser smoke emits media path probes

The Playwright smoke lane can now materialize a schema-backed
`browser_media_path_probe` from real smoke results. The builder extracts
`copyExternalImageToTexture` and `importExternalTexture` output digests from a
selected mode and records shared texture import as typed unsupported evidence
when the smoke report does not exercise that path.

Touched:

- `browser/chromium/scripts/build-browser-media-path-probe.py`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `bench/tests/test_browser_media_path_probe.py`
- `browser/chromium/contracts/browser-media-path-probe.contract.md`
- `docs/chromium-webgpu-task-list.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_media_path_probe.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `python3 browser/chromium/scripts/build-browser-media-path-probe.py --report <smoke-report.json> --mode doe --out <media-path-probe.json>`
- `python3 browser/chromium/scripts/check-browser-media-path-probe.py --probe <media-path-probe.json>`

## 2026-05-26 — Blocking runner enforces compare output partitioning

The canonical blocking runner now runs `compare_output_partition_gate.py` by
default. Claim-gate runs cannot disable it, so diagnostic rows cannot slip into
claimable compare output through the standard gate sequence.

Touched:

- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `docs/process.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_run_blocking_gates_wiring.py bench/tests/test_compare_output_partition_gate.py -q`

## 2026-05-26 — Browser superset checker validates runtime selector identity

The browser benchmark superset checker now rejects required-mode report rows
that lack forced-mode runtime selector evidence, browser executable hashes, Doe
library hashes, or hidden-fallback denial.

Touched:

- `browser/chromium/scripts/check-browser-benchmark-superset.py`
- `bench/tests/test_browser_benchmark_superset_checker.py`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_benchmark_superset_checker.py -q`

## 2026-05-26 — Browser lane defaults prefer the full Doe WebGPU library

Browser smoke, layered, ORT, and superset lane wrappers now resolve
`libwebgpu_doe_full` before the compute-only `libwebgpu_doe` default.

Touched:

- `browser/chromium/scripts/run-browser-benchmark-superset.py`
- `browser/chromium/scripts/lane-paths.sh`
- `browser/chromium/scripts/patch-chromium-app-doe.sh`
- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_doe_lib_defaults.py -q`

## 2026-05-26 — Native command graph receipts include submit and bind group identity

Native command graph receipts now use `schemaVersion=2` and carry submit
identity plus per-command bind group references:

- `config/native-command-graph-receipt.schema.json`
- `bench/tools/build_native_command_graph_receipt.py`
- `bench/tools/replay_native_command_graph_receipt.py`

The builder records `submitId`, `bindGroupRefs`, graph-level `bindGroups`, and
`summary.submitCount`. The replay checker rejects hash-chain drift, submit-count
drift, and bind-group set drift.

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_command_graph_receipt.py -q`
- `python3 bench/gates/schema_gate.py`

## 2026-05-26 — Browser claim promotion receipt checks forced-Doe windows

Browser claim promotion now has a schema-backed receipt:

- `config/browser-claim-promotion-receipt.schema.json`
- `examples/browser-claim-promotion-receipt.sample.json`
- `bench/tools/check_browser_claim_promotion_receipt.py`

The checker requires promotion artifacts to be forced-Doe runs, rejects hidden
fallback, requires each artifact to pass the browser claim policy, and requires
the hidden-fallback check to pass before a receipt can be promotable.

Verified:

- `python3 bench/tools/check_browser_claim_promotion_receipt.py --receipt examples/browser-claim-promotion-receipt.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_claim_promotion_receipt.py -q`

## 2026-05-26 — Browser release artifact bundle is schema-backed

Browser release evidence now has a schema-backed artifact bundle:

- `config/browser-release-artifact-bundle.schema.json`
- `examples/browser-release-artifact-bundle.sample.json`
- `bench/tools/check_browser_release_artifact_bundle.py`

The checker requires hash-bound browser binary, Doe runtime, shader compiler,
contract, browser claim report, runtime selector policy, and fork maintenance
policy artifacts. Release-candidate bundles cannot carry failure codes.

Verified:

- `python3 bench/tools/check_browser_release_artifact_bundle.py --bundle examples/browser-release-artifact-bundle.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_release_artifact_bundle.py -q`

## 2026-05-26 — Chromium fork maintenance policy is schema-backed

Chromium fork maintenance, rollback, and release artifact requirements now have
a schema-backed policy:

- `config/chromium-fork-maintenance-policy.schema.json`
- `config/chromium-fork-maintenance-policy.json`
- `bench/tools/check_chromium_fork_maintenance_policy.py`

The checker keeps Doe-owned patch roots separate from the local Chromium
checkout, requires a Dawn fallback path and kill-switch policy for rollback, and
requires release artifacts to bind the browser binary, Doe runtime, compiler,
and claim report.

Verified:

- `python3 bench/tools/check_chromium_fork_maintenance_policy.py --policy config/chromium-fork-maintenance-policy.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_chromium_fork_maintenance_policy.py -q`

## 2026-05-26 — Browser capture policy gates replay and raw data

Developer-visible browser capture and replay surfaces now have a schema-backed
policy:

- `config/browser-capture-policy.schema.json`
- `config/browser-capture-policy.json`
- `bench/tools/check_browser_capture_policy.py`

The checker requires capture surfaces to be origin-scoped, gates replay behind
secure-context developer opt-in, forbids raw page data unless it is hashed or
redacted, and requires a reason for developer-visible surfaces that do not
support replay.

Verified:

- `python3 bench/tools/check_browser_capture_policy.py --policy config/browser-capture-policy.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_capture_policy.py -q`

## 2026-05-26 — Native backend coverage matrix is explicit

Native backend workload coverage now has a schema-backed matrix:

- `config/native-backend-coverage-matrix.schema.json`
- `config/native-backend-coverage-matrix.json`
- `bench/tools/check_native_backend_coverage_matrix.py`

The checker requires every Doe native backend to declare upload, pipeline
creation, compute, readback, small command stream, cache behavior, concurrency,
and tail coverage. Covered rows require evidence paths; diagnostic and missing
rows require reason codes.

Verified:

- `python3 bench/tools/check_native_backend_coverage_matrix.py --matrix config/native-backend-coverage-matrix.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_backend_coverage_matrix.py -q`

## 2026-05-26 — Native resource reuse receipts preserve semantics

Command encoder and resource reuse now have a schema-backed receipt contract:

- `config/native-resource-reuse-receipts.schema.json`
- `examples/native-resource-reuse-receipts.sample.json`
- `bench/tools/check_native_resource_reuse_receipts.py`

The checker rejects reuse unless workload semantics allow it, keeps hidden
fallback disabled, and requires resource identity plus command order preservation
before a reused path can remain claim-eligible.

Verified:

- `python3 bench/tools/check_native_resource_reuse_receipts.py --receipts examples/native-resource-reuse-receipts.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_resource_reuse_receipts.py -q`

## 2026-05-26 — Native upload paths expose asymmetry before claims

Native upload path evidence now has a schema-backed receipt contract:

- `config/native-upload-path-receipts.schema.json`
- `examples/native-upload-path-receipts.sample.json`
- `bench/tools/check_native_upload_path_receipts.py`

The checker keeps strict comparable upload rows on the staging-copy path,
requires recorded copy commands for that path, rejects path-asymmetric rows
when they are claim-eligible, and requires an explicit note for hardware path
asymmetry.

Verified:

- `python3 bench/tools/check_native_upload_path_receipts.py --receipts examples/native-upload-path-receipts.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_upload_path_receipts.py -q`

## 2026-05-26 — Native pipeline cache receipts require cold and warm modes

Native pipeline cache behavior now has a schema-backed receipt contract:

- `config/native-pipeline-cache-receipts.schema.json`
- `examples/native-pipeline-cache-receipts.sample.json`
- `bench/tools/check_native_pipeline_cache_receipts.py`

The checker requires each workload to carry both cold and warm rows, rejects
warm rows that still report cache creation or miss states, rejects cold rows
that claim a cache hit, preserves hidden-fallback denial, and requires a note
whenever path asymmetry is present.

Verified:

- `python3 bench/tools/check_native_pipeline_cache_receipts.py --receipts examples/native-pipeline-cache-receipts.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_pipeline_cache_receipts.py -q`

## 2026-05-26 — Compare reports reject mixed claim and diagnostic output

Runtime compare reports now have a gate that keeps claimable rows separate from
diagnostic rows:

- `bench/gates/compare_output_partition_gate.py`
- `bench/tests/test_compare_output_partition_gate.py`

The gate rejects comparable top-level reports with comparability failures, rows
marked claim-eligible without comparable workload status, rows carrying
diagnostic comparability reasons while claim-eligible, and diagnostic benchmark
rows marked claim-eligible.

Verified:

- `python3 bench/gates/compare_output_partition_gate.py --report examples/compare-report.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_compare_output_partition_gate.py -q`

## 2026-05-26 — Strict native no-fallback reports are schema-backed

Strict native Doe run receipts can now be collected into a no-fallback report:

- `config/native-no-fallback-report.schema.json`
- `examples/native-no-fallback-report.sample.json`
- `bench/tools/build_native_no_fallback_report.py`

The report requires `product=doe`, `runtimeHost=native`, a `doe_*` execution
backend, and no per-sample fallback marker. Rows that fail those checks remain
non-promotable and carry typed failure codes.

Verified:

- `python3 bench/tools/build_native_no_fallback_report.py --run-receipt examples/run-receipt.sample.json --out /tmp/native-no-fallback-report.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_no_fallback_report.py -q`

## 2026-05-26 — Native command graph receipts are replay-checkable

Native runtime runs can now be converted into a schema-backed command graph
receipt:

- `config/native-command-graph-receipt.schema.json`
- `examples/native-command-graph-receipt.sample.json`
- `bench/tools/build_native_command_graph_receipt.py`
- `bench/tools/replay_native_command_graph_receipt.py`

The builder binds a run receipt, command JSON, runtime identity, buffers,
textures, pipelines, normalized command rows, command counts, and a deterministic
row hash chain. The replay checker recomputes the hash chain and rejects row,
sequence, terminal-hash, or command-count drift.

Verified:

- `python3 bench/tools/build_native_command_graph_receipt.py --run-receipt examples/run-receipt.sample.json --commands examples/kernel_dispatch_commands.json --out /tmp/native-command-graph.json`
- `python3 bench/tools/replay_native_command_graph_receipt.py --receipt /tmp/native-command-graph.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_native_command_graph_receipt.py -q`

## 2026-05-26 — Browser CTS subset artifact is schema-backed

The browser seam lane now has a browser-level CTS subset contract for paired
Dawn and forced-Doe evidence:

- `browser/chromium/contracts/browser-cts-subset.contract.md`
- `config/browser-cts-subset.schema.json`
- `examples/browser-cts-subset.sample.json`
- `browser/chromium/scripts/check-browser-cts-subset.py`

The structural checker requires Dawn and forced-Doe artifact paths, browser CTS
bucket coverage, typed reason codes for diagnostic or mismatch rows, parity
status discipline, and no hidden fallback.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-cts-subset.py --subset examples/browser-cts-subset.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_cts_subset.py -q`

## 2026-05-26 — Browser runtime selector policy is schema-backed

The browser runtime selector now has a schema-backed policy artifact:

- `config/browser-runtime-selector-policy.schema.json`
- `config/browser-runtime-selector-policy.json`
- `browser/chromium/scripts/check-browser-runtime-selector-policy.py`

The checker requires exact `dawn`, `doe`, and `auto` selection modes, emergency
kill-switch precedence, the typed fallback taxonomy, denylist reason discipline,
forced-Doe fail-closed behavior, and selector observability fields.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-runtime-selector-policy.py --policy config/browser-runtime-selector-policy.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_runtime_selector_policy.py -q`

## 2026-05-26 — Browser recovery parity checks are schema-backed

The browser seam lane now has a Dawn-vs-Doe recovery parity contract:

- `browser/chromium/contracts/browser-recovery-parity.contract.md`
- `config/browser-recovery-parity.schema.json`
- `examples/browser-recovery-parity.sample.json`
- `browser/chromium/scripts/check-browser-recovery-parity.py`

The structural checker requires crash, hang, device-loss, validation-error, and
recovery case coverage, matching status discipline for parity rows, typed reason
codes for diagnostic or mismatch rows, and no hidden fallback in forced-Doe
mode.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-recovery-parity.py --parity examples/browser-recovery-parity.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_recovery_parity.py -q`

## 2026-05-26 — Browser media path probes are schema-backed

The browser seam lane now has an external texture and media-path probe
contract:

- `browser/chromium/contracts/browser-media-path-probe.contract.md`
- `config/browser-media-path-probe.schema.json`
- `examples/browser-media-path-probe.sample.json`
- `browser/chromium/scripts/check-browser-media-path-probe.py`

The structural checker requires `GPUExternalTexture`,
`copyExternalImageToTexture`, and shared texture/import probe coverage with
media digests, output digests, explicit fallback reasons, and no raw media in
the artifact.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-media-path-probe.py --probe examples/browser-media-path-probe.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_media_path_probe.py -q`

## 2026-05-26 — Browser fallback explanations are schema-backed

The browser capability lane now has a developer-visible unsupported-capability
and fallback explanation contract:

- `browser/chromium/contracts/browser-fallback-explanations.contract.md`
- `config/browser-fallback-explanations.schema.json`
- `examples/browser-fallback-explanations.sample.json`
- `browser/chromium/scripts/check-browser-fallback-explanations.py`

The structural checker requires reason codes, developer actions, evidence
paths, no hidden fallback, and matching `fallback` status whenever fallback is
applied.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-fallback-explanations.py --explanations examples/browser-fallback-explanations.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_fallback_explanations.py -q`

## 2026-05-26 — Browser pipeline cache receipts are schema-backed

The browser capability lane now has a developer-visible cache hit/miss and
pipeline creation receipt contract:

- `browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md`
- `config/browser-pipeline-cache-receipts.schema.json`
- `examples/browser-pipeline-cache-receipts.sample.json`
- `browser/chromium/scripts/build-browser-pipeline-cache-receipts.py`

The builder consumes browser local AI workload artifacts and emits one receipt
per workload cache row with workload identity, shader identity, cache key, cache
state, pipeline creation path, and fallback status.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/build-browser-pipeline-cache-receipts.py --workloads examples/browser-local-ai-workloads.sample.json --out /tmp/browser-pipeline-cache-receipts.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_pipeline_cache_receipts.py -q`

## 2026-05-26 — Browser local AI workload receipts are schema-backed

The browser capability lane now has a local AI workload and receipt contract:

- `browser/chromium/contracts/browser-local-ai-workloads.contract.md`
- `config/browser-local-ai-workloads.schema.json`
- `examples/browser-local-ai-workloads.sample.json`
- `browser/chromium/scripts/check-browser-local-ai-workloads.py`

The structural checker requires embeddings, ranking, image transforms, video
transforms, and model inference workload rows. Each row must carry model
identity, shader identity, pipeline cache state, input contract, output digest,
and fallback status.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-local-ai-workloads.py --workloads examples/browser-local-ai-workloads.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_local_ai_workloads.py -q`

## 2026-05-26 — Browser WebGPU effect experiment is schema-backed

The browser capability lane now has a contract for explicit WebGPU-backed
HTML/CSS visual effect experiments:

- `browser/chromium/contracts/browser-webgpu-effect-experiment.contract.md`
- `config/browser-webgpu-effect-experiment.schema.json`
- `examples/browser-webgpu-effect-experiment.sample.json`
- `browser/chromium/scripts/check-browser-webgpu-effect-experiment.py`

The structural checker requires every effect surface to be WebGPU-backed while
layout, accessibility, and security semantics remain browser-owned. It also
requires output-hash, semantics-boundary, fallback-behavior, frame-timing, and
security-policy probes.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-webgpu-effect-experiment.py --experiment examples/browser-webgpu-effect-experiment.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_webgpu_effect_experiment.py -q`

## 2026-05-26 — Browser GPU scheduler probe is schema-backed

The browser capability lane now has a page-level GPU scheduler probe contract:

- `browser/chromium/contracts/browser-gpu-scheduler.contract.md`
- `config/browser-gpu-scheduler.schema.json`
- `examples/browser-gpu-scheduler.sample.json`
- `browser/chromium/scripts/check-browser-gpu-scheduler.py`

The structural checker requires coverage for WebGPU, canvas, video, CSS
effects, local AI, and compositor-adjacent work classes, plus priority,
fairness, frame-deadline, origin-quota, device-loss, and fallback-behavior
probe kinds.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-gpu-scheduler.py --probe examples/browser-gpu-scheduler.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gpu_scheduler.py -q`

## 2026-05-26 — Browser shader links build from flight-recorder artifacts

Developer-visible shader links now have a contract, schema, sample artifact,
and builder:

- `browser/chromium/contracts/browser-shader-links.contract.md`
- `config/browser-shader-links.schema.json`
- `examples/browser-shader-links.sample.json`
- `browser/chromium/scripts/build-browser-shader-links.py`

The builder consumes a `browser_gpu_flight_recorder` artifact and emits
source-to-IR-to-backend shader links. Missing source, IR, or backend anchors
produce typed failures instead of partial developer links.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/build-browser-shader-links.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --out /tmp/browser-shader-links.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_shader_links.py -q`

## 2026-05-26 — Canvas/WebGPU fusion probe is schema-backed

The browser capability lane now has a canvas/WebGPU fusion probe contract:

- `browser/chromium/contracts/browser-canvas-webgpu-fusion.contract.md`
- `config/browser-canvas-webgpu-fusion.schema.json`
- `examples/browser-canvas-webgpu-fusion.sample.json`
- `browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py`

The probe shape binds canvas 2D, WebGPU, image-filter, and presentation surfaces
to responsibility-map entries, visible graph edges, output hashes, timing
scopes, fallback reasons, and an origin-scoped no-raw-page-data policy.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py --probe examples/browser-canvas-webgpu-fusion.sample.json`

## 2026-05-26 — Browser runtime identity surface is explicit

The package browser shim now exposes
`createBrowserRuntimeIdentity()` from `packages/doe-gpu/src/browser.js`.
Without a Chromium runtime-selection artifact, the identity reports the surface
as `browser_wrapper_probe` and keeps `doeRuntimeActive=false`. When a
runtime-selection artifact is supplied, the same shape can report a
Chromium-lane `dawn` or `doe` runtime decision without implying that the package
shim itself replaced `navigator.gpu`.

Schema and sample:

- `config/browser-runtime-identity.schema.json`
- `examples/browser-runtime-identity.sample.json`

Verified:

- `python3 bench/gates/schema_gate.py`
- `node packages/doe-gpu/test/unit/browser-runtime-identity.test.js`

## 2026-05-26 — Browser GPU flight recorder contract is schema-backed

The Chromium browser lane now has a page-level GPU flight-recorder contract and
sample artifact schema:

- `browser/chromium/contracts/browser-gpu-flight-recorder.contract.md`
- `config/browser-gpu-flight-recorder.schema.json`
- `examples/browser-gpu-flight-recorder.sample.json`

The contract binds browser runtime identity, adapter identity, the active browser
responsibility map, shader source/IR/backend hashes, bind groups, buffers,
textures, command graph, timings, frame hashes, typed failure codes, and capture
privacy policy before browser replay or developer-visible capture work can
promote. The builder requires an explicit component manifest for shader
source/IR/backend and graph fields, so compiler evidence is not synthesized from
browser timings. The Playwright smoke lane can now emit the artifact directly
when given `--flight-recorder-components`, `--flight-recorder-out`, and
`--flight-recorder-mode`.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 browser/chromium/scripts/build-browser-gpu-flight-recorder.py --report browser/chromium/artifacts/20260525T202040Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json --components examples/browser-gpu-flight-recorder.sample.json --out /tmp/browser-gpu-flight-recorder.prototype.json`
- `./browser/chromium/scripts/run-smoke.sh --mode doe --strict --upload-iters 1 --dispatch-iters 1 --out /tmp/browser-smoke-flight.diagnostic.json --flight-recorder-components examples/browser-gpu-flight-recorder.sample.json --flight-recorder-out /tmp/browser-smoke-flight-recorder.json --flight-recorder-mode doe`
- `python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder /tmp/browser-smoke-flight-recorder.json`
- `python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gpu_flight_recorder_contract.py -q`

## 2026-05-26 — Browser responsibility map is schema-backed

The Chromium browser lane now has a schema-backed responsibility map for the
task-list CPU/GPU boundary work:

- `config/browser-responsibility-map.schema.json`
- `config/browser-responsibility-map.json`
- `browser/chromium/contracts/browser-responsibility-map.contract.md`

The map separates browser CPU duties, GPU duties, and CPU/GPU crossings, then
classifies each surface with the task-list taxonomy. Every
`doe_claim_candidate` entry must name its contract, schema, workload source,
gate, and artifact path before claim language can route through that surface.

Verified:

- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_responsibility_map.py -q`

## 2026-05-26 — Benchmark artifact hashing is shared and streaming

Benchmark IR materialization, synthetic asset manifests, and report conformance
now use `bench/lib/hash_utils.py` for canonical JSON hashes and file hashes.
The shared file hash path streams artifact bytes instead of loading the whole
file into memory.

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_benchmark_ir.py bench/tests/test_synthetic_assets.py bench/tests/test_report_conformance.py -q`
- `python3 -m py_compile bench/lib/hash_utils.py bench/lib/benchmark_ir.py bench/lib/synthetic_assets.py bench/lib/report_conformance.py`

## 2026-05-26 — Compare reports use diagnostic for failed comparability

New Dawn-vs-Doe compare reports now classify failed comparability or coherence
as `comparisonStatus=diagnostic`. The schema, conformance checker, claim gate,
report builder, viewer styling, and regression tests now use the same two-status
comparison contract: `comparable` for claim-eligible evidence and `diagnostic`
for engineering evidence.

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_compare_from_artifacts.py bench/tests/test_report_conformance.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_config_schemas.py bench/tests/test_comparability_coherence_smoke_floor.py -q`
- `python3 bench/gates/schema_gate.py`

## 2026-05-25 — Schema gate no longer depends on local generated bench output

The schema gate now treats generated `bench/out/` data targets as optional when
the local artifact is absent, while still validating those artifacts when they
exist. The provenance sidecar contract keeps positive schema coverage through
`examples/doe-promoted-artifact-provenance.sample.json`, and provenance globs
that scan generated bundle sidecars are explicitly marked `allowEmpty`.

Verified:

- `python3 bench/gates/schema_gate.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_schema_gate.py bench/tests/test_config_schemas.py -q`

## 2026-05-25 — Native delegate identity is pinned in run receipts

Run receipts now unwrap `env` launchers before hashing the benchmark runner and
record `runtimeIdentity.nativeDelegate` for Dawn-backed native lanes when the
delegate WebGPU library is discoverable from the launch library path. This keeps
Dawn-vs-Doe evidence tied to both the shared runner binary and the delegated
Dawn library instead of hashing the shell wrapper.

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_run_artifact.py bench/tests/test_compare_from_artifacts.py bench/tests/test_report_conformance.py -q`
- `python3 bench/cli.py run-config --side comparison --config bench/native-compare/compare.config.apple.metal.release.json --workload-filter compute_concurrent_execution_single --out bench/out/apple-metal/identity-check/dawn-vs-doe.apple.metal.identity-check.json --workspace bench/out/apple-metal/identity-check/runtime-comparisons.apple.metal.identity-check`

## 2026-05-25 — Browser executable identity is pinned in diagnostics

Browser smoke and layered diagnostics now hash the resolved Chromium executable
for both Dawn and Doe modes. The browser gate requires
`artifactIdentity.browserExecutableSha256`, so browser evidence is tied to the
exact executable plus the Doe runtime library when Doe mode is selected.

Current refreshed evidence:

- `browser/chromium/artifacts/20260525T202040Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
- `browser/chromium/artifacts/20260525T202052Z/dawn-vs-doe.browser-layered.superset.diagnostic.json`
- `browser/chromium/artifacts/20260525T202052Z/dawn-vs-doe.browser-layered.superset.check.json`
- `browser/chromium/artifacts/20260525T202052Z/dawn-vs-doe.browser-layered.superset.summary.json`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gate.py -q`
- `node --check browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- `node --check browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- `./browser/chromium/scripts/preflight.sh --mode bench`
- `./browser/chromium/scripts/run-smoke.sh --mode both --strict`
- `./browser/chromium/scripts/run-bench.sh --mode both --strict-run`

## 2026-05-25 — Browser smoke and layered diagnostics refreshed

Fresh browser-lane diagnostics were generated through the wrapper entrypoints
after bench-mode preflight was tightened. Use the artifacts as the source of
truth for runtime identity, fallback state, required-row status, and browser
proxy timings:

- `browser/chromium/artifacts/20260525T192219Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
- `browser/chromium/artifacts/20260525T192228Z/dawn-vs-doe.browser-layered.superset.diagnostic.json`
- `browser/chromium/artifacts/20260525T192228Z/dawn-vs-doe.browser-layered.superset.check.json`
- `browser/chromium/artifacts/20260525T192228Z/dawn-vs-doe.browser-layered.superset.summary.json`

Verified:

- `./browser/chromium/scripts/run-smoke.sh --mode both --strict`
- `./browser/chromium/scripts/run-bench.sh --mode both`

## 2026-05-25 — Browser bench preflight fails closed on missing executors

The Chromium browser lane preflight now treats the resolved browser executable
and Doe runtime library as required in `--mode bench`. General/build preflight
still reports them as warnings, but a benchmark preflight no longer passes when
the run wrapper would fail immediately on missing paths.

Verified:

- `./browser/chromium/scripts/preflight.sh --mode bench`
- `FAWN_CHROME_BIN=/tmp/not-a-chromium FAWN_DOE_LIB=/tmp/not-a-doe-lib ./browser/chromium/scripts/preflight.sh --mode bench`
- `FAWN_CHROME_BIN=/tmp/not-a-chromium FAWN_DOE_LIB=/tmp/not-a-doe-lib ./browser/chromium/scripts/preflight.sh --mode general`

## 2026-05-25 — Apple Metal preflight checks executor artifacts

The local Apple Metal preflight now verifies the actual compare-lane executor
artifacts before a run can proceed:

- `runtime/zig/zig-out/bin/doe-zig-runtime`
- `bench/vendor/dawn/out/Release/libwebgpu_dawn.dylib`

The Dawn delegate library check also inspects the exported WebGPU C ABI symbols
required by the delegate lane. This prevents a host-only Metal toolchain smoke
from being treated as a runnable Doe-vs-Dawn compare preflight.

Verified:

- `python3 bench/runners/preflight_metal_host.py`
- `python3 -m pytest bench/tests/test_preflight_metal_host.py -q`

## 2026-05-25 — Apple Metal copy contracts enter the release claim lane

Apple Metal native Doe-vs-Dawn release evidence has been refreshed after the
copy transfer contracts were strengthened from diagnostic-only rows into
claim-eligible release rows.

- buffer-to-texture and texture-to-texture rows now use the governed release
  repeat/window contract instead of the previous smoke-sized window.
- the default texture-to-texture command fixture now uses the larger transfer
  shape used by the stronger copy fixtures instead of the tiny smoke fixture.
- both sides now run the copy rows with deferred queue sync, so the repeated
  copy stream is encoded as one drained workload unit.
- the release claim policy can still select workload-unit wall timing for copy
  rows whose per-copy operation timing is below the useful measurement floor.

Release artifacts:

- `bench/out/apple-metal/release/20260525T190747Z/runtime-comparisons.apple.metal.release/run-artifacts/doe/`
- `bench/out/apple-metal/release/20260525T190829Z/runtime-comparisons.apple.metal.release/run-artifacts/dawn_delegate/`
- `bench/out/apple-metal/release/20260525T190829Z/dawn-vs-doe.apple.metal.release.compare.json`
- `bench/out/apple-metal/release/20260525T190829Z/dawn-vs-doe.apple.metal.release.claim.json`

The broader local compare lane can still carry diagnostic/non-claim rows for
methodology auditing. Marketing or release claims should cite the release claim
artifact above.

## 2026-05-25 — Apple Metal release claim uses complete operation timing

Apple Metal native Doe-vs-Dawn release evidence has been refreshed after two
timing-scope fixes in the compare harness:

- render macro workloads now keep full operation timing instead of encode-only
  timing; encode-only selection remains limited to render domains where encode
  is the comparable operation scope.
- kernel-dispatch traces now fold host kernel prewarm into selected operation
  timing when the trace actually contains `kernel_dispatch`; non-kernel copy
  and render traces keep their ordinary operation timing source.

Release artifacts:

- `bench/out/apple-metal/release/20260525T184401Z/runtime-comparisons.apple.metal.release/run-artifacts/doe/`
- `bench/out/apple-metal/release/20260525T184443Z/runtime-comparisons.apple.metal.release/run-artifacts/dawn_delegate/`
- `bench/out/apple-metal/release/20260525T184443Z/dawn-vs-doe.apple.metal.release.compare.json`
- `bench/out/apple-metal/release/20260525T184443Z/dawn-vs-doe.apple.metal.release.claim.json`

The broader local compare lane still includes diagnostic/non-claim rows for
methodology auditing. Marketing or release claims should cite the release claim
artifact above, whose selector excludes rows that are not claim-eligible.

## 2026-05-25 — P0 multi-draw fixtures use explicit indirect commands

The `render_multidraw` and `render_multidraw_indexed` fixtures now exercise
the explicit `draw_indirect` / `draw_indexed_indirect` command path instead of
implicitly enabling multi-draw from ordinary direct render draws. The WebGPU
full path now sizes and writes one indirect argument record per requested draw
before using the p0 multi-draw API; if the argument staging write cannot be
prepared, execution falls back to the regular draw loop.

Fresh directional evidence:

- `bench/out/apple-metal/explore/20260525T181045Z/runtime-comparisons.apple.metal.explore/run-artifacts/doe/doe-render_multidraw-20260525T181045Z.run.json`
- `bench/out/apple-metal/explore/20260525T181045Z/runtime-comparisons.apple.metal.explore/run-artifacts/doe/doe-render_multidraw_indexed-20260525T181045Z.run.json`
- `bench/out/apple-metal/explore/20260525T181126Z/runtime-comparisons.apple.metal.explore/run-artifacts/dawn_delegate/dawn_delegate-render_multidraw-20260525T181126Z.run.json`
- `bench/out/apple-metal/explore/20260525T181126Z/runtime-comparisons.apple.metal.explore/run-artifacts/dawn_delegate/dawn_delegate-render_multidraw_indexed-20260525T181126Z.run.json`

The rows remain directional until governed apples-to-apples evidence is
recorded.

## 2026-05-25 — Browser gate now records forced-runtime identity

The Chromium Track A browser gate now validates explicit runtime-selection
evidence for both Dawn and Doe modes. Smoke and layered browser artifacts carry
forced mode, selected runtime, fallback status, selector version, launch-args
hash, and Doe runtime artifact hash for Doe mode.

Current refreshed evidence:

- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser-layered.superset.diagnostic.json`
- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser-layered.superset.summary.json`
- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser-layered.superset.check.json`
- `bench/out/browser-promotion/20260525T163954Z/browser_gate.json`

The gate passes with zero failures. The output remains diagnostic; the next
promotion boundary is a formal browser claim lane.

## Current state

- Apple Metal native Doe-vs-Dawn fair-cold compare defaults are in place.
- AMD Vulkan now has Doe-side `VkPipelineCache` support and renewed strict
  compare evidence.
- Apple Metal package lanes and AMD Vulkan package lanes both have current
  narrow claimable surfaces.
- Benchmark reporting is artifact-first; JSON receipts under `bench/out/` are
  the canonical output surface.

## Active blockers

- Backend-wide claim language is still narrower than the existence of isolated
  claimable rows.
- D3D12 claim evidence still requires a suitable Windows host.
- Broader Metal and ORT/WebGPU package claims remain mixed or narrow.

## Landed infrastructure

- Fair-cold compare defaults on Metal
- Vulkan pipeline-cache implementation and optional persistence
- Artifact-first compare/claim/report flows
- Bench output viewer as the single tracked local HTML surface

## Ground truth

- Backend benchmark status is no longer the main source of status-log volume.
- This shard exists so backend and benchmark updates stop crowding compiler and
  Cerebras work into a single giant dated file.

## Use this shard for

- Native backend compare status
- Package-lane status
- Benchmark methodology / claim updates
- Backend-specific performance evidence
