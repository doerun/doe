const std = @import("std");

pub fn now_ns() u64 {
    const ts = std.time.nanoTimestamp();
    if (ts <= 0) return 0;
    return @as(u64, @intCast(ts));
}

pub fn operation_timing_ns() !u64 {
    return now_ns();
}

pub fn ns_delta(after: u64, before: u64) u64 {
    if (after > before) return after - before;
    return 0;
}
