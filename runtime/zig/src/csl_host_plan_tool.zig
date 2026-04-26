const std = @import("std");
const wgsl = @import("doe_wgsl/mod.zig");
const exec_v1 = wgsl.emit_csl_exec_v1;
const host = wgsl.emit_csl_host;
const host_plan = wgsl.emit_csl_host_plan;
const host_runtime = wgsl.emit_csl_host_runtime;
const mem_plan = wgsl.emit_csl_mem_plan;
const simulator = wgsl.emit_csl_simulator;
const compile_source = @import("doe_wgsl/emit_csl_host_compile_source.zig");
const pe_program_metadata = @import("csl_pe_program_metadata.zig");

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
        globalHeadDim: ?u32 = null,
        numKeyValueHeads: ?u32 = null,
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
const PHASE_TARGET_SUFFIXES = [_][]const u8{ "prefill", "decode" };
const PHASE_SPECIALIZED_KERNELS = [_][]const u8{ "rmsnorm", "residual", "gelu" };
const PHASE_COMPILE_TARGET_COUNT: usize = PHASE_TARGET_SUFFIXES.len * PHASE_SPECIALIZED_KERNELS.len;
const MAX_COMPILE_TARGETS: usize = MAX_KERNELS + PHASE_COMPILE_TARGET_COUNT;
const MAX_LAUNCHES: usize = 1024;
const MAX_STATE_BUFFERS: usize = 16;
const SHA256_HEX_LEN: usize = 64;
const HOST_PLAN_CAPACITY: usize = 128 * 1024;
const RUNTIME_CONFIG_CAPACITY: usize = 128 * 1024;
const MEMORY_PLAN_CAPACITY: usize = 64 * 1024;
const SIMULATOR_PLAN_CAPACITY: usize = 64 * 1024;
const LAUNCHER_CAPACITY: usize = 8 * 1024;
const PE_PROGRAM_METADATA_CAPACITY: usize = 16 * 1024;
const COMPILE_ROOT_NAME: []const u8 = "compile";

const CHUNK_SHAPE = host_plan.BindingShape{ .elements = "chunk_size" };
const HIDDEN_SHAPE = host_plan.BindingShape{ .elements = "hidden_size" };
const SUMMA_A_SHAPE = host_plan.BindingShape{ .elements = "Mt * Kt" };
const SUMMA_B_SHAPE = host_plan.BindingShape{ .elements = "Kt * Nt" };
const SUMMA_C_SHAPE = host_plan.BindingShape{ .elements = "Mt * Nt" };

const RMSNORM_BINDINGS = [_]host_plan.BindingMetadata{
    .{ .symbol = "input", .access = "read", .elem_type = "f32", .binding_shape = HIDDEN_SHAPE, .per_pe_shape = HIDDEN_SHAPE },
    .{ .symbol = "weight", .access = "read", .elem_type = "f32", .binding_shape = HIDDEN_SHAPE, .per_pe_shape = HIDDEN_SHAPE, .weight_source = "runtime_weight_mapping" },
    .{ .symbol = "output", .access = "read_write", .elem_type = "f32", .binding_shape = HIDDEN_SHAPE, .per_pe_shape = HIDDEN_SHAPE },
};

