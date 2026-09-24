# Vulkan submission and shader-source audit

Component: Zig Vulkan backend.
Intent: preserved.
Acceptance evidence: `build-test-final.log`, `physical-deferred.log`, `physical-timestamps.log`, `schema-gate.log`, `doc-links.log`, `review-check.log`.
Boundary effects: existing Vulkan submission owners and callers; no application, package, compiler, public schema, or backend-policy change.

## Changes and examination

The [file conclusions](file-reviews.json) record complete file examinations,
resolved defects, unresolved findings, and concrete continuation actions. The
append-only Zig ledger distinguishes those examinations from verified coverage.
Supporting edits in runtime assembly, device creation, upload, render and repeated
dispatch do not grant those files or their directories review credit. Ownership
stays with the existing components; no broad directory refactor was performed.

Deferred fence submission now rolls back its latest reservation on explicit
host/device allocation rejection. Timeline preparation no longer advances the
wait target before submission. Only results that can represent submitted work
publish that target; device loss and unknown errors remain conservative. Timeline
creation errors propagate rather than selecting a fallback after failed native
creation. Checked timeline-value exhaustion fails explicitly.

This distinction follows the native submission contract:
[Vulkan queue submission](https://docs.vulkan.org/refpages/latest/refpages/source/vkQueueSubmit.html)
leaves referenced resources and synchronization state unaffected on allocation
rejection, whereas [device loss](https://docs.vulkan.org/spec/latest/chapters/devsandqueues.html)
cannot authorize treating submitted resources as unused. The tests exercise the
owner's result transitions; they do not inject real driver allocation failures
or establish complete application recovery from device loss.

Shader sibling lookup changes only the filename extension, preventing a dotted
parent directory from selecting an unrelated module. File loading preserves
I/O/allocation errors; translation preserves allocator failure. Existing cache
ownership and publication rollback remain intact. Elapsed GPU ticks wrap at the
queue's valid-bit width; invalid calibration and unrepresentable conversion fail
explicitly. Dependent repeated-dispatch barriers include uniform reads. Capability
queries for handles lacking a native surface now fail instead of succeeding
without a native observation.

## Executed checks

The isolated ReleaseFast library and aggregate tests use the recorded Zig
compiler. The aggregate suite includes shader allocation-failure sweeps, dotted
path selection, fence/timeline result transitions and retry, invalid/masked/wrapped
timing arithmetic, missing-surface admission, cached shader selection and native
output regressions. Raw build results own the totals.

The focused deferred and timestamp runs explicitly select the Radeon ICD. The
former checks fence and timeline selection, outstanding obligations, drain and
later submission with exact integer output. The latter checks required native
timestamps and exact results for single and dependent repeated dispatches. These
physical success tests complement the pure rejected-submission tests. They do not
substitute for native failure injection or window-system presentation tests.

`build-test.log` retains the initial successful suite before additional physical
coverage. `build-test-test-import-failure.log` and
`build-test-test-switch-failure.log` preserve compile failures in the new test
setup; the final run uses the canonical policy type and exhaustive switch.
`identities.json` binds production/test inputs, starting commit, compiler, isolated
library and driver files. `changes.patch` contains the code and guidance diff
before ledger publication. `checksums.json` binds the retained evidence. Build
outputs remain at the isolated local prefix and are not accepted release binaries.

Reproduce from `runtime/zig`:

```sh
zig build test dropin -Doptimize=ReleaseFast --prefix /absolute/isolated/prefix --summary all
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json zig build test -Doptimize=ReleaseFast -Dtest-filter='Vulkan deferred fence and timeline submissions' --summary all
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json zig build test -Doptimize=ReleaseFast -Dtest-filter='Vulkan calibrated timestamps' --summary all
```

From the repository root, execute the schema gate, documentation-link test and
review generator/checker. Review history checks use the recorded starting commit
as `--base-ref`, including after commit. The failed attempt to locate the schema
gate at `bench/schema_gate.py` executed no gate; the canonical
`bench/gates/schema_gate.py` command produced the retained log.

## Migration and remaining work

No serialized field or version changed. Existing deferred synchronization and
query policies retain authority. Callers now receive file and native creation
errors that were previously swallowed; host elapsed-query conversion takes the
queue's explicit valid-bit width. Source-layout metadata keeps the same module
owners. The existing blocking correctness/schema/trace/verification gates retain
their roles; local diagnostics do not qualify a release.

Unknown-completion teardown, command resource retention, sampler validation and
anisotropy, exact presentation semantics, native error taxonomy, internal shader
cache identity, and texture-command footprint admission remain open in the file
conclusions. Address their named mechanisms before verifying those scopes. The
next never-examined file is `src/backend/vulkan/vk_structs.zig`; `vk_upload.zig`
and `vulkan_types.zig` also remain unexamined in this continuation. Previously
stale reviews are not refreshed merely because current tests pass.

No current Dawn comparison, Qwen oracle rerun, whole-application allocation count,
CPU comparison, memory-residency study, shader-family ISA attribution, second
workload, Metal, D3D12, windowed presentation, or release qualification was run
for this audit. The earlier Qwen cohort remains separately retained at
[HEAD confirmation](../../doppler-search/20260923-head-confirmation/README.md).
Its application deficit remains unresolved. This correctness/refactor batch does
not establish an application speedup, buyer dependence, or acquisition value.
