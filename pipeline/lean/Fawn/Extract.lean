import Fawn.Core.Bridge
import Fawn.Core.BindGroupSlot
import Fawn.Core.BufferLifecycle
import Fawn.Core.Dispatch
import Fawn.Full.ComparabilityFixtures
import Fawn.Full.WorkloadGeometry
import Fawn.Shader.ComputeBounds

set_option maxRecDepth 1024

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
  IO.println "  \"contractHashes\": {"
  IO.println ("    \"comparabilityObligationsSha256\": \"" ++ comparabilityContractSha256 ++ "\"")
  IO.println "  },"
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
  IO.println "    { \"name\": \"structurallyEquivalentGeometry_refl\", \"module\": \"Fawn.Full.WorkloadGeometry\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"structurallyEquivalentGeometry_forall_components\", \"module\": \"Fawn.Full.WorkloadGeometry\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"equalGeometrySetsExecutionShapeFacts\", \"module\": \"Fawn.Full.WorkloadGeometry\", \"category\": \"lean_verified\" },"
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
  IO.println "    { \"name\": \"identityActionPreservesCommand\", \"module\": \"Fawn.Core.Dispatch\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"mslBindingSlot_injective_within_group\", \"module\": \"Fawn.Core.BindGroupSlot\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"mslBindingSlot_injective_across_groups\", \"module\": \"Fawn.Core.BindGroupSlot\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"mslBindingSlot_in_bounds\", \"module\": \"Fawn.Core.BindGroupSlot\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"mslBindingSlot_distinct_groups\", \"module\": \"Fawn.Core.BindGroupSlot\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"doeRelease_terminal\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"released_absorbs_all\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"tautological\" },"
  IO.println "    { \"name\": \"doeMapAsync_idempotent\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"doeUnmap_idempotent\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"doeMapUnmap_roundtrip\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"doe_getMappedRange_gap\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"doe_dispatch_gap\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"doe_getMappedRange_superset\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"doe_dispatch_superset\", \"module\": \"Fawn.Core.BufferLifecycle\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"gid_component_lt_total\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"gid_inbounds_when_dispatch_fits\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"clamp_noop_when_inbounds\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"gid_2d_inbounds\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"flat_index_2d_inbounds\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"gid_texture_coords_2d_inbounds_when_dispatch_fits\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"guarded_gid_texture_coords_2d_inbounds\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"gid_texture_coords_3d_inbounds_when_dispatch_fits\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" },"
  IO.println "    { \"name\": \"guarded_gid_texture_coords_3d_inbounds\", \"module\": \"Fawn.Shader.ComputeBounds\", \"category\": \"lean_verified\" }"
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
  IO.println ("    \"dispatch.layoutSupportsRenderDraw\": " ++ jsonBool (supportsScope .layout .renderDraw) ++ ",")
  IO.println ("    \"bindGroupSlot.slot_0_0\": " ++ toString (mslBindingSlot 0 0) ++ ",")
  IO.println ("    \"bindGroupSlot.slot_1_0\": " ++ toString (mslBindingSlot 1 0) ++ ",")
  IO.println ("    \"bindGroupSlot.slot_3_15\": " ++ toString (mslBindingSlot 3 15) ++ ",")
  IO.println ("    \"bufferLifecycle.doeAllowsGetMappedRange_unmapped\": " ++ jsonBool (doeAllowsGetMappedRange .unmapped) ++ ",")
  IO.println ("    \"bufferLifecycle.specAllowsGetMappedRange_unmapped\": " ++ jsonBool (specAllowsGetMappedRange .unmapped) ++ ",")
  IO.println ("    \"bufferLifecycle.doeAllowsDispatch_mapped\": " ++ jsonBool (doeAllowsDispatch .mapped) ++ ",")
  IO.println ("    \"bufferLifecycle.specAllowsDispatch_mapped\": " ++ jsonBool (specAllowsDispatch .mapped))
  IO.println "  },"
  IO.println "  \"boundsEliminations\": ["
  IO.println "    {"
  IO.println "      \"theorem\": \"gid_inbounds_when_dispatch_fits\","
  IO.println "      \"module\": \"Fawn.Shader.ComputeBounds\","
  IO.println "      \"category\": \"lean_verified\","
  IO.println "      \"pattern\": \"global_invocation_id.{component} indexes storage buffer\","
  IO.println "      \"precondition\": \"workgroup_size.{component} * num_workgroups.{component} <= buffer_element_count\","
  IO.println "      \"eliminates\": \"min(gid.{component}, arrayLength(&buf) - 1) -> gid.{component}\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_runtime_sized\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"flat_index_2d_inbounds\","
  IO.println "      \"module\": \"Fawn.Shader.ComputeBounds\","
  IO.println "      \"category\": \"lean_verified\","
  IO.println "      \"pattern\": \"gid.y * width + gid.x indexes storage buffer\","
  IO.println "      \"precondition\": \"ws.x * nwg.x <= width AND ws.y * nwg.y <= height AND width * height <= buffer_element_count\","
  IO.println "      \"eliminates\": \"min(flat_index, arrayLength(&buf) - 1) -> flat_index\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_runtime_sized\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"guarded_gid_texture_coords_2d_inbounds\","
  IO.println "      \"module\": \"Fawn.Shader.ComputeBounds\","
  IO.println "      \"category\": \"lean_verified\","
  IO.println "      \"pattern\": \"global_invocation_id.xy texture coords guarded by root early-return against textureDimensions(tex[,level]).xy\","
  IO.println "      \"precondition\": \"if gid.x >= textureDimensions(...).x || gid.y >= textureDimensions(...).y { return; }\","
  IO.println "      \"eliminates\": \"clamp(coords, vec(0), textureDimensions(tex[,level]) - 1) -> coords\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_texture_coords\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"gid_texture_coords_2d_inbounds_when_dispatch_fits\","
  IO.println "      \"module\": \"Fawn.Shader.ComputeBounds\","
  IO.println "      \"category\": \"lean_verified\","
  IO.println "      \"pattern\": \"global_invocation_id.xy texture coords on a bound 2D texture\","
  IO.println "      \"precondition\": \"workgroup_size.x * num_workgroups.x <= textureDimensions(tex,0).x AND workgroup_size.y * num_workgroups.y <= textureDimensions(tex,0).y\","
  IO.println "      \"eliminates\": \"clamp(coords, vec(0), textureDimensions(tex[,level]) - 1) -> coords\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_texture_coords\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"guarded_gid_texture_coords_3d_inbounds\","
  IO.println "      \"module\": \"Fawn.Shader.ComputeBounds\","
  IO.println "      \"category\": \"lean_verified\","
  IO.println "      \"pattern\": \"global_invocation_id.xyz texture coords guarded by root early-return against textureDimensions(tex[,level]).xyz\","
  IO.println "      \"precondition\": \"if gid.x >= textureDimensions(...).x || gid.y >= textureDimensions(...).y || gid.z >= textureDimensions(...).z { return; }\","
  IO.println "      \"eliminates\": \"clamp(coords, vec(0), textureDimensions(tex[,level]) - 1) -> coords\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_texture_coords\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"gid_texture_coords_3d_inbounds_when_dispatch_fits\","
  IO.println "      \"module\": \"Fawn.Shader.ComputeBounds\","
  IO.println "      \"category\": \"lean_verified\","
  IO.println "      \"pattern\": \"global_invocation_id.xyz texture coords on a bound 3D texture\","
  IO.println "      \"precondition\": \"workgroup_size.x * num_workgroups.x <= textureDimensions(tex,0).x AND workgroup_size.y * num_workgroups.y <= textureDimensions(tex,0).y AND workgroup_size.z * num_workgroups.z <= textureDimensions(tex,0).z\","
  IO.println "      \"eliminates\": \"clamp(coords, vec(0), textureDimensions(tex[,level]) - 1) -> coords\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_texture_coords\""
  IO.println "    }"
  IO.println "  ],"
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
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"equalGeometrySetsExecutionShapeFacts\","
  IO.println "      \"condition\": \"matching buffer size and dispatch geometry force execution-shape comparability facts true for arbitrary Nat-valued workloads\","
  IO.println "      \"runtimePath\": \"bench/native_compare_modules/comparability.py:evaluate_comparability_from_facts\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"mslBindingSlot_injective_across_groups\","
  IO.println "      \"condition\": \"group*16+binding is injective for binding<16; flat buffer array has no collisions\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgsl/emit_msl_ir.zig:msl_binding_slot,runtime/zig/src/doe_compute_ext_native.zig:flattenBindGroups\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"mslBindingSlot_in_bounds\","
  IO.println "      \"condition\": \"valid group and binding produce slot < 64; bounds check can be elided at comptime\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_compute_ext_native.zig:flattenBindGroups\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"doe_getMappedRange_superset\","
  IO.println "      \"condition\": \"Doe permits all spec-valid getMappedRange calls; no false rejections\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgpu_native.zig:doeBufferGetMappedRange\""
  IO.println "    },"
  IO.println "    {"
  IO.println "      \"theorem\": \"doe_dispatch_superset\","
  IO.println "      \"condition\": \"Doe permits all spec-valid dispatch calls; no false rejections\","
  IO.println "      \"runtimePath\": \"runtime/zig/src/doe_wgpu_native.zig:doeBufferRelease\""
  IO.println "    }"
  IO.println "  ]"
  IO.println "}"
