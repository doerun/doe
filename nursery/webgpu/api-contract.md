# @simulatte/webgpu API Contract

Contract version: `v1`

Scope: current headless WebGPU package contract for Node.js and Bun, with a
default `full` surface, an explicit `compute` subpath, and the Doe API / Doe
routines surface used by benchmarking, CI, and artifact-backed comparison
workflows.

Terminology in this contract is explicit:

- `Doe runtime`
  the Zig/native WebGPU runtime underneath the package
- `Doe API`
  the explicit JS convenience surface under `doe.bind(...)`, `gpu.buffers.*`,
  `gpu.compute.run(...)`, and `gpu.compute.compile(...)`
- `Doe routines`
  the narrower, more opinionated JS flows layered on that same runtime;
  currently `gpu.compute.once(...)`

For the current `compute` vs `full` support split, see
[`./support-contracts.md`](./support-contracts.md).

Exact type and method shapes live in:

- [`./src/full.d.ts`](./src/full.d.ts)
- [`./src/compute.d.ts`](./src/compute.d.ts)
- [`./src/doe.d.ts`](./src/doe.d.ts)

This contract covers package-surface GPU access, provider metadata, and helper
entrypoints. It does not promise DOM/canvas ownership or browser-process
parity.

## API styles

The current package surface is organized around three API styles:

- `Direct WebGPU`
  raw `requestAdapter(...)`, `requestDevice(...)`, and direct `device.*` usage
- `Doe API`
  the package's explicit JS convenience surface under `doe.bind(...)`,
  `gpu.buffers.*`, `gpu.compute.run(...)`, and `gpu.compute.compile(...)`
- `Doe routines`
  the package's more opinionated precomposed flows; currently
  `gpu.compute.once(...)`

## Export surfaces

### `@simulatte/webgpu`

Default package surface.

Contract:

- headless `full` surface
- includes compute plus render/sampler/surface APIs already exposed by the Doe runtime package surface
- also exports the shared `doe` namespace for the Doe API and Doe routines surface

### `@simulatte/webgpu/compute`

Compute-first package surface.

Contract:

- sized for AI workloads and other buffer/dispatch-heavy headless execution
- excludes render/sampler/surface methods from the public JS facade
- also exports the same `doe` namespace for the Doe API and Doe routines surface

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

- provides the `Doe API` and `Doe routines` surface for common headless
  compute tasks
- the exported `doe` namespace is the JS convenience surface, distinct from
  the underlying Doe runtime
- `requestDevice(options?)` resolves the package-local `requestDevice(...)` and returns
  the bound helper object directly
- supports both static helper calls and `doe.bind(device)` for device-bound workflows
- helper methods are grouped under `buffers.*` and `compute.*`
- `buffers.*`, `compute.run(...)`, and `compute.compile(...)` are the main
  `Doe API` surface
- `compute.once(...)` is the first `Doe routines` path and stays intentionally
  narrow: typed-array/headless one-call execution, not a replacement for
  explicit reusable resource ownership
- infers `compute.run(...).bindings` access from Doe helper-created buffer usage when that
  usage maps to one bindable access mode (`uniform`, `storageRead`, `storageReadWrite`)
- `compute.once(...)` accepts Doe usage tokens only; raw numeric WebGPU usage flags stay on
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

## Non-goals in v1

1. Full browser-parity WebGPU JS object model emulation.
2. Browser presentation parity.
3. npm `webgpu` drop-in compatibility guarantee.
