# Ordinary Node shader semantics repair

Base: `c799399fbf9b2ca751bfb88cb827013d637b6d52` after the canonical Doe pull.
The earlier push was a no-op before this repair. This evidence concerns the
working source identified in `source.sha256` and the isolated runtime identified
in `binaries.sha256`; it does not promote or overwrite the accepted package.

## Diagnosis and repair

`baseline-complete.log` reproduces the clear-then-write counterexample through
the public package on physical AMD Vulkan hardware using the predecessor Node
provider and retained package library. Its native journal is
`baseline-complete-native.jsonl`. The old provider reports zero output where the
independent byte oracle requires the final write. Other adversarial shaders expose
additional false matches. The baseline test process intentionally exits nonzero;
`baseline-complete.exit-code` retains that result.

The provider now sends original shaders, entrypoints and commands to native
execution. Host clear/fill/texture-dimension replacements and buffer/texture
execution shadows were removed. Mapped-write staging starts with native bytes
and flushes the edited range to the mapped native allocation.

Real execution exposed missing texture descriptors with automatic pipeline
layouts. Bind groups now own a layout reference through final release, and failed
creation releases partially acquired resources. The Vulkan descriptor collector
uses that retained layout when the pipeline has no explicit layout. Obsolete
parallel collector code was removed. Native recording also admits empty
workgroup dimensions without skipping validation of pipeline/command ownership.

Independent SPIR-V validation caught invalid nesting of storage structs containing
runtime-sized arrays, even when RADV returned correct numerical results. Such a
struct now forms the block itself. `pre-spirv-vulkan-validation.log` retains the failed Vulkan-target verdict;
`native-validation-fixed.json` binds the corrected bytes, and
`vulkan-artifact-validation.log` checks Vulkan-specific constraints. The canonical
journal checker invokes universal SPIR-V validation; its passing
`pre-spirv-validation.json` does not establish Vulkan validity. `wgsl-suite.log` records an initial regression assertion that incorrectly
assumed a single array-length instruction; robustness lowering adds more. The
corrected regression checks every member index and the required block shape.

`native-validation.json` records the original identity-schema rejection of empty
dispatch dimensions. The schema correction admits encoded empty dispatches,
retains submission requirements, and rejects negative dimensions. The migration
is documented in `docs/doe-gpu-node-runtime-scope.md`.

## Acceptance evidence

- `validated-trace.log`, `validated-native.jsonl`, and
  `native-validation-fixed.json`: original source identities, native dispatches,
  render completion and validated shader bytes.
- `validated-ordinary.log`: a separate fresh process with identity tracing disabled.
- `public-native-identity.log`: public/native source, entrypoint and dispatch
  correspondence plus independent expected output checks in both runs.
- `validated-*.log`: existing copy, texture, resource, command, render, multipass,
  submission, prepared-program and one-shot integration regressions.
- `core-suite-final.log`, `wgsl-suite-fixed.log`, `contracts-final.log`,
  `trace-validator-tests.log`: runtime/compiler, package and evidence checks.
- `schema-final.log`, `catscan-final.log`, `doc-links-final.log`,
  `review-check.log`: contract, component and review-history checks.

Logs from unsuccessful intermediate runs remain intact. `final-*` predates the
SPIR-V correction; the accepted source/binary observations are `validated-*`.
`build/` and `baseline-package/` are local scratch outputs, excluded from the
retained source change. `binaries.sha256` identifies them without shipping another
runtime binary. `evidence.sha256` binds the retained files.

## Reproduce

From the repository root, choose a fresh evidence directory:

```bash
RUN_DIR=$(mktemp -d "$PWD/bench/out/shader-semantics.XXXXXX")
(cd runtime/zig && zig build dropin -Doptimize=ReleaseFast -Dtier=full --prefix "$RUN_DIR/build")
export DOE_WEBGPU_LIB="$RUN_DIR/build/lib/libwebgpu_doe.so"
touch "$RUN_DIR/native.jsonl"
DOE_PROGRAM_IDENTITY_TRACE_PATH="$RUN_DIR/native.jsonl" \
  node packages/doe-gpu/test/integration/test-integration-shader-semantics.js > "$RUN_DIR/traced.log" 2>&1
env -u DOE_PROGRAM_IDENTITY_TRACE_PATH \
  node packages/doe-gpu/test/integration/test-integration-shader-semantics.js > "$RUN_DIR/ordinary.log" 2>&1
python3 -m bench.tools.validate_native_program_identity_trace \
  --trace "$RUN_DIR/native.jsonl" --spirv-val /usr/bin/spirv-val \
  --require-render-completion --out "$RUN_DIR/validation.json"
for artifact in "$RUN_DIR"/*.spv; do
  spirv-val --target-env vulkan1.1 "$artifact" || exit
done
(cd runtime/zig && zig build test-core --summary all && zig build test-wgsl --summary all)
node packages/doe-gpu/test/run-contracts.js
python3 -m unittest bench.tests.test_validate_native_program_identity_trace
python3 -m bench.gates.schema_gate
python3 -m bench.gates.catscan_gate
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --check --base-ref c799399fbf9b2ca751bfb88cb827013d637b6d52
```

For the retained public/native identity comparison:

```bash
python3 bench/out/maintenance/20260919-shader-semantics/verify_public_identity.py
```

The baseline was constructed by copying the current package source and regression
into an isolated scratch package, replacing only `src/vendor/webgpu/index.js`
with `git show c799399fb:packages/doe-gpu/src/vendor/webgpu/index.js`, linking the
retained addon prebuilds, and explicitly selecting the retained package library.
It is a source/native correctness comparison, not an installed-package resolution
qualification or a performance experiment.

## Boundaries and next action

Physical execution is AMD Vulkan/RADV on the adapter recorded in the logs. No
Khronos Vulkan validation layer was installed; offline `spirv-val` checks actual
shader binaries but does not establish API synchronization validation. There is
no Dawn comparison, tail-latency claim, Metal/D3D12 hardware qualification, or
package publication in this evidence.

The review log records partial investigation of the touched Zig files. It does
not mark them or their containing directories verified. The pending bounded
review starts at `runtime/zig/src/backend/common/artifact_policy.zig`, continues
through the common files, directory and relationship passes, and then the agreed
D3D12 file scopes. Artifact ownership, native backend-state separation and strict
installed resolution remain subsequent architecture work.

Component: Node provider, native bind groups/Vulkan dispatch, WGSL SPIR-V emission
Intent: preserved
Acceptance evidence: commands and retained artifacts above
Boundary effects: package/native ownership; native layout lifetime; compiler block
layout; identity-row schema admits encoded empty dispatches
