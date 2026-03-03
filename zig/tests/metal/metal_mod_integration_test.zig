const std = @import("std");
const builtin = @import("builtin");
const model = @import("../../src/model.zig");
const capabilities = @import("../../src/backend/common/capabilities.zig");
const metal_mod = @import("../../src/backend/metal/mod.zig");
const surface_procs = @import("../../src/wgpu_surface_procs.zig");

fn test_profile() model.DeviceProfile {
    return .{
        .vendor = "apple",
        .api = .metal,
        .device_family = "m3",
        .driver_version = .{ .major = 1, .minor = 0, .patch = 0 },
    };
}

fn skip_if_runtime_unavailable(err: anyerror) bool {
    return switch (err) {
        error.LibraryOpenFailed,
        error.SymbolMissing,
        error.AdapterUnavailable,
        error.AdapterRequestFailed,
        error.AdapterRequestNoCallback,
        error.DeviceRequestFailed,
        error.DeviceRequestNoCallback,
        error.NativeInstanceUnavailable,
        error.NativeQueueUnavailable,
        => true,
        else => false,
    };
}

test "metal backend init fails fast on non-macos hosts" {
    if (builtin.os.tag == .macos) return;
    try std.testing.expectError(
        error.UnsupportedFeature,
        metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null),
    );
}

test "metal backend capability declarations reflect probed runtime support" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_capability_probe", "test_policy_hash");
    defer iface.deinit();

    const has_surface_procs = surface_procs.loadSurfaceProcs(backend.inner.dyn_lib) != null;
    try std.testing.expectEqual(has_surface_procs, backend.capability_set.supports(capabilities.Capability.surface_lifecycle));
    try std.testing.expectEqual(has_surface_procs, backend.capability_set.supports(capabilities.Capability.surface_present));

    const has_multi_draw_indirect = backend.inner.has_multi_draw_indirect;
    try std.testing.expectEqual(has_multi_draw_indirect, backend.capability_set.supports(capabilities.Capability.indirect_draw));
    try std.testing.expectEqual(has_multi_draw_indirect, backend.capability_set.supports(capabilities.Capability.indexed_indirect_draw));
}

test "metal backend executes kernel_dispatch and emits manifest telemetry" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_manifest", "test_policy_hash");
    defer iface.deinit();

    const result = try iface.execute_command(model.Command{ .kernel_dispatch = .{
        .kernel = "bench/kernels/shader_compile_pipeline_stress.wgsl",
        .x = 1,
        .y = 1,
        .z = 1,
    } });

    try std.testing.expect(result.status == .ok);
    try std.testing.expect(result.dispatch_count >= 1);

    const manifest_path = metal_mod.manifest_path_from_context(iface.context);
    const manifest_hash = metal_mod.manifest_hash_from_context(iface.context);
    try std.testing.expect(manifest_path != null);
    try std.testing.expect(manifest_hash != null);
    if (manifest_path) |path| {
        try std.testing.expect(path.len > 0);
    }
    if (manifest_hash) |hash| {
        try std.testing.expect(hash.len == 64);
    }

    if (manifest_path) |path| {
        const bytes = try std.fs.cwd().readFileAlloc(std.testing.allocator, path, 4096);
        defer std.testing.allocator.free(bytes);

        const needle = "\"statusCode\":\"";
        const start = std.mem.indexOf(u8, bytes, needle) orelse return error.MissingStatusCodeField;
        const value_index = start + needle.len;
        try std.testing.expect(value_index < bytes.len);
        try std.testing.expect(bytes[value_index] != '"');
    }
}

test "metal backend queue sync mode deferred executes kernel dispatch" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_queue_sync", "test_policy_hash");
    defer iface.deinit();

    iface.set_queue_sync_mode(.deferred);
    const result = try iface.execute_command(model.Command{ .kernel_dispatch = .{
        .kernel = "bench/kernels/shader_compile_pipeline_stress.wgsl",
        .x = 1,
        .y = 1,
        .z = 1,
    } });

    try std.testing.expect(result.status == .ok);
    try std.testing.expect(result.dispatch_count >= 1);
}

test "metal backend upload cadence and flush queue preserve execution result" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_upload_flush", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expect(first.status == .ok);
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);

    const flush_ns = try iface.flush_queue();
    try std.testing.expect(flush_ns > 0);

    const second = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expect(second.status == .ok);
    try std.testing.expectEqual(@as(u64, 0), second.submit_wait_ns);
}
