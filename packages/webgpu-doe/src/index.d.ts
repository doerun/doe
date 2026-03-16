export type DoeBufferUsage =
  | "upload"
  | "readback"
  | "uniform"
  | "storageRead"
  | "storageReadWrite";

export type DoeWorkgroups = number | [number, number] | [number, number, number];

export type DoeBindingAccess = "uniform" | "storageRead" | "storageReadWrite";

export interface DoeLabelOptions {
  label?: string;
}

export interface DoeCreateBufferOptions extends DoeLabelOptions {
  size?: number;
  usage?: DoeBufferUsage | DoeBufferUsage[] | number;
  data?: ArrayBufferView | ArrayBuffer;
  mappedAtCreation?: boolean;
}

export interface DoeReadBufferSubrangeOptions extends DoeLabelOptions {
  size?: number;
  offset?: number;
}

export interface DoeReadBufferOptions<T extends ArrayBufferView = ArrayBufferView>
  extends DoeReadBufferSubrangeOptions {
  buffer: unknown;
  type: { new (buffer: ArrayBuffer): T };
}

export interface DoeBindingBuffer<TBuffer> {
  buffer: TBuffer;
  access?: DoeBindingAccess;
}

export type DoeBindingLike<TBuffer> = TBuffer | DoeBindingBuffer<TBuffer>;

export interface DoeComputeInputDataOptions extends DoeLabelOptions {
  data: ArrayBufferView | ArrayBuffer;
  usage?: DoeBufferUsage | DoeBufferUsage[];
  access?: DoeBindingAccess;
}

export type DoeComputeInput<TBuffer> =
  | ArrayBufferView
  | ArrayBuffer
  | TBuffer
  | DoeBindingBuffer<TBuffer>
  | DoeComputeInputDataOptions;

export interface DoeComputeOutputOptions<T extends ArrayBufferView> extends DoeLabelOptions {
  type: { new (buffer: ArrayBuffer): T };
  size?: number;
  likeInput?: number;
  usage?: DoeBufferUsage | DoeBufferUsage[];
  access?: DoeBindingAccess;
  read?: DoeReadBufferSubrangeOptions;
}

export interface DoeComputeOptions<TBuffer, T extends ArrayBufferView> extends DoeLabelOptions {
  code: string;
  entryPoint?: string;
  inputs?: Array<DoeComputeInput<TBuffer>>;
  output: DoeComputeOutputOptions<T>;
  workgroups: DoeWorkgroups;
}

export interface DoeKernelCreateOptions<TBuffer> extends DoeLabelOptions {
  code: string;
  entryPoint?: string;
  bindings?: Array<DoeBindingLike<TBuffer>>;
}

export interface DoeKernelDispatchOptions<TBuffer, TBindingSet> extends DoeLabelOptions {
  bindings?: Array<DoeBindingLike<TBuffer>> | TBindingSet;
  workgroups: DoeWorkgroups;
}

export interface DoeBindingSet<TKernel = unknown> {
  readonly kernel: TKernel;
  readonly label?: string;
}

export interface DoeKernelBindingsNamespace<TBuffer, TBindingSet> {
  create(
    bindings: Array<DoeBindingLike<TBuffer>>,
    options?: DoeLabelOptions,
  ): TBindingSet;
}

export interface DoeComputeBatch<TKernel, TBuffer, TBindingSet> {
  dispatch(
    kernel: TKernel,
    options: DoeKernelDispatchOptions<TBuffer, TBindingSet>,
  ): this;
  submit(): Promise<void>;
}

export interface DoeComputePass<TKernel, TBuffer, TBindingSet> {
  dispatch(
    kernel: TKernel,
    options: DoeKernelDispatchOptions<TBuffer, TBindingSet>,
  ): this;
  end(): this;
}

export interface DoeCommandEncoder<TKernel, TBuffer, TBindingSet, TPass> {
  beginComputePass(options?: DoeLabelOptions): TPass;
  submit(): Promise<void>;
}

export interface DoeKernel<
  TBuffer,
  TBindingSet,
  TBatch,
  TPass,
> {
  readonly device: unknown;
  readonly entryPoint: string;
  readonly bindings: DoeKernelBindingsNamespace<TBuffer, TBindingSet>;
  dispatch(options: DoeKernelDispatchOptions<TBuffer, TBindingSet>): Promise<void>;
  encode(
    target: TBatch | TPass,
    options: DoeKernelDispatchOptions<TBuffer, TBindingSet>,
  ): TBatch | TPass;
}

