# Ordinary Vulkan occlusion queries

Public WebGPU recording reaches the Vulkan queue submitter and the backend draw
executor. Each native draw currently submits and completes separately. The query
owner now preserves zero/nonzero visibility across these completed observations;
a recorded logical begin clears the result, including queries with no draws.
Resolve embeds the current result snapshot in Vulkan update commands, with an
explicit dependency on earlier accesses. Later query reuse cannot change an
already recorded resolve. Query references remain owned by the recorded commands.
No public descriptor, serialized artifact, tuning switch, or schema field changes.

The native pool now uses Vulkan's occlusion enum, and every physical reset precedes
render-pass entry. Begin/end surround drawing. The old eager initialization used
a fence-dependent one-shot submission even when the runtime had no fence. It was
redundant with draw resets and is removed. Never-issued queries resolve to zero.
The synchronous draw path already confirms completion before collecting hardware
results; collection introduces no additional wait. Its CPU cost is unmeasured.

## Evidence and reproduction

[Identity](identity.json) binds source, isolated libraries, fixture, and native
observer. [Raw evidence](raw-evidence.tar.gz) retains code, implementation diff,
build/test logs, public fixture results, and the command-order observation.
The unchanged predecessor fails public query creation before rendering. This is
separate from the reset-order and multi-draw defects found by source inspection;
no claim is made that the predecessor physically demonstrated those later defects.

The public C fixture records a visible draw followed by an occluded draw, reverses
that order, checks fully occluded and unused queries, resolves repeatedly, and
reuses queries through empty and subsequent visible submissions. It releases the
caller's query reference before the final submission. Independent readback expects
opaque red or black pixels; query checks use only zero/nonzero visibility. The
native observer checks pool type and reset/pass/begin/draw/end order. The runtime
suite passes with its recorded platform skips.

From `runtime/zig`, build an isolated library:

```bash
zig build dropin -Doptimize=ReleaseFast --prefix /absolute/query-prefix
zig build test --summary all
cc -Wall -Wextra -Werror -I vendor/webgpu-headers tests/native_occlusion_query.c \
  -L /absolute/query-prefix/lib -lwebgpu_doe \
  -Wl,-rpath,/absolute/query-prefix/lib -o /absolute/query-test
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json /absolute/query-test
```

Extract the raw evidence and compile `order.c` with
`cc -shared -fPIC -Wall -Wextra -Werror order.c -ldl -o order.so`.
Set `LD_PRELOAD` to its absolute path for the fixture process only. It rejects
invalid ordering and missing query draws. This temporary observer is diagnostic,
not a runtime instrumentation surface.

## Limits and next work

Khronos validation layers are unavailable on this host. This physical Linux
AMD/Vulkan test is not WebGPU conformance, release qualification, browser testing,
or physical Metal/D3D12 evidence. Full query validation and broader rendering
semantics remain unqualified. Surface synchronization and attachment admission
retain their separate findings. SPIR-V instruction-cache ownership is next;
completed bundle and build-recipe work stays closed.

Component: native WebGPU query recording and Vulkan rendering/submission
Intent: preserved
Acceptance evidence: identity.json, raw-evidence.tar.gz
Boundary effects: internal recorded logical-query begin and retained query metadata; public ABI unchanged
