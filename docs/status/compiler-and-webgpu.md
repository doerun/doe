# Doe status: compiler and WebGPU

This is a live topical status shard. Follow the shared shard policy in
[`README.md`](README.md).

**Scope notice:** 2026-04-24 TSIR entries moved to
[`tsir.md`](./tsir.md); 2026-04-23 TSIR Step 4 history lives in
[`archive/2026-04-02-to-2026-04-15.md`](archive/2026-04-02-to-2026-04-15.md)
(tail block). **New TSIR entries go in [`tsir.md`](./tsir.md).** This shard
stays focused on non-TSIR compiler work (shader compiler non-TSIR paths,
WebGPU runtime, robustness).

## 2026-05-27 — WGSL verified output paths stay under verification root

WGSL corpus materialization and minimization receipt checks now reject verified
output paths that resolve outside `--verify-files-root`. Source paths remain
repo-relative, and generated materialized/minimized files must stay under the
verification root before hashing.

Touched:

- `bench/tools/check_wgsl_corpus_materialization.py`
- `bench/tools/check_wgsl_minimization_receipt.py`
- `bench/tests/test_wgsl_corpus_manifest.py`
- `bench/tests/test_wgsl_minimization_receipt.py`
- `docs/shader-compiler-architecture.md`
- `docs/status/compiler-and-webgpu.md`

Verified:

- `python3 -m py_compile bench/tools/check_wgsl_corpus_materialization.py bench/tools/check_wgsl_minimization_receipt.py bench/tests/test_wgsl_corpus_manifest.py bench/tests/test_wgsl_minimization_receipt.py`
- `python3 bench/tools/check_wgsl_corpus_materialization.py --receipt examples/wgsl-corpus-materialization.sample.json --verify-files-root . --json`
- `python3 bench/tools/check_wgsl_minimization_receipt.py --receipt examples/wgsl-minimization-receipt.sample.json --verify-files-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_corpus_manifest.py bench/tests/test_wgsl_minimization_receipt.py -q`

## 2026-05-27 — Standalone WGSL evidence paths reject traversal

Standalone WGSL fixture and receipt checkers now reject absolute or
parent-traversal source paths before hashing or file verification. The CTS
shader subset builder/checker also rejects unsafe CTS artifact references, and
the lowering-link checker rejects unsafe Doe receipt links.

Touched:

- `bench/tools/check_wgsl_robustness_fixtures.py`
- `bench/tools/check_wgsl_diagnostic_fixtures.py`
- `bench/tools/build_wgsl_cts_shader_subset.py`
- `bench/tools/check_wgsl_cts_shader_subset.py`
- `bench/tools/minimize_wgsl_corpus_failure.py`
- `bench/tools/check_wgsl_minimization_receipt.py`
- `bench/tools/check_wgsl_lowering_link_receipt.py`
- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_wgsl_robustness_fixtures.py`
- `bench/tests/test_wgsl_diagnostic_fixtures.py`
- `bench/tests/test_wgsl_cts_shader_subset.py`
- `bench/tests/test_wgsl_minimization_receipt.py`
- `bench/tests/test_wgsl_lowering_link_receipt.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `config/wgsl-cts-shader-subset.schema.json`
- `examples/wgsl-cts-shader-subset.sample.json`
- `examples/wgsl-minimization-receipt.sample.json`
- `docs/status/compiler-and-webgpu.md`

Verified:

