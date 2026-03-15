# Doe API examples

These examples are ordered from the most explicit Doe helper path to the most
opinionated one-shot helper.

- `buffers-readback.js`
  create a Doe-managed buffer and read it back
- `kernel-run.js`
  run a one-off compute kernel with explicit buffer ownership
- `kernel-create-and-dispatch.js`
  compile a reusable `DoeKernel` and dispatch it
- `compute-one-shot.js`
  use `gpu.compute(...)` with one typed-array input and inferred output size
- `compute-one-shot-like-input.js`
  use `gpu.compute(...)` with `likeInput` sizing and a uniform input
- `compute-one-shot-multiple-inputs.js`
  use `gpu.compute(...)` with multiple typed-array inputs
- `compute-one-shot-matmul.js`
  run a larger one-shot `gpu.compute(...)` example with explicit tensor shapes
