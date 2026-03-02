const std = @import("std");
const model = @import("../../src/model.zig");
const webgpu = @import("../../src/webgpu_ffi.zig");
const d3d12_mod = @import("../../src/backend/d3d12/mod.zig");
const d3d12_timing = @import("../../src/backend/d3d12/d3d12_timing.zig");

test "d3d12 timing source query succeeds" {
    const timing_ns = try d3d12_timing.operation_timing_ns();
    try std.testing.expect(timing_ns > 0);
}

test "d3d12 dispatch timing separates encode and submit-wait buckets" {
    const result = try d3d12_mod.run_contract_path_for_test(
        model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } },
        webgpu.QueueSyncMode.per_command,
    );
    try std.testing.expectEqual(@as(u64, 13_700), result.encode_ns);
    try std.testing.expectEqual(@as(u64, 16_000), result.submit_wait_ns);
}

test "d3d12 deferred sync records submit cost but not per-command wait cost" {
    const result = try d3d12_mod.run_contract_path_for_test(
        model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } },
        webgpu.QueueSyncMode.deferred,
    );
    try std.testing.expectEqual(@as(u64, 13_700), result.encode_ns);
    try std.testing.expectEqual(@as(u64, 7_000), result.submit_wait_ns);
}
