# Vulkan upload ownership and ABI continuation

Component: Zig Vulkan upload allocation and native declarations.
Intent: preserved.
Acceptance evidence: `fault-before.log`, `fault-after.log`, `abi.log`, `acceptance.log`, `schema.log`, `doc-links.log`, `review-check.log`.
Boundary effects: backend-private pool identity and allocation ownership; no application, public API, compiler, policy, receipt schema, or component authority changes.

## Inspected and changed

Complete file examinations cover `vk_structs.zig`, `vulkan_types.zig`, and
`vk_upload.zig`. The [file conclusions](file-reviews.json) retain findings and
continuation actions. Relevant callers, resource allocation and existing tests
were inspected without granting additional file or directory review credit.

Staged allocation previously scoped native cleanup inside source/destination
branches. Once the source branch succeeded, a later destination failure could
lose the source allocation, including one removed from a pool. A single native
acquisition helper now owns creation, memory allocation, binding, mapping and
rollback. Staged acquisition retains source ownership across destination
preparation. Direct and fast mapped uploads use that same helper, removing
competing cleanup sequences. Fast-buffer growth publishes only a fully prepared
replacement and preserves the previous buffer when preparation fails.

Hot and size-bucket pools now retain native usage flags. Selection requires every
requested bit; an incompatible entry remains owned by its pool while another
compatible entry can be selected. The pending upload carries the actual usage
mask back to the pool. Existing size classes, per-size capacity, path policy,
zero-fill behavior and failure taxonomy are preserved. Unknown usage cannot
satisfy a nonempty requested mask.

The ABI examination found no size, alignment, field-offset or field-size mismatch
against the installed Khronos C header. Structure declarations remain separate
from the canonical opaque-handle/type owner. This is host ABI evidence, not
cross-platform qualification or proof of every API semantic constraint.

## Executed evidence

`fault-before.log` reproduces the original leaked native acquisition and the lost
working buffer on resize failure. `fault-after.log` executes the same probe
against the correction: fresh acquisition, a source drawn from a populated pool,
and fast-buffer replacement. Injected failures cover native creation, allocation,
binding and mapping. The replacement fixture retries after each injected failure.
Counters check explicit native buffer/memory/mapping balance after teardown.

`fault.c` intercepts only the named Vulkan operations and delegates successful
operations to the real Radeon driver. Failure counters are armed after runtime
initialization. The probe performs no queue submissions during injection; it
does not establish recovery from submitted-work failures, driver hangs, or actual
memory exhaustion. The diagnostic library is never loaded during ordinary
acceptance or application timing. `build-options.zig` freezes the generated
options used by the standalone probe, not a new production configuration owner.

`acceptance.log` records the Radeon-only aggregate test suite and isolated
ReleaseFast drop-in build. New persistent regressions cover incompatible hot
entries, compatible entries behind an incompatible size-bucket entry, usage
supersets, reuse without calls to the runtime allocator, actual staged copy and exact readback.
Logs own totals and skips. The compiler/header/driver/library and source hashes
are in `identities.json`; `checksums.json` binds retained evidence.

The first ABI invocation used the repository root instead of `runtime/zig` and
failed before compiling its temporary root. The corrected invocation produced
`abi.log`. An intermediate review check correctly reported a stale queue after
source edits; the regenerated queue and predecessor-based history check are
retained separately. Temporary probe roots are removed after execution.

## Reproduction

From the repository root, compile the diagnostic interposer and copy the probe
roots into the Zig module root:

```sh
cc -shared -fPIC -Wall -Wextra -Werror bench/out/maintenance/20260923-vulkan-upload-audit/fault.c -ldl -o bench/out/maintenance/20260923-vulkan-upload-audit/libaudit_fault.so
cp bench/out/maintenance/20260923-vulkan-upload-audit/fault-probe.zig runtime/zig/.audit_upload_probe.zig
cp bench/out/maintenance/20260923-vulkan-upload-audit/abi-probe.zig runtime/zig/.audit_abi_probe.zig
```

From `runtime/zig`, replace the absolute evidence directory below with the local
checkout path. The ICD and header paths are Linux host prerequisites.

```sh
zig test .audit_abi_probe.zig -lc -I/usr/include
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json zig test -OReleaseFast -lc -L/absolute/evidence/directory -rpath /absolute/evidence/directory -laudit_fault -lvulkan --dep build_options -Mroot=.audit_upload_probe.zig -Mbuild_options=/absolute/evidence/directory/build-options.zig --test-filter 'upload fault'
rm .audit_abi_probe.zig .audit_upload_probe.zig
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json zig build test dropin -Doptimize=ReleaseFast --prefix /absolute/isolated/prefix --summary all
```

From the repository root, run the canonical schema gate, documentation-link test,
and review generator/checker. Pass the starting commit from `identities.json` as
`--base-ref` when checking append-only history, including after commit. Accepted
libraries are not overwritten. Local diagnostic JSON files are audit projections,
not new runtime or release receipt contracts.

## Remaining work and limits

Upload submission failure still needs an explicit recording/submitted/retired
state that supports retry without ending an already executable command buffer or
resetting potentially submitted work. Aggregate pool retention, complete copy
range admission, and mixed upload/replay completion ownership remain open in the
ledger. The next never-examined file is `src/backend/webgpu_backend.zig`. Source
layout metadata preserves existing ownership; passing tests grant no higher-level
review credit and do not refresh stale reviews.

No Qwen/Dawn timing cohort, application oracle, GPU residency study, shader-cost
analysis, second workload, native device-loss injection, windowed presentation,
Metal, D3D12, or release qualification was executed. The earlier application
latency deficit remains unresolved. Allocation cleanup and safer pool reuse do
not establish a runtime speed advantage.
