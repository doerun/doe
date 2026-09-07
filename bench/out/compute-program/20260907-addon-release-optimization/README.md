# Addon optimization experiment

The retained baseline is `../20260907-concurrent-qualified/summary.json` at source
revision `73b62124c8ed8b6804b5c6f98dbd2eddd14188dc`. `cc-o2` adds the compiler's
optimization option to the existing addon build without changing runtime code,
JavaScript, shaders, numerical acceptance, or the native Zig library. The exact
experimental package passes controlled-host qualification at
`../20260907-addon-o2-qualified/summary.json`.

`addon-sizes.txt` and `retained-addons/` establish a smaller addon file and text
section. This is a size-only experimental result. Application latency did not
establish a benefit, and the build default was not changed. Subsequent accepted
work uses the baseline addon hash.

The first frozen application matrix at
`../20260907-addon-o2-applications/summary.json` was rejected by the unrelated GPU
activity gate. The fresh run at
`../20260907-addon-o2-applications-retry/summary.json` passes artifact and work
verification in `experimental-verification.log`; its rows remain diagnostic.
`alternate.py` compares the two exact packages in alternating process order
through the existing admitted runner. `alternating.log` preserves an incomplete
attempt rejected by unrelated GPU activity. Its partial samples cannot establish
an accepted cross-application result.

`cpu-profile/` uses the accepted baseline package. Its retained runner enables the
Node inspector after warmup and saves a CPU profile around the sampling loop.
The profile includes reference calculations, output files, and instrumentation
outside the measured program invocation. Those costs must not be attributed to
Doe execution. Use ordinary unprofiled measurements for performance conclusions.
The profile pointed to native dispatch recording; the following correction is
retained separately at `../20260907-binding-storage/`.

`perf-availability.log` records that kernel profiling was unavailable under this
host's permissions. No system permission or benchmark acceptance setting was
changed. `SHA256SUMS` binds the experiment files; installed dependency trees are
reproducible inputs rather than retained output.
