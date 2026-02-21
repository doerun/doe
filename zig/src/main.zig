const std = @import("std");
const model = @import("model.zig");
const parser = @import("quirk_json.zig");
const command_parser = @import("command_json.zig");
const runtime = @import("runtime.zig");
const execution = @import("execution.zig");
const trace = @import("trace.zig");
const replay = @import("replay.zig");

const sample_quirks =
    \\[
    \\  {
    \\    "schemaVersion": 1,
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
        \\ [--queue-wait-mode process-events|wait-any]
        \\ [--kernel-root <path>]
        \\ [--replay <path>]
        \\ [--execute]
        \\commands file examples:
        \\  upload | buffer_upload
        \\  copy_buffer_to_texture | texture_copy | copy_texture | copy_buffer_to_buffer | copy_texture_to_buffer | copy_texture_to_texture
        \\  dispatch | dispatch_workgroups | dispatch_invocations
        \\  kernel_dispatch (requires a kernel string)
        \\  render_draw | draw | draw_call (requires draw_count)
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
        \\  native: execute through webgpu-native; dispatch and kernel_dispatch are lowered to compute passes (dispatch uses builtin fallback kernel), render_draw is lowered to a render pass.
        \\--upload-buffer-usage selects upload buffer usage when --execute is enabled.
        \\  copy-dst-copy-src: create upload buffers with CopyDst|CopySrc (default).
        \\  copy-dst: create upload buffers with CopyDst only.
        \\--upload-submit-every submits and waits after every N upload commands (default: 1).
        \\--queue-wait-mode controls queue completion waiting strategy for native execution.
        \\  process-events: callback + process-events loop (default).
        \\  wait-any: callback + wgpuInstanceWaitAny wait path (falls back to process-events when unsupported).
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

fn commandName(command: model.Command) []const u8 {
    return model.command_kind_name(model.command_kind(command));
}

fn commandKernel(command: model.Command) ?[]const u8 {
    return switch (command) {
        .kernel_dispatch => |dispatch| dispatch.kernel,
        else => null,
    };
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

fn printNormalizedCommand(stdout: anytype, seq: usize, command: model.Command) !void {
    switch (command) {
        .upload => |upload| {
            try stdout.writeAll("{\"seq\":");
            try stdout.print("{}", .{seq});
            try stdout.writeAll(",\"kind\":\"upload\",\"bytes\":");
            try stdout.print("{}", .{upload.bytes});
            try stdout.writeAll(",\"alignBytes\":");
            try stdout.print("{}", .{upload.align_bytes});
            try stdout.writeAll("}\n");
        },
        .copy_buffer_to_texture => |copy| {
            try stdout.writeAll("{\"seq\":");
            try stdout.print("{}", .{seq});
            try stdout.writeAll(",\"kind\":\"copy_buffer_to_texture\",\"direction\":\"");
            const direction = switch (copy.direction) {
                .buffer_to_buffer => "buffer_to_buffer",
                .buffer_to_texture => "buffer_to_texture",
                .texture_to_buffer => "texture_to_buffer",
                .texture_to_texture => "texture_to_texture",
            };
            try stdout.writeAll(direction);
            try stdout.writeAll("\",\"srcHandle\":");
            try stdout.print("{}", .{copy.src.handle});
            try stdout.writeAll(",\"dstHandle\":");
            try stdout.print("{}", .{copy.dst.handle});
            try stdout.writeAll(",\"bytes\":");
            try stdout.print("{}", .{copy.bytes});
            try stdout.writeAll(",\"usesTemporaryBuffer\":");
            try stdout.print("{}", .{copy.uses_temporary_buffer});
            try stdout.writeAll(",\"temporaryBufferAlignment\":");
            try stdout.print("{}", .{copy.temporary_buffer_alignment});
            try stdout.writeAll("}\n");
        },
        .dispatch => |dispatch_cmd| {
            try stdout.writeAll("{\"seq\":");
            try stdout.print("{}", .{seq});
            try stdout.writeAll(",\"kind\":\"dispatch\",\"x\":");
            try stdout.print("{}", .{dispatch_cmd.x});
            try stdout.writeAll(",\"y\":");
            try stdout.print("{}", .{dispatch_cmd.y});
            try stdout.writeAll(",\"z\":");
            try stdout.print("{}", .{dispatch_cmd.z});
            try stdout.writeAll("}\n");
        },
        .kernel_dispatch => |kernel_cmd| {
            try stdout.writeAll("{\"seq\":");
            try stdout.print("{}", .{seq});
            try stdout.writeAll(",\"kind\":\"kernel_dispatch\",\"kernel\":\"");
            try stdout.print("{s}\",\"x\":", .{kernel_cmd.kernel});
            try stdout.print("{}", .{kernel_cmd.x});
            try stdout.writeAll(",\"y\":");
            try stdout.print("{}", .{kernel_cmd.y});
            try stdout.writeAll(",\"z\":");
            try stdout.print("{}", .{kernel_cmd.z});
            try stdout.writeAll(",\"repeat\":");
            try stdout.print("{}", .{kernel_cmd.repeat});
            try stdout.writeAll("}\n");
        },
        .render_draw => |render_cmd| {
            try stdout.writeAll("{\"seq\":");
            try stdout.print("{}", .{seq});
            try stdout.writeAll(",\"kind\":\"render_draw\",\"drawCount\":");
            try stdout.print("{}", .{render_cmd.draw_count});
            try stdout.writeAll(",\"vertexCount\":");
            try stdout.print("{}", .{render_cmd.vertex_count});
            try stdout.writeAll(",\"instanceCount\":");
            try stdout.print("{}", .{render_cmd.instance_count});
            try stdout.writeAll(",\"targetHandle\":");
            try stdout.print("{}", .{render_cmd.target_handle});
            try stdout.writeAll(",\"targetWidth\":");
            try stdout.print("{}", .{render_cmd.target_width});
            try stdout.writeAll(",\"targetHeight\":");
            try stdout.print("{}", .{render_cmd.target_height});
            try stdout.writeAll(",\"targetFormat\":");
            try stdout.print("{}", .{render_cmd.target_format});
            try stdout.writeAll(",\"pipelineMode\":\"");
            try stdout.print("{s}\",", .{@tagName(render_cmd.pipeline_mode)});
            try stdout.writeAll("\"bindGroupMode\":\"");
            try stdout.print("{s}\"", .{@tagName(render_cmd.bind_group_mode)});
            try stdout.writeAll("}\n");
        },
        .barrier => |barrier_cmd| {
            try stdout.writeAll("{\"seq\":");
            try stdout.print("{}", .{seq});
            try stdout.writeAll(",\"kind\":\"barrier\",\"dependencyCount\":");
            try stdout.print("{}", .{barrier_cmd.dependency_count});
            try stdout.writeAll("}\n");
        },
    }
}

pub fn main() !void {
    const allocator = std.heap.page_allocator;
    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    const stdout = std.fs.File.stdout().deprecatedWriter();

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
    var queue_wait_mode: execution.QueueWaitMode = .process_events;

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
        } else if (std.mem.eql(u8, argv[i], "--execute")) {
            execute = true;
        } else if (std.mem.eql(u8, argv[i], "--replay") and i + 1 < argv.len) {
            i += 1;
            replay_path = argv[i];
        } else if (std.mem.eql(u8, argv[i], "--help")) {
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
            try printNormalizedCommand(stdout, normalized_idx, commands[normalized_idx]);
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
            ctx.configureQueueWaitMode(queue_wait_mode);
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
        .execution_backend = null,
        .final_hash = trace_state.previous_hash,
        .final_previous_hash = trace_state.previous_hash,
        .profile_vendor = profile_vendor,
        .profile_api = trace.apiName(profile.api),
        .profile_family = profile_family,
        .profile_driver = profile_driver,
    };
    if (execution_context != null) {
        trace_summary.execution_backend = execution.executionModeName(backend_mode);
    }

    var idx: usize = 0;
    while (idx < commands.len) : (idx += 1) {
        const command = commands[idx];
        const result = runtime.dispatch(profile, dispatch_context, command);
        const target = result.command;
        const kernel_name = commandKernel(target);
        const command_label = commandName(target);
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
                const trace_writer = file.deprecatedWriter();
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
        if (!emit_trace_payload) {
            switch (target) {
                .copy_buffer_to_texture => |copy| {
                    try stdout.print("  -> copy bytes={} temp={} align={}\\n", .{
                        copy.bytes,
                        copy.uses_temporary_buffer,
                        copy.temporary_buffer_alignment,
                    });
                },
                .upload => |upload| {
                    try stdout.print("  -> upload bytes={} align={}\\n", .{ upload.bytes, upload.align_bytes });
                },
                .kernel_dispatch => |kernel_cmd| {
                    try stdout.print("  -> kernel={s} dispatch {}x{}x{} repeat={}\\n", .{ kernel_cmd.kernel, kernel_cmd.x, kernel_cmd.y, kernel_cmd.z, kernel_cmd.repeat });
                },
                .dispatch => |dispatch_cmd| {
                    try stdout.print("  -> dispatch {}x{}x{}\\n", .{ dispatch_cmd.x, dispatch_cmd.y, dispatch_cmd.z });
                },
                .render_draw => |render_cmd| {
                    try stdout.print(
                        "  -> render_draw draws={} vertices={} instances={} target={}x{} handle={} pipelineMode={s} bindGroupMode={s}\\n",
                        .{
                            render_cmd.draw_count,
                            render_cmd.vertex_count,
                            render_cmd.instance_count,
                            render_cmd.target_width,
                            render_cmd.target_height,
                            render_cmd.target_handle,
                            @tagName(render_cmd.pipeline_mode),
                            @tagName(render_cmd.bind_group_mode),
                        },
                    );
                },
                .barrier => |barrier_cmd| {
                    try stdout.print("  -> barrier {} dependencies\\n", .{barrier_cmd.dependency_count});
                },
            }
                if (execute_result) |exec| {
                    try stdout.print(
                        "  -> exec backend={s} status={s} statusCode={s} durationNs={} setupNs={} encodeNs={} submitWaitNs={} dispatchCount={}\\n",
                        .{
                            exec.backend,
                            execution.executionStatusName(exec.status),
                            exec.status_code,
                            exec.duration_ns,
                            exec.setup_ns,
                            exec.encode_ns,
                            exec.submit_wait_ns,
                            exec.dispatch_count,
                        },
                    );
                }
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
