const std = @import("std");
const contract = @import("../../contracts/command_recording.zig");
const abi = @import("../../core/abi/wgpu_pipeline_descriptor_types.zig");
const texture_abi = @import("../../core/abi/wgpu_texture_base_types.zig");
const objects = @import("../support/doe_native_object_types.zig");
const helpers = @import("../support/doe_native_object_helpers.zig");

const Error = contract.RenderAttachmentError;
const Extent = struct { width: u32, height: u32 };

fn validateView(device: *objects.DoeDevice, raw: ?*anyopaque, depth: bool) Error!*objects.DoeTextureView {
    const view = helpers.cast(objects.DoeTextureView, raw) orelse return error.RenderAttachmentUnavailable;
    const texture = view.tex;
    if (texture.isUnavailable()) return error.RenderAttachmentUnavailable;
    if (texture.device_ref != device) return error.RenderAttachmentDeviceMismatch;
    if ((view.usage & texture_abi.WGPUTextureUsage_RenderAttachment) == 0) return error.RenderAttachmentUsageMissing;
    if (view.dimension != texture_abi.WGPUTextureViewDimension_2D) return error.RenderAttachmentUnsupported;
    if (view.mip_level_count != 1 or view.array_layer_count != 1 or
        view.aspect != texture_abi.WGPUTextureAspect_All or
        view.base_mip_level >= texture.mip_level_count or view.base_mip_level >= @bitSizeOf(u32))
        return error.RenderAttachmentViewInvalid;
    if (texture_abi.isDepthStencilFormat(view.format) != depth) return error.RenderAttachmentFormatMismatch;
    return view;
}

fn extent(view: *const objects.DoeTextureView) Extent {
    return .{
        .width = @max(1, view.tex.width >> @intCast(view.base_mip_level)),
        .height = @max(1, view.tex.height >> @intCast(view.base_mip_level)),
    };
}

fn validatePair(color: *const objects.DoeTextureView, depth: *const objects.DoeTextureView) Error!void {
    if (!std.meta.eql(extent(color), extent(depth))) return error.RenderAttachmentExtentMismatch;
    if (color.tex.sample_count != depth.tex.sample_count) return error.RenderAttachmentSampleMismatch;
}

/// Admit native attachment semantics before retaining views or recording work.
/// Unsupported attachment topologies cannot silently become a different pass.
pub fn validateDescriptor(device: *objects.DoeDevice, descriptor: ?*const abi.WGPURenderPassDescriptor) Error!void {
    const desc = descriptor orelse return error.RenderAttachmentUnavailable;
    if (desc.colorAttachmentCount != 1) return error.RenderAttachmentUnsupported;
    const colors = desc.colorAttachments orelse return error.RenderAttachmentUnavailable;
    const color = try validateView(device, colors[0].view, false);
    if (colors[0].resolveTarget != null) return error.RenderAttachmentUnsupported;
    if (desc.depthStencilAttachment) |raw| {
        const attachment: *const abi.WGPURenderPassDepthStencilAttachment = @ptrCast(@alignCast(raw));
        const depth = try validateView(device, attachment.view, true);
        try validatePair(color, depth);
    }
}

/// Pass views have encoder-owned leases. Recheck availability at each draw;
/// queue-wide lease validation separately rejects destruction after recording.
pub fn validateDraw(pass: *const objects.DoeRenderPass, clear_only: bool) Error!void {
    if (pass.target_view_handle == 0) return error.RenderAttachmentUnavailable;
    const color = try validateView(pass.enc.dev, @ptrFromInt(pass.target_view_handle), false);
    const depth = if (pass.depth_target_view_handle != 0)
        try validateView(pass.enc.dev, @ptrFromInt(pass.depth_target_view_handle), true)
    else
        null;
    if (depth) |view| try validatePair(color, view);
    if (clear_only) return;
    const pipeline = pass.pipeline orelse return error.RenderAttachmentUnavailable;
    if (pipeline.device_ref != pass.enc.dev) return error.RenderAttachmentDeviceMismatch;
    if (pipeline.color_target_count != 1) return error.RenderAttachmentUnsupported;
    if (pipeline.color_target_format != color.format or
        pipeline.depth_stencil_format != (if (depth) |view| view.format else @as(u32, 0)))
        return error.RenderAttachmentFormatMismatch;
    if (pipeline.sample_count != color.tex.sample_count) return error.RenderAttachmentSampleMismatch;
}