export interface BoundDoeBufferNamespace<TBuffer> {
  create(options: DoeCreateBufferOptions): TBuffer;
  read<T extends ArrayBufferView>(
    options: DoeReadBufferOptions<T>,
  ): Promise<T>;
  read<T extends ArrayBufferView>(
    buffer: TBuffer,
    type: { new (buffer: ArrayBuffer): T },
    options?: DoeReadBufferSubrangeOptions,
  ): Promise<T>;
}

export interface BoundDoeKernelNamespace<
  TBuffer,
  TKernel,
  TBindingSet,
> {
  run(options: DoeKernelCreateOptions<TBuffer> & DoeKernelDispatchOptions<TBuffer, TBindingSet>): Promise<void>;
  create(options: DoeKernelCreateOptions<TBuffer>): TKernel;
}

export interface BoundDoeCommandEncoderNamespace<TEncoder> {
  create(options?: DoeLabelOptions): TEncoder;
}

export interface BoundDoeComputeCallable<
  TBuffer,
  TBatch,
  T extends ArrayBufferView = ArrayBufferView,
> {
  (options: DoeComputeOptions<TBuffer, T>): Promise<T>;
  begin(options?: DoeLabelOptions): TBatch;
}

export interface BoundDoeNamespace<
  TDevice,
  TBuffer,
  TBindingSet,
  TKernel extends DoeKernel<TBuffer, TBindingSet, TBatch, TPass>,
  TBatch extends DoeComputeBatch<TKernel, TBuffer, TBindingSet>,
  TPass extends DoeComputePass<TKernel, TBuffer, TBindingSet>,
  TEncoder extends DoeCommandEncoder<TKernel, TBuffer, TBindingSet, TPass>,
> {
  readonly device: TDevice;
  readonly buffer: BoundDoeBufferNamespace<TBuffer>;
  readonly commandEncoder: BoundDoeCommandEncoderNamespace<TEncoder>;
  readonly kernel: BoundDoeKernelNamespace<TBuffer, TKernel, TBindingSet>;
  readonly compute: BoundDoeComputeCallable<TBuffer, TBatch>;
}

export interface DoeNamespace<
  TDevice,
  TBoundDoe,
  TRequestDeviceOptions = unknown,
> {
  requestDevice(options?: TRequestDeviceOptions): Promise<TBoundDoe>;
  bind(device: TDevice): TBoundDoe;
}

export declare function createDoeNamespace<
  TDevice = unknown,
  TBuffer = unknown,
  TBindingSet extends DoeBindingSet = DoeBindingSet,
  TKernel extends DoeKernel<TBuffer, TBindingSet, TBatch, TPass> = DoeKernel<TBuffer, TBindingSet, TBatch, TPass>,
  TBatch extends DoeComputeBatch<TKernel, TBuffer, TBindingSet> = DoeComputeBatch<TKernel, TBuffer, TBindingSet>,
  TPass extends DoeComputePass<TKernel, TBuffer, TBindingSet> = DoeComputePass<TKernel, TBuffer, TBindingSet>,
  TEncoder extends DoeCommandEncoder<TKernel, TBuffer, TBindingSet, TPass> = DoeCommandEncoder<TKernel, TBuffer, TBindingSet, TPass>,
  TBoundDoe extends BoundDoeNamespace<TDevice, TBuffer, TBindingSet, TKernel, TBatch, TPass, TEncoder> = BoundDoeNamespace<TDevice, TBuffer, TBindingSet, TKernel, TBatch, TPass, TEncoder>,
  TRequestDeviceOptions = unknown,
>(options?: {
  requestDevice?: (options?: TRequestDeviceOptions) => Promise<TDevice> | TDevice;
}): DoeNamespace<TDevice, TBoundDoe, TRequestDeviceOptions>;

export declare const doe: DoeNamespace<unknown, BoundDoeNamespace<unknown, unknown, DoeBindingSet, DoeKernel<unknown, DoeBindingSet, DoeComputeBatch<any, unknown, DoeBindingSet>, DoeComputePass<any, unknown, DoeBindingSet>>, DoeComputeBatch<any, unknown, DoeBindingSet>, DoeComputePass<any, unknown, DoeBindingSet>, DoeCommandEncoder<any, unknown, DoeBindingSet, DoeComputePass<any, unknown, DoeBindingSet>>>>;

export default doe;
