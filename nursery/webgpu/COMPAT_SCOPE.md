# Compatibility Scope: what we actually need

This note narrows compatibility work to concrete headless integration value for
the current package surface.

## Required now

1. Stable headless Node/Bun provider behavior for real Doe-native execution.
2. Stable command/trace orchestration for benchmark and CI pipelines.
3. Reliable wrappers for:
- Doe native bench runs
- Dawn-vs-Doe compare runs
4. Deterministic artifact paths and non-zero exit-code propagation.
5. Minimal convenience entrypoints for Node consumers:
- `create(args?)`
- `globals`
- `requestAdapter`/`requestDevice` convenience helpers
- `setupGlobals` for `navigator.gpu` + enum bootstrap

The point of this package is headless GPU work in Node/Bun: compute, offscreen
execution, benchmarking, and CI. Compatibility work should serve those
surfaces first.

## Optional later (only when demanded by integrations)

1. Minimal constants compatibility:
- only constants required by real integrations, not full WebGPU enum surface.
2. Provider-module swap support for non-default backends beyond `webgpu`.

## Not planned by default

1. Full `navigator.gpu` browser-parity behavior in Node.
2. Full object lifetime/event parity (`device lost`, full error scopes, full mapping semantics).
3. Broad drop-in support for arbitrary npm packages expecting complete `webgpu` behavior.

Decision rule:

- Add parity features only after a concrete headless integration is blocked by
  a missing capability and cannot be addressed by the existing package,
  bridge, or CLI contract.

Layering note:

- this file describes the current package surface and its present non-goals
- proposed future `core` vs `full` support contracts are defined separately in
  `SUPPORT_CONTRACTS.md`
