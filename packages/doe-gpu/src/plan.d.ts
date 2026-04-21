export type DoePlanValidationError = {
  path: string;
  message: string;
};

export type DoeCommandStreamValidationResult = {
  ok: boolean;
  kind: typeof DOE_COMMAND_STREAM_KIND;
  commandCount: number;
  errors: DoePlanValidationError[];
};

export type DoePlanValidationResult = {
  ok: boolean;
  kind?: string;
  artifactKind?: string;
  schemaVersion?: number;
  errors: DoePlanValidationError[];
};

export type DoeCommand = {
  kind: string;
  [key: string]: unknown;
};

export type DoeCommandStream = DoeCommand[];

export type DoeNormalizedPlan = {
  schemaVersion: typeof DOE_NORMALIZED_PLAN_SCHEMA_VERSION;
  planKind: string;
  workloadId: string;
  commands: DoeCommandStream;
  [key: string]: unknown;
};

export type DoePlanArtifact = {
  schemaVersion: number;
  artifactKind: string;
  [key: string]: unknown;
};

export type DoeCaptureGraph = {
  schemaVersion: typeof DOE_WEBGPU_CAPTURE_GRAPH_SCHEMA_VERSION;
  artifactKind: typeof DOE_WEBGPU_CAPTURE_GRAPH_ARTIFACT_KIND;
  graphSha256?: string;
  provider: Record<string, unknown>;
  metadata: Record<string, unknown>;
  supportedWebgpuMethods: string[];
  unsupportedCslFeatures: string[];
  buffers: Record<string, unknown>[];
  bufferEvents: Record<string, unknown>[];
  bufferWrites: Record<string, unknown>[];
  shaderModules: Record<string, unknown>[];
  bindGroupLayouts: Record<string, unknown>[];
  pipelineLayouts: Record<string, unknown>[];
  computePipelines: Record<string, unknown>[];
  bindGroups: Record<string, unknown>[];
  commandEncoders: Record<string, unknown>[];
  commandBuffers: Record<string, unknown>[];
  submissions: Record<string, unknown>[];
  readbacks: Record<string, unknown>[];
  unsupported: Record<string, unknown>[];
};

export type DoeCaptureProvider = {
  kind: "doe_capture_provider";
  graph(): DoeCaptureGraph;
  snapshot(): Promise<DoeCaptureGraph>;
  requestAdapter(options?: unknown): Promise<DoeCaptureAdapter>;
  requestDevice(options?: unknown): Promise<DoeCaptureDevice>;
};

export type DoeCaptureAdapter = {
  features: Set<unknown>;
  limits: Record<string, unknown>;
  info: Record<string, unknown>;
  requestDevice(descriptor?: unknown): Promise<DoeCaptureDevice>;
};

export type DoeCaptureBuffer = {
  label: string;
  readonly size: number;
  readonly usage: number;
  mapState: string;
  mapAsync(mode: number, offset?: number, size?: number): Promise<void>;
  getMappedRange(offset?: number, size?: number): ArrayBuffer;
  unmap(): void;
  destroy(): void;
};

export type DoeCaptureDevice = {
  label: string;
  features: Set<unknown>;
  limits: Record<string, unknown>;
  queue: DoeCaptureQueue;
  lost: Promise<unknown>;
  createBuffer(descriptor?: Record<string, unknown>): DoeCaptureBuffer;
  createShaderModule(descriptor: { code: string; label?: string; [key: string]: unknown }): unknown;
  createBindGroupLayout(descriptor?: Record<string, unknown>): unknown;
  createPipelineLayout(descriptor?: Record<string, unknown>): unknown;
  createComputePipeline(descriptor: Record<string, unknown>): unknown;
  createComputePipelineAsync(descriptor: Record<string, unknown>): Promise<unknown>;
  createBindGroup(descriptor?: Record<string, unknown>): unknown;
  createCommandEncoder(descriptor?: Record<string, unknown>): DoeCaptureCommandEncoder;
  createTexture(...args: unknown[]): never;
  createSampler(...args: unknown[]): never;
  createRenderPipeline(...args: unknown[]): never;
  createRenderPipelineAsync(...args: unknown[]): Promise<never>;
  destroy(): void;
};

