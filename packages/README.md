# Packages

`packages/` contains Fawn's public JavaScript package families:

- `packages/webgpu/`
  - `@simulatte/webgpu`, the main runtime package family
- `packages/webgpu-doe/`
  - `@simulatte/webgpu-doe`, the transport-free helper package family

Within `@simulatte/webgpu`, subpaths such as `node`, `bun`, `compute`, `full`,
and `native-direct` are subpath entrypoints of one package family, not separate
products.
