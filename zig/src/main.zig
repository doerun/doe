const std = @import("std");
const model = @import("model.zig");
const parser = @import("quirk_json.zig");
const command_parser = @import("command_json.zig");
const runtime = @import("runtime.zig");
const execution = @import("execution.zig");
const trace = @import("trace.zig");
const replay = @import("replay.zig");
const main_print = @import("main_print.zig");

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
    .{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } },
    .{ .kernel_dispatch = .{ .kernel = "builtin:noop", .x = 2, .y = 1, .z = 1 } },
    .{ .barrier = .{ .dependency_count = 3 } },
};

fn printUsage(stdout: anytype) !void {
    try stdout.print(
        \\fawn-zig-runtime --quirks <path> [--commands <path>] [--vendor X] [--api X] [--family X] [--driver X.Y.Z] [--trace]
        \\ [--trace-jsonl <path>] [--trace-meta <path>] [--backend trace|native]
        \\ [--upload-buffer-usage copy-dst-copy-src|copy-dst] [--upload-submit-every N]
        \\ [--gpu-timestamp-mode auto|off]
        \\ [--queue-wait-mode process-events|wait-any]
        \\ [--queue-sync-mode per-command|deferred]
        \\ [--kernel-root <path>]
        \\ [--replay <path>]
        \\ [--execute]
        \\commands file examples:
        \\  upload | buffer_upload
        \\  copy_buffer_to_texture | texture_copy | copy_texture | copy_buffer_to_buffer | copy_texture_to_buffer | copy_texture_to_texture
        \\  dispatch | dispatch_workgroups | dispatch_invocations
        \\  kernel_dispatch (requires a kernel string)
        \\  render_draw | draw | draw_call | draw_indexed (requires draw_count; draw_indexed requires indexData/indices)
        \\  sampler_create | create_sampler
        \\  sampler_destroy | destroy_sampler
        \\  texture_write | write_texture | queue_write_texture
        \\  texture_query | query_texture (optional expected width/height/depth/format/dimension/viewDimension/sampleCount/usage assertions)
        \\  texture_destroy | destroy_texture
        \\  surface_create | create_surface
        \\  surface_capabilities | get_surface_capabilities
        \\  surface_configure | configure_surface
        \\  surface_acquire | acquire_surface_texture
        \\  surface_present | present_surface
        \\  surface_unconfigure | unconfigure_surface
        \\  surface_release | release_surface
        \\  async_diagnostics | pipeline_async_diagnostics
        \\    optional fields: mode=pipeline_async|capability_introspection|resource_table_immediates|lifecycle_refcount|full, iterations>0
        \\  command can be expressed as "kind", "command", or "command_kind"
        \\  kernel can be expressed as "kernel" or "kernel_name"
        \\If --quirks is omitted, the embedded sample profile is used.
        \\If --commands is omitted, the embedded sample command list is used.
        \\If --emit-normalized is set, emit canonicalized commands as ndjson and exit.
        \\Runtime output includes Lean-required flags when a matching quirk is selected.
        \\--trace prints machine-readable ndjson rows to stdout.
        \\--trace-jsonl writes machine-readable ndjson rows to a file.
        \\--trace-meta writes a deterministic run summary JSON artifact.
        \\--backend chooses execution backend when --execute is enabled.
        \\  trace: do not execute commands (trace-only mode)
        \\  native: execute through webgpu-native; dispatch/kernel_dispatch lower to compute passes, render_draw lowers to render-pass or render-bundle mode, and sampler/texture/surface/async diagnostics commands run through explicit WebGPU API contracts.
        \\--upload-buffer-usage selects upload buffer usage when --execute is enabled.
        \\  copy-dst-copy-src: create upload buffers with CopyDst|CopySrc (default).
        \\  copy-dst: create upload buffers with CopyDst only.
        \\--upload-submit-every submits and waits after every N upload commands (default: 1).
        \\--gpu-timestamp-mode controls native GPU timestamp query usage for kernel dispatch timings.
        \\  auto: use GPU timestamps when feature/query artifacts are available (default).
        \\  off: disable GPU timestamp attempts and rely on non-timestamp operation timing sources.
        \\--queue-wait-mode controls queue completion waiting strategy for native execution.
        \\  process-events: callback + process-events loop (default).
        \\  wait-any: callback + wgpuInstanceWaitAny wait path (fails explicitly when unsupported).
        \\--queue-sync-mode controls when queue synchronization occurs.
        \\  per-command: waitForQueue after every submit (default).
        \\  deferred: skip per-submit waits; one final flush after the command loop.
        \\--kernel-root provides a filesystem root for kernel lookup when kernel_dispatch is used.
        \\--replay validates current dispatch rows against a replay artifact path.
        \\
    , .{});
}

