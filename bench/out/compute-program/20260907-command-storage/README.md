# Bounded native command storage

`baseline.txt` identifies the previous implementation, qualified in
`../20260907-dispatch-copy-qualified/summary.json`. The candidate archive pair is
`../20260907-command-storage-qualified/summary.json`. This correction changes
ordinary native command preparation; it requires no application or WGSL edits.

## Responsible work and invariant

The profile in `../20260907-dispatch-steady-sampling/` points to repeated host
mapping and command-array growth. Native command recording reserves array storage
in `doe_command_recording.reserve`; dispatch, copy, and query callers populate it.
`doe_encoder_native` previously freed that array on every final encoder or
command-buffer release. The native probe isolates this recording work and keeps
GPU validation outside its timed region. Its source, warmup, complete raw samples,
loaded-library paths, alternating process order, and shared percentile calculation
are retained here. Syscall tracing includes driver/setup activity and perturbs
execution; it is a locator, not an unprofiled application latency measurement.

`doe_command_storage.Pool` is the device-owned authority for empty array capacity.
An encoder takes an exclusive loan after acquiring its device reference. Finish
transfers the array and resource leases to the command buffer. Final release
releases every resource lease before returning empty capacity. Device references
keep the pool alive until all borrowers close. Final device release frees retained
storage. The array has no live commands while cached, and no GPU resource is
retained by the pool. A device-local mutex protects the available slot; concurrent
borrowers never share command contents. Allocator identity, the idle byte bound,
and an already occupied slot determine whether returned storage is reusable.

`config/native-command-storage-policy.json` defines the build-time idle storage
bound. Zero disables retention. Live arrays are caller-owned and outside that
idle bound. Oversized and foreign-allocator storage is freed normally. No global
allocator replacement, new runtime switch, command capture, arithmetic change,
barrier removal, or public ABI transition is introduced. The config schema and
migration are in `docs/config-schema-enforcement.md`; `docs/process.md` retains
the blocking ownership, correctness, and evidence requirements.

## Acceptance

`tests-debug-final.log`, `tests-release.log`, and `build-release.log` retain
canonical Zig tests and architecture/public-interface gates. `schema.log` covers
the registered config policy. Package helper tests use unittest; the structural
documentation tests run directly in `doc-tests.log` because pytest is unavailable
on this host. The new tests cover exclusive loans, empty reuse,
byte bounds, allocator identity, separate devices, concurrent access, and released
resource references. Existing systematic allocation-failure cases now exercise
fresh and prepopulated pools across compute, rendering, copies, and queries.

`package.log` records clean Node, Bun, and Electron main-process installation from
the same retained archive pair. `verify-native.py` independently verifies archive
and artifact hashes, staged versus extracted native/addon bytes, matching host
library identity, and the unchanged exported symbol set. `independent-package.log`
records its result. The wrapper archive and addon bytes are unchanged by this correction.

`run-native-validation.py` executes the public C ownership and copy regressions
against the extracted library. `native-validation.log` and `final-validation/`
retain commands, source fixtures, and raw output. Vulkan validation and
synchronization checking must be active, and either error category rejects the
run even when the process exits successfully.

`run-final-prolonged.py` verifies installed package bytes before and after the
existing prolonged resource and live simulation fixtures. Its independent CPU
checks, sampled DRM allocation totals, worker RSS, cancellation/reset/reopening,
and device cleanup remain bounded observations. They are not peak GPU residency,
physical driver-loss recovery, or arbitrary worker-termination qualification.

## Measurements and limits

`../20260907-command-storage-applications/summary.json` retains frozen shaders,
inputs, numerical acceptance, incumbent controls, completion schedules, readback,
preparation, cold operation, repeated latency, CPU costs, and cleanup. The effective
policy and native storage config are hash-linked with the source inputs.
`application-verification.log` records independent matrix verification.

`compare-previous.py` alternates exact previous and candidate packages through the
existing admitted application runner. `alternating/comparison.tsv` reports lower
encoding costs across applications and lower median complete-operation latency;
slow tails remain mixed. `alternating/process-costs.tsv` retains startup, cold
operation, preparation, cleanup, requested buffer bytes, and process RSS. This
is a measured ordinary-runtime correction, not an across-the-board latency or
memory reduction claim.

`native-record-cost-validated/comparison.tsv` shows the removed native recording
and cleanup cost through the measured tails. Each process executes an untimed GPU
oracle after recording samples. Native preparation timing cannot substitute for
complete useful-operation latency.

`summarize-ordinary.py` checks accepted outputs and matching work receipts before
producing `ordinary-incumbents.tsv`. Ordinary Doe's simulation comparison is
encouraging; image and heat comparisons remain mixed. Prepared comparisons remain
in the original matrix. The large Deno/wgpu ratios are suspicious host/polling
observations and cannot establish leadership. Every row remains diagnostic.

`steady/` preserves a rejected longer-sampling attempt: unrelated GPU activity
failed the existing gate. The retry uses the identical diagnostic policy. The
original frozen sampling policy, rejected attempt, and incumbent controls are
retained without weakening acceptance thresholds. `steady-retry/alternating/`
reports improved image and heat wall median and tails. Simulation wall median
and p99 improve, while p95 is slightly worse; its CPU p95 also regresses. The
longer policy changes only warmup and sample counts, identically for both
packages. It does not replace the mixed original frozen-policy result.

`syscall-profile.command.json` records paired previous/candidate strace commands.
The `*-memory-syscalls.txt` summaries show fewer mappings, unmaps, and remaps
in this probe. Profiled timing remains diagnostic;
unprofiled native and application samples above establish the measured effect.

Canonical model acceptance and its independent verifier are retained at
`../../external-projects/doppler/20260907-command-storage-p0-qualified/result.json`
and its sibling `independent-verification.log`. The frozen oracle, unchanged
source-built P0 control, loaded binary hashes, transcripts, and exact package
files pass verification. The unmodified npm control in Electron is not newly
qualified by this result.

The Linux implementation checklist in `docs/status/reusable-compute-programs.md`
is closed for this bounded pass. Every application comparison remains diagnostic;
performance leadership is a separate, unestablished outcome. Earlier resource
and independent-worker evidence remains at `../20260907-linux-completion/README.md`
and `../20260907-async-pipeline-ownership/README.md`.

Physical Metal and D3D12 testing, publication, production signing, independent
adoption, and broader performance leadership are outside this Linux milestone.

Component: native command ownership and storage
Intent: preserved
Acceptance evidence: canonical Zig checks, exact-package qualification, public C regressions, application and resource records
Boundary effects: internal device-owned host capacity; versioned retention policy; public interfaces preserved
