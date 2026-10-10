# ONNX Vulkan evaluation installation

The versioned evaluation archive runs ONNX Runtime's existing WebGPU operators
through the explicit Doe proc-table integration. It packages the qualified Doe
library, source-built provider, matching published ONNX core, bridge and context
helper, SqueezeNet example, independent reference, ABI headers, source examples,
licenses, installer and acceptance fixtures. It is independent of Doppler,
Reploid and browser GPU selection.

The [release report](../reports/releases/20261009-onnx-vulkan-evaluation/README.md)
binds the archive, manifest, reproduction checks and installed execution. The
[release input plan](../config/onnx-vulkan-release.json) owns versions and
qualification settings. See the [producer runbook](../bench/external-projects/onnx-vulkan-release/README.md)
for archive creation and semantic evidence replay.

## Install and evaluate

Use Linux x86_64, compatible glibc/libstdc++, Python with `hashlib.file_digest`,
bubblewrap, and an accessible AMD Vulkan adapter and driver. The archive includes
the model and native components. Running it needs no compiler, Python packages,
checkout or network. Driver and system-library dependencies stay host-owned.

Verify the archive checksum supplied by the release report before extracting
its bootstrap scripts into a new directory. Then run:

```bash
python3 bootstrap/doe_onnx.py install /path/to/archive.tar.gz \
  --sha256 EXPECTED_SHA256 --prefix /path/to/doe-onnx-version
python3 /path/to/doe-onnx-version/doe_onnx.py verify
python3 /path/to/doe-onnx-version/doe_onnx.py qualify \
  --out /path/to/new-results
python3 /path/to/doe-onnx-version/doe_onnx.py run \
  --out /path/to/new-example-results
```

Installations and results must use new directories. Results belong outside the
installation. Integrity failures reject before native execution. Initialization,
native, numerical and cleanup failures retain their logs and fail acceptance.
Both negative controls must fail at their intended boundary to qualify.

## Integration contract

The bundle preserves the unchanged SqueezeNet computation and original input
generation with explicit provider plumbing and independent observation. All
observed operators must remain on WebGPU with CPU fallback disabled. Manifest
hashes bind inputs; numerical agreement requires the frozen complete-output
oracle. Loader-observed native bytes, native dispatch/submission journals and
materialized SPIR-V establish the executed Doe path separately.

`CampaignContext` records the selected backend, vendor and device IDs. Loader
observations retain all initialized Vulkan libraries, including drivers probed
during enumeration; loading alone does not imply a driver executed the workload.
The selected AMD context, Doe journal and completed numerical readback are joined
with those observations. This is not an operating-system GPU command trace.

The included `source/application-provider.h` and C++ example show registration
against the pinned ONNX core, external table, instance and device. Upstream
operators stay with ONNX. The source-built provider and its explicit context
patch are required; substituting an arbitrary stock wheel is unsupported.
The bridge initializes once per process and rejects live rebinding. Libraries
remain loaded until process exit. Initialization failure permits a clean retry.

Release sessions before provider unregister and settle resource ownership before
device/instance teardown. The included callback and lifecycle contracts own
delivery modes, borrowed handles and cleanup leases. Unknown completion retains
ownership. Neither an evaluation deadline nor device destruction proves safe
interruption of submitted work. Install another version alongside the old one
and select it in a new process after existing work settles.

## Acceptance and exclusions

Qualification exercises the named initialization, callback, loss-notification,
destruction and settled cleanup paths, followed by independent application
processes and native/oracle sensitivity controls. It retains exact library,
application, model, reference, execution-setting and shader identities.

Each additional hardware/driver configuration requires physical qualification.
Real driver loss, abandoned instances, arbitrary concurrent API use, submitted
work cancellation, other backends and browser replacement remain outside this
release. External operator reproduction and voluntary adoption remain distinct
from local isolated installation. No speed or general conformance claim follows.

## Contract migration

This is an additive evaluation distribution and CLI, governed by
`onnx-vulkan-release.schema.json` and `onnx-vulkan-installation.schema.json`.
It changes no runtime ABI, shader arithmetic, numerical threshold, ONNX operator,
existing npm package or historical campaign verdict. The input plan permits
repacking from verified installed members without producer-directory access.
Mutable runtime results never enter the deterministic package manifest.
