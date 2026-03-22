# @simulatte/webgpu-doe examples

`@simulatte/webgpu-doe` is transport-free, so these examples mount Doe onto
`@simulatte/webgpu/compute` for runtime discovery.

They are ordered from the smallest helper path to the most explicit one:

- `with-webgpu-one-shot.js`
  smallest `gpu.compute(...)` example
- `with-webgpu-compute.js`
  reusable kernel with `gpu.compute.begin()`
- `with-webgpu-command-encoder.js`
  explicit `gpu.commandEncoder.create()` flow
