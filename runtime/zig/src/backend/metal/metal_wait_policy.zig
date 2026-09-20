const std = @import("std");

pub const VERSION: u32 = 1;
pub const MAX_POLICY_BYTES: usize = 4096;
pub const Policy = struct {
    schemaVersion: u32,
    timeoutNs: u64,
    pollIntervalNs: u64,
};

pub fn parse(allocator: std.mem.Allocator, bytes: []const u8) !Policy {
    const value = try std.json.parseFromSlice(std.json.Value, allocator, bytes, .{});
    defer value.deinit();
    if (value.value != .object) return error.ExpectedPolicyObject;
    inline for (@typeInfo(Policy).@"struct".fields) |field| {
        const item = value.value.object.get(field.name) orelse return error.MissingField;
        if (item != .integer) return error.ExpectedPolicyInteger;
    }
    const parsed = try std.json.parseFromSlice(Policy, allocator, bytes, .{});
    defer parsed.deinit();
    if (parsed.value.schemaVersion != VERSION) return error.UnsupportedMetalWaitPolicyVersion;
    if (parsed.value.timeoutNs == 0 or parsed.value.pollIntervalNs == 0) return error.InvalidMetalWaitPolicy;
    return parsed.value;
}

pub fn compiled() Policy {
    const options = @import("build_options");
    return .{
        .schemaVersion = VERSION,
        .timeoutNs = options.metal_wait_timeout_ns,
        .pollIntervalNs = options.metal_wait_poll_interval_ns,
    };
}

fn parseWithAllocator(allocator: std.mem.Allocator) !void {
    _ = try parse(allocator, "{\"schemaVersion\":1,\"timeoutNs\":100,\"pollIntervalNs\":10}");
}

test "Metal wait policy rejects incomplete coerced unknown and unbounded choices" {
    const allocator = std.testing.allocator;
    try std.testing.expectError(error.MissingField, parse(allocator, "{\"schemaVersion\":1,\"timeoutNs\":100}"));
    try std.testing.expectError(error.ExpectedPolicyInteger, parse(allocator, "{\"schemaVersion\":1,\"timeoutNs\":\"100\",\"pollIntervalNs\":10}"));
    try std.testing.expectError(error.UnknownField, parse(allocator, "{\"schemaVersion\":1,\"timeoutNs\":100,\"pollIntervalNs\":10,\"fallback\":true}"));
    try std.testing.expectError(error.UnsupportedMetalWaitPolicyVersion, parse(allocator, "{\"schemaVersion\":2,\"timeoutNs\":100,\"pollIntervalNs\":10}"));
    try std.testing.expectError(error.InvalidMetalWaitPolicy, parse(allocator, "{\"schemaVersion\":1,\"timeoutNs\":0,\"pollIntervalNs\":10}"));
    try std.testing.expectError(error.InvalidMetalWaitPolicy, parse(allocator, "{\"schemaVersion\":1,\"timeoutNs\":100,\"pollIntervalNs\":0}"));
    try std.testing.checkAllAllocationFailures(allocator, parseWithAllocator, .{});
}
