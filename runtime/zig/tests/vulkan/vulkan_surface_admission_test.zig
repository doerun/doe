const std = @import("std");
const surface = @import("../../src/backend/vulkan/vulkan_surface.zig");
const gpu = @import("../../src/contracts/model/model_gpu_types.zig");

fn capabilities() surface.SurfaceCapabilities {
    var caps = surface.SurfaceCapabilities{
        .present_supported = true,
        .min_width = 1,
        .min_height = 1,
        .max_width = 1024,
        .max_height = 1024,
        .current_width = std.math.maxInt(u32),
        .current_height = std.math.maxInt(u32),
        .supported_usage = 0x17,
        .supported_alpha = 0xf,
        .format_count = 1,
        .present_mode_count = 4,
    };
    caps.formats[0] = .{ .format = 50, .colorSpace = 0 };
    @memcpy(caps.present_modes[0..4], &[_]u32{ 2, 1, 0, 3 });
    return caps;
}

test "surface admission never aliases an unavailable format or color space" {
    var caps = capabilities();
    const request = @import("../../src/contracts/model/model_surface_control_types.zig").SurfaceConfigureCommand{ .handle = 1, .width = 8, .height = 8, .format = gpu.WGPUTextureFormat_BGRA8UnormSrgb, .present_mode = 1 };
    const admitted = try surface.admitConfiguration(caps, request);
    try std.testing.expectEqual(@as(u32, 50), admitted.format.format);
    var bad = request;
    bad.format = gpu.WGPUTextureFormat_BGRA8Unorm;
    try std.testing.expectError(error.UnsupportedFeature, surface.admitConfiguration(caps, bad));
    caps.formats[0].colorSpace = 1000104002;
    try std.testing.expectError(error.UnsupportedFeature, surface.admitConfiguration(caps, request));
    caps.formats[0] = .{ .format = 0, .colorSpace = 0 };
    const any_format = try surface.admitConfiguration(caps, bad);
    try std.testing.expectEqual(@as(u32, 44), any_format.format.format);
    bad.format = gpu.WGPUTextureFormat_RGBA8UnormSrgb;
    try std.testing.expectEqual(@as(u32, 43), (try surface.admitConfiguration(caps, bad)).format.format);
}

test "surface admission maps pinned WebGPU modes exactly and rejects unsupported modes" {
    var caps = capabilities();
    var request = @import("../../src/contracts/model/model_surface_control_types.zig").SurfaceConfigureCommand{ .handle = 1, .width = 8, .height = 8, .format = gpu.WGPUTextureFormat_BGRA8UnormSrgb };
    for ([_]u32{ 2, 1, 0, 3 }, 1..) |expected, public| {
        request.present_mode = @intCast(public);
        try std.testing.expectEqual(expected, (try surface.admitConfiguration(caps, request)).present_mode);
    }
    for ([_]u32{ 1, 2, 4, 8 }, 1..) |expected, public| {
        request.alpha_mode = @intCast(public);
        try std.testing.expectEqual(expected, (try surface.admitConfiguration(caps, request)).alpha);
    }
    request.present_mode = 0;
    request.alpha_mode = 0;
    const defaults = try surface.admitConfiguration(caps, request);
    try std.testing.expectEqual(@as(u32, 2), defaults.present_mode);
    try std.testing.expectEqual(@as(u32, 8), defaults.alpha);
    caps.supported_alpha = 1;
    request.alpha_mode = 2;
    try std.testing.expectError(error.UnsupportedFeature, surface.admitConfiguration(caps, request));
    request.alpha_mode = 0;
    request.present_mode = 4;
    caps.present_mode_count = 1;
    try std.testing.expectError(error.UnsupportedFeature, surface.admitConfiguration(caps, request));
}

test "surface admission preserves dimensions usage and present support" {
    var caps = capabilities();
    var request = @import("../../src/contracts/model/model_surface_control_types.zig").SurfaceConfigureCommand{ .handle = 1, .width = 8, .height = 8, .format = gpu.WGPUTextureFormat_BGRA8UnormSrgb, .present_mode = 1 };
    request.usage |= gpu.WGPUTextureUsage_StorageBinding;
    try std.testing.expectError(error.UnsupportedFeature, surface.admitConfiguration(caps, request));
    request.usage = gpu.WGPUTextureUsage_RenderAttachment | gpu.WGPUTextureUsage_CopySrc;
    caps.supported_usage = 0x10;
    try std.testing.expectError(error.UnsupportedFeature, surface.admitConfiguration(caps, request));
    request.usage = gpu.WGPUTextureUsage_RenderAttachment;
    caps.current_width = 16;
    caps.current_height = 8;
    try std.testing.expectError(error.UnsupportedFeature, surface.admitConfiguration(caps, request));
    request.width = 16;
    try std.testing.expectEqual(@as(u32, 16), (try surface.admitConfiguration(caps, request)).extent.width);
    request.height = 0;
    try std.testing.expectError(error.InvalidArgument, surface.admitConfiguration(caps, request));
    caps.present_supported = false;
    try std.testing.expectError(error.SurfaceUnavailable, surface.canvasCapabilities(caps));
}
