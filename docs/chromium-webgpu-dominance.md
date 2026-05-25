# Chromium WebGPU dominance strategy

## Purpose

Doe's flagship strategic target is to become the best open-source WebGPU
implementation path for Chromium-family browsers.

That is an engineering target, not a current claim. The path is to beat the
incumbent Dawn/Tint stack on claimable compiler, runtime, and browser-lane
evidence while keeping Chromium changes isolated to WebGPU integration
boundaries.

## Goal hierarchy

1. Beat Tint on the shader compiler surfaces that matter for WebGPU adoption:
   WGSL parsing, semantic validation, IR lowering, backend emission,
   robustness transforms, diagnostics, and reproducible compiler receipts.
2. Beat Dawn on runtime surfaces that matter to browser and AI workloads:
   pipeline creation, buffer upload, command encoding, queue submission,
   readback, cache behavior, concurrency, and tail stability.
3. Run as a forced Doe runtime inside a Chromium-family browser at the
   `navigator.gpu` seam with hidden fallback disabled and failure reasons
   recorded as artifacts.
4. Turn browser runtime identity into a product advantage: developers should
   see which runtime compiled and executed a workload, what IR/backend path ran,
   why a fallback or failure occurred, and which receipt supports the claim.

## Why Dawn and Tint are the real targets

Dawn is the runtime that Chromium depends on for WebGPU. Tint is Dawn's shader
compiler. A Chromium WebGPU win is therefore not just "Doe faster than Dawn" on
one benchmark row. It requires a linked stack:

- Doe compiler evidence against Tint.
- Doe runtime evidence against Dawn.
- Browser integration evidence at Chromium's WebGPU seam.
- Compatibility evidence that prevents a faster path from becoming a weaker
  implementation.
- Receipts that make every claim replayable.

The browser wrapper in `packages/doe-gpu/src/browser.js` does not satisfy this
target. It delegates to the browser's incumbent WebGPU implementation. The real
browser target lives in `browser/chromium/`.

## Engineering principles

1. Evidence before slogans.
2. Strict Dawn/Tint comparability before performance claims.
3. No hidden fallback in claim lanes.
4. Keep Dawn available as an explicit compatibility fallback until gates say
   otherwise.
5. Keep Chromium fork delta small and WebGPU-focused.
6. Do not replace browser sandbox, process, layout, media, or accessibility
   policy with Doe logic.
7. Prefer source-preserving diagnostics, IR receipts, and replay artifacts over
   opaque pass/fail output.

## Workstreams

### Compiler: Doe vs Tint

The compiler lane should measure Doe's WGSL pipeline against Tint under matched
contracts:

- representative WGSL corpora from browser, canvas, WebGPU samples, model
  inference, and game-engine shaders
- parse/sema/lower/emit phase timing where both sides can expose comparable
  boundaries
- output validation for MSL, SPIR-V, and DXIL/HLSL paths
- robustness transform coverage and failure taxonomy
- diagnostics quality for invalid shaders
- IR receipt output that binds source hash, IR hash, backend output hash, and
  validation result

Compiler wins are only useful when generated output remains spec-compatible.
The priority is not "smaller compiler"; it is a smaller compiler that emits
valid code, explains failures, and gives the browser path less hidden runtime
work.

The claim boundary for this lane is now schema-backed by
[`config/tint-compiler-evidence.schema.json`](../config/tint-compiler-evidence.schema.json)
and gated by
[`bench/gates/tint_compiler_evidence_gate.py`](../bench/gates/tint_compiler_evidence_gate.py).
A report can be diagnostic while the lane is still collecting comparable Tint
phase timing and validation receipts; `claimStatus=claimable` requires every
row to carry comparable Doe and Tint compiler evidence.

### Runtime: Doe vs Dawn

The runtime lane should keep using strict compare policy from
[`performance-strategy.md`](./performance-strategy.md):

- matched workload contracts
- operation-scope timing consistency
- structural work equivalence
- explicit cache and warm/cold configuration
- comparable setup, encode, submit, wait, and readback boundaries
- positive tails before promoted speed claims
- artifact-backed claimability status

Browser-relevant workloads include upload-heavy canvases, compute dispatch,
pipeline creation, model warmup, readback, concurrent queue pressure, and
small frequent command streams.

### Browser: Chromium WebGPU lane

The browser lane should prove forced-Doe behavior before claiming replacement:

- runtime selector with explicit Doe, Dawn, and fallback states
- hidden fallback disabled in claim mode
- browser-level WebGPU tests and CTS subsets
- canvas and presentation-path probes
- external texture and media-path probes
- ORT/browser model workloads
- Playwright artifacts with runtime identity, trace metadata, and failure
  taxonomy
- crash/hang/error parity checks against the Dawn fallback lane

The target is not to rewrite the browser. The target is to replace the WebGPU
runtime seam so every browser subsystem that routes through WebGPU can benefit
without Doe owning unrelated Chromium subsystems.

### Developer product surface

Doe should make the runtime visible in ways Dawn does not:

- runtime identity in browser-lane diagnostics
- shader source to IR to backend output links
- cache hit/miss and pipeline creation receipts
- unsupported-capability explanations
- compatibility fallback reasons
- trace/replay pointers for benchmark and bug reports

This is part of the browser strategy. The best implementation is not only
faster; it is more inspectable when it fails.

## Claim boundaries

Allowed claims when artifacts support them:

- Doe is faster than Dawn on a named workload row with claimable compare
  evidence.
- Doe's compiler is faster or more diagnostic than Tint on a named compiler
  corpus with comparable compiler receipts.
- The Chromium lane ran a named WebGPU workload through forced Doe with hidden
  fallback disabled.
- A browser-lane artifact proves runtime identity, failure reason, and trace
  continuity for a named workload.

Not allowed:

- Doe has already replaced Chromium WebGPU.
- Doe is faster than Dawn globally.
- Doe is more correct than Dawn/Tint without CTS, differential, or
  replay-backed evidence.
- The browser wrapper proves Doe browser execution.
- Chromium fork changes outside WebGPU integration count as Doe progress.

## Current repo routing

- Strategy and claim boundary: this document and [`thesis.md`](./thesis.md).
- Browser integration layer: [`../browser/chromium/`](../browser/chromium/README.md).
- Browser lane overview: [`browser-lane.md`](./browser-lane.md).
- Compiler architecture: [`shader-compiler-architecture.md`](./shader-compiler-architecture.md).
- Runtime performance methodology: [`performance-strategy.md`](./performance-strategy.md).
- Status routing: [`status.md`](./status.md).
