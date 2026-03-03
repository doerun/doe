const backend_registry_test = @import("tests/backend/backend_registry_test.zig");
const backend_runtime_config_policy_test = @import("tests/backend/backend_runtime_config_policy_test.zig");
const backend_runtime_policy_test = @import("tests/backend/backend_runtime_policy_test.zig");
const backend_selection_policy_test = @import("tests/backend/backend_selection_policy_test.zig");
const backend_vulkan_doe_app_lane_policy_test = @import("tests/backend/backend_vulkan_doe_app_lane_policy_test.zig");
const common_artifact_meta_test = @import("tests/backend/common_artifact_meta_test.zig");
const common_capabilities_test = @import("tests/backend/common_capabilities_test.zig");
const common_command_info_test = @import("tests/backend/common_command_info_test.zig");
const common_errors_test = @import("tests/backend/common_errors_test.zig");
const common_timing_test = @import("tests/backend/common_timing_test.zig");
const d3d12_mod_integration_test = @import("tests/d3d12/d3d12_mod_integration_test.zig");
const d3d12_timing_semantics_test = @import("tests/d3d12/d3d12_timing_semantics_test.zig");

comptime {
    _ = backend_registry_test;
    _ = backend_runtime_config_policy_test;
    _ = backend_runtime_policy_test;
    _ = backend_selection_policy_test;
    _ = backend_vulkan_doe_app_lane_policy_test;
    _ = common_artifact_meta_test;
    _ = common_capabilities_test;
    _ = common_command_info_test;
    _ = common_errors_test;
    _ = common_timing_test;
    _ = d3d12_mod_integration_test;
    _ = d3d12_timing_semantics_test;
}
