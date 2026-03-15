# @simulatte/webgpu API Contract

Contract version: `v1`

Scope: current headless WebGPU package contract for Node.js and Bun, with a
default `full` surface, an explicit `compute` subpath, and the Doe API surface
used by benchmarking, CI, and artifact-backed comparison workflows.

Terminology in this contract is explicit:

- `Doe runtime`
  the Zig/native WebGPU runtime underneath the package
- `Doe API`
  the explicit JS convenience surface under `doe.bind(...)`, `gpu.buffer.*`,
  `gpu.kernel.run(...)`, `gpu.kernel.create(...)`, and `gpu.compute(...)`

For the current `compute` vs `full` support split, see
[`./support-contracts.md`](./support-contracts.md). For scope and non-goals, see
the bottom of this document.

Exact type and method shapes live in:

- [`./src/full.d.ts`](./src/full.d.ts)
- [`./src/compute.d.ts`](./src/compute.d.ts)
- `@simulatte/webgpu-doe` in `src/index.d.ts`

Planned naming cleanup for the Doe helper surface is documented separately in:

- [`./doe-api-design.md`](./doe-api-design.md)

This contract covers package-surface GPU access, provider metadata, and helper
entrypoints. It does not promise DOM/canvas ownership or browser-process
parity.

This is the contract for the current implemented API. It intentionally may
differ from the future helper naming proposed in `doe-api-design.md`.

## API styles

The package surface has two API styles: `Direct WebGPU` (raw
`requestAdapter`, `requestDevice`, `device.*`) and `Doe API` (convenience
surface under `doe.bind(...)`, `gpu.buffer.*`, `gpu.kernel.*`, and the
one-shot `gpu.compute(...)` helper).

For the full layer stack from Zig native to package exports, see
[`./architecture.md`](./architecture.md).

## Export surfaces

| Import | Surface |
|--------|---------|
| `@simulatte/webgpu` | Default full headless surface + `doe` namespace |
| `@simulatte/webgpu/compute` | Compute-first facade + `doe` namespace |

Export paths and transport details are documented in
[`./architecture.md`](./architecture.md).

## Shared runtime API

Modules:

- `@simulatte/webgpu`
- `@simulatte/webgpu/compute`

### Top-level package API

The exact signatures are defined in the `.d.ts` files above. At the contract
level:

- `create(...)` loads the Doe-native addon/runtime and returns a package-local
  `GPU` object.
- `globals` exposes provider globals suitable for `Object.assign(...)` or
  bootstrap wiring.
- `setupGlobals(...)` installs globals and `navigator.gpu` when missing.
- `requestAdapter(...)` and `requestDevice(...)` are the `Direct WebGPU` entry
  points.
- `preflightShaderSource(code)` validates WGSL source before pipeline creation
  and returns structured compilation diagnostics.
- `setNativeTimeoutMs(ms)` sets the native-side timeout for synchronous GPU
  operations (map, flush).

On `@simulatte/webgpu/compute`, the returned device is intentionally
compute-only:

- buffer / bind group / compute pipeline / command encoder / queue methods are available
- render / sampler / surface methods are intentionally absent from the facade

### `providerInfo()`

Behavior:

- reports package-surface library provenance when prebuild metadata or Zig build
  metadata is available
- does not guess: if metadata is unavailable, `leanVerifiedBuild` is `null`
- reports whether the Doe-native path is loaded and where build metadata came from

### `doe`

Behavior:

- provides the `Doe API` surface for common headless compute tasks
- the exported `doe` namespace is the JS convenience surface, distinct from
  the underlying Doe runtime
- `requestDevice(options?)` resolves the package-local `requestDevice(...)` and returns
  the bound helper object directly
- `doe.bind(device)` wraps an existing raw device into the same bound helper object
- helper methods are grouped under the bound helper object's `buffer.*`,
  `kernel.*`, and `compute(...)`
- `buffer.*`, `kernel.run(...)`, and `kernel.create(...)` are the main
  `Doe API` surface
- `gpu.compute(...)` is the more opinionated one-shot helper inside the same
  `Doe API` surface and stays intentionally
  narrow: typed-array/headless one-call execution, not a replacement for
  explicit reusable resource ownership
- infers `kernel.run(...).bindings` access from Doe helper-created buffer usage when that
  usage maps to one bindable access mode (`uniform`, `storageRead`, `storageReadWrite`)
- `compute(...)` accepts Doe usage tokens only; raw numeric WebGPU usage flags stay on
  the more explicit `Doe API` surface
- fails fast for bare bindings that do not carry Doe helper usage metadata or whose
  usage is non-bindable/ambiguous; callers must pass `{ buffer, access }` explicitly
- additive only; it does not replace the raw WebGPU-facing package API

### `createDoeRuntime(options?)`

Behavior:

- returns the local Doe runtime/CLI wrapper used for command-stream execution
  and benchmark orchestration from Node/Bun environments
- preserves explicit file-path ownership for the binary/library location rather
  than hiding them behind package-only assumptions

### `runDawnVsDoeCompare(options)`

Behavior:

- wraps `bench/compare_dawn_vs_doe.py`
- requires either `configPath` or `--config` in `extraArgs`

## CLI contract

### `fawn-webgpu-bench`

Purpose:

- execute Doe command-stream benchmark runs and emit trace artifacts.

### `fawn-webgpu-compare`

Purpose:

- one-command Dawn-vs-Doe compare wrapper from Node tooling.

## Scope and non-goals

This package exists for headless GPU work in Node/Bun: compute, offscreen
execution, benchmarking, and CI. Compatibility work serves those surfaces first.

### Required now

1. Stable headless Node/Bun provider behavior for real Doe-native execution.
2. Stable command/trace orchestration for benchmark and CI pipelines.
3. Reliable wrappers for Doe native bench runs and Dawn-vs-Doe compare runs.
4. Deterministic artifact paths and non-zero exit-code propagation.
5. Minimal convenience entrypoints for Node consumers (`create`, `globals`,
   `requestAdapter`/`requestDevice`, `setupGlobals`).

### Optional later (only when demanded by integrations)

1. Minimal constants compatibility (only constants required by real integrations).
2. Provider-module swap support for non-default backends beyond `webgpu`.

### Not planned

1. Full `navigator.gpu` browser-parity behavior in Node.
2. Full object lifetime/event parity (`device lost`, full error scopes, full mapping semantics).
3. Broad drop-in support for arbitrary npm packages expecting complete `webgpu` behavior.
4. Browser presentation parity.

Decision rule: add parity features only after a concrete headless integration is
blocked by a missing capability and cannot be addressed by the existing package,
bridge, or CLI contract.
