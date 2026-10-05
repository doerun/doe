# Native ONNX WebGPU substitution diagnostic

Current executable integration: [pinned proc-table prototype](#explicit-proc-table-integration).
The preload experiment below remains its original historical diagnostic.

This checks ONNX Runtime's existing WebGPU execution provider, retaining its
operators and Python application interface. It does not use or extend the separate
Doe operator plugin. The [retained disposition](../../../reports/benchmarks/amd-vulkan/20261005-onnx-webgpu-substitution/README.md)
owns tested packages, native hashes, physical results, and the unresolved boundary.
This is internal integration evidence, not a performance benchmark or adoption claim.

## Reproduce

Use Linux x86-64, Python matching the retained wheels, an AMD Vulkan adapter, and
the accepted Doe library from the [standalone generation bundle](../doppler-generation/README.md#standalone-installed-execution).
Install `requirements.lock` from the report into a separate virtual environment:

```bash
python3 -m venv /tmp/onnx-webgpu-consumer
/tmp/onnx-webgpu-consumer/bin/pip install --require-hashes \
  -r reports/benchmarks/amd-vulkan/20261005-onnx-webgpu-substitution/requirements.lock
cc -std=c11 -shared -fPIC -O2 -Wall -Wextra -Werror \
  -I runtime/zig/vendor/webgpu-headers \
  bench/external-projects/onnx-webgpu-substitution/preload-probe.c \
  -ldl -o /tmp/onnx-webgpu-probe.so
/tmp/onnx-webgpu-consumer/bin/python \
  bench/external-projects/onnx-webgpu-substitution/run.py \
  --out /tmp/onnx-webgpu-baseline.json
```

For offline installation, obtain the checksum-bound wheel custody bundle named
in the report's manifest and add `--no-index --find-links /path/to/wheels`.
Use a new output path for each run. The runner refuses to replace a result.

Set `DOE_WEBGPU_LIB` to the exact installed native library, then preload the probe
before that library. Run a positive forwarding control in its own process:

```bash
export DOE_WEBGPU_LIB=/path/to/installed/doe-gpu/native/libwebgpu_doe.so
export LD_PRELOAD=/tmp/onnx-webgpu-probe.so:$DOE_WEBGPU_LIB
/tmp/onnx-webgpu-consumer/bin/python \
  bench/external-projects/onnx-webgpu-substitution/run.py \
  --out /tmp/onnx-webgpu-probe-control.json \
  --preload-probe /tmp/onnx-webgpu-probe.so --verify-probe
/tmp/onnx-webgpu-consumer/bin/python \
  bench/external-projects/onnx-webgpu-substitution/run.py \
  --out /tmp/onnx-webgpu-preload.json \
  --preload-probe /tmp/onnx-webgpu-probe.so
unset LD_PRELOAD DOE_WEBGPU_LIB
/tmp/onnx-webgpu-consumer/bin/python \
  bench/external-projects/onnx-webgpu-substitution/run.py \
  --out /tmp/onnx-webgpu-option-control.json --invalid-proc-table
```

Original MatMul and Add execute with graph optimization and CPU fallback disabled,
explicit Vulkan selection, and full provider validation. Both arms use the same
model, inputs, and NumPy oracle. Profiles identify each operator's provider.
The positive control only creates/releases an instance; it does not qualify an
ONNX computation or any device capability. Loaded libraries and intercepted calls
are distinct observations. `doeExecutionEstablished` remains false.

## Validate retained evidence

```bash
python3 bench/external-projects/onnx-webgpu-substitution/verify.py
```

Add `--with-custody` to check the retained binary/wheel/source bundle as well.
The Git report retains compact results, raw operator profiles, failures, and
linking observations. Its source inspection is bound separately from published
wheel bytes; their build provenance is not assumed equivalent.

## Blocking boundary

The tested provider exports no external WebGPU entry points and has no external
Dawn dependency. Preloading Doe does not redirect its execution. The safe option
control establishes that the published package parses `dawnProcTable`; it rejects
a non-pointer string before calling through a table. That does not qualify a
working table. Upstream's static/external-Dawn configuration supports this seam;
a source build can pin its ABI, but this diagnostic does not establish that a
rebuild is mandatory. Doe's standard proc table uses a different ordering from
Dawn's generated table. An explicit adapter must match that ABI, chained
extensions, callback semantics, and lifetimes. Passing an arbitrary table or
silently ignoring required extensions would not establish substitution.
No production compiler/runtime behavior changes in this diagnostic. The new
internal evidence schema adds no public API or runtime configuration migration.

## Explicit proc-table integration

The [subsequent integration report](../../../reports/benchmarks/amd-vulkan/20261005-onnx-proc-adapter/README.md)
qualifies a bounded source-built provider and typed adapter. It preserves the
older diagnostic above. Use the new report's supported runtime/plugin pairing,
source archive hashes and wheel lock; the previous lock is historical evidence.
The bridge binds once per process. Selecting Doe here does not change Chrome.

### Build the consumer

Acquire and verify the exact source archives in the new `source-build.json`.
Extract ONNX Runtime and Dawn into separate source directories. Apply
`default-external-context.patch` to a pristine ONNX checkout; verify the context
file's before/after hashes. Install the hashed wheel lock into a separate Python
environment. The retained build uses the recorded Node and private npm versions.
Use explicit paths for `ORT_SOURCE`, `DAWN_SOURCE`, `PYTHON`, `NPM_CLI` and `BUILD`:

```bash
patch -d "$ORT_SOURCE" -p1 --forward \
  < bench/external-projects/onnx-webgpu-substitution/default-external-context.patch
cmake -S "$ORT_SOURCE/cmake" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -Donnxruntime_USE_WEBGPU=ON -Donnxruntime_USE_EP_API_ADAPTERS=ON \
  -Donnxruntime_USE_EXTERNAL_DAWN=ON -Donnxruntime_BUILD_UNIT_TESTS=OFF \
  -Donnxruntime_BUILD_SHARED_LIB=OFF -Donnxruntime_WGSL_TEMPLATE=static \
  -Donnxruntime_PLUGIN_EP_VERSION=0.1.0-doe-abi \
  -DCMAKE_CXX_FLAGS=-Wno-error=maybe-uninitialized \
  -DFETCHCONTENT_SOURCE_DIR_DAWN="$DAWN_SOURCE" \
  -DDAWN_FETCH_DEPENDENCIES=ON -DPython_EXECUTABLE="$PYTHON" \
  -DNODE_EXECUTABLE=/usr/bin/node -DNPM_CLI="$NPM_CLI"
cmake --build "$BUILD" --target onnxruntime_providers_webgpu -j4
"$PYTHON" bench/external-projects/onnx-webgpu-substitution/build_adapter.py \
  --dawn-source "$DAWN_SOURCE" --python "$PYTHON" --out "$BRIDGE"
```

`BRIDGE` must be a new directory. The builder rejects changed generator/header
inputs, shared signatures, structure members and unqualified enum differences.
The GCC warning demotion is specific to the retained standard-library warning;
initial configure/build failures are preserved. Native Doe builds through the
existing `zig build dropin -Doptimize=ReleaseFast` target, with the correction's
source identity from the report, not the earlier accepted library.

### Execute the existing operators

```bash
"$PYTHON" bench/external-projects/onnx-webgpu-substitution/run_adapter.py \
  --provider "$BUILD/libonnxruntime_providers_webgpu.so" \
  --bridge-build "$BRIDGE" --doe-library "$DOE_LIBRARY" \
  --context external --context-id 0 --out /tmp/onnx-doe-result.json
```

Use a new output path. The runner requires the qualified context fixture and
bridge hashes, an explicit physical AMD Vulkan device, unchanged MatMul/Add,
independent outputs, cancellation before execution, reuse, and observed Doe calls.
The `--future-control` arm deliberately blocks callback delivery and detects
premature completion; it passes with the corrected native and fails with the
original. Automatic consumer device construction requests unsupported Dawn chains
and fails explicitly; it does not silently become the supported external-context
path. The `--incumbent --context automatic` arm requires the separately retained
published provider and observes no Doe execution calls.

The custody archive contains installed-consumer libraries, hashed wheels,
licenses, ABI build data, source archives, patches and failed observations.
Authenticate its archive digest and inventory before extracting it. An isolated
consumer can install the wheel lock with `--no-index --find-links wheels
--require-hashes`, then run its copied `run_adapter.py` with the archive's `bridge`,
`provider`, and `native` paths. Its offline run does not require either checkout.
The archive is in local custody, not an npm release or durable public download.

```bash
python3 bench/external-projects/onnx-webgpu-substitution/verify_adapter.py
python3 bench/external-projects/onnx-webgpu-substitution/verify_adapter.py --with-custody
```

The new internal evidence schema changes no public API or serialized runtime
configuration. Required default initialization and future settlement are native
correctness repairs. General future/callback conformance, asynchronous termination,
other operators/hosts, performance, and browser integration remain separately
unqualified.

The installed generation schema now admits the existing installed workload
identity and its audit receipts; model, oracle and resource contracts are unchanged.
