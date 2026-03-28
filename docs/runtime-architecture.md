# Runtime architecture

The Doe runtime is the core execution engine in this repo.

## Runtime family

- `runtime/zig`
  - Zig runtime, compiler, and backend implementation
- `runtime/bridge`
  - native bridge code and package-facing glue

## Separation of concerns

- `runtime/*` owns execution
- `packages/doe-gpu` packages Doe for JavaScript surfaces
- `bench/*` measures the runtime and package surfaces
- `browser/*` owns Chromium-lane integration docs and probes
- `pipeline/*` and `config/` supply policy, proof, trace, and quirk inputs
