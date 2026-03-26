# Internal tooling

This document separates Doe's repo-only tooling from its public package
surface.

The canonical machine-readable contract is [`config/tool-surfaces.json`](../config/tool-surfaces.json).
If prose and tooling metadata disagree, treat the schema-backed manifest as the
source of truth.

## Public package surface

The current public package contract is:

- `doe-gpu`
- its documented subpath exports
- the package docs in [`packages/doe-gpu/README.md`](../packages/doe-gpu/README.md)

Advanced helper exports such as `createDoeRuntime()` and
`runDawnVsDoeCompare()` are still part of the package surface, but they are
repo-adjacent helpers, not the canonical operator front doors for benchmark or
release work.

The npm package does not ship compare, bench, or release pipeline CLIs.

## Internal operator tooling

These are repo-only contributor/operator surfaces:

- [`bench/native-compare/compare_dawn_vs_doe.py`](../bench/native-compare/compare_dawn_vs_doe.py)
- [`bench/runners/run_release_pipeline.py`](../bench/runners/run_release_pipeline.py)
- [`bench/runners/run_blocking_gates.py`](../bench/runners/run_blocking_gates.py)
- [`bench/tools/generate_backend_workloads.py`](../bench/tools/generate_backend_workloads.py)
- [`runtime/zig/README.md`](../runtime/zig/README.md) and `doe-zig-runtime`
- browser lane scripts under [`browser/chromium`](../browser/chromium/README.md)

Repo-only directories should not be treated as public product commitments unless
`config/tool-surfaces.json` marks them `audience=public`.

In practice:

- `bench/`, `browser/chromium/`, `pipeline/`, and top-level `scripts/` are
  internal
- `packages/doe-gpu/` is the public npm surface
- overlapping helpers are allowed, but repo workflows are still owned by the
  repo tooling, not by the npm package

## Archive and deprecated areas

These areas exist for migration, reference, or research and should not be read
as active public product surfaces:

- legacy npm names `@simulatte/webgpu` and `@simulatte/webgpu-doe`
- `dawn-research/`
- `nursery/`

When a question is about public package behavior, ignore archive and repo-only
tooling unless the user explicitly asks about them.
