const std = @import("std");
const model = @import("model.zig");
const execution = @import("execution.zig");

pub const TraceState = struct {
    previous_hash: u64 = 0x9e3779b97f4a7c15,
};

pub const TraceRunSummary = struct {
    trace_version: u8,
    module_name: []const u8,
    seq_max: u64,
    row_count: u64,
    command_count: u64,
    matched_count: u64,
    blocking_count: u64,
    requires_lean_count: u64,
    lean_required_count: u64,
    execution_row_count: u64,
    execution_success_count: u64,
    execution_error_count: u64,
    execution_skipped_count: u64,
    execution_unsupported_count: u64,
    execution_total_ns: u64,
    execution_setup_total_ns: u64,
    execution_encode_total_ns: u64,
    execution_submit_wait_total_ns: u64,
    execution_dispatch_count: u64,
    execution_gpu_timestamp_total_ns: u64,
    execution_gpu_timestamp_attempted_count: u64,
    execution_gpu_timestamp_valid_count: u64,
    execution_backend: ?[]const u8,
    backend_selection_reason: ?[]const u8,
    fallback_used: ?bool,
    selection_policy_hash: ?[]const u8,
    shader_artifact_manifest_path: ?[]const u8,
    shader_artifact_manifest_hash: ?[]const u8,
    backend_lane: ?[]const u8,
    adapter_ordinal: ?u32 = null,
    queue_family_index: ?u32 = null,
    present_capable: ?bool = null,
    final_hash: u64,
    final_previous_hash: u64,
    profile_vendor: []const u8,
    profile_api: []const u8,
    profile_family: ?[]const u8,
    profile_driver: []const u8,
    queue_sync_mode: ?[]const u8 = null,
    quirk_mode: ?[]const u8 = null,
};

pub fn writef(writer: anytype, comptime format: []const u8, args: anytype) !void {
    try writer.print(format, args);
}

pub fn writeJsonString(writer: anytype, value: []const u8) !void {
    try writer.writeByte('"');
    for (value) |byte| {
        switch (byte) {
            '"' => try writer.writeAll("\\\""),
            '\\' => try writer.writeAll("\\\\"),
            '\n' => try writer.writeAll("\\n"),
            '\r' => try writer.writeAll("\\r"),
            '\t' => try writer.writeAll("\\t"),
            0...8, 11...12, 14...31 => {
                try writef(writer, "\\u00{x:0>2}", .{byte});
            },
            else => try writer.writeByte(byte),
        }
    }
    try writer.writeByte('"');
}

fn normalizeExecutionStatusCode(
    message: []const u8,
    fallback: []const u8,
    buffer: *[160]u8,
) []const u8 {
    const source = if (message.len > 0) message else fallback;
    var out_len: usize = 0;
    var last_was_separator = true;

    for (source) |byte| {
        const lower = std.ascii.toLower(byte);
        const is_alnum = (lower >= 'a' and lower <= 'z') or (lower >= '0' and lower <= '9');
        if (is_alnum) {
            if (out_len >= buffer.len) break;
            buffer[out_len] = lower;
            out_len += 1;
            last_was_separator = false;
            continue;
        }
        if (last_was_separator) continue;
        if (out_len >= buffer.len) break;
        buffer[out_len] = '_';
        out_len += 1;
        last_was_separator = true;
    }

    while (out_len > 0 and buffer[out_len - 1] == '_') {
        out_len -= 1;
    }

    if (out_len == 0) {
        const fallback_len = @min(fallback.len, buffer.len);
        std.mem.copyForwards(u8, buffer[0..fallback_len], fallback[0..fallback_len]);
        return buffer[0..fallback_len];
    }
    return buffer[0..out_len];
}

pub fn actionName(action: ?model.QuirkAction) []const u8 {
    const actual = action orelse return "none";
    return switch (actual) {
        .no_op => "no_op",
        .use_temporary_buffer => "use_temporary_buffer",
        .use_temporary_render_texture => "use_temporary_render_texture",
        .toggle => "toggle",
    };
}

pub fn scopeName(value: ?model.Scope) []const u8 {
    const scope = value orelse return "none";
    return model.scope_name(scope);
}

pub fn safetyClassName(value: ?model.SafetyClass) []const u8 {
    const safety = value orelse return "none";
    return model.safety_class_name(safety);
}

pub fn proofLevelName(value: ?model.ProofLevel) []const u8 {
    const proof = value orelse return "none";
    return model.proof_level_name(proof);
}

