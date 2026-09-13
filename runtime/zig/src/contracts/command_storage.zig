const std = @import("std");

pub const POLICY_VERSION: u32 = 1;
pub const MAX_POLICY_BYTES: usize = 64 * 1024;
pub const Policy = struct { schemaVersion: u32, maxRetainedBytes: u32 };
pub const ObservationMode = enum { ordinary, counters, timed };
pub const ObservationPolicy = struct { schemaVersion: u32, mode: ObservationMode };
pub const OPERATION_ID = "native-command-storage";

pub fn parsePolicy(allocator: std.mem.Allocator, bytes: []const u8) !Policy {
    try requireIntegerFields(Policy, allocator, bytes);
    const parsed = try std.json.parseFromSlice(Policy, allocator, bytes, .{});
    defer parsed.deinit();
    if (parsed.value.schemaVersion != POLICY_VERSION) return error.UnsupportedCommandStoragePolicyVersion;
    return parsed.value;
}

pub fn parseObservation(allocator: std.mem.Allocator, bytes: []const u8) !ObservationPolicy {
    try requireIntegerFields(ObservationPolicy, allocator, bytes);
    const parsed = try std.json.parseFromSlice(ObservationPolicy, allocator, bytes, .{});
    defer parsed.deinit();
    if (parsed.value.schemaVersion != POLICY_VERSION) return error.UnsupportedCommandStorageObservationVersion;
    return parsed.value;
}

fn requireIntegerFields(comptime T: type, allocator: std.mem.Allocator, bytes: []const u8) !void {
    const parsed = try std.json.parseFromSlice(std.json.Value, allocator, bytes, .{});
    defer parsed.deinit();
    if (parsed.value != .object) return error.ExpectedPolicyObject;
    inline for (@typeInfo(T).@"struct".fields) |field| {
        if (@typeInfo(field.type) == .int) {
            const value = parsed.value.object.get(field.name) orelse return error.MissingField;
            if (value != .integer) return error.ExpectedPolicyInteger;
        }
    }
}

pub const Metric = enum {
    take_calls,
    reuse_hits,
    recycle_calls,
    retained_returns,
    freed_returns,
    peak_retained_bytes,
    reservation_calls,
    capacity_growths,
    growth_failures,
    grown_bytes,
    contended_locks,
    lock_wait_ns,
    unavailable_clock_reads,
};

pub const MetricInfo = struct {
    unit: enum { count, bytes, nanoseconds },
    scope: enum { pool, ordinary_recording, contended_pool_lock },
};

pub fn metricInfo(metric: Metric) MetricInfo {
    return switch (metric) {
        .take_calls, .reuse_hits, .recycle_calls, .retained_returns, .freed_returns => .{ .unit = .count, .scope = .pool },
        .peak_retained_bytes => .{ .unit = .bytes, .scope = .pool },
        .reservation_calls, .capacity_growths, .growth_failures => .{ .unit = .count, .scope = .ordinary_recording },
        .grown_bytes => .{ .unit = .bytes, .scope = .ordinary_recording },
        .contended_locks, .unavailable_clock_reads => .{ .unit = .count, .scope = .contended_pool_lock },
        .lock_wait_ns => .{ .unit = .nanoseconds, .scope = .contended_pool_lock },
    };
}

pub const Measurement = struct {
    id: Metric,
    unit: @FieldType(MetricInfo, "unit"),
    scope: @FieldType(MetricInfo, "scope"),
    value: ?u64,
};
pub const METRIC_COUNT = @typeInfo(Metric).@"enum".fields.len;

pub fn metadata() [METRIC_COUNT]Measurement {
    var result: [METRIC_COUNT]Measurement = undefined;
    for (std.enums.values(Metric), 0..) |metric, index| {
        const info = metricInfo(metric);
        result[index] = .{ .id = metric, .unit = info.unit, .scope = info.scope, .value = null };
    }
    return result;
}

pub const Snapshot = struct {
    mode: ObservationMode,
    command_size_bytes: usize,
    max_retained_bytes: usize,
    retained_bytes: usize,
    counter_overflow: bool,
    measurements: [METRIC_COUNT]Measurement,
};

comptime {
    // Exhaustion checks metadata coverage, not measurement or ownership correctness.
    _ = metadata();
}

fn parseAllocationFailure(allocator: std.mem.Allocator) !void {
    _ = try parsePolicy(allocator, "{\"schemaVersion\":1,\"maxRetainedBytes\":0}");
    _ = try parseObservation(allocator, "{\"schemaVersion\":1,\"mode\":\"timed\"}");
}

test "command storage policy build parsing unwinds allocation failure" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, parseAllocationFailure, .{});
}

test "command storage build rejects unsupported and incomplete policies" {
    const allocator = std.testing.allocator;
    try std.testing.expectError(error.UnsupportedCommandStoragePolicyVersion, parsePolicy(allocator, "{\"schemaVersion\":2,\"maxRetainedBytes\":0}"));
    try std.testing.expectError(error.MissingField, parsePolicy(allocator, "{\"schemaVersion\":1}"));
    try std.testing.expectError(error.UnknownField, parsePolicy(allocator, "{\"schemaVersion\":1,\"maxRetainedBytes\":0,\"fallback\":true}"));
    try std.testing.expectError(error.InvalidEnumTag, parseObservation(allocator, "{\"schemaVersion\":1,\"mode\":\"automatic\"}"));
    try std.testing.expectError(error.ExpectedPolicyInteger, parsePolicy(allocator, "{\"schemaVersion\":1,\"maxRetainedBytes\":\"0\"}"));
    try std.testing.expectError(error.ExpectedPolicyInteger, parsePolicy(allocator, "{\"schemaVersion\":1,\"maxRetainedBytes\":1.5}"));
}
