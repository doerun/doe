# ONNX Vulkan evaluation delivery

The [delivery record](delivery.json) binds a versioned evaluation archive and
passing installation acceptance on the tested Linux AMD Vulkan host. Both
[first](build-one.json) and [second](build-two.json) builds have identical
manifest and archive bytes. The second build resolves pinned native inputs
from the first package rather than historical benchmark directories.

The archive location and checksum live in `delivery.json`; its complete
member inventory is [package-manifest.json](package-manifest.json). Native
binary custody remains local in the named archive. The tracked report is not
registry publication or external adoption.

## Installed execution

The installer ran in a fresh consumer namespace with the checkout and network
inaccessible. The exact installed package then passed the
[qualification](qualification.json) and standalone [example](example.json).
Initialization rejection/retry, callback delivery, descriptor loss, repeated
destruction, resource leases and settled DRM cleanup use the retained physical
fixtures. Independent application processes preserve SqueezeNet, the original
input generation, upstream operators and frozen full-output tolerances.

The application joins loaded installed libraries, AMD Vulkan context identity,
operator placement, native WGSL/SPIR-V identities, dispatch/submission journals
and independent numerical readback. Missing-native and corrupted-reference
controls fail at their intended boundaries. CPU fallback stays disabled. Loader
observations include drivers probed during enumeration; the context and native
journal establish the selected execution path separately.

[Raw evidence](evidence.tar.gz) retains stdout/stderr, operator profiles, native
journals and exact SPIR-V. Extract it into a fresh directory, then replay against
the same installed archive and host-library population:

```bash
tar -xzf reports/releases/20261009-onnx-vulkan-evaluation/evidence.tar.gz \
  -C /path/to/new-evidence-directory
python3 /path/to/installed/verify_evidence.py \
  --installation /path/to/installed \
  --results /path/to/new-evidence-directory/results
```

The producer and reproduction commands live in the
[release runbook](../../../bench/external-projects/onnx-vulkan-release/README.md).
The [installation contract](../../../docs/onnx-vulkan-installation.md) explains
prerequisites, embedding, callbacks, failures, upgrades and exclusions.

## Boundary

This delivers installed integration and correctness evidence, not a new
application performance campaign. The prior ONNX performance decision and
subsequent correctness qualifications retain their original bytes and meaning.
Native runtime and model arithmetic were not changed for this release.

Another operator's reproduction, another hardware configuration, voluntary
retention and measurable replacement value remain unestablished. Real driver
loss, abandoned instances, arbitrary concurrent API use, submitted-work
interruption, Metal, D3D12 and browser switching remain outside this release.
