# Gemma 4 + Doe + Cerebras hardware validation appendix

Compatibility governance document for the evidence bundle and claim gate.
Operational commands, setup, receipt fields, publication boundaries, and the
operator email live in [`cerebras-hardware-runbook.md`](cerebras-hardware-runbook.md).

This file intentionally remains at this path because the evidence-bundle
packer, verifier, prepack fingerprint guard, and claim-discipline gate depend
on it.

## Attached bundle

Current archive filename, sha256s, size, git commit, and verification commands
are auto-refreshed into
[`cerebras-evidence-bundle-pointer.md`](cerebras-evidence-bundle-pointer.md)
by `bench/tools/prepare_cerebras_validation_bundle.sh`.

The archive's own `BUNDLE_META.json` is always the authoritative source of
truth for any bundle in hand.

## Target order

The first hardware validation target is Gemma 4 31B dense through the af16
full-prompt HostPlan runner. Qwen 3.6 27B is the companion hybrid architecture
lane. Gemma 4 E2B remains a smaller control fixture and regression lane.
Gemma 4 26B/A4B MoE remains a later efficiency lane with separate MoE-specific
receipts.

Do not claim full 31B parity from smoke-shape, selected-logit, or synthetic
receipts. Full 31B hardware parity requires a returned hardware transcript
plus a Doppler reference export bound to the same manifest, execution graph,
weights, and input set.

## Hardware validation paths

The runbook gives the exact commands. The two allowed execution paths are:

- **Path A — endpoint access.** Cerebras provides a reachable CS/WSC endpoint;
  the Doe operator runs the wrapper with `--cmaddr <endpoint>`.
- **Path B — Cerebras-assisted bundle run.** A Cerebras engineer checks out the
  bundle commit, verifies the archive, runs the same commands internally, and
  returns the receipt artifacts. Nothing from the Doe side has to execute on
  Cerebras infrastructure.

## Receipt scope

A useful returned receipt records:

- redacted endpoint or appliance identity
- SDK version and device architecture
- compile/run status
- generated-token IDs when token output is reached
- logits or output digests when returned
- blocker taxonomy and last phase reached when the run fails closed
- manifest, source graph, HostPlan, compile target inventory, weight identity,
  and tokenized prompt identity
- explicit claim scope for what the receipt does and does not prove

## Publication boundary

Per [`claim-discipline.md`](claim-discipline.md), without the endpoint
provider's explicit approval we will not publish:

- hardware timing beyond what the endpoint operator authorizes
- endpoint identity, IP, physical location, rack, or appliance IDs
- queue-depth, fabric-level, or operator-internal telemetry surfaced in SDK logs
- performance claims beyond the returned parity receipt's own scope
- comparisons against other hardware unless the methodology is jointly signed
  off

The public claim scope remains portability and parity, not speed.

## Where to look first

- Lane front door: [`cerebras.md`](cerebras.md)
- Hardware runbook: [`cerebras-hardware-runbook.md`](cerebras-hardware-runbook.md)
- Model ledgers: [`cerebras-model-ledgers.md`](cerebras-model-ledgers.md)
- Claim discipline: [`claim-discipline.md`](claim-discipline.md)
- Status shard: [`status/cerebras-csl.md`](status/cerebras-csl.md)
