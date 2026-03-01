# Compatibility Scope: what we actually need

This note narrows optional parity work to concrete integration value.

## Required now

1. Stable command/trace orchestration for benchmark and CI pipelines.
2. Reliable wrappers for:
- Doe native bench runs
- Dawn-vs-Doe compare runs
3. Deterministic artifact paths and non-zero exit-code propagation.

## Optional later (only when demanded by integrations)

1. Minimal compute-only compatibility shim:
- enough API shape for specific Node consumers that need `requestAdapter`/`requestDevice`.
2. Minimal constants compatibility:
- only constants required by real integrations, not full WebGPU enum surface.

## Not planned by default

1. Full `navigator.gpu` browser-parity behavior in Node.
2. Full object lifetime/event parity (`device lost`, full error scopes, full mapping semantics).
3. Broad drop-in support for arbitrary npm packages expecting complete `webgpu` behavior.

Decision rule:

- Add parity features only after a concrete integration requirement is blocked by a missing capability and cannot be addressed by the existing bridge/CLI contract.
