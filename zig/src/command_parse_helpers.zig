const std = @import("std");
const model = @import("model.zig");

pub const ParseError = error{
    InvalidCommandPayload,
    OutOfMemory,
};

fn eqIgnoreCase(lhs: []const u8, rhs: []const u8) bool {
    return std.ascii.eqlIgnoreCase(lhs, rhs);
}

pub fn parseCopyResourceKind(raw_kind: ?[]const u8) ?model.CopyResourceKind {
    const raw_value = raw_kind orelse return null;
    if (eqIgnoreCase(raw_value, "buffer")) return .buffer;
    if (eqIgnoreCase(raw_value, "texture")) return .texture;
    return null;
}

pub fn parseCopyDirection(raw_direction: ?[]const u8, command_name: ?[]const u8) ParseError!model.CopyDirection {
    if (raw_direction) |raw_value| {
        if (eqIgnoreCase(raw_value, "buffer_to_buffer")) return .buffer_to_buffer;
        if (eqIgnoreCase(raw_value, "buffer_to_texture")) return .buffer_to_texture;
        if (eqIgnoreCase(raw_value, "texture_to_buffer")) return .texture_to_buffer;
        if (eqIgnoreCase(raw_value, "texture_to_texture")) return .texture_to_texture;
        return ParseError.InvalidCommandPayload;
    }

    const kind = command_name orelse return .buffer_to_buffer;
    if (eqIgnoreCase(kind, "copy_buffer_to_texture") or eqIgnoreCase(kind, "copy_texture") or eqIgnoreCase(kind, "copyBufferToTexture") or eqIgnoreCase(kind, "copyTexture")) {
        return .buffer_to_texture;
    }
    if (eqIgnoreCase(kind, "copy_texture_to_buffer") or eqIgnoreCase(kind, "copyTextureToBuffer")) {
        return .texture_to_buffer;
    }
    if (eqIgnoreCase(kind, "copy_texture_to_texture") or eqIgnoreCase(kind, "copyTextureToTexture")) {
        return .texture_to_texture;
    }
    return .buffer_to_buffer;
}

pub fn parseKernelBindingKind(raw_kind: ?[]const u8) ?model.KernelBindingResourceKind {
    const value = raw_kind orelse return .buffer;
    if (eqIgnoreCase(value, "buffer") or eqIgnoreCase(value, "uniform") or eqIgnoreCase(value, "storage_buffer") or eqIgnoreCase(value, "readonly_storage_buffer")) {
        return .buffer;
    }
    if (eqIgnoreCase(value, "texture") or eqIgnoreCase(value, "sampled_texture") or eqIgnoreCase(value, "texture_sampled")) {
        return .texture;
    }
    if (eqIgnoreCase(value, "storage_texture") or eqIgnoreCase(value, "storage_texture_binding") or eqIgnoreCase(value, "storage")) {
        return .storage_texture;
    }
    return null;
}

pub fn parseShaderStage(raw_stage: ?[]const u8) ?model.WGPUFlags {
    const value = raw_stage orelse return null;
    if (eqIgnoreCase(value, "compute") or eqIgnoreCase(value, "compute-only") or eqIgnoreCase(value, "computeOnly")) {
        return model.WGPUShaderStage_Compute;
    }
    if (eqIgnoreCase(value, "vertex")) return model.WGPUShaderStage_Vertex;
    if (eqIgnoreCase(value, "fragment")) return model.WGPUShaderStage_Fragment;
    if (eqIgnoreCase(value, "all") or eqIgnoreCase(value, "*")) return model.WGPUShaderStage_Vertex | model.WGPUShaderStage_Fragment | model.WGPUShaderStage_Compute;
    return null;
}

pub fn parseWGPUBits(raw_bits: ?u64) ?model.WGPUFlags {
    return raw_bits;
}

pub fn parseBufferBindingType(raw: ?[]const u8) u32 {
    const value = raw orelse return model.WGPUBufferBindingType_Undefined;
    if (eqIgnoreCase(value, "uniform")) return model.WGPUBufferBindingType_Uniform;
    if (eqIgnoreCase(value, "storage")) return model.WGPUBufferBindingType_Storage;
    if (eqIgnoreCase(value, "readonly") or eqIgnoreCase(value, "read_only_storage")) return model.WGPUBufferBindingType_ReadOnlyStorage;
    return model.WGPUBufferBindingType_Undefined;
}

pub fn parseTextureSampleType(raw: ?[]const u8) u32 {
    const value = raw orelse return model.WGPUTextureSampleType_Undefined;
    if (eqIgnoreCase(value, "float")) return model.WGPUTextureSampleType_Float;
    if (eqIgnoreCase(value, "unfilterable-float") or eqIgnoreCase(value, "unfilterable_float")) return model.WGPUTextureSampleType_UnfilterableFloat;
    if (eqIgnoreCase(value, "depth")) return model.WGPUTextureSampleType_Depth;
    if (eqIgnoreCase(value, "sint")) return model.WGPUTextureSampleType_Sint;
    if (eqIgnoreCase(value, "uint")) return model.WGPUTextureSampleType_Uint;
    return model.WGPUTextureSampleType_Undefined;
}

