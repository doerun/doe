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

export type DoeStableTokenTieBreakRule = "lowest-index-among-max";
export type DoeStableTokenSelectedBy = "stable-token-policy";
export type DoeDeterminismProofCategory =
  | "tautological"
  | "comptime_verified"
  | "lean_verified"
  | "lean_fixture"
  | "lean_required";

export interface DoeDeterminismProofLink {
  theorem: string;
  module: string;
  category: DoeDeterminismProofCategory;
  relation: string;
  artifactPath: string;
}

export interface DoeStableTokenTopCandidate {
  index: number;
  logit: number;
}

export interface DoeStableTokenReceipt {
  mode: "stable-token";
  policyRegistryPath: string;
  policyRegistryVersion: string;
  policyId: string;
  comparator: "scalar-f32-greedy";
  tieBreakRule: DoeStableTokenTieBreakRule;
  sourceKind: "host-bytes" | "buffer-readback";
  vocabSize: number;
  bytesRead: number;
  logitsSha256: string;
  token: number;
  maxLogit: number;
  tiedMaxCount: number;
  tiedMaxIndicesPrefix: number[];
  tiedMaxIndicesOmittedCount: number;
  selectedBy: DoeStableTokenSelectedBy;
  topCandidates: DoeStableTokenTopCandidate[];
  proofLinks: DoeDeterminismProofLink[];
}

export interface DoeStableTokenResult {
  token: number;
  receipt: DoeStableTokenReceipt;
}

export interface DoeStableTokenOptions<TBuffer> extends DoeReadBufferSubrangeOptions {
  logits: TBuffer | ArrayBufferView | ArrayBuffer;
  vocabSize?: number;
  topCandidates?: number;
  tieBreakRule?: DoeStableTokenTieBreakRule;
}

export type DoeStableChoiceTriggerMode = "exact-max-tie" | "candidate-margin-band";
export type DoeStableChoiceEvaluatorKind = "fixed-priority";
export type DoeStableChoiceSelectedBy = "stable-choice-policy" | "stable-token-fallback";
export type DoeStableChoiceCandidateSetSource =
  | "fixture-declared"
  | "registry-resolved"
  | "source-report-resolved";

export interface DoeStableChoiceCandidate {
  token: number;
  label?: string;
}

export interface DoeStableChoiceReceiptCandidate extends DoeStableChoiceCandidate {
  priority: number;
  logit: number;
}

export interface DoeStableChoiceTrigger {
  mode: DoeStableChoiceTriggerMode;
  epsilon?: number | null;
}

export interface DoeStableChoiceReceipt {
  mode: "stable-choice";
  policyRegistryPath: string;
  policyRegistryVersion: string;
  comparator: "scalar-f32-greedy";
  baseRuleId: string;
  evaluatorKind: DoeStableChoiceEvaluatorKind;
  policyId: string;
  triggerPolicyId: string | null;
  candidateSetId: string | null;
  candidateSetSource: DoeStableChoiceCandidateSetSource | null;
  sourceKind: "host-bytes" | "buffer-readback";
  vocabSize: number;
  bytesRead: number;
  logitsSha256: string;
  token: number;
  stableTokenToken: number;
  stableTokenTiedMaxCount: number;
  stableTokenTiedMaxIndicesPrefix: number[];
  stableTokenTiedMaxIndicesOmittedCount: number;
  ambiguityTrigger: {
    mode: DoeStableChoiceTriggerMode;
    epsilon: number | null;
  };
  ambiguityTriggered: boolean;
  ambiguityTopGap: number;
  selectedBy: DoeStableChoiceSelectedBy;
  candidateSet: DoeStableChoiceReceiptCandidate[];
  ambiguousCandidateCount: number;
  ambiguousCandidateIndicesPrefix: number[];
  ambiguousCandidateIndicesOmittedCount: number;
  topCandidates: DoeStableTokenTopCandidate[];
  proofLinks: DoeDeterminismProofLink[];
}

export interface DoeStableChoiceResult {
  token: number;
  receipt: DoeStableChoiceReceipt;
}

