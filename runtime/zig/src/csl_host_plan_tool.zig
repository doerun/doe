const std = @import("std");
const wgsl = @import("doe_wgsl/mod.zig");
const exec_v1 = wgsl.emit_csl_exec_v1;
const host = wgsl.emit_csl_host;
const host_plan = wgsl.emit_csl_host_plan;
const host_runtime = wgsl.emit_csl_host_runtime;
const mem_plan = wgsl.emit_csl_mem_plan;
const simulator = wgsl.emit_csl_simulator;

const Mode = enum {
    steps,
    manifest,
};

const Args = struct {
    input_path: []const u8,
    output_path: ?[]const u8 = null,
    bundle_root: ?[]const u8 = null,
    mode: Mode = .manifest,
    cslc_executable: ?[]const u8 = null,
    driver_executable_path: ?[]const u8 = null,
};

const BundleConfigJson = struct {
    modelConfig: ?ModelConfigJson = null,

    const ModelConfigJson = struct {
        hiddenDim: u32,
        numHeads: u32,
        headDim: u32,
        numLayers: u32,
        vocabSize: u32,
        maxSeqLen: u32,
        quantFormat: []const u8,
        ffnExpansionFactor: u32 = 4,
        ffnMatrixCount: u32 = 3,
        pleWidth: ?u32 = null,
        pleVocabSize: ?u32 = null,
    };
};

const MAX_KERNELS: usize = 64;
const MAX_LAUNCHES: usize = 96;
const MAX_STATE_BUFFERS: usize = 16;
const HOST_PLAN_CAPACITY: usize = 128 * 1024;
const RUNTIME_CONFIG_CAPACITY: usize = 128 * 1024;
const MEMORY_PLAN_CAPACITY: usize = 64 * 1024;
const SIMULATOR_PLAN_CAPACITY: usize = 64 * 1024;
const LAUNCHER_CAPACITY: usize = 8 * 1024;

fn printUsage() void {
    std.debug.print(
        "usage: doe-csl-host-plan-tool --input <execution.json> (--output <host-plan.json> | --bundle-root <dir>) [--mode manifest|steps] [--cslc-executable <path>] [--driver-executable-path <path>]\n",
        .{},
    );
}

fn parseArgs(allocator: std.mem.Allocator) !Args {
    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    var args = Args{
        .input_path = "",
    };

    var idx: usize = 1;
    while (idx < argv.len) : (idx += 1) {
        const arg = argv[idx];
        if (std.mem.eql(u8, arg, "--input")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            args.input_path = try allocator.dupe(u8, argv[idx]);
        } else if (std.mem.eql(u8, arg, "--output")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            args.output_path = try allocator.dupe(u8, argv[idx]);
        } else if (std.mem.eql(u8, arg, "--bundle-root")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            args.bundle_root = try allocator.dupe(u8, argv[idx]);
        } else if (std.mem.eql(u8, arg, "--mode")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            if (std.mem.eql(u8, argv[idx], "manifest")) {
                args.mode = .manifest;
            } else if (std.mem.eql(u8, argv[idx], "steps")) {
                args.mode = .steps;
            } else {
                return error.InvalidArgument;
            }
        } else if (std.mem.eql(u8, arg, "--cslc-executable")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            args.cslc_executable = try allocator.dupe(u8, argv[idx]);
        } else if (std.mem.eql(u8, arg, "--driver-executable-path")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            args.driver_executable_path = try allocator.dupe(u8, argv[idx]);
        } else if (std.mem.eql(u8, arg, "--help")) {
            printUsage();
            return error.HelpShown;
        } else {
            return error.InvalidArgument;
        }
    }

    if (args.input_path.len == 0) return error.InvalidArgument;
    if (args.bundle_root == null and args.output_path == null) return error.InvalidArgument;
    if (args.bundle_root != null and args.output_path != null) return error.InvalidArgument;
    return args;
}

fn ensureParent(path: []const u8) !void {
    if (std.fs.path.dirname(path)) |dir_name| {
        if (std.fs.path.isAbsolute(dir_name)) {
            var root = try std.fs.openDirAbsolute("/", .{});
            defer root.close();
            const relative = std.mem.trimLeft(u8, dir_name, "/");
            if (relative.len > 0) {
                try root.makePath(relative);
            }
        } else {
            try std.fs.cwd().makePath(dir_name);
        }
    }
}

fn readFileAllocAbsoluteAware(allocator: std.mem.Allocator, path: []const u8, max_bytes: usize) ![]u8 {
    const resolved_path = if (std.fs.path.isAbsolute(path))
        path
    else blk: {
        const cwd = try std.process.getCwdAlloc(allocator);
        break :blk try std.fs.path.join(allocator, &.{ cwd, path });
    };
    const file = try std.fs.openFileAbsolute(resolved_path, .{});
    defer file.close();
    return try file.readToEndAlloc(allocator, max_bytes);
}

