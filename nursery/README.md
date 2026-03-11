# Nursery

`nursery/` has three separate roles:

1. `webgpu/`
   - package surface for `@simulatte/webgpu`
   - packages the Doe runtime for Node.js and Bun and exposes raw WebGPU plus
     the Doe API / Doe routines JS surface
   - Node addon-backed runtime path, Bun platform-split runtime path (FFI on
     Linux, full/addon-backed on macOS), prebuild packaging
2. `fawn-browser/`
   - browser integration layer for Chromium work
   - repo-local docs, contracts, helper scripts, and diagnostic harnesses
   - not the Chromium checkout/build workspace itself
3. `chromium_webgpu_lane/`
   - Chromium checkout/build lane workspace
   - large source tree, build outputs, and browser artifacts driven by the browser integration layer

Relationship:

1. `fawn-browser/` is the control/documentation layer.
2. `chromium_webgpu_lane/` is the actual Chromium workspace it drives.
3. `webgpu/` is separate; it is the headless package/runtime surface, not the browser lane.

Terminology:

- `Doe runtime` means the Zig/native WebGPU runtime underneath Fawn
- `Doe API` / `Doe routines` mean the JS convenience layers exposed by
  `nursery/webgpu/`
