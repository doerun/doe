const std = @import("std");
const model_async_types = @import("../../../contracts/model/model_async_types.zig");
const common_timing = @import("../../common/timing.zig");
const bridge = @import("../d3d12_bridge_decls.zig");

pub const AsyncDiagnosticsMetrics = struct {
    setup_ns: u64 = 0,
    encode_ns: u64 = 0,
};

pub fn validateMode(mode: model_async_types.AsyncDiagnosticsMode) !void {
    switch (mode) {
        .lifecycle_refcount => {},
        .pipeline_async, .capability_introspection, .resource_table_immediates, .pixel_local_storage, .full => return error.UnsupportedFeature,
    }
}

pub fn execute_async_diagnostics(device: ?*anyopaque, cmd: model_async_types.AsyncDiagnosticsCommand) !AsyncDiagnosticsMetrics {
    try validateMode(cmd.mode);
    if (device == null) return error.InvalidState;
    const iterations = if (cmd.iterations == 0) @as(u32, 1) else cmd.iterations;
    return execute_lifecycle_refcount(device, iterations);
}

fn execute_lifecycle_refcount(device: ?*anyopaque, iterations: u32) !AsyncDiagnosticsMetrics {
    const encode_start = try common_timing.operation_timing_ns();
    var i: u32 = 0;
    while (i < iterations) : (i += 1) {
        const root_sig = bridge.c.d3d12_bridge_device_create_root_signature_empty(device) orelse return error.InvalidState;
        bridge.c.d3d12_bridge_release(root_sig);
    }
    return .{ .encode_ns = common_timing.ns_delta(try common_timing.operation_timing_ns(), encode_start) };
}

test "D3D12 diagnostics reject modes without native execution" {
    try validateMode(.lifecycle_refcount);
    try std.testing.expectError(error.InvalidState, execute_async_diagnostics(null, .{ .mode = .lifecycle_refcount }));
    inline for (.{ .pipeline_async, .capability_introspection, .resource_table_immediates, .pixel_local_storage, .full }) |mode| {
        try std.testing.expectError(error.UnsupportedFeature, validateMode(mode));
        try std.testing.expectError(error.UnsupportedFeature, execute_async_diagnostics(null, .{ .mode = mode }));
    }
}
