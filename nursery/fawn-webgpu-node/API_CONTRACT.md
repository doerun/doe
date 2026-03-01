# @fawn/webgpu-node API Contract

Contract version: `v1`

Scope: browserless benchmarking and CI orchestration for Doe runtime workflows.

## Node runtime API

Module: `@fawn/webgpu-node` (Node default export target)

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

1. Full in-process WebGPU JS object model parity.
2. Browser presentation parity.
3. npm `webgpu` drop-in compatibility guarantee.
