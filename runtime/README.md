# Runtime

`runtime/` contains the Doe engine and native bridge surfaces:

- `runtime/zig/`
  - the Zig runtime, compiler, and backend implementation
- `runtime/bridge/`
  - package-facing native bridge code and addon glue

This directory owns execution. Packaging and helper-only JavaScript surfaces
live under `packages/`.
