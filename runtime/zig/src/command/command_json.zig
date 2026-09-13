const std = @import("std");
const model_commands = @import("../contracts/command.zig");
const model_async_types = @import("../contracts/model/model_async_types.zig");
const command_kind = @import("command_kind.zig");
const command_parse_copy = @import("command_parse_copy.zig");
const command_parse_dispatch = @import("command_parse_dispatch.zig");
const command_parse_render = @import("command_parse_render.zig");
const parse_extra = @import("command_json_extra.zig");

const Allocator = std.mem.Allocator;

const command_json_raw = @import("command_json_raw.zig");
const RawCommand = command_json_raw.RawCommand;
pub const ParseError = command_json_raw.ParseError;

const model = struct {
    pub const Command = model_commands.Command;
    pub const MapAsyncMode = model_async_types.MapAsyncMode;
};

pub fn parseCommands(allocator: Allocator, text: []const u8) ![]model.Command {
    if (std.mem.eql(u8, std.mem.trim(u8, text, " \n\r\t"), "[]")) {
        return &[_]model.Command{};
    }

    // Zig's strict parser crashes if the string has a trailing newline after the valid JSON array end.
    const cleanly_trimmed = std.mem.trimRight(u8, text, " \n\r\t\\n");
    var parsed = try std.json.parseFromSlice([]const RawCommand, allocator, cleanly_trimmed, .{
        .ignore_unknown_fields = true,
        .allocate = .alloc_always,
    });
    defer parsed.deinit();

    var list = std.ArrayList(model.Command).empty;
    errdefer {
        for (list.items) |command| {
            freeCommandPayload(allocator, command);
        }
        list.deinit(allocator);
    }
    try list.ensureTotalCapacity(allocator, parsed.value.len);

    for (parsed.value) |raw| {
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
            if (kernel_command.output_oracle) |oracle| {
                allocator.free(oracle.kind);
                allocator.free(oracle.initialization);
                allocator.free(oracle.expected_sha256);
                allocator.free(oracle.reference_id);
                if (oracle.reference_path) |path| allocator.free(path);
            }
        },
        .buffer_write => |buffer_write| allocator.free(buffer_write.data),
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
        .upload,
        .copy_buffer_to_texture,
        .barrier,
        .dispatch,
        .dispatch_indirect,
        .sampler_create,
        .sampler_destroy,
        .texture_query,
        .texture_destroy,
        .surface_create,
        .surface_capabilities,
        .surface_configure,
        .surface_acquire,
        .surface_present,
        .surface_unconfigure,
        .surface_release,
        .async_diagnostics,
        .map_async,
        => {},
    }
}

fn parseOne(allocator: Allocator, raw: RawCommand) !model.Command {
    const kind = try command_kind.parseKind(raw);
    return switch (kind) {
        .upload => blk: {
            const bytes = raw.bytes orelse return ParseError.InvalidCommandPayload;
            const align_bytes = raw.alignBytes orelse raw.alignmentBytes orelse 4;
            break :blk .{ .upload = .{ .bytes = bytes, .align_bytes = align_bytes } };
        },
        .buffer_write => blk: {
            const handle = raw.handle orelse raw.resource_handle orelse raw.resourceHandle orelse return ParseError.InvalidCommandPayload;
            const data = raw.data orelse return ParseError.InvalidCommandPayload;
            if (data.len == 0) return ParseError.InvalidCommandPayload;
            const owned_data = try allocator.dupe(u32, data);
            errdefer allocator.free(owned_data);
            break :blk .{ .buffer_write = .{
                .handle = handle,
                .offset = raw.offset orelse 0,
                .buffer_size = raw.buffer_size orelse raw.bufferSize orelse 0,
                .data = owned_data,
            } };
        },
        .copy_buffer_to_texture => command_parse_copy.parseCopyCommand(raw),
        .barrier => .{ .barrier = .{ .dependency_count = raw.dependency_count orelse raw.dependencyCount orelse 0 } },
        .kernel_dispatch, .dispatch, .dispatch_indirect => command_parse_dispatch.parseDispatchCommand(allocator, kind, raw),
        .render_draw, .draw_indirect, .draw_indexed_indirect, .render_pass => command_parse_render.parseRenderCommand(allocator, kind, raw),
        .sampler_create => .{ .sampler_create = try parse_extra.parseSamplerCreateCommand(raw) },
        .sampler_destroy => .{ .sampler_destroy = try parse_extra.parseSamplerDestroyCommand(raw) },
        .texture_write => .{ .texture_write = try parse_extra.parseTextureWriteCommand(allocator, raw) },
        .texture_query => .{ .texture_query = try parse_extra.parseTextureQueryCommand(raw) },
        .texture_destroy => .{ .texture_destroy = try parse_extra.parseTextureDestroyCommand(raw) },
        .surface_create => .{ .surface_create = try parse_extra.parseSurfaceCreateCommand(raw) },
        .surface_capabilities => .{ .surface_capabilities = try parse_extra.parseSurfaceCapabilitiesCommand(raw) },
        .surface_configure => .{ .surface_configure = try parse_extra.parseSurfaceConfigureCommand(raw) },
        .surface_acquire => .{ .surface_acquire = try parse_extra.parseSurfaceAcquireCommand(raw) },
        .surface_present => .{ .surface_present = try parse_extra.parseSurfacePresentCommand(raw) },
        .surface_unconfigure => .{ .surface_unconfigure = try parse_extra.parseSurfaceUnconfigureCommand(raw) },
        .surface_release => .{ .surface_release = try parse_extra.parseSurfaceReleaseCommand(raw) },
        .async_diagnostics => .{ .async_diagnostics = try parse_extra.parseAsyncDiagnosticsCommand(raw) },
        .map_async => blk: {
            if (raw.map_async) |m| break :blk .{ .map_async = m };
            const bytes = raw.bytes orelse return ParseError.InvalidCommandPayload;
            const mode_str = raw.map_mode orelse raw.mapMode orelse "write";
            const mode: model.MapAsyncMode = if (std.mem.eql(u8, mode_str, "read")) .read else if (std.mem.eql(u8, mode_str, "write")) .write else return ParseError.InvalidCommandPayload;
            break :blk .{ .map_async = .{ .bytes = bytes, .mode = mode } };
        },
    };
}

// --- inline tests ---
