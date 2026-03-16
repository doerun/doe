# Runtime architecture

The Doe runtime is the engine underneath Fawn.

## Runtime family

- `runtime/zig`
  - Zig runtime, compiler, and backend implementation
- `runtime/bridge`
  - native bridge code and package-facing glue

## Separation of concerns

- `runtime/*` owns execution
- `packages/webgpu` packages the runtime for JavaScript surfaces
- `packages/webgpu-doe` owns helper APIs only
- `bench/*` measures the runtime and package surfaces
- `pipeline/*` and `config/` supply policy, proof, trace, and quirk inputs
