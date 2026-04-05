// emit_csl_exec_v1.zig — Doppler execution-v1 → HostPlan lowering.
//
// Parses Doppler's execution-v1 step tuples and constructs an explicit
// HostPlan that emit_csl_host.zig can render into compilation manifests
// and Python runner scaffolds.
//
// Execution-v1 format (JSON):
//   {
//     "grid": { "width": 32, "height": 4 },
//     "eosTokenId": 1,
//     "steps": [
//       { "phase": "prefill", "op": "embed", "kernelKey": "embed_gather" },
//       { "phase": "decode", "op": "sample", "kernelKey": "sampler" }
//     ]
//   }
//
// Step tuples are also accepted for bootstrap contracts:
//   [phase, op, kernelKey, weightsKey?, kind?]
//
// This module maps op names to KernelSpec patterns and orders them
// into prefill and decode launch sequences.

const std = @import("std");
const host = @import("emit_csl_host.zig");
const host_plan = @import("emit_csl_host_plan.zig");

pub const LowerError = error{
    OutputTooLarge,
    InvalidIr,
    InvalidJson,
    UnknownOp,
    MalformedStep,
    OutOfMemory,
};

const INVALID_DIMENSION: u32 = 0;
const LAUNCH_REPEAT: u32 = 1;
const TEST_ARTIFACT_CAPACITY: usize = 32 * 1024;

pub const GridDims = struct {
    width: u32,
    height: u32,
};

pub const ExecPhase = enum {
    prefill,
    decode,
};

pub const ExecStepKind = enum {
    compute,
    sample,
};

pub const AttentionType = enum {
    global,
    sliding,
};

pub const ExecStep = struct {
    phase: ExecPhase,
    kind: ExecStepKind,
    op: []const u8,
    kernel_key: []const u8,
    weights_key: ?[]const u8 = null,
    attention_type: ?AttentionType = null,
    kv_cache_alias: ?[]const u8 = null,
};

const OpSpec = struct {
    pattern: []const u8,
    allow_prefill: bool,
    allow_decode: bool,
    kind: ExecStepKind,
};