pub fn verificationModeName(value: ?model.VerificationMode) []const u8 {
    const mode = value orelse return "none";
    return model.verification_mode_name(mode);
}

pub fn apiName(value: model.Api) []const u8 {
    return switch (value) {
        .vulkan => "vulkan",
        .metal => "metal",
        .d3d12 => "d3d12",
        .webgpu => "webgpu",
    };
}

fn traceHashByte(value: u64, byte: u8) u64 {
    return (value ^ @as(u64, byte)) *% 1099511628211;
}

fn traceHashBytes(value: u64, bytes: []const u8) u64 {
    var state = value;
    for (bytes) |byte| {
        state = traceHashByte(state, byte);
    }
    return state;
}

fn traceHashU64(value: u64, input: u64) u64 {
    return traceHashBytes(value, std.mem.asBytes(&input));
}

fn traceHashBool(value: u64, input: bool) u64 {
    return traceHashByte(value, if (input) 1 else 0);
}

fn traceHashStr(value: u64, input: ?[]const u8) u64 {
    if (input) |text| {
        return traceHashBytes(value, text);
    }
    return traceHashByte(value, 0);
}

pub fn commandToTag(command: model.Command) []const u8 {
    return switch (command) {
        .upload => "upload",
        .copy_buffer_to_texture => "copy_buffer_to_texture",
        .barrier => "barrier",
        .dispatch => "dispatch",
        .dispatch_indirect => "dispatch_indirect",
        .kernel_dispatch => "kernel_dispatch",
        .render_draw => "render_draw",
        .draw_indirect => "draw_indirect",
        .draw_indexed_indirect => "draw_indexed_indirect",
        .render_pass => "render_pass",
        .sampler_create => "sampler_create",
        .sampler_destroy => "sampler_destroy",
        .texture_write => "texture_write",
        .texture_query => "texture_query",
        .texture_destroy => "texture_destroy",
        .surface_create => "surface_create",
        .surface_capabilities => "surface_capabilities",
        .surface_configure, .surface_acquire, .surface_present, .surface_unconfigure, .surface_release => "frame",
        .async_diagnostics => "diagnostics",
        .map_async => "sync",
    };
}

pub fn tracePayloadHash(
    state: TraceState,
    seq: usize,
    command_label: []const u8,
    command: model.Command,
    kernel_name: ?[]const u8,
    result: anytype,
) u64 {
    var next = state.previous_hash;
    next = traceHashU64(next, @as(u64, seq));
    next = traceHashStr(next, command_label);
    next = traceHashStr(next, commandToTag(command));
    next = traceHashStr(next, kernel_name);
    next = traceHashStr(next, result.decision.matched_quirk_id);
    next = traceHashStr(next, result.decision.applied_toggle);
    next = traceHashStr(next, scopeName(result.decision.matched_scope));
    next = traceHashStr(next, safetyClassName(result.decision.matched_safety_class));
    next = traceHashStr(next, verificationModeName(result.decision.verification_mode));
    next = traceHashStr(next, proofLevelName(result.decision.proof_level));
    next = traceHashStr(next, actionName(result.decision.action));
    next = traceHashU64(next, result.decision.score);
    next = traceHashU64(next, result.decision.matched_count);
    next = traceHashBool(next, result.decision.requires_lean);
    next = traceHashBool(next, result.decision.is_blocking);
    return next;
}

