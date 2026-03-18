# Chromium Blink merge queue: GPUCanvasContext + GPUExternalTexture (Track A API completion)

## Where these APIs are implemented (lane source)

- Canvas/context contracts: `src/third_party/blink/renderer/modules/webgpu/`
- WebGPU entrypoint glue: same Blink module directory and associated `*_test.cc` tests
- Runtime selection remains unchanged (`src/gpu/*`) and is already wired for Doe path

## Merge-queue implementation order

### 1) Expose preferred canvas format + context creation

1. In `third_party/blink/renderer/modules/webgpu/gpu_canvas_context.idl` add or confirm
   `configure`, `getCurrentTexture`, and related members for Fawn runtime behavior.
2. In `gpu_canvas_context.cc/.h` route the context object through the active proc-table path and
   keep presentation ownership checks against browser process state.
3. In `html_canvas_element.cc` update checks that gate WebGPU context creation under feature/runtime policy.
4. Add/extend `gpu_canvas_context_test.cc` regression asserting non-null context on `getContext('webgpu')`.

### 2) Implement/clarify external texture APIs on device/queue

1. In `gpu_device.idl` ensure `importExternalTexture` shape is present and deterministic.
2. In `gpu_device.cc` and `gpu_queue.idl/.cc` add explicit implementation path to platform import helpers.
3. Add Blink-side validation and `copy_size`/`source` shape guards before calling into runtime procs.
4. Add/extend `webgpu_context_test.cc` and any texture-focused test to lock behavior.
5. Return typed unsupported errors if browser image interop is unavailable on a platform.

### 3) Add probe-contract lock

1. Keep browser harness probe contract unchanged but required:
   - `webgpuCanvasApi.preferredCanvasFormatSupported`
   - `webgpuCanvasApi.webgpuContextAvailable`
   - `webgpuDeviceApi.hasImportExternalTexture`
   - `webgpuDeviceApi.hasCopyExternalImageToTexture`
2. Mark Track A merge gate blocked unless these are either:
   - fully available in Doe/Dawn lanes, or
   - explicitly unsupported with typed reason.

## Merge execution checklist (after symlink target exists)

1. Patch `browser/chromium_webgpu_lane/src` by implementing above files in order 1→2→3.
2. Build lane target:
   - `autoninja -C out/fawn_debug chrome`
3. Run browser smoke/layered superset in both modes.
4. Confirm no regression in legacy API probe lines from `webgpu-playwright-smoke.mjs` and `webgpu-playwright-layered-bench.mjs`.
5. Only then update `docs/status.md` and milestone gate notes to reflect browser API surface completeness.