export type DoeCaptureQueue = {
  writeBuffer(
    buffer: DoeCaptureBuffer,
    bufferOffset: number,
    data: ArrayBuffer | ArrayBufferView,
    dataOffset?: number,
    size?: number,
  ): void;
  submit(commandBuffers: unknown[]): void;
  onSubmittedWorkDone(): Promise<void>;
};

export type DoeCaptureComputePass = {
  setPipeline(pipeline: unknown): void;
  setBindGroup(index: number, bindGroup: unknown, dynamicOffsets?: unknown[]): void;
  dispatchWorkgroups(x: number, y?: number, z?: number): void;
  end(): void;
};

export type DoeCaptureCommandEncoder = {
  label: string;
  beginComputePass(descriptor?: Record<string, unknown>): DoeCaptureComputePass;
  copyBufferToBuffer(
    source: DoeCaptureBuffer,
    sourceOffset: number,
    target: DoeCaptureBuffer,
    targetOffset: number,
    size: number,
  ): void;
  finish(descriptor?: Record<string, unknown>): unknown;
};

export type DoeWebgpuEnumMap = Record<string, number>;

export type DoeCaptureGpu = {
  requestAdapter: DoeCaptureProvider["requestAdapter"];
};

export declare const DOE_COMMAND_STREAM_KIND: "doe_command_stream";
export declare const DOE_NORMALIZED_PLAN_SCHEMA_VERSION: 1;
export declare const DOE_WEBGPU_CAPTURE_GRAPH_ARTIFACT_KIND: "doe_webgpu_capture_graph";
export declare const DOE_WEBGPU_CAPTURE_GRAPH_SCHEMA_VERSION: 1;
export declare const DOE_WEBGPU_CAPTURE_EVIDENCE_ARTIFACT_KIND: "doe_webgpu_capture_evidence";
export declare const DOE_WEBGPU_CAPTURE_EVIDENCE_SCHEMA_VERSION: 1;
export declare const DOE_STREAM_GRAPH_ARTIFACT_KIND: "doe_stream_graph";
export declare const DOE_STREAM_EXECUTION_PLAN_ARTIFACT_KIND: "doe_stream_execution_plan";
export declare const DOE_CSL_HOST_PLAN_ARTIFACT_KIND: "csl_host_plan";
export declare const DOE_CAPTURE_SUPPORTED_WEBGPU_METHODS: readonly string[];
export declare const DOE_CAPTURE_UNSUPPORTED_CSL_FEATURES: readonly string[];
export declare const DOE_CAPTURE_LOWERING_STAGES: readonly string[];
export declare const DOE_CAPTURE_EVIDENCE_STATUSES: readonly string[];
export declare const DOE_PLAN_ARTIFACT_KINDS: readonly string[];
export declare const DOE_PLAN_SCHEMA_VERSIONS: Readonly<Record<string, number>>;
export declare const globals: {
  GPUBufferUsage: DoeWebgpuEnumMap;
  GPUShaderStage: DoeWebgpuEnumMap;
  GPUMapMode: DoeWebgpuEnumMap;
  GPUTextureUsage: DoeWebgpuEnumMap;
  [key: string]: unknown;
};
export declare const GPUBufferUsage: DoeWebgpuEnumMap;
export declare const GPUShaderStage: DoeWebgpuEnumMap;
export declare const GPUMapMode: DoeWebgpuEnumMap;
export declare const GPUTextureUsage: DoeWebgpuEnumMap;

export declare function validateCommandStream(commands: unknown): DoeCommandStreamValidationResult;
export declare function assertCommandStream(commands: unknown): DoeCommandStream;
export declare function validateNormalizedPlan(plan: unknown): DoePlanValidationResult;
export declare function assertNormalizedPlan(plan: unknown): DoeNormalizedPlan;
export declare function validatePlanArtifact(artifact: unknown): DoePlanValidationResult;
export declare function assertPlanArtifact(artifact: unknown): DoePlanArtifact;
export declare function validateCaptureGraph(graph: unknown): DoePlanValidationResult;
export declare function assertCaptureGraph(graph: unknown): DoeCaptureGraph;
export declare function classifyPlan(value: unknown): DoeCommandStreamValidationResult | DoePlanValidationResult;
export declare function createCaptureProvider(options?: {
  metadata?: Record<string, unknown>;
  deviceLabel?: string;
}): DoeCaptureProvider;
export declare const requestAdapter: DoeCaptureProvider["requestAdapter"];
export declare const requestDevice: DoeCaptureProvider["requestDevice"];
export declare const snapshotCaptureGraph: DoeCaptureProvider["snapshot"];
export declare const captureGraph: DoeCaptureProvider["graph"];
export declare const gpu: DoeCaptureGpu;
export declare const webgpu: DoeCaptureGpu;

