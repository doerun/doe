// Native immediate-data admission. Shader-visible payload execution is unsupported.

const std = @import("std");
const recording = @import("doe_command_recording.zig");
const native_types = @import("../support/doe_native_object_types.zig");
const native_helpers = @import("../support/doe_native_object_helpers.zig");
const render_bundle = @import("../../runtime/render/render_bundle.zig");
const bundle_native = @import("../render/doe_bundle_native.zig");
const contract = @import("../../contracts/command_recording.zig");

fn validate_payload(index: u32, data_ptr: ?[*]const u8, data_len: usize) contract.Failure!void {
    if (data_len != 0 and data_ptr == null) return error.InvalidArgument;
    if (index != 0 or data_len != 0) return error.ImmediateDataUnsupported;
}

pub export fn doeNativeBindingCommandsSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    _ = encoder_raw;
    _ = index;
    _ = data_ptr;
    _ = data_len;
    std.log.err("doe: doeNativeBindingCommandsSetImmediates: unsupported — " ++
        "abstract mixin entry has no standalone encoder type; use the concrete " ++
        "compute/render pass setImmediates entry points", .{});
}

pub export fn doeNativeComputePassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    const encoder = native_helpers.cast(native_types.DoeComputePass, encoder_raw) orelse return;
    if (!recording.requirePass(encoder.enc, @intFromPtr(encoder))) return;
    validate_payload(index, data_ptr, data_len) catch |err| recording.fail(encoder.enc, err);
}

pub export fn doeNativeRenderPassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    const encoder = native_helpers.cast(native_types.DoeRenderPass, encoder_raw) orelse return;
    if (!recording.requirePass(encoder.enc, @intFromPtr(encoder))) return;
    validate_payload(index, data_ptr, data_len) catch |err| recording.fail(encoder.enc, err);
}

pub export fn doeNativeRenderBundleEncoderSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    const encoder = render_bundle.cast_bundle_encoder(encoder_raw) orelse return;
    if (!bundle_native.requireBundleOpen(encoder)) return;
    validate_payload(index, data_ptr, data_len) catch |err| bundle_native.failBundle(encoder, err);
}

test "immediate payload rejection invalidates compute render and bundle recording" {
    const encoders = @import("doe_encoder_native.zig");
    const compute = @import("../compute/doe_compute_ext_native.zig");
    const render = @import("../render/doe_render_native.zig");
    const errors = @import("../../runtime/diagnostics/error_scope.zig");
    const Capture = struct {
        rejected: bool = false,
        fn receive(kind: u32, message: @import("../../core/abi/wgpu_handle_types.zig").WGPUStringView, raw: ?*anyopaque, _: ?*anyopaque) callconv(.c) void {
            const self: *@This() = @ptrCast(@alignCast(raw.?));
            self.rejected = kind == errors.ERROR_TYPE_VALIDATION and message.data != null and
                std.mem.indexOf(u8, message.data[0..message.length], "shader-visible immediate data is unsupported") != null;
        }
    };
    var device = native_types.DoeDevice{};
    const bytes = [_]u8{ 1, 2, 3, 4 };
    for ([_]bool{ false, true }) |render_pass| {
        const encoder = try encoders.createEncoder(std.testing.allocator, &device);
        defer encoders.doeNativeCommandEncoderRelease(encoder);
        const pass = if (render_pass)
            render.doeNativeCommandEncoderBeginRenderPass(encoder, null).?
        else
            encoders.doeNativeCommandEncoderBeginComputePass(encoder, null).?;
        defer if (render_pass) render.doeNativeRenderPassRelease(pass) else compute.doeNativeComputePassRelease(pass);
        device.error_scopes.push(errors.FILTER_VALIDATION);
        if (render_pass) {
            doeNativeRenderPassSetImmediates(pass, 0, null, 0);
            try std.testing.expect(encoder.state == .pass);
            doeNativeRenderPassSetImmediates(pass, 0, &bytes, bytes.len);
        } else {
            doeNativeComputePassSetImmediates(pass, 0, null, 0);
            try std.testing.expect(encoder.state == .pass);
            doeNativeComputePassSetImmediates(pass, 0, &bytes, bytes.len);
        }
        try std.testing.expectEqual(error.ImmediateDataUnsupported, encoder.state.failed);
        var capture = Capture{};
        try std.testing.expect(device.error_scopes.pop(.{ .callback = Capture.receive, .userdata1 = &capture }));
        try std.testing.expect(capture.rejected);
        const commands = encoders.doeNativeCommandEncoderFinish(encoder, null).?;
        defer encoders.doeNativeCommandBufferRelease(commands);
        try std.testing.expect(native_helpers.cast(native_types.DoeCommandBuffer, commands).?.error_object);
    }
    var descriptor = std.mem.zeroes(@import("../../full/render/wgpu_render_types.zig").RenderBundleEncoderDescriptor);
    descriptor.sampleCount = 1;
    const encoder = bundle_native.doeNativeDeviceCreateRenderBundleEncoder(&device, &descriptor).?;
    defer bundle_native.doeNativeRenderBundleEncoderRelease(encoder);
    doeNativeRenderBundleEncoderSetImmediates(encoder, 0, null, 0);
    try std.testing.expect(render_bundle.cast_bundle_encoder(encoder).?.state == .open);
    doeNativeRenderBundleEncoderSetImmediates(encoder, 0, &bytes, bytes.len);
    try std.testing.expectEqual(error.ImmediateDataUnsupported, render_bundle.cast_bundle_encoder(encoder).?.state.failed);
    const bundle = bundle_native.doeNativeRenderBundleEncoderFinish(encoder, null).?;
    defer bundle_native.doeNativeRenderBundleRelease(bundle);
    try std.testing.expect(render_bundle.cast_bundle(bundle).?.error_object);
}

test "immediate layouts reject unsupported state before retaining bindings" {
    const bindings = @import("../resource/doe_bind_group_native.zig");
    const abi = @import("../../core/abi/wgpu_pipeline_descriptor_types.zig");
    var device = native_types.DoeDevice{};
    var group = native_types.DoeBindGroupLayout{};
    try std.testing.expect(bindings.doeNativeDeviceCreatePipelineLayoutOne(&device, &group, 4) == null);
    var descriptor = std.mem.zeroes(abi.WGPUPipelineLayoutDescriptor);
    descriptor.immediateSize = 4;
    try std.testing.expect(bindings.doeNativeDeviceCreatePipelineLayout(&device, &descriptor) == null);
    try std.testing.expectEqual(@as(u32, 1), group.ref_count);
    const layout = bindings.doeNativeDeviceCreatePipelineLayoutOne(&device, &group, 0).?;
    bindings.doeNativePipelineLayoutRelease(layout);
    try std.testing.expectEqual(@as(u32, 1), group.ref_count);
    try std.testing.expectError(error.InvalidArgument, validate_payload(0, null, 4));
}
