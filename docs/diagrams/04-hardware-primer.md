# 04 - Execution surfaces: "Browser, simfabric, wafer"

## Purpose

Define the icons and colors used for execution surfaces.

## Slide content

- **WebGPU reference:** browser tab + workgroup grid. Runs the Doppler/Doe
  reference path.
- **Doe CSL simfabric:** PE-grid program under Cerebras SDK simulator. Useful
  for bounded evidence and typed blockers.
- **Cerebras WSE:** wafer + ROI + hardware receipt. This is the validation
  target.

## Visual spec

- Three columns.
- WebGPU icon: `doe.blue` browser/workgroup outline.
- Simfabric icon: `doe.purple` runner box feeding a `cerebras.orange` PE grid.
- Hardware icon: `cerebras.charcoal` wafer outline with `cerebras.orange` ROI.
- Captions:
  - `WebGPU reference`
  - `CSL simfabric`
  - `Cerebras WSE hardware`

## Scope guard

- Do not imply simfabric is hardware.
- Do not imply WSE implements WebGPU.
- Do not imply the icons are topology-accurate.

## Evidence sources

- `docs/csl-architecture.md`
- `runtime/zig/tools/csl_sdk_driver.py`
- `bench/runners/csl-runners/`
