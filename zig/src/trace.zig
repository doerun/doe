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
    final_hash: u64,
    final_previous_hash: u64,
    profile_vendor: []const u8,
    profile_api: []const u8,
    profile_family: ?[]const u8,
    profile_driver: []const u8,
    queue_sync_mode: ?[]const u8 = null,
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
        .kernel_dispatch => "kernel_dispatch",
        .render_draw => "render_draw",
        .sampler_create => "sampler_create",
        .sampler_destroy => "sampler_destroy",
        .texture_write => "texture_write",
        .texture_query => "texture_query",
        .texture_destroy => "texture_destroy",
        .surface_create => "surface_create",
        .surface_capabilities => "surface_capabilities",
        .surface_configure => "surface_configure",
        .surface_acquire => "surface_acquire",
        .surface_present => "surface_present",
        .surface_unconfigure => "surface_unconfigure",
        .surface_release => "surface_release",
        .async_diagnostics => "async_diagnostics",
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
    if (summary.shader_artifact_manifest_path) |path| {
        try writer.writeAll("\"shaderArtifactManifestPath\":");
        try writeJsonString(&writer, path);
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
    if (summary.queue_sync_mode) |sync_mode| {
        try writer.writeAll("\"queueSyncMode\":");
        try writeJsonString(&writer, sync_mode);
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
