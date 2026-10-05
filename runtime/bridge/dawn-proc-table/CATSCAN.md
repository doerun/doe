# CATSCAN: Dawn proc-table adapter

Parent: [Runtime](../../CATSCAN.md)

## Target

Adapt one pinned Dawn C proc-table ABI to Doe's independently owned native
WebGPU entrypoints for external consumer integration.

## Authority

- Owns proc-table construction, ABI admission, native library lifetime and
  explicit rejection at this bridge.
- Does not own ONNX operators, browser policy, runtime optimization or claims.

## Scope

- Includes this directory; the external application harness owns generation,
  source preparation, physical execution and evidence.

## Contracts

- Inputs: generated headers from the consumer's pinned Dawn revision and Doe's
  [pinned WebGPU header](../../zig/vendor/webgpu-headers/webgpu.h).
- Outputs: an explicitly initialized, process-owned table and call observations.

## Invariants

- ABI layouts and values are verified before table publication.
- Native function addresses come from the selected library's exports.
- Rebinding a live table is rejected. The library remains loaded until the
  process exits; no borrowed GPU objects are transferred between providers.
- Unsupported procs and descriptor chains fail explicitly, without fallback.

## Acceptance

- The [external consumer harness](../../../bench/external-projects/onnx-webgpu-substitution/README.md)
  retains library, generated ABI, source, output and failure identities.
- Evidence: [`verify_adapter.py`](../../../bench/external-projects/onnx-webgpu-substitution/verify_adapter.py).

## Non-goals

- Universal Dawn extension compatibility or switching existing live devices.

## Freedom

Implementation freedom requires these boundaries and acceptance evidence.
