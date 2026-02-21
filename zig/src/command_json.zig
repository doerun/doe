const std = @import("std");
const model = @import("model.zig");

const Allocator = std.mem.Allocator;

const RawKernelBinding = struct {
    binding: ?u32 = null,
    group: ?u32 = null,
    group_index: ?u32 = null,
    groupIndex: ?u32 = null,
    kind: ?[]const u8 = null,
    resource_kind: ?[]const u8 = null,
    resourceKind: ?[]const u8 = null,
    handle: ?u64 = null,
    resource_handle: ?u64 = null,
    resourceHandle: ?u64 = null,
    visibility: ?[]const u8 = null,
    visibilityMask: ?u64 = null,
    buffer_offset: ?u64 = null,
    bufferOffset: ?u64 = null,
    buffer_size: ?u64 = null,
    bufferSize: ?u64 = null,
    buffer_type: ?[]const u8 = null,
    bufferType: ?[]const u8 = null,
    texture_sample_type: ?[]const u8 = null,
    textureSampleType: ?[]const u8 = null,
    texture_view_dimension: ?[]const u8 = null,
    textureViewDimension: ?[]const u8 = null,
    storage_access: ?[]const u8 = null,
    storageAccess: ?[]const u8 = null,
    texture_aspect: ?[]const u8 = null,
    textureAspect: ?[]const u8 = null,
    texture_format: ?[]const u8 = null,
    textureFormat: ?[]const u8 = null,
    multisampled: ?bool = null,
};

const RawCommand = struct {
    kind: ?[]const u8 = null,
    command: ?[]const u8 = null,
    command_kind: ?[]const u8 = null,
    bytes: ?usize = null,
    kernel: ?[]const u8 = null,
    kernel_name: ?[]const u8 = null,
    entry_point: ?[]const u8 = null,
    entryPoint: ?[]const u8 = null,
    alignBytes: ?u32 = null,
    alignmentBytes: ?u32 = null,
    bytesPerRow: ?u32 = null,
    rowsPerImage: ?u32 = null,
    direction: ?[]const u8 = null,
    src_handle: ?u64 = null,
    srcHandle: ?u64 = null,
    dst_handle: ?u64 = null,
    dstHandle: ?u64 = null,
    src_kind: ?[]const u8 = null,
    srcKind: ?[]const u8 = null,
    dst_kind: ?[]const u8 = null,
    dstKind: ?[]const u8 = null,
    src_width: ?u32 = null,
    srcWidth: ?u32 = null,
    src_height: ?u32 = null,
    srcHeight: ?u32 = null,
    src_depth_or_array_layers: ?u32 = null,
    srcDepthOrArrayLayers: ?u32 = null,
    src_depth: ?u32 = null,
    dst_width: ?u32 = null,
    dstWidth: ?u32 = null,
    dst_height: ?u32 = null,
    dstHeight: ?u32 = null,
    dst_depth_or_array_layers: ?u32 = null,
    dstDepthOrArrayLayers: ?u32 = null,
    dst_depth: ?u32 = null,
    src_format: ?[]const u8 = null,
    srcFormat: ?[]const u8 = null,
    dst_format: ?[]const u8 = null,
    dstFormat: ?[]const u8 = null,
    src_usage: ?u64 = null,
    srcUsage: ?u64 = null,
    dst_usage: ?u64 = null,
    dstUsage: ?u64 = null,
    src_dimension: ?[]const u8 = null,
    srcDimension: ?[]const u8 = null,
    dst_dimension: ?[]const u8 = null,
    dstDimension: ?[]const u8 = null,
    src_view_dimension: ?[]const u8 = null,
    srcViewDimension: ?[]const u8 = null,
    dst_view_dimension: ?[]const u8 = null,
    dstViewDimension: ?[]const u8 = null,
    src_mip_level: ?u32 = null,
    srcMipLevel: ?u32 = null,
    dst_mip_level: ?u32 = null,
    dstMipLevel: ?u32 = null,
    src_sample_count: ?u32 = null,
    srcSampleCount: ?u32 = null,
    dst_sample_count: ?u32 = null,
    dstSampleCount: ?u32 = null,
    src_aspect: ?[]const u8 = null,
    srcAspect: ?[]const u8 = null,
    dst_aspect: ?[]const u8 = null,
    dstAspect: ?[]const u8 = null,
    src_bytes_per_row: ?u32 = null,
    srcBytesPerRow: ?u32 = null,
    dst_bytes_per_row: ?u32 = null,
    dstBytesPerRow: ?u32 = null,
    src_rows_per_image: ?u32 = null,
    srcRowsPerImage: ?u32 = null,
    dst_rows_per_image: ?u32 = null,
    dstRowsPerImage: ?u32 = null,
    src_offset: ?u64 = null,
    srcOffset: ?u64 = null,
    dst_offset: ?u64 = null,
    dstOffset: ?u64 = null,
    dependency_count: ?u32 = null,
    dependencyCount: ?u32 = null,
    x: ?u32 = null,
    y: ?u32 = null,
    z: ?u32 = null,
    repeat: ?u32 = null,
    dispatch_count: ?u32 = null,
    dispatchCount: ?u32 = null,
    draw_count: ?u32 = null,
    drawCount: ?u32 = null,
    vertex_count: ?u32 = null,
    vertexCount: ?u32 = null,
    instance_count: ?u32 = null,
    instanceCount: ?u32 = null,
    first_vertex: ?u32 = null,
    firstVertex: ?u32 = null,
    first_instance: ?u32 = null,
    firstInstance: ?u32 = null,
    index_count: ?u32 = null,
    indexCount: ?u32 = null,
    first_index: ?u32 = null,
    firstIndex: ?u32 = null,
    base_vertex: ?i32 = null,
    baseVertex: ?i32 = null,
    index_format: ?[]const u8 = null,
    indexFormat: ?[]const u8 = null,
    index_data: ?[]u32 = null,
    indexData: ?[]u32 = null,
    indices: ?[]u32 = null,
    target_handle: ?u64 = null,
    targetHandle: ?u64 = null,
    target_width: ?u32 = null,
    targetWidth: ?u32 = null,
    target_height: ?u32 = null,
    targetHeight: ?u32 = null,
    target_format: ?[]const u8 = null,
    targetFormat: ?[]const u8 = null,
    pipeline_mode: ?[]const u8 = null,
    pipelineMode: ?[]const u8 = null,
    bind_group_mode: ?[]const u8 = null,
    bindGroupMode: ?[]const u8 = null,
    workgroupCount: ?[3]u32 = null,
    workgroups: ?[3]u32 = null,
    bindings: ?[]RawKernelBinding = null,
};

