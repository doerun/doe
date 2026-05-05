# bench/workloads

Workload manifests — JSON declarations of the dispatch geometry,
repeat counts, and metadata that runners consume. Manifests are the
contract; runners must not silently extend or override.

Layout:

- `workloads.<platform>.<backend>[.variant].json` — top-level manifests
  per backend × variant (smoke, full, gemma270m, etc.).
- `metadata/` — owner, freshness, and provenance metadata that ride
  alongside each manifest into the run receipt.
- `specialized/` — domain-specific manifest collections (inference
  prefill/decode shapes, attention-slice probes, etc.).

Selection rules and the canonical compare taxonomy are in
[`docs/benchmark-taxonomy.md`](../../docs/benchmark-taxonomy.md) and
[`config/compare-taxonomy.json`](../../config/compare-taxonomy.json).

Manifest fields are schema-checked. Adding a new field requires a
schema update and migration note in the same change (CLAUDE.md
non-negotiable #3 + #9).
