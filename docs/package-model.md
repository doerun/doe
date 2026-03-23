# Doe package model

## Package families

Doe has two package families (both deprecated in favor of `doe-gpu`):

- `@simulatte/webgpu` *(deprecated — use `doe-gpu`)*
  - the main runtime package family
- `@simulatte/webgpu-doe` *(deprecated — merged into `doe-gpu`)*
  - the helper-only package family

## `@simulatte/webgpu` *(deprecated)*

Treat these as subpath entrypoints into one package family, not separate
products. All `@simulatte/webgpu` entrypoints are deprecated; use `doe-gpu`.

- runtime entrypoints
  - `@simulatte/webgpu`
  - `@simulatte/webgpu/node`
  - `@simulatte/webgpu/bun`
- API-shape entrypoints
  - `@simulatte/webgpu/compute`
  - `@simulatte/webgpu/full`
- advanced diagnostic entrypoint
  - `@simulatte/webgpu/native-direct`

## `@simulatte/webgpu-doe` *(deprecated)*

`@simulatte/webgpu-doe` is transport-free. It does not ship the Doe native
runtime. It binds onto any compatible WebGPU surface, including
`@simulatte/webgpu` and browser-provided `GPUDevice` objects.

This package is deprecated and has been merged into `doe-gpu`.