pub const ParseError = error{
    MissingCommandKind,
    UnknownCommandKind,
    InvalidCommandPayload,
    UnsupportedTextureCopyField,
};

pub fn parseCommands(allocator: Allocator, text: []const u8) ![]model.Command {
    const parsed = try std.json.parseFromSlice([]const RawCommand, allocator, text, .{ .ignore_unknown_fields = true });
    defer parsed.deinit();

    var list = std.array_list.Managed(model.Command).init(allocator);
    errdefer {
        for (list.items) |command| {
            freeCommandPayload(allocator, command);
        }
        list.deinit();
    }
    try list.ensureTotalCapacity(parsed.value.len);

    for (parsed.value) |raw| {
        list.appendAssumeCapacity(try parseOne(allocator, raw));
    }

    return list.toOwnedSlice();
}

pub fn freeCommands(allocator: Allocator, commands: []model.Command) void {
    for (commands) |command| {
        freeCommandPayload(allocator, command);
    }
    allocator.free(commands);
}

fn freeCommandPayload(allocator: Allocator, command: model.Command) void {
    switch (command) {
        .kernel_dispatch => |kernel_command| {
            allocator.free(kernel_command.kernel);
            if (kernel_command.entry_point) |entry_point| allocator.free(entry_point);
            if (kernel_command.bindings) |bindings| allocator.free(bindings);
        },
        .render_draw => |render_command| {
            if (render_command.index_data) |index_data| {
                switch (index_data) {
                    .uint16 => |values| allocator.free(values),
                    .uint32 => |values| allocator.free(values),
                }
            }
        },
        else => {},
    }
}

fn commandKindEquals(raw_kind: []const u8, kind: []const u8) bool {
    return std.ascii.eqlIgnoreCase(raw_kind, kind);
}

fn getCommandName(raw: RawCommand) ?[]const u8 {
    return raw.command orelse raw.kind orelse raw.command_kind;
}

const NormalizedKind = enum {
    upload,
    copy,
    barrier,
    dispatch,
    kernel_dispatch,
    render_draw,
};

fn parseKind(raw: RawCommand) !NormalizedKind {
    const kind = getCommandName(raw) orelse return ParseError.MissingCommandKind;

    if (commandKindEquals(kind, "upload") or commandKindEquals(kind, "buffer_upload")) {
        return .upload;
    }

    if (commandKindEquals(kind, "copy_buffer_to_texture") or
        commandKindEquals(kind, "copy_texture") or
        commandKindEquals(kind, "texture_copy") or
        commandKindEquals(kind, "copy_texture_to_buffer") or
        commandKindEquals(kind, "copy_buffer_to_buffer") or
        commandKindEquals(kind, "buffer_copy") or
        commandKindEquals(kind, "copyBufferToTexture") or
        commandKindEquals(kind, "copyTextureToBuffer") or
        commandKindEquals(kind, "copyBufferToBuffer") or
        commandKindEquals(kind, "copy_texture_to_texture"))
    {
        return .copy;
    }

    if (commandKindEquals(kind, "barrier")) {
        return .barrier;
    }

    if (commandKindEquals(kind, "dispatch") or
        commandKindEquals(kind, "dispatch_workgroups") or
        commandKindEquals(kind, "dispatch_invocations"))
    {
        return .dispatch;
    }

    if (commandKindEquals(kind, "kernel_dispatch")) {
        return .kernel_dispatch;
    }
    if (commandKindEquals(kind, "render_draw") or
        commandKindEquals(kind, "draw") or
        commandKindEquals(kind, "draw_call") or
        commandKindEquals(kind, "draw_indexed"))
    {
        return .render_draw;
    }

    return ParseError.UnknownCommandKind;
}

