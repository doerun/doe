# Nursery

`nursery/` has four separate roles:

1. `webgpu/`
   - package surface for `@simulatte/webgpu`
   - packages the Doe runtime for Node.js and Bun and exposes raw WebGPU plus
     the Doe API / Doe routines JS surface
   - Node addon-backed runtime path, Bun platform-split runtime path (FFI on
     Linux, full/addon-backed on macOS), prebuild packaging
2. `webgpu-doe/`
   - standalone package surface for `@simulatte/webgpu-doe`
   - helper-only extraction of the Doe API namespace
   - no runtime transport; meant to bind to `@simulatte/webgpu` or another
     compatible raw WebGPU-like device source
3. `fawn-browser/`
   - browser integration layer for Chromium work
   - repo-local docs, contracts, helper scripts, and diagnostic harnesses
   - not the Chromium checkout/build workspace itself
4. `chromium_webgpu_lane/`
   - Chromium checkout/build lane workspace
   - large source tree, build outputs, and browser artifacts driven by the browser integration layer

Relationship:

1. `webgpu/` is the headless runtime package surface.
2. `webgpu-doe/` is the helper-only package extracted from that surface.
3. `fawn-browser/` is the control/documentation layer.
4. `chromium_webgpu_lane/` is the actual Chromium workspace it drives.

Terminology:

- `Doe runtime` means the Zig/native WebGPU runtime underneath Fawn
- `Doe API` / `Doe routines` mean the JS convenience layers exposed by
  `nursery/webgpu/` and `nursery/webgpu-doe/`
