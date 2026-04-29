const std = @import("std");
const wgsl = @import("doe_wgsl/mod.zig");
const exec_v1 = wgsl.emit_csl_exec_v1;
const host = wgsl.emit_csl_host;
const host_plan = wgsl.emit_csl_host_plan;
const host_runtime = wgsl.emit_csl_host_runtime;
const mem_plan = wgsl.emit_csl_mem_plan;
const simulator = wgsl.emit_csl_simulator;
const materialize = @import("csl_host_plan_materialize.zig");
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
    session: ?SessionJson = null,
    const ModelConfigJson = struct {
        hiddenDim: u32,
        numHeads: u32,
        headDim: u32,
        linearKeyHeadDim: ?u32 = null,
        linearValueHeadDim: ?u32 = null,
        linearConvKernelDim: ?u32 = null,
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
        partialRotaryFactor: f32 = 1.0,
        mropeSection: ?[3]u32 = null,
    };
    const SessionJson = struct {
        compute: ?ComputeJson = null,
        const ComputeJson = struct {
            defaults: ?DefaultsJson = null,
            const DefaultsJson = struct {
                activationDtype: ?[]const u8 = null,
            };
        };
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
// Linear-attention state is sharded across pe_y so per-PE state fits the
// WSE-3 48 KiB SRAM budget. value_dim is split into value_dim_per_pe rows
// per PE; key_dim is broadcast. output[d] only reduces over k, so each PE
// owns its d-block end-to-end with no cross-PE reduction.
const SSM_LINEAR_ATTENTION_STATE_SHARD_PES: u32 = 2;
const CHUNK_SHAPE = host_plan.BindingShape{ .elements = "chunk_size" };
const HIDDEN_SHAPE = host_plan.BindingShape{ .elements = "hidden_size" };
const SSM_TOKEN_CHANNEL_SHAPE = host_plan.BindingShape{ .elements = "num_tokens * channels" };
const SSM_CHANNEL_KERNEL_SHAPE = host_plan.BindingShape{ .elements = "channels * kernel_size" };
const SSM_CHANNEL_SHAPE = host_plan.BindingShape{ .elements = "channels" };
const SSM_KEY_SHAPE = host_plan.BindingShape{ .elements = "key_dim" };
const SSM_VALUE_SHAPE = host_plan.BindingShape{ .elements = "value_dim" };
const SSM_VALUE_PER_PE_SHAPE = host_plan.BindingShape{ .elements = "value_dim_per_pe" };
const SSM_STATE_SHAPE = host_plan.BindingShape{ .elements = "value_dim * key_dim" };
const SSM_STATE_PER_PE_SHAPE = host_plan.BindingShape{ .elements = "value_dim_per_pe * key_dim" };
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
const GATED_BINDINGS = [_]host_plan.BindingMetadata{
    .{ .symbol = "gate", .access = "read", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
    .{ .symbol = "input", .access = "read", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
    .{ .symbol = "output", .access = "read_write", .elem_type = "f32", .binding_shape = CHUNK_SHAPE, .per_pe_shape = CHUNK_SHAPE },
};
const L2_NORMALIZE_BINDINGS = [_]host_plan.BindingMetadata{
    .{ .symbol = "input", .access = "read", .elem_type = "f32", .binding_shape = HIDDEN_SHAPE, .per_pe_shape = HIDDEN_SHAPE },
    .{ .symbol = "output", .access = "read_write", .elem_type = "f32", .binding_shape = HIDDEN_SHAPE, .per_pe_shape = HIDDEN_SHAPE },
};
const CONV1D_DEPTHWISE_BINDINGS = [_]host_plan.BindingMetadata{
    .{ .symbol = "input", .access = "read", .elem_type = "f32", .binding_shape = SSM_TOKEN_CHANNEL_SHAPE, .per_pe_shape = SSM_TOKEN_CHANNEL_SHAPE },
    .{ .symbol = "weight", .access = "read", .elem_type = "f32", .binding_shape = SSM_CHANNEL_KERNEL_SHAPE, .per_pe_shape = SSM_CHANNEL_KERNEL_SHAPE, .weight_source = "runtime_weight_mapping" },
    .{ .symbol = "bias", .access = "read", .elem_type = "f32", .binding_shape = SSM_CHANNEL_SHAPE, .per_pe_shape = SSM_CHANNEL_SHAPE, .weight_source = "runtime_weight_mapping" },
    .{ .symbol = "output", .access = "read_write", .elem_type = "f32", .binding_shape = SSM_TOKEN_CHANNEL_SHAPE, .per_pe_shape = SSM_TOKEN_CHANNEL_SHAPE },
};
const LINEAR_ATTENTION_BINDINGS = [_]host_plan.BindingMetadata{
    .{ .symbol = "query", .access = "read", .elem_type = "f32", .binding_shape = SSM_VALUE_SHAPE, .per_pe_shape = SSM_VALUE_PER_PE_SHAPE },
    .{ .symbol = "key", .access = "read", .elem_type = "f32", .binding_shape = SSM_KEY_SHAPE, .per_pe_shape = SSM_KEY_SHAPE },
    .{ .symbol = "value", .access = "read", .elem_type = "f32", .binding_shape = SSM_KEY_SHAPE, .per_pe_shape = SSM_KEY_SHAPE },
    .{ .symbol = "gate", .access = "read", .elem_type = "f32", .binding_shape = SSM_VALUE_SHAPE, .per_pe_shape = SSM_VALUE_PER_PE_SHAPE },
    .{ .symbol = "linear_state", .access = "read_write", .elem_type = "f32", .binding_shape = SSM_STATE_SHAPE, .per_pe_shape = SSM_STATE_PER_PE_SHAPE },
    .{ .symbol = "output", .access = "read_write", .elem_type = "f32", .binding_shape = SSM_VALUE_SHAPE, .per_pe_shape = SSM_VALUE_PER_PE_SHAPE },
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
        .linear_key_head_dim = model_config.linearKeyHeadDim,
        .linear_value_head_dim = model_config.linearValueHeadDim,
        .linear_conv_kernel_dim = model_config.linearConvKernelDim,
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
        .partial_rotary_factor = model_config.partialRotaryFactor,
        .mrope_section = model_config.mropeSection,
    };
}
fn parseBundleActivationDtype(allocator: std.mem.Allocator, payload: []const u8) !?[]const u8 {
    const parsed = try std.json.parseFromSlice(BundleConfigJson, allocator, payload, .{
        .ignore_unknown_fields = true,
    });
    defer parsed.deinit();
    const session = parsed.value.session orelse return null;
    const compute = session.compute orelse return null;
    const defaults = compute.defaults orelse return null;
    return defaults.activationDtype;
}
// CSL activation-dtype admission for the bundle session.
//
// Door-level admission is permissive for the dtypes Doe has lowering shape
// for. f32 is the legacy lane and is fully supported. f16 is admitted as
// a Track-2 work-in-progress lane: this gate intentionally lets the
// session through, and individual op emit paths (`emit_kernel_body*.zig`)
// hold the closed-fail surface via their `requireElem(_, .f32)` checks.
// As Track-2 lands per-op f16 coverage, those op-level assertions are
// where the dtype routing widens.
//
// Anything other than f32 / f16 is still rejected at the door — the
// lowering surface has no shape for bf16 / int8 / etc. yet.
fn admitCslActivationDtype(dtype: ?[]const u8) !void {
    const raw = dtype orelse return;
    if (std.mem.eql(u8, raw, "f32")) return;
    if (std.mem.eql(u8, raw, "f16")) return;
    return error.InvalidArgument;
}
fn activationDtypeScalar(dtype: ?[]const u8) !wgsl.ir.ScalarType {
    const raw = dtype orelse return .f32;
    if (std.mem.eql(u8, raw, "f32")) return .f32;
    if (std.mem.eql(u8, raw, "f16")) return .f16;
    return error.InvalidArgument;
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
        .compile_blocked_reason = null,
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
    if (std.mem.eql(u8, pattern, "gelu_gated") or
        std.mem.eql(u8, pattern, "silu_gated") or
        std.mem.eql(u8, pattern, "sigmoid_gated"))
    {
        return .{ .target_phase = target_phase, .bindings = &GATED_BINDINGS };
    }
    if (std.mem.eql(u8, pattern, "l2_normalize")) {
        return .{ .target_phase = target_phase, .bindings = &L2_NORMALIZE_BINDINGS };
    }
    if (std.mem.eql(u8, pattern, "conv1d_depthwise")) {
        return .{ .target_phase = target_phase, .bindings = &CONV1D_DEPTHWISE_BINDINGS };
    }
    if (std.mem.eql(u8, pattern, "linear_attention")) {
        return .{ .target_phase = target_phase, .bindings = &LINEAR_ATTENTION_BINDINGS };
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
        const tile = if (is_ple) @as(u32, 16) else ceilDivU32(config.hidden_dim, 32);
        const block = if (is_ple) @as(u32, 16) else @as(u32, 32);
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
    } else if (std.mem.eql(u8, pattern, "gelu_gated") or
        std.mem.eql(u8, pattern, "silu_gated") or
        std.mem.eql(u8, pattern, "sigmoid_gated"))
    {
        try appendParam(allocator, &params, "width", row_width);
        try appendParam(allocator, &params, "height", row_height);
        try appendParam(allocator, &params, "chunk_size", config.hidden_dim);
    } else if (std.mem.eql(u8, pattern, "l2_normalize")) {
        try appendParam(allocator, &params, "width", row_width);
        try appendParam(allocator, &params, "height", row_height);
        try appendParam(allocator, &params, "hidden_size", config.linear_key_head_dim orelse @min(config.head_dim, 128));
    } else if (std.mem.eql(u8, pattern, "conv1d_depthwise")) {
        try appendParam(allocator, &params, "width", row_width);
        try appendParam(allocator, &params, "height", row_height);
        try appendParam(allocator, &params, "num_tokens", @min(config.max_seq_len, @as(u32, 4)));
        try appendParam(allocator, &params, "channels", config.linear_key_head_dim orelse @min(config.head_dim, 128));
        try appendParam(allocator, &params, "kernel_size", config.linear_conv_kernel_dim orelse 4);
    } else if (std.mem.eql(u8, pattern, "linear_attention")) {
        // value_dim is sharded across pe_y so per-PE state
        // (value_dim_per_pe * key_dim) fits the WSE-3 48 KiB SRAM budget.
        // No cross-PE reduction is needed: output[d] only sums over k.
        const value_dim = config.linear_value_head_dim orelse @min(config.head_dim, 128);
        const value_dim_per_pe = ceilDivU32(value_dim, SSM_LINEAR_ATTENTION_STATE_SHARD_PES);
        try appendParam(allocator, &params, "width", 1);
        try appendParam(allocator, &params, "height", SSM_LINEAR_ATTENTION_STATE_SHARD_PES);
        try appendParam(allocator, &params, "key_dim", config.linear_key_head_dim orelse @min(config.head_dim, 128));
        try appendParam(allocator, &params, "value_dim", value_dim);
        try appendParam(allocator, &params, "value_dim_per_pe", value_dim_per_pe);
    } else if (std.mem.eql(u8, pattern, "fused_gemv_dequant")) {
        const out_dim_per_pe = ceilDivU32(config.hidden_dim, plan.pe_grid_height);
        try appendParam(allocator, &params, "width", plan.pe_grid_width);
        try appendParam(allocator, &params, "height", plan.pe_grid_height);
        try appendParam(allocator, &params, "out_dim", config.hidden_dim);
        try appendParam(allocator, &params, "out_dim_per_pe", out_dim_per_pe);
        try appendParam(allocator, &params, "in_dim_per_pe", @min(config.hidden_dim, @as(u32, 512)));
        try appendParam(allocator, &params, "num_blocks_per_row", 2);
    } else if (std.mem.eql(u8, pattern, "kv_write")) {
        const slot_shard_pes = plan.pe_grid_height;
        try appendParam(allocator, &params, "width", config.num_heads);
        try appendParam(allocator, &params, "height", slot_shard_pes);
        try appendParam(allocator, &params, "head_dim", config.head_dim);
        try appendParam(allocator, &params, "max_seq_len", config.max_seq_len);
        try appendParam(allocator, &params, "slots_per_pe", ceilDivU32(config.max_seq_len, slot_shard_pes));
    } else if (std.mem.eql(u8, pattern, "attention_tiled")) {
        const q_len_per_pe = ceilDivU32(config.max_seq_len, plan.pe_grid_width);
        try appendParam(allocator, &params, "width", plan.pe_grid_width);
        try appendParam(allocator, &params, "height", 1);
        try appendParam(allocator, &params, "head_dim", config.head_dim);
        try appendParam(allocator, &params, "q_len", config.max_seq_len);
        try appendParam(allocator, &params, "q_len_per_pe", q_len_per_pe);
        try appendParam(allocator, &params, "block_size", @min(config.max_seq_len, @as(u32, 16)));
    } else if (std.mem.eql(u8, pattern, "attention_prefill_kv_axis_sharded")) {
        try appendParam(allocator, &params, "width", 512);
        try appendParam(allocator, &params, "height", 512);
        try appendParam(allocator, &params, "kv_len", config.max_seq_len);
        try appendParam(allocator, &params, "slots_per_pe", ceilDivU32(config.max_seq_len, 512));
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
    } else if (std.mem.eql(u8, pattern, "rope")) {
        const head_dim_f: f32 = @floatFromInt(config.head_dim);
        const num_pairs_f: f32 = head_dim_f * config.partial_rotary_factor / 2.0;
        const num_pairs: u32 = @intFromFloat(@round(num_pairs_f));
        try appendParam(allocator, &params, "width", plan.pe_grid_width);
        try appendParam(allocator, &params, "head_dim", config.head_dim);
        try appendParam(allocator, &params, "num_pairs", num_pairs);
        if (config.mrope_section) |s| {
            if (s[0] + s[1] + s[2] != num_pairs) return error.InvalidMRopeSection;
            try appendParam(allocator, &params, "mrope_t_pairs", s[0]);
            try appendParam(allocator, &params, "mrope_h_pairs", s[1]);
            try appendParam(allocator, &params, "mrope_w_pairs", s[2]);
        }
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
    const activation_dtype = try parseBundleActivationDtype(allocator, input_bytes);
    try admitCslActivationDtype(activation_dtype);
    const activation_elem = try activationDtypeScalar(activation_dtype);
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
        try materialize.materializeCompileSources(allocator, bundle_root, plan, activation_elem);
        try materialize.materializeTargetsMetadata(allocator, bundle_root, targets);
        try materialize.emitHostPlanFile(host_plan_path, plan, targets, cslc_plan);
        try materialize.emitMemoryPlanFile(memory_plan_path, memory);
        try materialize.emitRuntimeConfigFile(runtime_config_path, runtime);
        const driver = simulator.DriverConfig{
            .executable_path = if (args.driver_executable_path) |value|
                value
            else
                try materialize.defaultDriverPath(allocator, bundle_root),
        };
        try materialize.emitSimulatorPlanFile(simulator_plan_path, runtime, targets, driver);
        try materialize.emitLauncherFile(launcher_path, driver);
        return;
    }
    try materialize.emitHostPlanFile(args.output_path.?, plan, targets, cslc_plan);
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
test "csl activation dtype admission: f32 + f16 admitted at door, others rejected" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const payload =
        \\{
        \\  "session": {
        \\    "compute": {
        \\      "defaults": {
        \\        "activationDtype": "f16"
        \\      }
        \\    }
        \\  }
        \\}
    ;
    const dtype = try parseBundleActivationDtype(arena.allocator(), payload);
    try std.testing.expectEqualStrings("f16", dtype.?);
    // f16 is admitted at the door; per-op fail-closed lives in the
    // emit_kernel_body*.zig requireElem assertions until Track 2 lands
    // per-op f16 coverage.
    try admitCslActivationDtype(dtype);
    try admitCslActivationDtype("f32");
    try admitCslActivationDtype(null);
    try std.testing.expectError(error.InvalidArgument, admitCslActivationDtype("bf16"));
    try std.testing.expectError(error.InvalidArgument, admitCslActivationDtype("int8"));
    try std.testing.expectEqual(wgsl.ir.ScalarType.f16, try activationDtypeScalar(dtype));
    try std.testing.expectEqual(wgsl.ir.ScalarType.f32, try activationDtypeScalar(null));
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
test "buildCompileTargets uses Qwen linear SSM dims with state-sharded linear_attention" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const plan = host.HostPlan{
        .pe_grid_width = 16,
        .pe_grid_height = 1,
        .kernels = &[_]host.KernelSpec{
            .{ .name = "ssm_conv1d_depthwise", .pattern = "conv1d_depthwise", .count = 1 },
            .{ .name = "ssm_l2_normalize", .pattern = "l2_normalize", .count = 1 },
            .{ .name = "ssm_linear_attention", .pattern = "linear_attention", .count = 1 },
            .{ .name = "attn_prefill_kv_axis_sharded", .pattern = "attention_prefill_kv_axis_sharded", .count = 1 },
        },
        .prefill_launches = &[_]host.LaunchSpec{},
        .decode_launches = &[_]host.LaunchSpec{},
    };
    const config = host.ModelConfig{
        .hidden_dim = 5120,
        .num_heads = 24,
        .head_dim = 256,
        .linear_key_head_dim = 96,
        .linear_value_head_dim = 64,
        .linear_conv_kernel_dim = 7,
        .num_layers = 64,
        .vocab_size = 248320,
        .max_seq_len = 4096,
        .quant_format = .q4k,
    };
    var target_buf: [MAX_COMPILE_TARGETS]host_plan.CompileTarget = undefined;
    const targets = try buildCompileTargets(arena.allocator(), plan, config, &target_buf);
    try std.testing.expectEqual(@as(usize, 4), targets.len);
    try std.testing.expectEqual(@as(u32, 96), targets[0].compile_params[3].value);
    try std.testing.expectEqual(@as(u32, 7), targets[0].compile_params[4].value);
    try std.testing.expectEqual(@as(u32, 96), targets[1].compile_params[2].value);
    // linear_attention: width=1, height=2 (state shard), key_dim=96, value_dim=64, value_dim_per_pe=32
    try std.testing.expectEqual(@as(u32, 1), targets[2].compile_params[0].value);
    try std.testing.expectEqual(@as(u32, SSM_LINEAR_ATTENTION_STATE_SHARD_PES), targets[2].compile_params[1].value);
    try std.testing.expectEqual(@as(u32, 96), targets[2].compile_params[2].value);
    try std.testing.expectEqual(@as(u32, 64), targets[2].compile_params[3].value);
    try std.testing.expectEqual(@as(u32, 32), targets[2].compile_params[4].value);
    // Both former typed blockers are removed; manifest-shape compile lane is open for cslc.
    try std.testing.expect(targets[2].compile_blocked_reason == null);
    try std.testing.expect(targets[3].compile_blocked_reason == null);
}
test "parseBundleWeightMappings leaves absent mapping input empty" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const mappings = try parseBundleWeightMappings(arena.allocator(), "{}");
    try std.testing.expectEqual(@as(usize, 0), mappings.len);
}
