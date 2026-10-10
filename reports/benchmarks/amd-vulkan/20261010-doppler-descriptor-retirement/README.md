# Doppler descriptor-retirement experiment

The descriptor-retirement candidate is **rejected**. [Disposition](disposition.json)
records failed baseline first-token stability and failed material resident
complete-generation improvement. [Baseline](baseline-summary.json) and
[candidate](candidate-summary.json) retain the actual medians, tails and controls.
The candidate's observed complete-generation median is worse. No speed advantage
is established; the runtime patch is archived and absent from production.

## Mechanism and acceptance

The repaired mapping baseline is source commit `1e298f267`; provider manifests
retain the earlier build ancestry metadata, while [the manifest](manifest.json)
and [candidate patch](candidate.patch.gz) identify this experiment's source.
[Baseline providers](providers.json) and [candidate providers](candidate-providers.json)
bind the actual native libraries and the identical repaired host snapshot.
Historical host archives remain custody inputs, not the executed host identity.

The [frozen candidate policy](retirement-candidate.json) selects complete-generation
latency against repaired Doe, with Dawn as an unchanged control. This is an
unchanged-application comparison: model, shaders, numerical requirements, public
behavior, independent CPU reference and workload remain fixed. Qualification,
balanced process order, resident controls, tails and memory limits precede
promotion. Incremental admission and the separate incumbent ambition are distinct.

The candidate replaces a full descriptor-cache scan on every buffer destruction
with one sweep before subsequent descriptor preparation. Missing live allocations
and changed generations invalidate descriptors. Native completion and physical
buffer release remain unchanged; no allocation pool or buffer reuse policy is
added. The [Vulkan descriptor rules](https://docs.vulkan.org/spec/latest/chapters/descriptorsets.html)
allow descriptor contents to become undefined after resource destruction, but
require populated contents before use. The patch checks that boundary and keeps
metadata owned until sweeping or teardown.

[API attribution](attribution.json) includes destruction, creation and overlapping
completion. These intervals do not identify pure GPU time or add into a latency
budget. `source/observe-destruction-initial.mjs` is the observer used for the initial
profile and native-cost probe; `source/observe-phases.mjs` adds the failure capture
used for the cleanup profile. Exploratory Vulkan interposition is retained under
`diagnostics/`: its first resolver failed, and its corrected totals are process-wide,
uninstrumented-control-free observations. They are not performance evidence.

## Executed disposition

Raw baseline and candidate process receipts, stdout/stderr, qualifications and
source snapshots are hash-bound by the manifest. Candidate core/full checks,
physical buffer replacement, mapping, rendering and command ownership pass;
see `candidate-checks/`. The physical replacement test executes rather than skips.
The Vulkan validation layer was not available on this host.

The first candidate cohort invocation accidentally used baseline qualification
receipts. The manifest join rejected it before provider loading or measurement.
Its failed process list and logs remain in `diagnostics/`. The corrected invocation
uses the candidate's qualification directory and retains its complete planned
cohort. There was no timing-selected rerun or threshold change. Baseline stability
failure was recorded before candidate timing. Unrelated ONNX transfer was not run
after failed admission; regression success cannot rescue this candidate.

Both timing cohorts predate the separate [queue-completion repair](../../../maintenance/20261010-queue-completion/README.md).
Their unload warnings remain in evidence. Do not use that repair to reinterpret
these results. Process CPU consumption and fully settled application cleanup were
not qualified by this experiment.

## Reproduction and next boundary

Use the existing generation runbook with separate baseline/candidate directories
and matching qualifications. Apply the archived patch to the recorded source
commit to reconstruct the candidate. Native binaries and model custody remain
local; this is not an isolated installable release.

```bash
python3 bench/external-projects/doppler-generation/compare.py \
  --baseline reports/benchmarks/amd-vulkan/20261010-doppler-descriptor-retirement/baseline-summary.json \
  --candidate reports/benchmarks/amd-vulkan/20261010-doppler-descriptor-retirement/candidate-summary.json \
  --contract bench/external-projects/doppler-generation/contract.json \
  --candidate-policy bench/external-projects/doppler-generation/retirement-candidate.json \
  --out /tmp/doe-retirement-decision.json
python3 bench/external-projects/doppler-generation/validate.py \
  --report reports/benchmarks/amd-vulkan/20261010-doppler-descriptor-retirement \
  --schema config/doppler-generation.schema.json
```

The next selection needs evidence separating native allocation/driver work from
descriptor scanning. API destruction cost alone did not select a successful
optimization. No successor batch is selected, and the earlier buffer-reuse
rejection remains closed.

Component: Vulkan descriptor ownership and generation experiment tooling.
Intent: preserved. Acceptance evidence: manifest, disposition and candidate checks.
Boundary effects: rejected runtime patch removed; optional admission policy and
failure-preserving diagnostic observation remain. No model or shader change.
