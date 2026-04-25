# 17 - Forward path: "Evidence gets easier after the first contract"

## Purpose

Close with the practical ask: once Doppler emits the contract, Doe can keep
refreshing evidence without redesigning the model path.

## Slide content

- Bottom: complete Doppler contract for Gemma 4 31B.
- Middle: Doe re-emits HostPlan, CSL, and receipts from that identity.
- Top: Cerebras validation path:
  - Path A: endpoint access, Doe runs with `--cmaddr`.
  - Path B: Cerebras-assisted bundle run, Cerebras returns receipt.
- Final node: parity or typed blocker tied to the same identity chain.

## Visual spec

- Bottom-up DAG.
- Doppler contract node uses `doppler.red`.
- Doe lowering/evidence node uses `doe.blue` and `doe.purple`.
- Cerebras validation node uses `cerebras.orange` and `cerebras.charcoal`.
- Identity hash spine uses `accent.gold` from bottom to top.

## Scope guard

- Do not promise a timeline.
- Do not imply both Cerebras paths are equally available.
- Do not imply the first hardware receipt ends all work; it starts the durable
  refresh loop.

## Evidence sources

- `docs/cerebras-north-star.md`
- `docs/cerebras-evidence-bundle.md`
- `runtime/zig/tools/csl_sdk_driver.py`