- `python3 -m py_compile bench/tools/check_wgsl_robustness_fixtures.py bench/tools/check_wgsl_diagnostic_fixtures.py bench/tools/build_wgsl_cts_shader_subset.py bench/tools/check_wgsl_cts_shader_subset.py bench/tools/minimize_wgsl_corpus_failure.py bench/tools/check_wgsl_minimization_receipt.py bench/tools/check_wgsl_lowering_link_receipt.py bench/runners/run_blocking_gates.py bench/tests/test_wgsl_robustness_fixtures.py bench/tests/test_wgsl_diagnostic_fixtures.py bench/tests/test_wgsl_cts_shader_subset.py bench/tests/test_wgsl_minimization_receipt.py bench/tests/test_wgsl_lowering_link_receipt.py bench/tests/test_run_blocking_gates_wiring.py`
- `python3 bench/tools/build_wgsl_cts_shader_subset.py --manifest config/wgsl-browser-corpus.json --cts-evidence config/webgpu-cts-evidence.json --out examples/wgsl-cts-shader-subset.sample.json`
- `python3 bench/tools/minimize_wgsl_corpus_failure.py --manifest config/wgsl-browser-corpus.json --shader-id invalid-missing-return --taxonomy-code wgsl_sema_failed --failure-stage sema --diagnostic-category control_flow --backend-target msl --diagnostic-line 3 --context-lines 1 --out-dir examples/wgsl-minimize --receipt-out examples/wgsl-minimization-receipt.sample.json`
- `python3 bench/tools/check_wgsl_robustness_fixtures.py --fixtures config/wgsl-robustness-fixtures.json --json`
- `python3 bench/tools/check_wgsl_diagnostic_fixtures.py --fixtures config/wgsl-diagnostic-fixtures.json --manifest config/wgsl-browser-corpus.json --taxonomy config/shader-error-taxonomy.json --json`
- `python3 bench/tools/check_wgsl_cts_shader_subset.py --subset examples/wgsl-cts-shader-subset.sample.json --json`
- `python3 bench/tools/check_wgsl_minimization_receipt.py --receipt examples/wgsl-minimization-receipt.sample.json --verify-files-root . --json`
- `python3 bench/tools/check_wgsl_lowering_link_receipt.py --receipt examples/wgsl-lowering-link-receipt.sample.json --verify-files-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_*.py bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-27 — WGSL corpus source paths stay repo-relative

WGSL corpus manifests now reject absolute or parent-traversal `sourcePath`
values before materialization can read files. Materialization receipts also
reject unsafe row `sourcePath` values, so compiler evidence cannot point outside
the repo-owned corpus while still claiming normalized source identity.

Touched:

- `bench/tools/materialize_wgsl_corpus_manifest.py`
- `bench/tools/check_wgsl_corpus_materialization.py`
- `bench/tests/test_wgsl_corpus_manifest.py`
- `config/wgsl-corpus-materialization.schema.json`
- `examples/wgsl-corpus-materialization.sample.json`
- `docs/shader-compiler-architecture.md`
- `docs/status/compiler-and-webgpu.md`

Verified:

- `python3 -m py_compile bench/tools/materialize_wgsl_corpus_manifest.py bench/tools/check_wgsl_corpus_materialization.py bench/tests/test_wgsl_corpus_manifest.py`
- `python3 bench/tools/materialize_wgsl_corpus_manifest.py --manifest config/wgsl-browser-corpus.json --out-dir examples/wgsl-corpus-materialized/browser-wgsl-corpus-v0 --receipt-out examples/wgsl-corpus-materialization.sample.json`
- `python3 bench/tools/check_wgsl_corpus_materialization.py --receipt examples/wgsl-corpus-materialization.sample.json --verify-files-root . --json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_corpus_manifest.py -q`
- `python3 bench/gates/schema_gate.py`
- `git diff --check`

## 2026-05-26 — Blocking runner can gate standalone WGSL receipts

The canonical blocking runner now exposes opt-in gates for standalone WGSL
diagnostic fixtures, robustness fixtures, lowering-link receipts, minimization
receipts, CTS shader subsets, and corpus materializations. Compiler lanes can
promote those receipts through the same runner as schema/correctness/trace
gates instead of relying on separate manual commands.

Touched:

- `bench/runners/run_blocking_gates.py`
- `bench/tests/test_run_blocking_gates_wiring.py`
- `bench/README.md`
- `docs/process.md`

Verified:

- `python3 -m py_compile bench/runners/run_blocking_gates.py bench/tests/test_run_blocking_gates_wiring.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_run_blocking_gates_wiring.py -q`
- `python3 bench/tools/check_wgsl_diagnostic_fixtures.py --fixtures config/wgsl-diagnostic-fixtures.json --manifest config/wgsl-browser-corpus.json --taxonomy config/shader-error-taxonomy.json`
- `python3 bench/tools/check_wgsl_robustness_fixtures.py --fixtures config/wgsl-robustness-fixtures.json`

## 2026-05-26 — WGSL corpus materializations have a standalone checker

WGSL corpus materialization receipts now have an independent checker. It
validates materialization status, row uniqueness, required shader metadata,
source hashes, backend targets, shader stages, and can optionally verify that
materialized WGSL files still hash to the receipt values.

Touched:

- `bench/tools/check_wgsl_corpus_materialization.py`
- `bench/tests/test_wgsl_corpus_manifest.py`

Verified:

- `python3 -m py_compile bench/tools/check_wgsl_corpus_materialization.py bench/tools/materialize_wgsl_corpus_manifest.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_corpus_manifest.py -q`
- `python3 bench/tools/check_wgsl_corpus_materialization.py --receipt examples/wgsl-corpus-materialization.sample.json`

## 2026-05-26 — WGSL CTS shader subsets have a standalone checker

WGSL CTS shader subset artifacts now have an independent checker. It enforces
pass status, non-empty CTS rows, unique shader/query linkage, source hashes,
CTS artifact anchors, backend targets, and shader stages.

Touched:

- `bench/tools/check_wgsl_cts_shader_subset.py`
- `bench/tests/test_wgsl_cts_shader_subset.py`

Verified:

- `python3 -m py_compile bench/tools/check_wgsl_cts_shader_subset.py bench/tools/build_wgsl_cts_shader_subset.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_cts_shader_subset.py -q`
- `python3 bench/tools/check_wgsl_cts_shader_subset.py --subset examples/wgsl-cts-shader-subset.sample.json`

## 2026-05-26 — WGSL minimization receipts have a standalone checker

WGSL corpus minimization receipts now have an independent checker. It enforces
source identity preservation, taxonomy/failure metadata, pending-replay
candidate status, parent-source hash linkage, line-range sanity, and the
required normalized-original candidate.

Touched:

- `bench/tools/check_wgsl_minimization_receipt.py`
- `bench/tests/test_wgsl_minimization_receipt.py`

Verified:

- `python3 -m py_compile bench/tools/check_wgsl_minimization_receipt.py bench/tools/minimize_wgsl_corpus_failure.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_minimization_receipt.py -q`
- `python3 bench/tools/check_wgsl_minimization_receipt.py --receipt examples/wgsl-minimization-receipt.sample.json`

## 2026-05-26 — WGSL lowering link receipts have a standalone checker

WGSL source-to-IR-to-backend lowering link receipts now have an independent
checker. It verifies row counts, linked/diagnostic status, required source, IR,
and backend hashes, Doe receipt paths, and summary failure mirroring before the
receipt can be used as compiler evidence.

Touched:

- `bench/tools/check_wgsl_lowering_link_receipt.py`
- `bench/tests/test_wgsl_lowering_link_receipt.py`

Verified:

- `python3 -m py_compile bench/tools/check_wgsl_lowering_link_receipt.py bench/tools/build_wgsl_lowering_link_receipt.py`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_lowering_link_receipt.py -q`
- `python3 bench/tools/check_wgsl_lowering_link_receipt.py --receipt examples/wgsl-lowering-link-receipt.sample.json`

