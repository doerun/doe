import type {
  BoundDoeNamespace,
  DoeKernelDispatchOptions,
  DoeNamespace,
  DoeRunComputeOptions,
} from "./doe.js";

export interface ProviderInfo {
  module: string;
  loaded: boolean;
  loadError: string;
  defaultCreateArgs: string[];
  doeNative: boolean;
  libraryFlavor: string;
  doeLibraryPath: string;
  buildMetadataSource: string;
  buildMetadataPath: string;
  leanVerifiedBuild: boolean | null;
  proofArtifactSha256: string | null;
}

export interface DoeRuntimeRunResult {
  ok: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  signal: string | null;
  command: string[];
}

export interface DoeRuntimeBenchResult extends DoeRuntimeRunResult {
  traceJsonlPath: string | null;
  traceMetaPath: string | null;
  traceMeta: Record<string, unknown> | null;
}

export interface DoeRuntimeBenchOptions {
  commandsPath: string;
  quirksPath?: string;
  vendor?: string;
  api?: string;
  family?: string;
  driver?: string;
  traceJsonlPath?: string;
  traceMetaPath?: string;
  uploadBufferUsage?: string;
  uploadSubmitEvery?: number;
  queueWaitMode?: string;
  queueSyncMode?: string;
  extraArgs?: string[];
  cwd?: string;
}

export interface DoeRuntime {
  binPath: string;
  libPath: string | null;
  runRaw(args: string[], spawnOptions?: Record<string, unknown>): DoeRuntimeRunResult;
  runBench(options: DoeRuntimeBenchOptions): DoeRuntimeBenchResult;
}

export interface RequestDeviceOptions {
  adapterOptions?: GPURequestAdapterOptions;
  deviceDescriptor?: GPUDeviceDescriptor;
  createArgs?: string[] | null;
}

export interface FullDoeRunComputeOptions extends DoeRunComputeOptions<GPUBuffer> {}

export interface FullDoeKernelDispatchOptions extends DoeKernelDispatchOptions<GPUBuffer> {}

export interface FullDoeKernel {
  readonly device: GPUDevice;
  readonly entryPoint: string;
  dispatch(options: FullDoeKernelDispatchOptions): Promise<void>;
}

export interface FullBoundDoeNamespace
  extends BoundDoeNamespace<GPUDevice, GPUBuffer, FullDoeKernel, FullDoeRunComputeOptions> {}

export interface FullDoeNamespace
  extends DoeNamespace<
    GPUDevice,
    GPUBuffer,
    FullDoeKernel,
    FullBoundDoeNamespace,
    FullDoeRunComputeOptions,
    RequestDeviceOptions
  > {}

export const globals: Record<string, unknown>;
export function create(createArgs?: string[] | null): GPU;
export function setupGlobals(target?: object, createArgs?: string[] | null): GPU;
export function requestAdapter(
  adapterOptions?: GPURequestAdapterOptions,
  createArgs?: string[] | null
): Promise<GPUAdapter | null>;
export function requestDevice(options?: RequestDeviceOptions): Promise<GPUDevice>;
export function providerInfo(): ProviderInfo;
export function createDoeRuntime(options?: {
  binPath?: string;
  libPath?: string;
}): DoeRuntime;
export function runDawnVsDoeCompare(options: Record<string, unknown>): DoeRuntimeRunResult;

export const doe: FullDoeNamespace;

declare const _default: {
  create: typeof create;
  globals: typeof globals;
  setupGlobals: typeof setupGlobals;
  requestAdapter: typeof requestAdapter;
  requestDevice: typeof requestDevice;
  providerInfo: typeof providerInfo;
  createDoeRuntime: typeof createDoeRuntime;
  runDawnVsDoeCompare: typeof runDawnVsDoeCompare;
  doe: FullDoeNamespace;
};

export default _default;
