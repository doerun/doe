# Vulkan submission and shader-owner metadata

This is a scoped implementation and diagnostic checkpoint. The baseline is
`3bcadf420`; the candidate is the accompanying source change. Exact production
source, library, workload, provider and hardware identities are retained in
[submission-evidence.json](submission-evidence.json). The accepted adapter
selection reuse remains intact.

Executable custody includes the original measured library hash and local
checkpoint archives. A post-measurement ELF dumping command rewrote file
layout; the exact original hash was restored from the unchanged rebuild and
preserved debug-line section. The artifact records this repair and the
rebuild's generated-cache path difference. Runtime sections are identical;
comparison evidence stays bound to the original measured executable.

## Attribution and correction

The unchanged UMAP workload still prepares and submits its original compute
and copy commands, requests completion, and maps the final output. Existing
addon submission breakdowns and temporary native boundary measurements separate
API validation, pipeline and descriptor preparation, recording, finalization,
synchronization preparation, driver submission, and completion waits. Their
raw observations and first-submission distinctions are retained in
[phase-observations.json](phase-observations.json). Nested measurements are not
disjoint whole-process phases. Unavailable exported counters are not evidence
of zero work.

Driver submission dominates the measured native submission phases. Within
pipeline preparation, repeated subgroup-policy inspection was the largest
demonstrated avoidable cost. The existing shared pipeline now retains immutable
local-size and workgroup-storage facts with its owned SPIR-V words. Active,
hot and spilled states lend those facts only after exact word comparison.
Effective device policy and environment overrides are evaluated on each
selection; exact words, entry point, layout and subgroup requirement still
authorize pipeline reuse. The lookup adds no heap allocation or global cache.
Existing module-inspection semantics are preserved.

The instrumented before/after observations show lower repeated policy-inspection
cost. Separate diagnostic observations retain actual metadata hits and misses,
command-buffer growth and API validation. Complete allocator accounting remains
unmeasured. Temporary timing and logging changes are retained as patches and
are absent from the production source. Queue ordering, explicit waits, pending
resource ownership, numerical behavior and generated shader code are preserved.

## Application disposition

The [evaluation policy](evaluation-policy.json) was recorded before comparisons.
Its limits and cohort order are preserved in the versioned
[config](../../../../config/vulkan-submission-evaluation.json). Every alternating
baseline/candidate cohort is retained, including inconsistent timing signs.
The frozen UMAP application, shaders, inputs and oracle were unchanged.
Comparisons used fresh processes with populated shared shader and driver disk
caches; empty disk-cache behavior was not requalified.

The candidate passed physical eligibility, the frozen output oracle and exact
within-provider replay. Candidate and baseline Doe outputs match. Dawn and Doe
outputs differ while satisfying the declared cluster oracle; this is not
bitwise cross-provider equivalence. No declared metric has a repeated regression
under the recorded diagnostic rule. Selected-operation and complete-process
medians changed direction between matched pairs. **A repeatable application gain,
material Dawn advantage, and runtime ownership credit remain unestablished.**

Retain the correction for explicit shader ownership and demonstrated scoped
inspection savings. Application performance remains a separate outcome. The
prior frozen UMAP ownership decision is unchanged.

## Correctness and remaining work

The [combined runtime and WGSL log](test-candidate-final.log) retains the passing
source gates and suites. Physical Vulkan regressions cover policy changes,
shader and descriptor collisions, cache spill, failed allocation, caller
release, dependent submissions and delayed completion. The new physical
metadata regression changes workgroup size and storage under a deliberately
shared shader hash. The initial [gate failure](test-candidate.log) is preserved;
its source-layout decision hashes were updated with the existing owners.
The [checkpoint gate index](checkpoint-gates.json) binds schema, architecture
inventory, documentation links, public claim checks and review-log validation.

Public package [shader and render checks](shader-semantics-candidate.log),
[entry-point and override checks](preparation-physical-candidate.json),
[contract checks](package-contracts.log) and [smoke](package-smoke.log) passed.
The [Doppler transfer result](doppler-result.json) preserves exact output against
the incumbent and independent sampled arithmetic for the existing edge and QKV
kernel fixtures. It does not qualify complete Doppler inference or reopen its
retired performance family. Registry publication, installed-package release,
browser replacement, physical device loss and complete conformance remain
separate obligations.

The next bounded investigation profiles generated Vulkan execution and selects
one shader family by recoverable application cost. Compiler cost and generated
program speed must remain separate. Vulkan stays active; Metal and D3D12 do not
inherit this evidence.

Component: `doe.runtime-zig`, `doe.config`, `doe.docs`, `doe.reports`.
Intent: preserved. Acceptance evidence: linked raw receipts, logs and source
hashes. Boundary effects: backend-private immutable pipeline metadata and
repository-only evaluation configuration; no public ABI or serialized shader
cache change.
