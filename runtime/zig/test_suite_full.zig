const aggregate_test_suite = @import("test_suite.zig");
const core_command_partition_test = @import("tests/core/command_partition_test.zig");
const full_command_partition_test = @import("tests/full/command_partition_test.zig");
const core_surface_test = @import("tests/core/surface_test.zig");
const full_surface_api_test = @import("tests/full/surface_api_test.zig");

comptime {
    _ = aggregate_test_suite;
    _ = core_command_partition_test;
    _ = full_command_partition_test;
    _ = core_surface_test;
    _ = full_surface_api_test;
}
