# Vulkan surface runtime dependencies

The ordinary Vulkan surface helper now receives a typed registry for surface
identity, allocation, native capability discovery, and queue family selection.
Its execution view exposes the device, retirement state, texture registry,
command buffer, and fence that presentation uses. Queue draining, submission
setup, clear, and destruction waits cross a small callback port owned by the
native runtime. The helper no longer accepts the whole runtime through `anytype`.
The runtime still owns the actual queue, render, and destruction methods.

No public descriptor, schema, configuration default, or native admission rule
changed. The [windowed results](windowed-results.json) retain the public fixture's
pixel, exact configuration, failure/retry, and native lifetime checks on XCB
through Xwayland. The observer checks native creations and balanced destruction;
the fixture checks GPU readback, not compositor output. Debug and standalone
ReleaseFast Zig suites pass. A combined ReleaseFast invocation had a policy
fixture collision through a shared temporary file; both suites pass separately.

The [build receipt](build-measurements.json) is a clean private snapshot using
the declared source edit profile. The [process receipt](process-observations.json)
interleaves the prior library from the [surface admission checkpoint](../20260928-surface-admission/README.md)
with this candidate using the unchanged public fixture. Candidate wall-time
tails are variable in this cohort, and the previous checkpoint also retained
variable tails. These observations do not establish a stable performance bound
or speed claim. Library hashes and sizes are in the process receipt. The
original tail variability remains unresolved.

Reproduce from the repository root with the local display and Xauthority set:

```bash
cd runtime/zig
zig build test test-full --summary all
zig build test -Doptimize=ReleaseFast --summary all
zig build test-full -Doptimize=ReleaseFast --summary all
zig build dropin -Doptimize=ReleaseFast --prefix /absolute/candidate
cd ../..
cc -Wall -Wextra -Werror -I runtime/zig/vendor/webgpu-headers \
  runtime/zig/tests/native_surface_handoff.c -L /absolute/candidate/lib \
  -lwebgpu_doe -Wl,-rpath,/absolute/candidate/lib -lxcb -ldl -o /absolute/surface-test
cc -shared -fPIC -Wall -Wextra -Werror \
  runtime/zig/tests/native_surface_observer.c -ldl -o /absolute/surface-observer.so
LD_PRELOAD=/absolute/surface-observer.so /absolute/surface-test admission
python3 runtime/zig/tools/capture_build_measurements.py --output /absolute/build-receipt.json
```

The retained `windowed-results.json` lists every executed mode and raw output.
The physical coverage remains XCB/Xwayland on the available RADV adapter.
Validation layers are unavailable. Other window systems, Metal, D3D12,
frame pacing, broader public surface validation, and complete runtime
decomposition remain outside this bounded interface change.

Component: doe.runtime.zig

Intent: preserved

Acceptance evidence: windowed, build, and process receipts linked above; Zig suites

Boundary effects: typed Vulkan surface registry and submission interface; no public ABI change
