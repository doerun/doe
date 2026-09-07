# Declared shader constant initialization

`baseline.txt` and `source.patch` bind the source revision and correction.
`SHA256SUMS` binds the retained files. The earlier scalar reproducer is retained
at `../20260907-linux-completion/constant-repros/`: compilation succeeded but
produced a zero initializer. `baseline-public.log` records the resulting wrong
GPU output through the old retained library. Intermediate failing logs remain
historical evidence; the acceptance logs are named explicitly below.

Declared module initializers now evaluate or fail explicitly instead of becoming
omitted defaults. Constant bit counts evaluate scalar and vector integers.
Partially constructed composite operands are released on unsupported folding
and allocation failure. Semantic analysis classifies module constants as values.
SPIR-V emits their vector values and indexed accesses; dynamically indexed array
values use function-owned storage declared before executable instructions.
MSL emits typed vector constructors. Its source tests do not establish physical
Metal execution. Unsupported constant expressions remain explicit failures.

Canonical verification, from `runtime/zig`:

```sh
zig build test test-wgsl --summary all
zig build test test-wgsl emit-spirv dropin dropin-compute dropin-full -Doptimize=ReleaseFast --summary all
```

`debug-complete.log` and `release-fast-complete.log` are the final passing runs.
Allocation-failure tests cover IR construction and both emission paths.
`public-constant.wgsl`, its SPIR-V and disassembly retain the public regression;
`public-spirv-val.log` records validation with `spirv-val --target-env vulkan1.1`.
`native-public-complete.log` passes actual native dispatch/readback with the
Khronos synchronization validation layer active.

Reproduce discovered shader validation from the repository root:

```sh
python3 bench/gates/spirv_val_gate.py --require --discover-wgsl --require-subgroup-coverage --json-report <new-report.json>
```

`spirv-val.json` separates freshly discovered shaders from pre-existing binaries.
The corpus does not establish unrestricted WGSL support or model correctness.

`stage-complete.log` records staging from the freshly built native library.
`package-qualification.log` and
`../20260907-constant-initializers-qualified/summary.json` retain fresh Node, Bun,
and Electron main-process qualification from identical wrapper/platform archives.
`package-verification.txt` independently checks every referenced artifact and
archive, extracts the library to check its identity against every host receipt,
and verifies new public regression markers, active Khronos validation, and the
absence of validation errors in each host's retained streams. The retained
summary supplies reproduction limits and exact package/executable identities.

No public descriptor or receipt fields change. Model numerical acceptance,
driver-loss recovery, and fair application performance remain separate work in
the existing Linux completion checklist. Physical Metal/D3D12 testing is excluded.

Component: WGSL compiler and native package regression
Intent: preserved
Acceptance evidence: final canonical, public dispatch, corpus, and package logs above
Boundary effects: compiler emission; existing WebGPU shader errors and output
