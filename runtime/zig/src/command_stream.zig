const std = @import("std");
const model = @import("model.zig");
const command_json = @import("command_json.zig");
const command_json_raw = @import("command_json_raw.zig");
const semantic_trace = @import("semantic_trace.zig");

const RawCommand = command_json_raw.RawCommand;

pub const CommandMetadata = struct {
    semantic: semantic_trace.SemanticContext = .{},
    capture: ?semantic_trace.CaptureRequest = null,
};

pub const ParsedCommandStream = struct {
    commands: []model.Command,
    metadata: []CommandMetadata,

    pub fn deinit(self: ParsedCommandStream, allocator: std.mem.Allocator) void {
        command_json.freeCommands(allocator, self.commands);
        allocator.free(self.metadata);
    }
};

pub fn metadata_for_slice(
    allocator: std.mem.Allocator,
    commands: []const model.Command,
) ![]CommandMetadata {
    const metadata = try allocator.alloc(CommandMetadata, commands.len);
    @memset(metadata, .{});
    return metadata;
}

pub fn parse_command_stream(
    allocator: std.mem.Allocator,
    text: []const u8,
) anyerror!ParsedCommandStream {
    const commands = try command_json.parseCommands(allocator, text);
    errdefer command_json.freeCommands(allocator, commands);

    if (std.mem.eql(u8, std.mem.trim(u8, text, " \n\r\t"), "[]")) {
        return .{
            .commands = commands,
            .metadata = try metadata_for_slice(allocator, commands),
        };
    }

    const cleanly_trimmed = std.mem.trimRight(u8, text, " \n\r\t\\n");
    const raw = try std.json.parseFromSliceLeaky([]const RawCommand, allocator, cleanly_trimmed, .{
        .ignore_unknown_fields = true,
        .allocate = .alloc_always,
    });
    if (raw.len != commands.len) return error.InvalidCommandStream;

    const metadata = try allocator.alloc(CommandMetadata, raw.len);
    errdefer allocator.free(metadata);
    @memset(metadata, .{});

    for (raw, 0..) |entry, idx| {
        metadata[idx] = .{
            .semantic = .{
                .op_id = entry.semantic_op_id orelse entry.semanticOpId,
                .stage = entry.semantic_stage orelse entry.semanticStage,
                .phase = entry.semantic_phase orelse entry.semanticPhase,
                .token_index = entry.semantic_token_index orelse entry.semanticTokenIndex,
                .layer_index = entry.semantic_layer_index orelse entry.semanticLayerIndex,
                .execution_plan_hash = entry.semantic_execution_plan_hash orelse entry.semanticExecutionPlanHash,
            },
            .capture = parse_capture(entry),
        };
    }

    return .{
        .commands = commands,
        .metadata = metadata,
    };
}

fn parse_capture(raw: RawCommand) ?semantic_trace.CaptureRequest {
    const handle = raw.capture_buffer_handle orelse raw.captureBufferHandle orelse return null;
    const size = raw.capture_size orelse raw.captureSize orelse return null;
    if (size == 0) return null;
    return .{
        .buffer_handle = handle,
        .offset = raw.capture_offset orelse raw.captureOffset orelse 0,
        .size = size,
    };
}
