# bench/executors

Process-level executors that runners hand off to. An executor wraps a
specific runtime host (Node, Bun, browser, native) and emits one
`.run.json` per workload.

Layout:

- `node-webgpu/`, `package-webgpu/`, `vendor-node/` — Node-hosted
  WebGPU executors and their vendored shims.
- `run-browser-ort-bench.py`, `run-bun-tjs-ort-webgpu.js`,
  `run-node-tjs-ort-webgpu.js` — ORT WebGPU EP lane.
- `run-doe-*-choice.js`, `run-doe-stable-token.js` — Doe-side
  deterministic-decode executors used by browser / package compares.
- `harvest-doppler-browser-*.js` — Doppler reference capture from a
  controlled browser session (Playwright-driven).
- `adapter_health.js`, `determinism-trace-meta.js` — pre-run capability
  + determinism probes consumed by the comparability gate.

Executors must report timing in matched phases (setup / encode /
submit_wait) for any compare workload — see CLAUDE.md
non-negotiables #7 (Dawn apples-to-apples) and #11 (timing-scope
completeness).
