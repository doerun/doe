# AMD Vulkan shutdown and compute reuse investigation

The retained baseline runtime is `b21adb3d0`; `9c1f45e13` published its preceding
evidence. Those identities are not interchangeable. The combined memory policy,
completed allocation reuse, and writable-mapping repair remain the starting point.
The retained correction is committed as `0f817f746`; its binary matches the
measured teardown-only arm. This report describes local diagnostics, not release
qualification.

Component: Zig Vulkan completion, destruction, and compute allocation retention.
Intent: preserved.
Acceptance evidence: linked executed tests, frozen policy, raw receipts, and comparisons.
Boundary effects: failed completion retains synchronous ownership. The larger compute allowance is rejected; existing allocation and upload-pool policies remain. Application and shader contracts are preserved.

## Disposition and comparison rule

Retain the failed-flush teardown repair. Reject the larger compute-pool allowance
for production: it improves Qwen but does not pass the frozen UMAP slowdown bound.
The UMAP result is inconclusive against that bound, not proof of a consistent
large regression or equivalence; unchanged controls also vary substantially.
No follow-up run or changed threshold rescues the candidate. Preserve its isolated
library identity, source patch, and measurements for review. The final production
build is byte-identical to the measured teardown-only arm.

Dawn parity remains unestablished. The near-equal arithmetic means do not override
the primary confidence requirement or the lower Dawn nearest-rank median. The
candidate's better tail remains a separate observation. The current cohort's
arithmetic excess and fraction removed are artifact-owned, not combined with
historical medians or Doe-only cohorts.

[Outcome](outcome.json) owns the final retention decision, confidence bounds,
remaining gap, and limitations. The [frozen experiment policy](experiment-policy.json)
precedes confirmation. Its primary estimate uses paired process means, with a
predeclared improvement threshold and separate UMAP slowdown bound. Nearest-rank
percentiles and conventional central-pair medians are retained separately.
Neither percentile convention is substituted after seeing the observations.

[Qwen process variation](qwen-process-variation.json) and [every Qwen sample](qwen-samples.csv)
retain invocation order and latency bands. Startup remains separate from resident
reranking. UMAP retains its original invocation boundary, warmup, exact replay,
and symmetric process-tree RSS observer. Its bound does not establish equivalence.

## Lifetime correction

Shutdown no longer discards a failed flush and destroys referenced resources.
A failed wait closes execution and reuse, retains the caller's complete ownership
scope, and resolves device completion before teardown proceeds. Nonterminal idle
errors keep that scope alive. Device-idle success or confirmed device loss permits
retirement, while device loss remains a distinct failure cause. Repeated completed
shutdown releases nothing twice. Native direct destruction and pool admission
share the ownership boundary.

The fault fixture first completes real driver work, then injects unresolved
completion observations. It checks retained allocations and mappings before
allowing terminal completion or device loss. This tests lifetime handling without
claiming a physical hardware reset. The unchanged source's failing results remain
alongside the repaired results. A cleanup re-entry failure found during development
is retained in the executed logs; terminal retirement now precedes child cleanup.

[Vulkan buffer destruction](https://docs.vulkan.org/refpages/latest/refpages/source/vkDestroyBuffer.html)
requires completion of submitted references. The
[device-loss rules](https://docs.vulkan.org/spec/latest/chapters/devsandqueues.html#devsandqueues-lost-device)
provide a separate lifetime outcome; they do not require eventual successful
workload execution. If neither completion nor device loss becomes known, this
synchronous destructor can remain blocked. No background owner or unprotected
borrowed pointer is introduced.

## Allocation mechanism

The temporary counter build records allocation and release occupancy, pending-work
rejection, incompatible properties, per-size capacity, and global capacity.
[Before](allocation-before.json), [after](allocation-after.json), and [allocation table](allocation-results.csv) retain the
counts and native call observations. [Prediction](candidate-prediction.json) was
written before candidate confirmation. The observed sequence motivates a larger
compute-specific per-size allowance within the existing byte bound; upload pools
retain their previous policy. No waits were added to manufacture reuse hits.

The regression checks capacity, fresh generations, zero initialization, and
unchanged upload allowance. Existing native dispatch/copy/readback tests retain
binding, caller-release, mapped-write, and failed-construction coverage. Diagnostic
source counters and the native interposer are absent from all clean confirmation
binaries and processes. Native allocation bytes, retained pool bytes, query RSS,
and whole-process peak RSS have distinct scopes and are not GPU residency.

## Evidence and reproduction

- [Qwen confirmation](confirmation-qwen.json), [UMAP confirmation](confirmation-umap.json), and [outcome with paired uncertainty](outcome.json).
- [Retained aggregate suite](tests.log), [candidate aggregate suite](tests-candidate.log), [schema gate](schema.log), [documentation links](doc-links.log), [native execution regression](native-recorded-compute.log), and [retained fault/capacity results](lifetime-after.log), and [candidate fault/capacity results](lifetime-candidate-after.log).
- [Unchanged-source fault failures](lifetime-before.log), [teardown-only diff](teardown.patch), and [combined experimental diff](candidate.patch).
- [Retained production identity](retained-production.json), [source and library identities](variants.json), [preflight](preflight.json), [postflight](postflight.json), and [work record](work-record.json).
- [Raw receipts and reproducer sources](raw-receipts.tar.gz), [publication checksums](checksums.json), and [preceding report](../20260926-memory-policy/README.md).

The archive preserves repository-relative paths for policies, runners, exact
replay, raw samples, source counters, physical failure injection, failed commands,
and build metadata. Working-machine absolute paths remain provenance. Model bytes
and shared libraries are identified by hash rather than redistributed. No accepted
binary or claim-index row is overwritten. No new measurement framework, compiler
transformation, synchronization tracker, Metal path, or broad refactor is included.
