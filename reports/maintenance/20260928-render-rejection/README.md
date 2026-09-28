# Vulkan bundle rejection and build-recipe repair

Standalone Vulkan bundle replay now returns the original `ReplayError` before
submission. An unsuccessful recording releases its scope-owned render target,
view, memory, render pass, and framebuffer. These resources have not been
submitted; their destruction invalidates recorded references. The existing
command-pool reset precedes the next recording. No new wait, runtime toggle,
resource owner, or public descriptor field is introduced.

The helper had no current production caller and was not instantiated by existing
tests. Instantiating it exposed a missing command initializer field and distinct
opaque Vulkan command-buffer pointer types. The unmodified predecessor therefore
fails compilation. The retained compile-only control repairs those admission
issues while preserving the swallowed-error branch; it submits rejected work and
returns success. This is a repair to that standalone helper, not evidence of a
changed ordinary native WebGPU bundle route or application performance.

## Executed evidence

[Identities and outcomes](identity.json) binds source, test/probe binaries, driver,
configuration, and results. [Raw evidence](raw-evidence.tar.gz) retains the original
compilation failure, compile-only control patch, control and candidate execution,
probe sources, compiler options, full runtime test log, and implementation diff.

The permanent regression checks invalid bundles, format mismatch, and sample-count
mismatch, each as the first bundle and after a valid vertex-buffer binding. It
executes a subsequent valid bundle and indexed drawing on the same runtime. The
shared drawing fixture independently expects opaque red pixels through native
readback for both supported index formats. The leading valid bundle records a
binding, not a draw; this isolates replay rejection without introducing an
unrelated graphics-pipeline compatibility requirement.

The temporary interposer observes actual native submissions, vertex bindings,
and exact live image, view, memory, render-pass, and framebuffer handles. Each
rejected sequence makes no submission and returns to its prior live-handle count;
the later-bundle cases first record the valid binding. Repeated valid execution
and final destruction release tracked resources exactly once. Both fence and
timeline paths execute on the pinned Radeon driver. Injected framebuffer
allocation failure exercises partial acquisition cleanup and retry. Its error
remains the existing Vulkan `InvalidState` mapping, independently of the preserved
bundle-specific errors. Earlier probe attempts used an incorrect allocation-error
expectation and omitted explicit timeline initialization; their failed logs remain
separate from final acceptance.

The complete runtime suite passes with its recorded platform skips.
[Documentation, schema, charter, and ledger checks](verification.log) also pass. These tests
exercise physical output and native ownership, not full WebGPU conformance.
Khronos validation layers are unavailable on this host. No performance comparison,
installed-package qualification, Chromium, physical Metal/D3D12, presentation,
or hardware-loss run was performed.

## Build measurement

The stock profile's leaf-backend edit referred to a removed function body.
It now renames the parameter of the existing Vulkan format translation owner,
preserving the switch and mapping. Other edit scenarios and the measurement tool
are unchanged. [Build measurements](build-measurements.json) retains the full
profile, source identity, clean and no-change builds, each edit and restored
baseline, per-build process RSS, and artifact inventory. RSS is the largest
observed process value, not simultaneous build-tree memory. This is diagnostic
workflow validation; it establishes no build-speed or application-speed gain.

## Reproduction

From the repository root:

```bash
python3 runtime/zig/tools/capture_build_measurements.py --output /absolute/output.json
python3 runtime/zig/tools/review_log.py --next
python3 runtime/zig/tools/review_log.py --check --base-ref 466a8d70a
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
```

From `runtime/zig`, select the Radeon ICD and run:

```bash
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json \
  zig build test -Dtest-filter='Vulkan bundle rejection' --summary all
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json zig build test --summary all
```

For the temporary probe, extract the raw evidence and build `probe.c` with
`cc -shared -fPIC probe.c -ldl -o libprobe.so`. In an isolated checkout, copy
`probe.zig` to `runtime/zig/.audit_bundle_probe.zig`, refusing to overwrite an
existing file. From `runtime/zig`, substitute absolute extraction paths:

```bash
zig test -O ReleaseFast --dep build_options -Mroot=.audit_bundle_probe.zig \
  -Mbuild_options=/absolute/evidence/build-options.zig -lc -lvulkan \
  -L /absolute/evidence -lprobe -rpath /absolute/evidence \
  -femit-bin=/absolute/evidence/probe --test-no-exec
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json \
  LD_PRELOAD=/absolute/evidence/libprobe.so /absolute/evidence/probe
```

Remove the temporary source after execution. Reproduce the control from the
predecessor in `identity.json` plus `control-compile-only.patch`; it must fail the
same oracle. The raw probe logs include imported module tests separately from the
named physical test.

## Remaining work

The bounded plan selects occlusion-query reset ordering next. Reset is currently
inside the render pass; [Vulkan requires it outside](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdResetQueryPool.html).
Preserve begin/end around drawing, add a command-order regression, and run layer
validation when available. Surface synchronization and attachment admission remain
separate findings. SPIR-V cache/query ownership remains ready. Narrow Vulkan
resource/submission interfaces and independent Metal/D3D12 examinations remain
unfinished; this batch neither repeats completed compiler/cache work nor grants
whole-file or parent-directory review completion. A generated architecture-catalog
refresh exposed accumulated changes outside this repair and was retained locally
for inspection; checked-in catalogs were not renewed or recertified. The runtime
suite executed the current source-layout and import gates.

Component: Vulkan render execution; Zig build-measurement profile
Intent: preserved
Acceptance evidence: identity.json, raw-evidence.tar.gz, build-measurements.json
Boundary effects: standalone replay now rejects instead of submitting partial work; public ABI and schemas unchanged
