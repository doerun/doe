# Packages

`packages/` contains Doe's public JavaScript package:

- `packages/doe-gpu/`
  - `doe-gpu`, the merged runtime and helper package

Within `doe-gpu`, subpaths such as `compute` and `browser` are subpath
entrypoints of one package, not separate products.

## Deprecated

- `packages/webgpu/` — `@simulatte/webgpu`, deprecated in favor of `doe-gpu`
- `packages/webgpu-doe/` — `@simulatte/webgpu-doe`, merged into `doe-gpu`
