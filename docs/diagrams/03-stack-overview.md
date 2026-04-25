# 03 - Names and boundaries: "Doppler, Doe, Cerebras"

## Purpose

Make the deck self-contained. A reviewer should know who owns the source
contract, who owns the lowering/evidence path, and where Cerebras begins.

## Slide content

- **Doppler:** raw JS orchestration + raw WGSL kernels + manifest + weights +
  tokenizer/input contract + reference transcript.
- **Doe:** consumes that Doppler contract and emits evidence artifacts. For
  normal GPU targets Doe also lowers through WebGPU/Vulkan/SPIR-V, Metal/MSL,
  DXIL, and native runtime paths. This deck shows only the Cerebras slice:
  TSIR where applicable, HostPlan, CSL, SDK execution, receipts.
- **Cerebras:** WSE/SDK execution target. Doe emits `layout.csl`,
  `pe_program.csl`, compile/runtime config, and receipts for Cerebras tools.
- Two preservation labels:
  - **source identity preserved:** same Doppler contract.
  - **kernel body preserved:** axes, bindings, reductions, body ops, and
    symbol bindings survive lowering where TSIR/HostPlan covers the kernel.

## Visual spec

- Layout: three equal columns.
- Doppler column uses `doppler.red`; Doe column uses `doe.blue` with
  `doe.purple` for receipt/parity plumbing; Cerebras column uses
  `cerebras.orange` and `cerebras.charcoal`.
- Draw two thick arrows:
  - Doppler -> Doe: label `same raw JS/WGSL + manifest identity`.
  - Doe -> Cerebras: label `same program lowered to CSL + receipts`.
- Add a small side note in the Doe column: `Other Doe backends continue through
  WGSL IR -> MSL/SPIR-V/DXIL/native. Not this slice.`

## Scope guard

- Do not imply TSIR is Doe's only IR.
- Do not imply Cerebras is a WebGPU backend. This is a retargeting path.
- Do not imply Doe authors the model. Doppler owns the source contract.

## Evidence sources

- `docs/csl-architecture.md` - source contract and CSL slice boundary.
- `runtime/zig/README.md` - Doe GPU backend and DXIL/MSL/SPIR-V context.
- `docs/doppler-ingest.md` - Doppler ingest boundary.
