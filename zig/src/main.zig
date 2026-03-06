const std = @import("std");
const model = @import("model.zig");
const quirk = @import("quirk/mod.zig");
const command_parser = @import("command_json.zig");
const execution = @import("execution.zig");
const trace = @import("trace.zig");
const replay = @import("replay.zig");
const main_print = @import("main_print.zig");
const lean_proof = @import("lean_proof.zig");

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
    .{ .kernel_dispatch = .{ .kernel = "bench/kernels/shader_compile_pipeline_stress.wgsl", .x = 2, .y = 1, .z = 1 } },
    .{ .barrier = .{ .dependency_count = 3 } },
};

fn printUsage(stdout: anytype) !void {
    try stdout.print(
        \\doe-zig-runtime --quirks <path> [--commands <path>] [--quirk-mode off|trace|active] [--vendor X] [--api X] [--family X] [--driver X.Y.Z] [--trace]
        \\ [--trace-jsonl <path>] [--trace-meta <path>] [--backend trace|native] [--backend-lane vulkan_dawn_release|vulkan_doe_app|d3d12_doe_app|metal_doe_directional|metal_doe_comparable|metal_doe_release|metal_dawn_release|d3d12_doe_directional|d3d12_doe_comparable|d3d12_doe_release|d3d12_dawn_release|vulkan_dawn_directional|vulkan_doe_comparable|vulkan_doe_release|metal_doe_app]
        \\ [--upload-buffer-usage copy-dst-copy-src|copy-dst] [--upload-submit-every N]
        \\ [--gpu-timestamp-mode auto|off|require]
        \\ [--queue-wait-mode process-events|wait-any]
        \\ [--queue-sync-mode per-command|deferred]
        \\ [--kernel-root <path>]
        \\ [--replay <path>]
        \\ [--execute]
        \\commands file examples:
        \\  upload | buffer_upload
        \\  copy_buffer_to_texture | texture_copy | copy_texture | copy_buffer_to_buffer | copy_texture_to_buffer | copy_texture_to_texture
        \\  dispatch | dispatch_workgroups | dispatch_invocations
        \\  dispatch_indirect
        \\  kernel_dispatch (requires a kernel string)
        \\  render_draw | draw | draw_call | draw_indexed
        \\  draw_indirect | draw_indexed_indirect | render_pass (render_draw-compatible payload fields)
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
        \\--quirk-mode controls how quirks affect command execution.
        \\  off: no quirk processing; commands pass through unmodified.
        \\  trace: quirks are matched and traced, but commands are not modified for execution (default).
        \\  active: quirks are matched, traced, and command modifications are consumed by backends.
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
        \\--backend-lane selects backend selection policy lane when native execution is enabled.
        \\  vulkan_dawn_release, vulkan_doe_app, d3d12_doe_app, metal_doe_directional, metal_doe_comparable, metal_doe_release, metal_dawn_release, d3d12_doe_directional, d3d12_doe_comparable, d3d12_doe_release, d3d12_dawn_release, vulkan_dawn_directional, vulkan_doe_comparable, vulkan_doe_release, metal_doe_app
        \\--upload-buffer-usage selects upload buffer usage when --execute is enabled.
        \\  copy-dst-copy-src: create upload buffers with CopyDst|CopySrc (default).
        \\  copy-dst: create upload buffers with CopyDst only.
        \\--upload-submit-every submits and waits after every N upload commands (default: 1).
        \\--gpu-timestamp-mode controls native GPU timestamp query usage for kernel dispatch timings.
        \\  auto: use GPU timestamps when feature/query artifacts are available (default).
        \\  off: disable GPU timestamp attempts and rely on non-timestamp operation timing sources.
        \\  require: fail command execution when timestamp capture is unavailable or invalid.
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
        std.mem.eql(u8, option, "--quirk-mode") or
        std.mem.eql(u8, option, "--vendor") or
        std.mem.eql(u8, option, "--api") or
        std.mem.eql(u8, option, "--family") or
        std.mem.eql(u8, option, "--driver") or
        std.mem.eql(u8, option, "--trace-jsonl") or
        std.mem.eql(u8, option, "--trace-meta") or
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
            else => {},
        }
    }
    return max_bytes;
}