pub fn printTraceLine(
    stdout: anytype,
    seq: usize,
    command_label: []const u8,
    kernel_name: ?[]const u8,
    result: anytype,
    timestamp_ns: u64,
    hash: u64,
    previous_hash: u64,
    maybe_execution: ?execution.ExecutionResult,
) !void {
    try writef(
        stdout,
        "{{\"traceVersion\":1,\"module\":\"doe-zig-runtime\",\"opCode\":\"dispatch\",\"seq\":{},\"timestampMonoNs\":{},\"hash\":\"0x{x}\",\"previousHash\":\"0x{x}\",\"command\":",
        .{
            seq,
            timestamp_ns,
            hash,
            previous_hash,
        },
    );
    try writeJsonString(stdout, command_label);
    try stdout.writeByte(',');

    if (kernel_name) |kernel| {
        try stdout.writeAll("\"kernel\":");
        try writeJsonString(stdout, kernel);
        try stdout.writeByte(',');
    }

    if (result.decision.matched_quirk_id) |quirk| {
        try stdout.writeAll("\"matched\":");
        try writeJsonString(stdout, quirk);
        try stdout.writeByte(',');
    } else {
        try stdout.writeAll("\"matched\":null,");
    }

    try stdout.writeAll("\"scope\":");
    try writeJsonString(stdout, scopeName(result.decision.matched_scope));
    try stdout.writeAll(",\"safetyClass\":");
    try writeJsonString(stdout, safetyClassName(result.decision.matched_safety_class));
    try stdout.writeAll(",\"verificationMode\":");
    try writeJsonString(stdout, verificationModeName(result.decision.verification_mode));
    try stdout.writeAll(",\"proofLevel\":");
    try writeJsonString(stdout, proofLevelName(result.decision.proof_level));
    try writef(
        stdout,
        ",\"requiresLean\":{},\"blocking\":{},\"score\":{},\"matched_count\":{},\"action\":",
        .{
            result.decision.requires_lean,
            result.decision.is_blocking,
            result.decision.score,
            result.decision.matched_count,
        },
    );
    try writeJsonString(stdout, actionName(result.decision.action));
    try stdout.writeAll(",\"toggle\":");
    try writeJsonString(stdout, result.decision.applied_toggle orelse "none");

    if (maybe_execution) |exec| {
        var status_code_buffer: [160]u8 = undefined;
        const status_name = execution.executionStatusName(exec.status);
        const status_code = normalizeExecutionStatusCode(
            exec.status_code,
            status_name,
            &status_code_buffer,
        );
        try stdout.writeAll(",\"executionBackend\":");
        try writeJsonString(stdout, exec.backend);
        try stdout.writeAll(",\"backendId\":");
        try writeJsonString(stdout, exec.backend);
        try stdout.writeAll(",\"executionStatus\":");
        try writeJsonString(stdout, status_name);
        try stdout.writeAll(",\"executionStatusCode\":");
        try writeJsonString(stdout, status_code);
        try stdout.writeAll(",\"executionStatusMessage\":");
        try writeJsonString(stdout, exec.status_code);
        try writef(
            stdout,
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

    try writef(stdout, "}}\n", .{});
}

// --- Inline tests ---

test "traceHashByte is deterministic for same inputs" {
    const a = traceHashByte(0x9e3779b97f4a7c15, 42);
    const b = traceHashByte(0x9e3779b97f4a7c15, 42);
    try std.testing.expectEqual(a, b);
}

test "traceHashByte differs for different bytes" {
    const a = traceHashByte(0x9e3779b97f4a7c15, 0);
    const b = traceHashByte(0x9e3779b97f4a7c15, 1);
    try std.testing.expect(a != b);
}

test "traceHashBytes produces chained result matching sequential traceHashByte" {
    const input = "abc";
    const chained = traceHashBytes(0x9e3779b97f4a7c15, input);
    var manual: u64 = 0x9e3779b97f4a7c15;
    manual = traceHashByte(manual, 'a');
    manual = traceHashByte(manual, 'b');
    manual = traceHashByte(manual, 'c');
    try std.testing.expectEqual(manual, chained);
}

test "traceHashStr hashes null as single zero byte" {
    const from_null = traceHashStr(0x9e3779b97f4a7c15, null);
    const from_zero_byte = traceHashByte(0x9e3779b97f4a7c15, 0);
    try std.testing.expectEqual(from_zero_byte, from_null);
}

test "traceHashStr with value differs from null" {
    const from_null = traceHashStr(0x9e3779b97f4a7c15, null);
    const from_value = traceHashStr(0x9e3779b97f4a7c15, "hello");
    try std.testing.expect(from_null != from_value);
}

test "traceHashBool encodes true as 1 and false as 0" {
    const from_true = traceHashBool(0x9e3779b97f4a7c15, true);
    const from_false = traceHashBool(0x9e3779b97f4a7c15, false);
    const from_byte_1 = traceHashByte(0x9e3779b97f4a7c15, 1);
    const from_byte_0 = traceHashByte(0x9e3779b97f4a7c15, 0);
    try std.testing.expectEqual(from_byte_1, from_true);
    try std.testing.expectEqual(from_byte_0, from_false);
}

test "normalizeExecutionStatusCode lowercases and replaces non-alnum with underscores" {
    var buf: [160]u8 = undefined;
    const result = normalizeExecutionStatusCode("Hello World!", "fallback", &buf);
    try std.testing.expectEqualStrings("hello_world", result);
}

test "normalizeExecutionStatusCode collapses consecutive separators" {
    var buf: [160]u8 = undefined;
    const result = normalizeExecutionStatusCode("a---b", "fallback", &buf);
    try std.testing.expectEqualStrings("a_b", result);
}

test "normalizeExecutionStatusCode uses fallback when message is empty" {
    var buf: [160]u8 = undefined;
    const result = normalizeExecutionStatusCode("", "my_fallback", &buf);
    try std.testing.expectEqualStrings("my_fallback", result);
}

test "normalizeExecutionStatusCode strips trailing underscores" {
    var buf: [160]u8 = undefined;
    const result = normalizeExecutionStatusCode("trailing!!!", "fb", &buf);
    try std.testing.expectEqualStrings("trailing", result);
}

test "normalizeExecutionStatusCode returns fallback verbatim when all chars are separators" {
    var buf: [160]u8 = undefined;
    const result = normalizeExecutionStatusCode("!!!", "fallback_code", &buf);
    try std.testing.expectEqualStrings("fallback_code", result);
}

test "actionName returns correct strings for all variants and null" {
    try std.testing.expectEqualStrings("none", actionName(null));
    try std.testing.expectEqualStrings("no_op", actionName(.no_op));
    const toggle_action = model.QuirkAction{ .toggle = .{ .toggle_name = "test_toggle" } };
    try std.testing.expectEqualStrings("toggle", actionName(toggle_action));
}

test "scopeName returns none for null and correct name for values" {
    try std.testing.expectEqualStrings("none", scopeName(null));
    try std.testing.expectEqualStrings("barrier", scopeName(.barrier));
    try std.testing.expectEqualStrings("memory", scopeName(.memory));
}

test "safetyClassName returns none for null and correct name for values" {
    try std.testing.expectEqualStrings("none", safetyClassName(null));
    try std.testing.expectEqualStrings("critical", safetyClassName(.critical));
    try std.testing.expectEqualStrings("low", safetyClassName(.low));
}

test "verificationModeName returns none for null and correct name for values" {
    try std.testing.expectEqualStrings("none", verificationModeName(null));
    try std.testing.expectEqualStrings("lean_required", verificationModeName(.lean_required));
}

test "proofLevelName returns none for null and correct name for values" {
    try std.testing.expectEqualStrings("none", proofLevelName(null));
    try std.testing.expectEqualStrings("proven", proofLevelName(.proven));
    try std.testing.expectEqualStrings("rejected", proofLevelName(.rejected));
}

test "apiName returns correct string for each Api variant" {
    try std.testing.expectEqualStrings("vulkan", apiName(.vulkan));
    try std.testing.expectEqualStrings("metal", apiName(.metal));
    try std.testing.expectEqualStrings("d3d12", apiName(.d3d12));
    try std.testing.expectEqualStrings("webgpu", apiName(.webgpu));
}

test "commandToTag maps command variants to expected tags" {
    const upload_cmd = model.Command{ .upload = .{ .bytes = 0, .align_bytes = 0 } };
    try std.testing.expectEqualStrings("upload", commandToTag(upload_cmd));

    const barrier_cmd = model.Command{ .barrier = .{ .dependency_count = 1 } };
    try std.testing.expectEqualStrings("barrier", commandToTag(barrier_cmd));

    const diag_cmd = model.Command{ .async_diagnostics = .{} };
    try std.testing.expectEqualStrings("diagnostics", commandToTag(diag_cmd));

    const map_cmd = model.Command{ .map_async = .{ .bytes = 64 } };
    try std.testing.expectEqualStrings("sync", commandToTag(map_cmd));
}

test "writeJsonString escapes special characters correctly" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);
    const writer = fbs.writer();
    try writeJsonString(writer, "hello\"world\\end\nnew\ttab");
    const result = fbs.getWritten();
    try std.testing.expectEqualStrings("\"hello\\\"world\\\\end\\nnew\\ttab\"", result);
}

