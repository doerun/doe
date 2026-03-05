const std = @import("std");
const model = @import("model.zig");
const parse_helpers = @import("command_parse_helpers.zig");
const parse_extra = @import("command_json_extra.zig");

const Allocator = std.mem.Allocator;

const command_json_raw = @import("command_json_raw.zig");
const RawCommand = command_json_raw.RawCommand;
const RawKernelBinding = command_json_raw.RawKernelBinding;
pub const ParseError = command_json_raw.ParseError;

pub fn parseCommands(allocator: Allocator, text: []const u8) ![]model.Command {
    if (std.mem.eql(u8, std.mem.trim(u8, text, " \n\r\t"), "[]")) {
        return &[_]model.Command{};
    }

    // Zig's strict parser crashes if the string has a trailing newline after the valid JSON array end.
    const cleanly_trimmed = std.mem.trimRight(u8, text, " \n\r\t\\n");
    const parsed = try std.json.parseFromSliceLeaky([]const RawCommand, allocator, cleanly_trimmed, .{ 
        .ignore_unknown_fields = true,
        .allocate = .alloc_always,
    });

    var list = std.ArrayList(model.Command).empty;
    errdefer {
        for (list.items) |command| {
            freeCommandPayload(allocator, command);
        }
        list.deinit(allocator);
    }
    try list.ensureTotalCapacity(allocator, parsed.len);

    for (parsed) |raw| {
        list.appendAssumeCapacity(try parseOne(allocator, raw));
    }

    return list.toOwnedSlice(allocator);
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
        .render_draw, .draw_indirect, .draw_indexed_indirect, .render_pass => |render_command| {
            if (render_command.index_data) |index_data| {
                switch (index_data) {
                    .uint16 => |values| allocator.free(values),
                    .uint32 => |values| allocator.free(values),
                }
            }
            if (render_command.bind_group_dynamic_offsets) |offsets| {
                allocator.free(offsets);
            }
        },
        .texture_write => |write_texture| allocator.free(write_texture.data),
        else => {},
    }
}

fn commandKindEquals(raw_kind: []const u8, kind: []const u8) bool {
    return std.ascii.eqlIgnoreCase(raw_kind, kind);
}

fn getCommandName(raw: RawCommand) ?[]const u8 {
    if (raw.map_async != null) return "map_async";
    return raw.command orelse raw.kind orelse raw.command_kind;
}

