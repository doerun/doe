# Experimental demos

`demos/` contains experimental or diagnostic sample applications.

Current demos:

- `demos/doe-status-dashboard/`
  - Project-wide readiness table that links artifacts for browser runtimes,
    backend equivalence, CSL simulator parity, E2B and 31B receipts,
    Doppler-equivalent diagnostics, hardware blockers, and companion dashboard
    entry points for reviewers checking feature status.
- `demos/gemma4-e2b-csl-sim/`
  - Side-by-side cockpit for Gemma 4 E2B, showing Doppler reference, Doe CSL
    simfabric, WebGPU emulator, evidence ladder, claim scope, manifest-shape
    oracle, parity blockers, and hardware readiness without granting
    unsupported claims during demo reviews.
- `demos/doe-sdk-gui-viewer/`
  - Cerebras SDK-style spatial compute viewer for inspecting fabric topology,
    PE grids, routes, colors, source regions, instruction timelines, wavelet
    movement, host streams, evidence overlays, bundle commands, and failure
    state during CSL debugging sessions.
- `demos/volume-render`
  - local package-backed volume rendering demo for manual exploration
- `demos/service-worker-compute`
  - service-worker compute sample host
- `demos/canvas-stress`
  - browser-hosted 2D canvas stress test rendering 10,000+ animated
    rounded-rectangle SDF primitives in a single instanced draw
- `demos/gaussian-splat-viewer`
  - browser-hosted 3D Gaussian splatting viewer; loads a `.splat`
    binary and renders millions of 3D gaussians per frame through
    `doe-gpu`

This directory is repo-only and non-canonical:

- demos are not public package contracts
- demos are not runtime support commitments
- installed dependency trees such as `node_modules/` must not be checked in

If a demo becomes an actively supported surface, promote it explicitly in
[`config/tool-surfaces.json`](../config/tool-surfaces.json) and add durable docs
for its workflow and ownership.
