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

## Download the evaluation

The [public distribution](https://github.com/doerun/doe/tree/9c2bd310f07137cdad27d7d55b9ee2b3706eb0ab/reports/releases/20261009-onnx-vulkan-evaluation/publication) contains the exact qualified archive, manifest,
checksums, installation instructions, supported configuration, limitations, and
producer evidence. These URLs pin the publication commit; no binary was rebuilt.
This uses repository hosting, not a GitHub Releases API release. The
[anonymous download verification](../reports/releases/20261009-onnx-vulkan-evaluation/publication-download-verification.txt)
records matching bytes for every asset.

From a new consumer directory, download the archive and its companion files:

```bash
(
set -e
pub_base='https://raw.githubusercontent.com/doerun/doe/9c2bd310f07137cdad27d7d55b9ee2b3706eb0ab/reports/releases/20261009-onnx-vulkan-evaluation/publication'
for pub_file in doe-onnx-vulkan-0.1.0-eval.1-linux-x64.tar.gz SHA256SUMS package-manifest.json OPERATOR.txt; do
  curl --fail --location "$pub_base/$pub_file" --output "$pub_file"
done
sha256sum --check --ignore-missing SHA256SUMS
)
```

Require all downloads to succeed and the archive, manifest, and operator handoff
to pass their checks before extracting code. The
[operator handoff](https://raw.githubusercontent.com/doerun/doe/9c2bd310f07137cdad27d7d55b9ee2b3706eb0ab/reports/releases/20261009-onnx-vulkan-evaluation/publication/OPERATOR.txt) specifies acceptance, failure retention,
host dependency reporting, and an independent application's requirement intake.
Public download verification is separate from another operator's GPU execution.

## Install and evaluate

Use Linux x86_64, compatible glibc/libstdc++, Python with `hashlib.file_digest`,
bubblewrap, and an accessible AMD Vulkan adapter and driver. The archive includes
the model and native components. Running it needs no compiler, Python packages,
checkout or network. Driver and system-library dependencies stay host-owned.

After verifying the downloaded archive, extract its bootstrap scripts into a new
directory and install from the same archive:

```bash
mkdir bootstrap
tar -xzf doe-onnx-vulkan-0.1.0-eval.1-linux-x64.tar.gz -C bootstrap
python3 bootstrap/doe_onnx.py install \
  "$PWD/doe-onnx-vulkan-0.1.0-eval.1-linux-x64.tar.gz" \
  --sha256 9e469bbb7bbb02a4fcf40844553e873a05b14af2e1466e480b551724e0aec7d2 \
  --prefix "$PWD/installed"
python3 installed/doe_onnx.py verify
python3 installed/doe_onnx.py qualify --out "$PWD/qualification-results"
python3 installed/doe_onnx.py run --out "$PWD/example-results"
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
