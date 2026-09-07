# Dot accumulation and Electron model reproduction

`baseline.txt`, `source.patch`, and `SHA256SUMS` bind this correction and its
retained evidence. `native-package-verification.log` identifies the library
from `../20260907-multi-dot-qualified/summary.json`, verifies all archive and
artifact hashes, checks installed members against those archives, and verifies
public dot-search results and active Khronos validation in every host.

## Reproduction and correction

`extract.py` reads hash-checked full-model checkpoint tensors from
`../20260907-linux-completion/`, identifies the first differing attention
operation, and verifies that its Q/K/V inputs agree exactly between providers.
It reconstructs the half-precision KV cache and computes a separate double-
precision CPU reference. The isolated unchanged `attention.wgsl` reproduces
each original provider's model output exactly; inspect `W0-isolated.log` and
`D0-isolated.log`. `inputs.sha256` binds its inputs and original expected data.

`capture-stages.py` preserves the original output while observing scores,
exponentials, sums, and accumulation. The first differences precede softmax
and subgroup reductions. Capturing every inner-loop partial also changes Doe's
final rounding; the script rejects that perturbation explicitly. Its failed
assertion is investigation evidence, not an acceptance pass. `dot-rounding.py`
records a rejected search over elementary reduction orders.

`dot-boundary.c` is an isolated diagnostic interposer, never a product input.
Restricting dot-add contraction did not match the original control. Disabling
all loop unrolling repaired the isolated output but broke previously matching
prefill results (`dont-unroll-oracle.json`). Restricting that experiment to
innermost loops with multiple dot instructions passed the unchanged numerical
oracle (`multi-dot-loops-oracle.json`). The Node experiment remains correctly
rejected as evidence for an Electron application identity.

The Zig emitter now implements that structural rule directly under version 2
of `config/spirv-compute-arithmetic-policy.json`. It sets SPIR-V `DontUnroll`
only for qualifying innermost compute loops; it adds no GPU commands, arithmetic
instructions, application names, shader hashes, or runtime environment switches.
The schema and migration describe the explicit driver-default alternative.
Other loops and non-compute/mixed-stage modules preserve their controls.

## Final native checks

`debug.log`, `release-fast.log`, and `schema.log` are passing canonical checks:

```sh
# From runtime/zig
zig build test test-wgsl --summary all
zig build test test-wgsl emit-spirv dropin dropin-compute dropin-full -Doptimize=ReleaseFast --summary all
# From the repository root
python3 bench/gates/schema_gate.py
python3 bench/gates/spirv_val_gate.py --require --discover-wgsl --require-subgroup-coverage --json-report <new-report.json>
```

`spirv-val.json` records discovered-source and pre-existing binary validation.
Canonical tests distinguish inner, outer, single-dot, fragment, and mixed-stage
loops. The retained-package compute-program fixture also runs an unrelated
dot-product search against independent exact CPU sums through ordinary and
recorded execution modes. `package-qualification.log` records fresh Node, Bun,
and Electron main-process installations using identical retained archives.

`run.mjs D0 <shader> <output> native` uses the newly installed native package;
`D0-native.log` matches the original Dawn attention output exactly. The explicit
`native` argument selects the new package; earlier experiments retain their old
package directory. `run-model.py native-node` and `native-electron` run the full
unchanged model from the new archives without the interposer. Their numerical
oracle comparisons pass. Comparing a Node control with an Electron receipt
still fails the appropriate application-identity requirement.

## Existing Electron control correction

`dawn-electron-model/` repeats the unmodified npm control's failure: Electron
rejects external ArrayBuffers, and subsequent cleanup aborts without a complete
transcript. The repository already contains the bounded native mapping repair
used by the HoloScript control. The inspected node-webgpu release tags share
the same Dawn commit and identical JavaScript entry point.

`p0-provider/` retains the existing source-built binary, exact canonical patch,
license, and source/binary identity. No existing checkout or build was changed.
`run-model.py p0-electron` selects that control explicitly. Its transcript and
the new Doe Electron transcript pass the original frozen oracle together:
`p0-electron-oracle.json`. That file uses the oracle's W0 comparison slot for
the explicitly identified patched incumbent; it is not evidence that the
unmodified npm provider succeeded. No tolerance, model shader, prompt, input,
checkpoint, KV requirement, or fallback policy changed.

Canonical runner integration of this source-built control remains follow-up
execution work. These results establish numerical acceptance and host execution,
not provider performance leadership or physical Metal/D3D12 support.

## Application measurements

The unchanged invocation-local policy is retained at
`../20260906-gpu-activity-matrix/policy.json`. `application-evaluation.log`
records the rejected first matrix at `../20260907-multi-dot-applications/`;
unrelated GPU activity prevents accepting its timing results. The retry at
`../20260907-multi-dot-applications-retry/summary.json` passes independent
verification in `application-verification.log` using its retained effective
`policy.json`. The evaluator relocates fixture paths when retaining inputs;
using the original policy path correctly fails the policy-hash check.
The raw rows include image and heat tail losses against Dawn. Deno/wgpu ratios
remain suspicious host-path observations and cannot establish runtime superiority.

Component: WGSL compiler, prepared-program regression, and Linux model evidence
Intent: preserved
Acceptance evidence: canonical checks, retained package logs, and frozen model oracle above
Boundary effects: SPIR-V build policy; existing WebGPU execution and error contracts
