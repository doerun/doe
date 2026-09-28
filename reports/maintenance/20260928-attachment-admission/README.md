# Native Vulkan attachment admission

Ordinary public render-pass recording previously discarded the pipeline's color
format and replaced its sample count with the attachment's. The retained baseline
accepts incompatible pipeline/pass layouts without a validation error. One baseline
reproduction executes the mismatched sample-count draw and passes pixel/query
oracles: plausible output did not establish valid WebGPU execution.

The first missing owner is native WebGPU admission, before command publication,
not Vulkan framebuffer construction. `vulkan_render_attachments.zig` now validates
view availability, device identity, render usage, selected mip/layer shape, format
role, color/depth mip extent and sample compatibility. Pipeline objects retain
the declared color-target format/count. Each draw checks that declaration and the
pipeline depth format and sample count against the pass. The existing encoder
failure state preserves the typed cause and prevents partial command submission.
Empty passes validate attachments without requiring a pipeline. Queue-wide lease
validation still rejects explicit destruction after recording.

The [WebGPU attachment and pipeline rules](https://www.w3.org/TR/webgpu/)
require compatible attachment layouts. The currently implemented Vulkan adapter
represents a color target and optional depth/stencil target. Multiple color targets,
resolve targets, depth-only passes and non-2D attachment views now fail explicitly
instead of silently discarding work or creating substitute attachments. This is
an explicit unsupported boundary, not implementation of those features. Other
backends are unchanged.

## Verification and reproduction

[Identity](identity.json) binds the source, isolated libraries, driver, fixtures,
executed tests and observations. [Public results](public-results.json) records
baseline failures and candidate outcomes. [Raw evidence](raw-evidence.tar.gz)
retains execution logs, the native submission observer, original mismatch source,
and reproduction scripts. Accepted binaries were not overwritten.

The public C regression records a valid draw before the invalid pass, rejects the
whole encoder, verifies the original blue pixels survived, and executes a fresh
red draw on the same device. Native observation independently shows no submission
inside the rejected recording/submission window. Tests cover layout mismatches,
foreign devices, destroyed textures, usage, broad views and unsupported attachment
topologies. Matching depth and selected mip/array-layer views remain successful.
Caller view and pipeline references are released before submission. A separate
query/pixel fixture reconfirms direct and indirect indexed/nonindexed paths.

Canonical tests cover matching selected mip extents and format/sample identities,
plus every allocation failure while recording and retaining an attachment. A valid
draw followed by an incompatible draw in the same pass preserves the original
failure, publishes no second draw and releases each retained reference. The first
version of that test mistakenly used the global allocator to free its private
list; its failed log is retained as test-harness history. The corrected test uses
the allocation owner's cleanup contract.

From `runtime/zig`:

```bash
zig build test --summary all
zig build dropin -Doptimize=ReleaseFast --prefix /absolute/candidate
cc -Wall -Wextra -Werror -I vendor/webgpu-headers tests/native_render_attachments.c \
  -L /absolute/candidate/lib -lwebgpu_doe \
  -Wl,-rpath,/absolute/candidate/lib -o /absolute/attachment-test
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json /absolute/attachment-test samples
```

Use the modes retained in `public-results.json`. Compile extracted `submissions.c`
with `cc -shared -fPIC submissions.c -ldl -o submissions.so` and set its absolute
`LD_PRELOAD` path to reproduce native submission observation. No diagnostic hook
is enabled for the separate [process cost observations](process-observations.json).
Those measurements cover complete query-fixture processes, including startup and
shader compilation; they do not measure resident application latency. CPU and peak
RSS are process-scoped, not GPU residency. [Build observations](build-measurements.json)
reuse the existing isolated capture tool with its leaf-backend edit.

## Migration and limits

This repairs admission behind existing WebGPU descriptors. Internal pipeline
metadata and typed recording failures change; public ABI, serialized command,
trace and report contracts are unchanged. No runtime switch or new policy heuristic
is added. Native admission owns WebGPU semantics; backend recording, image layout,
submission/completion and resource retirement keep their existing authority.
Runtime checks remain necessary because view, device and pipeline identities are
invocation inputs; no proof-elimination claim is made.

Khronos validation layers are unavailable. Surface synchronization, command-oriented
backend attachment admission, complete texture-view validation, depth/stencil
write permissions, store/discard, resolve implementation and general rendering
conformance remain open. Passing matching depth output does not qualify all
stencil or multisample behavior. Compiler, query ordering, SPIR-V ownership,
standalone bundle and build-recipe batches remain closed. This is local native
correctness evidence, not package/browser/Metal/D3D12 qualification, general code
review completion, release admission or an application performance advantage.

Component: native Vulkan attachment admission and command recording diagnostics
Intent: preserved
Acceptance evidence: identity.json, public-results.json, raw-evidence.tar.gz, build-measurements.json, process-observations.json
Boundary effects: native pipeline metadata and validation failure taxonomy; public ABI and backend lifetime owners unchanged
