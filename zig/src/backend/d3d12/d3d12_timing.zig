const std = @import("std");
const d3d12_errors = @import("d3d12_errors.zig");

fn now_ns() u64 {
    const now = std.time.nanoTimestamp();
    if (now <= 0) return 0;
    return @as(u64, @intCast(now));
}

pub fn operation_timing_ns() d3d12_errors.D3D12Error!u64 {
    return now_ns();
}