fn parseCopyDirectionFromKind(raw: RawCommand) model.CopyDirection {
    const kind = getCommandName(raw) orelse return .buffer_to_buffer;
    if (commandKindEquals(kind, "copy_buffer_to_texture") or
        commandKindEquals(kind, "copy_texture") or
        commandKindEquals(kind, "copyBufferToTexture") or
        commandKindEquals(kind, "copyTexture"))
    {
        return .buffer_to_texture;
    }
    if (commandKindEquals(kind, "copy_texture_to_buffer") or commandKindEquals(kind, "copyTextureToBuffer")) {
        return .texture_to_buffer;
    }
    if (commandKindEquals(kind, "copy_texture_to_texture") or commandKindEquals(kind, "copyTextureToTexture")) {
        return .texture_to_texture;
    }
    return .buffer_to_buffer;
}

fn parseCopyDirection(raw_direction: ?[]const u8, raw: RawCommand) !model.CopyDirection {
    if (raw_direction) |raw_value| {
        if (commandKindEquals(raw_value, "buffer_to_buffer")) return .buffer_to_buffer;
        if (commandKindEquals(raw_value, "buffer_to_texture")) return .buffer_to_texture;
        if (commandKindEquals(raw_value, "texture_to_buffer")) return .texture_to_buffer;
        if (commandKindEquals(raw_value, "texture_to_texture")) return .texture_to_texture;
        return ParseError.InvalidCommandPayload;
    }
    return parseCopyDirectionFromKind(raw);
}

fn parseCopyResourceKind(raw_kind: ?[]const u8) ?model.CopyResourceKind {
    const raw_value = raw_kind orelse return null;
    if (commandKindEquals(raw_value, "buffer")) return .buffer;
    if (commandKindEquals(raw_value, "texture")) return .texture;
    return null;
}

fn parseCopyResource(
    side: []const u8,
    raw: RawCommand,
    _direction: model.CopyDirection,
    default_kind: model.CopyResourceKind,
    direction_default_to_texture: bool,
) !model.CopyTextureResource {
    _ = _direction;
    const handle = if (std.mem.eql(u8, side, "src"))
        (raw.src_handle orelse raw.srcHandle)
    else
        (raw.dst_handle orelse raw.dstHandle);

    if (handle == null) return ParseError.InvalidCommandPayload;

    const kind = parseCopyResourceKind(if (std.mem.eql(u8, side, "src")) raw.src_kind orelse raw.srcKind else raw.dst_kind orelse raw.dstKind) orelse default_kind;

    const width = if (std.mem.eql(u8, side, "src"))
        (raw.src_width orelse raw.srcWidth orelse 1)
    else
        (raw.dst_width orelse raw.dstWidth orelse 1);
    const height = if (std.mem.eql(u8, side, "src"))
        (raw.src_height orelse raw.srcHeight orelse 1)
    else
        (raw.dst_height orelse raw.dstHeight orelse 1);
    const depth = if (std.mem.eql(u8, side, "src"))
        (raw.src_depth_or_array_layers orelse raw.srcDepthOrArrayLayers orelse raw.src_depth orelse 1)
    else
        (raw.dst_depth_or_array_layers orelse raw.dstDepthOrArrayLayers orelse raw.dst_depth orelse 1);
    const format_raw = if (std.mem.eql(u8, side, "src"))
        (raw.src_format orelse raw.srcFormat)
    else
        (raw.dst_format orelse raw.dstFormat);
    const usage = if (std.mem.eql(u8, side, "src"))
        (raw.src_usage orelse raw.srcUsage orelse 0)
    else
        (raw.dst_usage orelse raw.dstUsage orelse 0);
    const dimension = if (std.mem.eql(u8, side, "src"))
        parseTextureDimension(raw.src_dimension orelse raw.srcDimension, .texture) catch model.WGPUTextureDimension_Undefined
    else
        parseTextureDimension(raw.dst_dimension orelse raw.dstDimension, .texture) catch model.WGPUTextureDimension_Undefined;
    const view_dimension = if (std.mem.eql(u8, side, "src"))
        parseTextureViewDimension(raw.src_view_dimension orelse raw.srcViewDimension) orelse model.WGPUTextureViewDimension_Undefined
    else
        parseTextureViewDimension(raw.dst_view_dimension orelse raw.dstViewDimension) orelse model.WGPUTextureViewDimension_Undefined;
    const mip_level = if (std.mem.eql(u8, side, "src"))
        (raw.src_mip_level orelse raw.srcMipLevel orelse 0)
    else
        (raw.dst_mip_level orelse raw.dstMipLevel orelse 0);
    const sample_count = if (std.mem.eql(u8, side, "src"))
        (raw.src_sample_count orelse raw.srcSampleCount orelse 1)
    else
        (raw.dst_sample_count orelse raw.dstSampleCount orelse 1);
    const aspect = if (std.mem.eql(u8, side, "src"))
        parseTextureAspect(raw.src_aspect orelse raw.srcAspect) orelse model.WGPUTextureAspect_Undefined
    else
        parseTextureAspect(raw.dst_aspect orelse raw.dstAspect) orelse model.WGPUTextureAspect_Undefined;
    const bytes_per_row = if (std.mem.eql(u8, side, "src"))
        (raw.src_bytes_per_row orelse raw.srcBytesPerRow orelse 0)
    else
        (raw.dst_bytes_per_row orelse raw.dstBytesPerRow orelse 0);
    const rows_per_image = if (std.mem.eql(u8, side, "src"))
        (raw.src_rows_per_image orelse raw.srcRowsPerImage orelse 0)
    else
        (raw.dst_rows_per_image orelse raw.dstRowsPerImage orelse 0);
    const offset = if (std.mem.eql(u8, side, "src"))
        (raw.src_offset orelse raw.srcOffset orelse 0)
    else
        (raw.dst_offset orelse raw.dstOffset orelse 0);

    var effective_kind = kind;
    if (kind == .buffer and direction_default_to_texture) {
        effective_kind = .texture;
    }

    var texture_format: u32 = model.WGPUTextureFormat_Undefined;
    if (format_raw) |raw_format| {
        texture_format = parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload;
    }

    return .{
        .handle = handle.?,
        .kind = effective_kind,
        .width = width,
        .height = height,
        .depth_or_array_layers = depth,
        .format = texture_format,
        .usage = usage,
        .dimension = dimension,
        .view_dimension = view_dimension,
        .mip_level = mip_level,
        .sample_count = sample_count,
        .aspect = aspect,
        .bytes_per_row = bytes_per_row,
        .rows_per_image = rows_per_image,
        .offset = offset,
    };
}