declare const _default: {
  DOE_COMMAND_STREAM_KIND: typeof DOE_COMMAND_STREAM_KIND;
  DOE_NORMALIZED_PLAN_SCHEMA_VERSION: typeof DOE_NORMALIZED_PLAN_SCHEMA_VERSION;
  DOE_WEBGPU_CAPTURE_GRAPH_ARTIFACT_KIND: typeof DOE_WEBGPU_CAPTURE_GRAPH_ARTIFACT_KIND;
  DOE_WEBGPU_CAPTURE_GRAPH_SCHEMA_VERSION: typeof DOE_WEBGPU_CAPTURE_GRAPH_SCHEMA_VERSION;
  DOE_WEBGPU_CAPTURE_EVIDENCE_ARTIFACT_KIND: typeof DOE_WEBGPU_CAPTURE_EVIDENCE_ARTIFACT_KIND;
  DOE_WEBGPU_CAPTURE_EVIDENCE_SCHEMA_VERSION: typeof DOE_WEBGPU_CAPTURE_EVIDENCE_SCHEMA_VERSION;
  DOE_STREAM_GRAPH_ARTIFACT_KIND: typeof DOE_STREAM_GRAPH_ARTIFACT_KIND;
  DOE_STREAM_EXECUTION_PLAN_ARTIFACT_KIND: typeof DOE_STREAM_EXECUTION_PLAN_ARTIFACT_KIND;
  DOE_CSL_HOST_PLAN_ARTIFACT_KIND: typeof DOE_CSL_HOST_PLAN_ARTIFACT_KIND;
  DOE_CAPTURE_SUPPORTED_WEBGPU_METHODS: typeof DOE_CAPTURE_SUPPORTED_WEBGPU_METHODS;
  DOE_CAPTURE_UNSUPPORTED_CSL_FEATURES: typeof DOE_CAPTURE_UNSUPPORTED_CSL_FEATURES;
  DOE_CAPTURE_LOWERING_STAGES: typeof DOE_CAPTURE_LOWERING_STAGES;
  DOE_CAPTURE_EVIDENCE_STATUSES: typeof DOE_CAPTURE_EVIDENCE_STATUSES;
  DOE_PLAN_ARTIFACT_KINDS: typeof DOE_PLAN_ARTIFACT_KINDS;
  DOE_PLAN_SCHEMA_VERSIONS: typeof DOE_PLAN_SCHEMA_VERSIONS;
  globals: typeof globals;
  GPUBufferUsage: typeof GPUBufferUsage;
  GPUShaderStage: typeof GPUShaderStage;
  GPUMapMode: typeof GPUMapMode;
  GPUTextureUsage: typeof GPUTextureUsage;
  validateCommandStream: typeof validateCommandStream;
  assertCommandStream: typeof assertCommandStream;
  validateNormalizedPlan: typeof validateNormalizedPlan;
  assertNormalizedPlan: typeof assertNormalizedPlan;
  validatePlanArtifact: typeof validatePlanArtifact;
  assertPlanArtifact: typeof assertPlanArtifact;
  validateCaptureGraph: typeof validateCaptureGraph;
  assertCaptureGraph: typeof assertCaptureGraph;
  classifyPlan: typeof classifyPlan;
  createCaptureProvider: typeof createCaptureProvider;
  requestAdapter: typeof requestAdapter;
  requestDevice: typeof requestDevice;
  snapshotCaptureGraph: typeof snapshotCaptureGraph;
  captureGraph: typeof captureGraph;
  gpu: typeof gpu;
  webgpu: typeof webgpu;
};

export default _default;