pub fn parseTextureViewDimension(raw: ?[]const u8) u32 {
    const value = raw orelse return model.WGPUTextureViewDimension_Undefined;
    if (eqIgnoreCase(value, "1d") or eqIgnoreCase(value, "1D") or eqIgnoreCase(value, "1d-array")) return model.WGPUTextureViewDimension_1D;
    if (eqIgnoreCase(value, "2d") or eqIgnoreCase(value, "2D")) return model.WGPUTextureViewDimension_2D;
    if (eqIgnoreCase(value, "2d-array")) return model.WGPUTextureViewDimension_2DArray;
    if (eqIgnoreCase(value, "cube")) return model.WGPUTextureViewDimension_Cube;
    if (eqIgnoreCase(value, "cube-array")) return model.WGPUTextureViewDimension_CubeArray;
    if (eqIgnoreCase(value, "3d") or eqIgnoreCase(value, "3D")) return model.WGPUTextureViewDimension_3D;
    return model.WGPUTextureViewDimension_Undefined;
}

pub fn parseTextureDimension(raw: ?[]const u8) u32 {
    const value = raw orelse return model.WGPUTextureDimension_Undefined;
    if (eqIgnoreCase(value, "1d")) return model.WGPUTextureDimension_1D;
    if (eqIgnoreCase(value, "2d")) return model.WGPUTextureDimension_2D;
    if (eqIgnoreCase(value, "3d")) return model.WGPUTextureDimension_3D;
    return model.WGPUTextureDimension_Undefined;
}

pub fn parseStorageTextureAccess(raw: ?[]const u8) u32 {
    const value = raw orelse return model.WGPUStorageTextureAccess_Undefined;
    if (eqIgnoreCase(value, "write_only") or eqIgnoreCase(value, "write-only")) return model.WGPUStorageTextureAccess_WriteOnly;
    if (eqIgnoreCase(value, "read_only") or eqIgnoreCase(value, "read-only")) return model.WGPUStorageTextureAccess_ReadOnly;
    if (eqIgnoreCase(value, "read_write") or eqIgnoreCase(value, "read-write")) return model.WGPUStorageTextureAccess_ReadWrite;
    return model.WGPUStorageTextureAccess_Undefined;
}

pub fn parseTextureAspect(raw: ?[]const u8) u32 {
    const value = raw orelse return model.WGPUTextureAspect_Undefined;
    if (eqIgnoreCase(value, "all")) return model.WGPUTextureAspect_All;
    if (eqIgnoreCase(value, "depth-only") or eqIgnoreCase(value, "depth_only") or eqIgnoreCase(value, "depth")) return model.WGPUTextureAspect_DepthOnly;
    if (eqIgnoreCase(value, "stencil-only") or eqIgnoreCase(value, "stencil_only") or eqIgnoreCase(value, "stencil")) return model.WGPUTextureAspect_StencilOnly;
    return model.WGPUTextureAspect_Undefined;
}

