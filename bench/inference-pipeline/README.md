## Inference pipeline kernels

This folder now exists only to hold real WGSL model kernels used by Doe-vs-Tint
compilation benchmarks.

The old synthetic JS inference benchmark surface was removed because it used
random dense F32 weights instead of realistic quantized, sharded model layouts.

For real model/runtime inference benchmarking, use Doe-owned runtime command
streams and example paths under `runtime/zig/examples/`.
