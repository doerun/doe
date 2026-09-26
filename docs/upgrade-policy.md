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