test "attachment admission compares selected mip extent and preserves format and sample identities" {
    var device = objects.DoeDevice{};
    var color_texture = objects.DoeTexture{ .device_ref = &device, .width = 16, .height = 16, .mip_level_count = 2 };
    var depth_texture = objects.DoeTexture{ .device_ref = &device, .width = 8, .height = 8 };
    var color = objects.DoeTextureView{
        .tex = &color_texture,
        .format = texture_abi.WGPUTextureFormat_RGBA8Unorm,
        .dimension = texture_abi.WGPUTextureViewDimension_2D,
        .base_mip_level = 1,
        .mip_level_count = 1,
        .array_layer_count = 1,
        .aspect = texture_abi.WGPUTextureAspect_All,
        .usage = texture_abi.WGPUTextureUsage_RenderAttachment,
    };
    var depth = color;
    depth.tex = &depth_texture;
    depth.base_mip_level = 0;
    depth.format = texture_abi.WGPUTextureFormat_Depth32Float;
    try validatePair(&color, &depth);
    depth_texture.width = 16;
    try std.testing.expectError(error.RenderAttachmentExtentMismatch, validatePair(&color, &depth));
    depth_texture.width = 8;
    depth_texture.sample_count = 4;
    try std.testing.expectError(error.RenderAttachmentSampleMismatch, validatePair(&color, &depth));
    depth_texture.sample_count = 1;
    var encoder = objects.DoeCommandEncoder{ .dev = &device };
    var pipeline = objects.DoeRenderPipeline{
        .device_ref = &device,
        .color_target_count = 1,
        .color_target_format = color.format,
        .depth_stencil_format = depth.format,
    };
    var pass = objects.DoeRenderPass{
        .enc = &encoder,
        .pipeline = &pipeline,
        .target_view_handle = @intFromPtr(&color),
        .depth_target_view_handle = @intFromPtr(&depth),
    };
    try validateDraw(&pass, false);
    pipeline.sample_count = 4;
    try std.testing.expectError(error.RenderAttachmentSampleMismatch, validateDraw(&pass, false));
    pipeline.sample_count = 1;
    pipeline.color_target_format = texture_abi.WGPUTextureFormat_BGRA8Unorm;
    try std.testing.expectError(error.RenderAttachmentFormatMismatch, validateDraw(&pass, false));
    pipeline.color_target_format = color.format;
    pipeline.depth_stencil_format = 0;
    try std.testing.expectError(error.RenderAttachmentFormatMismatch, validateDraw(&pass, false));
    try validateDraw(&pass, true);
    color_texture.destroyed = true;
    try std.testing.expectError(error.RenderAttachmentUnavailable, validateDraw(&pass, true));
}

test "attachment admission rejects unavailable foreign nonrenderable and broad views" {
    var device = objects.DoeDevice{};
    var other = objects.DoeDevice{};
    var texture = objects.DoeTexture{ .device_ref = &device, .width = 8, .height = 8 };
    var view = objects.DoeTextureView{
        .tex = &texture,
        .format = texture_abi.WGPUTextureFormat_RGBA8Unorm,
        .dimension = texture_abi.WGPUTextureViewDimension_2D,
        .mip_level_count = 1,
        .array_layer_count = 1,
        .aspect = texture_abi.WGPUTextureAspect_All,
        .usage = texture_abi.WGPUTextureUsage_RenderAttachment,
    };
    try std.testing.expectEqual(&view, try validateView(&device, &view, false));
    try std.testing.expectError(error.RenderAttachmentUnavailable, validateView(&device, null, false));
    try std.testing.expectError(error.RenderAttachmentDeviceMismatch, validateView(&other, &view, false));
    view.usage = texture_abi.WGPUTextureUsage_TextureBinding;
    try std.testing.expectError(error.RenderAttachmentUsageMissing, validateView(&device, &view, false));
    view.usage = texture_abi.WGPUTextureUsage_RenderAttachment;
    view.mip_level_count = 2;
    try std.testing.expectError(error.RenderAttachmentViewInvalid, validateView(&device, &view, false));
    view.mip_level_count = 1;
    view.array_layer_count = 2;
    try std.testing.expectError(error.RenderAttachmentViewInvalid, validateView(&device, &view, false));
    view.array_layer_count = 1;
    try std.testing.expectError(error.RenderAttachmentFormatMismatch, validateView(&device, &view, true));
    texture.error_object = true;
    try std.testing.expectError(error.RenderAttachmentUnavailable, validateView(&device, &view, false));
}
