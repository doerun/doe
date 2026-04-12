# Runtime

`runtime/` contains the Doe engine and native bridge surfaces:

- `runtime/zig/`
  - the Zig runtime, compiler, and backend implementation
- `runtime/bridge/`
  - package-facing native bridge code, addon glue, and repo-only runtime
    integration surfaces such as the ONNX Runtime plugin EP scaffold

This directory owns execution. Packaging and helper-only JavaScript surfaces
live under `packages/`.
