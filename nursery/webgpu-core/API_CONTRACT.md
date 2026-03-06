# @simulatte/webgpu API Contract

Contract version: `v1`

Scope: browserless benchmarking and CI orchestration for Doe runtime workflows.

## Node runtime API

Module: `@simulatte/webgpu` (Node default export target)

### `create(createArgs?)`

Input:

- `createArgs?: string[]` (provider-specific options)

Behavior:

- loads in-process provider module from `FAWN_WEBGPU_NODE_PROVIDER_MODULE` (default: `webgpu`)
- calls provider `create(createArgs)` and returns GPU object

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
