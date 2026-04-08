# Doe status

This file is the front door for Doe project status.

Read this file first. Use the shard files under
[`docs/status/`](/Users/xyz/deco/doe/docs/status) for the dated history.

## How to use the status log

- Keep this file concise. It is the mandatory-reading summary, not the full
  ledger.
- Current shard: [`docs/status/2026-04.md`](/Users/xyz/deco/doe/docs/status/2026-04.md).
- Add new dated status entries to the current shard at the top of that shard
  file.
- Historical shard files are append-only. Do not rewrite old entries except for
  deliberate archive maintenance like this sharding change.
- When a task leaves placeholders, temporary methodology choices, or follow-up
  work, record that in the current shard and refresh this front door only if
  the current summary materially changes.

## Current status summary

- Benchmark visualization now has a real timestamped bundle pipeline and a
  stable `bench/out/visualization/latest/` landing page over the current AMD
  Vulkan native plus package compare reports.
- AMD Vulkan Gemma-270M package compute is now a claimable local compare
  surface on both Node and Bun package lanes.
- Current status terminology now treats numeric stability as a `strategy`
  surface rather than a `moat` surface.
- Shader proof-backed robustness now covers additional 3D storage and texture
  coord families in the native Zig runtime path.
- Apple `node-webgpu` package execution on `mac.lan` was restored after keeping
  the provider root alive through async completion.
- Benchmark/package compare cleanup in early April moved more of the compare
  stack onto artifact-first, config-backed paths.

## Current follow-up highlights

- Lean artifact regeneration remains blocked by pre-existing comparability drift
  outside the current shader-bounds proof expansion work.
- Status history is now sharded; future follow-ups should go into the current
  shard instead of bloating this front door.

## Archive shards

- [2026-04.md](/Users/xyz/deco/doe/docs/status/2026-04.md)
- [2026-03-30-to-2026-03-28.md](/Users/xyz/deco/doe/docs/status/2026-03-30-to-2026-03-28.md)
- [2026-03-27-to-2026-03-24.md](/Users/xyz/deco/doe/docs/status/2026-03-27-to-2026-03-24.md)
- [2026-03-23-to-2026-03-01.md](/Users/xyz/deco/doe/docs/status/2026-03-23-to-2026-03-01.md)
- [2026-02-and-legacy.md](/Users/xyz/deco/doe/docs/status/2026-02-and-legacy.md)

## Historical note

The shard split preserves original top-to-bottom ordering from the former
single-file log. The `2026-02-and-legacy` shard intentionally keeps some older
early-2026 backfilled sections in their original order rather than
reclassifying them retroactively.
