# Bounded physical Metal validation

## Executable target

On an Apple host with the pinned Zig toolchain, Apple SDK and an available Metal
device, run from `runtime/zig` and retain stdout, stderr and exit status:

```bash
zig build test -Dtest-filter='Metal repair proof' --summary all
zig build test-core -Doptimize=ReleaseFast -Dtest-filter='Metal repair proof' --summary all
```

The executable sequence lives in
[`metal_repair_proof_test.zig`](../../../../runtime/zig/tests/metal/metal_repair_proof_test.zig).
The source and inventory are hash-bound inputs of this checkpoint. Preserve the
checkout commit/diff, OS and SDK versions, device name/registry identity and test
logs alongside any future result. A missing drawable or native acquisition on an
Apple host fails the test rather than becoming a success. A non-Apple host reports
`SkipZigTest`; see [physical-availability.log](physical-availability.log).

| Case | Sequence and independent expectation | Current evidence |
| --- | --- | --- |
| Interleaved staged writes | Write byte 17 to source, queue copy to another buffer, write byte 83 over source, poison caller bytes before flush; expect destination 17 and source 83 throughout. Repeat across increasing boundary sizes and reuse. | Test compiled on Linux; native execution skipped. |
| Boundary-sized transfers | Sizes straddle a row-alignment boundary and the runtime's small-upload capacity. Distinct handles prevent accidental reliance on automatic buffer growth. Repeat each size to exercise reusable storage. | Test compiled on Linux; native execution skipped. |
| Caller input lifetime and dispatch order | Free allocated source after queuing u32 42; compile explicit single-thread raw MSL increment; dispatch, flush and expect exactly 43. | Test compiled on Linux; native execution skipped. This does not qualify WGSL translation or GPU-object early release. |
| Surface retirement | Acquire separate offscreen surfaces, explicitly release one, destroy runtime with the other acquired. Run with native API validation and leak diagnostics. | Test compiled on Linux; native execution skipped. Host recording teardown sequence remains in predecessor evidence. |

## Additional checks still required

The committed fixtures do not yet exercise caller release of a GPU buffer,
sampler or bind group while its submitted command remains in flight. The physical
campaign must record the native-object creation, retained command reference,
caller release, submission, completion and final release. Verify independently
known output and absence of validation errors or leaked references. Freeing a
host byte slice is not evidence of this GPU-object lifetime.

Sampler checks must use the ordinary WebGPU native path with known texture
values: nearest versus linear sampling, clamp versus repeat/mirror at out-of-range
coordinates, and depth comparisons that give opposite results for Less and Greater.
Repeat construction with different descriptors concurrently on distinct device
owners. Compare independent expected pixel/scalar values, not provider agreement.
The source translation probe and cache recording tests do not execute these cases.

Keep allocation-failure injection in a separate run and receipt. Native failed
encoding, failed completion/device loss and unavailable timestamp sampling need
fault-injection checks through their real status bridge once implemented. Do not
label these unimplemented cases as passed, and do not require a speed gain to
accept a correctness repair. Existing performance packages and thresholds stay
outside this checkpoint.
