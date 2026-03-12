const common_artifact_meta_test = @import("tests/backend/common_artifact_meta_test.zig");
const common_capabilities_test = @import("tests/backend/common_capabilities_test.zig");
const common_command_info_test = @import("tests/backend/common_command_info_test.zig");
const common_errors_test = @import("tests/backend/common_errors_test.zig");
const common_timing_test = @import("tests/backend/common_timing_test.zig");
const core_command_partition_test = @import("tests/core/command_partition_test.zig");
const core_surface_test = @import("tests/core/surface_test.zig");

comptime {
    _ = common_artifact_meta_test;
    _ = common_capabilities_test;
    _ = common_command_info_test;
    _ = common_errors_test;
    _ = common_timing_test;
    _ = core_command_partition_test;
    _ = core_surface_test;
}
