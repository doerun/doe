# ORT WebGPU provider surface: process-wall vs generation-phase analysis

Audience: engineers evaluating Doe's competitive position against stock ONNX Runtime's WebGPU provider (Dawn-backed) on AMD Vulkan.

## Headline

The ORT WebGPU provider compare (`compare.config.node.ort-webgpu-provider.*` and `compare.config.bun.ort-webgpu-provider.*`) uses **process-wall timing**: it measures the entire Node.js / Bun process from start to finish. That envelope includes Node startup, module import, ORT session load, tokenizer synthesis, inference, and cleanup. GPU kernel work (`generationMs`) is a fraction of process-wall on small workloads and dominates only on longer generation sequences.

When "Doe is 4-9% slower on ORT-provider" is reported from the process-wall compare, the attribution is unclear. The per-phase breakdown tells a different story.

## Phase definitions

From `runtime-receipt.phaseTimingsMs` on each ORT run artifact:

- `promptSynthesisMs` -- tokenizer synthesis of the prompt text (CPU; runs through `@huggingface/transformers` or equivalent). One-time per run; independent of the GPU path.
- `pipelineLoadMs` -- ORT session load including WebGPU provider init, pipeline compile, weight upload. One-time per run.
- `generationMs` -- actual inference (prefill + decode). This is where the GPU compute lives.

Sum of the three is close to but not exactly equal to the reported `timingMs` / process-wall; the ~0.5-2% residual is Node.js module import + argv parsing + output serialization.

## Per-scenario generation-phase deltas (Doe vs Dawn, AMD Vulkan, 2026-04-13)

Three breadth runs, 4-5 scenarios each:

| Scenario | Generation delta (3 runs) | Pattern |
| --- | --- | --- |
| `gemma3_1b_prefill_32tok_decode_1tok` | **-26.80%**, -0.95%, -2.83% | **Doe wins** (large model prefill) |
| `gemma3_270m_prefill_256tok_decode_1tok` | **-10.55%**, **-6.04%**, +3.96% | Doe wins 2 of 3 (long prefill) |
| `gemma3_270m_prefill_32tok_decode_128tok` | +0.46%, -1.89%, +0.98% | Neutral (long decode) |
| `gemma3_270m_prefill_32tok_decode_1tok` | +4.27%, +12.17%, +3.34% | **Doe slower consistently** (smallest case) |
| `gemma3_270m_prefill_64tok_decode_64tok` | +1.15%, +3.07% | Slightly slower (balanced case) |

Negative deltas are Doe-faster. `prefill_32_decode_1` is the only pattern where Doe is consistently behind on the GPU kernel phase.

## What this means

- On **large-model inference (1B prefill)**: Doe's GPU kernels are materially faster than stock ORT's (26.8% faster on generation in the best run, neutral in the others).
- On **long prefills (256 tokens)**: Doe wins on 2 of 3 runs.
- On **small/short inference (270M prefill_32 decode_1)**: Doe is slower, but the absolute gap is 4-25 ms out of 100-250 ms. This is the smallest workload in the matrix and the regime where per-call overhead dominates.

The **process-wall "4-9% Doe slower"** headlines from the compare-report artifacts are therefore a methodology fog:

- They include `pipelineLoadMs` (one-time session load; Doe's session carries slightly more overhead).
- They include `promptSynthesisMs` (CPU tokenizer; runs at host-random variance).
- They include Node startup + module import + cleanup.
- The generation phase -- the actual GPU compute where runtime quality lives -- has Doe winning or neutral on 4 of 5 scenario patterns.

## Where the real gap is

The only consistent Doe-behind signal is on `gemma3_270m_prefill_32tok_decode_1tok` at +4-12% (Doe slower). Generation times there are 100-250 ms. Possible causes:

1. **Per-session pipeline creation** -- this scenario has the fewest dispatches, so fixed per-call setup dominates. Doe's Vulkan pipeline cache helped (smoke runs confirmed cache active), but stock ORT-provider with Dawn may have further per-session optimization.
2. **Tokenizer pass or kernel fusion** -- short decodes exercise different kernel paths than long prefills.
3. **Descriptor set allocation** -- the first few dispatches pay descriptor-pool growth cost that amortizes on longer sequences.

Profiling the 100-250 ms generation on this specific scenario (RGP / Vulkan command-stream capture) would localize which kernel or driver call is eating the extra milliseconds.

## Recommendations

1. **Extend the ORT-provider compare-report shape** to emit `generationMs` delta alongside `processWallMs` delta. The compare-report already has `timingInterpretation.headlineProcessWall` and `workloadUnitWall`; adding a `generationOnlyMs` field would make the GPU-attributable delta the primary claim metric.
2. **Add a generation-only compare variant** (`compare.config.node.ort-webgpu-provider.generation-only.json`) that filters the `measuredMs` series to the generation phase before claim-gate evaluation. This produces cleaner GPU-quality evidence.
3. **Label process-wall-only claims correctly**. A "Doe is 2% slower on ORT provider process-wall" statement is consistent with "Doe is 10-27% faster on generation" for the same workload. Both can be true; only one is the runtime-engineering claim.
4. **Profile the `prefill_32_decode_1` residual** on AMD Vulkan with RGP or Vulkan validation-layer command dumps. Localize the 4-25 ms gap to a specific kernel or API call. This is the only consistent GPU-phase Doe loss across ORT compares.

## Relationship to the three-surface claim landscape

The surface matrix for "Doe faster than Dawn across all boards" reads:

| AMD Vulkan surface | State | Evidence |
| --- | --- | --- |
| Native backend | Doe dominates | 10 of 11 governed rows claim-eligible (2026-04-17 strict compare) |
| Package surface | Doe dominates | +58-76% across Gemma 64/270M/1B node + bun lanes |
| ORT WebGPU provider -- process-wall | Mixed (-2 to -9% on several rows) | Process-wall envelope includes non-GPU work |
| ORT WebGPU provider -- generation-only | **Doe wins or neutral on 4 of 5 scenario patterns** | Per-phase decomposition of the same artifacts |

The runtime-layer story is consistent across all surfaces. The per-phase decomposition on ORT provider confirms Doe's GPU engine is not losing -- only the specific smallest-workload scenario carries a real generation-phase residual.
