# Doe ONNX Vulkan evaluation 0.1.0-eval.1

This evaluation distribution contains the retained ONNX Runtime integration evaluated at
commit `55c937e4605e04b9828ff8ba5ebc8ae572169452`. The qualified binaries were not
rebuilt for publication. It preserves ONNX Runtime's existing WebGPU operators,
the SqueezeNet model, original input generation, and frozen full-output oracle.
Doppler, Reploid, browser integration, and npm are not required.

Download `doe-onnx-vulkan-0.1.0-eval.1-linux-x64.tar.gz`, `SHA256SUMS`, and
`OPERATOR.txt` from the commit-pinned repository distribution. Check the archive before extracting executable
bootstrap scripts. The supplied `INSTALL.txt` is the original bundled guide;
`onnx-vulkan-installation.md` explains the integration and its limits.
`OPERATOR.txt` provides commands and the evidence return checklist.

The files are distributed directly from Git at a pinned commit, using existing
repository hosting. This is not a GitHub Releases API release or a claim of
GitHub-enforced release immutability. Exact commit URLs and SHA-256 verification
bind the distributed bytes. See the installation guide's acquisition section.

## Supported evaluation configuration

Linux x86_64, Python 3.11 or newer, bubblewrap, compatible glibc/libstdc++, and
an accessible AMD Vulkan GPU with its installed driver. Each additional
hardware/driver configuration requires its own passing qualification. The
retained host and loaded dependency identities are in `qualification.json` and
`evidence.tar.gz`; they do not qualify every AMD device or driver.

The archive pins ONNX core 1.24.4, the source-built external-Dawn WebGPU provider,
its context patch, the procedure-table bridge, and the qualified Doe library.
`package-manifest.json` binds the exact components, ABI, provider revision,
qualification settings, and file inventory. Arbitrary stock ONNX wheels cannot
replace these components. Drivers and system libraries remain host dependencies.

Installation and execution need no repository checkout, compiler, Python package,
model download, or network. The embedded example's header and C++ source show
explicit provider registration and ownership against the pinned ONNX core.

## Established evidence and limits

The retained delivery establishes deterministic archive reconstruction, isolated
local installation, numerical agreement, observed Doe dispatch/submission,
initialization rejection/retry, named callback/lifecycle paths, settled cleanup,
and sensitivity to missing-native and corrupted-reference controls.

This is delivery evidence. The earlier matched performance campaign rejected
material application advantage; its verdict is unchanged. External reproduction,
independent application adoption, retained use, broader compatibility, and runtime
superiority remain unestablished. The producer's supplied qualification files
must not be submitted as another operator's results.

Real driver loss, instance abandonment, arbitrary concurrent API use, submitted
GPU-work interruption, Metal, D3D12, browser switching, and general WebGPU
conformance remain outside this release. A timeout is not permission to free
resources still owned by submitted GPU work. Keep libraries loaded through process
exit; release sessions before provider unregister and settle GPU ownership before
teardown. Upgrade by selecting a separate version in a new process.

See the retained [delivery report](https://github.com/doerun/doe/tree/55c937e4605e04b9828ff8ba5ebc8ae572169452/reports/releases/20261009-onnx-vulkan-evaluation)
for the original evidence and the [installation guide](https://github.com/doerun/doe/blob/55c937e4605e04b9828ff8ba5ebc8ae572169452/docs/onnx-vulkan-installation.md)
for the qualified contract.
