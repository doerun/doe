# 16 - Evidence ledger: "What backs the story"

## Purpose

Turn the deck from narrative into a checklist. Every externally sent deck must
render this slide from the bundle being sent.

## Slide content

Required rows for a Gemma 4 31B-first send:

| Row | Claim | Evidence source |
|---|---|---|
| Doppler contract | raw JS/WGSL, manifest, weights, tokenizer, prompt identity | Program Bundle |
| WebGPU reference | same contract runs on the reference surface | WebGPU transcript |
| Doe lowering | same contract emits HostPlan, compile targets, CSL artifacts | HostPlan bundle |
| CSL bounded run | smoke-shape or bounded prefill/decode executes under SDK/simfabric | CSL receipt |
| KV/decode | `kv_write`, `kv_read`, logits, sample, token IDs are executed or explicitly blocked | decode receipt or typed blocker |
| Cerebras hardware | WSE run succeeds or returns a typed hardware blocker | hardware receipt |
| Parity bind | comparable receipts point to the same identity chain | parity receipt |

Current deck versions may include expected rows, but expected rows must be
visually separated from in-hand rows.

## Visual spec

- One ledger table.
- In-hand rows use solid border.
- Expected-before-send rows use dashed border.
- Blocked rows use `contrast.gray` and a short blocker code.
- Doppler cells use `doppler.red`; Doe cells use `doe.blue`/`doe.purple`;
  Cerebras cells use `cerebras.orange`.

## Scope guard

- Do not say "done" unless the artifact exists in the bundle being sent.
- Do not hide missing KV/decode behind a structural emitter claim.
- Do not cite stale receipts without the bundle pointer/version.

## Evidence sources

- `docs/cerebras-evidence-bundle.md`
- `docs/cerebras-evidence-bundle-pointer.md`
- `docs/status/cerebras-csl.md`
- `bench/out/overnight/`
- `bench/out/r3-1-31b-l61-smoke/trace.json`
