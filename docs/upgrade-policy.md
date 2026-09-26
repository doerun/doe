# Doe toolchain upgrade policy

## Scope

This policy governs upgrades for:
- Lean
- Zig

## Rules

1. Config-first upgrade
- Update `config/toolchains.json` first.

2. Dedicated branch
- Use `upgrade/lean-<version>` or `upgrade/zig-<version>`.

3. Mandatory gate coverage
- Run all blocking gates.
- Run advisory gates and attach reports.

4. No silent degradation
- Any correctness failure blocks merge.
- Perf regressions are reported in v0 and may block only when gate mode is promoted to blocking.

5. Reproducibility
- Persist before/after reports with:
  - toolchain versions
  - quirk set hash
  - validator hash
  - benchmark deltas
  - baseline ids (`dawn`, `wgpu`)
  - run metadata conforming to `config/run-metadata.schema.json`

## Rollback

Rollback is config-based:
- restore previous `toolchains.json`
- rebuild and rerun gates
- no manual patching of runtime behavior

## Vulkan buffer memory policy migration

`config/vulkan-buffer-memory-policy.json` advances from schema version 1 to 2.
The new required `hostVisiblePreferredProperties` field makes host-visible
compute-buffer allocation prefer device-local memory while retaining the
host-visible and coherent requirements. Builds reject
older policy versions. Unsupported preferences retain a compatible required type;
allocation failures remain explicit errors. Readback preference is unchanged.

Allocations retain their actual memory property flags. Storage binding preserves
an allocation already known to be device-local, including its mapping, generation,
and contents. Unknown properties retain the existing promotion and copy path.
This changes ordinary Vulkan allocation policy without changing application,
shader, public API, or artifact identity contracts. See
`bench/out/doppler-search/20260925-excess/README.md` for scoped acceptance evidence.

The subsequent policy schema requires `computeBufferCacheMaxBytes`. Older
policy versions fail at build time. The fixed bound permits retention of
completed host-visible, coherent, device-local compute allocations through the
existing Vulkan pool machinery. Retention also observes its per-size capacity;
unknown properties, pending work, and cache allocation failure retain normal
allocation or cleanup behavior. Reuse preserves native memory properties and
mapping, assigns a fresh resource generation, and initializes returned bytes.
This does not add a runtime ablation switch or change shader semantics.

Writable Vulkan mapping now waits for preceding GPU use, as readable mapping
already did. Coherence and an available mapping do not establish completion.
See `reports/benchmarks/amd-vulkan/20260926-memory-policy/README.md` for the
separated policy evidence, candidate verdict, and lifecycle limitations.

The shutdown policy now requires `unresolvedCompletionRetryNs`. Failed flush or
wait results retain runtime ownership synchronously until device-idle completion
is known. Confirmed device loss remains a distinct typed backend cause and a
terminal lifetime outcome; it is not successful workload execution. The retry
interval is fixed by versioned configuration. If the driver never establishes
completion or device loss, destruction does not return. Subsequent execution and
allocation reuse remain rejected after failure, including after retirement
becomes safe. Repeated completed shutdown is harmless.

The rejected compute-reuse experiment used `computeBufferCacheMaxEntriesPerSize`,
separate from the upload-pool allowance and subordinate to the existing byte bound.
That field is absent from the retained policy; the existing per-size allowance
remains unchanged. See `reports/benchmarks/amd-vulkan/20260926-shutdown-reuse/README.md` for the tested
source patches, policy versions, frozen comparison rule, and final disposition.
