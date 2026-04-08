const std = @import("std");
const model_commands = @import("model_commands.zig");
const model_policy = @import("model_policy.zig");
const model_profile = @import("model_profile.zig");
const quirk = @import("quirk/mod.zig");
const command_stream = @import("command_stream.zig");
const execution = @import("execution.zig");
const operator_artifacts = @import("operator_artifacts.zig");
const semantic_trace = @import("semantic_trace.zig");
const trace = @import("trace.zig");
const trace_jsonl_emit = @import("trace_jsonl_emit.zig");
const replay = @import("replay.zig");
const main_print = @import("main_print.zig");
const main_usage = @import("main_usage.zig");
const numeric_stability_runtime = @import("numeric_stability_runtime.zig");
const lean_proof = @import("lean_proof.zig");

const model = struct {
    pub const Command = model_commands.Command;
    pub const DeviceProfile = model_profile.DeviceProfile;
    pub const SemVer = model_profile.SemVer;
    pub const parse_api = model_policy.parse_api;
};

const sample_quirks =
    \\[
    \\  {
    \\    "schemaVersion": 2,
    \\    "quirkId": "vulkan.intel.gen12.use_temp_buffer_compressed_copy",
    \\    "scope": "memory",
    \\    "match": {
    \\      "vendor": "intel",
    \\      "deviceFamily": "gen12",
    \\      "driverRange": ">=31.0.101,<32.0.0",
    \\      "api": "vulkan"
    \\    },
    \\    "action": {
    \\      "kind": "use_temporary_buffer",
    \\      "params": {
    \\        "bufferAlignmentBytes": 4
    \\      }
    \\    },
    \\    "safetyClass": "high",
    \\    "verificationMode": "lean_preferred",
    \\    "proofLevel": "guarded",
    \\    "provenance": {
    \\      "sourceRepo": "dawn",
    \\      "sourcePath": "src/dawn/native/Toggles.cpp",
    \\      "sourceCommit": "example",
    \\      "observedAt": "2026-02-17T00:00:00Z"
    \\    }
    \\  }
    \\]
;

const default_commands = [_]model.Command{
    .{ .copy_buffer_to_texture = .{ .direction = .buffer_to_texture, .src = .{ .handle = 0x1000 }, .dst = .{ .handle = 0x2000 }, .bytes = 4096 } },
    .{ .upload = .{ .bytes = 4096, .align_bytes = 4 } },
    .{ .buffer_write = .{ .handle = 0x3000, .buffer_size = 16, .data = @constCast(&[_]u32{ 1, 2, 3, 4 }) } },
    .{ .kernel_dispatch = .{ .kernel = "bench/kernels/shader_compile_pipeline_stress.wgsl", .x = 2, .y = 1, .z = 1 } },
    .{ .barrier = .{ .dependency_count = 3 } },
};

fn printUsage(stdout: anytype) !void {
    try main_usage.printUsage(stdout);
}

fn readFileAlloc(allocator: std.mem.Allocator, path: []const u8) ![]const u8 {
    const file = try std.fs.cwd().openFile(path, .{});
    defer file.close();
    return try file.readToEndAlloc(allocator, 16 * 1024 * 1024);
}

fn nowNs() u64 {
    return @as(u64, @intCast(std.time.nanoTimestamp()));
}

fn elapsedSince(start_ns: u64) u64 {
    return nowNs() - start_ns;
}

fn optionExpectsValue(option: []const u8) bool {
    return std.mem.eql(u8, option, "--quirks") or
        std.mem.eql(u8, option, "--commands") or
        std.mem.eql(u8, option, "--command-repeat") or
        std.mem.eql(u8, option, "--quirk-mode") or
        std.mem.eql(u8, option, "--vendor") or
        std.mem.eql(u8, option, "--api") or
        std.mem.eql(u8, option, "--family") or
        std.mem.eql(u8, option, "--driver") or
        std.mem.eql(u8, option, "--trace-jsonl") or
        std.mem.eql(u8, option, "--trace-meta") or
        std.mem.eql(u8, option, "--numeric-stability-policy") or
        std.mem.eql(u8, option, "--numeric-stability-execution-profile") or
        std.mem.eql(u8, option, "--kernel-root") or
        std.mem.eql(u8, option, "--backend") or
        std.mem.eql(u8, option, "--backend-lane") or
        std.mem.eql(u8, option, "--upload-buffer-usage") or
        std.mem.eql(u8, option, "--upload-submit-every") or
        std.mem.eql(u8, option, "--gpu-timestamp-mode") or
        std.mem.eql(u8, option, "--queue-wait-mode") or
        std.mem.eql(u8, option, "--queue-sync-mode") or
        std.mem.eql(u8, option, "--replay");
}

