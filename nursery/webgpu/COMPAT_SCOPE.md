# Compatibility Scope: what we actually need

This note narrows optional parity work to concrete integration value.

## Required now

1. Stable command/trace orchestration for benchmark and CI pipelines.
2. Reliable wrappers for:
- Doe native bench runs
- Dawn-vs-Doe compare runs
3. Deterministic artifact paths and non-zero exit-code propagation.
4. Minimal in-process provider surface for Node consumers:
- `create(args?)`
- `globals`
- `requestAdapter`/`requestDevice` convenience helpers
- `setupGlobals` for `navigator.gpu` + enum bootstrap

## Optional later (only when demanded by integrations)

1. Minimal constants compatibility:
- only constants required by real integrations, not full WebGPU enum surface.
2. Provider-module swap support for non-default backends beyond `webgpu`.

## Not planned by default

1. Full `navigator.gpu` browser-parity behavior in Node.
2. Full object lifetime/event parity (`device lost`, full error scopes, full mapping semantics).
3. Broad drop-in support for arbitrary npm packages expecting complete `webgpu` behavior.

Decision rule:

- Add parity features only after a concrete integration requirement is blocked by a missing capability and cannot be addressed by the existing bridge/CLI contract.

Layering note:

- this file describes the current package surface and its present non-goals
- proposed future `core` vs `full` support contracts are defined separately in
  `SUPPORT_CONTRACTS.md`