## 2026-05-26 — Doe compile reports emit phase timings

The single-shader runtime compile reporter now records parse, sema, lower,
emit, and total timings from the Doe WGSL pipeline. Compiler evidence consumes
those receipt timings for Doe rows instead of reducing Doe evidence to a
whole-compile-only total.

Touched:

- `config/runtime-compile-report.schema.json`
- `examples/runtime-compile-report.sample.json`
- `runtime/zig/src/doe_wgsl/mod.zig`
- `runtime/zig/src/doe_wgsl/runtime_compile.zig`
- `runtime/zig/src/doe_wgsl/runtime_compile_report.zig`
- `bench/native-compare/compare_doe_vs_tint_compilation.py`
- `bench/tests/test_compare_doe_vs_tint_compilation.py`
- `bench/tests/test_runtime_compile_report_schema.py`
- `config/schema-targets.json`
- `bench/README.md`
- `runtime/zig/README.md`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_compare_doe_vs_tint_compilation.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_runtime_compile_report_schema.py -q`
- `python3 bench/gates/schema_gate.py`
- `zig build runtime-compile-report`
- `runtime/zig/zig-out/bin/doe-runtime-compile-report --shader-path bench/fixtures/wgsl-robustness/bounds-storage-buffer-1d.wgsl --shader-name bounds-storage-buffer-1d`
- `zig build test-wgsl`

## 2026-05-26 — Compiler evidence cannot claim whole-compile-only timing

Doe-vs-Tint compiler evidence now keeps whole-compile-only timing diagnostic.
Claimable rows require the phase model and row timings to cover parse, sema,
lower, emit, and total phases.

Touched:

- `bench/native-compare/compare_doe_vs_tint_compilation.py`
- `bench/gates/tint_compiler_evidence_gate.py`
- `bench/tests/test_compare_doe_vs_tint_compilation.py`
- `bench/tests/test_tint_compiler_evidence_gate.py`

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_compare_doe_vs_tint_compilation.py bench/tests/test_tint_compiler_evidence_gate.py -q`

## 2026-05-26 — Browser WGSL robustness fixture classes are covered

Browser-facing robustness transform fixtures now have a schema-backed coverage
manifest:

- `config/wgsl-robustness-fixtures.schema.json`
- `config/wgsl-robustness-fixtures.json`
- `bench/tools/check_wgsl_robustness_fixtures.py`
- `bench/fixtures/wgsl-robustness/`

The checker requires fixture coverage for bounds, aliasing, texture dimension,
and guard patterns. Each row binds a source path, normalized source hash,
expected transform class, required source needles, and the browser workload
classes that use the pattern.

Verified:

- `python3 bench/tools/check_wgsl_robustness_fixtures.py --fixtures config/wgsl-robustness-fixtures.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_robustness_fixtures.py -q`

## 2026-05-26 — WGSL lowering links bind source, IR, and backend output

Compiler evidence can now be converted into a schema-backed lowering link
receipt:

- `config/wgsl-lowering-link-receipt.schema.json`
- `examples/wgsl-lowering-link-receipt.sample.json`
- `bench/tools/build_wgsl_lowering_link_receipt.py`

The receipt maps compiler evidence rows back to the WGSL corpus manifest by
shader id or source path, then binds source hash, Doe IR hash, backend output
hash, backend target, validation status, and Doe receipt path. Rows with source
hash drift, missing IR hash, missing backend hash, or missing compiler receipt
stay diagnostic with typed failure codes.

Verified:

- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_lowering_link_receipt.py -q`

## 2026-05-26 — WGSL failure minimization preserves corpus identity

Corpus shader failures now have a schema-backed minimization receipt producer:

- `config/wgsl-minimization-receipt.schema.json`
- `examples/wgsl-minimization-receipt.sample.json`
- `bench/tools/minimize_wgsl_corpus_failure.py`

The minimizer emits deterministic candidate WGSL files while carrying the
original manifest shader id, source path, normalized source hash, backend
targets, failure stage, and taxonomy code on every receipt. Candidates remain
`pending_replay`, so a reduced shader cannot become evidence until the compiler
replays it against the same typed failure identity.

Verified:

- `python3 bench/tools/minimize_wgsl_corpus_failure.py --manifest config/wgsl-browser-corpus.json --shader-id invalid-missing-return --taxonomy-code wgsl_sema_failed --failure-stage sema --diagnostic-category control_flow --backend-target msl --diagnostic-line 3 --context-lines 1 --out-dir /tmp/wgsl-minimize --receipt-out /tmp/wgsl-minimization-receipt.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_minimization_receipt.py -q`

## 2026-05-26 — Invalid WGSL diagnostics compare typed categories

Invalid browser WGSL corpus rows now have a schema-backed diagnostic fixture
set:

- `config/wgsl-diagnostic-fixtures.schema.json`
- `config/wgsl-diagnostic-fixtures.json`
- `bench/tools/check_wgsl_diagnostic_fixtures.py`

The checker binds each diagnostic fixture to an invalid manifest row, source
hash, expected diagnostic category, and Doe taxonomy code. It rejects free-form
message comparison and requires every invalid manifest row to have typed
diagnostic coverage.

Verified:

- `python3 bench/tools/check_wgsl_diagnostic_fixtures.py --fixtures config/wgsl-diagnostic-fixtures.json --manifest config/wgsl-browser-corpus.json --taxonomy config/shader-error-taxonomy.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_diagnostic_fixtures.py -q`

## 2026-05-26 — Browser WGSL corpus manifest is schema-backed

The compiler lane now has a browser-facing WGSL corpus manifest and
materializer:

- `config/wgsl-corpus-manifest.schema.json`
- `config/wgsl-browser-corpus.json`
- `config/wgsl-corpus-materialization.schema.json`
- `bench/tools/materialize_wgsl_corpus_manifest.py`

The manifest binds each row to source path, normalized source hash, expected
validity, backend targets, shader stages, and provenance. The materializer
checks category coverage and source-hash drift before writing normalized WGSL
files and a receipt. The Tint compiler evidence gate now requires claimable
rows to carry corpus linkage fields and a Doe IR hash alongside source and
backend output hashes. CTS shader-subset ingestion now links CTS evidence rows
to manifest shader rows through the same normalized source-hash contract.

Verified:

- `python3 bench/gates/schema_gate.py`
- `python3 bench/tools/materialize_wgsl_corpus_manifest.py --manifest config/wgsl-browser-corpus.json --out-dir /tmp/wgsl-browser-corpus --receipt-out /tmp/wgsl-browser-corpus.materialization.json`
- `python3 bench/tools/build_wgsl_cts_shader_subset.py --manifest config/wgsl-browser-corpus.json --cts-evidence config/webgpu-cts-evidence.json --out /tmp/wgsl-cts-shader-subset.json`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_corpus_manifest.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_wgsl_cts_shader_subset.py -q`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_tint_compiler_evidence_gate.py -q`

## 2026-05-26 — Guarded texture coordinate aliases stay unclamped

The WGSL robustness transform now resolves const-local value aliases while
classifying guarded `global_invocation_id` texture coordinates and root guard
conditions. Clamp elision now requires guards tied to the same
`textureDimensions(...)` expression, so `const coords = vec2(gid.x, gid.y)` and
`const out_of_bounds = ...` paths keep their proof only when the guard is bound
to the actual texture extent.

Verified:

- `zig build test-wgsl`

## 2026-05-25 — Tint compiler evidence pins warm benchmark identity

Doe-vs-Tint compiler evidence now records the `tint_benchmark` binary in the
toolchain block alongside the Doe compiler-report binary and the Tint CLI. The
compiler evidence gate requires compiler artifact hashes for comparable reports
and requires the warm Tint benchmark artifact hash for claimable reports, so
in-process Tint timing evidence cannot be separated from the exact binary that
produced it.

Refreshed compiler evidence:

- `bench/out/tint-compiler-evidence.json`
- `bench/out/compilation/doe-vs-tint.msl.claim.json`

Verified:

- `python3 bench/native-compare/compare_doe_vs_tint_compilation.py --config bench/native-compare/compare_doe_vs_tint.config.json --claim-mode release --evidence-out bench/out/tint-compiler-evidence.json`
- `python3 bench/gates/tint_compiler_evidence_gate.py --report bench/out/tint-compiler-evidence.json --require-claimable`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_tint_compiler_evidence_gate.py bench/tests/test_compare_doe_vs_tint_compilation.py -q`
- `python3 bench/gates/tint_compiler_evidence_gate.py --report examples/tint-compiler-evidence.sample.json`

## 2026-05-25 — Apple Metal Tint warm corpus evidence

The Doe-vs-Tint compiler lane now has a reproducible path for true
warm/in-process Tint timing on Doe-owned Apple Metal WGSL workload rows. The
materializer copies the selected WGSL rows into the ignored local Dawn checkout,
normalizes copied benchmark input text for Dawn's generated C++ header, widens
the local MSL writer benchmark's array-length bindpoint coverage for the Doe
corpus, and rebuilds `tint_benchmark`.

Fresh local warm-corpus state:

- `bench/fixtures/dawn_tint_warm_corpus_state.json`

Fresh compiler evidence:

- `bench/out/tint-compiler-evidence.json`
- `bench/out/compilation/doe-vs-tint.msl.claim.json`

Verified:

- `python3 bench/tools/materialize_tint_warm_corpus.py --workloads bench/workloads/workloads.apple.metal.json --dawn-source-dir bench/vendor/dawn --build-dir bench/vendor/dawn/out/Release --target msl --build --ninja-bin ninja --output-state bench/fixtures/dawn_tint_warm_corpus_state.json`
- `python3 bench/native-compare/compare_doe_vs_tint_compilation.py --config bench/native-compare/compare_doe_vs_tint.config.json --claim-mode release --evidence-out bench/out/tint-compiler-evidence.json`
- `python3 bench/gates/tint_compiler_evidence_gate.py --report bench/out/tint-compiler-evidence.json --require-claimable`
- `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_materialize_tint_warm_corpus.py bench/tests/test_compare_doe_vs_tint_compilation.py -q`

## 2026-05-25 — Local Tint toolchain and claimable corpus evidence

The Dawn bootstrapper now supports the local MacBook layout where
`bench/vendor/dawn` already contains ignored build outputs but is not yet a
source checkout. The bootstrap path can initialize that existing directory,
sync Dawn dependencies, bootstrap depot_tools-backed GN/CIPD, and build the
Tint CLI plus `tint_benchmark` without deleting the existing Dawn delegate
library under `bench/vendor/dawn/out/Release`.

Fresh local Tint toolchain state:

- `bench/fixtures/dawn_tint_runtime_state.json`