pub fn parseTextureFormat(raw: []const u8) ParseError!u32 {
    if (raw.len == 0) return model.WGPUTextureFormat_Undefined;
    if (eqIgnoreCase(raw, "r8unorm")) return model.WGPUTextureFormat_R8Unorm;
    if (eqIgnoreCase(raw, "r8snorm")) return model.WGPUTextureFormat_R8Snorm;
    if (eqIgnoreCase(raw, "r8uint")) return model.WGPUTextureFormat_R8Uint;
    if (eqIgnoreCase(raw, "r8sint")) return model.WGPUTextureFormat_R8Sint;
    if (eqIgnoreCase(raw, "r16unorm")) return model.WGPUTextureFormat_R16Unorm;
    if (eqIgnoreCase(raw, "r16snorm")) return model.WGPUTextureFormat_R16Snorm;
    if (eqIgnoreCase(raw, "r16uint")) return model.WGPUTextureFormat_R16Uint;
    if (eqIgnoreCase(raw, "r16sint")) return model.WGPUTextureFormat_R16Sint;
    if (eqIgnoreCase(raw, "r16float")) return model.WGPUTextureFormat_R16Float;
    if (eqIgnoreCase(raw, "rg8unorm")) return model.WGPUTextureFormat_RG8Unorm;
    if (eqIgnoreCase(raw, "rg8snorm")) return model.WGPUTextureFormat_RG8Snorm;
    if (eqIgnoreCase(raw, "rg8uint")) return model.WGPUTextureFormat_RG8Uint;
    if (eqIgnoreCase(raw, "rg8sint")) return model.WGPUTextureFormat_RG8Sint;
    if (eqIgnoreCase(raw, "r32float")) return model.WGPUTextureFormat_R32Float;
    if (eqIgnoreCase(raw, "r32uint")) return model.WGPUTextureFormat_R32Uint;
    if (eqIgnoreCase(raw, "r32sint")) return model.WGPUTextureFormat_R32Sint;
    if (eqIgnoreCase(raw, "rg16unorm")) return model.WGPUTextureFormat_RG16Unorm;
    if (eqIgnoreCase(raw, "rg16snorm")) return model.WGPUTextureFormat_RG16Snorm;
    if (eqIgnoreCase(raw, "rg16uint")) return model.WGPUTextureFormat_RG16Uint;
    if (eqIgnoreCase(raw, "rg16sint")) return model.WGPUTextureFormat_RG16Sint;
    if (eqIgnoreCase(raw, "rg16float")) return model.WGPUTextureFormat_RG16Float;
    if (eqIgnoreCase(raw, "rgba8unorm")) return model.WGPUTextureFormat_RGBA8Unorm;
    if (eqIgnoreCase(raw, "rgba8unorm-srgb") or eqIgnoreCase(raw, "rgba8unormsrgb")) return model.WGPUTextureFormat_RGBA8UnormSrgb;
    if (eqIgnoreCase(raw, "rgba8snorm")) return model.WGPUTextureFormat_RGBA8Snorm;
    if (eqIgnoreCase(raw, "rgba8uint")) return model.WGPUTextureFormat_RGBA8Uint;
    if (eqIgnoreCase(raw, "rgba8sint")) return model.WGPUTextureFormat_RGBA8Sint;
    if (eqIgnoreCase(raw, "bgra8unorm")) return model.WGPUTextureFormat_BGRA8Unorm;
    if (eqIgnoreCase(raw, "bgra8unorm-srgb") or eqIgnoreCase(raw, "bgra8unormsrgb")) return model.WGPUTextureFormat_BGRA8UnormSrgb;
    if (eqIgnoreCase(raw, "depth16unorm")) return model.WGPUTextureFormat_Depth16Unorm;
    if (eqIgnoreCase(raw, "depth24plus")) return model.WGPUTextureFormat_Depth24Plus;
    if (eqIgnoreCase(raw, "depth24plus-stencil8")) return model.WGPUTextureFormat_Depth24PlusStencil8;
    if (eqIgnoreCase(raw, "depth32float")) return model.WGPUTextureFormat_Depth32Float;
    if (eqIgnoreCase(raw, "depth32float-stencil8")) return model.WGPUTextureFormat_Depth32FloatStencil8;
    if (eqIgnoreCase(raw, "undefined")) return model.WGPUTextureFormat_Undefined;
    return std.fmt.parseInt(u32, raw, 10) catch ParseError.InvalidCommandPayload;
}

pub fn parseRenderDrawPipelineMode(raw: ?[]const u8) ParseError!model.RenderDrawPipelineMode {
    const value = raw orelse return .static;
    if (eqIgnoreCase(value, "static")) return .static;
    if (eqIgnoreCase(value, "redundant")) return .redundant;
    return ParseError.InvalidCommandPayload;
}

pub fn parseRenderDrawBindGroupMode(raw: ?[]const u8) ParseError!model.RenderDrawBindGroupMode {
    const value = raw orelse return .no_change;
    if (eqIgnoreCase(value, "no-change") or eqIgnoreCase(value, "no_change")) return .no_change;
    if (eqIgnoreCase(value, "redundant")) return .redundant;
    return ParseError.InvalidCommandPayload;
}

pub fn parseRenderIndexFormat(raw: ?[]const u8) ParseError!?model.RenderIndexFormat {
    const value = raw orelse return null;
    if (eqIgnoreCase(value, "uint16") or eqIgnoreCase(value, "u16")) return .uint16;
    if (eqIgnoreCase(value, "uint32") or eqIgnoreCase(value, "u32")) return .uint32;
    return ParseError.InvalidCommandPayload;
}

fn inferRenderIndexFormat(indices: []const u32) model.RenderIndexFormat {
    for (indices) |value| {
        if (value > std.math.maxInt(u16)) return .uint32;
    }
    return .uint16;
}

pub fn parseRenderIndexData(
    allocator: std.mem.Allocator,
    raw_indices: []const u32,
    requested_format: ?model.RenderIndexFormat,
) ParseError!model.RenderIndexData {
    const chosen_format = requested_format orelse inferRenderIndexFormat(raw_indices);
    return switch (chosen_format) {
        .uint16 => blk: {
            var values = try allocator.alloc(u16, raw_indices.len);
            errdefer allocator.free(values);
            for (raw_indices, 0..) |value, idx| {
                if (value > std.math.maxInt(u16)) return ParseError.InvalidCommandPayload;
                values[idx] = @as(u16, @intCast(value));
            }
            break :blk .{ .uint16 = values };
        },
        .uint32 => blk: {
            const values = try allocator.alloc(u32, raw_indices.len);
            errdefer allocator.free(values);
            @memcpy(values, raw_indices);
            break :blk .{ .uint32 = values };
        },
    };
}
