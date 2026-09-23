# Qwen reranker ownership and synchronization experiments

Component: Vulkan shader selection, artifact ownership, and compute synchronization.
Intent: preserved.
Acceptance evidence: build/test logs, matched comparisons and retained raw receipts below.
Boundary effects: no public API, shader, model, numerical oracle, workload, accepted package or release-policy change.

## Frozen starting point

`identities.json` binds the clean starting commit and native libraries. The initial
`baseline/` cohort compares that commit's final safeguarded compiler build with
Dawn in fresh processes. The previous compiler experiment's earlier candidate
comparison and separate final Doe-only cohort remain separate historical results;
none supplies a matched final-candidate Dawn observation for this experiment.

The installed Doppler Capsule, Node-qualified Qwen reranker, independent CPU
reference, tolerances, inputs, resident-model lifetime, and provider construction
are unchanged from the preceding admission. Policies and receipts bind them.
All inference uses ordinary WebGPU through Doppler's installed public Capsule
session; Doe's optional compute-program API is not the application treatment.
The local runner uses installed internal oracle and cleanup helpers outside the
measured operation. This is not a clean-install or wholly public-helper example.

## Immutable shader owner

Cached pipeline selection used to duplicate SPIR-V bytes for pending artifact
capture even though the device-local shared pipeline already owns those exact
immutable words. The pending observation now retains that pipeline. Replacement
acquires the new reference before releasing the old one; command boundaries and
teardown discard it. Explicit artifact capture still owns a separate byte snapshot
and releases the retained pipeline on both success and allocation failure.

`owner.patch` preserves the first candidate. `owner-verified.log` records the
ReleaseFast aggregate tests and isolated native build. The tests exercise repeated
selection with an allocator that rejects allocation, replacement, failed retain,
capture failures, independent capture bytes, program release, and final registry
cleanup. Earlier failed build invocations and the corrected fixture compilation
failure remain in their original logs.

`owner-compare/comparison.json` compares predecessor Doe, owner-only Doe, and
Dawn in a single interleaved fresh-process cohort. The owner correction removes
the targeted allocation/copy; it did not establish an application latency gain.
It must not be described as closing the measured deficit.

## Selecting the second candidate

`owner-profile/` reuses the existing timestamp diagnostic. It changes pass
boundaries, so its kernel costs suggest investigation targets and cannot establish
unprofiled application speed or intrinsic per-shader causes. Dawn timestamp
quantization can produce zero for short dispatches; that is not skipped work.
The retained costs motivated one synchronization experiment, not another compiler
transformation.

The candidate records buffer access by native backing allocation and a device
allocation epoch. It elides barriers only for independent accesses in the same
recording. Read-after-write, write-after-write, write-after-read, aliasing,
allocation changes, unknown resources, capacity exhaustion, indirect work and
recording boundaries retain conservative synchronization. No GPU dispatch or
readback is removed. Uniform-buffer visibility uses its distinct Vulkan access
bit, as defined by the [Vulkan access-mask contract](https://docs.vulkan.org/refpages/latest/refpages/source/VkAccessFlagBits.html).

## Disposition

`sync-compare/comparison.json` does not establish a repeatable application gain:
the small median/tail differences disagree with the slowest observations and
individual fresh-process runs. The allocation-access tracker is rejected and
removed from the final source. `sync.patch`, tests and receipts preserve the
attempt; no threshold was changed to accept it.

The final source keeps the immutable shader-owner correction and the separately
identified uniform-read visibility fix. `final.patch` and `final-compare/` bind
that exact result; the candidate there has no access tracker. The uniform fix is
supported by the Vulkan access contract and a physical storage-to-uniform
regression, not a reproduced predecessor numerical failure. It is a correctness
repair, not a claimed optimization.

`sync-verified.log` preserves a source-layout fingerprint failure during the
expanded test build; `sync-final-check.log` records the corrected complete run.
Module ownership decisions were re-examined for the changed responsibilities.
This targeted product repair grants no systematic file-review credit. The review
queue is regenerated without rewriting history.

## Measurement boundaries

Read each cohort's `comparison.json` and raw results independently. Each comparison
checks unchanged inputs, source oracle, Capsule, declared plan, recorded operations,
cleanup, and process-boundary GPU observations before reporting timings. Native
work equivalence beyond those observations remains a limitation, not release
qualification. An observer cannot exclude every short-lived GPU client. CPU exclusivity was not
established; an unrelated Doppler Node test runner was visible during the
synchronization cohort. No causal attribution is made from that observation.

The selected timing is the complete awaited rerank operation with models already
loaded. Initialization, oracle evaluation, artifact writing and cleanup are outside
that interval. These are local diagnostics for a named model and host, not compute
operation-speed claims, general Doe superiority, peak GPU residency or complete
search. No thresholds were relaxed and no failed oracle was replaced.

Final build acceptance is in `final-build.log`; schema and documentation checks
are retained alongside it. Hardware scope is this Linux AMD/Vulkan host. The
previous ordinary-provider render failure remains open, and the embedding
Capsule remains browser-qualified. These checks do not qualify Metal, D3D12,
browser/Fawn, complete document search, or release packaging.

## Reproduction

Use the pinned Zig toolchain and retained model/package prerequisites identified
by the policies and receipts. Build candidates into isolated output prefixes:

```sh
cd runtime/zig
zig build test dropin -Doptimize=ReleaseFast --prefix /absolute/isolated/prefix --summary all
```

Each cohort's `run.py` binds its exact library paths and refuses to reuse existing
result directories. `compare.mjs` verifies its retained results. Preserve existing
cohorts; use a new output directory and update runner/probe paths together for a
new experiment. Do not pool partial or interrupted runs. Profiling and builds must
finish before unprofiled comparisons begin.

## Retained evidence

`outcome.json` records the bounded experiments and disposition. `identities.json`
binds the base commit, candidate patches, source hashes, library hashes and tools.
Each patch is relative to that base; use an isolated checkout when reconstructing
an earlier candidate. The synchronization patch is a rejected experiment, not a
recommendation to apply it to the final source.

Raw result and timestamp-profile JSON is compressed without changing its content
in `raw-receipts.tar.gz`; `raw-receipts.json` binds every extracted member. Restore
those files before replaying `compare.mjs` on a fresh checkout:

```sh
tar -xzf bench/out/doppler-search/20260923-shader-owner/raw-receipts.tar.gz \
  -C bench/out/doppler-search/20260923-shader-owner
```

Libraries and model weights remain local prerequisites, identified by their hashes;
they are not copied into Git or published as an accepted release. The comparison
reports, policies, runner/probe sources, logs and compressed raw receipts are
retained. Failed command invocations are distinguished from passing build evidence.
