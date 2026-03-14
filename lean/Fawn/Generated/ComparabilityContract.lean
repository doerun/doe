import Fawn.Core.Model

def comparabilityContractSha256 : String := "68598321d000d069f8d95eef213dcfe0dc2559a24a35275d06d2c4dda4b9d10c"

inductive ComparabilityObligationId where
  | workloadMarkedComparable
  | leftSamplesPresent
  | rightSamplesPresent
  | leftSingleTimingClass
  | rightSingleTimingClass
  | leftRequiredTimingClass
  | rightRequiredTimingClass
  | leftRightTimingClassMatch
  | leftRightTraceMetaSourceMatch
  | leftRightTimingSelectionPolicyMatch
  | leftRightQueueSyncModeMatch
  | leftRightTimingPhaseMatch
  | leftRightExecutionShapeMatch
  | leftRightHardwarePathMatch
  | leftNativeOperationTimingForWebgpuFfi
  | leftUploadIgnoreFirstScopeConsistent
  | rightUploadIgnoreFirstScopeConsistent
  | leftRightUploadBufferUsageMatch
  | leftRightUploadSubmitCadenceMatch
  | leftExecutionEvidencePresent
  | leftSuccessfulExecutionPresent
  | leftSuccessOrUnsupportedOrSkipped
  | leftExecutionErrorsAbsent
  | rightExecutionErrorsAbsent
  | leftResourceProbeAvailable
  | rightResourceProbeAvailable
  | strictResourceSampleTargetPositive
  | leftResourceSampleTargetMatch
  | rightResourceSampleTargetMatch
  | leftResourceSamplingNotTruncated
  | rightResourceSamplingNotTruncated
  | leftResourceSampleDensitySufficient
  | rightResourceSampleDensitySufficient
  deriving Repr, DecidableEq

structure ComparabilityObligation where
  id : ComparabilityObligationId
  blocking : Bool
  applicable : Bool
  passes : Bool
  deriving Repr, DecidableEq

def isFailedBlocking (item : ComparabilityObligation) : Bool :=
  item.blocking && item.applicable && !item.passes

def failedBlockingObligations (items : List ComparabilityObligation) : List ComparabilityObligation :=
  items.filter isFailedBlocking

def comparableFromObligations (items : List ComparabilityObligation) : Bool :=
  (failedBlockingObligations items).isEmpty

structure ComparabilityFacts where
  workloadMarkedComparable : Bool
  leftSamplesPresent : Bool
  rightSamplesPresent : Bool
  leftSingleTimingClass : Bool
  rightSingleTimingClass : Bool
  requiredTimingClassApplies : Bool
  leftRequiredTimingClass : Bool
  rightRequiredTimingClass : Bool
  timingClassMatchApplies : Bool
  leftRightTimingClassMatch : Bool
  traceMetaSourceMatchApplies : Bool
  leftRightTraceMetaSourceMatch : Bool
  timingSelectionPolicyMatchApplies : Bool
  leftRightTimingSelectionPolicyMatch : Bool
  queueSyncModeMatchApplies : Bool
  leftRightQueueSyncModeMatch : Bool
  timingPhaseMatchApplies : Bool
  leftRightTimingPhaseMatch : Bool
  executionShapeMatchApplies : Bool
  leftRightExecutionShapeMatch : Bool
  hardwarePathMatchApplies : Bool
  leftRightHardwarePathMatch : Bool
  operationTimingClassRequired : Bool
  leftNativeOperationTimingForWebgpuFfi : Bool
  uploadDomain : Bool
  leftUploadIgnoreFirstScopeConsistent : Bool
  rightUploadIgnoreFirstScopeConsistent : Bool
  leftRightUploadBufferUsageMatch : Bool
  leftRightUploadSubmitCadenceMatch : Bool
  allowLeftNoExecution : Bool
  leftExecutionEvidencePresent : Bool
  leftSuccessfulExecutionPresent : Bool
  leftSuccessOrUnsupportedOrSkipped : Bool
  leftExecutionErrorsAbsent : Bool
  rightExecutionErrorsAbsent : Bool
  resourceProbeEnabled : Bool
  leftResourceProbeAvailable : Bool
  rightResourceProbeAvailable : Bool
  strictComparability : Bool
  resourceSampleTargetPositive : Bool
  leftResourceSampleTargetMatch : Bool
  rightResourceSampleTargetMatch : Bool
  leftResourceSamplingNotTruncated : Bool
  rightResourceSamplingNotTruncated : Bool
  leftResourceSampleDensitySufficient : Bool
  rightResourceSampleDensitySufficient : Bool
  deriving Repr, DecidableEq

