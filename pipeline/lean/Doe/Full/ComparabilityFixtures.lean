import Doe.Full.Comparability

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
    baselineComparisonTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    baselineComparisonTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    baselineComparisonTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    baselineComparisonQueueSyncModeMatch := true
    submitScopeMatchApplies := true
    baselineComparisonSubmitScopeMatch := true
    timingPhaseMatchApplies := true
    baselineComparisonTimingPhaseMatch := true
    executionShapeMatchApplies := true
    baselineComparisonExecutionShapeMatch := true
    hardwarePathMatchApplies := true
    baselineComparisonHardwarePathMatch := true
    explicitNativeShaderArtifactMatchApplies := false
    baselineComparisonExplicitNativeShaderArtifactMatch := true
    operationTimingClassRequired := true
    baselineNativeOperationTimingForWebgpuFfi := true
    uploadDomain := true
    baselineUploadIgnoreFirstScopeConsistent := true
    comparisonUploadIgnoreFirstScopeConsistent := true
    baselineComparisonUploadBufferUsageMatch := true
    baselineComparisonUploadSubmitCadenceMatch := true
    allowBaselineNoExecution := false
    baselineExecutionEvidencePresent := true
    baselineSuccessfulExecutionPresent := true
    baselineSuccessOrUnsupportedOrSkipped := false
    baselineExecutionErrorsAbsent := true
    comparisonExecutionErrorsAbsent := true
    baselineComparisonTimingPlausibility := true
    resourceProbeEnabled := true
    baselineResourceProbeAvailable := true
    comparisonResourceProbeAvailable := true
    strictComparability := true
    resourceSampleTargetPositive := true
    baselineResourceSampleTargetMatch := true
    comparisonResourceSampleTargetMatch := true
    baselineResourceSamplingNotTruncated := true
    comparisonResourceSamplingNotTruncated := true
    baselineResourceSampleDensitySufficient := false
    comparisonResourceSampleDensitySufficient := false
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
    baselineComparisonTimingClassMatch := false
    traceMetaSourceMatchApplies := false
    baselineComparisonTraceMetaSourceMatch := false
    timingSelectionPolicyMatchApplies := false
    baselineComparisonTimingSelectionPolicyMatch := false
    queueSyncModeMatchApplies := false
    baselineComparisonQueueSyncModeMatch := false
    submitScopeMatchApplies := false
    baselineComparisonSubmitScopeMatch := false
    timingPhaseMatchApplies := false
    baselineComparisonTimingPhaseMatch := false
    executionShapeMatchApplies := false
    baselineComparisonExecutionShapeMatch := false
    hardwarePathMatchApplies := false
    baselineComparisonHardwarePathMatch := true
    explicitNativeShaderArtifactMatchApplies := false
    baselineComparisonExplicitNativeShaderArtifactMatch := true
    operationTimingClassRequired := true
    baselineNativeOperationTimingForWebgpuFfi := true
    uploadDomain := false
    baselineUploadIgnoreFirstScopeConsistent := true
    comparisonUploadIgnoreFirstScopeConsistent := true
    baselineComparisonUploadBufferUsageMatch := true
    baselineComparisonUploadSubmitCadenceMatch := true
    allowBaselineNoExecution := false
    baselineExecutionEvidencePresent := false
    baselineSuccessfulExecutionPresent := false
    baselineSuccessOrUnsupportedOrSkipped := false
    baselineExecutionErrorsAbsent := true
    comparisonExecutionErrorsAbsent := true
    baselineComparisonTimingPlausibility := true
    resourceProbeEnabled := false
    baselineResourceProbeAvailable := false
    comparisonResourceProbeAvailable := false
    strictComparability := true
    resourceSampleTargetPositive := false
    baselineResourceSampleTargetMatch := false
    comparisonResourceSampleTargetMatch := false
    baselineResourceSamplingNotTruncated := false
    comparisonResourceSamplingNotTruncated := false
    baselineResourceSampleDensitySufficient := false
    comparisonResourceSampleDensitySufficient := false
  }

def strictMissingLeftSamplesExpectedBlocking : List ComparabilityObligationId :=
  [ .leftSamplesPresent
  , .leftSingleTimingClass
  , .leftRequiredTimingClass
  , .baselineExecutionEvidencePresent
  , .baselineSuccessfulExecutionPresent
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
    baselineComparisonTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    baselineComparisonTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    baselineComparisonTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    baselineComparisonQueueSyncModeMatch := true
    submitScopeMatchApplies := false
    baselineComparisonSubmitScopeMatch := true
    timingPhaseMatchApplies := false
    baselineComparisonTimingPhaseMatch := false
    executionShapeMatchApplies := true
    baselineComparisonExecutionShapeMatch := true
    hardwarePathMatchApplies := false
    baselineComparisonHardwarePathMatch := true
    explicitNativeShaderArtifactMatchApplies := false
    baselineComparisonExplicitNativeShaderArtifactMatch := true
    operationTimingClassRequired := true
    baselineNativeOperationTimingForWebgpuFfi := true
    uploadDomain := false
    baselineUploadIgnoreFirstScopeConsistent := true
    comparisonUploadIgnoreFirstScopeConsistent := true
    baselineComparisonUploadBufferUsageMatch := true
    baselineComparisonUploadSubmitCadenceMatch := true
    allowBaselineNoExecution := true
    baselineExecutionEvidencePresent := false
    baselineSuccessfulExecutionPresent := false
    baselineSuccessOrUnsupportedOrSkipped := true
    baselineExecutionErrorsAbsent := true
    comparisonExecutionErrorsAbsent := true
    baselineComparisonTimingPlausibility := true
    resourceProbeEnabled := true
    baselineResourceProbeAvailable := true
    comparisonResourceProbeAvailable := true
    strictComparability := false
    resourceSampleTargetPositive := false
    baselineResourceSampleTargetMatch := false
    comparisonResourceSampleTargetMatch := false
    baselineResourceSamplingNotTruncated := false
    comparisonResourceSamplingNotTruncated := false
    baselineResourceSampleDensitySufficient := false
    comparisonResourceSampleDensitySufficient := true
  }

