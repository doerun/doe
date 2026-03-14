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

export interface DoeKernelCreateOptions<TBuffer> {
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

export interface BoundDoeBufferNamespace<TBuffer> {
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

export interface BoundDoeKernelNamespace<
  TBuffer,
  TKernel,
  TKernelOptions,
> {
  run(options: TKernelOptions): Promise<void>;
  create(options: TKernelOptions): TKernel;
}

export interface BoundDoeComputeNamespace<
  TBuffer,
> {
  once<T extends ArrayBufferView>(
    options: DoeComputeOnceOptions<TBuffer, T>,
  ): Promise<T>;
}

export interface BoundDoeNamespace<
  TDevice,
  TBuffer,
  TKernel,
  TKernelOptions,
> {
  readonly device: TDevice;
  readonly buffer: BoundDoeBufferNamespace<TBuffer>;
  readonly kernel: BoundDoeKernelNamespace<
    TBuffer,
    TKernel,
    TKernelOptions
  >;
  readonly compute: BoundDoeComputeNamespace<
    TBuffer
  >;
}

export interface DoeNamespace<
  TDevice,
  TBoundDoe,
  TRequestDeviceOptions = unknown,
> {
  requestDevice(options?: TRequestDeviceOptions): Promise<TBoundDoe>;
  bind(device: TDevice): TBoundDoe;
}
