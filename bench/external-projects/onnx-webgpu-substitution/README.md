# Native ONNX WebGPU substitution diagnostic

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
