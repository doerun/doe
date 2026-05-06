# Doe ↔ Cerebras

Index for the Doppler → Doe → Cerebras lane: current status, source locations,
reproduce commands, hardware runbook, bundle pointer, and claim scope.

## Progress at a glance

```bash
python3 bench/tools/cerebras_status_snapshot.py
```

Writes `bench/out/r3-cerebras-status/snapshot.{json,md}`. The snapshot is a
per-lane verdict table built from receipts and carries the current counts.

Live narrative status: [`docs/status/cerebras-csl.md`](status/cerebras-csl.md).
Per-model evidence checklists with acceptance bars and active blocker queues:
[`cerebras-evidence-ledger-gemma.md`](cerebras-evidence-ledger-gemma.md),
[`cerebras-evidence-ledger-qwen.md`](cerebras-evidence-ledger-qwen.md).

## Source code

| Surface | Path |
|---|---|
| TSIR (semantic + planner + emitters) | `runtime/zig/src/tsir/` |
| CSL emit (classifier/template path) | `runtime/zig/src/doe_wgsl/emit_csl_*.zig` |
| Hardware runners (Gemma/Qwen HostPlan + bounded cells) | `bench/runners/csl-runners/` |
| Bundle / verify / status tools | `bench/tools/cerebras_*`, `bench/tools/*evidence*`, `bench/tools/synthesize_*` |
| TSIR architecture plan | [`docs/tsir-lowering-plan.md`](tsir-lowering-plan.md) |
| CSL abstraction stack | [`docs/csl-architecture.md`](csl-architecture.md) |

## Reproduce

| Goal | Command |
|---|---|
| Refresh status snapshot | `python3 bench/tools/cerebras_status_snapshot.py` |
| Build a clean evidence bundle | `bench/tools/prepare_cerebras_validation_bundle.sh` |
| Build an emulator source archive | `python3 bench/tools/pack_cerebras_emulator_source_archive.py` |
| Verify a received bundle archive | `python3 bench/tools/verify_cerebras_validation_archive.py --archive <path>` |
| Summarize an archive without unpacking | `bench/tools/summarize_cerebras_evidence_archive.sh <path>` |
| Verify a returned hardware receipt | `python3 bench/tools/verify_returned_hardware_receipt.py --receipt <path>` |
| Run Gemma full-prompt hardware path | `bench/tools/run_gemma4_31b_af16_hardware_path.sh --cmaddr <endpoint>` |
| Run Qwen full-prompt hardware path | `bench/tools/run_qwen3_6_27b_af16_hardware_path.sh --cmaddr <endpoint>` |
| Run Gemma final-norm selected-logit check | `python3 bench/tools/run_gemma4_31b_af16_doppler_selected_logit_splice.py` |
| Run Qwen final-norm selected-logit check | `python3 bench/tools/run_qwen_3_6_27b_af16_doppler_selected_logit_splice.py` |
| Run blocking gates locally | `python3 bench/runners/run_blocking_gates.py` |

## Run on hardware

Operator runbook: commands, hardware receipt paths, required receipt fields,
publication boundaries, and email text:
[`docs/cerebras-hardware-runbook.md`](cerebras-hardware-runbook.md).

Bundle pointer with archive sha256, pinned commit, and regenerated timestamp:
[`docs/cerebras-evidence-bundle-pointer.md`](cerebras-evidence-bundle-pointer.md).

Bundle source. The packer extracts archive-root files like `README.md`,
`CLAIM_SCOPE.md`, `MODEL_ACCESS.md`, `CEREBRAS_ASK.md`, and
`LOCAL_INSPECTION.md` from marked sections of this file:
[`docs/cerebras-evidence-bundle.md`](cerebras-evidence-bundle.md).

Governance + claim scope: [`docs/hardware-validation-appendix.md`](hardware-validation-appendix.md).

## Why

- Project rationale: [`docs/thesis.md`](thesis.md).
- Practitioner pain points: [`docs/problems-addressed.md`](problems-addressed.md).
- Model target rationale: dense Gemma plus hybrid Qwen, both on the Q4K → f16
  contract. See the public page copy and the per-model ledgers above.

## Scope notes

- Embedded counts (e.g. "23/23 pass"). Run the snapshot.
- Roadmap timing. Status snapshot + evidence ledgers carry current state;
  blockers are named without estimates.
- Internal iteration jargon. Build-iteration vs parity-iteration discipline
  for the TSIR rewrite lives in [`docs/loop-protocol.md`](loop-protocol.md);
  it sits outside the Cerebras lane progress signal.