fn maxUploadBytes(commands: []const model.Command) u64 {
    var max_bytes: u64 = 0;
    for (commands) |command| {
        switch (command) {
            .upload => |upload| {
                if (upload.bytes > max_bytes) {
                    max_bytes = upload.bytes;
                }
            },
            .buffer_write => |buffer_write| {
                const bytes = std.mem.sliceAsBytes(buffer_write.data).len;
                if (bytes > max_bytes) max_bytes = bytes;
            },
            else => {},
        }
    }
    return max_bytes;
}

fn operator_artifact_anchor(trace_meta_path: ?[]const u8, trace_jsonl_path: ?[]const u8) ?[]const u8 {
    return trace_meta_path orelse trace_jsonl_path;
}

fn prewarmKernelDispatches(ctx: *execution.ExecutionContext, commands: []const model.Command) void {
    for (commands) |command| {
        switch (command) {
            .kernel_dispatch => |kd| {
                ctx.prewarmKernelDispatch(kd.kernel, kd.bindings) catch |err| {
                    std.debug.print("warn: main: kernel dispatch prewarm: {s}\n", .{@errorName(err)});
                };
            },
            else => {},
        }
    }
}

const BufferedTraceRow = trace_jsonl_emit.BufferedTraceRow;

fn executionRowTotalNs(executed: execution.ExecutionResult) u64 {
    const component_total_ns = executed.setup_ns +| executed.encode_ns +| executed.submit_wait_ns;
    if (component_total_ns > 0) {
        return @max(executed.duration_ns, component_total_ns);
    }
    return executed.duration_ns;
}

