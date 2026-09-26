# AMD Vulkan memory policy investigation

`77fdc716e` remains the preserved Qwen-improved candidate. The additional tested
source is `b21adb3d0`; [changes.patch](changes.patch) records its runtime and
policy delta. This report retains local diagnostics, not release qualification.

Component: Zig Vulkan allocation, lifetime, and native mapping.
Intent: preserved.
Acceptance evidence: linked comparisons, raw receipts, and executed test logs below.
Boundary effects: fixed versioned allocation-retention bound; writable mapping waits for GPU completion. Application and shader contracts are preserved.

## Disposition

Retain allocation selection and locality-proven promotion avoidance together.
Neither isolated half improved the original Qwen result. Retain bounded reuse of
completed allocations as a further local Qwen improvement. The unchanged UMAP
fixture passed correctness and exact replay, but establishes neither a speed
benefit nor equivalence. Its earlier slowdown did not repeat consistently;
a smaller regression remains unresolved. Dawn parity is still open.

[Outcome and effect sizes](outcome.json) contain the current cohort statistics,
remaining deficit, candidate verdict, and limitations. Every reuse process
median was below every preserved-build process median in confirmation. Dawn's
alternating latency bands make its median sensitive to the convention:
[process variation](qwen-process-variation.json) retains sample order, shared
nearest-rank statistics, and the conventional central-pair median. No samples
were removed. Historical comparisons are separate from this cohort.

The [investigation record](investigation.md) explains attribution and scope.
The writable-mapping correctness repair passes its before/after regression.
Existing destruction after a failed queue flush remains unqualified; this batch
does not establish complete failure-path lifecycle safety. Synchronization
validation was unavailable on this host.

## Reviewable evidence

- [Factorial Qwen comparison](factorial-qwen.json), [factorial UMAP comparison](factorial-umap.json), and [UMAP process pairs and unchanged controls](umap-process-pairs.json).
- [Clean Qwen confirmation](confirmation-qwen.json), [UMAP confirmation](confirmation-umap.json), and [UMAP reuse process pairs](umap-reuse-process-pairs.json).
- [Allocation before](allocation-before.json), [allocation after](allocation-after.json), and [UMAP mechanism separation](umap-allocation-mechanisms.json).
- [Original dispatch sequences](current-sequence.json), [native memory before](native-memory-before.json), and [native memory after](native-memory-after.json). Native API allocation bytes are not residency; query RSS and whole-process peak RSS have separate scopes.
- [Aggregate tests](tests.log), [schema gate](schema.log), [physical fault and lifecycle tests](native-fault-and-lifecycle.log), [write mapping before](native-lifecycle-before.log), and [write mapping after](native-lifecycle-after.log).
- [Library/source identities](variants.json), [unchanged input identities](prior/input-identities.json), [compiler/driver identities](prior/libraries.json), and [post-execution verification](postflight.json).
- [Selection-only patch](selection-only.patch), [avoidance-only patch](avoidance-only.patch), and [inspected/changed/executed/skipped record](work-record.json).
- [Prior investigation](prior/README.md), [historical shader-family costs](prior/shader-costs.csv), and [prior raw receipts](prior/raw-receipts.tar.gz). Historical split-pass timings do not account for the current application gap.
- [Current raw receipts](raw-receipts.tar.gz) and [publication checksums](checksums.json).

The current archive preserves repository-relative `bench/out/` paths. It includes
raw process results, oracle decisions, exact replay, GPU activity observations,
policies, probe sources, native call logs, profiles, build metadata, and failed
launch logs. The prior archive uses paths relative to its original experiment
directory. Working-machine absolute paths remain provenance, not download links.
The installed model/archive and runnable shared libraries are not redistributed;
their immutable identities and build/source inputs are retained. Neither archive
promotes a claim-index row or an accepted package binary.

This bounded batch stops after the policy disposition and allocation-reuse
candidate. Broader refactoring, additional optimization, Metal expansion,
prepared execution and the rejected synchronization tracker were skipped.