fn parseDispatchDimensions(raw: RawCommand) !model.DispatchCommand {
    var dims: [3]u32 = .{ 1, 1, 1 };

    if (raw.workgroupCount) |group_count| {
        dims[0] = group_count[0];
        dims[1] = group_count[1];
        dims[2] = group_count[2];
    } else if (raw.workgroups) |group_count| {
        dims[0] = group_count[0];
        dims[1] = group_count[1];
        dims[2] = group_count[2];
    } else {
        dims[0] = raw.x orelse 1;
        dims[1] = raw.y orelse 1;
        dims[2] = raw.z orelse 1;
    }

    if (dims[0] == 0 or dims[1] == 0 or dims[2] == 0) {
        return ParseError.InvalidCommandPayload;
    }

    return .{
        .x = dims[0],
        .y = dims[1],
        .z = dims[2],
    };
}

fn parseKernelBindings(allocator: Allocator, raw_bindings: []const RawKernelBinding) ![]const model.KernelBinding {
    var bindings = try std.array_list.Managed(model.KernelBinding).initCapacity(allocator, raw_bindings.len);
    errdefer bindings.deinit();

    for (raw_bindings) |raw_binding| {
        const binding_index = raw_binding.binding orelse return ParseError.InvalidCommandPayload;
        const group = raw_binding.group orelse raw_binding.groupIndex orelse raw_binding.group_index orelse 0;
        const handle = raw_binding.handle orelse raw_binding.resource_handle orelse raw_binding.resourceHandle orelse return ParseError.InvalidCommandPayload;
        const kind = parseKernelBindingKind(raw_binding.kind orelse raw_binding.resource_kind orelse raw_binding.resourceKind) orelse return ParseError.InvalidCommandPayload;
        const visibility = parseShaderStage(raw_binding.visibility) orelse parseWGPUBits(raw_binding.visibilityMask) orelse model.WGPUShaderStage_Compute;
        const buffer_offset = raw_binding.buffer_offset orelse raw_binding.bufferOffset orelse 0;
        const buffer_size = raw_binding.buffer_size orelse raw_binding.bufferSize orelse model.WGPUWholeSize;

        try bindings.append(.{
            .binding = binding_index,
            .group = group,
            .resource_kind = kind,
            .resource_handle = handle,
            .visibility = visibility,
            .buffer_offset = buffer_offset,
            .buffer_size = buffer_size,
            .buffer_type = parseBufferBindingType(raw_binding.buffer_type orelse raw_binding.bufferType) orelse model.WGPUBufferBindingType_Undefined,
            .texture_sample_type = parseTextureSampleType(raw_binding.texture_sample_type orelse raw_binding.textureSampleType) orelse model.WGPUTextureSampleType_Undefined,
            .texture_view_dimension = parseTextureViewDimension(raw_binding.texture_view_dimension orelse raw_binding.textureViewDimension) orelse model.WGPUTextureViewDimension_Undefined,
            .storage_texture_access = parseStorageTextureAccess(raw_binding.storage_access orelse raw_binding.storageAccess) orelse model.WGPUStorageTextureAccess_Undefined,
            .texture_aspect = parseTextureAspect(raw_binding.texture_aspect orelse raw_binding.textureAspect) orelse model.WGPUTextureAspect_Undefined,
            .texture_format = if (raw_binding.texture_format orelse raw_binding.textureFormat) |raw_format|
                parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload
            else
                model.WGPUTextureFormat_Undefined,
            .texture_multisampled = raw_binding.multisampled orelse false,
        });
    }

    return bindings.toOwnedSlice();
}

