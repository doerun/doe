const std = @import("std");
const native = @import("../../src/native/mod.zig");
const objects = @import("../../src/native/support/doe_native_object_types.zig");
const helpers = @import("../../src/native/support/doe_native_object_helpers.zig");
const lifecycle = @import("../../src/native/lifecycle/doe_instance_device_native.zig");
const buffers = @import("../../src/native/resource/doe_buffer_ops_native.zig");
const queue = @import("../../src/native/queue/doe_queue_submit_native.zig");
const base = @import("../../src/core/abi/wgpu_core_base_types.zig");
const callbacks = @import("../../src/core/abi/wgpu_callback_descriptor_types.zig");

test "last external device release invalidates while internal cleanup lease survives" {
    const device = helpers.make(objects.DoeDevice) orelse return error.OutOfMemory;
    device.* = .{ .backend = .vulkan };
    const raw = helpers.toOpaque(device);
    lifecycle.doeNativeDeviceRetainInternal(raw);
    lifecycle.doeNativeDeviceAddRef(raw);
    lifecycle.doeNativeDeviceRelease(raw);
    try std.testing.expect(!device.isDestroyed());
    try std.testing.expectEqual(@as(u32, 2), device.ref_count);
    lifecycle.doeNativeDeviceRelease(raw);
    try std.testing.expect(device.isDestroyed());
    try std.testing.expectEqual(@as(u32, 0), device.external_ref_count);
    try std.testing.expectEqual(@as(u32, 1), device.ref_count);
    lifecycle.doeNativeDeviceDestroy(raw);
    try std.testing.expectEqual(@as(u32, 1), device.ref_count);
    lifecycle.doeNativeDeviceReleaseInternal(raw);
}

test "destroyed device rejects construction submission writes and successful mapping" {
    var device = objects.DoeDevice{ .destroyed = true };
    const raw = helpers.toOpaque(&device);
    try std.testing.expect(native.doeNativeDeviceCreateBuffer(raw, null) == null);
    try std.testing.expect(native.doeNativeDeviceCreateShaderModule(raw, null) == null);
    try std.testing.expect(native.doeNativeDeviceCreateComputePipeline(raw, null) == null);
    try std.testing.expect(native.doeNativeDeviceCreateRenderPipeline(raw, null) == null);
    try std.testing.expect(native.doeNativeDeviceCreateCommandEncoder(raw, null) == null);
    try std.testing.expect(native.doeNativeDeviceCreatePipelineLayout(raw, null) == null);
    try std.testing.expect(native.doeNativeDeviceCreateBindGroup(raw, null) == null);
    var bytes = [_]u8{0} ** 16;
    var q = objects.DoeQueue{ .dev = &device };
    var b = objects.DoeBuffer{ .dev = &device, .device_ref = &device, .ref_count = 2, .size = bytes.len, .usage = base.WGPUBufferUsage_MapRead | base.WGPUBufferUsage_CopyDst, .metal_mapped_ptr = &bytes };
    const pattern = [_]u8{42} ** bytes.len;
    queue.doeNativeQueueWriteBuffer(helpers.toOpaque(&q), helpers.toOpaque(&b), 0, &pattern, pattern.len);
    try std.testing.expectEqualSlices(u8, &([_]u8{0} ** 16), &bytes);
    const commands = [_]?*anyopaque{null};
    queue.doeNativeQueueSubmit(helpers.toOpaque(&q), 1, &commands);
    var status: u32 = 0;
    var info = std.mem.zeroes(callbacks.WGPUBufferMapCallbackInfo);
    info.userdata1 = &status;
    info.callback = struct {
        fn receive(value: u32, _: base.WGPUStringView, userdata: ?*anyopaque, _: ?*anyopaque) callconv(.c) void {
            const out: *u32 = @ptrCast(@alignCast(userdata.?));
            out.* = value;
        }
    }.receive;
    _ = buffers.doeNativeBufferMapAsync(helpers.toOpaque(&b), base.WGPUMapMode_Read, 0, bytes.len, info);
    try std.testing.expectEqual(@as(u32, 4), status);
    try std.testing.expect(!b.mapped);
    try std.testing.expectEqual(@as(u32, 2), b.ref_count);
    try std.testing.expectEqual(@as(u32, 1), device.ref_count);
}