Fresh compiler evidence:

- `bench/out/tint-compiler-evidence.benchmark-corpus.json`
- `bench/out/compilation/doe-vs-tint-benchmark.msl.claim.json`
- `bench/out/tint-compiler-evidence.json`
- `bench/out/compilation/doe-vs-tint.msl.claim.json`

Verified:

- `python3 bench/tools/bootstrap_dawn.py --source-dir bench/vendor/dawn --build-dir bench/vendor/dawn/out/Release --build-system gn --targets tint tint_benchmark --branch main --gn-args 'is_debug=false' --init-existing-source-dir --fetch-depth 1 --sync-deps --gn-bin .tooling/depot_tools/gn --gclient-bin .tooling/depot_tools/gclient --output-state bench/fixtures/dawn_tint_runtime_state.json`
- `python3 bench/native-compare/compare_doe_vs_tint_compilation.py --config bench/native-compare/compare_doe_vs_tint.benchmark-corpus.config.json --claim-mode release --evidence-out bench/out/tint-compiler-evidence.benchmark-corpus.json`
- `python3 bench/gates/tint_compiler_evidence_gate.py --report bench/out/tint-compiler-evidence.benchmark-corpus.json --require-claimable`
- `python3 bench/native-compare/compare_doe_vs_tint_compilation.py --config bench/native-compare/compare_doe_vs_tint.config.json --claim-mode release --evidence-out bench/out/tint-compiler-evidence.json`
- `python3 bench/gates/tint_compiler_evidence_gate.py --report bench/out/tint-compiler-evidence.json`
- `python3 -m pytest bench/tests/test_bootstrap_dawn.py bench/tests/test_tint_compiler_evidence_gate.py -q`

## 2026-05-25 — Tint benchmark-corpus diagnostic evidence

The Doe-vs-Tint compiler evidence runner now treats an unavailable Tint
benchmark-corpus source script as diagnostic evidence instead of aborting
before report emission. Zero-row compiler evidence reports are schema-valid
only when they remain diagnostic and carry a summary reason.

Fresh diagnostic artifacts:

- `bench/out/tint-compiler-evidence.benchmark-corpus.json`
- `bench/out/tint-compiler-evidence.json`

Verified:

- `python3 bench/gates/tint_compiler_evidence_gate.py --report bench/out/tint-compiler-evidence.benchmark-corpus.json`
- `python3 bench/gates/tint_compiler_evidence_gate.py --report bench/out/tint-compiler-evidence.json`
- `python3 -m pytest bench/tests/test_tint_compiler_evidence_gate.py -q`

## 2026-05-25 — Doe-vs-Tint evidence report emitter

The legacy Doe-vs-Tint compilation runner can now emit the
`tint-compiler-evidence` report consumed by the compiler evidence gate:

```sh
python3 bench/native-compare/compare_doe_vs_tint_compilation.py \
  --config bench/native-compare/compare_doe_vs_tint.config.json \
  --evidence-out bench/out/tint-compiler-evidence.json
```

The report binds toolchain identity, shader source hashes, compiler output
hashes, Metal validation receipts for MSL rows, whole-compile timing evidence,
row comparability, and row claimability. Missing Tint/Dawn binaries now produce
a schema-valid diagnostic evidence report instead of an unsupported compiler
claim.

## 2026-05-25 — Doe-vs-Tint compiler evidence gate

Added a schema-backed gate for compiler evidence against Tint:

- `config/tint-compiler-evidence.schema.json`
- `bench/gates/tint_compiler_evidence_gate.py`
- `examples/tint-compiler-evidence.sample.json`
- `bench/tests/test_tint_compiler_evidence_gate.py`

The gate keeps compiler bring-up reports diagnostic until each row binds Doe
and Tint toolchain identity, source/output hashes, validation status, phase
timing symmetry, and row-level comparability. Claim lanes can pass
`--require-claimable` to fail closed unless the report is fully comparable and
claimable.

## 2026-04-24 — Track C first-zero diagnostic receipt

Added a schema-backed diagnostic front door for the native Doe WebGPU
C-lane:

- `bench/tools/analyze_doe_webgpu_first_zero.py`
- `config/doe-webgpu-first-zero-diagnostic.schema.json`

The tool binds the Doe WebGPU runner receipt, exporter receipt,
stdout/stderr logs, and `final_logits.f32` into a claim-boundary
receipt. It distinguishes missing tensor, all-zero tensor, non-finite
logits, and finite non-zero logits without claiming browser, CSL, or
hardware parity.

The current Gemma 3 1B native Vulkan run classifies as
`blocked_no_finite_logits`: `hasF16=true` and `hasSubgroups=true` are
advertised, pipeline creation is not the failing surface, KV/cache
byte evidence is present in the exporter receipt, and sampling fails
because the logits tensor has no finite candidates. The receipt carries
the tensor hash, digest comparison, and finite/non-finite counts.

Verified:

- `python3 -m unittest bench.tests.test_analyze_doe_webgpu_first_zero`
- `python3 bench/tools/analyze_doe_webgpu_first_zero.py --webgpu-receipt /tmp/gemma-3-1b-doe-webgpu-transcript.json --exporter-receipt /tmp/gemma-3-1b-doe-webgpu-export/doppler_int4ple_reference_export.json --final-logits /tmp/gemma-3-1b-doe-webgpu-export/final_logits.f32 --stdout-log /tmp/doe-webgpu-export.stdout.log --stderr-log /tmp/doe-webgpu-export.stderr.log --out /tmp/gemma-3-1b-doe-webgpu-first-zero-diagnostic.json`