export interface DoeStableChoiceOptions<TBuffer> extends DoeReadBufferSubrangeOptions {
  logits: TBuffer | ArrayBufferView | ArrayBuffer;
  vocabSize?: number;
  topCandidates?: number;
  candidates: Array<number | DoeStableChoiceCandidate>;
  ambiguityTrigger: DoeStableChoiceTrigger;
  policyId?: string;
  triggerPolicyId?: string;
  candidateSetId?: string;
  candidateSetSource?: DoeStableChoiceCandidateSetSource;
}

export type DoeReviewedChoiceEvaluatorKind = "explicit-review-decision";
export type DoeReviewedChoiceSelectedBy = "reviewed-choice-decision" | "stable-token-fallback";
export type DoeReviewedChoiceDecisionAcceptanceReason =
  | "reviewed-choice-decision"
  | "stable-token-fallback/not-triggered"
  | "stable-token-fallback/not-in-candidate-set"
  | "stable-token-fallback/not-ambiguous";

export interface DoeReviewedChoiceDecision extends DoeStableChoiceCandidate {
  reviewerId: string;
  decisionId?: string | null;
  decisionRef?: string | null;
  signature?: string | null;
}

export interface DoeReviewedChoiceReceiptDecision extends DoeReviewedChoiceDecision {}

export interface DoeReviewedChoiceReceipt {
  mode: "reviewed-choice";
  policyRegistryPath: string;
  policyRegistryVersion: string;
  comparator: "scalar-f32-greedy";
  baseRuleId: string;
  evaluatorKind: DoeReviewedChoiceEvaluatorKind;
  reviewPolicyId: string;
  triggerPolicyId: string | null;
  candidateSetId: string | null;
  candidateSetSource: DoeStableChoiceCandidateSetSource | null;
  sourceKind: "host-bytes" | "buffer-readback";
  vocabSize: number;
  bytesRead: number;
  logitsSha256: string;
  token: number;
  stableTokenToken: number;
  stableTokenTiedMaxCount: number;
  stableTokenTiedMaxIndicesPrefix: number[];
  stableTokenTiedMaxIndicesOmittedCount: number;
  ambiguityTrigger: {
    mode: DoeStableChoiceTriggerMode;
    epsilon: number | null;
  };
  ambiguityTriggered: boolean;
  ambiguityTopGap: number;
  selectedBy: DoeReviewedChoiceSelectedBy;
  decision: DoeReviewedChoiceReceiptDecision;
  decisionAccepted: boolean;
  decisionAcceptanceReason: DoeReviewedChoiceDecisionAcceptanceReason;
  candidateSet: DoeStableChoiceReceiptCandidate[];
  ambiguousCandidateCount: number;
  ambiguousCandidateIndicesPrefix: number[];
  ambiguousCandidateIndicesOmittedCount: number;
  topCandidates: DoeStableTokenTopCandidate[];
  proofLinks: DoeDeterminismProofLink[];
}

export interface DoeReviewedChoiceResult {
  token: number;
  receipt: DoeReviewedChoiceReceipt;
}

export interface DoeReviewedChoiceOptions<TBuffer> extends DoeReadBufferSubrangeOptions {
  logits: TBuffer | ArrayBufferView | ArrayBuffer;
  vocabSize?: number;
  topCandidates?: number;
  candidates: Array<number | DoeStableChoiceCandidate>;
  ambiguityTrigger: DoeStableChoiceTrigger;
  reviewPolicyId?: string;
  triggerPolicyId?: string;
  candidateSetId?: string;
  candidateSetSource?: DoeStableChoiceCandidateSetSource;
  decision: DoeReviewedChoiceDecision;
}

export type DoeNumericStabilityRouteDecision =
  | "accept-fast"
  | "prefer-stable"
  | "abstain";

export type DoeNumericStabilitySelectionMode =
  | "fast"
  | "stable"
  | "none";

export type DoeNumericStabilityDownstreamAction =
  | "continue"
  | "stop";

export interface DoeNumericStabilityCandidateInput {
  tokenId: number;
  label?: string | null;
  weights: ReadonlyArray<number> | Float32Array | Float64Array;
  bias?: number | null;
}

export interface DoeNumericStabilityReceiptCandidate {
  tokenId: number;
  label?: string | null;
  fastLogit: number;
  stableLogit: number;
  referenceLogit: number;
}

export interface DoeNumericStabilityFirstDivergence {
  semanticOpId: string;
  semanticStage: string;
  semanticPhase: string;
  fastDigest: string;
  stableDigest: string;
}

