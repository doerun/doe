export type DoeBufferUsage =
  | "upload"
  | "readback"
  | "uniform"
  | "storageRead"
  | "storageReadWrite";

export type DoeWorkgroups = number | [number, number] | [number, number, number];

export type DoeBindingAccess = "uniform" | "storageRead" | "storageReadWrite";

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

export interface DoeCreateBufferLikeOptions extends Omit<
  DoeCreateBufferOptions,
  "size"
> {
  size?: number;
}

export interface DoeBindingBuffer<TBuffer> {
  buffer: TBuffer;
  access?: DoeBindingAccess;
}

export interface DoeComputeInputDataOptions {
  data: ArrayBufferView | ArrayBuffer;
  usage?: DoeBufferUsage | DoeBufferUsage[];
  access?: DoeBindingAccess;
  label?: string;
}

export type DoeComputeInput<TBuffer> =
  | ArrayBufferView
  | ArrayBuffer
  | TBuffer
  | DoeBindingBuffer<TBuffer>
  | DoeComputeInputDataOptions;

export interface DoeComputeOnceOutputOptions<T extends ArrayBufferView> {
  type: { new (buffer: ArrayBuffer): T };
  size?: number;
  likeInput?: number;
  usage?: DoeBufferUsage | DoeBufferUsage[];
  access?: DoeBindingAccess;
  label?: string;
  read?: DoeReadBufferOptions;
}

export interface DoeComputeOnceOptions<TBuffer, T extends ArrayBufferView> {
  code: string;
  entryPoint?: string;
  inputs?: Array<DoeComputeInput<TBuffer>>;
  output: DoeComputeOnceOutputOptions<T>;
  workgroups: DoeWorkgroups;
  label?: string;
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

export interface BoundDoeBuffersNamespace<TBuffer> {
  create(options: DoeCreateBufferOptions): TBuffer;
  fromData<T extends ArrayBufferView>(
    data: T | ArrayBuffer,
    options?: DoeCreateBufferFromDataOptions,
  ): TBuffer;
  like(
    source: TBuffer | ArrayBufferView | ArrayBuffer,
    options?: DoeCreateBufferLikeOptions,
  ): TBuffer;
  read<T extends ArrayBufferView>(
    buffer: TBuffer,
    type: { new (buffer: ArrayBuffer): T },
    options?: DoeReadBufferOptions,
  ): Promise<T>;
}

export interface DoeBuffersNamespace<TDevice, TBuffer> {
  create(device: TDevice, options: DoeCreateBufferOptions): TBuffer;
  fromData<T extends ArrayBufferView>(
    device: TDevice,
    data: T | ArrayBuffer,
    options?: DoeCreateBufferFromDataOptions,
  ): TBuffer;
  like(
    device: TDevice,
    source: TBuffer | ArrayBufferView | ArrayBuffer,
    options?: DoeCreateBufferLikeOptions,
  ): TBuffer;
  read<T extends ArrayBufferView>(
    device: TDevice,
    buffer: TBuffer,
    type: { new (buffer: ArrayBuffer): T },
    options?: DoeReadBufferOptions,
  ): Promise<T>;
}

export interface BoundDoeComputeNamespace<
  TBuffer,
  TKernel,
  TRunComputeOptions,
> {
  run(options: TRunComputeOptions): Promise<void>;
  compile(options: TRunComputeOptions): TKernel;
  once<T extends ArrayBufferView>(
    options: DoeComputeOnceOptions<TBuffer, T>,
  ): Promise<T>;
}

export interface DoeComputeNamespace<
  TDevice,
  TBuffer,
  TKernel,
  TRunComputeOptions,
> {
  run(device: TDevice, options: TRunComputeOptions): Promise<void>;
  compile(device: TDevice, options: TRunComputeOptions): TKernel;
  once<T extends ArrayBufferView>(
    device: TDevice,
    options: DoeComputeOnceOptions<TBuffer, T>,
  ): Promise<T>;
}

export interface BoundDoeNamespace<
  TDevice,
  TBuffer,
  TKernel,
  TRunComputeOptions,
> {
  readonly device: TDevice;
  readonly buffers: BoundDoeBuffersNamespace<TBuffer>;
  readonly compute: BoundDoeComputeNamespace<
    TBuffer,
    TKernel,
    TRunComputeOptions
  >;
}

export interface DoeNamespace<
  TDevice,
  TBuffer,
  TKernel,
  TBoundDoe,
  TRunComputeOptions,
  TRequestDeviceOptions = unknown,
> {
  requestDevice(options?: TRequestDeviceOptions): Promise<TBoundDoe>;
  bind(device: TDevice): TBoundDoe;
  readonly buffers: DoeBuffersNamespace<TDevice, TBuffer>;
  readonly compute: DoeComputeNamespace<
    TDevice,
    TBuffer,
    TKernel,
    TRunComputeOptions
  >;
}
