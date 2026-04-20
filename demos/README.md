# Experimental demos

`demos/` contains experimental or diagnostic sample applications.

Current demos:

- `demos/doe-status-dashboard/`
  - high-level status rollup of Doe lane statuses, driven from
    `bench/out/` JSON at view time. Static, no server required.
    Cross-links to the two Gemma-4 demos below.
- `demos/gemma4-e2b-csl-sim/`
  - Gemma 4 E2B layer-block side-by-side: browser WebGPU (via Dawn)
    + stored/live CSL simfabric + CSL-WebGPU-emulator, with an
    evidence cockpit (program identity, emulator-vs-simfabric
    speed, per-layer accuracy, real-weight promotion badges).
    Has `server.py` for live CSL runs + the two `/api` routes the
    SDK-GUI viewer depends on.
- `demos/doe-sdk-gui-viewer/`
  - Browser facsimile of the Cerebras SDK GUI shape: work-directory
    bar, route/color selector, scalable fabric viewport, PE drilldown,
    instruction/source/wavelet timeline panes, debug pane, timeline
    navigation controls, and terminal/exported commands. Point it at
    a compile artifact dir under
    `bench/out/scratch/gemma4-e2b-csl-sim/compile-L<N>` to inspect
    metadata without unpacking SDK binaries. Requires the E2B demo
    server running on the same origin for its `/api` routes.
    Has a "redact paths" toggle for screen-share-safe mode:
    hides local filesystem path bytes, keeps hashes + verdicts
    and the evidence-bundle step rollup visible.
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
