# Fawn package model

## Package families

Fawn has two package families:

- `@simulatte/webgpu`
  - the main runtime package family
- `@simulatte/webgpu-doe`
  - the helper-only package family

## `@simulatte/webgpu`

Treat these as subpath entrypoints into one package family, not separate
products:

- runtime entrypoints
  - `@simulatte/webgpu`
  - `@simulatte/webgpu/node`
  - `@simulatte/webgpu/bun`
- API-shape entrypoints
  - `@simulatte/webgpu/compute`
  - `@simulatte/webgpu/full`
- advanced diagnostic entrypoint
  - `@simulatte/webgpu/native-direct`

## `@simulatte/webgpu-doe`

`@simulatte/webgpu-doe` is transport-free. It does not ship the Doe native
runtime. It binds onto any compatible WebGPU surface, including
`@simulatte/webgpu` and browser-provided `GPUDevice` objects.