const RESIDUAL_BINDINGS = [_]host_plan.BindingMetadata{
    .{ .symbol = "input", .access = "read", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
    .{ .symbol = "residual", .access = "read", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
    .{ .symbol = "output", .access = "read_write", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
};

const GELU_BINDINGS = [_]host_plan.BindingMetadata{
    .{ .symbol = "input", .access = "read", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
    .{ .symbol = "output", .access = "read_write", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
};

const TILED_BINDINGS = [_]host_plan.BindingMetadata{
    .{
        .symbol = "a",
        .access = "read",
        .elem_type = "f32",
        .binding_shape = SUMMA_A_SHAPE,
        .per_pe_shape = SUMMA_A_SHAPE,
        .staging_transform = .{ .kind = "logical_matrix_to_summa_tiles", .matrix_role = "a" },
    },
    .{
        .symbol = "b",
        .access = "read",
        .elem_type = "f32",
        .binding_shape = SUMMA_B_SHAPE,
        .per_pe_shape = SUMMA_B_SHAPE,
        .staging_transform = .{ .kind = "weight_matrix_to_summa_tiles", .matrix_role = "b" },
        .weight_source = "runtime_weight_mapping",
    },
    .{
        .symbol = "c",
        .access = "read_write",
        .elem_type = "f32",
        .binding_shape = SUMMA_C_SHAPE,
        .per_pe_shape = SUMMA_C_SHAPE,
        .detile_transform = .{ .kind = "summa_tiles_to_logical_matrix", .matrix_role = "c", .rows_from_input = "a" },
    },
};

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
        .global_head_dim = model_config.globalHeadDim,
        .num_key_value_heads = model_config.numKeyValueHeads,
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

fn parseWeightDtype(raw: []const u8) ?host_runtime.WeightMapping.Dtype {
    if (std.mem.eql(u8, raw, "f16")) return .f16;
    if (std.mem.eql(u8, raw, "u8_q4k")) return .u8_q4k;
    if (std.mem.eql(u8, raw, "u8_q8")) return .u8_q8;
    return null;
}

fn jsonObject(value: std.json.Value) !std.json.ObjectMap {
    return switch (value) {
        .object => |object| object,
        else => error.InvalidArgument,
    };
}

fn jsonArray(value: std.json.Value) !std.json.Array {
    return switch (value) {
        .array => |array| array,
        else => error.InvalidArgument,
    };
}

fn jsonString(value: std.json.Value) ![]const u8 {
    return switch (value) {
        .string => |string| string,
        else => error.InvalidArgument,
    };
}

fn jsonU32(value: std.json.Value) !u32 {
    return switch (value) {
        .integer => |integer| std.math.cast(u32, integer) orelse error.InvalidArgument,
        else => error.InvalidArgument,
    };
}

fn jsonU64(value: std.json.Value) !u64 {
    return switch (value) {
        .integer => |integer| std.math.cast(u64, integer) orelse error.InvalidArgument,
        else => error.InvalidArgument,
    };
}

fn optionalJsonStringDup(allocator: std.mem.Allocator, value: ?std.json.Value) !?[]const u8 {
    const raw = value orelse return null;
    return switch (raw) {
        .null => null,
        else => try allocator.dupe(u8, try jsonString(raw)),
    };
}

fn optionalJsonU32(value: ?std.json.Value) !?u32 {
    const raw = value orelse return null;
    return switch (raw) {
        .null => null,
        else => try jsonU32(raw),
    };
}

fn parseSha256(raw: []const u8) ![]const u8 {
    if (raw.len != SHA256_HEX_LEN) return error.InvalidArgument;
    for (raw) |c| {
        const is_digit = c >= '0' and c <= '9';
        const is_lower_hex = c >= 'a' and c <= 'f';
        if (!is_digit and !is_lower_hex) return error.InvalidArgument;
    }
    return raw;
}

fn parseWeightPeRange(value: std.json.Value) !struct { start: u32, end: u32 } {
    const array = try jsonArray(value);
    if (array.items.len != 2) return error.InvalidArgument;
    const start = try jsonU32(array.items[0]);
    const end = try jsonU32(array.items[1]);
    if (end <= start) return error.InvalidArgument;
    return .{ .start = start, .end = end };
}

fn parseWeightShape(allocator: std.mem.Allocator, value: std.json.Value) ![]const u64 {
    const array = try jsonArray(value);
    if (array.items.len == 0) return error.InvalidArgument;
    const shape = try allocator.alloc(u64, array.items.len);
    errdefer allocator.free(shape);
    for (array.items, 0..) |item, idx| {
        const dim = try jsonU64(item);
        if (dim == 0) return error.InvalidArgument;
        shape[idx] = dim;
    }
    return shape;
}

fn parseWeightQuant(allocator: std.mem.Allocator, value: std.json.Value) !host_runtime.WeightMapping.QuantMetadata {
    const object = try jsonObject(value);
    return .{
        .format = try allocator.dupe(u8, try jsonString(object.get("format") orelse return error.InvalidArgument)),
        .storage_dtype = try allocator.dupe(u8, try jsonString(object.get("storageDtype") orelse return error.InvalidArgument)),
        .source_dtype = try optionalJsonStringDup(allocator, object.get("sourceDtype")),
        .block_size_elements = try optionalJsonU32(object.get("blockSizeElements")),
        .block_size_bytes = try optionalJsonU32(object.get("blockSizeBytes")),
        .encoding = try optionalJsonStringDup(allocator, object.get("encoding")),
    };
}

fn parseBundleWeightMappings(
    allocator: std.mem.Allocator,
    payload: []const u8,
) ![]const host_runtime.WeightMapping {
    const parsed = try std.json.parseFromSlice(std.json.Value, allocator, payload, .{});
    defer parsed.deinit();

    const root = try jsonObject(parsed.value);
    const mappings_value = root.get("weightMappings") orelse return &.{};
    const mappings_array = try jsonArray(mappings_value);
    if (mappings_array.items.len == 0) return &.{};

    const mappings = try allocator.alloc(host_runtime.WeightMapping, mappings_array.items.len);
    errdefer allocator.free(mappings);

    for (mappings_array.items, 0..) |mapping_value, idx| {
        const mapping = try jsonObject(mapping_value);
        const pe_range = try parseWeightPeRange(mapping.get("peRange") orelse return error.InvalidArgument);
        const dtype_text = try jsonString(mapping.get("dtype") orelse return error.InvalidArgument);
        mappings[idx] = .{
            .shard_name = try allocator.dupe(u8, try jsonString(mapping.get("shard") orelse return error.InvalidArgument)),
            .shard_path = try allocator.dupe(u8, try jsonString(mapping.get("path") orelse return error.InvalidArgument)),
            .shard_sha256 = try allocator.dupe(u8, try parseSha256(try jsonString(mapping.get("sha256") orelse return error.InvalidArgument))),
            .pe_buffer = try allocator.dupe(u8, try jsonString(mapping.get("peBuffer") orelse return error.InvalidArgument)),
            .pe_start = pe_range.start,
            .pe_end = pe_range.end,
            .dtype = parseWeightDtype(dtype_text) orelse return error.InvalidArgument,
            .tensor_name = try allocator.dupe(u8, try jsonString(mapping.get("tensor") orelse return error.InvalidArgument)),
            .tensor_offset_bytes = try jsonU64(mapping.get("offsetBytes") orelse return error.InvalidArgument),
            .tensor_shape = try parseWeightShape(allocator, mapping.get("shape") orelse return error.InvalidArgument),
            .quant = try parseWeightQuant(allocator, mapping.get("quant") orelse return error.InvalidArgument),
        };
    }

    return mappings;
}

fn buildCompileTargets(
    allocator: std.mem.Allocator,
    plan: host.HostPlan,
    model_config: ?host.ModelConfig,
    out: *[MAX_COMPILE_TARGETS]host_plan.CompileTarget,
) ![]const host_plan.CompileTarget {
    var count: usize = 0;
    for (plan.kernels) |kernel| {
        try appendCompileTarget(allocator, plan, model_config, out, &count, kernel.name, kernel.name, kernel.pattern, null);
        if (isPhaseSpecializedKernel(kernel.name)) {
            for (PHASE_TARGET_SUFFIXES) |suffix| {
                const phase_name = try std.fmt.allocPrint(allocator, "{s}_{s}", .{ kernel.name, suffix });
                try appendCompileTarget(allocator, plan, model_config, out, &count, phase_name, kernel.name, kernel.pattern, suffix);
            }
        }
    }
    return out[0..count];
}

fn appendCompileTarget(
    allocator: std.mem.Allocator,
    plan: host.HostPlan,
    model_config: ?host.ModelConfig,
    out: *[MAX_COMPILE_TARGETS]host_plan.CompileTarget,
    count: *usize,
    target_name: []const u8,
    source_name: []const u8,
    pattern: []const u8,
    phase: ?[]const u8,
) !void {
    if (count.* >= out.len) @panic("too many CSL compile targets");
    out[count.*] = .{
        .kernel_name = target_name,
        .layout_path = try std.fmt.allocPrint(allocator, "{s}/layout.csl", .{source_name}),
        .pe_program_path = try std.fmt.allocPrint(allocator, "{s}/pe_program.csl", .{source_name}),
        .metadata = compileTargetMetadata(pattern, phase orelse "base"),
        .compile_params = try compileTargetParams(allocator, plan, model_config, target_name, pattern, phase),
        .phase = phase,
        .base_kernel = if (phase != null) source_name else null,
    };
    count.* += 1;
}

fn compileTargetMetadata(pattern: []const u8, target_phase: []const u8) ?host_plan.CompileTargetMetadata {
    if (std.mem.eql(u8, pattern, "rms_norm") or std.mem.eql(u8, pattern, "reduction")) {
        return .{ .target_phase = target_phase, .bindings = &RMSNORM_BINDINGS };
    }
    if (std.mem.eql(u8, pattern, "residual")) {
        return .{ .target_phase = target_phase, .bindings = &RESIDUAL_BINDINGS };
    }
    if (std.mem.eql(u8, pattern, "gelu")) {
        return .{ .target_phase = target_phase, .bindings = &GELU_BINDINGS };
    }
    if (std.mem.eql(u8, pattern, "tiled_matmul")) {
        return .{ .target_phase = target_phase, .bindings = &TILED_BINDINGS };
    }
    return null;
}

fn compileTargetParams(
    allocator: std.mem.Allocator,
    plan: host.HostPlan,
    model_config: ?host.ModelConfig,
    target_name: []const u8,
    pattern: []const u8,
    phase: ?[]const u8,
) ![]const host_plan.CompileParam {
    const config = model_config orelse return &.{};
    var params = try std.ArrayList(host_plan.CompileParam).initCapacity(allocator, 0);
    const is_decode = phase != null and std.mem.eql(u8, phase.?, "decode");
    const row_width = if (is_decode) @as(u32, 1) else plan.pe_grid_width;
    const row_height: u32 = 1;

    if (std.mem.eql(u8, pattern, "gather")) {
        const vocab = if (std.mem.startsWith(u8, target_name, "ple_"))
            config.ple_vocab_size orelse config.vocab_size
        else
            config.vocab_size;
        const hidden = if (std.mem.startsWith(u8, target_name, "ple_"))
            config.ple_width orelse config.hidden_dim
        else
            config.hidden_dim;
        const pe_count = @max(@as(u32, 1), plan.pe_grid_width * plan.pe_grid_height);
        try appendParam(allocator, &params, "width", plan.pe_grid_width);
        try appendParam(allocator, &params, "height", plan.pe_grid_height);
        try appendParam(allocator, &params, "hidden_size", hidden);
        try appendParam(allocator, &params, "hidden_per_pe", ceilDivU32(hidden, plan.pe_grid_height));
        try appendParam(allocator, &params, "rows_per_pe", ceilDivU32(vocab, pe_count));
        try appendParam(allocator, &params, "num_tokens", @min(config.max_seq_len, @as(u32, 16)));
        try appendParam(allocator, &params, "tokens_per_chunk", @min(config.max_seq_len, @as(u32, 16)));
    } else if (std.mem.eql(u8, pattern, "tiled_matmul")) {
        const is_ple = std.mem.startsWith(u8, target_name, "ple_");
        const tile = if (is_ple) @as(u32, 16) else ceilDivU32(config.hidden_dim, 64);
        const block = if (is_ple) @as(u32, 16) else @as(u32, 64);
        try appendParam(allocator, &params, "width", tile);
        try appendParam(allocator, &params, "height", tile);
        try appendParam(allocator, &params, "P", tile);
        try appendParam(allocator, &params, "Mt", block);
        try appendParam(allocator, &params, "Kt", block);
        try appendParam(allocator, &params, "Nt", block);
    } else if (std.mem.eql(u8, pattern, "rms_norm") or
        std.mem.eql(u8, pattern, "reduction"))
    {
        try appendParam(allocator, &params, "width", row_width);
        try appendParam(allocator, &params, "height", row_height);
        try appendParam(allocator, &params, "hidden_size", config.hidden_dim);
    } else if (std.mem.eql(u8, pattern, "residual") or
        std.mem.eql(u8, pattern, "gelu") or
        std.mem.eql(u8, pattern, "element_wise"))
    {
        try appendParam(allocator, &params, "width", row_width);
        try appendParam(allocator, &params, "height", row_height);
        try appendParam(allocator, &params, "chunk_size", config.hidden_dim);
    } else if (std.mem.eql(u8, pattern, "fused_gemv_dequant")) {
        const out_dim_per_pe = ceilDivU32(config.hidden_dim, plan.pe_grid_height);
        try appendParam(allocator, &params, "width", plan.pe_grid_width);
        try appendParam(allocator, &params, "height", plan.pe_grid_height);
        try appendParam(allocator, &params, "out_dim", config.hidden_dim);
        try appendParam(allocator, &params, "out_dim_per_pe", out_dim_per_pe);
        try appendParam(allocator, &params, "in_dim_per_pe", @min(config.hidden_dim, @as(u32, 512)));
        try appendParam(allocator, &params, "num_blocks_per_row", 2);
    } else if (std.mem.eql(u8, pattern, "kv_write")) {
        try appendParam(allocator, &params, "width", config.num_heads);
        try appendParam(allocator, &params, "height", 1);
        try appendParam(allocator, &params, "head_dim", config.head_dim);
        try appendParam(allocator, &params, "max_seq_len", config.max_seq_len);
    } else if (std.mem.eql(u8, pattern, "attention_tiled")) {
        const q_len_per_pe = ceilDivU32(config.max_seq_len, plan.pe_grid_width);
        try appendParam(allocator, &params, "width", plan.pe_grid_width);
        try appendParam(allocator, &params, "height", 1);
        try appendParam(allocator, &params, "head_dim", config.head_dim);
        try appendParam(allocator, &params, "q_len", config.max_seq_len);
        try appendParam(allocator, &params, "q_len_per_pe", q_len_per_pe);
        try appendParam(allocator, &params, "block_size", @min(config.max_seq_len, @as(u32, 16)));
    } else if (std.mem.eql(u8, pattern, "attention_decode")) {
        try appendParam(allocator, &params, "width", plan.pe_grid_width);
        try appendParam(allocator, &params, "height", 1);
        try appendParam(allocator, &params, "head_dim", config.head_dim);
        try appendParam(allocator, &params, "kv_chunk", ceilDivU32(config.max_seq_len, plan.pe_grid_width));
    } else if (std.mem.eql(u8, pattern, "sample")) {
        const width = ceilDivU32(config.vocab_size, 1024);
        try appendParam(allocator, &params, "width", width);
        try appendParam(allocator, &params, "height", 1);
        try appendParam(allocator, &params, "chunk_size", ceilDivU32(config.vocab_size, width));
    }
    return try params.toOwnedSlice(allocator);
}

fn appendParam(
    allocator: std.mem.Allocator,
    params: *std.ArrayList(host_plan.CompileParam),
    name: []const u8,
    value: u32,
) !void {
    try params.append(allocator, .{
        .name = name,
        .value = @max(@as(u32, 1), value),
    });
}

fn ceilDivU32(lhs: u32, rhs: u32) u32 {
    return (lhs + rhs - 1) / rhs;
}

fn isPhaseSpecializedKernel(name: []const u8) bool {
    for (PHASE_SPECIALIZED_KERNELS) |kernel_name| {
        if (std.mem.eql(u8, name, kernel_name)) return true;
    }
    return false;
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
        .compile_root_path = COMPILE_ROOT_NAME,
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

fn materializeTargetsMetadata(
    allocator: std.mem.Allocator,
    bundle_root: []const u8,
    targets: []const host_plan.CompileTarget,
) !void {
    var descriptors: [MAX_COMPILE_TARGETS]pe_program_metadata.TargetDescriptor = undefined;
    var idx: usize = 0;
    for (targets) |target| {
        descriptors[idx] = .{
            .name = target.kernel_name,
            .base_kernel = target.base_kernel orelse target.kernel_name,
            .phase = target.phase,
            .layout = target.layout_path,
            .pe_program = target.pe_program_path,
        };
        idx += 1;
    }
    const path = try std.fs.path.join(
        allocator,
        &.{ bundle_root, COMPILE_ROOT_NAME, "targets.metadata.json" },
    );
    var buf: [PE_PROGRAM_METADATA_CAPACITY]u8 = undefined;
    var stream = std.io.fixedBufferStream(&buf);
    try pe_program_metadata.emitTargetsJson(descriptors[0..idx], stream.writer());
    try writeFile(path, stream.getWritten());
}

fn materializeCompileSources(
    allocator: std.mem.Allocator,
    bundle_root: []const u8,
    plan: host.HostPlan,
) !void {
    var csl_buf: [wgsl.MAX_CSL_OUTPUT]u8 = undefined;
    for (plan.kernels) |kernel| {
        const sections = try compile_source.emitPatternSections(allocator, kernel.pattern, &csl_buf);

        const layout_path = try std.fs.path.join(
            allocator,
            &.{ bundle_root, COMPILE_ROOT_NAME, kernel.name, "layout.csl" },
        );
        const pe_program_path = try std.fs.path.join(
            allocator,
            &.{ bundle_root, COMPILE_ROOT_NAME, kernel.name, "pe_program.csl" },
        );
        const metadata_path = try std.fs.path.join(
            allocator,
            &.{ bundle_root, COMPILE_ROOT_NAME, kernel.name, "pe_program.metadata.json" },
        );
        const layout_metadata_path = try std.fs.path.join(
            allocator,
            &.{ bundle_root, COMPILE_ROOT_NAME, kernel.name, "layout.metadata.json" },
        );

        try writeFile(layout_path, sections.layout);
        try writeFile(pe_program_path, sections.pe_program);
        try emitPeProgramMetadataFile(metadata_path, sections.pe_program);
        try emitLayoutMetadataFile(layout_metadata_path, sections.layout);
    }
}

fn emitPeProgramMetadataFile(path: []const u8, pe_program_source: []const u8) !void {
    var buf: [PE_PROGRAM_METADATA_CAPACITY]u8 = undefined;
    var stream = std.io.fixedBufferStream(&buf);
    try pe_program_metadata.emitJson(pe_program_source, stream.writer());
    try writeFile(path, stream.getWritten());
}

fn emitLayoutMetadataFile(path: []const u8, layout_source: []const u8) !void {
    var buf: [PE_PROGRAM_METADATA_CAPACITY]u8 = undefined;
    var stream = std.io.fixedBufferStream(&buf);
    try pe_program_metadata.emitLayoutJson(layout_source, stream.writer());
    try writeFile(path, stream.getWritten());
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

    const model_config = (try parseBundleModelConfig(allocator, input_bytes));
    var target_buf: [MAX_COMPILE_TARGETS]host_plan.CompileTarget = undefined;
    const targets = try buildCompileTargets(allocator, plan, model_config, &target_buf);
    const cslc_plan = try host_plan.makeCslcPlan(args.cslc_executable);

    if (args.bundle_root) |bundle_root| {
        const resolved_model_config = model_config orelse return error.InvalidArgument;
        const weight_mappings = try parseBundleWeightMappings(allocator, input_bytes);
        const memory = mem_plan.planMemory(resolved_model_config, plan, .{});
        var state_buffer_buf: [MAX_STATE_BUFFERS]host_runtime.StateBuffer = undefined;
        const state_buffers = buildStateBuffers(memory, &state_buffer_buf);
        const runtime = host_runtime.RuntimeConfig{
            .plan = plan,
            .config = resolved_model_config,
            .weight_mappings = weight_mappings,
            .weight_mapping_count = @as(u32, @intCast(weight_mappings.len)),
            .state_buffers = state_buffers,
            .state_buffer_count = @as(u32, @intCast(state_buffers.len)),
            .memory_plan = memory,
        };
        const host_plan_path = try std.fs.path.join(allocator, &.{ bundle_root, "host-plan.json" });
        const memory_plan_path = try std.fs.path.join(allocator, &.{ bundle_root, "memory-plan.json" });
        const runtime_config_path = try std.fs.path.join(allocator, &.{ bundle_root, "runtime-config.json" });
        const simulator_plan_path = try std.fs.path.join(allocator, &.{ bundle_root, "simulator-plan.json" });
        const launcher_path = try std.fs.path.join(allocator, &.{ bundle_root, "launch-simulator.sh" });

        try materializeCompileSources(allocator, bundle_root, plan);
        try materializeTargetsMetadata(allocator, bundle_root, targets);
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

test "parseBundleWeightMappings preserves artifact-backed RDRR tensor metadata" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const payload =
        \\{
        \\  "weightMappings": [
        \\    {
        \\      "shard": "shard_00038.bin",
        \\      "path": "/models/gemma/shard_00038.bin",
        \\      "sha256": "6a0e8ecfb1190554392143f79434839b629ee9284a3fd643d84cb62522a0cdcd",
        \\      "peBuffer": "weights_q",
        \\      "peRange": [0, 16],
        \\      "dtype": "u8_q4k",
        \\      "tensor": "layer.0.self_attn.q_proj",
        \\      "offsetBytes": 2550136832,
        \\      "shape": [1536, 1536],
        \\      "quant": {
        \\        "format": "Q4_K_M",
        \\        "storageDtype": "uint8",
        \\        "sourceDtype": "float16",
        \\        "blockSizeElements": 256,
        \\        "blockSizeBytes": 144,
        \\        "encoding": "rdrr_int4ple"
        \\      }
        \\    }
        \\  ]
        \\}
    ;

    const mappings = try parseBundleWeightMappings(arena.allocator(), payload);
    try std.testing.expectEqual(@as(usize, 1), mappings.len);
    try std.testing.expectEqualStrings("shard_00038.bin", mappings[0].shard_name);
    try std.testing.expectEqualStrings("/models/gemma/shard_00038.bin", mappings[0].shard_path);
    try std.testing.expectEqualStrings("layer.0.self_attn.q_proj", mappings[0].tensor_name);
    try std.testing.expectEqual(@as(u64, 2550136832), mappings[0].tensor_offset_bytes);
    try std.testing.expectEqual(@as(u64, 1536), mappings[0].tensor_shape[0]);
    try std.testing.expectEqual(@as(u64, 1536), mappings[0].tensor_shape[1]);
    try std.testing.expectEqualStrings("Q4_K_M", mappings[0].quant.format);
    try std.testing.expectEqualStrings("rdrr_int4ple", mappings[0].quant.encoding.?);
}

test "buildCompileTargets emits phase variants for elementwise kernels" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const plan = host.HostPlan{
        .pe_grid_width = 16,
        .pe_grid_height = 1,
        .kernels = &[_]host.KernelSpec{
            .{ .name = "rmsnorm", .pattern = "element_wise", .count = 1 },
            .{ .name = "sample", .pattern = "sample", .count = 1 },
        },
        .prefill_launches = &[_]host.LaunchSpec{},
        .decode_launches = &[_]host.LaunchSpec{},
    };
    var target_buf: [MAX_COMPILE_TARGETS]host_plan.CompileTarget = undefined;

    const targets = try buildCompileTargets(arena.allocator(), plan, null, &target_buf);

    try std.testing.expectEqual(@as(usize, 4), targets.len);
    try std.testing.expectEqualStrings("rmsnorm", targets[0].kernel_name);
    try std.testing.expectEqualStrings("rmsnorm/layout.csl", targets[0].layout_path);
    try std.testing.expectEqualStrings("rmsnorm_prefill", targets[1].kernel_name);
    try std.testing.expectEqualStrings("rmsnorm/layout.csl", targets[1].layout_path);
    try std.testing.expectEqualStrings("rmsnorm_decode", targets[2].kernel_name);
    try std.testing.expectEqualStrings("rmsnorm/pe_program.csl", targets[2].pe_program_path);
    try std.testing.expectEqualStrings("sample", targets[3].kernel_name);
}

test "buildCompileTargets attaches structured binding metadata" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const plan = host.HostPlan{
        .pe_grid_width = 16,
        .pe_grid_height = 1,
        .kernels = &[_]host.KernelSpec{
            .{ .name = "residual", .pattern = "residual", .count = 1 },
            .{ .name = "tiled", .pattern = "tiled_matmul", .count = 1 },
        },
        .prefill_launches = &[_]host.LaunchSpec{},
        .decode_launches = &[_]host.LaunchSpec{},
    };
    var target_buf: [MAX_COMPILE_TARGETS]host_plan.CompileTarget = undefined;

    const targets = try buildCompileTargets(arena.allocator(), plan, null, &target_buf);

    try std.testing.expectEqual(@as(usize, 4), targets.len);
    const residual_metadata = targets[0].metadata.?;
    try std.testing.expectEqualStrings("base", residual_metadata.target_phase);
    try std.testing.expectEqual(@as(usize, 3), residual_metadata.bindings.len);
    try std.testing.expectEqualStrings("residual", residual_metadata.bindings[1].symbol);
    try std.testing.expectEqualStrings("prefill", targets[1].metadata.?.target_phase);
    try std.testing.expectEqualStrings("decode", targets[2].metadata.?.target_phase);

    const tiled_metadata = targets[3].metadata.?;
    try std.testing.expectEqual(@as(usize, 3), tiled_metadata.bindings.len);
    try std.testing.expectEqualStrings("b", tiled_metadata.bindings[1].symbol);
    try std.testing.expectEqualStrings(
        "runtime_weight_mapping",
        tiled_metadata.bindings[1].weight_source.?,
    );
    try std.testing.expectEqualStrings(
        "summa_tiles_to_logical_matrix",
        tiled_metadata.bindings[2].detile_transform.?.kind,
    );
}

test "parseBundleWeightMappings leaves absent mapping input empty" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const mappings = try parseBundleWeightMappings(arena.allocator(), "{}");
    try std.testing.expectEqual(@as(usize, 0), mappings.len);
}
