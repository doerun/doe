import type {
  BoundDoeNamespace,
  DoeKernelDispatchOptions,
  DoeNamespace,
  DoeRunComputeOptions,
} from "./doe.js";
import type {
  DoeRuntime,
  DoeRuntimeRunResult,
  ProviderInfo,
} from "./full.js";

export interface ComputeGPUBuffer {
  readonly size: number;
  readonly usage: number;
  mapAsync(mode: number, offset?: number, size?: number): Promise<void>;
  getMappedRange(offset?: number, size?: number): ArrayBuffer;
  assertMappedPrefixF32?(expected: number[], count: number): boolean;
  unmap(): void;
  destroy(): void;
}

export interface ComputeBindGroupLayout {}

export interface ComputeBindGroup {}

export interface ComputePipelineLayout {}

export interface ComputeQuerySet {
  destroy(): void;
}

export interface ComputeComputePipeline {
  getBindGroupLayout(index: number): ComputeBindGroupLayout;
}

export interface ComputePassEncoder {
  setPipeline(pipeline: ComputeComputePipeline): void;
  setBindGroup(index: number, bindGroup: ComputeBindGroup): void;
  dispatchWorkgroups(x: number, y?: number, z?: number): void;
  dispatchWorkgroupsIndirect(indirectBuffer: ComputeGPUBuffer, indirectOffset?: number): void;
  writeTimestamp?(querySet: ComputeQuerySet, queryIndex: number): void;
  end(): void;
}

export interface ComputeCommandEncoder {
  beginComputePass(descriptor?: GPUComputePassDescriptor): ComputePassEncoder;
  copyBufferToBuffer(
    source: ComputeGPUBuffer,
    sourceOffset: number,
    target: ComputeGPUBuffer,
    targetOffset: number,
    size: number
  ): void;
  resolveQuerySet?(
    querySet: ComputeQuerySet,
    firstQuery: number,
    queryCount: number,
    destination: ComputeGPUBuffer,
    destinationOffset: number
  ): void;
  finish(): GPUCommandBuffer;
}

export interface ComputeQueue {
  submit(commandBuffers: GPUCommandBuffer[]): void;
  writeBuffer(
    buffer: ComputeGPUBuffer,
    bufferOffset: number,
    data: BufferSource,
    dataOffset?: number,
    size?: number
  ): void;
  onSubmittedWorkDone(): Promise<void>;
}

export interface ComputeGPUDevice {
  readonly queue: ComputeQueue;
  readonly limits: GPUSupportedLimits;
  readonly features: GPUSupportedFeatures;
  createBuffer(descriptor: GPUBufferDescriptor): ComputeGPUBuffer;
  createShaderModule(descriptor: GPUShaderModuleDescriptor): GPUShaderModule;
  createComputePipeline(descriptor: GPUComputePipelineDescriptor): ComputeComputePipeline;
  createComputePipelineAsync(descriptor: GPUComputePipelineDescriptor): Promise<ComputeComputePipeline>;
  createBindGroupLayout(descriptor: GPUBindGroupLayoutDescriptor): ComputeBindGroupLayout;
  createBindGroup(descriptor: GPUBindGroupDescriptor): ComputeBindGroup;
  createPipelineLayout(descriptor: GPUPipelineLayoutDescriptor): ComputePipelineLayout;
  createCommandEncoder(descriptor?: GPUCommandEncoderDescriptor): ComputeCommandEncoder;
  createQuerySet?(descriptor: GPUQuerySetDescriptor): ComputeQuerySet;
  destroy(): void;
}

export interface ComputeGPUAdapter {
  readonly limits: GPUSupportedLimits;
  readonly features: GPUSupportedFeatures;
  requestDevice(descriptor?: GPUDeviceDescriptor): Promise<ComputeGPUDevice>;
  destroy(): void;
}

export interface ComputeGPU {
  requestAdapter(options?: GPURequestAdapterOptions): Promise<ComputeGPUAdapter | null>;
}

export interface RequestDeviceOptions {
  adapterOptions?: GPURequestAdapterOptions;
  deviceDescriptor?: GPUDeviceDescriptor;
  createArgs?: string[] | null;
}

export interface ComputeDoeRunComputeOptions extends DoeRunComputeOptions<ComputeGPUBuffer> {}

export interface ComputeDoeKernelDispatchOptions extends DoeKernelDispatchOptions<ComputeGPUBuffer> {}

export interface ComputeDoeKernel {
  readonly device: ComputeGPUDevice;
  readonly entryPoint: string;
  dispatch(options: ComputeDoeKernelDispatchOptions): Promise<void>;
}

export interface ComputeBoundDoeNamespace
  extends BoundDoeNamespace<ComputeGPUDevice, ComputeGPUBuffer, ComputeDoeKernel, ComputeDoeRunComputeOptions> {}

export interface ComputeDoeNamespace
  extends DoeNamespace<
    ComputeGPUDevice,
    ComputeGPUBuffer,
    ComputeDoeKernel,
    ComputeBoundDoeNamespace,
    ComputeDoeRunComputeOptions
  > {}

export const globals: Record<string, unknown>;
export function create(createArgs?: string[] | null): ComputeGPU;
export function setupGlobals(target?: object, createArgs?: string[] | null): ComputeGPU;
export function requestAdapter(
  adapterOptions?: GPURequestAdapterOptions,
  createArgs?: string[] | null
): Promise<ComputeGPUAdapter | null>;
export function requestDevice(options?: RequestDeviceOptions): Promise<ComputeGPUDevice>;
export function providerInfo(): ProviderInfo;
export function createDoeRuntime(options?: {
  binPath?: string;
  libPath?: string;
}): DoeRuntime;
export function runDawnVsDoeCompare(options: Record<string, unknown>): DoeRuntimeRunResult;

export const doe: ComputeDoeNamespace;

declare const _default: {
  create: typeof create;
  globals: typeof globals;
  setupGlobals: typeof setupGlobals;
  requestAdapter: typeof requestAdapter;
  requestDevice: typeof requestDevice;
  providerInfo: typeof providerInfo;
  createDoeRuntime: typeof createDoeRuntime;
  runDawnVsDoeCompare: typeof runDawnVsDoeCompare;
  doe: ComputeDoeNamespace;
};

export default _default;
