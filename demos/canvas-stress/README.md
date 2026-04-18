# Doe canvas stress demo

Browser-hosted 2D canvas stress test rendered through Doe's WebGPU runtime.
Draws 10,000+ animated rounded-rectangle primitives with per-primitive SDF
antialiasing in a single instanced draw call.

## Run

```
cd demos/canvas-stress
npm install
npx vite
```

Open the reported URL in a WebGPU-capable browser.

## What it does

- 10,000 rounded rectangles with per-instance position, size, rotation, corner
  radius, hue, and opacity
- animation driven by a single time uniform; the vertex shader advects each
  primitive in a stable low-frequency curl field
- SDF fragment shader produces smooth antialiased edges at any resolution
- single render pipeline, single draw call, no CPU per-frame allocation

## Status

Demo-only. Not a public package contract, not covered by the Doe runtime
support matrix. If promoted to an active surface, register in
`config/tool-surfaces.json`.
