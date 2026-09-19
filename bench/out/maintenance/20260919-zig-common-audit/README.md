# Common-backend Zig audit checkpoint

Batch base: `e24ffcd74b5a04ba819b7f0f338dbacbdd3da726`.
The scope order and verdicts are recorded in
[`runtime/zig/reviews/log.json`](../../../../runtime/zig/reviews/log.json);
[`queue.tsv`](../../../../runtime/zig/reviews/queue.tsv) is the derived current
view. This checkpoint examines the agreed batch and stops before
`src/backend/d3d12/commands/d3d12_dispatch.zig`. Consumer repairs do not grant
additional file or cross-directory review credit.

## Scope conclusions

Paths below are relative to `runtime/zig/`.

| Scope | Conclusion and responsibility |
| --- | --- |
| `src/backend/common/artifact_policy.zig` | Keep command classification beside backend evidence policy. Every canonical tag now receives an explicit decision. Status rendering returns the actual formatted or static fallback slice; consumers cannot read an unwritten buffer prefix. The negative compilation probe removes a real decision and requires rejection. |
| `src/backend/common/artifact_state.zig` | Replace field-name reflection and borrowed pending strings with a named allocator-owning state. Capture copies complete module/status/SPIR-V inputs, rejects overwriting pending work, hides stale published identity on capture failure, and frees pending/published allocations at teardown. Output paths are borrowed through owner lifetime. Allocation-failure tests cover capture rollback. |
| `src/backend/common/path_utils.zig` | Keep the small shared path admission operation. Absence returns false; access/path errors propagate. Candidate owners unwind allocated paths on errors. This is an existence probe, not a regular-file or race-free open guarantee; actual reads remain authoritative. |
| `src/backend/common/shader_artifact_manifest.zig` | Keep serialization/identity/file publication in an explicit collector. It accepts named state, never executes backend work, preserves failures for retry, atomically publishes files, escapes dynamic JSON, and distinguishes content from derived identity. Deduplication binds source observation, stage records/content, metadata, and configured toolchain identity. Emission counts advance on successful publication only. Allocation injection covers pending ownership and the serializer. |
| `src/backend/common/submit_count_policy.zig` | Retain the existing exhaustive logical selected-command accounting. Remove the redundant import wrapper and explicitly register its tests. This count does not assert physical submissions; backend telemetry remains the physical owner. Failed commands have no selected count, and zero dispatch work has zero logical submits. |
| `src/backend/common/timing.zig` | Use Zig's elapsed-clock `Instant` sampling and platform conversion instead of calendar time. The fallible operation API preserves unsupported-clock errors. The compatibility API retains its existing zero-unavailable representation; a zero starting sample cannot turn into an epoch-sized duration. Delta saturation handles reversed samples. This supplies no guarantee against OS/hardware clock faults. |
| Directory `src/backend/common` | Keep the existing direct files. Artifact selection, retained ownership, and publication have distinct APIs; path admission, logical counts, and elapsed sampling each have a small independent purpose. Platform stage descriptions stay with their backend. No generic utility bucket or new directory is introduced. Public wrappers retained for existing consumers are internal repository interfaces, not npm promises. |
| Within-directory `src/backend/common` | Examine the capture→pending→publish→clear handoff separately from placement. Policy derives command identities from the canonical tagged union; state owns retained input; the collector alone performs I/O. Failures cannot consume pending data or publish stale identity. Timing and submit accounting remain independent of artifact publication. Provider adapters invoke explicit collection after measured execution; telemetry snapshots only read stored state. |
| `src/backend/d3d12/artifact_emit.zig` | Retain the D3D12 stage description and typed collector call. Remove the unobserved `dxv` invocation. Derived DXIL identity is not a digest of DXIL bytes. Generated output is schema-validated on Linux; this establishes no Windows execution evidence. |
| `src/backend/d3d12/commands/d3d12_async_diagnostics.zig` | Remove empty-loop and fabricated-pipeline diagnostic success. Exhaustive admission rejects unimplemented modes before work. Preserve the existing native root-signature create/release lifecycle probe, release each acquired handle, reject a missing device before the C adapter, and propagate timing/native failures. Align advertised capabilities with admission. Host-independent admission tests pass; native Windows lifecycle execution is not qualified here. |

## Contract migration

Artifact manifest schema version 3 is additive to the retained version-1 and
version-2 schema branches. Historical output keeps its original meaning.

- `stages[].hashKind=content` requires a sibling `artifactPath` and hashes actual
  retained bytes. `derived` forbids that path and denotes identity construction,
  not serialized IR or binary content. Top-level legacy stage digest fields take
  their meaning from their matching stage record.
- `wgslHashKind=source_observation` hashes source read by the provider during
  capture. It does not prove those were the exact bytes used by an earlier
  compilation or a cache. `module_label` hashes the module identifier because no
  source observation exists. The `wgsl_parse` stage does not claim parsed-IR bytes.
- Stage `implementation=unobserved` explicitly withholds implementation execution
  evidence. A stage description is not an invocation trace. Configured compiler
  tools and versions are not silently reported as executed tools. The Metal
  description no longer invents `xcrun` invocations; D3D12 no longer invents `dxv`.
  The configured toolchain file is still hash-bound as policy input, not as
  attestation of installed or invoked tool versions.
- Provider initialization emits no bootstrap shader receipt. Successful
  shader-bearing commands capture owned inputs. The command runtime invokes
  `collectArtifacts` after measuring execution; ordinary telemetry snapshots do
  not load configuration or write files. Collector errors are visible execution
  receipt errors, while actual dispatch/count/timing observations survive. An
  earlier execution failure keeps its original cause.
