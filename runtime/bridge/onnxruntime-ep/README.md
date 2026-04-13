# ONNX Runtime plugin EP bridge

Audience:

- repo-only runtime integration work
- not part of the public `doe-gpu` package contract

This directory is the experimental bridge surface for a Doe-backed ONNX Runtime
plugin execution provider.

Why it exists:

- ONNX Runtime's WebGPU execution path is a concrete incumbent integration seam
- Doe needs a real plugin-EP entrypoint if we want to compare `ORT + incumbent`
  against `ORT + Doe` honestly
- the plugin EP is a narrower and more winnable lane than claiming browser
  runtime replacement

What is implemented today:

- vendored public ONNX Runtime C/plugin-EP headers under `vendor/onnxruntime/`
- a loadable shared-library scaffold that exports:
  - `CreateEpFactories`
  - `ReleaseEpFactory`
- a repo-only smoke runner that loads the host ORT shared library and the Doe
  plugin, validates factory metadata, and checks the current explicit
  unsupported contract without pretending there is a working execution bridge
- a repo-only session smoke runner that registers the Doe plugin with ORT,
  discovers Doe `OrtEpDevice` instances, appends Doe to session options, and
  builds/runs tiny in-memory proof models
- a Doe-owned `OrtEpFactory` implementation with explicit metadata and explicit
  narrow behavior for the still-missing graph-execution bridge
- a real but intentionally narrow `OrtEpDevice` / `OrtEp` path:
  - `GetSupportedDevices` creates `OrtEpDevice` instances when ORT provides
    hardware devices
  - `CreateEp` creates a real `OrtEp`
  - `GetCapability` claims narrow float32 ONNX-domain `Identity`, `Add`,
    `Relu`, and rank-2 `MatMul` nodes plus the exact two-node
    `MatMul -> Add` and `Add -> Relu` slices
  - `Compile` installs tiny compiled compute paths for single-node
    `Identity`/`Add`/`Relu`/`MatMul` groups and the exact two-node
    `MatMul -> Add` and `Add -> Relu` groups
  - the session smoke now proves `Compute()` ran by reading plugin debug
    counters from the shared library and checking expected outputs for
    `Add`, `Relu`, `MatMul`, `MatMul -> Add`, and `Add -> Relu`

What is not implemented yet:

 - a general Doe-backed graph execution path beyond the current narrow
   basic-ops slice
- allocator, stream, external-resource, or custom-op support
- any strict native compare lane against an incumbent ORT peer in `bench/`

Current behavior is intentionally narrow:

- the factory loads
- the factory identifies itself as Doe
- when ORT provides hardware devices, Doe creates `OrtEpDevice` instances for
  them
- `CreateEp` returns a real `OrtEp` instance
- `GetCapability` only claims supported dense float32 ONNX-domain nodes:
  same-rank same-shape `Identity`, `Add`, and `Relu`; rank-2 exact-shape
  `MatMul`; plus the exact two-node `MatMul -> Add` and `Add -> Relu` slices
- `Compile` creates a real `OrtNodeComputeInfo` for those narrow groups
- `Compute` executes that slice with boring explicit float32 kernels:
  copy, elementwise add, `Relu`, rank-2 `MatMul`, and fused
  `MatMul -> Add` / `Add -> Relu`
- the repo-only session smoke proves Doe executed the non-trivial slice and
  matched expected outputs via
  `artifacts/20260413T170900Z/doe-ort-ep-session-smoke.json`
- anything beyond that narrow slice still returns explicit unsupported
  behavior rather than pretending a broader graph-execution bridge exists

Build:

```sh
cd runtime/zig
zig build ort-plugin-ep ort-plugin-ep-smoke ort-plugin-ep-session-smoke -Doptimize=ReleaseFast
```

Expected output:

- Linux: `runtime/zig/zig-out/lib/libonnxruntime_doe_ep.so`
- macOS: `runtime/zig/zig-out/lib/libonnxruntime_doe_ep.dylib`
- Windows: `runtime/zig/zig-out/lib/onnxruntime_doe_ep.dll`
- smoke runner: `runtime/zig/zig-out/bin/doe-ort-ep-smoke`
- session smoke runner: `runtime/zig/zig-out/bin/doe-ort-ep-session-smoke`

