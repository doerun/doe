# Submission resource availability

`baseline.txt`, `source.patch`, and `SHA256SUMS` bind this correction and its
retained evidence. `baseline-native.log` records the preceding native library
accepting a copy whose source remained mapped at submission. The exact baseline
fixture/executable and `baseline-library.sha256` are retained here; the baseline
library is also in `../20260907-buffer-copy-admission-qualified/`.

Command references now carry a resource kind. The queue validates the entire
submitted batch before invoking a backend, without allocating or changing lease
ownership. Checks follow buffers, textures, views, bind groups, external texture
planes, query sets, and nested render-bundle dependencies. Error scopes preserve
an actionable validation cause. Query commands use the same reference list for
retention, validation, and release instead of walking recorded commands separately
during cleanup. Existing allocation-failure tests exercise that ownership path.

Explicit texture destruction marks future execution and writes unavailable.
Backing storage remains retained by live views and command owners until release.
A texture view may still be constructed from a destroyed texture; it cannot make
that texture available for execution. A mapped buffer may be encoded and then
unmapped before submission. Releasing the caller reference is not destruction.
Public signatures and receipt schemas are unchanged; the internal lease metadata
migration and blocking acceptance requirements are in `docs/process.md`.

The C fixture checks mapped/destroyed source and destination buffers, a valid
first command buffer preceding an invalid second one, and a readback witness
that must remain unchanged when the batch is rejected. Accepted copies must
produce independent expected bytes after unmapping or caller release. Texture
cases compare caller release with explicit destruction, reject writes after
destruction, and continue through valid fused compute and layered/resident
buffer-image transfers. Canonical tests additionally exercise bind groups,
render bundles, expired external textures, destroyed queries, and unchanged
reference counts across validation.

`debug-initial.log` retains an invocation from the wrong working directory.
`debug-compile.log` and `debug-second.log` retain intermediate compile failures
from the new enum spelling and migrated test cleanup calls. The final canonical
runs are `debug.log` and `release-fast.log`. `release-fast-intermediate.log`
preceded a correction preserving view creation independently of submission
availability. None of those intermediate records establishes final acceptance.

Reproduce from the repository revision containing this patch:

```sh
cd runtime/zig
zig build test test-wgsl --summary all
zig build test test-wgsl dropin dropin-compute dropin-full -Doptimize=ReleaseFast --summary all
```

Compile `runtime/zig/tests/native_recorded_compute.c` using the retained C build
recipe in `../20260907-texture-transfers/README.md`. Run the resulting executable
with `DOE_PROGRAM_IDENTITY_TRACE_PATH` pointing to an already created empty file.
Verify the journal with `python3 bench/cli.py program verify-native`. Enable the
Khronos layer using the extraction and environment recipe in that same README;
reject validation errors and synchronization hazards regardless of process exit.
The layer identity is bound by its `validation-tool.sha256`.

The physical run passed in `native-run.log`; `vulkan-validation.log` retains the
Khronos synchronization-validation run. `native-validation.json` verifies the
completion journal and retained shader binaries. The controlled-host runs also
enabled the same layer; their retained streams contain no native validation or
synchronization-hazard diagnostics. Package identity is bound by the adjacent
`../20260907-submit-availability-qualified/summary.json`. Require matching native
library hashes across the direct C run and every controlled host. Package
qualification covers fresh Node, Bun, and Electron main-process installations
from the same retained archives; it does not establish publication.

This is targeted AMD Vulkan correctness and lifecycle evidence. It does not
establish complete WebGPU conformance, command-buffer consumption rules,
texture-origin/aspect support, concurrent queue safety, physical Metal/D3D12,
driver-loss recovery, peak GPU memory, or a measured application advantage.