fn parseKernelBindingKind(raw_kind: ?[]const u8) ?model.KernelBindingResourceKind {
    const value = raw_kind orelse return .buffer;
    if (commandKindEquals(value, "buffer") or commandKindEquals(value, "uniform") or commandKindEquals(value, "storage_buffer") or commandKindEquals(value, "readonly_storage_buffer")) {
        return .buffer;
    }
    if (commandKindEquals(value, "texture") or commandKindEquals(value, "sampled_texture") or commandKindEquals(value, "texture_sampled")) {
        return .texture;
    }
    if (commandKindEquals(value, "storage_texture") or commandKindEquals(value, "storage_texture_binding") or commandKindEquals(value, "storage")) {
        return .storage_texture;
    }
    return null;
}

fn parseShaderStage(raw_stage: ?[]const u8) ?model.WGPUFlags {
    const value = raw_stage orelse return null;
    if (commandKindEquals(value, "compute") or commandKindEquals(value, "compute-only") or commandKindEquals(value, "computeOnly")) {
        return model.WGPUShaderStage_Compute;
    }
    if (commandKindEquals(value, "vertex")) return model.WGPUShaderStage_Vertex;
    if (commandKindEquals(value, "fragment")) return model.WGPUShaderStage_Fragment;
    if (commandKindEquals(value, "all") or commandKindEquals(value, "*")) return model.WGPUShaderStage_Vertex | model.WGPUShaderStage_Fragment | model.WGPUShaderStage_Compute;
    return null;
}

fn parseWGPUBits(raw_bits: ?u64) ?model.WGPUFlags {
    return raw_bits;
}

fn parseBufferBindingType(raw: ?[]const u8) ?u32 {
    const value = raw orelse return model.WGPUBufferBindingType_Undefined;
    if (commandKindEquals(value, "uniform")) return model.WGPUBufferBindingType_Uniform;
    if (commandKindEquals(value, "storage")) return model.WGPUBufferBindingType_Storage;
    if (commandKindEquals(value, "readonly") or commandKindEquals(value, "read_only_storage")) return model.WGPUBufferBindingType_ReadOnlyStorage;
    return model.WGPUBufferBindingType_Undefined;
}

fn parseTextureSampleType(raw: ?[]const u8) ?u32 {
    const value = raw orelse return model.WGPUTextureSampleType_Undefined;
    if (commandKindEquals(value, "float")) return model.WGPUTextureSampleType_Float;
    if (commandKindEquals(value, "unfilterable-float") or commandKindEquals(value, "unfilterable_float")) return model.WGPUTextureSampleType_UnfilterableFloat;
    if (commandKindEquals(value, "depth")) return model.WGPUTextureSampleType_Depth;
    if (commandKindEquals(value, "sint")) return model.WGPUTextureSampleType_Sint;
    if (commandKindEquals(value, "uint")) return model.WGPUTextureSampleType_Uint;
    return model.WGPUTextureSampleType_Undefined;
}

fn parseTextureViewDimension(raw: ?[]const u8) ?u32 {
    const value = raw orelse return model.WGPUTextureViewDimension_Undefined;
    if (commandKindEquals(value, "1d") or commandKindEquals(value, "1D") or commandKindEquals(value, "1d-array")) return model.WGPUTextureViewDimension_1D;
    if (commandKindEquals(value, "2d") or commandKindEquals(value, "2D")) return model.WGPUTextureViewDimension_2D;
    if (commandKindEquals(value, "2d-array")) return model.WGPUTextureViewDimension_2DArray;
    if (commandKindEquals(value, "cube")) return model.WGPUTextureViewDimension_Cube;
    if (commandKindEquals(value, "cube-array")) return model.WGPUTextureViewDimension_CubeArray;
    if (commandKindEquals(value, "3d") or commandKindEquals(value, "3D")) return model.WGPUTextureViewDimension_3D;
    return model.WGPUTextureViewDimension_Undefined;
}

