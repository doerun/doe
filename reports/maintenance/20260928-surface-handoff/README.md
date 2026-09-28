# Ordinary Vulkan surface handoff

The ordinary public surface consumer acquired an image without waiting before
rendering, reused binary semaphores in each clear, presented without a wait, and
reported success on out-of-date presentation. Its acquired texture also lacked
a device reference and was freed directly even when callers retained it. The
retained baseline fails the windowed pixel fixture. These are separate ownership
and synchronization defects; the failed pixels alone do not attribute each one.

The candidate gives the swapchain a typed completion owner. Acquisition uses a
fence and completes before exposing the image. Clears and draws use ordinary
submission. Presentation flushes queued work, transitions the exact acquired
texture to presentation layout, and signals a binary semaphore in a final
submission. Presentation waits on that semaphore and supplies its own fence;
that fence authorizes semaphore reuse and swapchain destruction. Device idle
alone does not establish presentation ownership. The implementation follows the
[Khronos presentation-fence lifetime contract](https://docs.vulkan.org/refpages/latest/refpages/source/VkSwapchainPresentFenceInfoKHR.html).

Partial setup rolls back. Unknown acquire/present completion retains its owner
and retries during destruction; confirmed device loss is handled separately.
Rejected submission can retry without pretending a signal happened. Rejected
presentation can retry its existing signal, while the texture expires to prevent
intervening writes. Out-of-date presentation fails publicly and expires the
texture; recreation waits for its presentation fence. An acquired texture has
separate surface and caller references and retains its device. Present,
reconfigure and unconfigure invalidate further use without freeing caller-held
objects. An image presented without rendering is cleared through the existing
render executor before the final transition.

## Support boundary

The versioned capability inventory declares native Vulkan windowed presentation's
requirement for `VK_EXT_swapchain_maintenance1`, its feature and instance
extension dependencies. Device creation queries support; surface configuration
rejects unavailable support explicitly. Offscreen execution remains available.
There is no hidden device-idle fallback and no production diagnostic switch.
This is a tighter, explicit support boundary. Native capability/format admission,
other window systems, frame pacing and broader rendering qualification remain
separate obligations.

## Evidence and reproduction

[Diff](source.diff), [identity](identity.json), [public results](public-results.json),
[verification log](verification.log), [build observations](build-measurements.json),
[process observations](process-observations.json) and [raw evidence](raw-evidence.tar.gz)
bind the local source, isolated libraries, commands and outcomes. The accepted
library was copied and not overwritten. Failed intermediate builds and earlier
fixture runs remain in the raw archive; final qualification uses the library
identified in `identity.json`.

The public C fixture uses a real XCB window on Xwayland and physical RADV Vulkan.
It records repeated clears and a draw, copies pixels back through ordinary
WebGPU, and checks independently specified colors. It exercises recreation,
repeated acquisition, early caller release, expired-view rejection and references
surviving surface/device release. The test-only native interposer checks acquire
completion before submission, presentation semaphore/fence ownership, and
balanced native destruction. It injects rejected submit/present, out-of-date
presentation, failed waits followed by completion, partial native setup failures,
unavailable presentation-fence support and device loss. Out-of-date and device
loss are injected after real driver work; they do not establish physical display
loss or hardware-reset qualification. Pixel checks concern GPU readback, not a
compositor screenshot. An empty-present case checks completion and cleanup.

From `runtime/zig`, with a valid local `DISPLAY` and `XAUTHORITY`:

```bash
zig build test --summary all
zig build dropin -Doptimize=ReleaseFast --prefix /absolute/candidate
cc -Wall -Wextra -Werror -I vendor/webgpu-headers tests/native_surface_handoff.c \
  -L /absolute/candidate/lib -lwebgpu_doe -Wl,-rpath,/absolute/candidate/lib \
  -lxcb -ldl -o /absolute/surface-test
cc -shared -fPIC -Wall -Wextra -Werror tests/native_surface_observer.c \
  -ldl -o /absolute/surface-observer.so
LD_PRELOAD=/absolute/surface-observer.so /absolute/surface-test present-wait
/absolute/surface-test normal
```

The raw runner enumerates the executed fault cases. The final normal run disables
interposition. Offscreen query/pixel regression cases exercise the same isolated
library. Process observations use independent interleaved offscreen fixtures,
including startup, compilation, readback and teardown; they are not resident
application timings or presentation throughput measurements. RSS is the process
high-water mark, not GPU memory. Build observations use the existing private
snapshot tool. There is no Dawn speed claim. The candidate cohort records higher offscreen CPU
consumption; these observations do not establish performance equivalence.
Startup capability discovery remains a cost to examine.

Validation layers were unavailable. Wayland, Xlib, other drivers, simultaneous
windows, actual GPU loss, exhaustive host allocation failure and the full WebGPU
surface validation contract were not qualified. Blocking gate policy is
unchanged. This checkpoint is local correctness and ownership evidence, not
release or whole-backend qualification.
