const std = @import("std");

/// Legacy counter callers use zero for unavailable timing. Error-aware callers
/// use operation_timing_ns; neither value is a Unix epoch timestamp.
pub fn now_ns() u64 {
    return operation_timing_ns() catch 0;
}

pub fn operation_timing_ns() !u64 {
    const instant = try std.time.Instant.now();
    return instant.since(std.mem.zeroes(std.time.Instant));
}

pub fn ns_delta(after: u64, before: u64) u64 {
    if (before != 0 and after > before) return after - before;
    return 0;
}
