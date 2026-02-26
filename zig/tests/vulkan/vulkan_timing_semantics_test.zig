const vulkan_timing = @import("../../src/backend/vulkan/vulkan_timing.zig");

test "vulkan timing source query succeeds" {
    const timing_ns = try vulkan_timing.operation_timing_ns();
    try std.testing.expect(timing_ns > 0);
}