export interface DoeNumericStabilityExecutionIdentity {
  kernelPath?: string | null;
  kernelBasename?: string | null;
  layoutFingerprint?: string | null;
  compiledPlanHash?: string | null;
  backend?: string | null;
  backendLane?: string | null;
  adapterOrdinal?: number | null;
  queueFamilyIndex?: number | null;
  presentCapable?: boolean | null;
  profileVendor?: string | null;
  profileApi?: string | null;
  profileFamily?: string | null;
  profileDriver?: string | null;
  selectionPolicyHash?: string | null;
  hostPlanArtifactHash?: string | null;
}

export interface DoeNumericStabilityUpstreamReceiptLink {
  semanticOpId: string;
  semanticStage: string;
  semanticPhase: string;
  selectedPolicyId?: string | null;
  decision: DoeNumericStabilityRouteDecision;
}

export interface DoeNumericStabilityDecodeBoundaryReceipt {
  decodeMode: string;
  logitsCoverage: string;
  vocabSize: number;
  residualMassUpperBound?: number | null;
  temperature?: number | null;
  topK?: number | null;
  topP?: number | null;
  rngSeed?: number | null;
  rngDraw?: number | null;
  survivingTokenSetKind: string;
  survivingTokenIds?: number[] | null;
  liveSelectedToken: number;
  liveSelectedMatchesCommittedSelection: boolean;
  metrics: {
    fastTop1Margin: number;
    stableTop1Margin: number;
    referenceTop1Margin: number;
    topKBoundaryGap?: number | null;
    topPBoundaryGap?: number | null;
    cdfDistanceToDraw?: number | null;
    adjacentDecodePersistence?: number | null;
    actualSelectedTokenChanged: boolean;
    liveSelectedMatchesFast: boolean;
    liveSelectedMatchesStable: boolean;
    liveSelectedMatchesReference: boolean;
  };
  upstreamLinks: DoeNumericStabilityUpstreamReceiptLink[];
}

export interface DoeNumericStabilityReceipt {
  schemaVersion: 1;
  mode: "numeric-stability";
  operatorFamily: string;
  semanticOpId: string;
  semanticStage: string;
  semanticPhase: string;
  policyRegistryPath: string;
  policyRegistryVersion: string;
  routeTaxonomyVersion: string;
  proofArtifactPath: string;
  triggerPolicyId: string;
  routingPolicyId: string;
  fastPolicyId: string;
  stablePolicyId: string;
  referencePolicyId: string;
  candidates: DoeNumericStabilityReceiptCandidate[];
  executionIdentity?: DoeNumericStabilityExecutionIdentity | null;
  firstDivergence?: DoeNumericStabilityFirstDivergence | null;
  decodeBoundary?: DoeNumericStabilityDecodeBoundaryReceipt | null;
  selectedToken: {
    fast: number;
    stable: number;
    reference: number;
    fastMatchesReference: boolean;
    stableMatchesReference: boolean;
  };
  trigger: {
    fired: boolean;
    checks: {
      firstDivergencePresent: boolean;
      sensitiveOperatorMatched: boolean;
      selectedTokenDisagreement: boolean;
      stableMatchesExactReference: boolean;
      fastMissesExactReference: boolean;
    };
    proofLinks: DoeDeterminismProofLink[];
  };
  route: {
    decision: DoeNumericStabilityRouteDecision;
    selectionMode: DoeNumericStabilitySelectionMode;
    committedResultMode: DoeNumericStabilitySelectionMode;
    downstreamAction: DoeNumericStabilityDownstreamAction;
    effectApplied: boolean;
    selectedPolicyId?: string | null;
    selectedToken?: number | null;
    proofLinks: DoeDeterminismProofLink[];
    selectionProofLinks: DoeDeterminismProofLink[];
  };
}

