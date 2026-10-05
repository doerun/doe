# Existing ONNX WebGPU provider: substitution boundary

The [disposition](disposition.json) records a physical native ONNX WebGPU control
and a Doe-preloaded repetition using original ONNX operators and its ordinary
Python session interface. Both agree exactly with the independent NumPy oracle.
CPU fallback and graph optimization are disabled; Vulkan is explicitly selected
and retained profiles establish WebGPU-provider placement. The existing Doe
custom-operator plugin was not used.

## Result

[Baseline](dawn-control.json) and [preload](doe-preload.json) bind model, runner,
provider, output, and execution options. Doe and the observation library are
loaded, but ONNX reaches none of the intercepted entry points. The separate
[positive control](probe-control.json) establishes that the same observation
library detects and forwards an explicit Doe instance call.

This is a failed simple-preload substitution, not Doe-backed ONNX inference.
No timing comparison, adoption, or performance superiority is claimed.

## Concrete blocking boundary

[Dynamic dependencies](elf-dynamic.txt), [defined symbols](elf-defined.txt), and
[undefined symbols](elf-undefined.txt) show that the tested published provider has
no external Dawn shared dependency or externally visible WebGPU entry-point seam.
Library presence alone cannot replace its internal execution path.

The separately [pinned source inspection](source-inspection.json) identifies a
supported upstream boundary: a source-built static/external-Dawn provider accepts
`ep.webgpuexecutionprovider.dawnProcTable` and uses `dawnProcSetProcs`. Shared-Dawn
builds reject a supplied table. The pinned generated table follows Dawn's own
header and method ordering; arbitrary standard-header pointers do not supply an
ABI contract. Doe's standard generated table begins with adapter methods;
Dawn's template places global functions first. It cannot be passed unchanged as
a Dawn table. Doe's independently pinned header has not been qualified against
the provider's ABI.

The [safe option control](option-control.json) establishes that this published
package recognizes the table option: a non-pointer string fails at pointer
parsing without reaching native calls. This does not qualify a usable table, and
the preload failure does not establish that a provider rebuild is mandatory.
An ABI-matched adapter is the concrete missing integration; a source-built
external-Dawn provider is a way to pin and test that boundary.

The source also requires timed future waiting and uses Dawn chained descriptors
and optional feature negotiation. A source-built integration must qualify table
layout, descriptors, callbacks, feature admission, resource release, and pending
work lifetimes while preserving existing ONNX operators. That integration has not
been executed. Published wheel source provenance is not inferred from inspecting
an upstream tag. This report does not establish universal substitution failure.

## Evidence and reproduction

The [runbook](../../../../bench/external-projects/onnx-webgpu-substitution/README.md)
provides fresh-process commands and offline installation. [Hashed dependencies](requirements.lock)
identify the exact published wheels. [Manifest](manifest.json) binds compact Git
evidence and local custody of wheels, binaries, generated models, source captures,
and original failures. The Git manifest is external to the archive it hashes.
Heavy files remain outside Git. Profile timings serve only
operator-placement admission and are not performance results.

The [initial fused control failure](fused-control-failure.json) is preserved:
correct output did not satisfy the harness's original-operator check. Disabling
graph optimization equally in both final arms preserves the requested operators.
The [missing preload library failure](missing-preload-library-failure.txt) preserves
the incorrect initial path; the final runs use the installed native path and
observe its actual loading. Provider limit warnings remain in retained stderr.

The preceding [standalone generation qualification](../20261005-installed-generation/README.md)
and [closed optimization experiment](../20261004-doppler-generation/README.md)
remain unchanged. No production compiler, runtime, package, or model arithmetic
changed in this framework diagnostic.

Component: `doe.bench.external-projects`, `doe.config`, `doe.reports`, `doe.docs`.
Intent: preserved. Acceptance evidence: physical control, positive interception
control, exact output oracle, retained profiles, hash validation, schema and
component gates. Boundary effects: none.
