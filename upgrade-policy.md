# Fawn Toolchain Upgrade Policy

## Scope

This policy governs upgrades for:
- Lean
- Zig

## Rules

1. Config-first upgrade
- Update `fawn/config/toolchains.json` first.

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
  - run metadata conforming to `fawn/config/run-metadata.schema.json`

## Rollback

Rollback is config-based:
- restore previous `toolchains.json`
- rebuild and rerun gates
- no manual patching of runtime behavior
