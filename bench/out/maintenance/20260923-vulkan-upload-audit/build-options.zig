pub const @"enums.EnumFieldStruct(src.contracts.backend.BackendLane,src.contracts.backend.SelectionPolicy,null)" = struct {
    metal_doe_app: @"src.contracts.backend.SelectionPolicy",
    metal_doe_directional: @"src.contracts.backend.SelectionPolicy",
    metal_doe_comparable: @"src.contracts.backend.SelectionPolicy",
    metal_doe_release: @"src.contracts.backend.SelectionPolicy",
    metal_dawn_release: @"src.contracts.backend.SelectionPolicy",
    metal_webkit_release: @"src.contracts.backend.SelectionPolicy",
    metal_webkit_comparable: @"src.contracts.backend.SelectionPolicy",
    vulkan_doe_app: @"src.contracts.backend.SelectionPolicy",
    vulkan_doe_comparable: @"src.contracts.backend.SelectionPolicy",
    vulkan_doe_compute_only_diagnostic: @"src.contracts.backend.SelectionPolicy",
    vulkan_doe_compute_only_fence_diagnostic: @"src.contracts.backend.SelectionPolicy",
    vulkan_doe_release: @"src.contracts.backend.SelectionPolicy",
    vulkan_dawn_release: @"src.contracts.backend.SelectionPolicy",
    d3d12_doe_app: @"src.contracts.backend.SelectionPolicy",
    d3d12_doe_directional: @"src.contracts.backend.SelectionPolicy",
    d3d12_doe_comparable: @"src.contracts.backend.SelectionPolicy",
    d3d12_doe_release: @"src.contracts.backend.SelectionPolicy",
    d3d12_dawn_release: @"src.contracts.backend.SelectionPolicy",
};
pub const @"src.contracts.backend.SelectionPolicy" = struct {
    lane: @"src.contracts.backend.BackendLane",
    default_backend: @"src.contracts.backend.BackendId",
    allow_fallback: bool,
    strict_no_fallback: bool,
    policy_hash: []const u8,
    upload_path_policy: @"src.contracts.backend.UploadPathPolicy",
    queue_family_policy: @"src.contracts.backend.QueueFamilyPolicy",
    deferred_submission_sync_policy: @"src.contracts.backend.DeferredSubmissionSyncPolicy",
    vulkan_subgroup_size_policy: @"src.contracts.backend.VulkanSubgroupSizePolicy",
};
pub const @"src.contracts.backend.BackendLane" = enum (u5) {
    metal_doe_app = 0,
    metal_doe_directional = 1,
    metal_doe_comparable = 2,
    metal_doe_release = 3,
    metal_dawn_release = 4,
    metal_webkit_release = 5,
    metal_webkit_comparable = 6,
    vulkan_doe_app = 7,
    vulkan_doe_comparable = 8,
    vulkan_doe_compute_only_diagnostic = 9,
    vulkan_doe_compute_only_fence_diagnostic = 10,
    vulkan_doe_release = 11,
    vulkan_dawn_release = 12,
    d3d12_doe_app = 13,
    d3d12_doe_directional = 14,
    d3d12_doe_comparable = 15,
    d3d12_doe_release = 16,
    d3d12_dawn_release = 17,
};
pub const @"src.contracts.backend.BackendId" = enum (u3) {
    dawn_delegate = 0,
    webkit_delegate = 1,
    doe_metal = 2,
    doe_vulkan = 3,
    doe_d3d12 = 4,
};
pub const @"src.contracts.backend.UploadPathPolicy" = enum (u1) {
    allow_mapped_shortcuts = 0,
    staged_copy_only = 1,
};
pub const @"src.contracts.backend.QueueFamilyPolicy" = enum (u2) {
    prefer_graphics_compute = 0,
    prefer_compute_only = 1,
    require_compute_only = 2,
};
pub const @"src.contracts.backend.DeferredSubmissionSyncPolicy" = enum (u1) {
    prefer_timeline_semaphore = 0,
    require_fence_pool = 1,
};
pub const @"src.contracts.backend.VulkanSubgroupSizePolicy" = enum (u2) {
    fixed_32_when_supported = 0,
    suppress_for_workgroup_memory_256 = 1,
    suppress_for_workgroup_memory_256_or_single_invocation = 2,
};
pub const backend_runtime_policy: @"enums.EnumFieldStruct(src.contracts.backend.BackendLane,src.contracts.backend.SelectionPolicy,null)" = .{
    .metal_doe_app = .{
        .lane = .metal_doe_app,
        .default_backend = .doe_metal,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .metal_doe_directional = .{
        .lane = .metal_doe_directional,
        .default_backend = .doe_metal,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .metal_doe_comparable = .{
        .lane = .metal_doe_comparable,
        .default_backend = .doe_metal,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .metal_doe_release = .{
        .lane = .metal_doe_release,
        .default_backend = .doe_metal,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .metal_dawn_release = .{
        .lane = .metal_dawn_release,
        .default_backend = .dawn_delegate,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .metal_webkit_release = .{
        .lane = .metal_webkit_release,
        .default_backend = .webkit_delegate,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .metal_webkit_comparable = .{
        .lane = .metal_webkit_comparable,
        .default_backend = .webkit_delegate,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .vulkan_doe_app = .{
        .lane = .vulkan_doe_app,
        .default_backend = .doe_vulkan,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .require_fence_pool,
        .vulkan_subgroup_size_policy = .suppress_for_workgroup_memory_256_or_single_invocation,
    },
    .vulkan_doe_comparable = .{
        .lane = .vulkan_doe_comparable,
        .default_backend = .doe_vulkan,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .suppress_for_workgroup_memory_256_or_single_invocation,
    },
    .vulkan_doe_compute_only_diagnostic = .{
        .lane = .vulkan_doe_compute_only_diagnostic,
        .default_backend = .doe_vulkan,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .require_compute_only,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .suppress_for_workgroup_memory_256_or_single_invocation,
    },
    .vulkan_doe_compute_only_fence_diagnostic = .{
        .lane = .vulkan_doe_compute_only_fence_diagnostic,
        .default_backend = .doe_vulkan,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .require_compute_only,
        .deferred_submission_sync_policy = .require_fence_pool,
        .vulkan_subgroup_size_policy = .suppress_for_workgroup_memory_256_or_single_invocation,
    },
    .vulkan_doe_release = .{
        .lane = .vulkan_doe_release,
        .default_backend = .doe_vulkan,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .suppress_for_workgroup_memory_256_or_single_invocation,
    },
    .vulkan_dawn_release = .{
        .lane = .vulkan_dawn_release,
        .default_backend = .dawn_delegate,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .d3d12_doe_app = .{
        .lane = .d3d12_doe_app,
        .default_backend = .doe_d3d12,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .d3d12_doe_directional = .{
        .lane = .d3d12_doe_directional,
        .default_backend = .doe_d3d12,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .d3d12_doe_comparable = .{
        .lane = .d3d12_doe_comparable,
        .default_backend = .doe_d3d12,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .d3d12_doe_release = .{
        .lane = .d3d12_doe_release,
        .default_backend = .doe_d3d12,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .staged_copy_only,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
    .d3d12_dawn_release = .{
        .lane = .d3d12_dawn_release,
        .default_backend = .dawn_delegate,
        .allow_fallback = false,
        .strict_no_fallback = true,
        .policy_hash = "backend-runtime-policy-v7",
        .upload_path_policy = .allow_mapped_shortcuts,
        .queue_family_policy = .prefer_graphics_compute,
        .deferred_submission_sync_policy = .prefer_timeline_semaphore,
        .vulkan_subgroup_size_policy = .fixed_32_when_supported,
    },
};
pub const compute_program_contract_version: u32 = 2;
pub const vulkan_share_live_compute_pipelines: bool = true;
pub const vulkan_readback_required_properties: u32 = 6;
pub const vulkan_readback_preferred_properties: u32 = 8;
pub const vulkan_timestamp_workgroup_size: u32 = 64;
pub const native_command_storage_max_retained_bytes: usize = 1048576;
pub const native_command_storage_policy_sha256: []const u8 = "1ec9c9b6c9fc8011cfc098d4fc00963d780e8ccafbd16acccb09ae515e8362f7";
pub const native_command_storage_observation_mode: []const u8 = "ordinary";
pub const native_command_storage_observation_sha256: []const u8 = "4c96f721dadc11bd3c1aa90e7f73f21728648e4dd726507b0664efeba7ed753c";
pub const metal_wait_timeout_ns: u64 = 2000000000;
pub const metal_wait_poll_interval_ns: u64 = 50000;
pub const spirv_compute_fuse_trailing_add: bool = true;
pub const spirv_compute_preserve_multi_dot_loops: bool = true;
pub const spirv_compute_unroll_independent_dot_loops: bool = true;
pub const lean_verified: bool = false;
pub const @"build.build.BuildTier" = enum (u2) {
    compute = 0,
    headless = 1,
    full = 2,
};
pub const build_tier: @"build.build.BuildTier" = .headless;
pub const lean_toolchain_ref: []const u8 = "leanprover/lean4:v4.16.0";
pub const lean_extract_program_sha256: []const u8 = "be23888c64ea12e4c483817025ad9bf68344e59e14e9067b25ce8d83fb6ea791";
pub const lean_source_tree_sha256: []const u8 = "fd033d23739cf58940d423d3064c2c7f648ade02177e8a7737748e5586802e45";
pub const generated_comparability_contract_sha256: []const u8 = "d1da49837aae69cbcc87557a15f158166f35ac9ba017af72fe0fe6a9b59eebc7";
pub const proof_pattern_spec_sha256: []const u8 = "0e839bfbcd0f4c5f8087c880434c9741804fb32797fc8650fe8951c00d57529d";
pub const comparability_obligations_json: []const u8 = "{\n  \"schemaVersion\": 2,\n  \"facts\": [\n    \"workload_marked_comparable\",\n    \"left_samples_present\",\n    \"right_samples_present\",\n    \"result_output_match_applies\",\n    \"baseline_comparison_result_output_match\",\n    \"left_single_timing_class\",\n    \"right_single_timing_class\",\n    \"required_timing_class_applies\",\n    \"left_required_timing_class\",\n    \"right_required_timing_class\",\n    \"timing_class_match_applies\",\n    \"baseline_comparison_timing_class_match\",\n    \"trace_meta_source_match_applies\",\n    \"baseline_comparison_trace_meta_source_match\",\n    \"timing_selection_policy_match_applies\",\n    \"baseline_comparison_timing_selection_policy_match\",\n    \"queue_sync_mode_match_applies\",\n    \"baseline_comparison_queue_sync_mode_match\",\n    \"submit_scope_match_applies\",\n    \"baseline_comparison_submit_scope_match\",\n    \"effective_readback_path_match_applies\",\n    \"baseline_comparison_effective_readback_path_match\",\n    \"timing_phase_match_applies\",\n    \"baseline_comparison_timing_phase_match\",\n    \"package_resident_buffer_load_mode_match_applies\",\n    \"baseline_comparison_package_resident_buffer_load_mode_match\",\n    \"package_resident_buffer_load_shape_match_applies\",\n    \"baseline_comparison_package_resident_buffer_load_shape_match\",\n    \"package_shader_source_receipts_match_applies\",\n    \"baseline_comparison_shader_source_receipts_match\",\n    \"execution_shape_match_applies\",\n    \"baseline_comparison_execution_shape_match\",\n    \"readback_capture_match_applies\",\n    \"baseline_comparison_readback_capture_match\",\n    \"hardware_path_match_applies\",\n    \"baseline_comparison_hardware_path_match\",\n    \"explicit_native_shader_artifact_match_applies\",\n    \"baseline_comparison_explicit_native_shader_artifact_match\",\n    \"operation_timing_class_required\",\n    \"baseline_native_operation_timing_for_webgpu_ffi\",\n    \"upload_domain\",\n    \"baseline_upload_ignore_first_scope_consistent\",\n    \"comparison_upload_ignore_first_scope_consistent\",\n    \"baseline_comparison_upload_buffer_usage_match\",\n    \"baseline_comparison_upload_submit_cadence_match\",\n    \"allow_baseline_no_execution\",\n    \"baseline_execution_evidence_present\",\n    \"baseline_successful_execution_present\",\n    \"baseline_success_or_unsupported_or_skipped\",\n    \"baseline_execution_errors_absent\",\n    \"comparison_execution_errors_absent\",\n    \"baseline_comparison_timing_plausibility\",\n    \"resource_probe_enabled\",\n    \"baseline_resource_probe_available\",\n    \"comparison_resource_probe_available\",\n    \"strict_comparability\",\n    \"resource_sample_target_positive\",\n    \"baseline_resource_sample_target_match\",\n    \"comparison_resource_sample_target_match\",\n    \"baseline_resource_sampling_not_truncated\",\n    \"comparison_resource_sampling_not_truncated\",\n    \"baseline_resource_sample_density_sufficient\",\n    \"comparison_resource_sample_density_sufficient\"\n  ],\n  \"obligations\": [\n    {\n      \"id\": \"workload_marked_comparable\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"workload_marked_comparable\" }\n    },\n    {\n      \"id\": \"left_samples_present\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"left_samples_present\" }\n    },\n    {\n      \"id\": \"right_samples_present\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"right_samples_present\" }\n    },\n    {\n      \"id\": \"baseline_comparison_result_output_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"result_output_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_result_output_match\" }\n    },\n    {\n      \"id\": \"left_single_timing_class\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"left_single_timing_class\" }\n    },\n    {\n      \"id\": \"right_single_timing_class\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"right_single_timing_class\" }\n    },\n    {\n      \"id\": \"left_required_timing_class\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"required_timing_class_applies\" },\n      \"passesWhen\": { \"fact\": \"left_required_timing_class\" }\n    },\n    {\n      \"id\": \"right_required_timing_class\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"required_timing_class_applies\" },\n      \"passesWhen\": { \"fact\": \"right_required_timing_class\" }\n    },\n    {\n      \"id\": \"baseline_comparison_timing_class_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"timing_class_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_timing_class_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_trace_meta_source_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"trace_meta_source_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_trace_meta_source_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_timing_selection_policy_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"timing_selection_policy_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_timing_selection_policy_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_queue_sync_mode_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"queue_sync_mode_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_queue_sync_mode_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_submit_scope_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"submit_scope_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_submit_scope_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_effective_readback_path_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"effective_readback_path_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_effective_readback_path_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_timing_phase_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"timing_phase_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_timing_phase_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_package_resident_buffer_load_mode_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"package_resident_buffer_load_mode_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_package_resident_buffer_load_mode_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_package_resident_buffer_load_shape_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"package_resident_buffer_load_shape_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_package_resident_buffer_load_shape_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_shader_source_receipts_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"package_shader_source_receipts_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_shader_source_receipts_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_execution_shape_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"execution_shape_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_execution_shape_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_readback_capture_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"readback_capture_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_readback_capture_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_hardware_path_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"hardware_path_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_hardware_path_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_explicit_native_shader_artifact_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"explicit_native_shader_artifact_match_applies\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_explicit_native_shader_artifact_match\" }\n    },\n    {\n      \"id\": \"baseline_native_operation_timing_for_webgpu_ffi\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"operation_timing_class_required\" },\n      \"passesWhen\": { \"fact\": \"baseline_native_operation_timing_for_webgpu_ffi\" }\n    },\n    {\n      \"id\": \"baseline_upload_ignore_first_scope_consistent\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"upload_domain\" },\n      \"passesWhen\": { \"fact\": \"baseline_upload_ignore_first_scope_consistent\" }\n    },\n    {\n      \"id\": \"comparison_upload_ignore_first_scope_consistent\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"upload_domain\" },\n      \"passesWhen\": { \"fact\": \"comparison_upload_ignore_first_scope_consistent\" }\n    },\n    {\n      \"id\": \"baseline_comparison_upload_buffer_usage_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"upload_domain\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_upload_buffer_usage_match\" }\n    },\n    {\n      \"id\": \"baseline_comparison_upload_submit_cadence_match\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"upload_domain\" },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_upload_submit_cadence_match\" }\n    },\n    {\n      \"id\": \"baseline_execution_evidence_present\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"not\": { \"fact\": \"allow_baseline_no_execution\" } },\n      \"passesWhen\": { \"fact\": \"baseline_execution_evidence_present\" }\n    },\n    {\n      \"id\": \"baseline_successful_execution_present\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"not\": { \"fact\": \"allow_baseline_no_execution\" } },\n      \"passesWhen\": { \"fact\": \"baseline_successful_execution_present\" }\n    },\n    {\n      \"id\": \"baseline_success_or_unsupported_or_skipped\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"allow_baseline_no_execution\" },\n      \"passesWhen\": { \"fact\": \"baseline_success_or_unsupported_or_skipped\" }\n    },\n    {\n      \"id\": \"baseline_execution_errors_absent\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"baseline_execution_errors_absent\" }\n    },\n    {\n      \"id\": \"comparison_execution_errors_absent\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"comparison_execution_errors_absent\" }\n    },\n    {\n      \"id\": \"baseline_comparison_timing_plausibility\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"const\": true },\n      \"passesWhen\": { \"fact\": \"baseline_comparison_timing_plausibility\" }\n    },\n    {\n      \"id\": \"baseline_resource_probe_available\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"resource_probe_enabled\" },\n      \"passesWhen\": { \"fact\": \"baseline_resource_probe_available\" }\n    },\n    {\n      \"id\": \"comparison_resource_probe_available\",\n      \"blocking\": true,\n      \"applicableWhen\": { \"fact\": \"resource_probe_enabled\" },\n      \"passesWhen\": { \"fact\": \"comparison_resource_probe_available\" }\n    },\n    {\n      \"id\": \"strict_resource_sample_target_positive\",\n      \"blocking\": true,\n      \"applicableWhen\": {\n        \"allOf\": [\n          { \"fact\": \"resource_probe_enabled\" },\n          { \"fact\": \"strict_comparability\" }\n        ]\n      },\n      \"passesWhen\": { \"fact\": \"resource_sample_target_positive\" }\n    },\n    {\n      \"id\": \"baseline_resource_sample_target_match\",\n      \"blocking\": true,\n      \"applicableWhen\": {\n        \"allOf\": [\n          { \"fact\": \"resource_probe_enabled\" },\n          { \"fact\": \"strict_comparability\" },\n          { \"fact\": \"resource_sample_target_positive\" }\n        ]\n      },\n      \"passesWhen\": { \"fact\": \"baseline_resource_sample_target_match\" }\n    },\n    {\n      \"id\": \"comparison_resource_sample_target_match\",\n      \"blocking\": true,\n      \"applicableWhen\": {\n        \"allOf\": [\n          { \"fact\": \"resource_probe_enabled\" },\n          { \"fact\": \"strict_comparability\" },\n          { \"fact\": \"resource_sample_target_positive\" }\n        ]\n      },\n      \"passesWhen\": { \"fact\": \"comparison_resource_sample_target_match\" }\n    },\n    {\n      \"id\": \"baseline_resource_sampling_not_truncated\",\n      \"blocking\": true,\n      \"applicableWhen\": {\n        \"allOf\": [\n          { \"fact\": \"resource_probe_enabled\" },\n          { \"fact\": \"strict_comparability\" },\n          { \"fact\": \"resource_sample_target_positive\" }\n        ]\n      },\n      \"passesWhen\": { \"fact\": \"baseline_resource_sampling_not_truncated\" }\n    },\n    {\n      \"id\": \"comparison_resource_sampling_not_truncated\",\n      \"blocking\": true,\n      \"applicableWhen\": {\n        \"allOf\": [\n          { \"fact\": \"resource_probe_enabled\" },\n          { \"fact\": \"strict_comparability\" },\n          { \"fact\": \"resource_sample_target_positive\" }\n        ]\n      },\n      \"passesWhen\": { \"fact\": \"comparison_resource_sampling_not_truncated\" }\n    },\n    {\n      \"id\": \"baseline_resource_sample_density_sufficient\",\n      \"blocking\": true,\n      \"applicableWhen\": {\n        \"allOf\": [\n          { \"fact\": \"resource_probe_enabled\" },\n          { \"not\": { \"fact\": \"strict_comparability\" } }\n        ]\n      },\n      \"passesWhen\": { \"fact\": \"baseline_resource_sample_density_sufficient\" }\n    },\n    {\n      \"id\": \"comparison_resource_sample_density_sufficient\",\n      \"blocking\": true,\n      \"applicableWhen\": {\n        \"allOf\": [\n          { \"fact\": \"resource_probe_enabled\" },\n          { \"not\": { \"fact\": \"strict_comparability\" } }\n        ]\n      },\n      \"passesWhen\": { \"fact\": \"comparison_resource_sample_density_sufficient\" }\n    }\n  ]\n}\n";
pub const comparability_obligations_sha256: []const u8 = "122a21b854428b45c6c4dc17780057eda8c0b16d56739b1625a580f8ba0af3db";
pub const wgsl_compiler_source_sha256: []const u8 = "eee43bef037fb69584958161638e28e7a67f74292c4bf71f685525fe8265f27d";
pub const shader_translation_cache_source_sha256: []const u8 = "80c92ed793440096df74cd04851f8c4a18aca6363535acb45e36126a4f2c0edb";
pub const pipeline_cache_source_sha256: []const u8 = "eb10699a0de97452d281dc6629eda1fa8b0b7b0b9dc42f5a09e14a43553378df";
pub const proof_artifact_sha256: []const u8 = "0000000000000000000000000000000000000000000000000000000000000000";
pub const dropin_behavior_config_json: []const u8 = "{\n  \"schemaVersion\": 1,\n  \"defaultMode\": \"dawn_ownership\",\n  \"laneModes\": {\n    \"metal_doe_app\": \"doe_metal_ownership\",\n    \"metal_doe_directional\": \"mixed_ownership\",\n    \"metal_doe_comparable\": \"doe_metal_ownership\",\n    \"metal_doe_release\": \"doe_metal_ownership\",\n    \"metal_dawn_release\": \"dawn_ownership\",\n    \"vulkan_doe_app\": \"doe_vulkan_ownership\",\n    \"vulkan_doe_comparable\": \"doe_vulkan_ownership\",\n    \"vulkan_doe_release\": \"doe_vulkan_ownership\",\n    \"vulkan_dawn_release\": \"dawn_ownership\",\n    \"vulkan_dawn_directional\": \"dawn_ownership\",\n    \"d3d12_doe_app\": \"doe_d3d12_ownership\",\n    \"d3d12_doe_directional\": \"mixed_ownership\",\n    \"d3d12_doe_comparable\": \"doe_d3d12_ownership\",\n    \"d3d12_doe_release\": \"doe_d3d12_ownership\",\n    \"d3d12_dawn_release\": \"dawn_ownership\"\n  },\n  \"strictFallbackForbidden\": true\n}\n";
pub const dropin_symbol_ownership_config_json: []const u8 = "{\n  \"schemaVersion\": 3,\n  \"tiers\": {\n    \"compute\": \"Dispatch, buffer, shader, bind group, command encoder, queue. No render, no textures-as-attachments.\",\n    \"headless\": \"Full WebGPU sans windowed presentation. Includes compute + render + textures + samplers + queries.\",\n    \"full\": \"Dawn drop-in. Includes headless + surface presentation + external textures + browser interop.\"\n  },\n  \"symbols\": [\n    {\n      \"symbol\": \"wgpuGetProcAddress\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuCreateInstance\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuCommandEncoderCopyBufferToBuffer\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuComputePassEncoderDispatchWorkgroups\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuDeviceCreateBuffer\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuDeviceCreateShaderModule\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuDeviceCreateComputePipeline\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuQueueSubmit\",\n      \"owner\": \"shared\",\n      \"tier\": \"compute\"\n    },\n    {\n      \"symbol\": \"wgpuRenderPassEncoderDraw\",\n      \"owner\": \"shared\",\n      \"tier\": \"headless\"\n    },\n    {\n      \"symbol\": \"wgpuRenderPassEncoderDrawIndexed\",\n      \"owner\": \"shared\",\n      \"tier\": \"headless\"\n    },\n    {\n      \"symbol\": \"wgpuDeviceCreateRenderPipeline\",\n      \"owner\": \"shared\",\n      \"tier\": \"headless\"\n    },\n    {\n      \"symbol\": \"wgpuDeviceCreateTexture\",\n      \"owner\": \"shared\",\n      \"tier\": \"headless\"\n    },\n    {\n      \"symbol\": \"wgpuDeviceCreateSampler\",\n      \"owner\": \"shared\",\n      \"tier\": \"headless\"\n    },\n    {\n      \"symbol\": \"wgpuCommandEncoderCopyTextureToBuffer\",\n      \"owner\": \"shared\",\n      \"tier\": \"headless\"\n    },\n    {\n      \"symbol\": \"wgpuDeviceCreateExternalTexture\",\n      \"owner\": \"shared\",\n      \"tier\": \"full\"\n    },\n    {\n      \"symbol\": \"wgpuSurfaceConfigure\",\n      \"owner\": \"shared\",\n      \"tier\": \"full\"\n    },\n    {\n      \"symbol\": \"wgpuSurfaceGetCurrentTexture\",\n      \"owner\": \"shared\",\n      \"tier\": \"full\"\n    },\n    {\n      \"symbol\": \"wgpuSurfacePresent\",\n      \"owner\": \"shared\",\n      \"tier\": \"full\"\n    }\n  ]\n}\n";
pub const quirk_toggle_registry = [_]struct {
    toggle_name: []const u8,
    effect: []const u8,
    description: []const u8,
}{
    .{ .toggle_name = "use_temporary_buffer_in_texture_to_texture_copy", .effect = "behavioral", .description = "Vulkan spec gap: staging buffer for compressed tex-to-tex with non-block-aligned extents (crbug.com/dawn/42)" },
    .{ .toggle_name = "use_temp_buffer_in_small_format_texture_to_texture_copy_from_greater_to_less_mip_level", .effect = "behavioral", .description = "Intel Gen9/Gen11 D3D12 CopyTextureRegion bug for small-format mip copies (crbug.com/1161355)" },
    .{ .toggle_name = "d3d12_use_temp_buffer_in_depth_stencil_texture_and_buffer_copy_with_non_zero_buffer_offset", .effect = "behavioral", .description = "D3D12 depth-stencil copy restriction without programmable MSAA (crbug.com/dawn/727)" },
    .{ .toggle_name = "d3d12_use_temp_buffer_in_texture_to_texture_copy_between_different_dimensions", .effect = "behavioral", .description = "D3D12 cross-dimension texture copy not natively supported (crbug.com/dawn/1216)" },
    .{ .toggle_name = "MetalRenderR8RG8UnormSmallMipToTempTexture", .effect = "behavioral", .description = "Intel Metal: render to temp texture for R8/RG8 unorm small mips (level >= 2) (crbug.com/dawn/1071)" },
    .{ .toggle_name = "VulkanCooperativeMatrixStrideIsMatrixElements", .effect = "informational", .description = "treat cooperative matrix stride as matrix elements instead of pointee elements (Mali workaround)" },
    .{ .toggle_name = "disable_resource_suballocation", .effect = "informational", .description = "disable sub-allocation for buffers and textures" },
    .{ .toggle_name = "use_d3d12_render_pass", .effect = "informational", .description = "use D3D12 render pass API when available" },
    .{ .toggle_name = "use_dxc", .effect = "informational", .description = "use DXC compiler instead of FXC for HLSL" },
    .{ .toggle_name = "disable_robustness", .effect = "informational", .description = "disable robustness transforms in shaders" },
    .{ .toggle_name = "use_vulkan_zero_initialize_workgroup_memory_extension", .effect = "informational", .description = "use VK_KHR_zero_initialize_workgroup_memory when available" },
    .{ .toggle_name = "MetalReplaceWorkgroupBoolWithU32", .effect = "informational", .description = "replace workgroup bool with u32 in MSL for Mac AMD/Intel" },
};
pub const quirk_toggle_registry_json: []const u8 = "{\n  \"schemaVersion\": 1,\n  \"toggles\": [\n    {\n      \"toggle_name\": \"use_temporary_buffer_in_texture_to_texture_copy\",\n      \"effect\": \"behavioral\",\n      \"description\": \"Vulkan spec gap: staging buffer for compressed tex-to-tex with non-block-aligned extents (crbug.com/dawn/42)\"\n    },\n    {\n      \"toggle_name\": \"use_temp_buffer_in_small_format_texture_to_texture_copy_from_greater_to_less_mip_level\",\n      \"effect\": \"behavioral\",\n      \"description\": \"Intel Gen9/Gen11 D3D12 CopyTextureRegion bug for small-format mip copies (crbug.com/1161355)\"\n    },\n    {\n      \"toggle_name\": \"d3d12_use_temp_buffer_in_depth_stencil_texture_and_buffer_copy_with_non_zero_buffer_offset\",\n      \"effect\": \"behavioral\",\n      \"description\": \"D3D12 depth-stencil copy restriction without programmable MSAA (crbug.com/dawn/727)\"\n    },\n    {\n      \"toggle_name\": \"d3d12_use_temp_buffer_in_texture_to_texture_copy_between_different_dimensions\",\n      \"effect\": \"behavioral\",\n      \"description\": \"D3D12 cross-dimension texture copy not natively supported (crbug.com/dawn/1216)\"\n    },\n    {\n      \"toggle_name\": \"MetalRenderR8RG8UnormSmallMipToTempTexture\",\n      \"effect\": \"behavioral\",\n      \"description\": \"Intel Metal: render to temp texture for R8/RG8 unorm small mips (level >= 2) (crbug.com/dawn/1071)\"\n    },\n    {\n      \"toggle_name\": \"VulkanCooperativeMatrixStrideIsMatrixElements\",\n      \"effect\": \"informational\",\n      \"description\": \"treat cooperative matrix stride as matrix elements instead of pointee elements (Mali workaround)\"\n    },\n    {\n      \"toggle_name\": \"disable_resource_suballocation\",\n      \"effect\": \"informational\",\n      \"description\": \"disable sub-allocation for buffers and textures\"\n    },\n    {\n      \"toggle_name\": \"use_d3d12_render_pass\",\n      \"effect\": \"informational\",\n      \"description\": \"use D3D12 render pass API when available\"\n    },\n    {\n      \"toggle_name\": \"use_dxc\",\n      \"effect\": \"informational\",\n      \"description\": \"use DXC compiler instead of FXC for HLSL\"\n    },\n    {\n      \"toggle_name\": \"disable_robustness\",\n      \"effect\": \"informational\",\n      \"description\": \"disable robustness transforms in shaders\"\n    },\n    {\n      \"toggle_name\": \"use_vulkan_zero_initialize_workgroup_memory_extension\",\n      \"effect\": \"informational\",\n      \"description\": \"use VK_KHR_zero_initialize_workgroup_memory when available\"\n    },\n    {\n      \"toggle_name\": \"MetalReplaceWorkgroupBoolWithU32\",\n      \"effect\": \"informational\",\n      \"description\": \"replace workgroup bool with u32 in MSL for Mac AMD/Intel\"\n    }\n  ]\n}\n";