def allowLeftNoExecutionDensityFailureExpectedBlocking : List ComparabilityObligationId :=
  [ .baselineResourceSampleDensitySufficient ]

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
    baselineComparisonTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    baselineComparisonTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    baselineComparisonTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    baselineComparisonQueueSyncModeMatch := true
    submitScopeMatchApplies := false
    baselineComparisonSubmitScopeMatch := true
    timingPhaseMatchApplies := true
    baselineComparisonTimingPhaseMatch := false
    executionShapeMatchApplies := true
    baselineComparisonExecutionShapeMatch := true
    hardwarePathMatchApplies := false
    baselineComparisonHardwarePathMatch := true
    explicitNativeShaderArtifactMatchApplies := false
    baselineComparisonExplicitNativeShaderArtifactMatch := true
    operationTimingClassRequired := true
    baselineNativeOperationTimingForWebgpuFfi := true
    uploadDomain := true
    baselineUploadIgnoreFirstScopeConsistent := true
    comparisonUploadIgnoreFirstScopeConsistent := true
    baselineComparisonUploadBufferUsageMatch := true
    baselineComparisonUploadSubmitCadenceMatch := true
    allowBaselineNoExecution := false
    baselineExecutionEvidencePresent := true
    baselineSuccessfulExecutionPresent := true
    baselineSuccessOrUnsupportedOrSkipped := false
    baselineExecutionErrorsAbsent := true
    comparisonExecutionErrorsAbsent := true
    baselineComparisonTimingPlausibility := true
    resourceProbeEnabled := false
    baselineResourceProbeAvailable := false
    comparisonResourceProbeAvailable := false
    strictComparability := true
    resourceSampleTargetPositive := false
    baselineResourceSampleTargetMatch := false
    comparisonResourceSampleTargetMatch := false
    baselineResourceSamplingNotTruncated := false
    comparisonResourceSamplingNotTruncated := false
    baselineResourceSampleDensitySufficient := false
    comparisonResourceSampleDensitySufficient := false
  }

def strictTimingPhaseFailureExpectedBlocking : List ComparabilityObligationId :=
  [ .baselineComparisonTimingPhaseMatch ]

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
    baselineComparisonTimingClassMatch := true
    traceMetaSourceMatchApplies := true
    baselineComparisonTraceMetaSourceMatch := true
    timingSelectionPolicyMatchApplies := true
    baselineComparisonTimingSelectionPolicyMatch := true
    queueSyncModeMatchApplies := true
    baselineComparisonQueueSyncModeMatch := true
    submitScopeMatchApplies := false
    baselineComparisonSubmitScopeMatch := true
    timingPhaseMatchApplies := true
    baselineComparisonTimingPhaseMatch := true
    executionShapeMatchApplies := true
    baselineComparisonExecutionShapeMatch := true
    hardwarePathMatchApplies := true
    baselineComparisonHardwarePathMatch := false
    explicitNativeShaderArtifactMatchApplies := false
    baselineComparisonExplicitNativeShaderArtifactMatch := true
    operationTimingClassRequired := true
    baselineNativeOperationTimingForWebgpuFfi := true
    uploadDomain := true
    baselineUploadIgnoreFirstScopeConsistent := true
    comparisonUploadIgnoreFirstScopeConsistent := true
    baselineComparisonUploadBufferUsageMatch := true
    baselineComparisonUploadSubmitCadenceMatch := true
    allowBaselineNoExecution := false
    baselineExecutionEvidencePresent := true
    baselineSuccessfulExecutionPresent := true
    baselineSuccessOrUnsupportedOrSkipped := false
    baselineExecutionErrorsAbsent := true
    comparisonExecutionErrorsAbsent := true
    baselineComparisonTimingPlausibility := true
    resourceProbeEnabled := false
    baselineResourceProbeAvailable := false
    comparisonResourceProbeAvailable := false
    strictComparability := true
    resourceSampleTargetPositive := false
    baselineResourceSampleTargetMatch := false
    comparisonResourceSampleTargetMatch := false
    baselineResourceSamplingNotTruncated := false
    comparisonResourceSamplingNotTruncated := false
    baselineResourceSampleDensitySufficient := false
    comparisonResourceSampleDensitySufficient := false
  }

def strictHardwarePathFailureExpectedBlocking : List ComparabilityObligationId :=
  [ .baselineComparisonHardwarePathMatch ]

theorem strictHardwarePathFailureExpectedBlocking_exact :
    (failedBlockingObligations (obligationsFromFacts strictHardwarePathFailureFacts)).map
      (fun item => item.id) = strictHardwarePathFailureExpectedBlocking := by
  native_decide

theorem strictHardwarePathFailureComparable :
    comparableFromFacts strictHardwarePathFailureFacts = false := by
  native_decide
