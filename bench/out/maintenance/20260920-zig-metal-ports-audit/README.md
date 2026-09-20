# Metal and capability-port review batch

Batch base: `a825aa79c062d8a939f8246924e56625fb5d4b9c`.
[scopes.tsv](scopes.tsv) freezes the requested batch and its per-file verdicts.
[File examinations](file-reviews.md) record responsibility, ownership, failure
paths, fixes, unresolved findings and the next concrete action for each file.
The append-only [ledger](../../../../runtime/zig/reviews/log.json) owns history;
[queue.tsv](../../../../runtime/zig/reviews/queue.tsv) is its derived current view.
These are file passes. Directory, relationship and complete execution-path
reviews receive no automatic credit.

## Repairs

Queued arbitrary writes own separate source buffers until queue retirement.
Their source data cannot be overwritten by a later staged write. Destination
ranges and offset arithmetic are checked before recording, and pending ownership
capacity is reserved before native acquisition. Upload acquisition and scratch
prewarm replace resources transactionally; constant-zero scratch initializes its
whole capacity. The recording test delays copies until both host writes have
occurred, mutates the caller bytes, and checks the resulting bytes independently.

Compute-buffer publication releases native objects on mapping or allocator
failure, and reused handles must have sufficient actual native length. Compute
pipeline publication releases its function exactly once and rolls back the PSO
on insertion failure. Render pipeline, target and ICB replacements retire prior
uses and preserve old objects until successful replacement. Copy allocation,
pitch and range arithmetic reject overflow. Buffer/texture bridge calls supply
the previously missing origin/aspect arguments.

Temporary copy and render resources remain retained through completion. Render
target swaps restore state on failure. Surface teardown now shares the complete
explicit-release operation: discard drawable, release texture, unconfigure and
release host. A recording test verifies order and idempotent reset.

Mapped writes and shared indirect argument updates retire preceding GPU uses.
Standalone/warmup kernel submissions retire earlier uncommitted streaming work.
Timestamp activation closes active compute encoding before recording samples.
Sampler lifecycle callers retire GPU uses before cache eviction or destruction;
logical reference increments reject overflow. The selected runtime device owns
the map-command allocation limit query.

Cache output paths no longer borrow caller/environment string lifetime. Failed
archive serialization preserves dirty state. Port documentation states borrowed
context lifetime and allocator ownership of returned snapshots. Cleanup uses the
canonical pool type and releases lists directly instead of copying owning lists.
Unused imports and unsupported performance commentary were removed.

## Remaining findings

See the per-file notes for exact repair targets. Open areas include sampler
comparison/filter/address semantics, format-aware texture footprints and input
admission, binding groups and offsets, native completion/error/timeout handling,
surface failure transitions, exact source/entrypoint pipeline identity, truthful
archive observations/invalidation, bounded retention policy and render ABI/bundle
semantics. Partial fixes do not close these files.

The next never-examined file is
`file:src/backend/ports/resource.zig`. Open repair work remains independently
queued; prioritize sampler semantic parity and native completion/error handling
before making Metal correctness or performance claims.

## Contract compatibility

No public serialized field, schema version, backend selection or charter boundary
changes. Existing ownership and bounds contracts now reject invalid buffer ranges
instead of performing unchecked writes. No hidden alternate execution path is
introduced. Existing diagnostics remain the reporting surface.

Synchronization changes can alter measured costs: indirect dispatch reports
argument-buffer retirement in submit/wait time; kernel setup includes retirement
before standalone/warmup work. Resource lifecycle and mapped writes also pay their
required retirement. Historical results keep their original build identity and
are not reinterpreted. Accepted packages, thresholds and calibration remain
unchanged. The gate policy in `docs/process.md` needs no change.

## Acceptance and reproduction

With pinned Zig 0.15.2, run from the repository root:

```bash
(cd runtime/zig && zig build test --summary all)
(cd runtime/zig && zig build test-core -Doptimize=ReleaseFast --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref a825aa79c062d8a939f8246924e56625fb5d4b9c
python3 runtime/zig/tools/review_log.py --check --base-ref a825aa79c062d8a939f8246924e56625fb5d4b9c
```

- [aggregate-acceptance.log](aggregate-acceptance.log): final host suite plus
  formatting, import/source-layout, ABI, bridge-manifest and test-inventory gates.
- [core-release-fast-acceptance.log](core-release-fast-acceptance.log): host
  behavior and checked arithmetic with debug safety removed.
- [schema.log](schema.log): registered schema validation.
- [doc-links.log](doc-links.log): local documentation-link validation.

Earlier logs are intermediate checkpoints. New inline tests are explicitly
registered in the canonical inventory and the generated suites were regenerated.
Module-decision hashes were refreshed mechanically and confer no review credit.
Source diffs were inspected before binding review evidence.

The recording adapters exercise Zig ownership/control flow and host bytes. They
do not execute Metal. The Linux host has no Apple frameworks or physical Metal
qualification; no GPU output, latency, cache hit rate, native allocation-failure
campaign or performance improvement is claimed. Existing platform-guarded tests
can return early on Linux; aggregate pass counts are not Apple coverage.

Component: Zig Metal command runtime, native cache seam and capability ports.
Intent: preserved.
Acceptance evidence: commands and retained logs above; physical limitations and
open findings remain explicit.
Boundary effects: internal resource lifetime, failure handling, synchronization
accounting, test inventory and review history. No public schema/authority change.
