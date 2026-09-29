# WGSL pointer references and current public path

This is a source-checkout diagnostic following the retained
[SPIR-V ownership checkpoint](../20260928-spirv-ownership/README.md). Its named
pointer-alias fixture failed with `InvalidIr` at predecessor `c623b7dfa`.
The fixture's WGSL pointer `let`, address-of and dereference are valid language
constructs. The first lost meaning was in `ir_builder.zig`: address-of became a
local reference with the wrong type, and dereference collapsed to the same
reference form. It was therefore not an emitter-only failure.

## Correction and scope

WGSL IR now represents address-of and dereference explicitly. Frontend and IR
validation keep pointer store type and address-space compatibility. The SPIR-V
emitter retains the resulting reference through locals and function calls, while
HLSL and MSL emissions preserve lvalue aliasing. HLSL captures a dynamic index
when the pointer alias is bound. The instruction cache and IR-owned reference
queries from the prior checkpoint remain in place.

Focused tests cover direct and named pointer calls, writes through aliases,
branches, member/index access, captured index semantics and prohibited scalar
pointer arguments. The [retained fixture](alias-fixture.wgsl) and
[emitted artifact](alias-fixture.spv) have SHA-256 hashes
`6f806435d4112b19f1f9ad9ffc97c76715e815341cc66d392f1d92ae377f2c25`
and `afa19c12a54e9794e6840d6764dc2038f8ee01f166ba2d9d3019e62f97123462`;
the latter passes `spirv-val --target-env vulkan1.1`. The
[direct](direct-fixture.wgsl) and [member/index](member-index-fixture.wgsl)
package fixtures also have retained
[direct SPIR-V](direct-fixture.spv) and
[member/index SPIR-V](member-index-fixture.spv) that pass the same validator.
The public package regression obtains the independent expected
integer output for direct and named forms through four submission paths on the
AMD Radeon 8060S RADV Vulkan provider. This qualifies the tested pointer cases,
not all WGSL pointer programs or other physical backends.

The public shader-semantics suite's prior render readback `[0,0,0,1065353216]`
was minimized to a render-only case. The package adapter dropped sequence-form
clear colors and supplied a zero fragment write mask when omitted. It now
normalizes the clear color and applies the WebGPU default write mask. The Bun FFI
path shares color normalization and uses the declared load/store operations.
Vulkan clear recording also selects float, signed or unsigned components for
the attachment format. The current suite returns `[9,5,8,10]` for its fragment
render and `[2,3,4,5]` for an integer clear. The broader render conformance
surface remains separate.

The backend runtime policy fixture now owns its temporary directory per test
and cleans it deterministically. Two overlapping invocations passed. The
combined `zig build test test-full -Doptimize=ReleaseFast --summary all` passed
14/14 build steps, 4700 tests passed and 22 skipped. Package contract tests and
the current public shader-semantics suite also passed. The native library used
by physical tests and the application comparison has SHA-256
`f1b6fc2032c14af95041b7737d1931e5c845f2d3058b6fb9b76e2e360f1975d5`;
it is a local build, not an installed release artifact.

## Unchanged application comparison

The pinned [UMAP GPU harness](../../../bench/external-projects/umap-gpu/run-sgd-benchmark.mjs)
used upstream `7884b287f49bc057df7e0856c5539f130a20e0ad` and unchanged
inputs, oracle, workload and shaders. Each provider ran 500 two-pass epochs,
1000 dispatches, three clean processes per governed lane, and passed the
application oracle and exact within-provider replay. Provider outputs differ
byte-for-byte while both satisfy that oracle. The summaries retain provider,
GPU/driver, input hashes and process-tree RSS.

| Run | Provider | Selected operation p50 / p95, ms | Clean process p50, ms | Peak process-tree RSS, MiB |
| --- | --- | ---: | ---: | ---: |
| First | Dawn | 18.109 / 26.808 | 629.628 | 290.1 |
| First | Doe | 15.871 / 16.850 | 761.807 | 325.8 |
| Repeat | Dawn | 15.345 / 22.517 | 616.277 | 289.6 |
| Repeat | Doe | 16.476 / 18.618 | 767.985 | 326.5 |

Selected-operation rank reverses between the two runs. Doe's full clean
process is slower and peak process-tree RSS is higher in both. A general or
material application advantage is not established. The next optimization
target is clean-process startup and memory cost, with costs separated from
steady-state dispatch. ONNX Runtime substitution remains an independent
integration investigation.

## Retained evidence and reproduction

[`shader-semantics.log`](shader-semantics.log) contains the package/native/backend
physical outputs. [`combined-releasefast.log`](combined-releasefast.log),
[`overlap-a.log`](overlap-a.log) and [`overlap-b.log`](overlap-b.log) retain the
test-loop results. The application evidence consists of
[`first summary`](umap-first-summary.json), [`first raw`](umap-first-raw.json),
[`repeat summary`](umap-repeat-summary.json) and
[`repeat raw`](umap-repeat-raw.json). Those are diagnostic source-checkout
receipts; neither reports product promotion nor replaces release qualification.

From `runtime/zig`, run the combined test command above and
`zig build dropin -Doptimize=ReleaseFast --prefix /absolute/prefix`.
The retained SPIR-V can be revalidated with
`spirv-val --target-env vulkan1.1 reports/maintenance/20260928-pointer-public/alias-fixture.spv`
from the repository root.
From the repository root, set `DOE_WEBGPU_LIB` to that build's
`lib/libwebgpu_doe.so` and run:

```bash
node packages/doe-gpu/test/integration/test-integration-shader-semantics.js
node bench/external-projects/umap-gpu/run-sgd-benchmark.mjs --run-id local-run --require-all-pass
```

The benchmark runner acquires its pinned upstream and Dawn dependency under
`bench/out/`. No package archive, physical Metal/D3D12 result, browser result,
device-loss qualification, application promotion or release claim is made.

Component: WGSL frontend/IR/emission, package render adapter, Vulkan clear recording, backend test fixture
Intent: preserved
Acceptance evidence: shader-semantics.log, combined-releasefast.log, overlap-a.log, overlap-b.log, UMAP raw and summary receipts
Boundary effects: explicit pointer reference IR; public color input/default handling and format-correct clear recording; per-test temporary storage