## 2026-04-24 — Track C native Vulkan: subgroup/f16 feature chain and queue replay

The Doe native Vulkan C-lane moved past two runtime blockers:

- `vkCreateDevice` now enables the Vulkan feature chain that the
  WebGPU adapter advertises for f16/subgroup work:
  `VkPhysicalDevice16BitStorageFeatures.storageBuffer16BitAccess`,
  `VkPhysicalDeviceVulkan12Features.shaderFloat16`,
  `subgroupBroadcastDynamicId`, and `shaderSubgroupExtendedTypes` when
  the physical device supports `subgroups-f16`.
- Vulkan feature publication now exposes `subgroups-f16` only from the
  real adapter probe (`subgroups && shader-f16 &&
  shaderSubgroupExtendedTypes`), rather than treating plain
  `subgroups` as enough for f16 subgroup kernels.
- `queue.writeBuffer` no longer writes through cached host pointers
  after storage-buffer promotion to device-local memory; it resolves
  the live Vulkan compute buffer and uses the staging upload path.
- Vulkan `copyBufferToBuffer` replay now uses a real `vkCmdCopyBuffer`
  + wait when source or destination lacks a CPU mapping, instead of
  silently skipping device-local copies.

Evidence:

- `zig build test-wgsl` exits 0.
- `zig build` exits 0.
- `env HOME=/tmp node bench/repros/doe-runtime-zero-dispatch/repro.mjs`
  prints `dispatched u32: 42 (expect 42)`.
- `env HOME=/tmp DOE_DISABLE_SUBGROUPS=0 runtime/zig/zig-out/bin/doe-zig-runtime --commands examples/rmsnorm_subgroup_commands.json --backend native --backend-lane vulkan_doe_release --execute --trace-meta /tmp/rmsnorm_subgroup.meta.json`
  exits 0.
- The analogous `matmul_gemv_subgroup_commands.json` run exits 0
  with the pre-existing prewarm warning.

Gemma 3 1B shared-contract rerun with `DOE_DISABLE_SUBGROUPS=0` now
advertises `hasF16=true` and `hasSubgroups=true` and gets through
pipeline creation/execution without the earlier segfault. It is still
not promotion-ready: the exporter exits with
`[Sampling] Logits has no finite candidate logits after masking the pad token`,
and the follow-up diagnostic classifies the output tensor as
non-finite logits. The next C-lane task is a first-divergence
kernel/output-buffer probe, not more capability suppression.

## 2026-04-24 — Track 1 diagnostic: Doe compute dispatch silently no-ops

After landing WS B1+B2 (if/else termination fix + scalar-op-vector
coercion fix), the Gemma 3 1B shared-contract lane was re-run. Stderr
is now clean aside from one "non-fatal" `[GPU] Platform/registry init
failed (reading 'vendor')` warning, but execution still emits `[1]`
with zero KV and zero logits.

### Root cause located: `adapter.info` was missing from the compute facade

`packages/doe-gpu/src/vendor/webgpu/compute.js:wrapAdapter` returned a
bare object with `_raw`, `features`, `limits`, `requestDevice`,
`destroy` but **no `info` property**. Doppler's
`src/config/platforms/loader.js:102` reads `adapter.info` and
dereferences `.vendor` at line 54. Empty-string fallback exists at
line 373 via `adapter.info || fallback`, but that fallback fires
AFTER platform detection has already thrown. Doppler's try/catch at
`src/gpu/device.js:337` swallows the error as "non-fatal" and sets
`resolvedPlatformConfig = null`.

Fix: added `get info() { return raw.info; }` to `wrapAdapter`. Direct
probe now shows `adapter.info` returning the native adapter's
Object.freeze with vendor/architecture/device as empty strings —
valid, if informationless.

### But adapter.info fix alone does NOT unblock execution

Re-ran the C gate after the adapter.info fix. Stderr is now empty
(platform detection no longer throws). Execution still produces
`[1]` with zero KV and zero logits. The vendor-init warning was a
symptom, not the blocker for all-zero output.

### Typed first-divergence receipt (Track 1 exit signal)

Constructed a minimum dispatch repro at
`/tmp/doe-compute-zero-repro.mjs`:

```js
const shader = device.createShaderModule({ code: `
  @group(0) @binding(0) var<storage, read_write> out: array<u32>;
  @compute @workgroup_size(1) fn main() { out[0] = 42u; }
` });
// ...create pipeline, buffer, bind group, encode, submit, copy+readback...
console.log('dispatched u32:', view[0], '(expect 42)');
// → prints: dispatched u32: 0 (expect 42)
```

All intermediate calls succeed without throwing
(`createShaderModule`, `createComputePipeline`, `createBuffer`,
`createBindGroup`, `dispatchWorkgroups`, `queue.submit`,
`copyBufferToBuffer`, `mapAsync`). The readback returns 0 instead
of 42.

**This is the first no-op dispatch.** Every real Doppler kernel
(which is far more complex than the 3-line repro) reaches the same
silent-zero endpoint. The Gemma 3 `[1]` + zero-KV + zero-logits
failure mode is a direct consequence — embed dispatches write zero,
which the sampler reads as the EOS token id, which stops decode at
step 1.

### Additional signals from the probe

- `adapter.info` returns all-empty-string fallback. Native backend
  isn't providing real vendor/architecture — platform detection falls
  back to "generic" (expected in this env).
