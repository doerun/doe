const std = @import("std");
const execution = @import("execution.zig");
const quirk = @import("quirk/mod.zig");
const semantic_trace = @import("semantic_trace.zig");
const trace = @import("trace.zig");

const ESTIMATED_TRACE_ROW_BYTES: usize = 768;
const ESTIMATED_PLAN_TRACE_ROW_BYTES: usize = 384;
const FILE_WRITE_BUFFER_BYTES: usize = 64 * 1024;

pub const WriteTiming = struct {
    serialize_ns: u64 = 0,
    write_ns: u64 = 0,
};

pub const BufferedTraceRow = struct {
    seq: usize,
    command_label: []const u8,
    kernel_name: ?[]const u8,
    semantic: semantic_trace.SemanticContext,
    decision: quirk.runtime.DispatchDecision,
    timestamp_ns: u64,
    hash: u64,
    previous_hash: u64,
    execution_result: ?execution.ExecutionResult,
};

pub fn writeBufferedTraceRows(
    allocator: std.mem.Allocator,
    path: []const u8,
    rows: []const BufferedTraceRow,
) !WriteTiming {
    const file = try std.fs.cwd().createFile(path, .{ .truncate = true });
    defer file.close();
    var file_buffer: [FILE_WRITE_BUFFER_BYTES]u8 = undefined;
    var file_writer = file.writer(&file_buffer);
    var row_buffer = try std.ArrayList(u8).initCapacity(allocator, ESTIMATED_TRACE_ROW_BYTES);
    defer row_buffer.deinit(allocator);
    var timing = WriteTiming{};

    for (rows) |row| {
        row_buffer.clearRetainingCapacity();
        const serialize_start_ns = nowNs();
        try trace.printTraceLineWithSemantic(
            row_buffer.writer(allocator),
            row.seq,
            row.command_label,
            row.kernel_name,
            row.semantic,
            .{ .decision = row.decision },
            row.timestamp_ns,
            row.hash,
            row.previous_hash,
            row.execution_result,
        );
        timing.serialize_ns += elapsedSince(serialize_start_ns);
        const write_start_ns = nowNs();
        try file_writer.interface.writeAll(row_buffer.items);
        timing.write_ns += elapsedSince(write_start_ns);
    }
    const flush_start_ns = nowNs();
    try file_writer.end();
    timing.write_ns += elapsedSince(flush_start_ns);
    return timing;
}

pub fn writeBufferedPlanTraceRows(
    allocator: std.mem.Allocator,
    path: []const u8,
    module_name: []const u8,
    rows: []const BufferedTraceRow,
) !WriteTiming {
    const file = try std.fs.cwd().createFile(path, .{ .truncate = true });
    defer file.close();
    var file_buffer: [FILE_WRITE_BUFFER_BYTES]u8 = undefined;
    var file_writer = file.writer(&file_buffer);
    var row_buffer = try std.ArrayList(u8).initCapacity(allocator, ESTIMATED_PLAN_TRACE_ROW_BYTES);
    defer row_buffer.deinit(allocator);
    var timing = WriteTiming{};

    for (rows) |row| {
        row_buffer.clearRetainingCapacity();
        const serialize_start_ns = nowNs();
        try writePlanTraceRow(row_buffer.writer(allocator), module_name, row);
        timing.serialize_ns += elapsedSince(serialize_start_ns);
        const write_start_ns = nowNs();
        try file_writer.interface.writeAll(row_buffer.items);
        timing.write_ns += elapsedSince(write_start_ns);
    }
    const flush_start_ns = nowNs();
    try file_writer.end();
    timing.write_ns += elapsedSince(flush_start_ns);
    return timing;
}

fn writePlanTraceRow(
    writer: anytype,
    module_name: []const u8,
    row: BufferedTraceRow,
) !void {
    const exec = row.execution_result orelse return error.MissingExecutionResult;
    try writer.writeAll("{\"traceVersion\":1,\"module\":");
    try trace.writeJsonString(writer, module_name);
    try writer.writeAll(",\"opCode\":");
    try trace.writeJsonString(writer, row.command_label);
    try writer.print(
        ",\"seq\":{},\"timestampMonoNs\":{},\"hash\":\"0x{x}\",\"previousHash\":\"0x{x}\",\"command\":",
        .{ row.seq, row.timestamp_ns, row.hash, row.previous_hash },
    );
    try trace.writeJsonString(writer, row.command_label);

    if (row.kernel_name) |kernel_name| {
        try writer.writeAll(",\"kernel\":");
        try trace.writeJsonString(writer, kernel_name);
    }
    try writePlanSemanticFields(writer, row.semantic);
    try writePlanExecutionFields(writer, exec);
    try writer.writeAll("}\n");
}

fn writePlanSemanticFields(writer: anytype, semantic: semantic_trace.SemanticContext) !void {
    if (semantic.op_id) |value| {
        try writer.writeAll(",\"semanticOpId\":");
        try trace.writeJsonString(writer, value);
    }
    if (semantic.stage) |value| {
        try writer.writeAll(",\"semanticStage\":");
        try trace.writeJsonString(writer, value);
    }
    if (semantic.phase) |value| {
        try writer.writeAll(",\"semanticPhase\":");
        try trace.writeJsonString(writer, value);
    }
    if (semantic.token_index) |value| {
        try writer.print(",\"semanticTokenIndex\":{}", .{value});
    }
    if (semantic.layer_index) |value| {
        try writer.print(",\"semanticLayerIndex\":{}", .{value});
    }
    if (semantic.execution_plan_hash) |value| {
        try writer.writeAll(",\"semanticExecutionPlanHash\":");
        try trace.writeJsonString(writer, value);
    }
}

fn writePlanExecutionFields(writer: anytype, exec: execution.ExecutionResult) !void {
    const status_name = execution.executionStatusName(exec.status);
    const status_code = if (exec.status_code.len > 0) exec.status_code else status_name;
    try writer.writeAll(",\"executionBackend\":");
    try trace.writeJsonString(writer, exec.backend);
    try writer.writeAll(",\"backendId\":");
    try trace.writeJsonString(writer, exec.backend);
    if (exec.backend_lane) |value| {
        try writer.writeAll(",\"executionBackendLane\":");
        try trace.writeJsonString(writer, value);
    }
    try writer.writeAll(",\"executionStatus\":");
    try trace.writeJsonString(writer, status_name);
    try writer.writeAll(",\"executionStatusCode\":");
    try trace.writeJsonString(writer, status_code);
    try writer.writeAll(",\"executionStatusMessage\":");
    try trace.writeJsonString(writer, exec.status_code);
    try writer.print(
        ",\"executionDurationNs\":{},\"executionSetupNs\":{},\"executionEncodeNs\":{},\"executionSubmitWaitNs\":{},\"executionDispatchCount\":{},\"executionGpuTimestampNs\":{},\"executionGpuTimestampAttempted\":{},\"executionGpuTimestampValid\":{}",
        .{
            exec.duration_ns,
            exec.setup_ns,
            exec.encode_ns,
            exec.submit_wait_ns,
            exec.dispatch_count,
            exec.gpu_timestamp_ns,
            exec.gpu_timestamp_attempted,
            exec.gpu_timestamp_valid,
        },
    );
}

fn nowNs() u64 {
    return @as(u64, @intCast(std.time.nanoTimestamp()));
}

fn elapsedSince(start_ns: u64) u64 {
    return nowNs() - start_ns;
}