const NormalizedKind = enum {
    upload,
    copy,
    barrier,
    dispatch,
    dispatch_indirect,
    kernel_dispatch,
    render_draw,
    draw_indirect,
    draw_indexed_indirect,
    render_pass,
    sampler_create,
    sampler_destroy,
    texture_write,
    texture_query,
    texture_destroy,
    surface_create,
    surface_capabilities,
    surface_configure,
    surface_acquire,
    surface_present,
    surface_unconfigure,
    surface_release,
    async_diagnostics,
    map_async,
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
    if (commandKindEquals(kind, "dispatch_indirect")) {
        return .dispatch_indirect;
    }

    if (commandKindEquals(kind, "kernel_dispatch")) {
        return .kernel_dispatch;
    }
    if (commandKindEquals(kind, "draw_indirect")) {
        return .draw_indirect;
    }
    if (commandKindEquals(kind, "draw_indexed_indirect")) {
        return .draw_indexed_indirect;
    }
    if (commandKindEquals(kind, "render_pass")) {
        return .render_pass;
    }
    if (commandKindEquals(kind, "render_draw") or
        commandKindEquals(kind, "draw") or
        commandKindEquals(kind, "draw_call") or
        commandKindEquals(kind, "draw_indexed"))
    {
        return .render_draw;
    }
    if (commandKindEquals(kind, "sampler_create") or commandKindEquals(kind, "create_sampler")) {
        return .sampler_create;
    }
    if (commandKindEquals(kind, "sampler_destroy") or commandKindEquals(kind, "destroy_sampler")) {
        return .sampler_destroy;
    }
    if (commandKindEquals(kind, "texture_write") or commandKindEquals(kind, "write_texture") or commandKindEquals(kind, "queue_write_texture")) {
        return .texture_write;
    }
    if (commandKindEquals(kind, "texture_query") or commandKindEquals(kind, "query_texture")) {
        return .texture_query;
    }
    if (commandKindEquals(kind, "texture_destroy") or commandKindEquals(kind, "destroy_texture")) {
        return .texture_destroy;
    }
    if (commandKindEquals(kind, "surface_create") or commandKindEquals(kind, "create_surface")) {
        return .surface_create;
    }
    if (commandKindEquals(kind, "surface_capabilities") or commandKindEquals(kind, "surface_get_capabilities")) {
        return .surface_capabilities;
    }
    if (commandKindEquals(kind, "surface_configure") or commandKindEquals(kind, "configure_surface")) {
        return .surface_configure;
    }
    if (commandKindEquals(kind, "surface_acquire") or commandKindEquals(kind, "surface_get_current_texture") or commandKindEquals(kind, "surface_current_texture")) {
        return .surface_acquire;
    }
    if (commandKindEquals(kind, "surface_present") or commandKindEquals(kind, "present_surface")) {
        return .surface_present;
    }
    if (commandKindEquals(kind, "surface_unconfigure") or commandKindEquals(kind, "unconfigure_surface")) {
        return .surface_unconfigure;
    }
    if (commandKindEquals(kind, "surface_release") or commandKindEquals(kind, "release_surface")) {
        return .surface_release;
    }
    if (commandKindEquals(kind, "async_diagnostics") or commandKindEquals(kind, "pipeline_async_diagnostics")) {
        return .async_diagnostics;
    }
    if (commandKindEquals(kind, "map_async") or commandKindEquals(kind, "buffer_map_async")) {
        return .map_async;
    }

    return ParseError.UnknownCommandKind;
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

    const kind = parse_helpers.parseCopyResourceKind(if (std.mem.eql(u8, side, "src")) raw.src_kind orelse raw.srcKind else raw.dst_kind orelse raw.dstKind) orelse default_kind;

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
        parse_helpers.parseTextureDimension(raw.src_dimension orelse raw.srcDimension)
    else
        parse_helpers.parseTextureDimension(raw.dst_dimension orelse raw.dstDimension);
    const view_dimension = if (std.mem.eql(u8, side, "src"))
        parse_helpers.parseTextureViewDimension(raw.src_view_dimension orelse raw.srcViewDimension)
    else
        parse_helpers.parseTextureViewDimension(raw.dst_view_dimension orelse raw.dstViewDimension);
    const mip_level = if (std.mem.eql(u8, side, "src"))
        (raw.src_mip_level orelse raw.srcMipLevel orelse 0)
    else
        (raw.dst_mip_level orelse raw.dstMipLevel orelse 0);
    const sample_count = if (std.mem.eql(u8, side, "src"))
        (raw.src_sample_count orelse raw.srcSampleCount orelse 1)
    else
        (raw.dst_sample_count orelse raw.dstSampleCount orelse 1);
    const aspect = if (std.mem.eql(u8, side, "src"))
        parse_helpers.parseTextureAspect(raw.src_aspect orelse raw.srcAspect)
    else
        parse_helpers.parseTextureAspect(raw.dst_aspect orelse raw.dstAspect);
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
        texture_format = parse_helpers.parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload;
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
    var bindings = try std.ArrayList(model.KernelBinding).initCapacity(allocator, raw_bindings.len);
    errdefer bindings.deinit(allocator);

    for (raw_bindings) |raw_binding| {
        const binding_index = raw_binding.binding orelse return ParseError.InvalidCommandPayload;
        const group = raw_binding.group orelse raw_binding.groupIndex orelse raw_binding.group_index orelse 0;
        const handle = raw_binding.handle orelse raw_binding.resource_handle orelse raw_binding.resourceHandle orelse return ParseError.InvalidCommandPayload;
        const kind = parse_helpers.parseKernelBindingKind(raw_binding.kind orelse raw_binding.resource_kind orelse raw_binding.resourceKind) orelse return ParseError.InvalidCommandPayload;
        const visibility = parse_helpers.parseShaderStage(raw_binding.visibility) orelse parse_helpers.parseWGPUBits(raw_binding.visibilityMask) orelse model.WGPUShaderStage_Compute;
        const buffer_offset = raw_binding.buffer_offset orelse raw_binding.bufferOffset orelse 0;
        const buffer_size = raw_binding.buffer_size orelse raw_binding.bufferSize orelse model.WGPUWholeSize;

        try bindings.append(allocator, .{
            .binding = binding_index,
            .group = group,
            .resource_kind = kind,
            .resource_handle = handle,
            .visibility = visibility,
            .buffer_offset = buffer_offset,
            .buffer_size = buffer_size,
            .buffer_type = parse_helpers.parseBufferBindingType(raw_binding.buffer_type orelse raw_binding.bufferType),
            .texture_sample_type = parse_helpers.parseTextureSampleType(raw_binding.texture_sample_type orelse raw_binding.textureSampleType),
            .texture_view_dimension = parse_helpers.parseTextureViewDimension(raw_binding.texture_view_dimension orelse raw_binding.textureViewDimension),
            .storage_texture_access = parse_helpers.parseStorageTextureAccess(raw_binding.storage_access orelse raw_binding.storageAccess),
            .texture_aspect = parse_helpers.parseTextureAspect(raw_binding.texture_aspect orelse raw_binding.textureAspect),
            .texture_format = if (raw_binding.texture_format orelse raw_binding.textureFormat) |raw_format|
                parse_helpers.parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload
            else
                model.WGPUTextureFormat_Undefined,
            .texture_multisampled = raw_binding.multisampled orelse false,
        });
    }

    return bindings.toOwnedSlice(allocator);
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
        const direction = parse_helpers.parseCopyDirection(raw.direction, getCommandName(raw)) catch return ParseError.InvalidCommandPayload;
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

    if (kind == .kernel_dispatch or kind == .dispatch or kind == .dispatch_indirect) {
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
                .warmup_dispatch_count = raw.warmup_dispatch_count orelse raw.warmupDispatchCount orelse 0,
                .initialize_buffers_on_create = raw.initialize_buffers_on_create orelse raw.initializeBuffersOnCreate orelse false,
                .bindings = kernel_bindings,
            } };
        }
        if (kind == .dispatch_indirect) {
            return .{ .dispatch_indirect = dispatch };
        }
        return .{ .dispatch = dispatch };
    }

    if (kind == .render_draw or kind == .draw_indirect or kind == .draw_indexed_indirect or kind == .render_pass) {
        const draw_count = raw.draw_count orelse raw.drawCount orelse return ParseError.InvalidCommandPayload;
        const vertex_count = raw.vertex_count orelse raw.vertexCount orelse 3;
        const instance_count = raw.instance_count orelse raw.instanceCount orelse 1;
        const first_vertex = raw.first_vertex orelse raw.firstVertex orelse 0;
        const first_instance = raw.first_instance orelse raw.firstInstance orelse 0;
        const parsed_index_count = raw.index_count orelse raw.indexCount;
        const is_draw_indexed = blk: {
            const command_name = getCommandName(raw) orelse break :blk false;
            break :blk commandKindEquals(command_name, "draw_indexed") or commandKindEquals(command_name, "draw_indexed_indirect");
        };
        const raw_index_data = raw.index_data orelse raw.indexData orelse raw.indices;
        const indexed_draw = is_draw_indexed or parsed_index_count != null or raw_index_data != null;
        const requested_index_format = parse_helpers.parseRenderIndexFormat(raw.index_format orelse raw.indexFormat) catch return ParseError.InvalidCommandPayload;
        const index_data = if (indexed_draw) blk: {
            const provided = raw_index_data orelse return ParseError.InvalidCommandPayload;
            if (provided.len == 0) return ParseError.InvalidCommandPayload;
            break :blk parse_helpers.parseRenderIndexData(allocator, provided, requested_index_format) catch return ParseError.InvalidCommandPayload;
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
            parse_helpers.parseTextureFormat(raw_format) catch return ParseError.InvalidCommandPayload
        else
            model.DEFAULT_RENDER_TARGET_FORMAT;
        const pipeline_mode = parse_helpers.parseRenderDrawPipelineMode(raw.pipeline_mode orelse raw.pipelineMode) catch return ParseError.InvalidCommandPayload;
        const bind_group_mode = parse_helpers.parseRenderDrawBindGroupMode(raw.bind_group_mode orelse raw.bindGroupMode) catch return ParseError.InvalidCommandPayload;
        const encode_mode = parse_extra.parseRenderDrawEncodeMode(raw.encode_mode orelse raw.encodeMode) catch return ParseError.InvalidCommandPayload;
        const viewport_x = raw.viewport_x orelse raw.viewportX orelse 0;
        const viewport_y = raw.viewport_y orelse raw.viewportY orelse 0;
        const viewport_width = raw.viewport_width orelse raw.viewportWidth;
        const viewport_height = raw.viewport_height orelse raw.viewportHeight;
        const viewport_min_depth = raw.viewport_min_depth orelse raw.viewportMinDepth orelse 0;
        const viewport_max_depth = raw.viewport_max_depth orelse raw.viewportMaxDepth orelse 1;
        const scissor_x = raw.scissor_x orelse raw.scissorX orelse 0;
        const scissor_y = raw.scissor_y orelse raw.scissorY orelse 0;
        const scissor_width = raw.scissor_width orelse raw.scissorWidth;
        const scissor_height = raw.scissor_height orelse raw.scissorHeight;
        const blend_r = raw.blend_r orelse raw.blendR orelse 0;
        const blend_g = raw.blend_g orelse raw.blendG orelse 0;
        const blend_b = raw.blend_b orelse raw.blendB orelse 0;
        const blend_a = raw.blend_a orelse raw.blendA orelse 0;
        const stencil_reference = raw.stencil_reference orelse raw.stencilReference orelse 0;
        const dynamic_offsets = if (raw.bind_group_dynamic_offsets orelse raw.bindGroupDynamicOffsets) |offsets| blk: {
            const copied = try allocator.alloc(u32, offsets.len);
            errdefer allocator.free(copied);
            @memcpy(copied, offsets);
            break :blk copied;
        } else null;
        errdefer if (dynamic_offsets) |offsets| allocator.free(offsets);

        if (draw_count == 0 or vertex_count == 0 or instance_count == 0 or target_width == 0 or target_height == 0) {
            return ParseError.InvalidCommandPayload;
        }
        if (viewport_min_depth < 0 or viewport_min_depth > 1 or viewport_max_depth < 0 or viewport_max_depth > 1 or viewport_max_depth < viewport_min_depth) {
            return ParseError.InvalidCommandPayload;
        }
        if (index_count != null and index_count.? == 0) return ParseError.InvalidCommandPayload;
        if (index_count != null) {
            const index_end = std.math.add(u32, first_index, index_count.?) catch return ParseError.InvalidCommandPayload;
            if (index_end > index_data_len_u32) return ParseError.InvalidCommandPayload;
        }

        const render_command: model.RenderDrawCommand = .{
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
            .encode_mode = encode_mode,
            .viewport_x = viewport_x,
            .viewport_y = viewport_y,
            .viewport_width = viewport_width,
            .viewport_height = viewport_height,
            .viewport_min_depth = viewport_min_depth,
            .viewport_max_depth = viewport_max_depth,
            .scissor_x = scissor_x,
            .scissor_y = scissor_y,
            .scissor_width = scissor_width,
            .scissor_height = scissor_height,
            .blend_constant = .{ blend_r, blend_g, blend_b, blend_a },
            .stencil_reference = stencil_reference,
            .bind_group_dynamic_offsets = dynamic_offsets,
        };
        return switch (kind) {
            .render_draw => .{ .render_draw = render_command },
            .draw_indirect => .{ .draw_indirect = render_command },
            .draw_indexed_indirect => .{ .draw_indexed_indirect = render_command },
            .render_pass => .{ .render_pass = render_command },
            else => unreachable,
        };
    }

    if (kind == .sampler_create) return .{ .sampler_create = parse_extra.parseSamplerCreateCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .sampler_destroy) return .{ .sampler_destroy = parse_extra.parseSamplerDestroyCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .texture_write) return .{ .texture_write = parse_extra.parseTextureWriteCommand(allocator, raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .texture_query) return .{ .texture_query = parse_extra.parseTextureQueryCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .texture_destroy) return .{ .texture_destroy = parse_extra.parseTextureDestroyCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .surface_create) return .{ .surface_create = parse_extra.parseSurfaceCreateCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .surface_capabilities) return .{ .surface_capabilities = parse_extra.parseSurfaceCapabilitiesCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .surface_configure) return .{ .surface_configure = parse_extra.parseSurfaceConfigureCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .surface_acquire) return .{ .surface_acquire = parse_extra.parseSurfaceAcquireCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .surface_present) return .{ .surface_present = parse_extra.parseSurfacePresentCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .surface_unconfigure) return .{ .surface_unconfigure = parse_extra.parseSurfaceUnconfigureCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .surface_release) return .{ .surface_release = parse_extra.parseSurfaceReleaseCommand(raw) catch return ParseError.InvalidCommandPayload };
    if (kind == .async_diagnostics) return .{ .async_diagnostics = parse_extra.parseAsyncDiagnosticsCommand(raw) catch return ParseError.InvalidCommandPayload };

    if (kind == .map_async) {
        if (raw.map_async) |m| return .{ .map_async = m };
        const bytes = raw.bytes orelse return ParseError.InvalidCommandPayload;
        const mode_str = raw.map_mode orelse raw.mapMode orelse "write";
        const mode: model.MapAsyncMode = if (std.mem.eql(u8, mode_str, "read")) .read else if (std.mem.eql(u8, mode_str, "write")) .write else return ParseError.InvalidCommandPayload;
        return .{ .map_async = .{ .bytes = bytes, .mode = mode } };
    }

    return ParseError.UnknownCommandKind;
}
