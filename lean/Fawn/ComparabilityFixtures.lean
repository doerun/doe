import Fawn.Comparability

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
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := true
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
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
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := false
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
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
    operationTimingClassRequired := true
    leftNativeOperationTimingForWebgpuFfi := true
    uploadDomain := false
    leftUploadIgnoreFirstScopeConsistent := true
    rightUploadIgnoreFirstScopeConsistent := true
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
