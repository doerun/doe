import Fawn.Full.Comparability

def strictHappyPathFacts : ComparabilityFacts :=
  { workloadMarkedComparable := true
    leftSamplesPresent := true
    rightSamplesPresent := true
    leftSingleTimingClass := true
    rightSingleTimingClass := true
    requiredTimingClassApplies := true
    leftRequiredTimingClass := true
    rightRequiredTimingClass := true
    timingClassMatchApplies := true
    leftRightTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    leftRightTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    leftRightTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    leftRightQueueSyncModeMatch := true
    timingPhaseMatchApplies := true
    leftRightTimingPhaseMatch := true
    executionShapeMatchApplies := true
    leftRightExecutionShapeMatch := true
    hardwarePathMatchApplies := true
    leftRightHardwarePathMatch := true
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := true
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
    leftRightUploadBufferUsageMatch := true
    leftRightUploadSubmitCadenceMatch := true
    allowLeftNoExecution := false
    leftExecutionEvidencePresent := true
    leftSuccessfulExecutionPresent := true
    leftSuccessOrUnsupportedOrSkipped := false
    leftExecutionErrorsAbsent := true
    rightExecutionErrorsAbsent := true
    resourceProbeEnabled := true
    leftResourceProbeAvailable := true
    rightResourceProbeAvailable := true
    strictComparability := true
    resourceSampleTargetPositive := true
    leftResourceSampleTargetMatch := true
    rightResourceSampleTargetMatch := true
    leftResourceSamplingNotTruncated := true
    rightResourceSamplingNotTruncated := true
    leftResourceSampleDensitySufficient := false
    rightResourceSampleDensitySufficient := false
  }

def strictHappyPathExpectedBlocking : List ComparabilityObligationId := []

theorem strictHappyPathExpectedBlocking_exact :
    (failedBlockingObligations (obligationsFromFacts strictHappyPathFacts)).map (fun item => item.id)
      = strictHappyPathExpectedBlocking := by
  native_decide

theorem strictHappyPathComparable :
    comparableFromFacts strictHappyPathFacts = true := by
  native_decide

def strictMissingLeftSamplesFacts : ComparabilityFacts :=
  { workloadMarkedComparable := true
    leftSamplesPresent := false
    rightSamplesPresent := true
    leftSingleTimingClass := false
    rightSingleTimingClass := true
    requiredTimingClassApplies := true
    leftRequiredTimingClass := false
    rightRequiredTimingClass := true
    timingClassMatchApplies := false
    leftRightTimingClassMatch := false
    traceMetaSourceMatchApplies := false
    leftRightTraceMetaSourceMatch := false
    timingSelectionPolicyMatchApplies := false
    leftRightTimingSelectionPolicyMatch := false
    queueSyncModeMatchApplies := false
    leftRightQueueSyncModeMatch := false
    timingPhaseMatchApplies := false
    leftRightTimingPhaseMatch := false
    executionShapeMatchApplies := false
    leftRightExecutionShapeMatch := false
    hardwarePathMatchApplies := false
    leftRightHardwarePathMatch := true
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := false
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
    leftRightUploadBufferUsageMatch := true
    leftRightUploadSubmitCadenceMatch := true
    allowLeftNoExecution := false
    leftExecutionEvidencePresent := false
    leftSuccessfulExecutionPresent := false
    leftSuccessOrUnsupportedOrSkipped := false
    leftExecutionErrorsAbsent := true
    rightExecutionErrorsAbsent := true
    resourceProbeEnabled := false
    leftResourceProbeAvailable := false
    rightResourceProbeAvailable := false
    strictComparability := true
    resourceSampleTargetPositive := false
    leftResourceSampleTargetMatch := false
    rightResourceSampleTargetMatch := false
    leftResourceSamplingNotTruncated := false
    rightResourceSamplingNotTruncated := false
    leftResourceSampleDensitySufficient := false
    rightResourceSampleDensitySufficient := false
  }

def strictMissingLeftSamplesExpectedBlocking : List ComparabilityObligationId :=
  [ .leftSamplesPresent
  , .leftSingleTimingClass
  , .leftRequiredTimingClass
  , .leftExecutionEvidencePresent
  , .leftSuccessfulExecutionPresent
  ]

theorem strictMissingLeftSamplesExpectedBlocking_exact :
    (failedBlockingObligations (obligationsFromFacts strictMissingLeftSamplesFacts)).map (fun item => item.id)
      = strictMissingLeftSamplesExpectedBlocking := by
  native_decide

theorem strictMissingLeftSamplesComparable :
    comparableFromFacts strictMissingLeftSamplesFacts = false := by
  native_decide

def allowLeftNoExecutionDensityFailureFacts : ComparabilityFacts :=
  { workloadMarkedComparable := true
    leftSamplesPresent := true
    rightSamplesPresent := true
    leftSingleTimingClass := true
    rightSingleTimingClass := true
    requiredTimingClassApplies := true
    leftRequiredTimingClass := true
    rightRequiredTimingClass := true
    timingClassMatchApplies := true
    leftRightTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    leftRightTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    leftRightTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    leftRightQueueSyncModeMatch := true
    timingPhaseMatchApplies := false
    leftRightTimingPhaseMatch := false
    executionShapeMatchApplies := true
    leftRightExecutionShapeMatch := true
    hardwarePathMatchApplies := false
    leftRightHardwarePathMatch := true
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := false
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
    leftRightUploadBufferUsageMatch := true
    leftRightUploadSubmitCadenceMatch := true
    allowLeftNoExecution := true
    leftExecutionEvidencePresent := false
    leftSuccessfulExecutionPresent := false
    leftSuccessOrUnsupportedOrSkipped := true
    leftExecutionErrorsAbsent := true
    rightExecutionErrorsAbsent := true
    resourceProbeEnabled := true
    leftResourceProbeAvailable := true
    rightResourceProbeAvailable := true
    strictComparability := false
    resourceSampleTargetPositive := false
    leftResourceSampleTargetMatch := false
    rightResourceSampleTargetMatch := false
    leftResourceSamplingNotTruncated := false
    rightResourceSamplingNotTruncated := false
    leftResourceSampleDensitySufficient := false
    rightResourceSampleDensitySufficient := true
  }