/// Map a Doppler op name to a CSL kernel pattern name and execution policy.
pub fn opToSpec(op: []const u8) ?OpSpec {
    const map = [_]struct { op: []const u8, spec: OpSpec }{
        .{ .op = "embed", .spec = .{ .pattern = "gather", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "attention", .spec = .{ .pattern = "attention_decode", .allow_prefill = false, .allow_decode = true, .kind = .compute } },
        .{ .op = "attention_prefill", .spec = .{ .pattern = "attention_tiled", .allow_prefill = true, .allow_decode = false, .kind = .compute } },
        .{ .op = "attention_linear", .spec = .{ .pattern = "attention_linear", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "rope", .spec = .{ .pattern = "rope", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "rmsnorm", .spec = .{ .pattern = "reduction", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "layernorm", .spec = .{ .pattern = "reduction", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "softmax", .spec = .{ .pattern = "reduction", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "gelu", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "silu", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "relu", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "scale", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "bias_add", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "residual", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "cast", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "dequant", .spec = .{ .pattern = "dequant", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "matmul", .spec = .{ .pattern = "tiled_matmul", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "matmul_q4k", .spec = .{ .pattern = "fused_gemv_dequant", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "ffn", .spec = .{ .pattern = "fused_ffn", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "kv_write", .spec = .{ .pattern = "kv_write", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "kv_read", .spec = .{ .pattern = "kv_read", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "sample", .spec = .{ .pattern = "sample", .allow_prefill = false, .allow_decode = true, .kind = .sample } },
        // Gemma 4: PLE composite — decomposes into gather + matmul + reduction + element_wise.
        // The host plan expands this into the four sub-steps; exec-v1 uses it as a scheduling marker.
        .{ .op = "ple_gather", .spec = .{ .pattern = "gather", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "ple_project", .spec = .{ .pattern = "fused_gemv_dequant", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "ple_norm", .spec = .{ .pattern = "reduction", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        .{ .op = "ple_modulate", .spec = .{ .pattern = "element_wise", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
        // Gemma 4: hybrid attention — uses attention_decode with sliding window
        .{ .op = "attention_sliding", .spec = .{ .pattern = "attention_decode", .allow_prefill = false, .allow_decode = true, .kind = .compute } },
        // Gemma 4: shared KV write — same pattern as kv_write, aliased buffer resolved at host-plan level
        .{ .op = "kv_write_shared", .spec = .{ .pattern = "kv_write", .allow_prefill = true, .allow_decode = true, .kind = .compute } },
    };
    inline for (map) |entry| {
        if (std.mem.eql(u8, op, entry.op)) return entry.spec;
    }
    return null;
}

/// Map a Doppler op name to a CSL kernel pattern name.
pub fn opToPattern(op: []const u8) ?[]const u8 {
    return (opToSpec(op) orelse return null).pattern;
}

fn parsePhase(text: []const u8) LowerError!ExecPhase {
    if (std.mem.eql(u8, text, "prefill")) return .prefill;
    if (std.mem.eql(u8, text, "decode")) return .decode;
    return error.InvalidJson;
}

fn parseKind(text: []const u8) LowerError!ExecStepKind {
    if (std.mem.eql(u8, text, "compute")) return .compute;
    if (std.mem.eql(u8, text, "sample")) return .sample;
    return error.InvalidJson;
}

fn expectObject(value: std.json.Value) LowerError!std.json.ObjectMap {
    return switch (value) {
        .object => |object| object,
        else => error.InvalidJson,
    };
}

fn expectArray(value: std.json.Value) LowerError!std.json.Array {
    return switch (value) {
        .array => |array| array,
        else => error.InvalidJson,
    };
}

fn expectString(value: std.json.Value) LowerError![]const u8 {
    return switch (value) {
        .string => |string| string,
        else => error.InvalidJson,
    };
}

fn expectU32(value: std.json.Value) LowerError!u32 {
    return switch (value) {
        .integer => |integer| std.math.cast(u32, integer) orelse error.InvalidJson,
        else => error.InvalidJson,
    };
}

fn parseGrid(value: std.json.Value) LowerError!GridDims {
    const object = try expectObject(value);
    const width_value = object.get("width") orelse return error.InvalidJson;
    const height_value = object.get("height") orelse return error.InvalidJson;
    return .{
        .width = try expectU32(width_value),
        .height = try expectU32(height_value),
    };
}

fn parseNullableStringDup(allocator: std.mem.Allocator, value: ?std.json.Value) LowerError!?[]const u8 {
    const raw = value orelse return null;
    return switch (raw) {
        .null => null,
        else => try allocator.dupe(u8, try expectString(raw)),
    };
}

fn parseStepObject(allocator: std.mem.Allocator, object: std.json.ObjectMap) LowerError!ExecStep {
    const phase_text = try expectString(object.get("phase") orelse return error.InvalidJson);
    const op = try expectString(object.get("op") orelse return error.InvalidJson);
    const kernel_key = try allocator.dupe(u8, try expectString(object.get("kernelKey") orelse return error.InvalidJson));
    const spec = opToSpec(op) orelse return error.UnknownOp;
    const kind = if (object.get("kind")) |kind_value|
        try parseKind(try expectString(kind_value))
    else
        spec.kind;

    const weights_key = try parseNullableStringDup(allocator, object.get("weightsKey"));

    const attention_type: ?AttentionType = if (object.get("attentionType")) |attn_val| blk: {
        const attn_text = try expectString(attn_val);
        if (std.mem.eql(u8, attn_text, "global")) break :blk .global;
        if (std.mem.eql(u8, attn_text, "sliding")) break :blk .sliding;
        break :blk null;
    } else null;

    const kv_cache_alias = try parseNullableStringDup(allocator, object.get("kvCacheAlias"));

    return .{
        .phase = try parsePhase(phase_text),
        .kind = kind,
        .op = op,
        .kernel_key = kernel_key,
        .weights_key = weights_key,
        .attention_type = attention_type,
        .kv_cache_alias = kv_cache_alias,
    };
}

fn parseStepTuple(allocator: std.mem.Allocator, array: std.json.Array) LowerError!ExecStep {
    if (array.items.len < 3 or array.items.len > 5) return error.InvalidJson;

    const phase = try parsePhase(try expectString(array.items[0]));
    const op = try expectString(array.items[1]);
    const kernel_key = try allocator.dupe(u8, try expectString(array.items[2]));
    const spec = opToSpec(op) orelse return error.UnknownOp;

    const weights_key = if (array.items.len >= 4)
        try parseNullableStringDup(allocator, array.items[3])
    else
        null;

    const kind = if (array.items.len == 5)
        try parseKind(try expectString(array.items[4]))
    else
        spec.kind;

    return .{
        .phase = phase,
        .kind = kind,
        .op = op,
        .kernel_key = kernel_key,
        .weights_key = weights_key,
    };
}

fn parseStepValue(allocator: std.mem.Allocator, value: std.json.Value) LowerError!ExecStep {
    return switch (value) {
        .object => |object| try parseStepObject(allocator, object),
        .array => |array| try parseStepTuple(allocator, array),
        else => error.InvalidJson,
    };
}

fn kernelFileToOp(kernel_file: []const u8) ?[]const u8 {
    if (std.mem.eql(u8, kernel_file, "gather.wgsl")) return "embed";
    if (std.mem.eql(u8, kernel_file, "rmsnorm.wgsl")) return "rmsnorm";
    if (std.mem.eql(u8, kernel_file, "rope.wgsl")) return "rope";
    if (std.mem.eql(u8, kernel_file, "residual.wgsl")) return "residual";
    if (std.mem.eql(u8, kernel_file, "gelu.wgsl")) return "gelu";
    if (std.mem.eql(u8, kernel_file, "sample.wgsl")) return "sample";
    if (std.mem.eql(u8, kernel_file, "attention_decode_online_f16kv.wgsl")) return "attention";
    if (std.mem.eql(u8, kernel_file, "attention_small_f16kv.wgsl")) return "attention_prefill";
    if (std.mem.eql(u8, kernel_file, "matmul_f16w_f32a_tiled.wgsl")) return "matmul";
    if (std.mem.eql(u8, kernel_file, "matmul_gemv_subgroup.wgsl")) return "matmul_q4k";
    return null;
}

fn parseKernelOpMap(
    allocator: std.mem.Allocator,
    kernel_obj: std.json.ObjectMap,
) LowerError!std.StringHashMap([]const u8) {
    var kernel_ops = std.StringHashMap([]const u8).init(allocator);
    errdefer kernel_ops.deinit();

    var iter = kernel_obj.iterator();
    while (iter.next()) |entry| {
        const kernel_key = entry.key_ptr.*;
        const meta = try expectObject(entry.value_ptr.*);
        const kernel_file = try expectString(meta.get("kernel") orelse return error.InvalidJson);
        const op = kernelFileToOp(kernel_file) orelse return error.InvalidJson;
        try kernel_ops.put(try allocator.dupe(u8, kernel_key), op);
    }
    return kernel_ops;
}

fn parseManifestPhaseTuple(
    allocator: std.mem.Allocator,
    phase: ExecPhase,
    kernel_ops: *const std.StringHashMap([]const u8),
    value: std.json.Value,
) LowerError!ExecStep {
    const tuple = try expectArray(value);
    if (tuple.items.len < 2 or tuple.items.len > 3) return error.InvalidJson;

    const kernel_key_raw = try expectString(tuple.items[1]);
    const op = kernel_ops.get(kernel_key_raw) orelse return error.InvalidJson;
    const spec = opToSpec(op) orelse return error.UnknownOp;

    return .{
        .phase = phase,
        .kind = spec.kind,
        .op = op,
        .kernel_key = try allocator.dupe(u8, kernel_key_raw),
        .weights_key = if (tuple.items.len == 3)
            try parseNullableStringDup(allocator, tuple.items[2])
        else
            null,
    };
}

fn parseManifestPhaseSteps(
    allocator: std.mem.Allocator,
    phase: ExecPhase,
    kernel_ops: *const std.StringHashMap([]const u8),
    raw_steps: std.json.Value,
    out: *std.ArrayList(ExecStep),
) LowerError!void {
    const steps = try expectArray(raw_steps);
    try out.ensureUnusedCapacity(allocator, steps.items.len);
    for (steps.items) |step_value| {
        out.appendAssumeCapacity(try parseManifestPhaseTuple(allocator, phase, kernel_ops, step_value));
    }
}

fn appendManifestPostLayerSteps(
    allocator: std.mem.Allocator,
    kernel_ops: *const std.StringHashMap([]const u8),
    raw_steps: std.json.Value,
    prefill_out: *std.ArrayList(ExecStep),
    decode_out: *std.ArrayList(ExecStep),
) LowerError!void {
    const steps = try expectArray(raw_steps);
    for (steps.items) |step_value| {
        const tuple = try expectArray(step_value);
        if (tuple.items.len < 2 or tuple.items.len > 3) return error.InvalidJson;
        const step_name = try expectString(tuple.items[0]);
        if (std.mem.eql(u8, step_name, "sample")) {
            try decode_out.append(allocator, try parseManifestPhaseTuple(allocator, .decode, kernel_ops, step_value));
            continue;
        }
        if (std.mem.eql(u8, step_name, "lm_head")) {
            try decode_out.append(allocator, try parseManifestPhaseTuple(allocator, .decode, kernel_ops, step_value));
            continue;
        }
        if (std.mem.endsWith(u8, step_name, "_prefill")) {
            try prefill_out.append(allocator, try parseManifestPhaseTuple(allocator, .prefill, kernel_ops, step_value));
            continue;
        }

        try prefill_out.append(allocator, try parseManifestPhaseTuple(allocator, .prefill, kernel_ops, step_value));
        try decode_out.append(allocator, try parseManifestPhaseTuple(allocator, .decode, kernel_ops, step_value));
    }
}

fn validateStep(step: ExecStep, spec: OpSpec) LowerError!void {
    if (step.op.len == 0 or step.kernel_key.len == 0) return error.MalformedStep;
    if (step.weights_key) |weights_key| {
        if (weights_key.len == 0) return error.MalformedStep;
    }
    if (step.kind != spec.kind) return error.MalformedStep;

    switch (step.phase) {
        .prefill => {
            if (!spec.allow_prefill) return error.MalformedStep;
            if (step.kind == .sample) return error.MalformedStep;
        },
        .decode => {
            if (!spec.allow_decode) return error.MalformedStep;
        },
    }

    if (step.kind == .sample and step.weights_key != null) return error.MalformedStep;
}

/// Lower a sequence of execution-v1 steps into a HostPlan.
/// The caller is responsible for providing an execution-v1 sequence with
/// explicit phase ordering and a valid grid dimension tuple.
pub fn lowerToHostPlan(
    steps: []const ExecStep,
    grid: GridDims,
    kernel_buf: []host.KernelSpec,
    prefill_buf: []host.LaunchSpec,
    decode_buf: []host.LaunchSpec,
) LowerError!host.HostPlan {
    if (grid.width == INVALID_DIMENSION or grid.height == INVALID_DIMENSION) {
        return error.MalformedStep;
    }

    var kernel_count: u32 = 0;
    var prefill_count: u32 = 0;
    var decode_count: u32 = 0;
    var saw_prefill_step = false;
    var saw_decode_step = false;
    var saw_decode_compute = false;
    var saw_sample_step = false;

    for (steps) |step| {
        if (saw_sample_step) return error.MalformedStep;

        const spec = opToSpec(step.op) orelse return error.UnknownOp;
        try validateStep(step, spec);

        switch (step.phase) {
            .prefill => {
                if (saw_decode_step) return error.MalformedStep;
                saw_prefill_step = true;
            },
            .decode => {
                if (!saw_prefill_step) return error.MalformedStep;
                saw_decode_step = true;
                if (step.kind == .compute) {
                    saw_decode_compute = true;
                }
            },
        }

        const pattern = spec.pattern;

        // Add kernel if not already present.
        var found = false;
        var ki: u32 = 0;
        while (ki < kernel_count) : (ki += 1) {
            if (std.mem.eql(u8, kernel_buf[ki].name, step.kernel_key)) {
                kernel_buf[ki].count += 1;
                found = true;
                break;
            }
        }
        if (!found) {
            if (kernel_count >= kernel_buf.len) return error.OutputTooLarge;
            kernel_buf[kernel_count] = .{
                .name = step.kernel_key,
                .pattern = pattern,
                .count = 1,
                .kv_cache_alias = step.kv_cache_alias,
            };
            kernel_count += 1;
        }

        switch (step.phase) {
            .prefill => {
                if (prefill_count >= prefill_buf.len) return error.OutputTooLarge;
                prefill_buf[prefill_count] = .{
                    .kernel_name = step.kernel_key,
                    .repeat = LAUNCH_REPEAT,
                };
                prefill_count += 1;
            },
            .decode => {
                if (decode_count >= decode_buf.len) return error.OutputTooLarge;
                decode_buf[decode_count] = .{
                    .kernel_name = step.kernel_key,
                    .repeat = LAUNCH_REPEAT,
                };
                decode_count += 1;
                if (step.kind == .sample) {
                    saw_sample_step = true;
                }
            },
        }
    }

    if (saw_decode_step and !saw_decode_compute) return error.MalformedStep;
    if (saw_decode_step and !saw_prefill_step) return error.MalformedStep;

    return .{
        .pe_grid_width = grid.width,
        .pe_grid_height = grid.height,
        .kernels = kernel_buf[0..kernel_count],
        .prefill_launches = prefill_buf[0..prefill_count],
        .decode_launches = decode_buf[0..decode_count],
    };
}

pub fn lowerJsonToHostPlan(
    allocator: std.mem.Allocator,
    json_payload: []const u8,
    kernel_buf: []host.KernelSpec,
    prefill_buf: []host.LaunchSpec,
    decode_buf: []host.LaunchSpec,
) LowerError!host.HostPlan {
    const parsed = std.json.parseFromSlice(std.json.Value, allocator, json_payload, .{}) catch |err| switch (err) {
        error.OutOfMemory => return error.OutOfMemory,
        else => return error.InvalidJson,
    };
    defer parsed.deinit();

    const root = try expectObject(parsed.value);
    const grid = try parseGrid(root.get("grid") orelse return error.InvalidJson);
    const steps_value = root.get("steps") orelse return error.InvalidJson;
    const steps_array = try expectArray(steps_value);

    var steps = try allocator.alloc(ExecStep, steps_array.items.len);
    defer allocator.free(steps);

    for (steps_array.items, 0..) |step_value, idx| {
        steps[idx] = try parseStepValue(allocator, step_value);
    }

    var plan = try lowerToHostPlan(steps, grid, kernel_buf, prefill_buf, decode_buf);
    if (root.get("eosTokenId")) |eos_value| {
        plan.eos_token_id = switch (eos_value) {
            .null => null,
            else => try expectU32(eos_value),
        };
    }
    return plan;
}

pub fn lowerManifestExecutionToHostPlan(
    allocator: std.mem.Allocator,
    json_payload: []const u8,
    kernel_buf: []host.KernelSpec,
    prefill_buf: []host.LaunchSpec,
    decode_buf: []host.LaunchSpec,
) LowerError!host.HostPlan {
    const parsed = std.json.parseFromSlice(std.json.Value, allocator, json_payload, .{}) catch |err| switch (err) {
        error.OutOfMemory => return error.OutOfMemory,
        else => return error.InvalidJson,
    };
    defer parsed.deinit();

    const root = try expectObject(parsed.value);
    const grid = try parseGrid(root.get("grid") orelse return error.InvalidJson);
    const execution = try expectObject(root.get("execution") orelse return error.InvalidJson);
    const kernels = try expectObject(execution.get("kernels") orelse return error.InvalidJson);
    var kernel_ops = try parseKernelOpMap(allocator, kernels);
    defer kernel_ops.deinit();

    var prefill_steps = try std.ArrayList(ExecStep).initCapacity(allocator, 0);
    defer prefill_steps.deinit(allocator);
    var decode_steps = try std.ArrayList(ExecStep).initCapacity(allocator, 0);
    defer decode_steps.deinit(allocator);

    try parseManifestPhaseSteps(allocator, .prefill, &kernel_ops, execution.get("preLayer") orelse return error.InvalidJson, &prefill_steps);
    try parseManifestPhaseSteps(allocator, .prefill, &kernel_ops, execution.get("prefill") orelse return error.InvalidJson, &prefill_steps);
    try parseManifestPhaseSteps(allocator, .decode, &kernel_ops, execution.get("decode") orelse return error.InvalidJson, &decode_steps);
    try appendManifestPostLayerSteps(
        allocator,
        &kernel_ops,
        execution.get("postLayer") orelse return error.InvalidJson,
        &prefill_steps,
        &decode_steps,
    );

    const total_steps = prefill_steps.items.len + decode_steps.items.len;
    var steps = try allocator.alloc(ExecStep, total_steps);
    defer allocator.free(steps);
    @memcpy(steps[0..prefill_steps.items.len], prefill_steps.items);
    @memcpy(steps[prefill_steps.items.len..], decode_steps.items);

    var plan = try lowerToHostPlan(steps, grid, kernel_buf, prefill_buf, decode_buf);
    if (root.get("eosTokenId")) |eos_value| {
        plan.eos_token_id = switch (eos_value) {
            .null => null,
            else => try expectU32(eos_value),
        };
    }
    return plan;
}

test "opToPattern maps known ops" {
    try std.testing.expectEqualStrings("gather", opToPattern("embed").?);
    try std.testing.expectEqualStrings("attention_decode", opToPattern("attention").?);
    try std.testing.expectEqualStrings("element_wise", opToPattern("gelu").?);
    try std.testing.expectEqualStrings("reduction", opToPattern("rmsnorm").?);
    try std.testing.expectEqualStrings("fused_ffn", opToPattern("ffn").?);
    try std.testing.expectEqualStrings("kv_write", opToPattern("kv_write").?);
    try std.testing.expect(opToPattern("unknown_op") == null);
}

test "opToPattern maps Gemma 4 PLE ops" {
    try std.testing.expectEqualStrings("gather", opToPattern("ple_gather").?);
    try std.testing.expectEqualStrings("fused_gemv_dequant", opToPattern("ple_project").?);
    try std.testing.expectEqualStrings("reduction", opToPattern("ple_norm").?);
    try std.testing.expectEqualStrings("element_wise", opToPattern("ple_modulate").?);
}

test "opToPattern maps Gemma 4 hybrid attention and shared KV ops" {
    try std.testing.expectEqualStrings("attention_decode", opToPattern("attention_sliding").?);
    try std.testing.expectEqualStrings("kv_write", opToPattern("kv_write_shared").?);
}

test "ExecStep carries attention type and kv cache alias" {
    const step = ExecStep{
        .phase = .decode,
        .kind = .compute,
        .op = "attention_sliding",
        .kernel_key = "attn_sliding",
        .attention_type = .sliding,
        .kv_cache_alias = "layer.0.kv",
    };
    try std.testing.expect(step.attention_type.? == .sliding);
    try std.testing.expectEqualStrings("layer.0.kv", step.kv_cache_alias.?);
}

test "lowerToHostPlan builds valid plan" {
    const steps = [_]ExecStep{
        .{ .phase = .prefill, .kind = .compute, .op = "embed", .kernel_key = "embed_gather" },
        .{ .phase = .prefill, .kind = .compute, .op = "rmsnorm", .kernel_key = "norm_0" },
        .{ .phase = .decode, .kind = .compute, .op = "attention", .kernel_key = "attn_0" },
        .{ .phase = .decode, .kind = .sample, .op = "sample", .kernel_key = "sampler" },
    };

    var kernels: [16]host.KernelSpec = undefined;
    var prefill: [16]host.LaunchSpec = undefined;
    var decode: [16]host.LaunchSpec = undefined;

    const plan = try lowerToHostPlan(&steps, .{ .width = 32, .height = 4 }, &kernels, &prefill, &decode);

    try std.testing.expectEqual(@as(u32, 32), plan.pe_grid_width);
    try std.testing.expectEqual(@as(u32, 4), plan.pe_grid_height);
    try std.testing.expect(plan.kernels.len == 4);
    try std.testing.expect(plan.prefill_launches.len == 2);
    try std.testing.expect(plan.decode_launches.len == 2);
}

test "lowerToHostPlan rejects decode before prefill" {
    const steps = [_]ExecStep{
        .{ .phase = .decode, .kind = .compute, .op = "attention", .kernel_key = "attn_0" },
    };

    var kernels: [4]host.KernelSpec = undefined;
    var prefill: [4]host.LaunchSpec = undefined;
    var decode: [4]host.LaunchSpec = undefined;

    try std.testing.expectError(error.MalformedStep, lowerToHostPlan(&steps, .{ .width = 32, .height = 1 }, &kernels, &prefill, &decode));
}

test "lowerJsonToHostPlan builds valid plan from object steps" {
    const json_payload =
        \\{
        \\  "grid": { "width": 16, "height": 2 },
        \\  "eosTokenId": 7,
        \\  "steps": [
        \\    { "phase": "prefill", "op": "embed", "kernelKey": "embed_gather" },
        \\    { "phase": "prefill", "op": "rmsnorm", "kernelKey": "norm_0" },
        \\    { "phase": "decode", "op": "attention", "kernelKey": "attn_0" },
        \\    { "phase": "decode", "op": "sample", "kernelKey": "sampler", "kind": "sample" }
        \\  ]
        \\}
    ;

    var kernels: [16]host.KernelSpec = undefined;
    var prefill: [16]host.LaunchSpec = undefined;
    var decode: [16]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const plan = try lowerJsonToHostPlan(arena.allocator(), json_payload, &kernels, &prefill, &decode);

    try std.testing.expectEqual(@as(u32, 16), plan.pe_grid_width);
    try std.testing.expectEqual(@as(u32, 2), plan.pe_grid_height);
    try std.testing.expectEqual(@as(?u32, 7), plan.eos_token_id);
    try std.testing.expect(plan.kernels.len == 4);
    try std.testing.expect(plan.prefill_launches.len == 2);
    try std.testing.expect(plan.decode_launches.len == 2);
}

test "lowerJsonToHostPlan accepts tuple steps" {
    const json_payload =
        \\{
        \\  "grid": { "width": 8, "height": 1 },
        \\  "steps": [
        \\    ["prefill", "embed", "embed_gather"],
        \\    ["decode", "attention", "attn_0"],
        \\    ["decode", "sample", "sampler", null, "sample"]
        \\  ]
        \\}
    ;

    var kernels: [16]host.KernelSpec = undefined;
    var prefill: [16]host.LaunchSpec = undefined;
    var decode: [16]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const plan = try lowerJsonToHostPlan(arena.allocator(), json_payload, &kernels, &prefill, &decode);

    try std.testing.expectEqual(@as(u32, 8), plan.pe_grid_width);
    try std.testing.expectEqual(@as(u32, 1), plan.pe_grid_height);
    try std.testing.expectEqual(@as(?u32, null), plan.eos_token_id);
    try std.testing.expect(plan.prefill_launches.len == 1);
    try std.testing.expect(plan.decode_launches.len == 2);
}

test "lowerJsonToHostPlan rejects mismatched explicit kind" {
    const json_payload =
        \\{
        \\  "grid": { "width": 8, "height": 1 },
        \\  "steps": [
        \\    { "phase": "prefill", "op": "embed", "kernelKey": "embed_gather", "kind": "sample" }
        \\  ]
        \\}
    ;

    var kernels: [4]host.KernelSpec = undefined;
    var prefill: [4]host.LaunchSpec = undefined;
    var decode: [4]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    try std.testing.expectError(error.MalformedStep, lowerJsonToHostPlan(arena.allocator(), json_payload, &kernels, &prefill, &decode));
}

test "lowerJsonToHostPlan rejects decode before prefill" {
    const json_payload =
        \\{
        \\  "grid": { "width": 8, "height": 1 },
        \\  "steps": [
        \\    { "phase": "decode", "op": "attention", "kernelKey": "attn_0" }
        \\  ]
        \\}
    ;

    var kernels: [4]host.KernelSpec = undefined;
    var prefill: [4]host.LaunchSpec = undefined;
    var decode: [4]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    try std.testing.expectError(error.MalformedStep, lowerJsonToHostPlan(arena.allocator(), json_payload, &kernels, &prefill, &decode));
}

test "Gemma 3 smoke fixture lowers to golden host plan artifact" {
    const fixture_json = @embedFile("../../examples/execution-v1/gemma-3-270m-smoke.json");
    const golden_artifact = @embedFile("../../examples/doe-wgsl-host-plan.gemma-3-270m-smoke.json");

    var kernels: [32]host.KernelSpec = undefined;
    var prefill: [32]host.LaunchSpec = undefined;
    var decode: [32]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const plan = try lowerJsonToHostPlan(arena.allocator(), fixture_json, &kernels, &prefill, &decode);

    const targets = [_]host_plan.CompileTarget{
        .{ .kernel_name = "embed", .layout_path = "embed/layout.csl", .pe_program_path = "embed/pe_program.csl" },
        .{ .kernel_name = "rmsnorm", .layout_path = "rmsnorm/layout.csl", .pe_program_path = "rmsnorm/pe_program.csl" },
        .{ .kernel_name = "tiled", .layout_path = "tiled/layout.csl", .pe_program_path = "tiled/pe_program.csl" },
        .{ .kernel_name = "rope", .layout_path = "rope/layout.csl", .pe_program_path = "rope/pe_program.csl" },
        .{ .kernel_name = "attn_small", .layout_path = "attn_small/layout.csl", .pe_program_path = "attn_small/pe_program.csl" },
        .{ .kernel_name = "residual", .layout_path = "residual/layout.csl", .pe_program_path = "residual/pe_program.csl" },
        .{ .kernel_name = "gelu", .layout_path = "gelu/layout.csl", .pe_program_path = "gelu/pe_program.csl" },
        .{ .kernel_name = "gemv", .layout_path = "gemv/layout.csl", .pe_program_path = "gemv/pe_program.csl" },
        .{ .kernel_name = "attn_decode", .layout_path = "attn_decode/layout.csl", .pe_program_path = "attn_decode/pe_program.csl" },
        .{ .kernel_name = "sample", .layout_path = "sample/layout.csl", .pe_program_path = "sample/pe_program.csl" },
    };
    const cslc_plan = try host_plan.makeCslcPlan(null);

    var artifact_buf: [TEST_ARTIFACT_CAPACITY]u8 = undefined;
    var artifact_pos: usize = 0;
    try host_plan.emitHostPlanArtifactJson(&artifact_buf, &artifact_pos, plan, &targets, cslc_plan);
    try host_plan.validateHostPlanArtifactJson(std.testing.allocator, artifact_buf[0..artifact_pos]);
    try std.testing.expectEqualStrings(golden_artifact, artifact_buf[0..artifact_pos]);
}

test "Gemma 3 manifest fixture lowers to the same golden host plan artifact" {
    const fixture_json = @embedFile("../../examples/execution-v1/gemma-3-270m-manifest-smoke.json");
    const golden_artifact = @embedFile("../../examples/doe-wgsl-host-plan.gemma-3-270m-manifest-smoke.json");

    var kernels: [32]host.KernelSpec = undefined;
    var prefill: [32]host.LaunchSpec = undefined;
    var decode: [32]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const plan = try lowerManifestExecutionToHostPlan(arena.allocator(), fixture_json, &kernels, &prefill, &decode);

    const targets = [_]host_plan.CompileTarget{
        .{ .kernel_name = "embed", .layout_path = "embed/layout.csl", .pe_program_path = "embed/pe_program.csl" },
        .{ .kernel_name = "rmsnorm", .layout_path = "rmsnorm/layout.csl", .pe_program_path = "rmsnorm/pe_program.csl" },
        .{ .kernel_name = "tiled", .layout_path = "tiled/layout.csl", .pe_program_path = "tiled/pe_program.csl" },
        .{ .kernel_name = "rope", .layout_path = "rope/layout.csl", .pe_program_path = "rope/pe_program.csl" },
        .{ .kernel_name = "attn_small", .layout_path = "attn_small/layout.csl", .pe_program_path = "attn_small/pe_program.csl" },
        .{ .kernel_name = "residual", .layout_path = "residual/layout.csl", .pe_program_path = "residual/pe_program.csl" },
        .{ .kernel_name = "gelu", .layout_path = "gelu/layout.csl", .pe_program_path = "gelu/pe_program.csl" },
        .{ .kernel_name = "gemv", .layout_path = "gemv/layout.csl", .pe_program_path = "gemv/pe_program.csl" },
        .{ .kernel_name = "attn_decode", .layout_path = "attn_decode/layout.csl", .pe_program_path = "attn_decode/pe_program.csl" },
        .{ .kernel_name = "sample", .layout_path = "sample/layout.csl", .pe_program_path = "sample/pe_program.csl" },
    };
    const cslc_plan = try host_plan.makeCslcPlan(null);

    var artifact_buf: [TEST_ARTIFACT_CAPACITY]u8 = undefined;
    var artifact_pos: usize = 0;
    try host_plan.emitHostPlanArtifactJson(&artifact_buf, &artifact_pos, plan, &targets, cslc_plan);
    try host_plan.validateHostPlanArtifactJson(std.testing.allocator, artifact_buf[0..artifact_pos]);
    try std.testing.expectEqualStrings(golden_artifact, artifact_buf[0..artifact_pos]);
}