fn parseTextureDimension(raw: ?[]const u8, fallback: model.CopyResourceKind) !u32 {
    _ = fallback;
    const value = raw orelse return model.WGPUTextureDimension_Undefined;
    if (commandKindEquals(value, "1d")) return model.WGPUTextureDimension_1D;
    if (commandKindEquals(value, "2d")) return model.WGPUTextureDimension_2D;
    if (commandKindEquals(value, "3d")) return model.WGPUTextureDimension_3D;
    return model.WGPUTextureDimension_Undefined;
}

fn parseStorageTextureAccess(raw: ?[]const u8) ?u32 {
    const value = raw orelse return model.WGPUStorageTextureAccess_Undefined;
    if (commandKindEquals(value, "write_only") or commandKindEquals(value, "write-only")) return model.WGPUStorageTextureAccess_WriteOnly;
    if (commandKindEquals(value, "read_only") or commandKindEquals(value, "read-only")) return model.WGPUStorageTextureAccess_ReadOnly;
    if (commandKindEquals(value, "read_write") or commandKindEquals(value, "read-write")) return model.WGPUStorageTextureAccess_ReadWrite;
    return model.WGPUStorageTextureAccess_Undefined;
}

fn parseTextureAspect(raw: ?[]const u8) ?u32 {
    const value = raw orelse return model.WGPUTextureAspect_Undefined;
    if (commandKindEquals(value, "all")) return model.WGPUTextureAspect_All;
    if (commandKindEquals(value, "depth-only") or commandKindEquals(value, "depth_only") or commandKindEquals(value, "depth")) return model.WGPUTextureAspect_DepthOnly;
    if (commandKindEquals(value, "stencil-only") or commandKindEquals(value, "stencil_only") or commandKindEquals(value, "stencil")) return model.WGPUTextureAspect_StencilOnly;
    return model.WGPUTextureAspect_Undefined;
}

fn parseTextureFormat(raw: []const u8) !u32 {
    if (raw.len == 0) return model.WGPUTextureFormat_Undefined;
    if (commandKindEquals(raw, "r8unorm")) return model.WGPUTextureFormat_R8Unorm;
    if (commandKindEquals(raw, "r8snorm")) return model.WGPUTextureFormat_R8Snorm;
    if (commandKindEquals(raw, "r8uint")) return model.WGPUTextureFormat_R8Uint;
    if (commandKindEquals(raw, "r8sint")) return model.WGPUTextureFormat_R8Sint;
    if (commandKindEquals(raw, "r16unorm")) return model.WGPUTextureFormat_R16Unorm;
    if (commandKindEquals(raw, "r16snorm")) return model.WGPUTextureFormat_R16Snorm;
    if (commandKindEquals(raw, "r16uint")) return model.WGPUTextureFormat_R16Uint;
    if (commandKindEquals(raw, "r16sint")) return model.WGPUTextureFormat_R16Sint;
    if (commandKindEquals(raw, "r16float")) return model.WGPUTextureFormat_R16Float;
    if (commandKindEquals(raw, "rg8unorm")) return model.WGPUTextureFormat_RG8Unorm;
    if (commandKindEquals(raw, "rg8snorm")) return model.WGPUTextureFormat_RG8Snorm;
    if (commandKindEquals(raw, "rg8uint")) return model.WGPUTextureFormat_RG8Uint;
    if (commandKindEquals(raw, "rg8sint")) return model.WGPUTextureFormat_RG8Sint;
    if (commandKindEquals(raw, "r32float")) return model.WGPUTextureFormat_R32Float;
    if (commandKindEquals(raw, "r32uint")) return model.WGPUTextureFormat_R32Uint;
    if (commandKindEquals(raw, "r32sint")) return model.WGPUTextureFormat_R32Sint;
    if (commandKindEquals(raw, "rg16unorm")) return model.WGPUTextureFormat_RG16Unorm;
    if (commandKindEquals(raw, "rg16snorm")) return model.WGPUTextureFormat_RG16Snorm;
    if (commandKindEquals(raw, "rg16uint")) return model.WGPUTextureFormat_RG16Uint;
    if (commandKindEquals(raw, "rg16sint")) return model.WGPUTextureFormat_RG16Sint;
    if (commandKindEquals(raw, "rg16float")) return model.WGPUTextureFormat_RG16Float;
    if (commandKindEquals(raw, "rgba8unorm")) return model.WGPUTextureFormat_RGBA8Unorm;
    if (commandKindEquals(raw, "rgba8unorm-srgb") or commandKindEquals(raw, "rgba8unormsrgb")) return model.WGPUTextureFormat_RGBA8UnormSrgb;
    if (commandKindEquals(raw, "rgba8snorm")) return model.WGPUTextureFormat_RGBA8Snorm;
    if (commandKindEquals(raw, "rgba8uint")) return model.WGPUTextureFormat_RGBA8Uint;
    if (commandKindEquals(raw, "rgba8sint")) return model.WGPUTextureFormat_RGBA8Sint;
    if (commandKindEquals(raw, "bgra8unorm")) return model.WGPUTextureFormat_BGRA8Unorm;
    if (commandKindEquals(raw, "bgra8unorm-srgb") or commandKindEquals(raw, "bgra8unormsrgb")) return model.WGPUTextureFormat_BGRA8UnormSrgb;
    if (commandKindEquals(raw, "depth16unorm")) return model.WGPUTextureFormat_Depth16Unorm;
    if (commandKindEquals(raw, "depth24plus")) return model.WGPUTextureFormat_Depth24Plus;
    if (commandKindEquals(raw, "depth24plus-stencil8") or commandKindEquals(raw, "depth24plus-stencil8")) return model.WGPUTextureFormat_Depth24PlusStencil8;
    if (commandKindEquals(raw, "depth32float")) return model.WGPUTextureFormat_Depth32Float;
    if (commandKindEquals(raw, "depth32float-stencil8")) return model.WGPUTextureFormat_Depth32FloatStencil8;
    if (std.ascii.eqlIgnoreCase(raw, "undefined")) return model.WGPUTextureFormat_Undefined;
    const int_value = std.fmt.parseInt(u32, raw, 10) catch return ParseError.InvalidCommandPayload;
    return int_value;
}