fn createFileAbsoluteAware(path: []const u8) !std.fs.File {
    const resolved_path = if (std.fs.path.isAbsolute(path))
        path
    else blk: {
        const cwd = try std.process.getCwdAlloc(std.heap.page_allocator);
        defer std.heap.page_allocator.free(cwd);
        break :blk try std.fs.path.join(std.heap.page_allocator, &.{ cwd, path });
    };
    defer if (!std.fs.path.isAbsolute(path)) std.heap.page_allocator.free(resolved_path);
    return try std.fs.createFileAbsolute(resolved_path, .{ .truncate = true });
}

fn writeFile(path: []const u8, data: []const u8) !void {
    try ensureParent(path);
    const file = try createFileAbsoluteAware(path);
    defer file.close();
    try file.writeAll(data);
}

fn writeExecutableFile(path: []const u8, data: []const u8) !void {
    try ensureParent(path);
    const file = try createFileAbsoluteAware(path);
    defer file.close();
    try file.writeAll(data);
    try file.chmod(0o755);
}

fn parseBundleModelConfig(allocator: std.mem.Allocator, payload: []const u8) !?host.ModelConfig {
    const parsed = try std.json.parseFromSlice(BundleConfigJson, allocator, payload, .{
        .ignore_unknown_fields = true,
    });
    defer parsed.deinit();
    const model_config = parsed.value.modelConfig orelse return null;
    return .{
        .hidden_dim = model_config.hiddenDim,
        .num_heads = model_config.numHeads,
        .head_dim = model_config.headDim,
        .num_layers = model_config.numLayers,
        .vocab_size = model_config.vocabSize,
        .max_seq_len = model_config.maxSeqLen,
        .quant_format = parseQuantFormat(model_config.quantFormat) orelse return error.InvalidArgument,
        .ffn_expansion_factor = model_config.ffnExpansionFactor,
        .ffn_matrix_count = model_config.ffnMatrixCount,
        .ple_width = model_config.pleWidth,
        .ple_vocab_size = model_config.pleVocabSize,
    };
}

fn parseQuantFormat(raw: []const u8) ?host.ModelConfig.QuantFormat {
    if (std.mem.eql(u8, raw, "f16")) return .f16;
    if (std.mem.eql(u8, raw, "q4k")) return .q4k;
    if (std.mem.eql(u8, raw, "q8_0")) return .q8_0;
    return null;
}

fn buildCompileTargets(
    allocator: std.mem.Allocator,
    plan: host.HostPlan,
    out: *[MAX_KERNELS]host_plan.CompileTarget,
) ![]const host_plan.CompileTarget {
    var count: usize = 0;
    for (plan.kernels) |kernel| {
        if (count >= out.len) @panic("too many CSL compile targets");
        out[count] = .{
            .kernel_name = kernel.name,
            .layout_path = try std.fmt.allocPrint(allocator, "{s}/layout.csl", .{kernel.name}),
            .pe_program_path = try std.fmt.allocPrint(allocator, "{s}/pe_program.csl", .{kernel.name}),
        };
        count += 1;
    }
    return out[0..count];
}

fn buildStateBuffers(memory_plan: mem_plan.MemoryPlan, out: *[MAX_STATE_BUFFERS]host_runtime.StateBuffer) []const host_runtime.StateBuffer {
    var count: usize = 0;
    for (memory_plan.buffers[0..memory_plan.buffer_count]) |buffer| {
        const kind: ?host_runtime.StateBuffer.Kind = switch (buffer.kind) {
            .kv_cache => .kv_cache,
            .decode_position, .sliding_window => .position,
            .activation_scratch, .output_logits => .scratch,
            else => null,
        };
        if (kind == null) continue;
        if (count >= out.len) @panic("too many CSL state buffers");
        out[count] = .{
            .name = buffer.name,
            .kind = kind.?,
            .bytes_per_pe = buffer.bytes_per_pe,
        };
        count += 1;
    }
    return out[0..count];
}

fn emitHostPlanFile(path: []const u8, plan: host.HostPlan, targets: []const host_plan.CompileTarget, cslc_plan: host_plan.CslcPlan) !void {
    var buf: [HOST_PLAN_CAPACITY]u8 = undefined;
    var pos: usize = 0;
    try host_plan.emitHostPlanArtifactJson(&buf, &pos, plan, targets, cslc_plan);
    try host_plan.validateHostPlanArtifactJson(std.heap.page_allocator, buf[0..pos]);
    try writeFile(path, buf[0..pos]);
}

fn emitMemoryPlanFile(path: []const u8, memory: mem_plan.MemoryPlan) !void {
    var buf: [MEMORY_PLAN_CAPACITY]u8 = undefined;
    var pos: usize = 0;
    try mem_plan.emitPlanJson(&buf, &pos, memory);
    try writeFile(path, buf[0..pos]);
}

fn emitRuntimeConfigFile(path: []const u8, runtime: host_runtime.RuntimeConfig) !void {
    var buf: [RUNTIME_CONFIG_CAPACITY]u8 = undefined;
    var pos: usize = 0;
    try host_runtime.emitRuntimeConfigJson(&buf, &pos, runtime);
    try writeFile(path, buf[0..pos]);
}

