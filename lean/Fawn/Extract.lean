import Fawn.Bridge
import Fawn.ComparabilityFixtures
import Fawn.Dispatch

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
  IO.println "    { \"name\": \"critical_is_max_rank\", \"module\": \"Fawn.Model\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"requiredProof_forbidden_reject_from_rank\", \"module\": \"Fawn.Model\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"toggleAlwaysSupported\", \"module\": \"Fawn.Dispatch\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"strongerSafetyRaisesProofDemand\", \"module\": \"Fawn.Dispatch\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"betterMatch_prefers_higher_score\", \"module\": \"Fawn.Runtime\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"comparableFromObligations_eq_noFailed\", \"module\": \"Fawn.Comparability\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"comparableFromFacts_eq_noFailed\", \"module\": \"Fawn.Comparability\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"comparableFromObligations_true_iff_failedBlockingNil\", \"module\": \"Fawn.Comparability\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"comparableFromObligations_false_iff_failedBlockingNonEmpty\", \"module\": \"Fawn.Comparability\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"comparableFromFacts_true_iff_failedBlockingNil\", \"module\": \"Fawn.Comparability\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"comparableFromFacts_false_iff_failedBlockingNonEmpty\", \"module\": \"Fawn.Comparability\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"strictHappyPathExpectedBlocking_exact\", \"module\": \"Fawn.ComparabilityFixtures\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"strictHappyPathComparable\", \"module\": \"Fawn.ComparabilityFixtures\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"strictMissingLeftSamplesExpectedBlocking_exact\", \"module\": \"Fawn.ComparabilityFixtures\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"strictMissingLeftSamplesComparable\", \"module\": \"Fawn.ComparabilityFixtures\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"allowLeftNoExecutionDensityFailureExpectedBlocking_exact\", \"module\": \"Fawn.ComparabilityFixtures\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"allowLeftNoExecutionDensityFailureComparable\", \"module\": \"Fawn.ComparabilityFixtures\", \"category\": \"comparability\" },"
  IO.println "    { \"name\": \"noOpActionIdentity\", \"module\": \"Fawn.Dispatch\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"informationalToggleIdentity\", \"module\": \"Fawn.Dispatch\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"unhandledToggleIdentity\", \"module\": \"Fawn.Dispatch\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"behavioralToggleNotIdentity\", \"module\": \"Fawn.Dispatch\", \"category\": \"dispatch\" },"
  IO.println "    { \"name\": \"identityActionComplete\", \"module\": \"Fawn.Dispatch\", \"category\": \"dispatch\" }"
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
  IO.println ("    \"dispatch.behavioralToggleIsIdentity\": " ++ jsonBool (ActionKind.toggle .behavioral).isIdentity)
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
  IO.println "    }"
  IO.println "  ]"
  IO.println "}"
