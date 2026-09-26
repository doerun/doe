# Ordinary reranker allocation investigation

Component: Zig Vulkan allocation and storage binding.
Intent: preserved.
Acceptance evidence: `tests-final.log`, `confirmation/`, `promotion/`, `sequence-results.json`, `capture/`, `native-regression/`.
Boundary effects: versioned buffer memory policy; application, compiler, synchronization and public API contracts unchanged.

## Acceptance state

The candidate at the commit recorded in `confirmation/preflight.json` is accepted
as a bounded local reranker improvement. The clean interleaved cohort passed the
frozen oracle and GPU-activity checks; both candidate process medians were below
both unchanged-Doe process medians. `confirmation/comparison.json` contains raw
summary statistics and per-process variation; `confirmation/effect.json` states
the measured portion of the deficit removed. Dawn remains faster. This is not
release qualification, application promotion, or a general runtime speed claim.

`second-workload/comparison.json` records the existing pinned UMAP SGD check.
Correctness and exact provider replay passed, but the latency advantage did not
transfer. Candidate central latency was higher in this small sample; a possible
regression remains unresolved. Keep the improvement scoped to the reranker.
Accepted package binaries are intact. Earlier rejected confirmation attempts
remain excluded from all before/after comparisons.

## Mechanism and correction

Ordinary WebGPU buffer creation used the first compatible host-visible coherent
memory type. First storage binding promoted large buffers to device-local memory.
That promotion allocated another buffer and copied its complete contents through
`copy_buffer_region_and_wait`, which drains earlier recorded work and waits for
the copy. Repeated allocation in resident reranking therefore introduces waits
inside the application's logical compute passes.

The candidate prefers a compatible memory type that is already device-local and
records the actual allocation property flags. Storage promotion retains that
allocation, its mapped address, generation and contents. Unknown property flags
retain the conservative allocation-and-copy path. Readback selection, initial
zeroing, mapping requirements, access barriers and completion ownership are
unchanged. The fallback is the existing required-properties selection, explicitly
represented in the versioned policy. Allocation errors remain errors.

The predicted reductions are native allocation count, promotion copy bytes,
mid-sequence waits and resident reranking latency. The native call observations
in `promotion/baseline-counts.json` and `promotion/candidate-counts.json` confirm
the first two. Their timed samples include query instrumentation and native call
logging. They are mechanism diagnostics, not confirmation timings. Summed fence
wait duration can increase as formerly fragmented work becomes longer individual
waits; it is not independently additive to the GPU intervals.

## Attribution and generated code

`shader-costs.json` ranks historical family excess, including grouped RMSNorm
variants; `shader-costs.csv` includes invocation counts, cumulative intervals,
final instruction counts, register allocation and scratch statistics. Historical
per-dispatch profiling split compute passes and cannot account for the current
application deficit. These intervals can include host-induced gaps between native
submissions. They are not isolated shader instruction costs.

`sequence-results.json` retains and compares complete original pass and dispatch
sequences. The candidate diagnostic uses the same observer plus native call
logging; the unchanged provider observations are separate. Dawn timestamp
quantization and process-boundary GPU monitoring remain measurement limitations.

The retained-source RMSNorm, Q4 and F16 isolated probes are in `rms/`, `q4/`, and
`f16/`. They use explicit layouts, original entrypoints and representative original
dispatch geometry with deterministic independently checked data. They are resident
buffer probes, not replays of captured model buffer contents. The large historical
penalties did not reproduce. `capture/` retains actual application WGSL, pipeline
constants, SPIR-V, final RADV disassembly and driver statistics. Pipeline creation
order binds those driver statistics to the captured family list. The Q4 isolated
Doe SPIR-V digest matches the application module. Scratch traffic and costly
indirect local-array access were not established as a recoverable cause. No
compiler transformation or synchronization tracker was implemented.