fn emitSimulatorPlanFile(
    path: []const u8,
    runtime: host_runtime.RuntimeConfig,
    targets: []const host_plan.CompileTarget,
    driver: simulator.DriverConfig,
) !void {
    var buf: [SIMULATOR_PLAN_CAPACITY]u8 = undefined;
    var pos: usize = 0;
    try simulator.emitSimulatorPlanArtifactJson(&buf, &pos, runtime, targets, .{
        .host_plan_artifact_path = "host-plan.json",
        .runtime_config_path = "runtime-config.json",
        .compile_root_path = "compile",
        .stdout_path = "stdout.log",
        .stderr_path = "stderr.log",
        .trace_path = "trace.json",
    }, driver);
    try simulator.validateSimulatorPlanArtifactJson(std.heap.page_allocator, buf[0..pos]);
    try writeFile(path, buf[0..pos]);
}

fn emitLauncherFile(path: []const u8, driver: simulator.DriverConfig) !void {
    var buf: [LAUNCHER_CAPACITY]u8 = undefined;
    var pos: usize = 0;
    try simulator.emitLauncherScript(&buf, &pos, "simulator-plan.json", driver);
    try writeExecutableFile(path, buf[0..pos]);
}

fn defaultDriverPath(allocator: std.mem.Allocator, bundle_root: []const u8) ![]const u8 {
    _ = bundle_root;
    const cwd = try std.process.getCwdAlloc(allocator);
    defer allocator.free(cwd);
    const driver_abs = try std.fs.path.join(allocator, &.{ cwd, "tools", "csl_sdk_driver.py" });
    return driver_abs;
}

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    const args = parseArgs(allocator) catch |err| switch (err) {
        error.HelpShown => return,
        else => {
            printUsage();
            return err;
        },
    };

    const input_bytes = try readFileAllocAbsoluteAware(allocator, args.input_path, 1 << 20);

    var kernel_buf: [MAX_KERNELS]host.KernelSpec = undefined;
    var prefill_buf: [MAX_LAUNCHES]host.LaunchSpec = undefined;
    var decode_buf: [MAX_LAUNCHES]host.LaunchSpec = undefined;

    const plan = switch (args.mode) {
        .manifest => try exec_v1.lowerManifestExecutionToHostPlan(
            allocator,
            input_bytes,
            &kernel_buf,
            &prefill_buf,
            &decode_buf,
        ),
        .steps => try exec_v1.lowerJsonToHostPlan(
            allocator,
            input_bytes,
            &kernel_buf,
            &prefill_buf,
            &decode_buf,
        ),
    };

    var target_buf: [MAX_KERNELS]host_plan.CompileTarget = undefined;
    const targets = try buildCompileTargets(allocator, plan, &target_buf);
    const cslc_plan = try host_plan.makeCslcPlan(args.cslc_executable);

    if (args.bundle_root) |bundle_root| {
        const model_config = (try parseBundleModelConfig(allocator, input_bytes)) orelse return error.InvalidArgument;
        const memory = mem_plan.planMemory(model_config, plan, .{});
        var state_buffer_buf: [MAX_STATE_BUFFERS]host_runtime.StateBuffer = undefined;
        const state_buffers = buildStateBuffers(memory, &state_buffer_buf);
        const runtime = host_runtime.RuntimeConfig{
            .plan = plan,
            .config = model_config,
            .weight_mappings = &[_]host_runtime.WeightMapping{},
            .weight_mapping_count = 0,
            .state_buffers = state_buffers,
            .state_buffer_count = @as(u32, @intCast(state_buffers.len)),
            .memory_plan = memory,
        };
        const host_plan_path = try std.fs.path.join(allocator, &.{ bundle_root, "host-plan.json" });
        const memory_plan_path = try std.fs.path.join(allocator, &.{ bundle_root, "memory-plan.json" });
        const runtime_config_path = try std.fs.path.join(allocator, &.{ bundle_root, "runtime-config.json" });
        const simulator_plan_path = try std.fs.path.join(allocator, &.{ bundle_root, "simulator-plan.json" });
        const launcher_path = try std.fs.path.join(allocator, &.{ bundle_root, "launch-simulator.sh" });

        try emitHostPlanFile(host_plan_path, plan, targets, cslc_plan);
        try emitMemoryPlanFile(memory_plan_path, memory);
        try emitRuntimeConfigFile(runtime_config_path, runtime);

        const driver = simulator.DriverConfig{
            .executable_path = if (args.driver_executable_path) |value|
                value
            else
                try defaultDriverPath(allocator, bundle_root),
        };
        try emitSimulatorPlanFile(simulator_plan_path, runtime, targets, driver);
        try emitLauncherFile(launcher_path, driver);
        return;
    }

    try emitHostPlanFile(args.output_path.?, plan, targets, cslc_plan);
}
