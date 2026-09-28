# Typed Vulkan draw recording

The production consumer is native WebGPU render-pass recording through
`vulkan_render_pass_native.zig`, queue submission through
`doe_queue_submit_vulkan.zig`, and `NativeVulkanRuntime.run_render_draw()`.
The backend acquires pass resources, prepares index storage, records commands,
submits and establishes completion before scope cleanup. Recorded native leases
keep caller-owned resources alive through this path.

`vk_draw_recording.zig` now records through a concrete `DrawRecording` value.
It borrows a command buffer, a read-only buffer registry, pass/pipeline handles
and a prepared index binding. It cannot access allocator, upload, presentation,
submission, completion or retirement state. The existing render owner retains
resource acquisition, image transitions, command-buffer begin/end and retirement.
Inline index storage remains owned by `RenderState` until completion permits
release. Preparation now precedes pass entry, so failed index allocation cannot
leave a partial render pass. No universal context, runtime callback dispatch,
new policy switch, public descriptor or serialized field is introduced.

## Reproduced correction

The native adapter already records index-buffer identity, format, offset and draw
count. The old direct backend indexed path only handled its other binding form
or inline index data, ignoring the recorded buffer handle. Public direct indexed
draws therefore failed the query and pixel oracles. Resolving a single prepared
index binding now serves both direct and indirect recording and honors that
existing adapter contract. This is a correctness repair alongside the structural
change; it is not labeled exact equivalence to the failing predecessor.

The existing direct, indirect and indexed-indirect paths retain their successful
query results and pixels. The expanded public fixture also checks both direct
index widths, nonzero binding offset and first index, repeated query resolution,
empty queries, reuse and caller release before submission. A native observer
checks query reset/pass/begin/draw/end ordering across each draw mode.

## Evidence

[Identity and outcomes](identity.json) binds source, isolated native libraries,
test inputs and scoped observations. [Public results](public-results.json)
retains predecessor versus candidate disposition by mode. [Raw evidence](raw-evidence.tar.gz)
contains fixture logs, observer and fault-injection sources, build options,
implementation patch, runtime-suite output and cost-measurement commands.

The failure probe executes real indexed draws, then injects failed fence/timeline
waiting, delayed completion, device-loss reports, rejected queue submission and
index-buffer allocation failure. Unresolved completion retains resources; failure
never becomes success. Tracked buffers, memory and mappings are released exactly
once when permitted. Rejected submission/allocation keeps the runtime active and
a following draw succeeds. Device loss is injected after real completion; this
is not physical hardware-loss qualification. The permanent runtime suite also
checks inline indexed pixels and retained allocation lifetimes.

[Process observations](process-observations.json) use fresh interleaved processes
with diagnostic hooks disabled. They measure the complete direct-draw public
fixture, including startup, compilation, rendering, query resolve and readback.
They are not resident-operation latency, Dawn comparison or application-speed
evidence. Process CPU and peak RSS retain their explicit scope. Binary section
sizes and [build observations](build-measurements.json) are diagnostic engineering
costs. The final isolated profile retains the existing leaf-backend edit and
measures clean, no-change, edit and restoration builds. An earlier full-profile
capture overlapped the final use of the canonical vertex-binding limit; its
source-change flag is retained in raw evidence and it is not the final receipt.
The existing build recipe and measurement tool are unchanged.

## Reproduction

From `runtime/zig`, build with an isolated prefix and run the permanent tests:

```bash
zig build test --summary all
zig build dropin -Doptimize=ReleaseFast --prefix /absolute/candidate
cc -Wall -Wextra -Werror -I vendor/webgpu-headers tests/native_occlusion_query.c \
  -L /absolute/candidate/lib -lwebgpu_doe \
  -Wl,-rpath,/absolute/candidate/lib -o /absolute/public-test
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json /absolute/public-test indexed16
```

The fixture accepts `direct`, `indexed16`, `indexed32`, `indirect`, and
`indexed-indirect`. For command observation, compile extracted `order.c` using
`cc -shared -fPIC order.c -ldl -o order.so`, then set its absolute `LD_PRELOAD`
path for the fixture process. The raw scripts bind the exact comparison commands.

For failure injection, compile extracted `fault.c` using
`cc -O2 -shared -fPIC -pthread fault.c -ldl -o libfault.so`. Temporarily copy
`draw-probe.zig` to `runtime/zig/.audit_draw_probe.zig`, refusing to overwrite an
existing file. From `runtime/zig`, substitute absolute extraction paths:

```bash
zig test -O ReleaseFast --dep build_options -Mroot=.audit_draw_probe.zig \
  -Mbuild_options=/absolute/evidence/build-options.zig -lc -lvulkan \
  -L /absolute/evidence -lfault -rpath /absolute/evidence \
  -femit-bin=/absolute/evidence/draw-probe --test-no-exec
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json \
  LD_PRELOAD=/absolute/evidence/libfault.so /absolute/evidence/draw-probe
```

Remove the temporary source afterward. The raw log distinguishes the focused
failure cases from imported module tests.

## Remaining boundaries

Khronos validation layers are unavailable. Surface synchronization, attachment
admission, invalid resource validation and broader descriptor/depth/stencil
semantics remain separate obligations. Other render setup functions still receive
broad runtime state; this batch narrows command recording only. Compiler,
standalone bundle and build-recipe repairs remain closed. No whole-file or
parent-directory review, browser, physical Metal/D3D12, general conformance,
performance advantage or release qualification is claimed. Checked-in generated
architecture catalogs were not refreshed or recertified; current import and
source-layout gates remain the structural checks.

Component: Vulkan rendering and native indexed-draw adapter contract
Intent: preserved
Acceptance evidence: identity.json, public-results.json, process-observations.json, raw-evidence.tar.gz
Boundary effects: typed borrowed recording inputs and corrected native index-buffer consumption; public ABI unchanged