Smoke:

```sh
cd runtime/zig
./zig-out/bin/doe-ort-ep-smoke \
  --plugin-path ./zig-out/lib/libonnxruntime_doe_ep.so \
  --ort-lib-path <path-to-libonnxruntime-shared-library> \
  --output /tmp/doe-ort-ep-smoke.json
```

Current smoke scope:

- loads the host ORT shared library and resolves `OrtGetApiBase`
- loads Doe's plugin EP shared library and resolves the official factory
  exports
- validates factory identity metadata and the current explicit scaffold
  behavior:
  - `GetSupportedDevices` returns zero devices when no ORT hardware-device list
    is supplied
  - `ValidateCompiledModelCompatibilityInfo` returns `EP_UNSUPPORTED`
  - `CreateEp` returns a real no-op `OrtEp`

Session smoke:

```sh
cd runtime/zig
./zig-out/bin/doe-ort-ep-session-smoke \
  --plugin-path ./zig-out/lib/libonnxruntime_doe_ep.so \
  --ort-lib-path <path-to-libonnxruntime-shared-library> \
  --case add|relu|matmul|matmul_add|add_relu|all \
  --output /tmp/doe-ort-ep-session-smoke.json
```

Current session smoke scope:

- creates an ORT env and registers Doe through
  `RegisterExecutionProviderLibrary`
- verifies that ORT surfaces Doe `OrtEpDevice` instances after registration
- appends a Doe `OrtEpDevice` to session options with
  `SessionOptionsAppendExecutionProvider_V2`
- disables ORT graph optimizations so the proof models stay structurally
  explicit
- builds tiny in-memory `Add`, `Relu`, `MatMul`, `MatMul -> Add`, and
  `Add -> Relu` models via ORT's Model Editor API, plus a one-node `Identity`
  proof case
- creates a session for each selected case and runs the model successfully
- verifies expected output values and the Doe claim/compile/compute counter
  deltas for each case
- current evidence is
  `artifacts/20260413T170900Z/doe-ort-ep-session-smoke.json`

Repo-only bench surface:

```sh
python3 bench/single-runtime/run_bench.py \
  --workloads bench/workloads/workloads.native.ort-doe-ep-smoke.json \
  --workload-id inference_ort_doe_ep_matmul_add_float32_rank2_exactshape \
  --executor-id ort_native_doe_ep \
  --iterations 3 \
  --warmup 1 \
  --out-dir bench/out/native-ort-doe-ep/matmul_add \
  --out-report bench/out/native-ort-doe-ep/matmul_add.report.json \
  --out-metadata bench/out/native-ort-doe-ep/matmul_add.metadata.json \
  --no-timestamp-output
```

Current repo-local bench evidence for the executor-backed narrow slice lives at:

- `bench/out/native-ort-doe-ep/identity.report.json`
- `bench/out/native-ort-doe-ep/add.report.json`
- `bench/out/native-ort-doe-ep/relu.report.json`
- `bench/out/native-ort-doe-ep/matmul.report.json`
- `bench/out/native-ort-doe-ep/matmul_add.report.json`
- `bench/out/native-ort-doe-ep/add_relu.report.json`

Compatibility note:

- the vendored headers are newer than some host ORT runtimes
- the scaffold pins its requested runtime API floor in
  `src/doe_ort_ep_api_version.h` so the repo-only smoke runner can exercise
  the current bridge contract against older installed runtimes without
  claiming a newer working execution path
- current host ORT `1.23.x` may emit duplicate ONNX schema-registration noise
  to stderr during the in-memory model-editor session smoke; the JSON report is
  still the source of truth for success/failure

The vendored ORT headers and license are copied from the public ONNX Runtime
repository and remain under the upstream MIT license in
`vendor/onnxruntime/LICENSE`.

The next honest milestone is not "benchmark victory." It is extending this from
a narrow basic-ops proof slice into a broader Doe-backed graph execution
bridge that can run more non-trivial ORT-assigned work and support a benchmark
lane.