- The state retains a single pending capture and the latest published path/hash.
  Capture allocates for complete input bytes; it is not claimed allocation-free.
  Failed output keeps pending data for explicit retry or owner cleanup. Vulkan
  discards prewarm/failed-command staging at the next command boundary, before
  selecting current-operation content. Published
  content-addressed files, including blobs written before a later failure, remain
  evidence on disk. Atomic replacement prevents partially published files; this
  is not a disk-durability/fsync guarantee.
- Existing default output and toolchain paths move into `artifact_state.Output`;
  explicit construction can supply borrowed paths. No environment toggle or
  deployment-policy choice is added. Required configuration errors remain errors.
- `file_exists` becomes fallible; callers must distinguish absence from access
  failure. Canonical JSON allocation now preserves `OutOfMemory` instead of
  converting it to `WriteFailed`. Vulkan cache admission releases loaded SPIR-V
  words when key or map allocation fails; allocation injection covers that
  consumer repair without granting it a separate file-review verdict.
- The common elapsed clock changes its epoch. Only differences are meaningful;
  historical timing evidence is not reinterpreted. Unsupported D3D12 diagnostic
  modes return `UnsupportedFeature` and are no longer advertised as capabilities.

These changes affect command-provider evidence and diagnostics. Native WebGPU
objects and ordinary package shader semantics remain their separate execution
path. Accepted package/release binaries are not replaced by the isolated build.
No calibration, incumbent comparison, speedup, or cross-platform support is
promoted by this checkpoint.

## Acceptance evidence

The final aggregate test result is in [aggregate-accepted.log](aggregate-accepted.log),
including format, import/layout, inventory, and contract checks. Shader compiler
checks are retained in [wgsl.log](wgsl.log); documentation links are checked in
[doc-links-final.log](doc-links-final.log). The targeted
core run is in [core-fourth.log](core-fourth.log). Earlier failed logs remain
retained: they exposed allocation-error erasure and incomplete test-call-site
migration, plus test/fixture compile mistakes corrected before acceptance.

[artifact-gate-final.log](artifact-gate-final.log) tests schema compatibility and
rejects missing identity kinds, content without paths, and derived identities
with paths. [schema-confirmed.log](schema-confirmed.log) is the canonical schema gate.
[exhaustive-check.log](exhaustive-check.log), [exhaustive-original.log](exhaustive-original.log),
and [exhaustive-omission.log](exhaustive-omission.log) bind the independent
compile-time omission experiment. [manifest-validation-confirmed.log](manifest-validation-confirmed.log)
validates produced output and content hashes. Schema-only backend probe binaries
under `manifests/` deliberately contain test bytes and are not executable GPU
artifacts.

The ReleaseFast command runtime was built under this evidence directory;
[physical-accepted.log](physical-accepted.log) records the final build and run. The physical
Vulkan trace and metadata are [physical.trace.jsonl](physical.trace.jsonl) and
[physical.meta.json](physical.meta.json). The shader clears a runtime array and
then writes a nonzero sentinel. Its independent little-endian reference is
[expected.bin](expected.bin). The output oracle compares that reference hash;
no provider agreement is used as a correctness oracle. Exact emitted manifest
and SPIR-V copies are retained under `physical-artifacts/`. The validator runs
`spirv-val --target-env vulkan1.1` on those actual bytes.

The supplied `--vendor`/`--api` profile is a selection input, not hardware
attestation. Physical host observations and build identity are recorded in
[environment.txt](environment.txt). This is a bounded command-path correctness
check, not ordinary-provider latency qualification. Metal and D3D12 have no
physical acceptance evidence in this checkpoint.

## Reproduction

From the repository root, with the pinned Zig toolchain on `PATH`:

```bash
(cd runtime/zig && zig build test --summary all)
python3 -m unittest bench.tests.test_shader_artifact_gate
python3 bench/gates/schema_gate.py
python3 bench/out/maintenance/20260919-zig-common-audit/check-exhaustiveness.py
PYTHONPATH=.:bench python3 bench/out/maintenance/20260919-zig-common-audit/verify-evidence.py
```

The compilation mutation script uses a private temporary source copy. Update its
`ZIG` path if the pinned toolchain is installed elsewhere. To regenerate the
schema-only producers, copy `manifest-probe.zig.txt` to
`runtime/zig/.audit-manifest.zig`, run `zig run` on it from the repository root,
and remove that temporary source before regenerating the review inventory.

The physical build and run are reproduced by [run-physical.sh](run-physical.sh).
Use its explicit prefix; it does not install over the accepted runtime. Its
measurement fields remain diagnostic regardless of whether the shader oracle
passes. Historical failed logs are not stitched into an accepted cohort.

For queue continuation retain the starting commit, append genuine examinations,
and validate history against that base even after committing:

```bash
python3 runtime/zig/tools/review_log.py --write --base-ref e24ffcd74b5a04ba819b7f0f338dbacbdd3da726
python3 runtime/zig/tools/review_log.py --check --base-ref e24ffcd74b5a04ba819b7f0f338dbacbdd3da726
```

Component: Zig command backends, artifact contracts, and review tooling.
Intent: preserved.
Acceptance evidence: the commands and hash-bound files above.
Boundary effects: backend ports/runtime explicit collection; versioned config
schema; benchmark manifest consumers; no ordinary WebGPU API migration.
