# ONNX Vulkan evaluation distribution

Build and qualify a versioned native evaluation integration preserving the
existing ONNX WebGPU operators, model, source-matched consumer and numerical
oracle. The [operator installation guide](../../../docs/onnx-vulkan-installation.md)
owns the supported boundary. This adds delivery and installation acceptance;
the earlier application performance decision retains its original meaning.

## Build

The [input plan](../../../config/onnx-vulkan-release.json) pins qualified binary,
source, header, model, reference and notice inputs. The producer needs Python
with `jsonschema`. Installed consumers require only the standard library.

```bash
python3 bench/external-projects/onnx-vulkan-release/build.py \
  --out bench/out/onnx-vulkan-release/build-one
python3 bench/external-projects/onnx-vulkan-release/build.py \
  --input-package bench/out/onnx-vulkan-release/build-one/package \
  --out bench/out/onnx-vulkan-release/build-two
```

The second build resolves pinned inputs by installed member name and digest,
without opening historical producer paths. Compare `manifest.json` and both
archive digests before acceptance. Archive timestamps, ownership and ordering
are deterministic; this does not assert reproducible native compilation across
different toolchains. Runtime libraries remain the retained qualified bytes.

## Qualification

Extract the archive into a bootstrap directory after verifying its supplied
checksum. Run the standalone installer, then `qualify` from a new consumer
directory. `INSTALL.txt` in the archive contains complete commands. Execution
uses bubblewrap with no checkout or network exposed. No package download,
Python wheel, Node installation or compiler is needed by the consumer.

`run` checks the example once. `qualify` additionally requires initialization
rejection/retry, callback and lifecycle fixtures, fresh application sessions,
native disabling and a corrupted oracle. Raw logs, operator profiles, native
journals and exact SPIR-V remain beside `qualification.json`. Failures are
retained; the first failed job stops acceptance. Loader diagnostics are enabled
for identity observation, so these runs supply no performance measurements.

Replay retained acceptance against exact installed bytes and the same host
library population:

```bash
python3 bench/external-projects/onnx-vulkan-release/verify_evidence.py \
  --installation /path/to/installed --results /path/to/results
python3 -m unittest bench.tests.test_onnx_vulkan_release
```

The semantic verifier rejects omitted controls, failed cleanup, CPU fallback,
unobserved package libraries, missing native submissions and changed shader
artifacts. System-library hashes are rechecked during replay; a changed driver
needs a fresh qualification. A local clean installation is distinct from another
operator's reproduction, adoption, registry publication and application advantage.