- `device.adapterInfo` is **undefined** (same kind of bug as
  `wrapAdapter`: `wrapDevice` in `compute.js:461` doesn't expose
  `adapterInfo`). Fix would be analogous — `get adapterInfo() {
  return raw.adapterInfo; }`. Not yet applied; adapter.info covers
  the Doppler path and adapterInfo may be a follow-on.
- `device.features` contains `depth-clip-control`,
  `depth32float-stencil8`, three texture-compression features —
  **graphics features, not compute features**. Critically missing:
  `shader-f16`, `subgroups`. For Doppler's capability-aware kernel
  path policy, this means f16 and subgroup kernels get remapped to
  f32/non-subgroup fallbacks. That's correctness-preserving but
  doesn't cause zeros; this is a pre-existing observation unrelated
  to the silent no-op.

### What this means for Track 1

Track 1 exit condition was "Either realKvCacheUsedOnExecutableLane=true,
OR a receipt names the first dispatch/buffer that failed to write
non-zero data." The minimum repro IS that receipt. The first no-op
dispatch is a 3-line WGSL compute shader writing a u32 literal —
simpler than any Gemma kernel — so the blocker is at the Doe
runtime / Vulkan compute queue level, NOT at WGSL compile, NOT at
platform detection, NOT at shader-f16 handling, NOT at Doppler's
kernel-path policy, NOT at buffer layout.

The fix site lives in Doe's runtime compute path (`runtime/zig/src/`,
specifically the Vulkan compute backend and the queue.submit /
readback plumbing). Candidates to investigate first:

1. Is `queue.submit` actually flushing the command buffer to the
   Vulkan device? Probe: add a logger at submit-time, observe
   command-buffer handle validity.
2. Is the buffer memory backed by device-visible Vulkan memory, or
   is it only CPU-visible? Probe: inspect buffer allocation flags
   after `createBuffer`.
3. Is `copyBufferToBuffer` targeting the correct source buffer? The
   readback target was a freshly-created MAP_READ buffer; if the
   storage buffer's memory is unsynchronized with the copy, we'd see
   zero-initialized readback memory.
4. Is `mapAsync(GPUMapMode.READ)` being handled correctly on a
   buffer whose contents come from a device-side compute write?

These are the four specific threads for the next Track 1 session.

### Handoff artifacts

- `packages/doe-gpu/src/vendor/webgpu/compute.js` — one-line fix
  adding `info` getter to `wrapAdapter`; pushed in this session.
- `/tmp/doe-compute-zero-repro.mjs` — the 60-line minimum repro;
  reproduces `dispatched u32: 0 (expect 42)` deterministically.
- `/tmp/ws-c-gate-postfix1-transcript.json` — post-fix Gemma 3 1B
  transcript showing `[1]`/zero-KV/zero-logits persists.

## 2026-04-24 — WS2 gap report: four real-Doppler-kernel SPIR-V failures, two root causes

Diagnosed the WGSL→SPIR-V failures blocking WS2 end-to-end green
(per stderr in
`bench/out/doppler-reference/doe-webgpu-export.stderr.log`). Four
real Doppler kernels fail `createShaderModule (Vulkan)`. Three share
one bug; the fourth is separate.

### Root cause 1 — if/else-both-return not recognized as terminal

Affects:
- `dequant_f16_rowwise.wgsl` (Q4_K dequant → f16, row-wise stride)
- `dequant_f16_out_vec4.wgsl` (Q4_K dequant → f16, vec4 variant)
- `rmsnorm.wgsl` (RMSNorm with fused residual add)

Failure site (same for all three):
`runtime/zig/src/doe_wgsl/emit_spirv.zig:303` fires `error.InvalidIr`
because `emit_function` sees a function with non-void return type whose
body completed without an explicit terminator.

**Bug location:**
`runtime/zig/src/doe_wgsl/emit_spirv_fn.zig:195` — the `.if_` case in
`emit_stmt` unconditionally returns `false` (not-terminated), even
when both the then-branch and else-branch are terminated. Lines
185/190 correctly compute `then_terminated` / `else_terminated`;
line 195 throws that information away.

Minimum repro (verified against `doe-emit-spirv`):
```wgsl
fn both_branches_return(x: u32) -> u32 {
    if (x > 0u) { return 1u; } else { return 0u; }
}
```
Fails `InvalidIr`. Adding any statement (including a redundant
`return 99u;`) after the if-else makes it compile. Moving either
branch outside the if (e.g., last `return 0u;` as a trailing
fallthrough) also compiles.

**Fix direction:** in `emit_spirv_fn.zig:195`, return
`then_terminated and else_terminated and if_stmt.else_block != null`.
SPIR-V structured control flow additionally requires that the merge
label not be orphaned — when both branches terminate, either skip
emitting the merge label or emit `OpUnreachable` as its sole
instruction. The function-scope fallthrough at `emit_spirv.zig:299–304`
should then correctly see the function body as terminated and skip
the implicit `OpReturn` emit.

**Session-scale?** Yes, the fix is localized to `emit_stmt` in one
file. Coverage tests should hit if/else-both-return in various
contexts (nested, with shared suffix after, inside loops) before
landing.

### Root cause 2 — scalar coerce_binary_operand called with non-scalar source

Affects:
- `attention_head256_f16kv.wgsl` (f16 head-256 attention, prefill)

Failure site:
`runtime/zig/src/doe_wgsl/emit_spirv_fn.zig:772` fires
`error.UnsupportedConstruct` from `emit_scalar_construct_from_type`,
called via `coerce_binary_operand` at line 727. Target type is
scalar; source type is not a scalar. The function unwraps
`source_type` as `.scalar`, falls through the switch `else`, and
errors.

