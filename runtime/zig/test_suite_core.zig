const common_artifact_meta_test = @import("tests/backend/common_artifact_meta_test.zig");
const common_capabilities_test = @import("tests/backend/common_capabilities_test.zig");
const common_command_info_test = @import("tests/backend/common_command_info_test.zig");
const common_errors_test = @import("tests/backend/common_errors_test.zig");
const common_timing_test = @import("tests/backend/common_timing_test.zig");
const core_command_partition_test = @import("tests/core/command_partition_test.zig");
const core_surface_test = @import("tests/core/surface_test.zig");
const wgpu_resource_normalizers_test = @import("src/core/resource/wgpu_resource_normalizers.zig");
const command_json_test = @import("src/command_json.zig");
const common_hash_utils = @import("src/backend/common/hash_utils.zig");
const common_artifact_state = @import("src/backend/common/artifact_state.zig");

comptime {
    _ = common_artifact_meta_test;
    _ = common_capabilities_test;
    _ = common_command_info_test;
    _ = common_errors_test;
    _ = common_timing_test;
    _ = core_command_partition_test;
    _ = core_surface_test;
    _ = wgpu_resource_normalizers_test;
    _ = command_json_test;
    _ = common_hash_utils;
    _ = common_artifact_state;
}