def obligationsFromFacts (facts : ComparabilityFacts) : List ComparabilityObligation :=
  [
    { id := .workloadMarkedComparable
      blocking := true
      applicable := true
      passes := facts.workloadMarkedComparable },
    { id := .leftSamplesPresent
      blocking := true
      applicable := true
      passes := facts.leftSamplesPresent },
    { id := .rightSamplesPresent
      blocking := true
      applicable := true
      passes := facts.rightSamplesPresent },
    { id := .leftSingleTimingClass
      blocking := true
      applicable := true
      passes := facts.leftSingleTimingClass },
    { id := .rightSingleTimingClass
      blocking := true
      applicable := true
      passes := facts.rightSingleTimingClass },
    { id := .leftRequiredTimingClass
      blocking := true
      applicable := facts.requiredTimingClassApplies
      passes := facts.leftRequiredTimingClass },
    { id := .rightRequiredTimingClass
      blocking := true
      applicable := facts.requiredTimingClassApplies
      passes := facts.rightRequiredTimingClass },
    { id := .leftRightTimingClassMatch
      blocking := true
      applicable := facts.timingClassMatchApplies
      passes := facts.leftRightTimingClassMatch },
    { id := .leftRightTraceMetaSourceMatch
      blocking := true
      applicable := facts.traceMetaSourceMatchApplies
      passes := facts.leftRightTraceMetaSourceMatch },
    { id := .leftRightTimingSelectionPolicyMatch
      blocking := true
      applicable := facts.timingSelectionPolicyMatchApplies
      passes := facts.leftRightTimingSelectionPolicyMatch },
    { id := .leftRightQueueSyncModeMatch
      blocking := true
      applicable := facts.queueSyncModeMatchApplies
      passes := facts.leftRightQueueSyncModeMatch },
    { id := .leftRightTimingPhaseMatch
      blocking := true
      applicable := facts.timingPhaseMatchApplies
      passes := facts.leftRightTimingPhaseMatch },
    { id := .leftRightExecutionShapeMatch
      blocking := true
      applicable := facts.executionShapeMatchApplies
      passes := facts.leftRightExecutionShapeMatch },
    { id := .leftRightHardwarePathMatch
      blocking := true
      applicable := facts.hardwarePathMatchApplies
      passes := facts.leftRightHardwarePathMatch },
    { id := .leftNativeOperationTimingForWebgpuFfi
      blocking := true
      applicable := facts.operationTimingClassRequired
      passes := facts.leftNativeOperationTimingForWebgpuFfi },
    { id := .leftUploadIgnoreFirstScopeConsistent
      blocking := true
      applicable := facts.uploadDomain
      passes := facts.leftUploadIgnoreFirstScopeConsistent },
    { id := .rightUploadIgnoreFirstScopeConsistent
      blocking := true
      applicable := facts.uploadDomain
      passes := facts.rightUploadIgnoreFirstScopeConsistent },
    { id := .leftRightUploadBufferUsageMatch
      blocking := true
      applicable := facts.uploadDomain
      passes := facts.leftRightUploadBufferUsageMatch },
    { id := .leftRightUploadSubmitCadenceMatch
      blocking := true
      applicable := facts.uploadDomain
      passes := facts.leftRightUploadSubmitCadenceMatch },
    { id := .leftExecutionEvidencePresent
      blocking := true
      applicable := !(facts.allowLeftNoExecution)
      passes := facts.leftExecutionEvidencePresent },
    { id := .leftSuccessfulExecutionPresent
      blocking := true
      applicable := !(facts.allowLeftNoExecution)
      passes := facts.leftSuccessfulExecutionPresent },
    { id := .leftSuccessOrUnsupportedOrSkipped
      blocking := true
      applicable := facts.allowLeftNoExecution
      passes := facts.leftSuccessOrUnsupportedOrSkipped },
    { id := .leftExecutionErrorsAbsent
      blocking := true
      applicable := true
      passes := facts.leftExecutionErrorsAbsent },
    { id := .rightExecutionErrorsAbsent
      blocking := true
      applicable := true
      passes := facts.rightExecutionErrorsAbsent },
    { id := .leftResourceProbeAvailable
      blocking := true
      applicable := facts.resourceProbeEnabled
      passes := facts.leftResourceProbeAvailable },
    { id := .rightResourceProbeAvailable
      blocking := true
      applicable := facts.resourceProbeEnabled
      passes := facts.rightResourceProbeAvailable },
    { id := .strictResourceSampleTargetPositive
      blocking := true
      applicable := (facts.resourceProbeEnabled) && (facts.strictComparability)
      passes := facts.resourceSampleTargetPositive },
    { id := .leftResourceSampleTargetMatch
      blocking := true
      applicable := (facts.resourceProbeEnabled) && (facts.strictComparability) && (facts.resourceSampleTargetPositive)
      passes := facts.leftResourceSampleTargetMatch },
    { id := .rightResourceSampleTargetMatch
      blocking := true
      applicable := (facts.resourceProbeEnabled) && (facts.strictComparability) && (facts.resourceSampleTargetPositive)
      passes := facts.rightResourceSampleTargetMatch },
    { id := .leftResourceSamplingNotTruncated
      blocking := true
      applicable := (facts.resourceProbeEnabled) && (facts.strictComparability) && (facts.resourceSampleTargetPositive)
      passes := facts.leftResourceSamplingNotTruncated },
    { id := .rightResourceSamplingNotTruncated
      blocking := true
      applicable := (facts.resourceProbeEnabled) && (facts.strictComparability) && (facts.resourceSampleTargetPositive)
      passes := facts.rightResourceSamplingNotTruncated },
    { id := .leftResourceSampleDensitySufficient
      blocking := true
      applicable := (facts.resourceProbeEnabled) && (!(facts.strictComparability))
      passes := facts.leftResourceSampleDensitySufficient },
    { id := .rightResourceSampleDensitySufficient
      blocking := true
      applicable := (facts.resourceProbeEnabled) && (!(facts.strictComparability))
      passes := facts.rightResourceSampleDensitySufficient }
  ]

def comparableFromFacts (facts : ComparabilityFacts) : Bool :=
  comparableFromObligations (obligationsFromFacts facts)
