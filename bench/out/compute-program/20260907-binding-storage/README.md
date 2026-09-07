# Caller-owned Vulkan binding storage

The baseline is identified by `baseline.txt` and the qualified archives at
`../20260907-concurrent-qualified/summary.json`. `source.patch` contains the
candidate correction, including the Linux-only guard on the worker fixture.

## Profile and correction

The accepted baseline profile in `../20260907-addon-release-optimization/cpu-profile/`
identifies native dispatch recording as material preparation work. It is a
sampling profile, not an accepted latency comparison. `baseline-append.asm` and
`baseline-collect.asm` show full-capacity binding-array copies and intermediate
stack storage in `vulkan_collect_recorded_bind_group_state` and its caller.

Vulkan collection now writes active bindings into caller-owned storage and
returns only the small count, mask, and hash value. Direct, indirect, ordinary,
and prepared callers consume the same binding interpretation. Cache lookups
retain exact bind-group identity checks; cache entries retain their resource
owners. Successful publication supplies the initialized prefix and its count.
Unused capacity is not an interface and is not read. No validation, descriptor
identity, dispatch geometry, command ordering, synchronization, or resource
lease is removed. `final-append.asm`, `final-collect.asm`, and `final-merge.asm` show the
intermediate copies and stack storage removed from the generated code.
`tryMergeDispatchIntoLast` additionally borrows its read-only dispatch payload
instead of copying a full command before comparing it. Aliased input and repeat
overflow checks preserve the original merge behavior. The command and resource
storage lifetimes remain owned by the encoder.

## Acceptance and scope

`final-tests-debug.log`, `final-tests-release.log`, and `final-build-release.log` retain canonical
Zig acceptance, source layout, import fences, and public surface checks. The
new regression covers sparse bindings, empty sets, active-prefix publication,
cache misses and hits, output storage reuse, and balanced cache ownership.
Existing command, allocation-failure, lifetime, and cache identity tests remain
unchanged. The public configuration, C exports, schemas, receipts, and arithmetic
policy have no transition; existing blocking requirements in `docs/process.md`
continue to apply.

`../20260907-binding-storage-qualified/summary.json` binds the earlier binding-only
candidate described by `binding-only.patch`. Its prolonged checks, public C test,
and canonical model acceptance passed. Its application matrix at
`../20260907-binding-storage-applications/summary.json` was rejected by unrelated
GPU activity. None of these records is overwritten by the final candidate.

`../20260907-dispatch-copy-qualified/summary.json` binds the final archive pair
installed with scripts in fresh Node, Bun, and Electron main-process projects.
`final-validation/package-independent-verification.log` recomputes retained
artifact identities and compares extracted native/addon bytes with staged binaries
and host reports. `final-validation/public-symbol-verification.log` checks the
unchanged defined dynamic symbol set. Earlier unprefixed logs describe the
binding-only candidate. `baseline-merge.asm` was captured from that intermediate
library, whose merge implementation was unchanged from the original baseline.

## Measurements

`../20260907-dispatch-copy-applications/summary.json` passes artifact, numerical,
identity, and structural-work verification in `final-application-verification.log`.
The policy, shaders, oracle, incumbent binaries, completion behavior, and effective
readback remain unchanged. All comparison rows remain diagnostic. Deno/wgpu host
and polling costs make its large ratios suspicious; they are not leadership claims.

`compare-previous.py` alternates the previous and final qualified Doe packages
through the existing admitted application runner. `alternating/comparison.tsv`
uses shared percentile calculations, and `alternating/process-costs.tsv` retains
startup, preparation, first execution, cleanup, requested allocations, and process
RSS. Raw reports preserve every sample and oracle. The heat simulation's median
improves, image processing's median regresses, and tails are mixed. This does not
establish a consistently faster application experience or a transferable win.

`record-cost.c` isolates ordinary native C command recording and cleanup with
alternating bind groups. `measure-record-cost.py` runs the same executable against
the exact previous and final libraries, verifies loaded-library identity, discards
warmup, and alternates process order. `native-record-cost-validated/comparison.tsv` reports
lower recording median and p95 CPU and wall costs; p99 and cleanup tails do not
improve consistently. An untimed GPU execution checks every integer output after
the recording samples. GPU submission is outside the timed region, so this probe
cannot establish a useful-operation speed claim. It confirms the native preparation effect while application-level overhead
and variability remain unresolved. No benchmark acceptance threshold was weakened.

## Bounded resource cases

The final archive's regular host fixtures cover command ownership, rendering,
indirect work, reflection, timestamps, state updates, cancellation, and cleanup.
`node-concurrent-devices.stdout` in the final qualification covers independent
devices, worker recreation, and a surviving parent; it does not cover concurrent
mutation of one device or arbitrary termination with outstanding GPU work.

`run-final-prolonged.py` checks archive members before and after the existing
prolonged fixtures. The logs in `final-validation/` cover independently checked
ordinary and prepared runs, timestamp modes, stable sampled post-close DRM totals,
retained closed program objects, device/client cleanup, continuing CPU-checked
simulation frames, cancellation, and reopening. The samples are observations of
DRM allocation totals and worker RSS, not peak physical GPU residency.

The final public C fixtures in `final-validation/` link to the library extracted
from the final archive. They cover async pipeline leases and callback cleanup,
ordinary and fused compute, caller release before submission, buffer/image regions and
aspects, rejected descriptors, untouched pixels, and readback. Khronos validation
and synchronization checking must be active; reject validation errors and
synchronization hazards even if the process exits successfully.

Canonical model acceptance and its independent verifier are retained at
`../../external-projects/doppler/20260907-dispatch-copy-p0-qualified/result.json`.
The explicit source-built P0 control and frozen oracle remain unchanged. This
does not qualify the unmodified npm control in Electron.

Physical Metal and D3D12, shared-device mutation, arbitrary worker termination,
physical driver failure, and peak GPU residency remain unqualified. Publication,
signing, and adoption are separate from this bounded Linux implementation work.
A reduction in generated copying does not establish application leadership.
The application-advantage item in the live Linux checklist remains open.

Component: native Vulkan binding preparation
Intent: preserved
Acceptance evidence: canonical Zig tests, generated code, retained package and application records
Boundary effects: internal caller-owned output storage; public contracts preserved
