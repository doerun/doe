# Vulkan binding-cache attribution

## Disposition

Close this UMAP binding-optimization line without a production candidate. The
lower-level descriptor cache already reuses unchanged binding state across public
submissions. Initial descriptor preparation is confined to newly encountered
program/resource identities; later epochs do not repeatedly allocate descriptor
pools or update native descriptors. UMAP remains a regression workload.

[Attribution](umap-attribution.json) retains active hits, retained-cache hits,
initial misses, resource identity snapshots, scoped allocation requests, native
descriptor writes and existing synchronization/driver preparation timings. The
observed descriptor and identity intervals are small relative to the
[uninstrumented complete-operation cohorts](../20261004-operation-timeline/application-comparison.json).
This does not identify a substantial recoverable application cost. It is not a
mathematical speedup bound or a new performance comparison.

## Ownership traced

`PreparedVulkanDispatchState` borrows recorded-command fields only during public
submission. Its local lifetime does not prevent reuse by the backend:

- `vulkan_compute_native.prepare_pipeline_bindings()` selects the stable program
  and captured binding identity.
- `vk_pipeline_cache` retains compute state and owned descriptor identities
  across program switches.
- `vk_descriptors.prepare()` resolves exact resource identity before using active
  or cached descriptors. Allocation generation, native handle, extent and layout
  checks remain in place.
- Recording state and pending synchronization remain separate from reusable
  descriptor ownership.

No command-owned pointer is retained beyond submission, no validation is skipped,
and no additional cache is introduced. All temporary instrumentation is removed.
The addon and accepted Vulkan library remain unchanged; the `-O3` rejection,
identifier admission repair and earlier hoisting/subgroup dispositions stay closed.

## Changed-binding controls

[Physical controls](binding-controls.json) compare literal expected outputs on the
instrumented runtime, accepted uninstrumented Doe runtime and pinned Dawn.

| Input change | Observed descriptor behavior |
| --- | --- |
| Same program and resources across submissions | Active reuse |
| New bind-group object with equivalent resources | Active reuse |
| Changed buffer contents | Active reuse with fresh output |
| Different resource, binding range or program layout | Initial preparation |
| Return to retained resource, range or layout | Cached reuse |

These are buffer-binding characterization cases, not full texture/sampler,
collision, allocation-failure, recovery or WebGPU conformance qualification.
Existing UMAP semantic checks and exact repeated output remain intact.

## Measurement limits and reproduction

The retained diagnostic patch counts branches and uses the existing recorded
submission timing owner. Timers and per-submission reporting perturb execution;
instrumented application latency cannot receive performance credit. Identity
snapshot time is nested inside resolution, descriptor preparation and whole
dispatch preparation. Those values must not be summed.

Allocation observations cover the temporary collections and retained identity
requests in the descriptor miss branch. They are not complete host/driver
allocation accounting. Complete allocation tracking and GPU/host clock calibration
are unnecessary to establish the observed cache behavior, and are not additional
prerequisites for closing this line.

```bash
# Apply the decompressed binding-instrumentation.patch to the recorded source.
cd runtime/zig
zig build dropin -Doptimize=ReleaseFast --prefix /path/to/diagnostic-runtime
```

Run the pinned UMAP Vitest config with `DOE_WEBGPU_LIB` selecting that library
and the provider/input environment recorded in [evidence.json](evidence.json).
The compressed binding control uses the ordinary public package API and accepts
`DOE_BINDING_PROVIDER` for the pinned Dawn control. Restore the patch before
ordinary execution. Native libraries remain in local custody with hashes; no
large provider binaries are duplicated in this report.

[Artifact index](artifact-index.json) authenticates logs, source patch, controls
and structured attribution. The earlier ordinary comparison remains authoritative
for latency and memory; no new production candidate or full-suite rerun is claimed.

## Next application

Select full Doppler Gemma text generation on Node/Vulkan as a separately scoped
application workload. Freeze model/shard/tokenizer identity, prompt, generation
settings, provider controls, correctness oracle and performance limits before
execution. Measure cold acquisition/loading separately from retained-device
prefill, first streamed token, decode and final completion. Preserve cancellation,
memory and resource-lifetime acceptance.

Retired provider-comparison contracts and earlier Electron qualification do not
grant credit to this new workload. It is selected, not executed or qualified here.
Doppler's product work continues independently on its supported provider. Vulkan
remains the active backend; Metal follows and D3D12 is deferred.

Component: `doe.runtime.zig`, `doe.bench`, `doe.reports`, `doe.docs`, `doe.config`.

Intent: preserved.

Acceptance evidence: [evidence.json](evidence.json), [umap-attribution.json](umap-attribution.json)
and [binding-controls.json](binding-controls.json).

Boundary effects: no production behavior change; the UMAP investigation closes
and the existing review plan selects a new application contract.
