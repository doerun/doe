const std = @import("std");
const model = @import("model.zig");
const parse_helpers = @import("command_parse_helpers.zig");

pub const ParseError = error{
    InvalidCommandPayload,
    OutOfMemory,
};

fn commandKindEqualsFn(raw_kind: []const u8, kind: []const u8) bool {
    return std.ascii.eqlIgnoreCase(raw_kind, kind);
}

fn parseCommandHandle(raw: anytype) ?u64 {
    return raw.handle orelse raw.resource_handle orelse raw.resourceHandle;
}

fn parseTextureHandle(raw: anytype) ?u64 {
    return raw.texture_handle orelse raw.textureHandle orelse parseCommandHandle(raw) orelse raw.target_handle orelse raw.targetHandle;
}

fn parseSamplerHandle(raw: anytype) ?u64 {
    return raw.sampler_handle orelse raw.samplerHandle orelse parseCommandHandle(raw);
}

fn parseSurfaceHandle(raw: anytype) ?u64 {
    return raw.surface_handle orelse raw.surfaceHandle orelse parseCommandHandle(raw);
}

fn parseSamplerAddressMode(raw: ?[]const u8) ParseError!u32 {
    const value = raw orelse return 0x00000001;
    if (commandKindEqualsFn(value, "clamp-to-edge") or commandKindEqualsFn(value, "clamp_to_edge")) return 0x00000001;
    if (commandKindEqualsFn(value, "repeat")) return 0x00000002;
    if (commandKindEqualsFn(value, "mirror-repeat") or commandKindEqualsFn(value, "mirror_repeat")) return 0x00000003;
    return ParseError.InvalidCommandPayload;
}

fn parseFilterMode(raw: ?[]const u8) ParseError!u32 {
    const value = raw orelse return 0x00000001;
    if (commandKindEqualsFn(value, "nearest")) return 0x00000001;
    if (commandKindEqualsFn(value, "linear")) return 0x00000002;
    return ParseError.InvalidCommandPayload;
}

fn parseCompareFunction(raw: ?[]const u8) ParseError!u32 {
    const value = raw orelse return 0;
    if (commandKindEqualsFn(value, "undefined")) return 0;
    if (commandKindEqualsFn(value, "never")) return 0x00000001;
    if (commandKindEqualsFn(value, "less")) return 0x00000002;
    if (commandKindEqualsFn(value, "equal")) return 0x00000003;
    if (commandKindEqualsFn(value, "less-equal") or commandKindEqualsFn(value, "less_equal")) return 0x00000004;
    if (commandKindEqualsFn(value, "greater")) return 0x00000005;
    if (commandKindEqualsFn(value, "not-equal") or commandKindEqualsFn(value, "not_equal")) return 0x00000006;
    if (commandKindEqualsFn(value, "greater-equal") or commandKindEqualsFn(value, "greater_equal")) return 0x00000007;
    if (commandKindEqualsFn(value, "always")) return 0x00000008;
    return ParseError.InvalidCommandPayload;
}

fn parseSurfaceAlphaMode(raw: ?[]const u8) ParseError!u32 {
    const value = raw orelse return 0x00000001;
    if (commandKindEqualsFn(value, "auto")) return 0x00000001;
    if (commandKindEqualsFn(value, "opaque")) return 0x00000002;
    if (commandKindEqualsFn(value, "premultiplied")) return 0x00000003;
    if (commandKindEqualsFn(value, "unpremultiplied")) return 0x00000004;
    if (commandKindEqualsFn(value, "inherit")) return 0x00000005;
    return ParseError.InvalidCommandPayload;
}

fn parseSurfacePresentMode(raw: ?[]const u8) ParseError!u32 {
    const value = raw orelse return 0x00000002;
    if (commandKindEqualsFn(value, "fifo")) return 0x00000002;
    if (commandKindEqualsFn(value, "immediate")) return 0x00000001;
    if (commandKindEqualsFn(value, "mailbox")) return 0x00000003;
    if (commandKindEqualsFn(value, "fifo-relaxed") or commandKindEqualsFn(value, "fifo_relaxed")) return 0x00000004;
    return ParseError.InvalidCommandPayload;
}

