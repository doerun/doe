const std = @import("std");
const vulkan_errors = @import("vulkan_errors.zig");

fn now_ns() u64 {
    const now = std.time.nanoTimestamp();
    if (now <= 0) return 0;
    return @as(u64, @intCast(now));
}

pub fn operation_timing_ns() vulkan_errors.VulkanError!u64 {
    return now_ns();
}