**What this means:** somewhere in the attention kernel, Doe's sema
or IR produces a binary operation whose target type is a scalar
(f32/f16/u32/i32) while the value being coerced has a non-scalar
type (vector, array element with the wrong shape, or similar). The
stderr doesn't name the specific expression.

**Suspect WGSL constructs** (by inspection of the kernel):
- Local `var q_local: array<vec4<f32>, HEAD_DIM_VECS>` used in nested
  loops; indexed access produces vec4<f32> refs.
- Mixed-type arithmetic: `dot(q_local[d4], vec4<f32>(shared_block[...]))`
  where `shared_block` is `array<vec4<f16>, ...>`; the explicit
  `vec4<f32>(vec4<f16>)` cast should go through coerce's `.vector →
  .vector` branch, but may instead hit a scalar-target path in some
  edge case.
- `continue` statements inside nested loops over `BLOCK_SIZE=32`
  arrays.
- `vec4<f16>` type in shared-workgroup allocations.

**Fix direction:** needs a minimum repro to pinpoint which
binary-op site produces the scalar-target-with-vector-source shape.
The fix may be in sema (where types are resolved) or in
`coerce_binary_operand` itself (if the source type it sees is legal
in WGSL but the coercion path doesn't handle it).

**Session-scale?** Probably, once a repro is cut. Days-scale if the
fix cascades into sema's type resolution for large function-local
arrays or vec4<f16> positional uses.

### What this unblocks

Both fixes land → Doe WebGPU compiles all four real Doppler kernels
→ Gemma 3 1B prefill can actually execute on Vulkan → KV buffers
write non-zero bytes → WS2's `realKvCache=false` flips to `true` for
the Gemma 3 shared contract → parity lane can compare tokens/logits
against the Program Bundle reference for real instead of for
trivially-zeroed execution.

Root cause 1 is the higher-priority fix: it's simpler, affects three
of four kernels, and is a single-file change. Root cause 2 is
follow-on; the attention kernel alone won't unblock WS2 end-to-end
unless the dequant+norm kernels also compile.

## 2026-04-24

- Gemma 3 1B now has a Doe WebGPU capture graph at
  `bench/out/doppler-capture/gemma-3-1b-doe-webgpu-capture-graph.json`.
  The capture tool accepts explicit model labels/capture IDs while preserving
  the Gemma-4 E2B default path, and `config/schema-targets.json` registers the
  Gemma 3 graph against `config/doe-webgpu-capture-graph.schema.json`.
- Gemma 3 1B Program Bundle -> Doe shared contract -> Doe WebGPU transcript
  plumbing is now materialized at:
  `bench/out/doppler-reference/gemma-3-1b-shared-execution-contract.json`,
  `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-transcript.json`, and
  `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-shared-execution-parity.json`.
  The source manifest, execution graph, and input-set hashes match the
  Program Bundle reference, and the prompt contract preserves Gemma chat
  templating.
- Gemma 3 1B is still not green through Doe WebGPU. The current transcript
  emits token `[1]` and stops after one decode step, while the Program Bundle
  reference emits eight tokens and stops by `decode_steps_exhausted`. KV/cache
  byte readback is captured, but all layer key/value digests are zero-buffer
  digests; receipts now classify that as `realKvCache=false` rather than
  promotion evidence.

## Current state

- TSIR (Tiled Spatial IR) current state and contracts live in
  [`tsir.md`](./tsir.md); that shard owns schema, digests, frontend,
  planner, collective-synthesis pass, reference interpreter, backend
  emitters (skeleton + semantic-aware body paths), parity CLI, manifest
  fixtures, and canary. Do not duplicate those bullets here.
- Postfix `++` / `--` statements are now supported in the WGSL compiler
  (tokens, lexer, AST `inc_stmt`/`dec_stmt`, parser, sema, IR lowering).
  `ir_transform` / `emit_spirv` errors are surfaced with specific kinds
  instead of silently becoming empty `OOM` strings, and the failing-kernel
  log carries the first 120 chars of the WGSL so failures are identifiable
  without re-running.
- The Doe WebGPU shared-contract lane has real transcript and parity plumbing,
  but it is not green end to end.
- The current blocker is in `runtime/zig/src/doe_wgsl/`, not Vulkan feature
  discovery.
- Vulkan-side capability bring-up has improved: the adapter now advertises
  `shader-f16` correctly, and the shared-contract runner can force subgroup
  removal with `DOE_DISABLE_SUBGROUPS=1`.

## Active blockers

- WGSL semantic-analysis and/or SPIR-V emission gaps still block some real
  Doppler kernels in the shared-contract lane.
- Mixed subgroup and non-subgroup entrypoints remain a real compiler surface.
- Real non-zero KV/cache evidence is still not emitted in the WebGPU transcript
  path; current Gemma 3 1B readbacks prove zero cache writes on the Doe lane.

## Landed infrastructure

- Shared-contract WebGPU transcript receipt
- Pairwise parity binder
- Generic transcript parity report surface
- Vulkan API-version and feature-capability fixes that expose `shader-f16`
  correctly
- Shared-contract runner defaults that force the declared subgroup workaround
  instead of silently relying on unsupported subgroup lowering

## Ground truth

- The WebGPU lane is blocked by WGSL compiler work, not by contract design.
- The current failures are concrete compiler/runtime gaps with named files and
  reproducible signatures.

## Use this shard for

- `doe_wgsl` compiler status
- WebGPU shared-contract transcript status
- WebGPU parity blockers
- Vulkan capability / adapter issues that affect the WebGPU lane