fn parseBytesU32ToU8(allocator: std.mem.Allocator, values: []const u32) ParseError![]const u8 {
    const bytes = try allocator.alloc(u8, values.len);
    errdefer allocator.free(bytes);
    for (values, 0..) |value, idx| {
        if (value > std.math.maxInt(u8)) return ParseError.InvalidCommandPayload;
        bytes[idx] = @as(u8, @intCast(value));
    }
    return bytes;
}

pub fn parseRenderDrawEncodeMode(raw: ?[]const u8) ParseError!model.RenderDrawEncodeMode {
    const value = raw orelse return .render_bundle;
    if (commandKindEqualsFn(value, "render-bundle") or commandKindEqualsFn(value, "render_bundle") or commandKindEqualsFn(value, "bundle")) return .render_bundle;
    if (commandKindEqualsFn(value, "render-pass") or commandKindEqualsFn(value, "render_pass") or commandKindEqualsFn(value, "pass")) return .render_pass;
    return ParseError.InvalidCommandPayload;
}

pub fn parseSamplerCreateCommand(raw: anytype) ParseError!model.SamplerCreateCommand {
    const handle = parseSamplerHandle(raw) orelse return ParseError.InvalidCommandPayload;
    const address_mode_u = try parseSamplerAddressMode(raw.address_mode_u orelse raw.addressModeU);
    const address_mode_v = try parseSamplerAddressMode(raw.address_mode_v orelse raw.addressModeV);
    const address_mode_w = try parseSamplerAddressMode(raw.address_mode_w orelse raw.addressModeW);
    const mag_filter = try parseFilterMode(raw.mag_filter orelse raw.magFilter);
    const min_filter = try parseFilterMode(raw.min_filter orelse raw.minFilter);
    const mipmap_filter = try parseFilterMode(raw.mipmap_filter orelse raw.mipmapFilter);
    const compare = try parseCompareFunction(raw.compare);
    const max_anisotropy = raw.max_anisotropy orelse raw.maxAnisotropy orelse 1;
    if (max_anisotropy == 0) return ParseError.InvalidCommandPayload;

    return .{
        .handle = handle,
        .address_mode_u = address_mode_u,
        .address_mode_v = address_mode_v,
        .address_mode_w = address_mode_w,
        .mag_filter = mag_filter,
        .min_filter = min_filter,
        .mipmap_filter = mipmap_filter,
        .lod_min_clamp = raw.lod_min_clamp orelse raw.lodMinClamp orelse 0,
        .lod_max_clamp = raw.lod_max_clamp orelse raw.lodMaxClamp orelse 32,
        .compare = compare,
        .max_anisotropy = max_anisotropy,
    };
}

