# Compare taxonomy

## Purpose

This document defines the canonical axis language for Doe compare lanes so
humans and agents do not have to reverse-engineer the vocabulary from several
near-duplicate configs.

Use this taxonomy when you need to answer questions like:

- what is a valid compare tuple?
- which combinations are only theoretical?
- which combinations are currently promoted through `bench/run_compare.py`?
- how do `native` / `direct` / `package` relate to `backend_native` /
  `node_package` / `bun_package` / `deno_package`?

## Canonical source of truth

The single source of truth for compare taxonomy is:

- `config/compare-taxonomy.json`

The schema that validates that source of truth is:

- `config/compare-taxonomy.schema.json`

The generated machine-readable expansion lives in:

- `config/generated/compare-taxonomy-expanded.jsonl`
- `config/compare-taxonomy-expanded-row.schema.json`

Those generated files are derived artifacts, not parallel taxonomy sources.

The promoted wrapper catalog and governed-lane catalog are also downstream
consumers of the taxonomy, not independent definitions of it:

- `config/promoted-compare-catalog.json`
- `config/governed-lanes.json`

If any of those disagree with `config/compare-taxonomy.json`, the taxonomy file
is authoritative and the derived wiring must be updated to match it.

The expansion enumerates the naive cartesian product of the canonical axes and
annotates each row with:

- whether it is type-correct structural
- which theoretical concrete target ids apply
- whether it is reachable through the current promoted compare subset
- which promoted compare profile ids map to that row

For current counts, use:

- `config/compare-taxonomy.json` `expectedCounts`
- `config/generated/compare-taxonomy-expanded.jsonl`

## Axis language

The canonical axis names are:

- `platformLane`
- `comparisonBoundary`
- `runtimeHost`
- `comparisonView`
- `temperature`
- `targetKind`

The important distinction is:

- `comparisonBoundary` names the benchmark boundary
- `runtimeHost` names the JS host runtime
- `comparisonView` names the currently promoted view over a broader provider set

So:

- `backend_native`, `direct_plan`, and `package_surface` are boundary values
- `none`, `node`, `bun`, and `deno` are runtime-host values
- `doe_vs_dawn_delegate`, `doe_vs_dawn_direct`, and package runtime views are comparison-view values

This avoids overloading `native` to mean both "non-package" and "backend-native
compare family."

The taxonomy also records:

- `providerSet` on each structural family
- `providers` on each structural family and expanded row

`providerPair` remains in the generated expansion as a compatibility alias for
pair-shaped consumers. New control-plane code should prefer `comparisonView`.

## Alias maps

The taxonomy also records the current alias maps for the two main user-facing
vocabularies:

- promoted compare front door aliases used by `bench/run_compare.py`
- broader repo surface aliases used by governed lanes and workload registry

That mapping lives under `aliases` in `config/compare-taxonomy.json`.

## How to use it

When you want the current promoted compare matrix:

1. Start from `config/compare-taxonomy.json`.
2. Use `promotedCompareCoverage` to see which type-correct rows are currently
   promoted.
3. Use `config/generated/compare-taxonomy-expanded.jsonl` if you need the full
   expanded matrix with row-level annotations.
4. Use `config/promoted-compare-catalog.json` only for remaining wiring details
   such as executor ids, config paths, and descriptions. Do not treat it as a
   second taxonomy source.

When you want the broader repo surface vocabulary:

1. Start from `config/compare-taxonomy.json` aliases.
2. Then use:
   - `config/governed-lanes.json`
   - `bench/workloads/metadata/workload-registry.json`

## How to update it

If you add or rename a compare axis, boundary, host runtime, promoted subset,
or alias vocabulary:

1. Edit `config/compare-taxonomy.json`.
2. Treat every other file as derived from that edit, then update dependent wiring:
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

- `bench/README.md` explains how to run compare lanes.
- `docs/benchmark-taxonomy.md` explains harness classes.
- This document defines the axis language and subset vocabulary underneath both.
