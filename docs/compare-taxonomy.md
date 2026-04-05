# Compare taxonomy

## Purpose

This document defines the canonical axis language for Doe benchmark lanes so
humans and agents do not have to reverse-engineer the vocabulary from configs.

Use this taxonomy when you need to answer questions like:

- what is a valid run tuple?
- which product x surface x platform combinations are promoted?
- how do `native` / `direct` / `package` relate to repo surface names?

## Canonical source of truth

The single source of truth for compare taxonomy is:

- `config/compare-taxonomy.json`

The schema that validates that source of truth is:

- `config/compare-taxonomy.schema.json`

The generated machine-readable expansion lives in:

- `config/generated/compare-taxonomy-expanded.jsonl`
- `config/compare-taxonomy-expanded-row.schema.json`

Those generated files are derived artifacts, not parallel taxonomy sources.

The promoted catalog and governed-lane catalog are downstream consumers of the
taxonomy, not independent definitions:

- `config/promoted-compare-catalog.json`
- `config/governed-lanes.json`

If any of those disagree with `config/compare-taxonomy.json`, the taxonomy file
is authoritative and the derived wiring must be updated to match it.

## Axis language

The canonical axes are:

| # | Axis | Values | What it names |
|---|------|--------|---------------|
| 1 | `platformLane` | apple-metal, amd-vulkan, local-d3d12 | Hardware/driver target |
| 2 | `surface` | backend_native, direct_plan, package, abi_dropin, browser, compiler | Execution boundary |
| 3 | `product` | doe, dawn, tint, dawn_node_webgpu, bun_webgpu, deno_webgpu | Implementation under test |
| 4 | `runtimeHost` | none, node, bun, deno, chromium | JS host runtime (none for native) |
| 5 | `temperature` | default, cold, warm | Session warmth |
| +1 | `targetKind` | preset, workload | Target selection mode |

Key distinctions:

- `surface` names the benchmark boundary, not the product
- `product` names what is being benchmarked, independently
- `runtimeHost` names the JS host; `none` for native/direct surfaces
- Comparison is derived from choosing which products to compare over the
  same axes — it is not an axis itself

### What changed from v1

The v1 taxonomy had `comparisonBoundary` (renamed to `surface`),
`comparisonView`, and `providerPairs` as axes. The last two baked product
pairs into the taxonomy, which meant adding a new product required taxonomy
changes and a new harness instead of just registering an executor. Those
axes are removed in v2 and replaced by the single `product` axis.

## Alias maps

The taxonomy records alias maps for user-facing vocabularies:

- Surface short names used by `bench/run_compare.py`: `native`, `direct`,
  `package`, `dropin`, `browser`, `compiler`
- Repo surface names used by governed lanes and workload registry:
  `backend_native`, `node_package`, `bun_package`, `deno_package`

That mapping lives under `aliases` in `config/compare-taxonomy.json`.

## How to use it

When you want to run a benchmark:

1. Pick the product, surface, platform, temperature, and target.
2. Run the product's executor for that axis combination.
3. To compare: run additional products under the same axes, then feed all
   independent run artifacts to the comparison framework.

When you want the current promoted run matrix:

1. Start from `config/compare-taxonomy.json`.
2. Use `promotedRunCoverage` to see which product x surface x platform
   combinations are currently promoted.
3. Use `config/generated/compare-taxonomy-expanded.jsonl` for the full
   expanded matrix with row-level annotations.

## How to update it

If you add or rename a product, surface, platform, or temperature:

1. Edit `config/compare-taxonomy.json`.
2. Treat every other file as derived from that edit, then update dependent
   wiring:
   - `config/promoted-compare-catalog.json`
   - `config/governed-lanes.json`
   - `bench/workloads/metadata/workload-registry.json`
3. Regenerate the expansion artifact:

```sh
python3 bench/tools/generate_compare_taxonomy.py --write
```

4. Verify it is current:

```sh
python3 bench/tools/generate_compare_taxonomy.py --verify
python3 -m unittest bench.tests.test_compare_taxonomy
python3 bench/gates/schema_gate.py
```

## Relationship to other docs

- `docs/benchmark-taxonomy.md` explains the run/compare model.
- `bench/README.md` explains how to run benchmarks.
- This document defines the axis language underneath both.
