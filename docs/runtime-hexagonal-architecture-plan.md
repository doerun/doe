# Zig architecture and migration history

The canonical-command structural migration is complete. Its design and checklist
are historical records, not a second work queue. The native WebGPU object API
and drop-in ABI remain separately governed execution surfaces; they are not
implicitly consumers of the canonical command runner.

Use these current owners:

- [Architecture](architecture.md) and the applicable `CATSCAN.md` chain define
  component responsibilities and invariants.
- [Source layout](../runtime/zig/source-layout.json) owns enforced imports,
  reachability views, compatibility facades, and size policy.
- [Zig review planning](../runtime/zig/reviews/README.md#planning-the-next-batch)
  explains the bounded plan and full coverage inventory. Run
  `python3 runtime/zig/tools/review_log.py --next` for current work selection.
- [Architecture status](status/runtime-architecture-audit.md) routes unresolved
  implementation findings. [Backend status](status/runtime-backends-and-bench.md)
  and the [browser lane](browser-lane.md) retain physical qualification blockers.
  Completed migration does not establish hardware or browser qualification.

The [archived design](status/archive/2026-09-27-hexagonal-migration-design.md)
and [archived checklist](status/archive/2026-09-27-hexagonal-migration-checklist.md)
preserve the original proposals, deleted paths, acceptance records, and historical
host statements. Some proposed modules were subsequently removed as unconsumed;
consult the current owners before treating an old proposal as unfinished work.