`crossover/` contains a diagnostic replacement prepared from Doe Q4 SPIR-V for
Dawn's Vulkan setup, changing only the exported entrypoint name. Descriptor sets,
bindings, buffer layout, workgroup size and override defaults were inspected;
`spirv-val` accepted the renamed module. The initial execution did not establish
that replacement took effect and is excluded from crossover attribution. Its
filename used the dump prefix, whereas the inspected Mesa replacement path omits
that prefix. The corrected isolated replacement passes its numerical check and produces
byte-identical final shader disassembly to Doe's original under Dawn's Vulkan
setup; `crossover/isa-verification.json` records the hashes and driver statistics.
Its timing is not application confirmation. The reverse
crossover was not attempted: Dawn's module requests Vulkan memory-model features
that Doe's enabled device-feature chain does not establish. This remains local
compiler diagnosis, never a production fallback. Capture/replacement uses Mesa's
[existing SPIR-V debugging facilities](https://docs.mesa3d.org/spirv/index.html).

## Frozen inputs and execution evidence

`input-identities.json` records the unchanged archive, installed-file validation,
Capsule, oracle and installation identities. `libraries.json` freezes baseline,
candidate, compiler and driver binaries. The archive receipt does not establish
an exact Doppler source commit; the archive hash and installed bytes are the
executed identity. Current source began at the commit recorded in
`input-identities.json`. `changes.patch` records the candidate source delta.
Accepted libraries and installed application files were not overwritten.
`rdpull.log` records the requested repository synchronization.

`baseline/` is a fresh balanced unchanged-Doe/Dawn cohort. It is separate from
all historical comparisons and later confirmation attempts. `confirmation/`
uses the same installed application operation, warmup/sample policy, numerical
oracle and tolerances, with query wall time, query CPU consumption, post-query
process RSS and whole-process resource logs. Startup is recorded separately.
Native instrumentation and Mesa shader replacement are forbidden there.

Confirmation attempts under `confirmation-rejected-activity/` and subsequent
rejected attempts are excluded. The activity gate observed other Doppler GPU
qualification work. The completed clean cohort is retained separately in `confirmation/`. Its
preflight records a HEAD change caused by committing the existing candidate; all
frozen source, library, toolchain and installed-package hashes still matched.

## Tests and remaining limits

`tests-final.log` records the successful aggregate Zig suite, including required
architecture and formatting checks. The focused regression proves that promotion
of an already device-local mapped buffer retains identity and contents with a
failing allocator and no native GPU handles. Memory selection tests cover an
available preference, a masked preference and missing required properties.
`schema.log` and `doc-links.log` record the blocking schema and documentation checks.
`native-regression/test.log` records physical allocation-failure sweeps, zero
initialization, mapped-content preservation, conservative copy for unknown
properties and final native buffer/memory/mapping balance. The probe uses the
retained upload-audit fault injector and current generated build options.

Early test attempts exposed a missing fixture field, stale source-layout hashes
and a test-only import cycle. The corrected regression lives in the existing
Vulkan unit-test surface; no production import cycle was admitted. The first
native call interposer could not resolve RTLD_NEXT through the Node loader and
aborted before reranking. The retained retry resolves the installed Vulkan loader
explicitly and passes the oracle. A confirmation attempt rejected for foreign
GPU activity is not evidence of performance or correctness failure.

RSS observations describe this process at query boundaries; they do not measure
GPU residency, total shared-memory use, native heap peaks or release leaks.
Native allocation counters cover intercepted Vulkan operations, not all host
allocations. No current release qualification, parity claim, broad workload claim,
Metal/D3D12 expansion, prepared-program comparison or architectural reorganization
is included. The second workload does not support broadening the reranker result and records
a possible small-workload regression. The rejected synchronization experiment
remains rejected.

## Reproduction and retained package

The executed commands are retained in `outcome.json` and the runner scripts.
Use a fresh artifact destination for another run; do not overwrite this cohort.
The comparison runner uses the already frozen library prefixes. Rebuilding the unchanged control requires a clean checkout of the
recorded base commit; building the candidate uses its recorded commit or `changes.patch` on that base.
Both use the pinned Zig compiler and `zig build dropin -Doptimize=ReleaseFast`
from `runtime/zig` with an isolated `--prefix`. Do not rebuild the baseline from
the modified working tree. The normal runner retains the same application
warmup and timed-query interval as the initial baseline.

The aggregate check is `zig build test --summary all` from `runtime/zig`.
The native regression source and generated options are retained beneath
`native-regression/`; its temporary module root was removed after execution.
Physical memory support remains driver-dependent, so the explicit runtime
property check and conservative fallback cannot be eliminated by assuming that
every supported host-visible type is device-local. No new Lean proof is claimed.

`raw-receipts.tar.gz` packages the diagnostic sources, captures, raw receipts,
logs and projections, including copies of the second-workload receipts. `checksums.json` binds retained local files, including
isolated binaries. Installed model/archive bytes remain at their pinned paths
rather than being republished in the diagnostic package. The initial clean
baseline's shared-statistics p50 uses the repository's nearest-rank percentile
convention; raw samples, mean, tails and per-process statistics are retained so
Dawn's bimodal sample distribution remains visible.