fn readFileAlloc(allocator: std.mem.Allocator, path: []const u8) ![]const u8 {
    const file = try std.fs.cwd().openFile(path, .{});
    defer file.close();
    return try file.readToEndAlloc(allocator, 16 * 1024 * 1024);
}

fn optionExpectsValue(option: []const u8) bool {
    return std.mem.eql(u8, option, "--quirks") or
        std.mem.eql(u8, option, "--commands") or
        std.mem.eql(u8, option, "--vendor") or
        std.mem.eql(u8, option, "--api") or
        std.mem.eql(u8, option, "--family") or
        std.mem.eql(u8, option, "--driver") or
        std.mem.eql(u8, option, "--trace-jsonl") or
        std.mem.eql(u8, option, "--trace-meta") or
        std.mem.eql(u8, option, "--kernel-root") or
        std.mem.eql(u8, option, "--backend") or
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
            else => {},
        }
    }
    return max_bytes;
}

pub fn main() !void {
    const allocator = std.heap.page_allocator;
    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    const stdout = std.io.getStdOut().writer();

    var quirks_text: ?[]const u8 = null;
    var commands_text: ?[]const u8 = null;
    var profile_vendor: []const u8 = "intel";
    var profile_api: []const u8 = "vulkan";
    var profile_family: ?[]const u8 = "gen12";
    var profile_driver: []const u8 = "31.0.101";
    var emit_trace = false;
    var emit_trace_jsonl: ?[]const u8 = null;
    var emit_normalized = false;
    var trace_meta_path: ?[]const u8 = null;
    var replay_path: ?[]const u8 = null;
    var execute = false;
    var backend_mode: execution.BackendMode = .trace;
    var kernel_root: ?[]const u8 = null;
    var upload_buffer_usage_mode: execution.UploadBufferUsageMode = .copy_dst_copy_src;
    var upload_submit_every: u32 = 1;
    var gpu_timestamp_mode: execution.GpuTimestampMode = .auto;
    var queue_wait_mode: execution.QueueWaitMode = .process_events;
    var queue_sync_mode: execution.QueueSyncMode = .per_command;

    var i: usize = 1;
    while (i < argv.len) {
        if (std.mem.eql(u8, argv[i], "--quirks") and i + 1 < argv.len) {
            i += 1;
            quirks_text = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--commands") and i + 1 < argv.len) {
            i += 1;
            commands_text = argv[i];
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
                    "invalid --gpu-timestamp-mode value: {s} (expected auto|off)\n",
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

    const quirks_bytes = if (quirks_text) |path| try readFileAlloc(allocator, path) else sample_quirks;
    const using_quarks_from_file = quirks_text != null;

    const quirks = try parser.parseQuirks(allocator, quirks_bytes);
    defer {
        if (using_quarks_from_file) allocator.free(quirks_bytes);
        parser.freeQuirks(allocator, quirks);
    }
    var replay_expectations: ?[]replay.ReplayExpectation = null;
    if (replay_path) |path| {
        replay_expectations = try replay.loadReplayExpectations(allocator, path);
    }
    defer if (replay_expectations) |expectations| replay.freeReplayExpectations(allocator, expectations);
    var commands: []const model.Command = default_commands[0..];
    var owned_commands: ?[]model.Command = null;

    if (commands_text) |commands_path| {
        const commands_bytes = try readFileAlloc(allocator, commands_path);
        defer allocator.free(commands_bytes);
        const parsed_commands = try command_parser.parseCommands(allocator, commands_bytes);
        commands = parsed_commands;
        owned_commands = parsed_commands;
    }
    defer if (owned_commands) |parsed_commands| command_parser.freeCommands(allocator, parsed_commands);

    const profile = model.DeviceProfile{
        .vendor = profile_vendor,
        .api = try model.parse_api(profile_api),
        .device_family = profile_family,
        .driver_version = try model.SemVer.parse(profile_driver),
    };

    if (emit_normalized) {
        var normalized_idx: usize = 0;
        while (normalized_idx < commands.len) : (normalized_idx += 1) {
            try main_print.printNormalizedCommand(stdout, normalized_idx, commands[normalized_idx]);
        }
        return;
    }

    var dispatch_context = try runtime.buildProfileDispatchContext(allocator, profile, quirks);
    defer dispatch_context.deinit();
    var trace_state = trace.TraceState{};

    if (execute and backend_mode == .trace) {
        try trace.writef(stdout, "cannot execute with backend=trace. use --backend native\n", .{});
        return;
    }

    var execution_context: ?execution.ExecutionContext = null;
    if (execute) {
        execution_context = try execution.ExecutionContext.init(allocator, backend_mode, profile, kernel_root);
        if (execution_context) |*ctx| {
            ctx.configureUploadBehavior(upload_buffer_usage_mode, upload_submit_every);
            ctx.configureGpuTimestampMode(gpu_timestamp_mode);
            ctx.configureQueueWaitMode(queue_wait_mode);
            ctx.configureQueueSyncMode(queue_sync_mode);
            const max_upload_bytes = maxUploadBytes(commands);
            if (max_upload_bytes > 0) {
                try ctx.prewarmUploadPath(max_upload_bytes);
            }
        }
    }
    defer {
        if (execution_context) |*ctx| {
            ctx.deinit();
        }
    }

    var trace_jsonl_file: ?std.fs.File = null;
    if (emit_trace_jsonl) |path| {
        trace_jsonl_file = try std.fs.cwd().createFile(path, .{});
    }
    defer if (trace_jsonl_file) |trace_file| trace_file.close();

    var trace_summary = trace.TraceRunSummary{
        .trace_version = 1,
        .module_name = "fawn-zig-runtime",
        .seq_max = 0,
        .row_count = 0,
        .command_count = @intCast(commands.len),
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
        .queue_sync_mode = if (execution_context != null) @tagName(queue_sync_mode) else null,
    };
    if (execution_context != null) {
        trace_summary.execution_backend = execution.executionModeName(backend_mode);
    }

    var idx: usize = 0;
    while (idx < commands.len) : (idx += 1) {
        const command = commands[idx];
        const result = runtime.dispatch(profile, dispatch_context, command);
        const target = result.command;
        const kernel_name = main_print.commandKernel(target);
        const command_label = main_print.commandName(target);
        const timestamp_ns: u64 = @intCast(std.time.nanoTimestamp());
        var execute_result: ?execution.ExecutionResult = null;
        const emit_trace_payload = emit_trace or (trace_jsonl_file != null) or (trace_meta_path != null) or (replay_expectations != null);

        if (execution_context) |*ctx| {
            const executed = try ctx.execute(target);
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

        if (emit_trace_payload) {
            const previous_hash = trace_state.previous_hash;
            const current_hash = trace.tracePayloadHash(
                trace_state,
                idx,
                command_label,
                target,
                kernel_name,
                result,
            );
            if (replay_expectations) |expectations| {
                if (idx >= expectations.len) return replay.ReplayValidationError.ReplayMissingRow;
                const expected = expectations[idx];
                if (expected.seq != idx) return replay.ReplayValidationError.ReplaySeqMismatch;
                if (!std.mem.eql(u8, expected.command, command_label)) return replay.ReplayValidationError.ReplayCommandMismatch;
                if (!replay.matchOptionalText(expected.kernel, kernel_name)) return replay.ReplayValidationError.ReplayKernelMismatch;
                if (expected.previous_hash != previous_hash) return replay.ReplayValidationError.ReplayPreviousHashMismatch;
                if (expected.hash != current_hash) return replay.ReplayValidationError.ReplayHashMismatch;
            }
            if (emit_trace) {
                try trace.printTraceLine(
                    stdout,
                    idx,
                    command_label,
                    kernel_name,
                    result,
                    @intCast(timestamp_ns),
                    current_hash,
                    trace_state.previous_hash,
                    execute_result,
                );
            }
            if (trace_jsonl_file) |*file| {
                const trace_writer = file.writer();
                try trace.printTraceLine(
                    trace_writer,
                    idx,
                    command_label,
                    kernel_name,
                    result,
                    @intCast(timestamp_ns),
                    current_hash,
                    trace_state.previous_hash,
                    execute_result,
                );
            }
            trace_summary.seq_max = @intCast(idx);
            trace_summary.row_count += 1;
            trace_summary.final_previous_hash = trace_state.previous_hash;
            trace_summary.final_hash = current_hash;
            trace_state.previous_hash = current_hash;
        } else if (result.decision.matched_quirk_id) |id| {
            try stdout.print(
                "cmd[{d}] matched={s} verification={s} proof={s} requiresLean={} blocking={} score={} matched_count={d}\\n",
                .{
                    idx,
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
            try stdout.print("cmd[{d}] matched=<none> score=0 matched_count={d}\\n", .{ idx, result.decision.matched_count });
        }
        if (!emit_trace_payload) try main_print.printCommandSummary(stdout, target, execute_result);
    }

    if (execution_context) |*ctx| {
        if (queue_sync_mode == .deferred) {
            const flush_ns = try ctx.flushQueue();
            trace_summary.execution_submit_wait_total_ns += flush_ns;
        }
    }

    if (trace_meta_path) |path| {
        try trace.writeTraceMeta(path, trace_summary);
    }
    if (replay_expectations) |expectations| {
        if (expectations.len != commands.len) {
            return replay.ReplayValidationError.ReplayRowCountMismatch;
        }
    }
}
