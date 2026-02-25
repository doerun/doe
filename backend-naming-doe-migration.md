# Doe Backend Naming Migration (Completed)

## Contract

1. Product: `Fawn`
2. Browser distribution: `Fawn Browser`
3. WebGPU backend/runtime implementation: `Doe`

`Fawn` remains the product name. `Doe` identifies only backend/runtime surfaces.

## Completed Outcomes (Phase 1 -> 2 -> 3)

1. Canonical backend artifacts are Doe-only:
   - runtime binary: `doe-zig-runtime`
   - drop-in shared library: `libdoe_webgpu.so`
2. Bench/gate/workflow defaults now use Doe artifacts.
3. Chromium Track-A runtime selection surfaces now use Doe-only names:
   - `--use-webgpu-runtime=doe`
   - `--disable-webgpu-doe`
   - `--doe-webgpu-library-path=<path>`
4. Chromium GPU preference fields and enum variants are Doe-only (`kDoe`, `disable_webgpu_doe`, `doe_webgpu_library_path`).
5. Legacy backend aliases were removed from runtime-visible paths.
6. Drop-in/runtime diagnostics use Doe naming:
   - helper exports: `doeWgpuDropinLastErrorCode`, `doeWgpuDropinClearLastError`
   - env flag: `DOE_WGPU_TIMESTAMP_DEBUG`
   - trace semantic-parity module eligibility: `module` starts with `doe-`

## Scope Preserved

1. Repository/product naming remains `fawn`.
2. Performance report family naming remains `dawn-vs-fawn`.
3. Historical artifacts were not rewritten.
