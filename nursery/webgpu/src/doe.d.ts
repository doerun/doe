export type DoeBufferUsage =
  | "upload"
  | "readback"
  | "uniform"
  | "storage-read"
  | "storage-readwrite";

export type DoeWorkgroups = number | [number, number, number];

export type DoeBindingAccess =
  | "uniform"
  | "storage-read"
  | "storage-readwrite";

export interface DoeCreateBufferOptions {
  size: number;
  usage: DoeBufferUsage | DoeBufferUsage[] | number;
  label?: string;
  mappedAtCreation?: boolean;
}

export interface DoeCreateBufferFromDataOptions {
  usage?: DoeBufferUsage | DoeBufferUsage[] | number;
  label?: string;
}

export interface DoeReadBufferOptions {
  size?: number;
  offset?: number;
  label?: string;
}

export interface DoeBindingBuffer<TBuffer> {
  buffer: TBuffer;
  access?: DoeBindingAccess;
}

export interface DoeRunComputeOptions<TBuffer> {
  code: string;
  entryPoint?: string;
  bindings?: Array<TBuffer | DoeBindingBuffer<TBuffer>>;
  workgroups: DoeWorkgroups;
  label?: string;
}

export interface DoeKernelDispatchOptions<TBuffer> {
  bindings?: Array<TBuffer | DoeBindingBuffer<TBuffer>>;
  workgroups: DoeWorkgroups;
  label?: string;
}

export interface BoundDoeNamespace<TDevice, TBuffer, TKernel, TRunComputeOptions> {
  readonly device: TDevice;
  createBuffer(options: DoeCreateBufferOptions): TBuffer;
  createBufferFromData<T extends ArrayBufferView>(
    data: T | ArrayBuffer,
    options?: DoeCreateBufferFromDataOptions
  ): TBuffer;
  readBuffer<T extends ArrayBufferView>(
    buffer: TBuffer,
    type: { new(buffer: ArrayBuffer): T },
    options?: DoeReadBufferOptions
  ): Promise<T>;
  runCompute(options: TRunComputeOptions): Promise<void>;
  compileCompute(options: TRunComputeOptions): TKernel;
}

export interface DoeNamespace<TDevice, TBuffer, TKernel, TBoundDoe, TRunComputeOptions> {
  bind(device: TDevice): TBoundDoe;
  createBuffer(device: TDevice, options: DoeCreateBufferOptions): TBuffer;
  createBufferFromData<T extends ArrayBufferView>(
    device: TDevice,
    data: T | ArrayBuffer,
    options?: DoeCreateBufferFromDataOptions
  ): TBuffer;
  readBuffer<T extends ArrayBufferView>(
    device: TDevice,
    buffer: TBuffer,
    type: { new(buffer: ArrayBuffer): T },
    options?: DoeReadBufferOptions
  ): Promise<T>;
  runCompute(device: TDevice, options: TRunComputeOptions): Promise<void>;
  compileCompute(device: TDevice, options: TRunComputeOptions): TKernel;
}
