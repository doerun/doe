# Doppler Vulkan mapping repair

Current source at `acd45ecd2` could not complete the retained Doppler generation
application: the Node bridge requested AllowProcessEvents mapping callbacks but
required delivery before the native call returned. The combined flat runtime
map/copy/unmap adapter had the same assumption. The callback contract intentionally
defers delivery until the owning instance processes events.

The repair makes five Node entry points share a synchronous map adapter that
processes events and propagates callback status. The runtime's combined adapter
uses its existing synchronous mapping boundary. Both retain callback storage
past timeout, releasing it upon eventual delivery. The standard callback modes,
model, shaders, numerical requirements and generation harness are unchanged.

## Evidence

- [Before repair](current/doe-qualification.json): current native library with the
  retained source-bound host package fails `flushAndMapSync` during initial prefill.
  [Log](current/doe-qualification.log) and [provider identities](current/providers.json)
  preserve that failure; this pairing is a diagnostic, not a release qualification.
- [Focused negative control](buffer-map-before-runtime-fix.log): repaired addon
  with the original current-source library still fails combined flat readback.
- [Mapping regression](buffer-map-fixed.log): final addon and runtime pass raw
  map, flush/map, combined readback, invalid-usage rejection/recovery, native direct
  mapping, and a deliberately wrong-instance timeout followed by delivery on the
  correct instance. Timeout coverage applies to the Node adapter; the flat runtime
  timeout path is inspected, not fault-injected here.
- [Doppler](fixed/doe-qualification.json) and [Dawn](fixed/dawn-qualification.json)
  pass all four frozen generation cases against the retained independent CPU
  reference, cancellation, and following generation. [Provider identities](fixed/providers.json)
  bind every file in the current host snapshot plus the library, pinned Doppler,
  and pinned Dawn inputs. This source snapshot is not an isolated installed release.
- [Rendering](render-ownership.log) passes direct/bundled draws, retained resources,
  load/read-only depth persistence and clear. [Command ownership](command-ownership.log)
  passes consumed-command rejection, mapping write-back/detachment and DRM cleanup.
- [Runtime checks](runtime-tests.log): `zig build test-core test-full` exits zero.
  [Package contracts](package-contracts.log), [source layout](source-layout.log),
  and [import boundaries](import-fence.log) pass.

Both retained and repaired Doe application logs contain a Doppler BufferPool
`Deferred destruction failed` warning after device destruction. The frozen harness
reports model unloaded and four devices destroyed, but does not reject that
asynchronous warning. This report does **not** qualify fully settled application
cleanup. Preserve that limitation for the next application acceptance; no Doppler
source changed in this repair.

## Performance boundary and next attribution

[Doe](fixed/doe-profile.json.gz), [Dawn](fixed/dawn-profile.json.gz), and the compressed
[Node CPU profile](fixed/doe.cpuprofile.gz) are diagnostic observations. They are
not an uninstrumented balanced performance cohort. Buffer creation/destruction,
submission and completion are candidate costs, with overlap and full-process CPU
samples preventing a direct critical-path sum. No 20% improvement is established.

Exploratory native sampling remains under the local diagnosis directory: its
process summary was incomplete, some PCs were unmapped and timer overruns occurred.
It is not accepted quantitative attribution. It suggests inspecting descriptor
invalidation and allocator/driver work, but supplies no optimization acceptance.
Do not reopen the rejected buffer-reuse candidate on that basis.

The next engineering step is to isolate the dominant generation cost on the
repaired baseline, including creation/destruction and the unload warning. Freeze
complete-generation acceptance before selecting a general compiler/runtime change.
External recruitment does not gate this work. ONNX transfer is required for a
subsequent general advantage claim; it was not rerun for this bridge repair.

## Reproduction and custody

Run from the repository root, with the pinned model and reference inputs described
in `bench/external-projects/doppler-generation/README.md`:

```bash
node packages/doe-gpu/scripts/build-addon.js
(cd runtime/zig && zig build dropin -Doptimize=ReleaseFast)
export DOE_WEBGPU_LIB="$PWD/runtime/zig/zig-out/lib/libwebgpu_doe.so"
node packages/doe-gpu/test/integration/test-integration-native-buffer-map.js
node packages/doe-gpu/test/integration/test-integration-native-render-ownership.js
node packages/doe-gpu/test/integration/test-integration-native-command-ownership.js
(cd runtime/zig && zig build test-core test-full)
node packages/doe-gpu/test/run-contracts.js
```

Application execution uses the unchanged `run-generation.mjs` with `contract.json`,
a provider manifest, the retained `reference.json`, lane and output path. The
manifests retain the actual local paths and binary hashes; relocations require a
new manifest and new qualification receipts. `source-SHA256SUMS` binds the bridge,
regression, workload and reference files. Published ONNX binaries and historical
performance verdicts were not modified.

Component: native host mapping adapters. Intent: preserved.
Acceptance evidence: the commands and artifacts above.
Boundary effects: Node and flattened C ABI adapters now honor native callback
readiness; no compiler, model, backend-selection or ABI-layout change.