def allowLeftNoExecutionDensityFailureExpectedBlocking : List ComparabilityObligationId :=
  [ .leftResourceSampleDensitySufficient ]

theorem allowLeftNoExecutionDensityFailureExpectedBlocking_exact :
    (failedBlockingObligations (obligationsFromFacts allowLeftNoExecutionDensityFailureFacts)).map
      (fun item => item.id) = allowLeftNoExecutionDensityFailureExpectedBlocking := by
  native_decide

theorem allowLeftNoExecutionDensityFailureComparable :
    comparableFromFacts allowLeftNoExecutionDensityFailureFacts = false := by
  native_decide

def strictTimingPhaseFailureFacts : ComparabilityFacts :=
  { workloadMarkedComparable := true
    leftSamplesPresent := true
    rightSamplesPresent := true
    leftSingleTimingClass := true
    rightSingleTimingClass := true
    requiredTimingClassApplies := true
    leftRequiredTimingClass := true
    rightRequiredTimingClass := true
    timingClassMatchApplies := true
    leftRightTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    leftRightTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    leftRightTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    leftRightQueueSyncModeMatch := true
    timingPhaseMatchApplies := true
    leftRightTimingPhaseMatch := false
    executionShapeMatchApplies := true
    leftRightExecutionShapeMatch := true
    hardwarePathMatchApplies := false
    leftRightHardwarePathMatch := true
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := true
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
    leftRightUploadBufferUsageMatch := true
    leftRightUploadSubmitCadenceMatch := true
    allowLeftNoExecution := false
    leftExecutionEvidencePresent := true
    leftSuccessfulExecutionPresent := true
    leftSuccessOrUnsupportedOrSkipped := false
    leftExecutionErrorsAbsent := true
    rightExecutionErrorsAbsent := true
    resourceProbeEnabled := false
    leftResourceProbeAvailable := false
    rightResourceProbeAvailable := false
    strictComparability := true
    resourceSampleTargetPositive := false
    leftResourceSampleTargetMatch := false
    rightResourceSampleTargetMatch := false
    leftResourceSamplingNotTruncated := false
    rightResourceSamplingNotTruncated := false
    leftResourceSampleDensitySufficient := false
    rightResourceSampleDensitySufficient := false
  }

def strictTimingPhaseFailureExpectedBlocking : List ComparabilityObligationId :=
  [ .leftRightTimingPhaseMatch ]

theorem strictTimingPhaseFailureExpectedBlocking_exact :
    (failedBlockingObligations (obligationsFromFacts strictTimingPhaseFailureFacts)).map
      (fun item => item.id) = strictTimingPhaseFailureExpectedBlocking := by
  native_decide

theorem strictTimingPhaseFailureComparable :
    comparableFromFacts strictTimingPhaseFailureFacts = false := by
  native_decide

def strictHardwarePathFailureFacts : ComparabilityFacts :=
  { workloadMarkedComparable := true
    leftSamplesPresent := true
    rightSamplesPresent := true
    leftSingleTimingClass := true
    rightSingleTimingClass := true
    requiredTimingClassApplies := true
    leftRequiredTimingClass := true
    rightRequiredTimingClass := true
    timingClassMatchApplies := true
    leftRightTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    leftRightTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    leftRightTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    leftRightQueueSyncModeMatch := true
    timingPhaseMatchApplies := true
    leftRightTimingPhaseMatch := true
    executionShapeMatchApplies := true
    leftRightExecutionShapeMatch := true
    hardwarePathMatchApplies := true
    leftRightHardwarePathMatch := false
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := true
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
    leftRightUploadBufferUsageMatch := true
    leftRightUploadSubmitCadenceMatch := true
    allowLeftNoExecution := false
    leftExecutionEvidencePresent := true
    leftSuccessfulExecutionPresent := true
    leftSuccessOrUnsupportedOrSkipped := false
    leftExecutionErrorsAbsent := true
    rightExecutionErrorsAbsent := true
    resourceProbeEnabled := false
    leftResourceProbeAvailable := false
    rightResourceProbeAvailable := false
    strictComparability := true
    resourceSampleTargetPositive := false
    leftResourceSampleTargetMatch := false
    rightResourceSampleTargetMatch := false
    leftResourceSamplingNotTruncated := false
    rightResourceSamplingNotTruncated := false
    leftResourceSampleDensitySufficient := false
    rightResourceSampleDensitySufficient := false
  }

def strictHardwarePathFailureExpectedBlocking : List ComparabilityObligationId :=
  [ .leftRightHardwarePathMatch ]

theorem strictHardwarePathFailureExpectedBlocking_exact :
    (failedBlockingObligations (obligationsFromFacts strictHardwarePathFailureFacts)).map
      (fun item => item.id) = strictHardwarePathFailureExpectedBlocking := by
  native_decide

theorem strictHardwarePathFailureComparable :
    comparableFromFacts strictHardwarePathFailureFacts = false := by
  native_decide
