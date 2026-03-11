# @simulatte/webgpu API Contract

Contract version: `v1`

Scope: current headless WebGPU package contract for Node.js and Bun, with a
default `full` surface, an explicit `compute` subpath, and Doe runtime helpers
used by benchmarking, CI, and artifact-backed comparison workflows.

For the current `compute` vs `full` support split, see
[`./support-contracts.md`](./support-contracts.md).

This contract covers package-surface GPU access, provider metadata, and helper
entrypoints. It does not promise DOM/canvas ownership or browser-process
parity.

## Export surfaces

### `@simulatte/webgpu`

Default package surface.

Contract:

- headless `full` surface
- includes compute plus render/sampler/surface APIs already exposed by the package runtime
- also exports the `doe` ergonomic namespace

### `@simulatte/webgpu/compute`

Compute-first package surface.

Contract:

- sized for AI workloads and other buffer/dispatch-heavy headless execution
- excludes render/sampler/surface methods from the public JS facade
- also exports the same `doe` ergonomic namespace

## Shared runtime API

Modules:

- `@simulatte/webgpu`
- `@simulatte/webgpu/compute`

### `create(createArgs?)`

Input:

- `createArgs?: string[]` (currently ignored by the default Doe-native provider)

Behavior:

- loads the Doe-native N-API addon and `libwebgpu_doe`
- returns a GPU object backed by the in-tree Doe provider

Output:

- `GPU` object with `requestAdapter(...)`

### `globals`

Output:

- provider globals object suitable for `Object.assign(globalThis, globals)`

### `setupGlobals(target?, createArgs?)`

Input:

- `target?: object` (default: `globalThis`)
- `createArgs?: string[]`

Behavior:

- installs provider globals if missing
- installs `navigator.gpu` if missing

Output:

- `GPU` object

### `requestAdapter(adapterOptions?, createArgs?)`

Output:

- `Promise<GPUAdapter | null>`

### `requestDevice(options?)`

Input:

- `options.adapterOptions?: object`
- `options.deviceDescriptor?: object`
- `options.createArgs?: string[]`

Output:

- `Promise<GPUDevice>`

On `@simulatte/webgpu/compute`, the returned device is a compute-only facade:

- buffer / bind group / compute pipeline / command encoder / queue methods are available
- render / sampler / surface methods are intentionally absent from the facade

### `providerInfo()`

Output object:

- `module: string`
- `loaded: boolean`
- `loadError: string`
- `defaultCreateArgs: string[]`
- `doeNative: boolean`
- `libraryFlavor: string`
- `doeLibraryPath: string`
- `buildMetadataSource: string`
- `buildMetadataPath: string`
- `leanVerifiedBuild: boolean | null`
- `proofArtifactSha256: string | null`

Behavior:

- reports package-surface library provenance when prebuild metadata or Zig build
  metadata is available
- does not guess: if metadata is unavailable, `leanVerifiedBuild` is `null`

### `doe`

Output object:

- `bind(device)`
- `createBuffer(device, options)`
- `createBufferFromData(device, data, options?)`
- `readBuffer(device, buffer, TypedArray, options?)`
- `runCompute(device, options)`
- `compileCompute(device, options)`

Behavior:

- provides an ergonomic JS surface for common headless compute tasks
- supports both static helper calls and `doe.bind(device)` for device-bound workflows
- infers `runCompute(...).bindings` access from Doe helper-created buffer usage when that
  usage maps to one bindable access mode (`uniform`, `storage-read`, `storage-readwrite`)
- fails fast for bare bindings that do not carry Doe helper usage metadata or whose
  usage is non-bindable/ambiguous; callers must pass `{ buffer, access }` explicitly
- additive only; it does not replace the raw WebGPU-facing package API

### `createDoeRuntime(options?)`

Input:

- `options.binPath?: string`
- `options.libPath?: string`

Output object:

- `binPath: string`
- `libPath: string | null`
- `runRaw(args: string[], spawnOptions?): RunResult`
- `runBench(options: BenchOptions): BenchResult`

`BenchOptions`:

- `commandsPath: string` (required)
- `quirksPath?: string`
- `vendor?: string`
- `api?: string`
- `family?: string`
- `driver?: string`
- `traceJsonlPath?: string`
- `traceMetaPath?: string`
- `uploadBufferUsage?: string`
- `uploadSubmitEvery?: number`
- `queueWaitMode?: string`
- `queueSyncMode?: string`
- `extraArgs?: string[]`

`RunResult`:

- `ok: boolean`
- `exitCode: number`
- `stdout: string`
- `stderr: string`
- `signal: string | null`
- `command: string[]`

`BenchResult` extends `RunResult` with:

- `traceJsonlPath: string | null`
- `traceMetaPath: string | null`
- `traceMeta: object | null`

### `runDawnVsDoeCompare(options)`

Input:

- `repoRoot?: string`
- `compareScriptPath?: string`
- `pythonBin?: string`
- `configPath?: string`
- `outPath?: string`
- `extraArgs?: string[]`
- `env?: Record<string, string>`

Behavior:

- wraps `bench/compare_dawn_vs_doe.py`
- requires either `configPath` or `--config` in `extraArgs`

Output:

- `RunResult`

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
