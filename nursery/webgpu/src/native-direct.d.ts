import type { ProviderInfo } from "./full.js";

export interface NativeDirectGPUBuffer {
  readonly size: number;
  readonly usage: number;
  mapAsync(mode: number, offset?: number, size?: number): Promise<void>;
  getMappedRange(offset?: number, size?: number): ArrayBuffer;
  unmap(): void;
  destroy(): void;
}

export interface NativeDirectBindGroupLayout {}

export interface NativeDirectBindGroup {}

export interface NativeDirectPipelineLayout {}

export interface NativeDirectComputePipeline {}

export interface NativeDirectComputePassEncoder {
  setPipeline(pipeline: NativeDirectComputePipeline): void;
  setBindGroup(index: number, bindGroup: NativeDirectBindGroup): void;
  dispatchWorkgroups(x: number, y?: number, z?: number): void;
  dispatchWorkgroupsIndirect(indirectBuffer: NativeDirectGPUBuffer, indirectOffset?: number): void;
  end(): void;
}

export interface NativeDirectCommandEncoder {
  beginComputePass(descriptor?: GPUComputePassDescriptor): NativeDirectComputePassEncoder;
  copyBufferToBuffer(
    source: NativeDirectGPUBuffer,
    sourceOffset: number,
    target: NativeDirectGPUBuffer,
    targetOffset: number,
    size: number
  ): void;
  finish(): GPUCommandBuffer;
}

export interface NativeDirectQueue {
  submit(commandBuffers: GPUCommandBuffer[]): void;
  writeBuffer(
    buffer: NativeDirectGPUBuffer,
    bufferOffset: number,
    data: BufferSource,
    dataOffset?: number,
    size?: number
  ): void;
  onSubmittedWorkDone(): Promise<void>;
}

export interface NativeDirectShaderModule {}

export interface NativeDirectGPUDevice {
  readonly queue: NativeDirectQueue;
  readonly limits: GPUSupportedLimits;
  readonly features: GPUSupportedFeatures;
  createBuffer(descriptor: GPUBufferDescriptor): NativeDirectGPUBuffer;
  createShaderModule(descriptor: GPUShaderModuleDescriptor): NativeDirectShaderModule;
  createComputePipeline(descriptor: GPUComputePipelineDescriptor): NativeDirectComputePipeline;
  createComputePipelineAsync(descriptor: GPUComputePipelineDescriptor): Promise<NativeDirectComputePipeline>;
  createBindGroupLayout(descriptor: GPUBindGroupLayoutDescriptor): NativeDirectBindGroupLayout;
  createBindGroup(descriptor: GPUBindGroupDescriptor): NativeDirectBindGroup;
  createPipelineLayout(descriptor: GPUPipelineLayoutDescriptor): NativeDirectPipelineLayout;
  createCommandEncoder(descriptor?: GPUCommandEncoderDescriptor): NativeDirectCommandEncoder;
  destroy(): void;
}

export interface NativeDirectGPUAdapter {
  readonly limits: GPUSupportedLimits;
  readonly features: GPUSupportedFeatures;
  readonly info: Record<string, unknown>;
  requestDevice(descriptor?: GPUDeviceDescriptor): Promise<NativeDirectGPUDevice>;
  destroy(): void;
}

export interface NativeDirectGPU {
  requestAdapter(options?: GPURequestAdapterOptions): Promise<NativeDirectGPUAdapter | null>;
}

export interface RequestDeviceOptions {
  adapterOptions?: GPURequestAdapterOptions;
  deviceDescriptor?: GPUDeviceDescriptor;
  createArgs?: string[] | null;
}

export const globals: Record<string, unknown>;
export function create(createArgs?: string[] | null): NativeDirectGPU;
export function setupGlobals(target?: object, createArgs?: string[] | null): NativeDirectGPU;
export function requestAdapter(
  adapterOptions?: GPURequestAdapterOptions,
  createArgs?: string[] | null
): Promise<NativeDirectGPUAdapter | null>;
export function requestDevice(options?: RequestDeviceOptions): Promise<NativeDirectGPUDevice>;
export function providerInfo(): ProviderInfo;
export function preflightShaderSource(code: string): {
  ok: boolean;
  stage: string;
  kind: string;
  message: string;
  reasons: string[];
  line?: number;
  column?: number;
};
export function setNativeTimeoutMs(ms: number): void;

declare const _default: {
  create: typeof create;
  globals: typeof globals;
  setupGlobals: typeof setupGlobals;
  requestAdapter: typeof requestAdapter;
  requestDevice: typeof requestDevice;
  providerInfo: typeof providerInfo;
  preflightShaderSource: typeof preflightShaderSource;
  setNativeTimeoutMs: typeof setNativeTimeoutMs;
};

export default _default;
