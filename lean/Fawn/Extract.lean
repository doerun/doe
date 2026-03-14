import Fawn.Core.Bridge
import Fawn.Core.Dispatch
import Fawn.Full.ComparabilityFixtures

private def jsonBool (b : Bool) : String := if b then "true" else "false"

/-- Emit proof artifact as JSON to stdout.
    Compilation of this module verifies all imported theorems.
    Decidable propositions are additionally evaluated at runtime. -/
def main : IO Unit := do
  let happyPath := comparableFromFacts strictHappyPathFacts
  let missingLeft := comparableFromFacts strictMissingLeftSamplesFacts
  let densityFailure := comparableFromFacts allowLeftNoExecutionDensityFailureFacts
  let happyPathBlocking := (failedBlockingObligations (obligationsFromFacts strictHappyPathFacts)).length
  let missingLeftBlocking := (failedBlockingObligations (obligationsFromFacts strictMissingLeftSamplesFacts)).length
  let densityFailureBlocking := (failedBlockingObligations (obligationsFromFacts allowLeftNoExecutionDensityFailureFacts)).length

  IO.println "{"
  IO.println "  \"schemaVersion\": 1,"
  IO.println "  \"status\": \"verified\","
  IO.println "  \"theorems\": ["
  IO.println "    { \"name\": \"critical_is_max_rank\", \"module\": \"Fawn.Core.Model\", \"category\": \"comptime_verified\" },"
  IO.println "    { \"name\": \"requiredProof_forbidden_reject_from_rank\", \"module\": \"Fawn.Core.Model\", \"category\": \"comptime_verified\" },"
  IO.println "    { \"name\": \"toggleAlwaysSupported\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"strongerSafetyRaisesProofDemand\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"comptime_verified\" },"
  IO.println "    { \"name\": \"betterMatch_prefers_higher_score\", \"module\": \"Fawn.Core.Runtime\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"comparableFromObligations_eq_noFailed\", \"module\": \"Fawn.Full.Comparability\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"comparableFromFacts_eq_noFailed\", \"module\": \"Fawn.Full.Comparability\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"comparableFromObligations_true_iff_failedBlockingNil\", \"module\": \"Fawn.Full.Comparability\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"comparableFromObligations_false_iff_failedBlockingNonEmpty\", \"module\": \"Fawn.Full.Comparability\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"comparableFromFacts_true_iff_failedBlockingNil\", \"module\": \"Fawn.Full.Comparability\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"comparableFromFacts_false_iff_failedBlockingNonEmpty\", \"module\": \"Fawn.Full.Comparability\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"strictHappyPathExpectedBlocking_exact\", \"module\": \"Fawn.Full.ComparabilityFixtures\", \"category\": \"lean_fixture\" },"
  IO.println "    { \"name\": \"strictHappyPathComparable\", \"module\": \"Fawn.Full.ComparabilityFixtures\", \"category\": \"lean_fixture\" },"
  IO.println "    { \"name\": \"strictMissingLeftSamplesExpectedBlocking_exact\", \"module\": \"Fawn.Full.ComparabilityFixtures\", \"category\": \"lean_fixture\" },"
  IO.println "    { \"name\": \"strictMissingLeftSamplesComparable\", \"module\": \"Fawn.Full.ComparabilityFixtures\", \"category\": \"lean_fixture\" },"
  IO.println "    { \"name\": \"allowLeftNoExecutionDensityFailureExpectedBlocking_exact\", \"module\": \"Fawn.Full.ComparabilityFixtures\", \"category\": \"lean_fixture\" },"
  IO.println "    { \"name\": \"allowLeftNoExecutionDensityFailureComparable\", \"module\": \"Fawn.Full.ComparabilityFixtures\", \"category\": \"lean_fixture\" },"
  IO.println "    { \"name\": \"noOpActionIdentity\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"informationalToggleIdentity\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"unhandledToggleIdentity\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"behavioralToggleNotIdentity\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"identityActionComplete\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"comptime_verified\" },"
  IO.println "    { \"name\": \"scopeCommandTableComplete\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"identityActionPreservesCommand\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" }"
  IO.println "  ],"
  IO.println "  \"evaluatedConditions\": {"
  IO.println ("    \"comparability.strictHappyPath.comparable\": " ++ jsonBool happyPath ++ ",")
  IO.println ("    \"comparability.strictHappyPath.failedBlockingCount\": " ++ toString happyPathBlocking ++ ",")
  IO.println ("    \"comparability.strictMissingLeftSamples.comparable\": " ++ jsonBool missingLeft ++ ",")
  IO.println ("    \"comparability.strictMissingLeftSamples.failedBlockingCount\": " ++ toString missingLeftBlocking ++ ",")
  IO.println ("    \"comparability.allowLeftNoExecutionDensityFailure.comparable\": " ++ jsonBool densityFailure ++ ",")
  IO.println ("    \"comparability.allowLeftNoExecutionDensityFailure.failedBlockingCount\": " ++ toString densityFailureBlocking ++ ",")
  IO.println ("    \"dispatch.criticalSafetyRank\": " ++ toString SafetyClass.critical.rank ++ ",")
  IO.println ("    \"dispatch.provenProofRank\": " ++ toString ProofLevel.proven.rank ++ ",")
  IO.println ("    \"dispatch.noOpIsIdentity\": " ++ jsonBool ActionKind.no_op.isIdentity ++ ",")
  IO.println ("    \"dispatch.informationalToggleIsIdentity\": " ++ jsonBool (ActionKind.toggle .informational).isIdentity ++ ",")
  IO.println ("    \"dispatch.behavioralToggleIsIdentity\": " ++ jsonBool (ActionKind.toggle .behavioral).isIdentity ++ ",")
  IO.println ("    \"dispatch.driverToggleSupportsUpload\": " ++ jsonBool (supportsScope .driver_toggle .upload) ++ ",")
  IO.println ("    \"dispatch.driverToggleSupportsMapAsync\": " ++ jsonBool (supportsScope .driver_toggle .mapAsync) ++ ",")
  IO.println ("    \"dispatch.alignmentSupportsBarrier\": " ++ jsonBool (supportsScope .alignment .barrier) ++ ",")
  IO.println ("    \"dispatch.layoutSupportsRenderDraw\": " ++ jsonBool (supportsScope .layout .renderDraw))
  IO.println "  },"
  IO.println "  \"eliminationTargets\": ["
  IO.println "    {"
  IO.println "      \"theorem\": \"toggleAlwaysSupported\","
  IO.println "      \"condition\": \"scope == driver_toggle implies supports all commands\","
  IO.println "      \"runtimePath\": \"quirk/runtime.zig:supportsScope\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"requiredProof_forbidden_reject_from_rank\","
  IO.println "      \"condition\": \"no safety class maps to ProofLevel.rejected\","
  IO.println "      \"runtimePath\": \"quirk/runtime.zig:finalizeBucket\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"strongerSafetyRaisesProofDemand\","
  IO.println "      \"condition\": \"critical safety class requires proven proof level\","
  IO.println "      \"runtimePath\": \"quirk/runtime.zig:finalizeBucket\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"identityActionComplete\","
  IO.println "      \"condition\": \"no_op, informational toggle, and unhandled toggle actions are identity; behavioral toggle is not\","
  IO.println "      \"runtimePath\": \"quirk/runtime.zig:dispatch\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"scopeCommandTableComplete\","
  IO.println "      \"condition\": \"comptime scope×command table matches supportsScope for all pairs; subsumes toggleAlwaysSupported\","
  IO.println "      \"runtimePath\": \"quirk/runtime.zig:buildDispatchContext,buildProfileDispatchContext\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"identityActionPreservesCommand\","
  IO.println "      \"condition\": \"identity actions preserve the command unchanged; dispatch can skip applyAction\","
  IO.println "      \"runtimePath\": \"quirk/runtime.zig:dispatch\""
  IO.println "    }"
  IO.println "  ]"
  IO.println "}"
