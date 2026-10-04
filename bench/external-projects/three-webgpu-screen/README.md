# Three.js WebGPU application screen

Repo-only screening of the pinned upstream fog-scattering application. The
[plan](screen.json) freezes acquisition, browser environment, trial order and
stopping. [Runner](run-screen.mjs) observes generated shaders and the engine's
existing timestamps without rewriting the shader graph. [Analyzer](analyze-screen.mjs)
verifies retained byte parity and native-family counts, excludes cached and
incomplete timestamp sets, and computes paired A/A diagnostics.

See the [retained report](../../../reports/browser-compiler/20261004/three-screen/README.md)
for reproduction, failure, hardware, timing limitations and disposition.
The screen is closed without a worthwhile automatic transformation. It does
not establish application adoption or accelerate the upstream engine.
