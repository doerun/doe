// GPU timestamp query helpers for the Vulkan backend.
// Data structures and pure arithmetic only — no Vulkan API calls.

const std = @import("std");
const common_timing = @import("../common/timing.zig");

pub const now_ns = common_timing.now_ns;
pub const operation_timing_ns = common_timing.operation_timing_ns;
pub const ns_delta = common_timing.ns_delta;

/// Begin + end timestamp pair.
pub const TIMESTAMP_QUERY_COUNT: u32 = 2;

/// Byte size for the readback buffer: 2 x @sizeOf(u64).
pub const TIMESTAMP_BUFFER_SIZE: u64 = TIMESTAMP_QUERY_COUNT * @sizeOf(u64);

/// Holds Vulkan handles and calibration data needed to issue and resolve
/// GPU timestamp queries. Fields are nullable so the struct can exist in
/// an uninitialised state before the device exposes timestamp support.
pub const TimestampState = struct {
    query_pool: ?*anyopaque = null,
    resolve_buffer: ?*anyopaque = null,
    /// Nanoseconds per GPU timestamp tick (from VkPhysicalDeviceProperties.limits.timestampPeriod).
    timestamp_period: f32 = 0.0,
    valid: bool = false,
};

/// Convert a begin/end GPU tick pair into elapsed nanoseconds using the
/// device's timestamp period.
pub fn computeElapsedNs(begin_tick: u64, end_tick: u64, timestamp_period: f32, valid_bits: u32) !u64 {
    if (!std.math.isFinite(timestamp_period) or timestamp_period <= 0 or valid_bits == 0 or valid_bits > 64) return error.InvalidArgument;
    const mask = @as(u64, std.math.maxInt(u64)) >> @as(u6, @intCast(64 - valid_bits));
    const delta: f64 = @floatFromInt((end_tick -% begin_tick) & mask);
    const ns: f64 = delta * @as(f64, @floatCast(timestamp_period));
    const U64_LIMIT_EXCLUSIVE: f64 = 0x1p64;
    if (!std.math.isFinite(ns) or ns >= U64_LIMIT_EXCLUSIVE) return error.InvalidState;
    return @intFromFloat(ns);
}

test "Vulkan elapsed timestamps wrap at the queue counter width" {
    try std.testing.expectEqual(@as(u64, 27), try computeElapsedNs(250, 5, 2.5, 8));
    try std.testing.expectEqual(@as(u64, 25), try computeElapsedNs(std.math.maxInt(u64) - 9, 15, 1, 64));
    try std.testing.expectEqual(@as(u64, 0), try computeElapsedNs(7, 7, 1, 64));
    try std.testing.expectEqual(@as(u64, 12), try computeElapsedNs(10, 15, 2.5, 64));
}

test "Vulkan elapsed timestamps reject invalid calibration and unrepresentable nanoseconds" {
    for ([_]f32{ 0, -1, std.math.inf(f32), std.math.nan(f32) }) |period| {
        try std.testing.expectError(error.InvalidArgument, computeElapsedNs(1, 2, period, 64));
    }
    try std.testing.expectError(error.InvalidArgument, computeElapsedNs(1, 2, 1, 0));
    try std.testing.expectError(error.InvalidArgument, computeElapsedNs(1, 2, 1, 65));
    try std.testing.expectError(error.InvalidState, computeElapsedNs(0, std.math.maxInt(u64), 1, 64));
}
