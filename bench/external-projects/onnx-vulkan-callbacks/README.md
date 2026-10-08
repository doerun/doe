# Bounded ONNX Vulkan callback qualification

This repository-only campaign compares callback semantics at the pinned ONNX/Dawn
procedure-table boundary. It follows the completed application and CPU campaigns,
without reopening their performance decisions. The normative operations, modes,
process count and deadline are in
[`native-callback-contract.json`](../../../config/native-callback-contract.json).
See the [retained report](../../../reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-callbacks/README.md)
for evidence and explicit exclusions.

`run.py` builds one C++ fixture against the pinned Dawn headers and executes the
retained Doe baseline, source-built Dawn and corrected Doe sequentially in independent
processes. It records exact source/header/library identities and rejects runtime byte
mutation during a cohort. Inputs and output directory must be explicit; output must
be new. Use the already prepared libraries from the completed campaign:

```bash
python3 bench/external-projects/onnx-vulkan-callbacks/run.py \
  --native bench/out/onnx-vulkan-callbacks/20261008/native/lib/libwebgpu_doe.so \
  --before bench/out/onnx-vulkan-campaign/20261005/native-corrected/libwebgpu_doe.so \
  --dawn bench/out/onnx-vulkan-campaign/20261005/libdoe_dawn_control.so \
  --bridge bench/out/onnx-vulkan-campaign/20261005/bridge-matched/libdoe_dawn_bridge.so \
  --headers bench/out/onnx-vulkan-campaign/20261005/bridge-matched/generated/include \
  --out bench/out/onnx-vulkan-callbacks/reproduction
```

Build the native arm with the pinned Zig toolchain from `runtime/zig`:
`zig build dropin -Doptimize=ReleaseFast --prefix ../../bench/out/onnx-vulkan-callbacks/20261008/native`.
Finish that build before starting qualification. Reuse the completed campaign's
`safety.py` and `run_application.py` with the corrected native library; qualification
must bind the same bytes. No measurement runner is part of this campaign.

`bundle.py --run <prepared-run-directory> --out <report-directory>` retains final
controls, failed/intermediate records, application safety/oracles, source snapshots,
validation logs and hash-bound local executable custody. It refuses to overwrite
an existing manifest. `verify.py` semantically audits retained evidence; optional
`--check-current` binds active code, and `--with-custody` authenticates local binaries.
New changes require a new report, preserving prior source-bound qualifications.