pub fn main() !void {
    const allocator = std.heap.page_allocator;
    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    const stdout = std.fs.File.stdout().deprecatedWriter();

    var quirks_text: ?[]const u8 = null;
    var commands_text: ?[]const u8 = null;
    var quirk_mode: quirk.QuirkMode = .trace;
    var profile_vendor: []const u8 = "intel";
    var profile_api: []const u8 = "vulkan";
    var profile_family: ?[]const u8 = "gen12";
    var profile_driver: []const u8 = "31.0.101";
    var emit_trace = false;
    var emit_trace_jsonl: ?[]const u8 = null;
    var emit_normalized = false;
    var trace_meta_path: ?[]const u8 = null;
    var numeric_stability_policy_path: ?[]const u8 = null;
    var numeric_stability_execution_profile_id: ?[]const u8 = null;
    var replay_path: ?[]const u8 = null;
    var execute = false;
    var backend_mode: execution.BackendMode = .trace;
    var backend_lane_value: ?[]const u8 = null;
    var kernel_root: ?[]const u8 = null;
    var command_repeat: u32 = 1;
    var upload_buffer_usage_mode: execution.UploadBufferUsageMode = .copy_dst_copy_src;
    var upload_submit_every: u32 = 1;
    var gpu_timestamp_mode: execution.GpuTimestampMode = .auto;
    var queue_wait_mode: execution.QueueWaitMode = .process_events;
    var queue_sync_mode: execution.QueueSyncMode = .per_command;
    var host_input_read_total_ns: u64 = 0;
    var host_input_parse_total_ns: u64 = 0;
    var host_workload_prepare_total_ns: u64 = 0;
    var host_executor_init_total_ns: u64 = 0;
    var host_upload_prewarm_total_ns: u64 = 0;
    var host_kernel_prewarm_total_ns: u64 = 0;
    var host_command_orchestration_total_ns: u64 = 0;
    var host_artifact_finalize_total_ns: u64 = 0;
    var host_artifact_trace_jsonl_serialize_total_ns: u64 = 0;
    var host_artifact_trace_jsonl_write_total_ns: u64 = 0;
    var host_artifact_operator_manifest_finalize_total_ns: u64 = 0;

    var i: usize = 1;
    while (i < argv.len) {
        if (std.mem.eql(u8, argv[i], "--quirks") and i + 1 < argv.len) {
            i += 1;
            quirks_text = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--commands") and i + 1 < argv.len) {
            i += 1;
            commands_text = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--quirk-mode") and i + 1 < argv.len) {
            i += 1;
            if (quirk.QuirkMode.parse(argv[i])) |mode| {
                quirk_mode = mode;
            } else {
                try trace.writef(stdout, "invalid --quirk-mode value: {s} (expected off|trace|active)\n", .{argv[i]});
                return;
            }
        } else if (std.mem.eql(u8, argv[i], "--vendor") and i + 1 < argv.len) {
            i += 1;
            profile_vendor = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--api") and i + 1 < argv.len) {
            i += 1;
            profile_api = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--family") and i + 1 < argv.len) {
            i += 1;
            profile_family = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--driver") and i + 1 < argv.len) {
            i += 1;
            profile_driver = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--trace")) {
            emit_trace = true;
        } else if (std.mem.eql(u8, argv[i], "--trace-jsonl") and i + 1 < argv.len) {
            i += 1;
            emit_trace_jsonl = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--emit-normalized")) {
            emit_normalized = true;
        } else if (std.mem.eql(u8, argv[i], "--trace-meta") and i + 1 < argv.len) {
            i += 1;
            trace_meta_path = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--numeric-stability-policy") and i + 1 < argv.len) {
            i += 1;
            numeric_stability_policy_path = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--numeric-stability-execution-profile") and i + 1 < argv.len) {
            i += 1;
            numeric_stability_execution_profile_id = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--kernel-root") and i + 1 < argv.len) {
            i += 1;
            kernel_root = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--backend") and i + 1 < argv.len) {
            i += 1;
            if (execution.parseBackend(argv[i])) |mode| {
                backend_mode = mode;
            } else {
                try trace.writef(stdout, "invalid --backend value: {s}\n", .{argv[i]});
                return;
            }
        } else if (std.mem.eql(u8, argv[i], "--backend-lane") and i + 1 < argv.len) {
            i += 1;
            backend_lane_value = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--command-repeat") and i + 1 < argv.len) {
            i += 1;
            const parsed = std.fmt.parseInt(u32, argv[i], 10) catch {
                try trace.writef(stdout, "invalid --command-repeat value: {s}\n", .{argv[i]});
                return;
            };
            if (parsed == 0) {
                try trace.writef(stdout, "invalid --command-repeat value: must be >= 1\n", .{});
                return;
            }
            command_repeat = parsed;
        } else if (std.mem.eql(u8, argv[i], "--upload-buffer-usage") and i + 1 < argv.len) {
            i += 1;
            if (execution.parseUploadBufferUsage(argv[i])) |mode| {
                upload_buffer_usage_mode = mode;
            } else {
                try trace.writef(
                    stdout,
                    "invalid --upload-buffer-usage value: {s} (expected copy-dst-copy-src|copy-dst)\n",
                    .{argv[i]},
                );
                return;
            }
        } else if (std.mem.eql(u8, argv[i], "--upload-submit-every") and i + 1 < argv.len) {
            i += 1;
            const parsed = std.fmt.parseInt(u32, argv[i], 10) catch {
                try trace.writef(stdout, "invalid --upload-submit-every value: {s}\n", .{argv[i]});
                return;
            };
            if (parsed == 0) {
                try trace.writef(stdout, "invalid --upload-submit-every value: must be >= 1\n", .{});
                return;
            }
            upload_submit_every = parsed;
        } else if (std.mem.eql(u8, argv[i], "--gpu-timestamp-mode") and i + 1 < argv.len) {
            i += 1;
            if (execution.parseGpuTimestampMode(argv[i])) |mode| {
                gpu_timestamp_mode = mode;
            } else {
                try trace.writef(
                    stdout,
                    "invalid --gpu-timestamp-mode value: {s} (expected auto|off|require)\n",
                    .{argv[i]},
                );
                return;
            }
        } else if (std.mem.eql(u8, argv[i], "--queue-wait-mode") and i + 1 < argv.len) {
            i += 1;
            if (execution.parseQueueWaitMode(argv[i])) |mode| {
                queue_wait_mode = mode;
            } else {
                try trace.writef(
                    stdout,
                    "invalid --queue-wait-mode value: {s} (expected process-events|wait-any)\n",
                    .{argv[i]},
                );
                return;
            }
        } else if (std.mem.eql(u8, argv[i], "--queue-sync-mode") and i + 1 < argv.len) {
            i += 1;
            if (execution.parseQueueSyncMode(argv[i])) |mode| {
                queue_sync_mode = mode;
            } else {
                try trace.writef(
                    stdout,
                    "invalid --queue-sync-mode value: {s} (expected per-command|deferred)\n",
                    .{argv[i]},
                );
                return;
            }
        } else if (std.mem.eql(u8, argv[i], "--execute")) {
            execute = true;
        } else if (std.mem.eql(u8, argv[i], "--replay") and i + 1 < argv.len) {
            i += 1;
            replay_path = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--help")) {
            try printUsage(stdout);
            return;
        } else if (optionExpectsValue(argv[i])) {
            try trace.writef(stdout, "missing value for option: {s}\n", .{argv[i]});
            try printUsage(stdout);
            return;
        } else if (std.mem.startsWith(u8, argv[i], "--")) {
            try trace.writef(stdout, "unknown option: {s}\n", .{argv[i]});
            try printUsage(stdout);
            return;
        } else {
            try trace.writef(stdout, "unexpected positional argument: {s}\n", .{argv[i]});
            try printUsage(stdout);
            return;
        }
        i += 1;
    }

    const quirks_read_start_ns = nowNs();
    const quirks_bytes = if (quirk_mode.loadsQuirks())
        (if (quirks_text) |path| try readFileAlloc(allocator, path) else sample_quirks)
    else
        "[]";
    host_input_read_total_ns += elapsedSince(quirks_read_start_ns);
    const using_quarks_from_file = quirks_text != null and quirk_mode.loadsQuirks();

    const quirks_parse_start_ns = nowNs();
    const quirks = try quirk.parser.parseQuirks(allocator, quirks_bytes);
    host_input_parse_total_ns += elapsedSince(quirks_parse_start_ns);
    defer {
        if (using_quarks_from_file) allocator.free(quirks_bytes);
        quirk.parser.freeQuirks(allocator, quirks);
    }
    var replay_expectations: ?[]replay.ReplayExpectation = null;
    if (replay_path) |path| {
        const replay_parse_start_ns = nowNs();
        replay_expectations = try replay.loadReplayExpectations(allocator, path);
        host_input_parse_total_ns += elapsedSince(replay_parse_start_ns);
    }
    defer if (replay_expectations) |expectations| replay.freeReplayExpectations(allocator, expectations);
    var commands: []const model.Command = default_commands[0..];
    const default_metadata_start_ns = nowNs();
    var command_metadata: []command_stream.CommandMetadata = try command_stream.metadata_for_slice(allocator, commands);
    host_input_parse_total_ns += elapsedSince(default_metadata_start_ns);
    var owned_stream: ?command_stream.ParsedCommandStream = null;

    if (commands_text) |commands_path| {
        const commands_read_start_ns = nowNs();
        const commands_bytes = try readFileAlloc(allocator, commands_path);
        host_input_read_total_ns += elapsedSince(commands_read_start_ns);
        defer allocator.free(commands_bytes);
        const commands_parse_start_ns = nowNs();
        const parsed_stream = try command_stream.parse_command_stream(allocator, commands_bytes);
        host_input_parse_total_ns += elapsedSince(commands_parse_start_ns);
        commands = parsed_stream.commands;
        allocator.free(command_metadata);
        command_metadata = parsed_stream.metadata;
        owned_stream = parsed_stream;
    }
    defer {
        if (owned_stream) |parsed_stream| {
            parsed_stream.deinit(allocator);
        } else {
            allocator.free(command_metadata);
        }
    }

    const command_repeat_usize = std.math.cast(usize, command_repeat) orelse {
        try trace.writef(stdout, "invalid --command-repeat value: {d}\n", .{command_repeat});
        return;
    };
    const physical_command_count = std.math.mul(u64, @as(u64, @intCast(commands.len)), @as(u64, command_repeat)) catch {
        try trace.writef(stdout, "invalid --command-repeat value: physical command count overflow\n", .{});
        return;
    };
    const physical_command_count_usize = std.math.cast(usize, physical_command_count) orelse {
        try trace.writef(stdout, "invalid --command-repeat value: physical command count overflow\n", .{});
        return;
    };

    var requires_numeric_stability = false;
    for (command_metadata) |metadata| {
        if (metadata.numeric_stability != null) {
            requires_numeric_stability = true;
            break;
        }
    }
    if (requires_numeric_stability and command_repeat > 1) {
        try trace.writef(stdout, "numeric-stability annotations do not support --command-repeat > 1\n", .{});
        return;
    }
    if (requires_numeric_stability and !execute) {
        try trace.writef(stdout, "numeric-stability annotations require --execute\n", .{});
        return;
    }
    if (requires_numeric_stability and backend_mode != .native) {
        try trace.writef(stdout, "numeric-stability annotations require --backend native\n", .{});
        return;
    }
    if (requires_numeric_stability and trace_meta_path == null) {
        try trace.writef(stdout, "numeric-stability annotations require --trace-meta\n", .{});
        return;
    }

    const profile_prepare_start_ns = nowNs();
    const profile = model.DeviceProfile{
        .vendor = profile_vendor,
        .api = try model.parse_api(profile_api),
        .device_family = profile_family,
        .driver_version = try model.SemVer.parse(profile_driver),
    };
    host_workload_prepare_total_ns += elapsedSince(profile_prepare_start_ns);

    const backend_lane = if (backend_lane_value) |raw_lane| blk: {
        if (execution.parseBackendLane(raw_lane)) |lane| {
            break :blk lane;
        }
        try trace.writef(stdout, "invalid --backend-lane value: {s}\n", .{raw_lane});
        return;
    } else execution.defaultBackendLane(profile);

    if (emit_normalized) {
        var repeat_idx: usize = 0;
        var normalized_idx: usize = 0;
        while (repeat_idx < command_repeat_usize) : (repeat_idx += 1) {
            var command_idx: usize = 0;
            while (command_idx < commands.len) : (command_idx += 1) {
                try main_print.printNormalizedCommand(stdout, normalized_idx, commands[command_idx]);
                normalized_idx += 1;
            }
        }
        return;
    }

    const dispatch_context_start_ns = nowNs();
    var dispatch_context = try quirk.runtime.buildProfileDispatchContext(allocator, profile, quirks);
    host_workload_prepare_total_ns += elapsedSince(dispatch_context_start_ns);
    defer dispatch_context.deinit();
    var trace_state = trace.TraceState{};

    if (execute and backend_mode == .trace) {
        try trace.writef(stdout, "cannot execute with backend=trace. use --backend native\n", .{});
        return;
    }

    var execution_context: ?execution.ExecutionContext = null;
    if (execute) {
        const executor_init_start_ns = nowNs();
        execution_context = try execution.ExecutionContext.init(allocator, backend_mode, profile, kernel_root, backend_lane);
        if (execution_context) |*ctx| {
            ctx.configureUploadBehavior(upload_buffer_usage_mode, upload_submit_every);
            ctx.configureGpuTimestampMode(gpu_timestamp_mode);
            ctx.configureQueueWaitMode(queue_wait_mode);
            ctx.configureQueueSyncMode(queue_sync_mode);
            host_executor_init_total_ns += elapsedSince(executor_init_start_ns);
            const max_upload_bytes = maxUploadBytes(commands);
            if (max_upload_bytes > 0) {
                const upload_prewarm_start_ns = nowNs();
                try ctx.prewarmUploadPath(max_upload_bytes);
                host_upload_prewarm_total_ns += elapsedSince(upload_prewarm_start_ns);
            }
            const kernel_prewarm_start_ns = nowNs();
            prewarmKernelDispatches(ctx, commands);
            host_kernel_prewarm_total_ns += elapsedSince(kernel_prewarm_start_ns);
        } else {
            host_executor_init_total_ns += elapsedSince(executor_init_start_ns);
        }
    }
    defer {
        if (execution_context) |*ctx| {
            ctx.deinit();
        }
    }

    const compact_upload_trace = blk: {
        if (emit_trace) break :blk false;
        if (emit_trace_jsonl == null) break :blk false;
        if (replay_expectations != null) break :blk false;
        if (physical_command_count_usize <= 1) break :blk false;
        for (commands) |command| {
            switch (command) {
                .upload => {},
                else => break :blk false,
            }
        }
        break :blk true;
    };

    var compact_upload_trace_row_totals: ?std.ArrayList(u64) = null;
    if (compact_upload_trace) {
        compact_upload_trace_row_totals = try std.ArrayList(u64).initCapacity(allocator, physical_command_count_usize);
    }
    defer if (compact_upload_trace_row_totals) |*rows| rows.deinit(allocator);

    var buffered_trace_rows: ?std.ArrayList(BufferedTraceRow) = null;
    if (emit_trace_jsonl != null and !compact_upload_trace) {
        buffered_trace_rows = try std.ArrayList(BufferedTraceRow).initCapacity(allocator, 0);
    }
    defer if (buffered_trace_rows) |*rows| rows.deinit(allocator);

    var artifact_recorder = try operator_artifacts.Recorder.init(
        allocator,
        operator_artifact_anchor(trace_meta_path, emit_trace_jsonl),
    );
    defer artifact_recorder.deinit();
    var numeric_stability_recorder = try numeric_stability_runtime.Recorder.init(
        allocator,
        trace_meta_path,
        numeric_stability_policy_path,
        numeric_stability_execution_profile_id,
    );
    defer numeric_stability_recorder.deinit();

    var trace_summary = trace.TraceRunSummary{
        .trace_version = 1,
        .module_name = "doe-zig-runtime",
        .seq_max = 0,
        .row_count = 0,
        .command_count = @intCast(physical_command_count),
        .matched_count = 0,
        .blocking_count = 0,
        .requires_lean_count = 0,
        .lean_required_count = 0,
        .execution_row_count = 0,
        .execution_success_count = 0,
        .execution_error_count = 0,
        .execution_skipped_count = 0,
        .execution_unsupported_count = 0,
        .execution_total_ns = 0,
        .execution_setup_total_ns = 0,
        .execution_encode_total_ns = 0,
        .execution_submit_wait_total_ns = 0,
        .execution_dispatch_count = 0,
        .host_input_read_total_ns = host_input_read_total_ns,
        .host_input_parse_total_ns = host_input_parse_total_ns,
        .host_workload_prepare_total_ns = host_workload_prepare_total_ns,
        .host_executor_init_total_ns = host_executor_init_total_ns,
        .host_upload_prewarm_total_ns = host_upload_prewarm_total_ns,
        .host_kernel_prewarm_total_ns = host_kernel_prewarm_total_ns,
        .execution_gpu_timestamp_total_ns = 0,
        .execution_gpu_timestamp_attempted_count = 0,
        .execution_gpu_timestamp_valid_count = 0,
        .execution_backend = null,
        .final_hash = trace_state.previous_hash,
        .final_previous_hash = trace_state.previous_hash,
        .profile_vendor = profile_vendor,
        .profile_api = trace.apiName(profile.api),
        .profile_family = profile_family,
        .profile_driver = profile_driver,
        .backend_selection_reason = null,
        .fallback_used = null,
        .selection_policy_hash = null,
        .shader_artifact_manifest_path = null,
        .shader_artifact_manifest_hash = null,
        .host_plan_artifact_path = null,
        .host_plan_artifact_hash = null,
        .semantic_tracing_enabled = false,
        .semantic_op_row_count = 0,
        .semantic_capture_count = 0,
        .semantic_repro_count = 0,
        .operator_record_manifest_path = null,
        .operator_record_manifest_hash = null,
        .backend_lane = execution.backendLaneName(backend_lane),
        .adapter_ordinal = null,
        .queue_family_index = null,
        .present_capable = null,
        .queue_sync_mode = if (execution_context != null)
            switch (queue_sync_mode) {
                .per_command => "per-command",
                .deferred => "deferred",
            }
        else
            null,
        .quirk_mode = quirk_mode.name(),
    };

    if (execution_context) |*ctx| {
        if (ctx.telemetry()) |selection| {
            trace_summary.execution_backend = execution.backend_id_name(selection.backend_id);
            trace_summary.backend_selection_reason = selection.backend_selection_reason;
            trace_summary.fallback_used = selection.fallback_used;
            trace_summary.selection_policy_hash = selection.selection_policy_hash;
            trace_summary.shader_artifact_manifest_path = selection.shader_artifact_manifest_path;
            trace_summary.shader_artifact_manifest_hash = selection.shader_artifact_manifest_hash;
            trace_summary.host_plan_artifact_path = selection.host_plan_artifact_path;
            trace_summary.host_plan_artifact_hash = selection.host_plan_artifact_hash;
        }
    }

    const command_loop_start_ns = nowNs();
    var repeat_idx: usize = 0;
    var physical_idx: usize = 0;
    command_loop: while (repeat_idx < command_repeat_usize) : (repeat_idx += 1) {
        var idx: usize = 0;
        while (idx < commands.len) : (idx += 1) {
            const command = commands[idx];
            const metadata = command_metadata[idx];
            const physical_command_index = physical_idx;
            physical_idx += 1;
            if (metadata.semantic.present()) {
                trace_summary.semantic_tracing_enabled = true;
            }
            const result = quirk.dispatchWithMode(quirk_mode, profile, dispatch_context, command);
            const target = result.command;
            const kernel_name = main_print.commandKernel(target);
            const command_label = main_print.commandName(target);
            const timestamp_ns: u64 = @intCast(std.time.nanoTimestamp());
            var execute_result: ?execution.ExecutionResult = null;
            const emit_trace_payload = emit_trace or (buffered_trace_rows != null) or (trace_meta_path != null) or (replay_expectations != null);

            if (execution_context) |*ctx| {
                const executed = try ctx.execute_with_semantic(target, metadata.semantic);
                execute_result = executed;
                trace_summary.execution_row_count += 1;
                trace_summary.execution_total_ns += executed.duration_ns;
                trace_summary.execution_setup_total_ns += executed.setup_ns;
                trace_summary.execution_encode_total_ns += executed.encode_ns;
                trace_summary.execution_submit_wait_total_ns += executed.submit_wait_ns;
                trace_summary.execution_dispatch_count += @as(u64, executed.dispatch_count);
                trace_summary.execution_gpu_timestamp_total_ns += executed.gpu_timestamp_ns;
                if (executed.gpu_timestamp_attempted) trace_summary.execution_gpu_timestamp_attempted_count += 1;
                if (executed.gpu_timestamp_valid) trace_summary.execution_gpu_timestamp_valid_count += 1;
                trace_summary.execution_backend = executed.backend;
                if (executed.backend_selection_reason) |reason| trace_summary.backend_selection_reason = reason;
                if (executed.fallback_used) |fallback| trace_summary.fallback_used = fallback;
                if (executed.selection_policy_hash) |hash| trace_summary.selection_policy_hash = hash;
                if (executed.shader_artifact_manifest_path) |path| trace_summary.shader_artifact_manifest_path = path;
                if (executed.shader_artifact_manifest_hash) |hash| trace_summary.shader_artifact_manifest_hash = hash;
                if (executed.host_plan_artifact_path) |path| trace_summary.host_plan_artifact_path = path;
                if (executed.host_plan_artifact_hash) |hash| trace_summary.host_plan_artifact_hash = hash;
                if (executed.backend_lane) |lane| trace_summary.backend_lane = lane;
                if (executed.adapter_ordinal) |ordinal| trace_summary.adapter_ordinal = ordinal;
                if (executed.queue_family_index) |queue_family_index| trace_summary.queue_family_index = queue_family_index;
                if (executed.present_capable) |present_capable| trace_summary.present_capable = present_capable;
                switch (executed.status) {
                    .ok => trace_summary.execution_success_count += 1,
                    .@"error" => trace_summary.execution_error_count += 1,
                    .unsupported => trace_summary.execution_unsupported_count += 1,
                    .skipped => trace_summary.execution_skipped_count += 1,
                }
            }

            if (result.decision.matched_quirk_id != null) {
                trace_summary.matched_count += 1;
                if (result.decision.verification_mode) |mode| {
                    if (mode == .lean_required) trace_summary.lean_required_count += 1;
                }
            }
            if (result.decision.requires_lean) trace_summary.requires_lean_count += 1;
            if (result.decision.is_blocking) trace_summary.blocking_count += 1;

            if (compact_upload_trace) {
                if (execute_result) |executed| {
                    if (compact_upload_trace_row_totals) |*rows| {
                        try rows.append(allocator, executionRowTotalNs(executed));
                    }
                }
            } else if (emit_trace_payload) {
                const previous_hash = trace_state.previous_hash;
                const semantic_hash = trace.tracePayloadHashWithSemantic(
                    trace_state,
                    physical_command_index,
                    command_label,
                    target,
                    kernel_name,
                    metadata.semantic,
                    result,
                );
                if (replay_expectations) |expectations| {
                    if (physical_command_index >= expectations.len) return replay.ReplayValidationError.ReplayMissingRow;
                    const expected = expectations[physical_command_index];
                    if (expected.seq != physical_command_index) return replay.ReplayValidationError.ReplaySeqMismatch;
                    if (!std.mem.eql(u8, expected.command, command_label)) return replay.ReplayValidationError.ReplayCommandMismatch;
                    if (!replay.matchOptionalText(expected.kernel, kernel_name)) return replay.ReplayValidationError.ReplayKernelMismatch;
                    if (expected.previous_hash != previous_hash) return replay.ReplayValidationError.ReplayPreviousHashMismatch;
                    if (expected.hash != semantic_hash) return replay.ReplayValidationError.ReplayHashMismatch;
                }
                if (emit_trace) {
                    try trace.printTraceLineWithSemantic(
                        stdout,
                        physical_command_index,
                        command_label,
                        kernel_name,
                        metadata.semantic,
                        result,
                        @intCast(timestamp_ns),
                        semantic_hash,
                        trace_state.previous_hash,
                        execute_result,
                    );
                }
                if (buffered_trace_rows) |*rows| {
                    try rows.append(allocator, .{
                        .seq = physical_command_index,
                        .command_label = command_label,
                        .kernel_name = kernel_name,
                        .semantic = metadata.semantic,
                        .decision = result.decision,
                        .timestamp_ns = @intCast(timestamp_ns),
                        .hash = semantic_hash,
                        .previous_hash = trace_state.previous_hash,
                        .execution_result = execute_result,
                    });
                }
                try artifact_recorder.record(
                    if (execution_context) |*ctx| ctx else null,
                    .{
                        .source_index = physical_command_index,
                        .command = target,
                        .command_label = command_label,
                        .kernel_name = kernel_name,
                        .semantic = metadata.semantic,
                        .capture = metadata.capture,
                        .execution_result = execute_result,
                        .profile_vendor = profile_vendor,
                        .profile_api = trace.apiName(profile.api),
                        .profile_family = profile_family,
                        .profile_driver = profile_driver,
                        .trace_hash = semantic_hash,
                        .trace_previous_hash = trace_state.previous_hash,
                        .trace_meta_path = trace_meta_path,
                    },
                );
                if (execute_result) |executed| {
                    if (executed.status == .ok) {
                        if (execution_context) |*ctx| {
                            const numeric_outcome = try numeric_stability_recorder.record(
                                ctx,
                                target,
                                metadata.semantic,
                                metadata.numeric_stability,
                                commands[idx + 1 ..],
                                command_metadata[idx + 1 ..],
                                .{
                                    .profile_vendor = profile_vendor,
                                    .profile_api = trace.apiName(profile.api),
                                    .profile_family = profile_family,
                                    .profile_driver = profile_driver,
                                    .execution_result = executed,
                                },
                            );
                            if (numeric_outcome.should_stop_downstream) {
                                trace_summary.execution_skipped_count += @as(u32, @intCast(physical_command_count_usize - physical_idx));
                                break :command_loop;
                            }
                        }
                    }
                }
                trace_summary.seq_max = @intCast(physical_command_index);
                trace_summary.row_count += 1;
                trace_summary.final_previous_hash = trace_state.previous_hash;
                trace_summary.final_hash = semantic_hash;
                trace_state.previous_hash = semantic_hash;
            } else if (result.decision.matched_quirk_id) |id| {
                try stdout.print(
                    "cmd[{d}] matched={s} verification={s} proof={s} requiresLean={} blocking={} score={} matched_count={d}\\n",
                    .{
                        physical_command_index,
                        id,
                        trace.verificationModeName(result.decision.verification_mode),
                        trace.proofLevelName(result.decision.proof_level),
                        result.decision.requires_lean,
                        result.decision.is_blocking,
                        result.decision.score,
                        result.decision.matched_count,
                    },
                );
            } else {
                try stdout.print("cmd[{d}] matched=<none> score=0 matched_count={d}\\n", .{ physical_command_index, result.decision.matched_count });
            }
            if (!emit_trace_payload) try main_print.printCommandSummary(stdout, target, execute_result);
        }
    }
    const command_loop_wall_ns = elapsedSince(command_loop_start_ns);
    if (command_loop_wall_ns > trace_summary.execution_total_ns) {
        host_command_orchestration_total_ns = command_loop_wall_ns - trace_summary.execution_total_ns;
    }

    if (execution_context) |*ctx| {
        if (queue_sync_mode == .deferred or upload_submit_every > 1) {
            const flush_start_ns = nowNs();
            const flush_ns = try ctx.flushQueue();
            trace_summary.execution_submit_wait_total_ns += flush_ns;
            host_command_orchestration_total_ns += elapsedSince(flush_start_ns);
        }
    }

    const artifact_finalize_start_ns = nowNs();
    if (emit_trace_jsonl) |path| {
        if (compact_upload_trace_row_totals) |*rows| {
            if (rows.items.len > 0) {
                trace_summary.seq_max = 0;
                trace_summary.row_count = 1;
            }
            const trace_jsonl_timing = try trace_jsonl_emit.writeCompactUploadTraceRows(
                allocator,
                path,
                "doe-zig-runtime",
                rows.items,
            );
            host_artifact_trace_jsonl_serialize_total_ns = trace_jsonl_timing.serialize_ns;
            host_artifact_trace_jsonl_write_total_ns = trace_jsonl_timing.write_ns;
        } else if (buffered_trace_rows) |*rows| {
            const trace_jsonl_timing = try trace_jsonl_emit.writeBufferedTraceRows(allocator, path, rows.items);
            host_artifact_trace_jsonl_serialize_total_ns = trace_jsonl_timing.serialize_ns;
            host_artifact_trace_jsonl_write_total_ns = trace_jsonl_timing.write_ns;
        }
    }
    const operator_manifest_finalize_start_ns = nowNs();
    const artifact_summary = try artifact_recorder.finalize();
    host_artifact_operator_manifest_finalize_total_ns = elapsedSince(operator_manifest_finalize_start_ns);
    host_artifact_finalize_total_ns = elapsedSince(artifact_finalize_start_ns);
    trace_summary.semantic_op_row_count = artifact_summary.row_count;
    trace_summary.semantic_capture_count = artifact_summary.capture_count;
    trace_summary.semantic_repro_count = artifact_summary.repro_count;
    trace_summary.operator_record_manifest_path = artifact_summary.manifest_path;
    trace_summary.operator_record_manifest_hash = artifact_summary.manifest_hash;
    trace_summary.numeric_stability = numeric_stability_recorder.summary();
    trace_summary.host_command_orchestration_total_ns = host_command_orchestration_total_ns;
    trace_summary.host_artifact_finalize_total_ns = host_artifact_finalize_total_ns;
    trace_summary.host_artifact_trace_jsonl_serialize_total_ns = host_artifact_trace_jsonl_serialize_total_ns;
    trace_summary.host_artifact_trace_jsonl_write_total_ns = host_artifact_trace_jsonl_write_total_ns;
    trace_summary.host_artifact_operator_manifest_finalize_total_ns = host_artifact_operator_manifest_finalize_total_ns;

    if (trace_meta_path) |path| {
        try trace.writeTraceMeta(path, trace_summary);
    }
    if (replay_expectations) |expectations| {
        if (expectations.len != physical_command_count_usize) {
            return replay.ReplayValidationError.ReplayRowCountMismatch;
        }
    }
}