fn prewarmKernelDispatches(ctx: *execution.ExecutionContext, commands: []const model.Command) void {
    for (commands) |command| {
        switch (command) {
            .kernel_dispatch => |kd| {
                ctx.prewarmKernelDispatch(kd.kernel, kd.bindings) catch {};
            },
            else => {},
        }
    }
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
    var replay_path: ?[]const u8 = null;
    var execute = false;
    var backend_mode: execution.BackendMode = .trace;
    var backend_lane_value: ?[]const u8 = null;
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

    const quirks_bytes = if (quirk_mode.loadsQuirks())
        (if (quirks_text) |path| try readFileAlloc(allocator, path) else sample_quirks)
    else
        "[]";
    const using_quarks_from_file = quirks_text != null and quirk_mode.loadsQuirks();

    const quirks = try quirk.parser.parseQuirks(allocator, quirks_bytes);
    defer {
        if (using_quarks_from_file) allocator.free(quirks_bytes);
        quirk.parser.freeQuirks(allocator, quirks);
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

    const backend_lane = if (backend_lane_value) |raw_lane| blk: {
        if (execution.parseBackendLane(raw_lane)) |lane| {
            break :blk lane;
        }
        try trace.writef(stdout, "invalid --backend-lane value: {s}\n", .{raw_lane});
        return;
    } else execution.defaultBackendLane(profile);

    if (emit_normalized) {
        var normalized_idx: usize = 0;
        while (normalized_idx < commands.len) : (normalized_idx += 1) {
            try main_print.printNormalizedCommand(stdout, normalized_idx, commands[normalized_idx]);
        }
        return;
    }

    var dispatch_context = try quirk.runtime.buildProfileDispatchContext(allocator, profile, quirks);
    defer dispatch_context.deinit();
    var trace_state = trace.TraceState{};

    if (execute and backend_mode == .trace) {
        try trace.writef(stdout, "cannot execute with backend=trace. use --backend native\n", .{});
        return;
    }

    var execution_context: ?execution.ExecutionContext = null;
    if (execute) {
        execution_context = try execution.ExecutionContext.init(allocator, backend_mode, profile, kernel_root, backend_lane);
        if (execution_context) |*ctx| {
            ctx.configureUploadBehavior(upload_buffer_usage_mode, upload_submit_every);
            ctx.configureGpuTimestampMode(gpu_timestamp_mode);
            ctx.configureQueueWaitMode(queue_wait_mode);
            ctx.configureQueueSyncMode(queue_sync_mode);
            const max_upload_bytes = maxUploadBytes(commands);
            if (max_upload_bytes > 0) {
                try ctx.prewarmUploadPath(max_upload_bytes);
            }
            prewarmKernelDispatches(ctx, commands);
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
        .module_name = "doe-zig-runtime",
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
        .backend_selection_reason = null,
        .fallback_used = null,
        .selection_policy_hash = null,
        .shader_artifact_manifest_path = null,
        .shader_artifact_manifest_hash = null,
        .backend_lane = execution.backendLaneName(backend_lane),
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
            trace_summary.execution_backend = execution.backendIdName(selection.backend_id);
            trace_summary.backend_selection_reason = selection.backend_selection_reason;
            trace_summary.fallback_used = selection.fallback_used;
            trace_summary.selection_policy_hash = selection.selection_policy_hash;
            trace_summary.shader_artifact_manifest_path = selection.shader_artifact_manifest_path;
            trace_summary.shader_artifact_manifest_hash = selection.shader_artifact_manifest_hash;
        }
    }

    var idx: usize = 0;
    while (idx < commands.len) : (idx += 1) {
        const command = commands[idx];
        const result = quirk.dispatchWithMode(quirk_mode, profile, dispatch_context, command);
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
            if (executed.backend_selection_reason) |reason| trace_summary.backend_selection_reason = reason;
            if (executed.fallback_used) |fallback| trace_summary.fallback_used = fallback;
            if (executed.selection_policy_hash) |hash| trace_summary.selection_policy_hash = hash;
            if (executed.shader_artifact_manifest_path) |path| trace_summary.shader_artifact_manifest_path = path;
            if (executed.shader_artifact_manifest_hash) |hash| trace_summary.shader_artifact_manifest_hash = hash;
            if (executed.backend_lane) |lane| trace_summary.backend_lane = lane;
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
        if (!emit_trace_payload) try main_print.printCommandSummary(stdout, target, execute_result);
    }

    if (execution_context) |*ctx| {
        if (queue_sync_mode == .deferred or upload_submit_every > 1) {
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
