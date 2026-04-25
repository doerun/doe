# 13 - Bundle: "One contract, three receipts"

## Purpose

Show why evidence can be refreshed cheaply: a new Doppler contract is enough to
recreate the Doe lowering and rerun the receipts.

## Slide content

- Center: Doppler Program Bundle with manifest, raw JS, raw WGSL, weights,
  tokenizer/input, and reference metadata.
- Three receipt surfaces:
  - WebGPU reference transcript.
  - Doe CSL/simfabric bounded transcript.
  - Cerebras hardware receipt.
- Bottom: parity/binding tool compares receipts only when identities match.

## Visual spec

- Center tarball in `doppler.red` with `accent.gold` hash badges.
- WebGPU/Doe receipt column uses `doe.blue`.
- Simfabric/runner plumbing uses `doe.purple`.
- Cerebras hardware column uses `cerebras.orange` and `cerebras.charcoal`.
- Draw all arrows from the same bundle, not from separate model boxes.

## Scope guard

- Do not imply all receipts are numerically identical without parity binding.
- Do not imply simfabric equals hardware.
- Do not claim hardware success unless slide 16 names a hardware receipt.

## Evidence sources

- `docs/cerebras-evidence-bundle.md`
- `docs/cerebras-evidence-bundle-pointer.md`
- `bench/tools/pack_cerebras_validation_archive.py`
- `bench/tools/bind_shared_execution_parity.py`
