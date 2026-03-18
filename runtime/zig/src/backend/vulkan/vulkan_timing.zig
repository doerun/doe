// GPU timestamp query helpers for the Vulkan backend.
// Data structures and pure arithmetic only — no Vulkan API calls.

const common_timing = @import("../common/timing.zig");

pub const now_ns = common_timing.now_ns;
pub const operation_timing_ns = common_timing.operation_timing_ns;
pub const ns_delta = common_timing.ns_delta;

/// Begin + end timestamp pair.
pub const TIMESTAMP_QUERY_COUNT: u32 = 2;

/// Byte size for the readback buffer: 2 x @sizeOf(u64).
pub const TIMESTAMP_BUFFER_SIZE: u64 = 16;

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
pub fn computeElapsedNs(begin_tick: u64, end_tick: u64, timestamp_period: f32) u64 {
    if (end_tick <= begin_tick) return 0;
    const delta: f64 = @floatFromInt(end_tick - begin_tick);
    const ns: f64 = delta * @as(f64, @floatCast(timestamp_period));
    if (ns <= 0.0) return 0;
    return @intFromFloat(ns);
}