pub fn parseSamplerDestroyCommand(raw: anytype) ParseError!model.SamplerDestroyCommand {
    const handle = parseSamplerHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseTextureWriteCommand(allocator: std.mem.Allocator, raw: anytype) ParseError!model.TextureWriteCommand {
    const handle = parseTextureHandle(raw) orelse return ParseError.InvalidCommandPayload;
    const width = raw.width orelse raw.target_width orelse raw.targetWidth orelse 1;
    const height = raw.height orelse raw.target_height orelse raw.targetHeight orelse 1;
    const depth = raw.depth_or_array_layers orelse raw.depthOrArrayLayers orelse raw.depth orelse 1;
    const mip_level = raw.mip_level orelse raw.mipLevel orelse 0;
    const sample_count = raw.sample_count orelse raw.sampleCount orelse 1;
    const format = if (raw.format orelse raw.target_format orelse raw.targetFormat) |raw_format|
        parse_helpers.parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload
    else
        model.WGPUTextureFormat_RGBA8Unorm;
    const usage = raw.usage orelse (model.WGPUTextureUsage_CopyDst | model.WGPUTextureUsage_TextureBinding);
    const dimension = parse_helpers.parseTextureDimension(raw.dimension);
    const view_dimension = parse_helpers.parseTextureViewDimension(raw.view_dimension orelse raw.viewDimension);
    const aspect = parse_helpers.parseTextureAspect(raw.aspect);
    const bytes_per_row = raw.bytesPerRow orelse 0;
    const rows_per_image = raw.rows_per_image orelse raw.rowsPerImage orelse 0;
    const offset = raw.offset orelse 0;
    const data_values = raw.data orelse return ParseError.InvalidCommandPayload;
    if (data_values.len == 0) return ParseError.InvalidCommandPayload;
    const data = try parseBytesU32ToU8(allocator, data_values);

    return .{
        .texture = .{
            .handle = handle,
            .kind = .texture,
            .width = width,
            .height = height,
            .depth_or_array_layers = depth,
            .format = format,
            .usage = usage,
            .dimension = dimension,
            .view_dimension = view_dimension,
            .mip_level = mip_level,
            .sample_count = sample_count,
            .aspect = aspect,
            .bytes_per_row = bytes_per_row,
            .rows_per_image = rows_per_image,
            .offset = offset,
        },
        .data = data,
    };
}

pub fn parseTextureQueryCommand(raw: anytype) ParseError!model.TextureQueryCommand {
    const handle = parseTextureHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseTextureDestroyCommand(raw: anytype) ParseError!model.TextureDestroyCommand {
    const handle = parseTextureHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseSurfaceCreateCommand(raw: anytype) ParseError!model.SurfaceCreateCommand {
    const handle = parseSurfaceHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseSurfaceCapabilitiesCommand(raw: anytype) ParseError!model.SurfaceCapabilitiesCommand {
    const handle = parseSurfaceHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseSurfaceConfigureCommand(raw: anytype) ParseError!model.SurfaceConfigureCommand {
    const handle = parseSurfaceHandle(raw) orelse return ParseError.InvalidCommandPayload;
    const width = raw.width orelse raw.target_width orelse raw.targetWidth orelse return ParseError.InvalidCommandPayload;
    const height = raw.height orelse raw.target_height orelse raw.targetHeight orelse return ParseError.InvalidCommandPayload;
    const format = if (raw.format orelse raw.target_format orelse raw.targetFormat) |raw_format|
        parse_helpers.parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload
    else
        model.WGPUTextureFormat_RGBA8Unorm;
    const usage = raw.usage orelse model.WGPUTextureUsage_RenderAttachment;
    const alpha_mode = try parseSurfaceAlphaMode(raw.alpha_mode orelse raw.alphaMode);
    const present_mode = try parseSurfacePresentMode(raw.present_mode orelse raw.presentMode);
    const desired_maximum_frame_latency = raw.desired_maximum_frame_latency orelse raw.desiredMaximumFrameLatency orelse 2;
    if (width == 0 or height == 0) return ParseError.InvalidCommandPayload;

    return .{
        .handle = handle,
        .width = width,
        .height = height,
        .format = format,
        .usage = usage,
        .alpha_mode = alpha_mode,
        .present_mode = present_mode,
        .desired_maximum_frame_latency = desired_maximum_frame_latency,
    };
}

pub fn parseSurfaceAcquireCommand(raw: anytype) ParseError!model.SurfaceAcquireCommand {
    const handle = parseSurfaceHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseSurfacePresentCommand(raw: anytype) ParseError!model.SurfacePresentCommand {
    const handle = parseSurfaceHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseSurfaceUnconfigureCommand(raw: anytype) ParseError!model.SurfaceUnconfigureCommand {
    const handle = parseSurfaceHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseSurfaceReleaseCommand(raw: anytype) ParseError!model.SurfaceReleaseCommand {
    const handle = parseSurfaceHandle(raw) orelse return ParseError.InvalidCommandPayload;
    return .{ .handle = handle };
}

pub fn parseAsyncDiagnosticsCommand(raw: anytype) ParseError!model.AsyncDiagnosticsCommand {
    const target_format = if (raw.format orelse raw.target_format orelse raw.targetFormat) |raw_format|
        parse_helpers.parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload
    else
        model.WGPUTextureFormat_RGBA8Unorm;
    return .{ .target_format = target_format };
}
