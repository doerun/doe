export interface NodeWebGPUBootstrapResult {
  ok: boolean;
  provider: string | null;
  detail?: string | null;
}

export interface NodeWebGPUProviderBootstrapResult {
  ok: true;
  provider: string;
  module: unknown;
}

export interface NodeWebGPUBootstrapOptions {
  force?: boolean;
}

export function hasNavigatorGpu(): boolean;
export function hasGpuEnums(): boolean;
export function installNavigatorGpu(gpu: unknown, options?: NodeWebGPUBootstrapOptions): boolean;
export function bootstrapNodeWebGPU(): Promise<NodeWebGPUBootstrapResult>;
export function bootstrapNodeWebGPUProvider(
  providerSpecifier: string,
  options?: NodeWebGPUBootstrapOptions,
): Promise<NodeWebGPUProviderBootstrapResult>;
