const std = @import("std");
const builtin = @import("builtin");
const model = @import("../../src/model.zig");
const webgpu = @import("../../src/webgpu_ffi.zig");
const metal_mod = @import("../../src/backend/metal/mod.zig");

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
        error.UnsupportedFeature,
        => true,
        else => false,
    };
}

test "metal upload timing charges staged host work to setup ns" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_timing", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 1);
    const result = try iface.execute_command(model.Command{ .upload = .{
        .bytes = 1024 * 1024,
        .align_bytes = 4,
    } });
    try std.testing.expect(result.status == .ok);
    try std.testing.expect(result.setup_ns > 0);
    try std.testing.expectEqual(@as(u64, 0), result.encode_ns);
    try std.testing.expect(result.submit_wait_ns > 0);
}

test "metal upload flush cadence reports nonzero submit_wait_ns" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_barrier_timing", "test_policy_hash");
    defer iface.deinit();

    // With submit_every = 1, every upload should flush inline.
    iface.set_upload_behavior(.copy_dst, 1);
    const upload_result = try iface.execute_command(model.Command{ .upload = .{
        .bytes = 256 * 1024,
        .align_bytes = 4,
    } });
    try std.testing.expect(upload_result.status == .ok);
    try std.testing.expect(upload_result.submit_wait_ns > 0);
}

test "metal deferred upload keeps per-command submit_wait_ns at zero until final flush" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_deferred_upload_timing", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 1);
    iface.set_queue_sync_mode(.deferred);

    const upload_result = try iface.execute_command(model.Command{ .upload = .{
        .bytes = 256 * 1024,
        .align_bytes = 4,
    } });
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, upload_result.status);
    try std.testing.expectEqual(@as(u64, 0), upload_result.submit_wait_ns);

    const flush_ns = try iface.flush_queue();
    try std.testing.expect(flush_ns > 0);
}

test "metal barrier flushes deferred upload work" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_barrier_flush", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 1);
    iface.set_queue_sync_mode(.deferred);

    const upload_result = try iface.execute_command(model.Command{ .upload = .{
        .bytes = 64 * 1024,
        .align_bytes = 4,
    } });
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, upload_result.status);
    try std.testing.expectEqual(@as(u64, 0), upload_result.submit_wait_ns);

    const barrier_result = try iface.execute_command(model.Command{ .barrier = .{ .dependency_count = 1 } });
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, barrier_result.status);
    try std.testing.expect(barrier_result.submit_wait_ns > 0);
}

test "metal kernel_dispatch returns error when kernel file not found" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_timing_unsupported", "test_policy_hash");
    defer iface.deinit();

    const result = try iface.execute_command(model.Command{ .kernel_dispatch = .{
        .kernel = "bench/kernels/shader_compile_pipeline_stress.wgsl",
        .x = 1,
        .y = 1,
        .z = 1,
    } });

    // Native Metal implements kernel_dispatch natively via MSL.
    // Tests run from fawn/zig/ so bench/kernels/ is not on the lookup path; expect .@"error".
    try std.testing.expect(result.status == .@"error");
}

test "metal copy contract path executes native buffer-to-texture copy" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_copy_contract", "test_policy_hash");
    defer iface.deinit();

    const result = try iface.execute_command(model.Command{ .copy_buffer_to_texture = .{
        .direction = .buffer_to_texture,
        .src = .{ .handle = 51, .offset = 0, .bytes_per_row = 8, .rows_per_image = 2 },
        .dst = .{ .handle = 52, .kind = .texture, .width = 2, .height = 2, .depth_or_array_layers = 1, .format = model.WGPUTextureFormat_RGBA8Unorm, .usage = model.WGPUTextureUsage_CopyDst | model.WGPUTextureUsage_TextureBinding, .bytes_per_row = 8, .rows_per_image = 2 },
        .bytes = 16,
    } });
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, result.status);
    try std.testing.expect(result.encode_ns > 0 or result.submit_wait_ns > 0);
}

test "metal surface lifecycle executes full presentation protocol" {
    if (builtin.os.tag != .macos) return;

    const backend = metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null) catch |err| {
        if (skip_if_runtime_unavailable(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_surface_contract", "test_policy_hash");
    defer iface.deinit();

    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, (try iface.execute_command(model.Command{ .surface_create = .{ .handle = 901 } })).status);
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, (try iface.execute_command(model.Command{ .surface_capabilities = .{ .handle = 901 } })).status);
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, (try iface.execute_command(model.Command{ .surface_configure = .{ .handle = 901, .width = 64, .height = 64, .format = model.WGPUTextureFormat_RGBA8Unorm } })).status);
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, (try iface.execute_command(model.Command{ .surface_acquire = .{ .handle = 901 } })).status);
    const present = try iface.execute_command(model.Command{ .surface_present = .{ .handle = 901 } });
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, present.status);
    try std.testing.expect(present.submit_wait_ns > 0);
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, (try iface.execute_command(model.Command{ .surface_unconfigure = .{ .handle = 901 } })).status);
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, (try iface.execute_command(model.Command{ .surface_release = .{ .handle = 901 } })).status);
}