export interface DoeMatmulLogitsSliceOptions<TBuffer> {
  hiddenState: ReadonlyArray<number> | Float32Array | Float64Array;
  candidates: DoeNumericStabilityCandidateInput[];
  operatorFamily?: string;
  semanticOpId?: string;
  semanticStage?: string;
  semanticPhase?: string;
  triggerPolicyId?: string;
  routingPolicyId?: string;
  fastPolicyId?: string;
  stablePolicyId?: string;
  runtime?: {
    runNumericStabilityMatmulLogitsSlice(
      options: Record<string, unknown>,
    ): {
      token: number | null;
      routeDecision: DoeNumericStabilityRouteDecision;
      receipt: DoeNumericStabilityReceipt;
    };
  } | null;
  runtimeOptions?: {
    binPath?: string;
    libPath?: string;
    moduleRunnerPath?: string;
  } | null;
  policyPath?: string | null;
  moduleRunnerPath?: string | null;
  receiptPath?: string | null;
  traceMetaPath?: string | null;
  cwd?: string | null;
}

export interface DoeMatmulLogitsSliceResult {
  token: number | null;
  routeDecision: DoeNumericStabilityRouteDecision;
  receipt: DoeNumericStabilityReceipt;
}

export interface DoeNumericStabilityOrdinaryExecutionResult {
  traceJsonlPath: string | null;
  traceMetaPath: string | null;
  traceMeta: Record<string, unknown> | null;
  executionProfileId: string | null;
  receiptPath: string | null;
  receipts: DoeNumericStabilityReceipt[];
  routeDecisions: DoeNumericStabilityRouteDecision[];
  latestReceipt: DoeNumericStabilityReceipt | null;
  latestRouteDecision: DoeNumericStabilityRouteDecision | null;
  latestToken: number | null;
}

export interface DoeOrdinaryExecutionOptions
  extends DoeNumericStabilityOrdinaryExecutionOptions {}

export interface DoeOrdinaryExecutionResult
  extends DoeNumericStabilityOrdinaryExecutionResult {}

export interface DoeNumericStabilityOrdinaryExecutionOptions {
  commandsPath: string;
  quirksPath?: string | null;
  kernelRoot?: string | null;
  vendor?: string | null;
  api?: string | null;
  family?: string | null;
  driver?: string | null;
  backendLane?: string | null;
  traceJsonlPath?: string | null;
  traceMetaPath?: string | null;
  uploadBufferUsage?: string | null;
  uploadSubmitEvery?: number | null;
  queueWaitMode?: string | null;
  queueSyncMode?: string | null;
  extraArgs?: string[] | null;
  runtime?: {
    runNumericStabilityOrdinaryExecution(
      options: Record<string, unknown>,
    ): DoeNumericStabilityOrdinaryExecutionResult;
  } | null;
  runtimeOptions?: {
    binPath?: string;
    libPath?: string;
    moduleRunnerPath?: string;
  } | null;
  policyPath?: string | null;
  executionProfileId?: string | null;
  cwd?: string | null;
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

export interface BoundDoeDeterminismNamespace<TBuffer> {
  stableToken(options: DoeStableTokenOptions<TBuffer>): Promise<DoeStableTokenResult>;
  stableChoice(options: DoeStableChoiceOptions<TBuffer>): Promise<DoeStableChoiceResult>;
  reviewedChoice(options: DoeReviewedChoiceOptions<TBuffer>): Promise<DoeReviewedChoiceResult>;
}

export interface BoundDoeNumericStabilityNamespace<TBuffer> {
  matmulLogitsSlice(
    options: DoeMatmulLogitsSliceOptions<TBuffer>,
  ): Promise<DoeMatmulLogitsSliceResult>;
  ordinaryExecution(
    options: DoeNumericStabilityOrdinaryExecutionOptions,
  ): Promise<DoeNumericStabilityOrdinaryExecutionResult>;
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
  readonly determinism: BoundDoeDeterminismNamespace<TBuffer>;
  readonly numericStability: BoundDoeNumericStabilityNamespace<TBuffer>;
  ordinaryExecution(
    options: DoeOrdinaryExecutionOptions,
  ): Promise<DoeOrdinaryExecutionResult>;
  readonly commandEncoder: BoundDoeCommandEncoderNamespace<TEncoder>;
  readonly kernel: BoundDoeKernelNamespace<TBuffer, TKernel, TBindingSet>;
  readonly compute: BoundDoeComputeCallable<TBuffer, TBatch>;
}

export interface DoeNamespace<
  TDevice,
  TBoundDoe,
  TRequestDeviceOptions = unknown,
> {
  ordinaryExecution(
    options: DoeOrdinaryExecutionOptions,
  ): Promise<DoeOrdinaryExecutionResult>;
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