fn parseRenderDrawPipelineMode(raw: ?[]const u8) !model.RenderDrawPipelineMode {
    const value = raw orelse return .static;
    if (commandKindEquals(value, "static")) return .static;
    if (commandKindEquals(value, "redundant")) return .redundant;
    return ParseError.InvalidCommandPayload;
}

fn parseRenderDrawBindGroupMode(raw: ?[]const u8) !model.RenderDrawBindGroupMode {
    const value = raw orelse return .no_change;
    if (commandKindEquals(value, "no-change") or commandKindEquals(value, "no_change")) return .no_change;
    if (commandKindEquals(value, "redundant")) return .redundant;
    return ParseError.InvalidCommandPayload;
}

fn parseRenderIndexFormat(raw: ?[]const u8) !?model.RenderIndexFormat {
    const value = raw orelse return null;
    if (commandKindEquals(value, "uint16") or commandKindEquals(value, "u16")) return .uint16;
    if (commandKindEquals(value, "uint32") or commandKindEquals(value, "u32")) return .uint32;
    return ParseError.InvalidCommandPayload;
}

fn inferRenderIndexFormat(indices: []const u32) model.RenderIndexFormat {
    for (indices) |value| {
        if (value > std.math.maxInt(u16)) return .uint32;
    }
    return .uint16;
}

