# Memory policy separation and completed allocation reuse

Component: Zig Vulkan allocation, resource lifetime, and native buffer mapping.
Intent: preserved.
Acceptance evidence: `qwen/comparison.json`, `umap/comparison.json`, `confirmation/comparison.json`, `umap-confirmation/comparison.json`, `tests.log`, and `native-regression/test-preload.log`.
Boundary effects: versioned bounded allocation retention; write mapping now waits for Vulkan completion. Application, shaders, precision, synchronization barriers, and public API fields are unchanged.

## Policy disposition

The candidate `77fdc716e` remains preserved with its original library hash in
`variants.json`. `selection-only.patch` and `avoidance-only.patch` describe
source-only ablations built outside accepted binary locations. No ablation
switch entered production. The original library and the preserved candidate
were reused unchanged.

`qwen/comparison.json` records the factorial cohort, including separate
same-binary controls. Neither selection alone nor promotion avoidance alone
improved the original Qwen median. Their combination improved it. The supported
mechanism is selecting a compatible allocation already on device-local memory
and retaining it on binding; either half alone leaves redundant promotion or
nonlocal allocation. All observations remain local to the frozen AMD/Vulkan
installation. Process medians, especially Dawn and combined controls, vary;
this cohort does not establish an exact universal effect size.

`umap/comparison.json` and `umap/process-pairs.json` retain independent
interleaved invocations and unchanged controls. The earlier slowdown does not
repeat consistently across process pairs, and the main aggregate mean and tail
move differently from the median. A smaller regression or equivalence remains
unresolved. No UMAP speed advantage or broad policy acceptance is asserted.
Neither workload name participates in the runtime policy.

## One additional candidate

Current native observations in `profile/allocation-analysis.json` locate
remaining ordinary rerank allocations in temporary activation buffers. The
allocation histogram and copy-purpose table are kept beside the raw interposer
log. The surviving copies carry chunk state, final-token slices, uniforms and
readback; the observed sequence does not establish remaining promotion copies.
Fence waits include earlier compute and cannot be attributed to copy execution
or added to GPU intervals.

The additional candidate reuses completed, mapped, host-visible, coherent,
device-local allocations through the existing Vulkan pool representation. It
matches exact logical size and native usage, retains actual allocation properties,
resets allocation generation and initializes returned bytes, invalidates old
descriptor associations, and bounds both bytes and entries. Pending work excludes
retention. Cache metadata allocation failure follows normal native cleanup.
Unknown locality remains ineligible for retention and preserves promotion.
This is a fixed schema-backed retention bound, not a performance ablation knob.

The prediction was fewer native allocations and lower host allocation cost,
without changing copied bytes or the application's GPU dispatch sequence.
`reuse-profile/allocation-analysis.json` and `current-sequence.json` test that
prediction. These are instrumented diagnostics and are separate from clean
application confirmation. Original coalesced passes contain several shader
families: their intervals cannot produce additive per-family excess attribution.
No new shader or hazard-tracking optimization was attempted.

## Lifecycle evidence and limits

A focused native regression reproduced a separate correctness defect: a writable
mapping could be returned while earlier GPU reads remained pending. The candidate
waits on Vulkan completion before granting either read or write mapping. The
same fixture fails against the preserved library and passes against the candidate;
see `native-lifecycle-before.log` and `native-lifecycle-after.log`. Retain this
correctness repair independently of the performance disposition.

`native-regression/test-preload.log` covers native create/allocate/bind/map failure,
retained contents and identity, unknown-locality promotion, cache reuse and zeroing,
allocator rejection, byte and per-size capacity, and final native allocation balance.
The initial linked launch did not intercept Vulkan and is invalid fault evidence;
its failures remain in `test-retry.log`. Explicit preloading corrected the launch.
The aggregate suite and native recorded execution fixture cover dispatch, copying,
caller release, initialization and readback. Vulkan synchronization validation was
unavailable on this host. Existing teardown after failed queue flush still logs
and continues destruction; device-loss/unknown-completion retirement is not
qualified by the successful-completion and allocation-failure checks here.

## Confirmation and evidence boundaries

`confirmation/policy.json` freezes the clean interleaving before execution.
It compares the preserved combined build, reuse candidate and Dawn with native
interposition, timestamp/CPU profilers and compiler replacement disabled.
`confirmation/comparison.json` preserves pooled percentiles, every process median,
query CPU, startup, and RSS observations. `confirmation/process-resources-and-variation.json`
retains sample order and the alternative central-pair median. Dawn alternates
between two latency bands; its pooled nearest-rank median is sensitive to that
convention, while the reuse-versus-preserved sign is consistent. RSS is whole-process resident memory
after a query, not device residency. GNU time records whole-process CPU and peak
RSS separately; neither is resident-query-only CPU. UMAP retains the existing
harness process-tree RSS observer and exact provider replay; its boundaries and
warmup are unchanged. Controls are separate from treatment aggregates.

The Doppler archive, installed files, Capsule, reference input, tolerance and
oracle identities are inherited from the preserved experiment and checked in
`preflight.json`; `variants.json` adds the isolated library identities. The
archive does not establish an exact Doppler Git commit. `current-sequence.json`
records matching observed original dispatch sequences. It does not turn model
counters into native dispatch validation or promote a release claim.

The final outcome and remaining measured deficit are in `outcome.json`.
Published receipts are local diagnostics, not release qualification. Historical
cohorts stay separate. Metal expansion, broader audit/refactoring, prepared
execution, another measurement framework, compiler scalarization and the rejected
synchronization tracker were skipped. The batch stops after this policy
disposition and the additional candidate's measured verdict.
