# Ordinary Vulkan surface admission

The retained public reproduction requests an sRGB RGBA texture and receives a
linear BGRA texture. Public capability arrays were static, ignored the adapter,
and used presentation/alpha values inconsistent with the pinned WebGPU header.
Configuration also discarded unsupported usage bits and substituted unsupported
formats. The reproduction is in [baseline evidence](baseline-reproduction.log).

The backend now derives canvas capabilities from native adapter/window facts and
uses the same format, presentation, alpha and usage tables for admission. Exact
format and sRGB color-space identity, supported usage and requested extent are
required before swapchain retirement. Only declared auto/undefined mode defaults
select a supported mode. HDR, alternate view formats and descriptor extensions
reject explicitly. There is no format fallback or production diagnostic switch.
The neutral FIFO default agrees with the existing command parser and pinned ABI.

Before device creation, capability discovery uses a temporary native instance and
surface, the adapter's captured queue-selection policy, and its retained identity
check. No logical device or swapchain is created by that probe. Once configured,
the query uses the bound device. Returned arrays belong to the caller and survive
surface/device destruction; partial allocation rolls back. Configuration errors
reach device error scopes; a public configuration must explicitly supply its device. Unsupported reconfiguration preserves the current
texture and swapchain. Once an admitted replacement retires the old swapchain,
native creation failure leaves the surface unconfigured and allows retry.

Failure injection exposed Vulkan allocation errors being collapsed into
`InvalidState`. The shared native error translation now preserves `OutOfMemory`;
submission-retention rules are unchanged. Tests preserve their earlier lifetime
assertions while expecting the corrected error. The prior acquire/render/present
completion and native reference repair remains in place.

## Evidence and reproduction

[Source identity](final/identity.json), [diff](final/source.diff), [public results](final/public-results.json),
[verification](final/verification.log), [build observations](final/build-measurements.json),
[process observations](final/process-observations.json), [confirmation](final/confirmation.json)
and [raw evidence](final/raw-evidence.tar.gz) bind the isolated builds and executed work.
The `final/` artifacts include the final null-device rejection regression. Earlier
top-level artifacts retain the preceding candidate and are not qualification of
the final library. The baseline is retained independently. Earlier failed tests and the disk-space
failure remain in raw evidence; they do not qualify the final candidate.

The public C fixture queries capabilities before requesting a device, checks
invalid-adapter rejection, and creates a real XCB window on Xwayland. It compares
texture identity and GPU readback against independently specified linear and
sRGB encoded colors. It covers supported presentation/alpha modes, usage,
unsupported initial configuration, rejected replacement with a retained acquired
texture, valid subsequent rendering, repeated acquire/reconfigure, caller release
and capability-array survival beyond surface destruction. The native interposer
records actual swapchain properties and checks the retained completion/lifetime
rules, failure injection and balanced native cleanup. Pure tests cover absent
format/color-space/mode/usage support and every capability-array allocation failure.

From `runtime/zig`, with a valid local `DISPLAY` and `XAUTHORITY`:

```bash
zig build test test-full --summary all
zig build dropin -Doptimize=ReleaseFast --prefix /absolute/candidate
cc -Wall -Wextra -Werror -I vendor/webgpu-headers tests/native_surface_handoff.c \
  -L /absolute/candidate/lib -lwebgpu_doe -Wl,-rpath,/absolute/candidate/lib \
  -lxcb -ldl -o /absolute/surface-test
cc -shared -fPIC -Wall -Wextra -Werror tests/native_surface_observer.c \
  -ldl -o /absolute/surface-observer.so
LD_PRELOAD=/absolute/surface-observer.so /absolute/surface-test admission
/absolute/surface-test srgb
```

The raw runner owns the complete executed case list and verifies native format,
color-space, usage, extent and presentation values, including absence of native
creation for rejected configurations. Confirmation disables the interposer.
Process observations compare the unchanged previous public fixture with both
libraries in independent interleaved processes. They include startup,
compilation, repeated frames, GPU readback and teardown; they do not measure
resident application latency or isolate capability-query overhead. That fixture
does not call `GetCapabilities`. Process RSS is a high-water mark, not GPU memory.
The final cohort has a higher candidate wall-time tail; the earlier cohort has
a higher baseline tail. Both remain retained. The small samples do not establish
equivalence, a stable regression bound, or a presentation-throughput improvement.
Build observations use the existing private-snapshot profile; binary size and
build observations do not establish a performance advantage.

## Limits and disposition

This is local correctness and implementation-quality evidence, not release
qualification or a Dawn comparison. Validation layers are unavailable. Pixel
checks observe GPU readback, not compositor output. Native XCB on physical RADV
is exercised; Wayland, Xlib, Metal and D3D12 are not physically qualified here.
Presentation loss and device loss are injected, not physical display removal or
hardware reset. HDR, alternate view formats, additional descriptor extensions,
resizing via implicit scaling, frame-latency policy and pacing remain unsupported
or separately unqualified. Array bounds retain explicit failure when native
capability enumeration exceeds supported storage.

Adapter matching retains the existing vendor/device/driver/name tuple rather than
introducing UUID ownership in this batch; same-model multi-adapter selection is
not independently demonstrated. Configured surfaces still bind to their original
device. Broader public surface validation/error delivery and typed runtime
resource/submission dependencies remain unfinished reviews.

Component: doe.runtime.zig
Intent: preserved
Acceptance evidence: linked executed artifacts and retained public/inline tests
Boundary effects: native surface ABI admission, Vulkan capability/configuration,
shared native allocation-error taxonomy; public layouts and schemas unchanged