fn parseRenderIndexData(
    allocator: Allocator,
    raw_indices: []const u32,
    requested_format: ?model.RenderIndexFormat,
) !model.RenderIndexData {
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

fn parseOne(allocator: Allocator, raw: RawCommand) !model.Command {
    const kind = try parseKind(raw);

    if (kind == .upload) {
        const bytes = raw.bytes orelse return ParseError.InvalidCommandPayload;
        const align_bytes = raw.alignBytes orelse raw.alignmentBytes orelse 4;
        return .{ .upload = .{ .bytes = bytes, .align_bytes = align_bytes } };
    }

    if (kind == .copy) {
        const bytes = raw.bytes orelse return ParseError.InvalidCommandPayload;
        const direction = try parseCopyDirection(raw.direction, raw);
        const default_src_kind: model.CopyResourceKind = switch (direction) {
            .buffer_to_buffer, .buffer_to_texture => .buffer,
            .texture_to_buffer, .texture_to_texture => .texture,
        };
        const default_dst_kind: model.CopyResourceKind = switch (direction) {
            .buffer_to_buffer, .texture_to_buffer => .buffer,
            .buffer_to_texture, .texture_to_texture => .texture,
        };

        const src = try parseCopyResource("src", raw, direction, default_src_kind, direction == .texture_to_buffer or direction == .texture_to_texture);
        const dst = try parseCopyResource("dst", raw, direction, default_dst_kind, direction == .buffer_to_texture or direction == .texture_to_texture);

        return .{ .copy_buffer_to_texture = .{ .direction = direction, .src = src, .dst = dst, .bytes = bytes } };
    }

    if (kind == .barrier) {
        const dependency_count = raw.dependency_count orelse raw.dependencyCount orelse 0;
        return .{ .barrier = .{ .dependency_count = dependency_count } };
    }

    if (kind == .kernel_dispatch or kind == .dispatch) {
        const dispatch = try parseDispatchDimensions(raw);
        if (kind == .kernel_dispatch) {
            const repeat_count = raw.repeat orelse raw.dispatch_count orelse raw.dispatchCount orelse 1;
            if (repeat_count == 0) return ParseError.InvalidCommandPayload;
            const kernel_name = try allocator.dupe(u8, raw.kernel orelse raw.kernel_name orelse return ParseError.InvalidCommandPayload);
            errdefer allocator.free(kernel_name);
            const entry_point = if (raw.entry_point) |entry| try allocator.dupe(u8, entry) else if (raw.entryPoint) |entry| try allocator.dupe(u8, entry) else null;
            errdefer if (entry_point) |entry| allocator.free(entry);
            const kernel_bindings = if (raw.bindings) |raw_bindings| try parseKernelBindings(allocator, raw_bindings) else null;
            errdefer if (kernel_bindings) |bindings| allocator.free(bindings);
            return .{ .kernel_dispatch = .{
                .kernel = kernel_name,
                .entry_point = entry_point,
                .x = dispatch.x,
                .y = dispatch.y,
                .z = dispatch.z,
                .repeat = repeat_count,
                .bindings = kernel_bindings,
            } };
        }
        return .{ .dispatch = dispatch };
    }

    if (kind == .render_draw) {
        const draw_count = raw.draw_count orelse raw.drawCount orelse return ParseError.InvalidCommandPayload;
        const vertex_count = raw.vertex_count orelse raw.vertexCount orelse 3;
        const instance_count = raw.instance_count orelse raw.instanceCount orelse 1;
        const first_vertex = raw.first_vertex orelse raw.firstVertex orelse 0;
        const first_instance = raw.first_instance orelse raw.firstInstance orelse 0;
        const parsed_index_count = raw.index_count orelse raw.indexCount;
        const is_draw_indexed = blk: {
            const command_name = getCommandName(raw) orelse break :blk false;
            break :blk commandKindEquals(command_name, "draw_indexed");
        };
        const raw_index_data = raw.index_data orelse raw.indexData orelse raw.indices;
        const indexed_draw = is_draw_indexed or parsed_index_count != null or raw_index_data != null;
        const requested_index_format = try parseRenderIndexFormat(raw.index_format orelse raw.indexFormat);
        const index_data = if (indexed_draw) blk: {
            const provided = raw_index_data orelse return ParseError.InvalidCommandPayload;
            if (provided.len == 0) return ParseError.InvalidCommandPayload;
            break :blk try parseRenderIndexData(allocator, provided, requested_index_format);
        } else null;
        errdefer if (index_data) |values| switch (values) {
            .uint16 => |items| allocator.free(items),
            .uint32 => |items| allocator.free(items),
        };
        const index_data_len_u32 = if (index_data) |values| switch (values) {
            .uint16 => |items| std.math.cast(u32, items.len) orelse return ParseError.InvalidCommandPayload,
            .uint32 => |items| std.math.cast(u32, items.len) orelse return ParseError.InvalidCommandPayload,
        } else 0;
        const index_count = if (parsed_index_count) |count| count else if (indexed_draw) index_data_len_u32 else null;
        const first_index = raw.first_index orelse raw.firstIndex orelse 0;
        const base_vertex = raw.base_vertex orelse raw.baseVertex orelse 0;
        const target_handle = raw.target_handle orelse raw.targetHandle orelse model.DEFAULT_RENDER_TARGET_HANDLE;
        const target_width = raw.target_width orelse raw.targetWidth orelse model.DEFAULT_RENDER_TARGET_WIDTH;
        const target_height = raw.target_height orelse raw.targetHeight orelse model.DEFAULT_RENDER_TARGET_HEIGHT;
        const target_format = if (raw.target_format orelse raw.targetFormat) |raw_format|
            parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload
        else
            model.DEFAULT_RENDER_TARGET_FORMAT;
        const pipeline_mode = parseRenderDrawPipelineMode(raw.pipeline_mode orelse raw.pipelineMode) catch return ParseError.InvalidCommandPayload;
        const bind_group_mode = parseRenderDrawBindGroupMode(raw.bind_group_mode orelse raw.bindGroupMode) catch return ParseError.InvalidCommandPayload;

        if (draw_count == 0 or vertex_count == 0 or instance_count == 0 or target_width == 0 or target_height == 0) {
            return ParseError.InvalidCommandPayload;
        }
        if (index_count != null and index_count.? == 0) return ParseError.InvalidCommandPayload;
        if (index_count != null) {
            const index_end = std.math.add(u32, first_index, index_count.?) catch return ParseError.InvalidCommandPayload;
            if (index_end > index_data_len_u32) return ParseError.InvalidCommandPayload;
        }

        return .{ .render_draw = .{
            .draw_count = draw_count,
            .vertex_count = vertex_count,
            .instance_count = instance_count,
            .first_vertex = first_vertex,
            .first_instance = first_instance,
            .index_count = index_count,
            .first_index = first_index,
            .base_vertex = base_vertex,
            .index_data = index_data,
            .target_handle = target_handle,
            .target_width = target_width,
            .target_height = target_height,
            .target_format = target_format,
            .pipeline_mode = pipeline_mode,
            .bind_group_mode = bind_group_mode,
        } };
    }

    return ParseError.UnknownCommandKind;
}