test "writeJsonString escapes control characters as unicode escapes" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);
    const writer = fbs.writer();
    try writeJsonString(writer, &[_]u8{0x01});
    const result = fbs.getWritten();
    try std.testing.expectEqualStrings("\"\\u0001\"", result);
}

test "TraceState default previous_hash is golden ratio constant" {
    const state = TraceState{};
    try std.testing.expectEqual(@as(u64, 0x9e3779b97f4a7c15), state.previous_hash);
}

pub fn writeTraceMeta(path: []const u8, summary: TraceRunSummary) !void {
    const file = try std.fs.cwd().createFile(path, .{});
    defer file.close();
    var writer = file.deprecatedWriter();

    try writef(writer, "{{\"traceVersion\":{},\"module\":", .{summary.trace_version});
    try writeJsonString(&writer, summary.module_name);
    try writef(writer, ",\"seqMax\":{},\"rowCount\":{},\"commandCount\":{},\"matchedCount\":{},\"blockingCount\":{},\"requiresLeanCount\":{},\"leanRequiredCount\":{},\"executionRowCount\":{},\"executionSuccessCount\":{},\"executionErrorCount\":{},\"executionSkippedCount\":{},\"executionUnsupportedCount\":{},\"executionTotalNs\":{},\"executionSetupTotalNs\":{},\"executionEncodeTotalNs\":{},\"executionSubmitWaitTotalNs\":{},\"executionDispatchCount\":{},\"executionGpuTimestampTotalNs\":{},\"executionGpuTimestampAttemptedCount\":{},\"executionGpuTimestampValidCount\":{},\"hash\":\"0x{x}\",\"previousHash\":\"0x{x}\",", .{
        summary.seq_max,
        summary.row_count,
        summary.command_count,
        summary.matched_count,
        summary.blocking_count,
        summary.requires_lean_count,
        summary.lean_required_count,
        summary.execution_row_count,
        summary.execution_success_count,
        summary.execution_error_count,
        summary.execution_skipped_count,
        summary.execution_unsupported_count,
        summary.execution_total_ns,
        summary.execution_setup_total_ns,
        summary.execution_encode_total_ns,
        summary.execution_submit_wait_total_ns,
        summary.execution_dispatch_count,
        summary.execution_gpu_timestamp_total_ns,
        summary.execution_gpu_timestamp_attempted_count,
        summary.execution_gpu_timestamp_valid_count,
        summary.final_hash,
        summary.final_previous_hash,
    });
    if (summary.execution_backend) |backend| {
        try writer.writeAll("\"executionBackend\":");
        try writeJsonString(&writer, backend);
        try writer.writeAll(",");
        try writer.writeAll("\"backendId\":");
        try writeJsonString(&writer, backend);
        try writer.writeAll(",");
    }
    if (summary.backend_selection_reason) |reason| {
        try writer.writeAll("\"backendSelectionReason\":");
        try writeJsonString(&writer, reason);
        try writer.writeAll(",");
    }
    if (summary.fallback_used) |fallback| {
        try writef(writer, "\"fallbackUsed\":{},", .{fallback});
    }
    if (summary.selection_policy_hash) |hash| {
        try writer.writeAll("\"selectionPolicyHash\":");
        try writeJsonString(&writer, hash);
        try writer.writeAll(",");
    }
    if (summary.shader_artifact_manifest_path) |manifest_path| {
        try writer.writeAll("\"shaderArtifactManifestPath\":");
        try writeJsonString(&writer, manifest_path);
        try writer.writeAll(",");
    }
    if (summary.shader_artifact_manifest_hash) |hash| {
        try writer.writeAll("\"shaderArtifactManifestHash\":");
        try writeJsonString(&writer, hash);
        try writer.writeAll(",");
    }
    if (summary.backend_lane) |lane| {
        try writer.writeAll("\"backendLane\":");
        try writeJsonString(&writer, lane);
        try writer.writeAll(",");
    }
    if (summary.adapter_ordinal) |ordinal| {
        try writef(writer, "\"adapterOrdinal\":{},", .{ordinal});
    }
    if (summary.queue_family_index) |queue_family_index| {
        try writef(writer, "\"queueFamilyIndex\":{},", .{queue_family_index});
    }
    if (summary.present_capable) |present_capable| {
        try writef(writer, "\"presentCapable\":{},", .{present_capable});
    }
    if (summary.queue_sync_mode) |sync_mode| {
        try writer.writeAll("\"queueSyncMode\":");
        try writeJsonString(&writer, sync_mode);
        try writer.writeAll(",");
    }
    if (summary.quirk_mode) |qmode| {
        try writer.writeAll("\"quirkMode\":");
        try writeJsonString(&writer, qmode);
        try writer.writeAll(",");
    }
    try writer.writeAll("\"profile\":{");
    try writer.writeAll("\"vendor\":");
    try writeJsonString(&writer, summary.profile_vendor);
    try writer.writeAll(",\"api\":");
    try writeJsonString(&writer, summary.profile_api);
    if (summary.profile_family) |family| {
        try writer.writeAll(",\"deviceFamily\":");
        try writeJsonString(&writer, family);
    } else {
        try writer.writeAll(",\"deviceFamily\":null");
    }
    try writer.writeAll(",\"driver\":");
    try writeJsonString(&writer, summary.profile_driver);
    try writer.writeAll("}}\n");
}
