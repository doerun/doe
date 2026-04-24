// Shared executable TSIR kernel-body writers.
//
// These routines consume the semantic body contract directly. Realization-only
// skeleton emitters remain available for contract inspection, but lowering
// paths call these semantic-aware writers once the frontend has assigned
// family roles.

const std = @import("std");
const schema = @import("schema.zig");

pub const Backend = enum {
    webgpu,
    csl,
    msl,
    dxil,
    spir_v,
};

pub const EmitError = std.mem.Allocator.Error || error{
    InvalidBodyContract,
    MissingBindingRole,
    UnsupportedKernelBody,
    UnsupportedScalarKind,
};

pub fn emit(writer: anytype, func: schema.SemanticFunction, backend: Backend) EmitError!void {
    return switch (backend) {
        .webgpu => emitWebGpu(writer, func),
        .csl => emitCsl(writer, func),
        .msl => emitMsl(writer, func),
        .dxil => emitDxil(writer, func),
        .spir_v => emitSpirV(writer, func),
    };
}

fn emitWebGpu(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    return switch (func.body.op) {
        .fused_gemv => emitWebGpuFusedGemv(writer, func),
        .rms_norm => emitWebGpuRmsNorm(writer, func),
        .gather => emitWebGpuGather(writer, func),
        // attention_scores lowering is fixture-only under Move 4 D3;
        // see runtime/zig/tests/tsir/real/attention_head256_f16kv/.
        // Add executable body emission when attention moves out of
        // the typed-rejection phase.
        .unknown, .attention_scores => error.UnsupportedKernelBody,
    };
}

fn emitCsl(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    return switch (func.body.op) {
        .fused_gemv => emitCslFusedGemv(writer, func),
        .rms_norm => emitCslRmsNorm(writer, func),
        .gather => emitCslGather(writer, func),
        // attention_scores lowering is fixture-only under Move 4 D3;
        // see runtime/zig/tests/tsir/real/attention_head256_f16kv/.
        // Add executable body emission when attention moves out of
        // the typed-rejection phase.
        .unknown, .attention_scores => error.UnsupportedKernelBody,
    };
}

fn emitMsl(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    return switch (func.body.op) {
        .fused_gemv => emitMslFusedGemv(writer, func),
        .rms_norm => emitMslRmsNorm(writer, func),
        .gather => emitMslGather(writer, func),
        // attention_scores lowering is fixture-only under Move 4 D3;
        // see runtime/zig/tests/tsir/real/attention_head256_f16kv/.
        // Add executable body emission when attention moves out of
        // the typed-rejection phase.
        .unknown, .attention_scores => error.UnsupportedKernelBody,
    };
}

fn emitDxil(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    return switch (func.body.op) {
        .fused_gemv => emitDxilFusedGemv(writer, func),
        .rms_norm => emitDxilRmsNorm(writer, func),
        .gather => emitDxilGather(writer, func),
        // attention_scores lowering is fixture-only under Move 4 D3;
        // see runtime/zig/tests/tsir/real/attention_head256_f16kv/.
        // Add executable body emission when attention moves out of
        // the typed-rejection phase.
        .unknown, .attention_scores => error.UnsupportedKernelBody,
    };
}

fn emitSpirV(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    return switch (func.body.op) {
        .fused_gemv => emitSpirVFusedGemv(writer, func),
        .rms_norm => emitSpirVRmsNorm(writer, func),
        .gather => emitSpirVGather(writer, func),
        // attention_scores lowering is fixture-only under Move 4 D3;
        // see runtime/zig/tests/tsir/real/attention_head256_f16kv/.
        // Add executable body emission when attention moves out of
        // the typed-rejection phase.
        .unknown, .attention_scores => error.UnsupportedKernelBody,
    };
}

fn emitWebGpuFusedGemv(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const matrix = try bindingForRole(func, .matrix);
    const vector = try bindingForRole(func, .vector);
    const output = try bindingForRole(func, .output);
    try requireElem(matrix, .f32);
    try requireElem(vector, .f32);
    try requireElem(output, .f32);

    try writer.print("@group({d}) @binding({d}) var<storage, read> tsir_matrix: array<f32>;\n", .{ matrix.group, matrix.binding });
    try writer.print("@group({d}) @binding({d}) var<storage, read> tsir_vector: array<f32>;\n", .{ vector.group, vector.binding });
    try writer.print("@group({d}) @binding({d}) var<storage, read_write> tsir_output: array<f32>;\n\n", .{ output.group, output.binding });
    try writer.writeAll("@compute @workgroup_size(1, 1, 1)\n");
    try writer.writeAll("fn main(@builtin(global_invocation_id) gid: vec3<u32>) {\n");
    try writer.writeAll("    let row = gid.x;\n");
    try writer.writeAll("    let rows = arrayLength(&tsir_output);\n");
    try writer.writeAll("    let cols = arrayLength(&tsir_vector);\n");
    try writer.writeAll("    if (row >= rows) {\n");
    try writer.writeAll("        return;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    var acc: f32 = 0.0;\n");
    try writer.writeAll("    for (var k = 0u; k < cols; k = k + 1u) {\n");
    try writer.writeAll("        acc = acc + tsir_matrix[row * cols + k] * tsir_vector[k];\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    tsir_output[row] = acc;\n");
    try writer.writeAll("}\n");
}

fn emitWebGpuRmsNorm(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const input = try bindingForRole(func, .input);
    const scale = try bindingForRole(func, .scale);
    const output = try bindingForRole(func, .output);
    try requireElem(input, .f32);
    try requireElem(scale, .f32);
    try requireElem(output, .f32);

    const rms = try rmsNormBody(func);
    switch (rms.epsilon.source) {
        .uniform_field => {
            if (rms.epsilon.byte_offset != 4) return error.InvalidBodyContract;
            try writer.writeAll("struct TsirRmsNormUniforms {\n");
            try writer.writeAll("    hidden_size: u32,\n");
            try writer.writeAll("    epsilon: f32,\n");
            try writer.writeAll("};\n\n");
        },
        .literal_f32 => {},
    }
    try writer.print("@group({d}) @binding({d}) var<storage, read> tsir_input: array<f32>;\n", .{ input.group, input.binding });
    try writer.print("@group({d}) @binding({d}) var<storage, read> tsir_scale: array<f32>;\n", .{ scale.group, scale.binding });
    try writer.print("@group({d}) @binding({d}) var<storage, read_write> tsir_output: array<f32>;\n", .{ output.group, output.binding });
    switch (rms.epsilon.source) {
        .uniform_field => {
            const uniform_index = rms.epsilon.binding_index orelse return error.InvalidBodyContract;
            const uniform = try bindingForIndex(func, uniform_index);
            try writer.print("@group({d}) @binding({d}) var<uniform> tsir_dims: TsirRmsNormUniforms;\n\n", .{ uniform.group, uniform.binding });
        },
        .literal_f32 => try writer.writeAll("\n"),
    }
    try writer.writeAll("@compute @workgroup_size(1, 1, 1)\n");
    try writer.writeAll("fn main(@builtin(global_invocation_id) gid: vec3<u32>) {\n");
    try writer.writeAll("    let d = gid.x;\n");
    switch (rms.epsilon.source) {
        .uniform_field => try writer.writeAll("    let hidden_size = tsir_dims.hidden_size;\n"),
        .literal_f32 => try writer.writeAll("    let hidden_size = arrayLength(&tsir_output);\n"),
    }
    try writer.writeAll("    if (d >= hidden_size) {\n");
    try writer.writeAll("        return;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    var sum_sq: f32 = 0.0;\n");
    try writer.writeAll("    for (var i = 0u; i < hidden_size; i = i + 1u) {\n");
    try writer.writeAll("        let v = tsir_input[i];\n");
    try writer.writeAll("        sum_sq = sum_sq + v * v;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    let mean_sq = sum_sq / f32(hidden_size);\n");
    try writer.writeAll("    let inv_rms = inverseSqrt(mean_sq + ");
    try writeWebGpuEpsilon(writer, rms.epsilon);
    try writer.writeAll(");\n");
    try writer.writeAll("    tsir_output[d] = tsir_input[d] * inv_rms * tsir_scale[d];\n");
    try writer.writeAll("}\n");
}

fn emitWebGpuGather(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const indices = try bindingForRole(func, .indices);
    const table = try bindingForRole(func, .table);
    const output = try bindingForRole(func, .output);
    try requireElem(indices, .u32);
    try requireElem(table, .f32);
    try requireElem(output, .f32);

    try writer.print("@group({d}) @binding({d}) var<storage, read> tsir_indices: array<u32>;\n", .{ indices.group, indices.binding });
    try writer.print("@group({d}) @binding({d}) var<storage, read> tsir_table: array<f32>;\n", .{ table.group, table.binding });
    try writer.print("@group({d}) @binding({d}) var<storage, read_write> tsir_output: array<f32>;\n\n", .{ output.group, output.binding });
    try writer.writeAll("@compute @workgroup_size(1, 1, 1)\n");
    try writer.writeAll("fn main(@builtin(global_invocation_id) gid: vec3<u32>) {\n");
    try writer.writeAll("    let h = gid.x;\n");
    try writer.writeAll("    let token = gid.y;\n");
    try writer.writeAll("    let tokens = arrayLength(&tsir_indices);\n");
    try writer.writeAll("    let hidden = arrayLength(&tsir_output) / tokens;\n");
    try writer.writeAll("    if (token >= tokens || h >= hidden) {\n");
    try writer.writeAll("        return;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    let row = tsir_indices[token];\n");
    try writer.writeAll("    let vocab = arrayLength(&tsir_table) / hidden;\n");
    try writer.writeAll("    if (row >= vocab) {\n");
    try writer.writeAll("        tsir_output[token * hidden + h] = 0.0;\n");
    try writer.writeAll("        return;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    tsir_output[token * hidden + h] = tsir_table[row * hidden + h];\n");
    try writer.writeAll("}\n");
}

fn emitCslFusedGemv(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const matrix = try bindingForRole(func, .matrix);
    const vector = try bindingForRole(func, .vector);
    const output = try bindingForRole(func, .output);
    try requireElem(matrix, .f32);
    try requireElem(vector, .f32);
    try requireElem(output, .f32);

    try writer.writeAll("param memcpy_params;\n");
    try writer.writeAll("param M: i16;\n");
    try writer.writeAll("param K: i16;\n");
    try writer.writeAll("const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try writer.writeAll("var tsir_matrix: [M * K]f32 = @zeros([M * K]f32);\n");
    try writer.writeAll("var tsir_vector: [K]f32 = @zeros([K]f32);\n");
    try writer.writeAll("var tsir_output: [M]f32 = @zeros([M]f32);\n");
    try writer.writeAll("var tsir_matrix_ptr: [*]f32 = &tsir_matrix;\n");
    try writer.writeAll("var tsir_vector_ptr: [*]f32 = &tsir_vector;\n");
    try writer.writeAll("var tsir_output_ptr: [*]f32 = &tsir_output;\n\n");
    try writer.writeAll("fn compute() void {\n");
    try writer.writeAll("    for (@range(i16, M)) |row| {\n");
    try writer.writeAll("        var acc: f32 = 0.0;\n");
    try writer.writeAll("        for (@range(i16, K)) |k| {\n");
    try writer.writeAll("            acc += tsir_matrix[@as(u32, row) * @as(u32, K) + @as(u32, k)] * tsir_vector[@as(u32, k)];\n");
    try writer.writeAll("        }\n");
    try writer.writeAll("        tsir_output[@as(u32, row)] = acc;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    sys_mod.unblock_cmd_stream();\n");
    try writer.writeAll("}\n\n");
    try writeCslFusedGemvExports(writer);
}

fn emitCslRmsNorm(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const input = try bindingForRole(func, .input);
    const scale = try bindingForRole(func, .scale);
    const output = try bindingForRole(func, .output);
    try requireElem(input, .f32);
    try requireElem(scale, .f32);
    try requireElem(output, .f32);
    const rms = try rmsNormBody(func);

    try writer.writeAll("param memcpy_params;\n");
    try writer.writeAll("param hidden_size: i16;\n");
    if (rms.epsilon.source == .uniform_field) {
        if (rms.epsilon.byte_offset != 4) return error.InvalidBodyContract;
        try writer.writeAll("param epsilon: f32;\n");
    }
    try writer.writeAll("const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try writer.writeAll("var tsir_input: [hidden_size]f32 = @zeros([hidden_size]f32);\n");
    try writer.writeAll("var tsir_scale: [hidden_size]f32 = @zeros([hidden_size]f32);\n");
    try writer.writeAll("var tsir_output: [hidden_size]f32 = @zeros([hidden_size]f32);\n");
    try writer.writeAll("var tsir_input_ptr: [*]f32 = &tsir_input;\n");
    try writer.writeAll("var tsir_scale_ptr: [*]f32 = &tsir_scale;\n");
    try writer.writeAll("var tsir_output_ptr: [*]f32 = &tsir_output;\n\n");
    try writer.writeAll("fn compute() void {\n");
    try writer.writeAll("    var sum_sq: f32 = 0.0;\n");
    try writer.writeAll("    for (@range(i16, hidden_size)) |i| {\n");
    try writer.writeAll("        const v = tsir_input[@as(u32, i)];\n");
    try writer.writeAll("        sum_sq += v * v;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    const mean_sq = sum_sq / @as(f32, hidden_size);\n");
    try writer.writeAll("    const inv_rms = 1.0 / @sqrt(mean_sq + ");
    try writeCslEpsilon(writer, rms.epsilon);
    try writer.writeAll(");\n");
    try writer.writeAll("    for (@range(i16, hidden_size)) |d| {\n");
    try writer.writeAll("        tsir_output[@as(u32, d)] = tsir_input[@as(u32, d)] * inv_rms * tsir_scale[@as(u32, d)];\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    sys_mod.unblock_cmd_stream();\n");
    try writer.writeAll("}\n\n");
    try writeCslRmsNormExports(writer);
}

fn emitCslGather(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const indices = try bindingForRole(func, .indices);
    const table = try bindingForRole(func, .table);
    const output = try bindingForRole(func, .output);
    try requireElem(indices, .u32);
    try requireElem(table, .f32);
    try requireElem(output, .f32);

    try writer.writeAll("param memcpy_params;\n");
    try writer.writeAll("param num_tokens: i16;\n");
    try writer.writeAll("param hidden: i16;\n");
    try writer.writeAll("param vocab: i16;\n");
    try writer.writeAll("const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try writer.writeAll("var tsir_indices: [num_tokens]u32 = @zeros([num_tokens]u32);\n");
    try writer.writeAll("var tsir_table: [vocab * hidden]f32 = @zeros([vocab * hidden]f32);\n");
    try writer.writeAll("var tsir_output: [num_tokens * hidden]f32 = @zeros([num_tokens * hidden]f32);\n");
    try writer.writeAll("var tsir_indices_ptr: [*]u32 = &tsir_indices;\n");
    try writer.writeAll("var tsir_table_ptr: [*]f32 = &tsir_table;\n");
    try writer.writeAll("var tsir_output_ptr: [*]f32 = &tsir_output;\n\n");
    try writer.writeAll("fn compute() void {\n");
    try writer.writeAll("    for (@range(i16, num_tokens)) |token| {\n");
    try writer.writeAll("        const row = tsir_indices[@as(u32, token)];\n");
    try writer.writeAll("        for (@range(i16, hidden)) |h| {\n");
    try writer.writeAll("            const dst = @as(u32, token) * @as(u32, hidden) + @as(u32, h);\n");
    try writer.writeAll("            if (row >= @as(u32, vocab)) {\n");
    try writer.writeAll("                tsir_output[dst] = 0.0;\n");
    try writer.writeAll("            } else {\n");
    try writer.writeAll("                tsir_output[dst] = tsir_table[row * @as(u32, hidden) + @as(u32, h)];\n");
    try writer.writeAll("            }\n");
    try writer.writeAll("        }\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    sys_mod.unblock_cmd_stream();\n");
    try writer.writeAll("}\n\n");
    try writeCslGatherExports(writer);
}

fn emitMslFusedGemv(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    try requireFusedGemvF32(func);
    try writer.writeAll("#include <metal_stdlib>\nusing namespace metal;\n");
    try writer.writeAll("constant uint tsir_M [[function_constant(0)]];\n");
    try writer.writeAll("constant uint tsir_K [[function_constant(1)]];\n");
    try writer.writeAll("kernel void main0(const device float* tsir_matrix [[buffer(0)]], const device float* tsir_vector [[buffer(1)]], device float* tsir_output [[buffer(2)]], uint row [[thread_position_in_grid]]) {\n");
    try writer.writeAll("    if (row >= tsir_M) return;\n");
    try writer.writeAll("    float acc = 0.0f;\n");
    try writer.writeAll("    for (uint k = 0; k < tsir_K; k++) acc += tsir_matrix[row * tsir_K + k] * tsir_vector[k];\n");
    try writer.writeAll("    tsir_output[row] = acc;\n");
    try writer.writeAll("}\n");
}

fn emitMslRmsNorm(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const rms = try requireRmsNormF32(func);
    try writer.writeAll("#include <metal_stdlib>\nusing namespace metal;\n");
    try writer.writeAll("constant uint tsir_hidden_size [[function_constant(0)]];\n");
    try writer.writeAll("constant float tsir_epsilon [[function_constant(1)]];\n");
    try writer.writeAll("kernel void main0(const device float* tsir_input [[buffer(0)]], const device float* tsir_scale [[buffer(1)]], device float* tsir_output [[buffer(2)]], uint d [[thread_position_in_grid]]) {\n");
    try writer.writeAll("    if (d >= tsir_hidden_size) return;\n");
    try writer.writeAll("    float sum_sq = 0.0f;\n");
    try writer.writeAll("    for (uint i = 0; i < tsir_hidden_size; i++) { float v = tsir_input[i]; sum_sq += v * v; }\n");
    try writer.writeAll("    float inv_rms = rsqrt((sum_sq / float(tsir_hidden_size)) + ");
    try writeCFloatEpsilon(writer, rms.epsilon, "tsir_epsilon");
    try writer.writeAll(");\n");
    try writer.writeAll("    tsir_output[d] = tsir_input[d] * inv_rms * tsir_scale[d];\n");
    try writer.writeAll("}\n");
}

fn emitMslGather(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    try requireGatherF32(func);
    try writer.writeAll("#include <metal_stdlib>\nusing namespace metal;\n");
    try writer.writeAll("constant uint tsir_num_tokens [[function_constant(0)]];\n");
    try writer.writeAll("constant uint tsir_hidden [[function_constant(1)]];\n");
    try writer.writeAll("constant uint tsir_vocab [[function_constant(2)]];\n");
    try writer.writeAll("kernel void main0(const device uint* tsir_indices [[buffer(0)]], const device float* tsir_table [[buffer(1)]], device float* tsir_output [[buffer(2)]], uint2 gid [[thread_position_in_grid]]) {\n");
    try writer.writeAll("    uint h = gid.x; uint token = gid.y;\n");
    try writer.writeAll("    if (token >= tsir_num_tokens || h >= tsir_hidden) return;\n");
    try writer.writeAll("    uint row = tsir_indices[token];\n");
    try writer.writeAll("    uint dst = token * tsir_hidden + h;\n");
    try writer.writeAll("    tsir_output[dst] = (row >= tsir_vocab) ? 0.0f : tsir_table[row * tsir_hidden + h];\n");
    try writer.writeAll("}\n");
}

fn emitDxilFusedGemv(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    try requireFusedGemvF32(func);
    try writer.writeAll("StructuredBuffer<float> tsir_matrix : register(t0);\n");
    try writer.writeAll("StructuredBuffer<float> tsir_vector : register(t1);\n");
    try writer.writeAll("RWStructuredBuffer<float> tsir_output : register(u2);\n");
    try writer.writeAll("cbuffer TsirDims : register(b0) { uint tsir_M; uint tsir_K; };\n");
    try writer.writeAll("[numthreads(1, 1, 1)] void main(uint3 gid : SV_DispatchThreadID) {\n");
    try writer.writeAll("    uint row = gid.x; if (row >= tsir_M) return;\n");
    try writer.writeAll("    float acc = 0.0f;\n");
    try writer.writeAll("    for (uint k = 0; k < tsir_K; k++) acc += tsir_matrix[row * tsir_K + k] * tsir_vector[k];\n");
    try writer.writeAll("    tsir_output[row] = acc;\n");
    try writer.writeAll("}\n");
}

fn emitDxilRmsNorm(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const rms = try requireRmsNormF32(func);
    try writer.writeAll("StructuredBuffer<float> tsir_input : register(t0);\n");
    try writer.writeAll("StructuredBuffer<float> tsir_scale : register(t1);\n");
    try writer.writeAll("RWStructuredBuffer<float> tsir_output : register(u2);\n");
    try writer.writeAll("cbuffer TsirDims : register(b0) { uint tsir_hidden_size; float tsir_epsilon; };\n");
    try writer.writeAll("[numthreads(1, 1, 1)] void main(uint3 gid : SV_DispatchThreadID) {\n");
    try writer.writeAll("    uint d = gid.x; if (d >= tsir_hidden_size) return;\n");
    try writer.writeAll("    float sum_sq = 0.0f;\n");
    try writer.writeAll("    for (uint i = 0; i < tsir_hidden_size; i++) { float v = tsir_input[i]; sum_sq += v * v; }\n");
    try writer.writeAll("    float inv_rms = rsqrt((sum_sq / float(tsir_hidden_size)) + ");
    try writeCFloatEpsilon(writer, rms.epsilon, "tsir_epsilon");
    try writer.writeAll(");\n");
    try writer.writeAll("    tsir_output[d] = tsir_input[d] * inv_rms * tsir_scale[d];\n");
    try writer.writeAll("}\n");
}

fn emitDxilGather(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    try requireGatherF32(func);
    try writer.writeAll("StructuredBuffer<uint> tsir_indices : register(t0);\n");
    try writer.writeAll("StructuredBuffer<float> tsir_table : register(t1);\n");
    try writer.writeAll("RWStructuredBuffer<float> tsir_output : register(u2);\n");
    try writer.writeAll("cbuffer TsirDims : register(b0) { uint tsir_num_tokens; uint tsir_hidden; uint tsir_vocab; };\n");
    try writer.writeAll("[numthreads(1, 1, 1)] void main(uint3 gid : SV_DispatchThreadID) {\n");
    try writer.writeAll("    uint h = gid.x; uint token = gid.y;\n");
    try writer.writeAll("    if (token >= tsir_num_tokens || h >= tsir_hidden) return;\n");
    try writer.writeAll("    uint row = tsir_indices[token]; uint dst = token * tsir_hidden + h;\n");
    try writer.writeAll("    tsir_output[dst] = (row >= tsir_vocab) ? 0.0f : tsir_table[row * tsir_hidden + h];\n");
    try writer.writeAll("}\n");
}

fn emitSpirVFusedGemv(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    try requireFusedGemvF32(func);
    try writer.writeAll("#version 450\nlayout(local_size_x = 1, local_size_y = 1, local_size_z = 1) in;\n");
    try writer.writeAll("layout(set = 0, binding = 0) readonly buffer TsirMatrix { float tsir_matrix[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 1) readonly buffer TsirVector { float tsir_vector[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 2) buffer TsirOutput { float tsir_output[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 3) uniform TsirDims { uint tsir_M; uint tsir_K; };\n");
    try writer.writeAll("void main() { uint row = gl_GlobalInvocationID.x; if (row >= tsir_M) return; float acc = 0.0; for (uint k = 0; k < tsir_K; k++) acc += tsir_matrix[row * tsir_K + k] * tsir_vector[k]; tsir_output[row] = acc; }\n");
}

fn emitSpirVRmsNorm(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    const rms = try requireRmsNormF32(func);
    try writer.writeAll("#version 450\nlayout(local_size_x = 1, local_size_y = 1, local_size_z = 1) in;\n");
    try writer.writeAll("layout(set = 0, binding = 0) readonly buffer TsirInput { float tsir_input[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 1) readonly buffer TsirScale { float tsir_scale[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 2) buffer TsirOutput { float tsir_output[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 3) uniform TsirDims { uint tsir_hidden_size; float tsir_epsilon; };\n");
    try writer.writeAll("void main() { uint d = gl_GlobalInvocationID.x; if (d >= tsir_hidden_size) return; float sum_sq = 0.0; for (uint i = 0; i < tsir_hidden_size; i++) { float v = tsir_input[i]; sum_sq += v * v; } float inv_rms = inversesqrt((sum_sq / float(tsir_hidden_size)) + ");
    try writeCFloatEpsilon(writer, rms.epsilon, "tsir_epsilon");
    try writer.writeAll("); tsir_output[d] = tsir_input[d] * inv_rms * tsir_scale[d]; }\n");
}

fn emitSpirVGather(writer: anytype, func: schema.SemanticFunction) EmitError!void {
    try requireGatherF32(func);
    try writer.writeAll("#version 450\nlayout(local_size_x = 1, local_size_y = 1, local_size_z = 1) in;\n");
    try writer.writeAll("layout(set = 0, binding = 0) readonly buffer TsirIndices { uint tsir_indices[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 1) readonly buffer TsirTable { float tsir_table[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 2) buffer TsirOutput { float tsir_output[]; };\n");
    try writer.writeAll("layout(set = 0, binding = 3) uniform TsirDims { uint tsir_num_tokens; uint tsir_hidden; uint tsir_vocab; };\n");
    try writer.writeAll("void main() { uint h = gl_GlobalInvocationID.x; uint token = gl_GlobalInvocationID.y; if (token >= tsir_num_tokens || h >= tsir_hidden) return; uint row = tsir_indices[token]; uint dst = token * tsir_hidden + h; tsir_output[dst] = (row >= tsir_vocab) ? 0.0 : tsir_table[row * tsir_hidden + h]; }\n");
}

fn bindingForRole(func: schema.SemanticFunction, role: schema.SemanticBindingRole) EmitError!schema.BufferBinding {
    for (func.body.binding_roles) |binding_role| {
        if (binding_role.role == role) return bindingForIndex(func, binding_role.binding_index);
    }
    return error.MissingBindingRole;
}

fn bindingForIndex(func: schema.SemanticFunction, binding_index: u32) EmitError!schema.BufferBinding {
    if (binding_index >= func.bindings.len) return error.InvalidBodyContract;
    return func.bindings[@intCast(binding_index)];
}

fn rmsNormBody(func: schema.SemanticFunction) EmitError!schema.RmsNormBody {
    const rms = func.body.rms_norm orelse return error.InvalidBodyContract;
    if (rms.formula != .sum_squares_mean_epsilon_rsqrt_scale) return error.UnsupportedKernelBody;
    if (rms.reduction_target != .intermediate_scalar) return error.UnsupportedKernelBody;
    return rms;
}

fn requireElem(binding: schema.BufferBinding, elem: schema.ScalarKind) EmitError!void {
    if (binding.elem != elem) return error.UnsupportedScalarKind;
}

fn requireFusedGemvF32(func: schema.SemanticFunction) EmitError!void {
    try requireElem(try bindingForRole(func, .matrix), .f32);
    try requireElem(try bindingForRole(func, .vector), .f32);
    try requireElem(try bindingForRole(func, .output), .f32);
}

fn requireRmsNormF32(func: schema.SemanticFunction) EmitError!schema.RmsNormBody {
    try requireElem(try bindingForRole(func, .input), .f32);
    try requireElem(try bindingForRole(func, .scale), .f32);
    try requireElem(try bindingForRole(func, .output), .f32);
    return rmsNormBody(func);
}

fn requireGatherF32(func: schema.SemanticFunction) EmitError!void {
    try requireElem(try bindingForRole(func, .indices), .u32);
    try requireElem(try bindingForRole(func, .table), .f32);
    try requireElem(try bindingForRole(func, .output), .f32);
}

fn writeWebGpuEpsilon(writer: anytype, epsilon: schema.RmsNormEpsilon) EmitError!void {
    switch (epsilon.source) {
        .uniform_field => try writer.writeAll("tsir_dims.epsilon"),
        .literal_f32 => {
            const value = epsilon.literal_f32 orelse return error.InvalidBodyContract;
            try writer.print("{d}", .{value});
        },
    }
}

fn writeCslEpsilon(writer: anytype, epsilon: schema.RmsNormEpsilon) EmitError!void {
    switch (epsilon.source) {
        .uniform_field => try writer.writeAll("epsilon"),
        .literal_f32 => {
            const value = epsilon.literal_f32 orelse return error.InvalidBodyContract;
            try writer.print("{d}", .{value});
        },
    }
}

fn writeCFloatEpsilon(writer: anytype, epsilon: schema.RmsNormEpsilon, uniform_name: []const u8) EmitError!void {
    switch (epsilon.source) {
        .uniform_field => try writer.writeAll(uniform_name),
        .literal_f32 => {
            const value = epsilon.literal_f32 orelse return error.InvalidBodyContract;
            try writer.print("{d}f", .{value});
        },
    }
}

fn writeCslFusedGemvExports(writer: anytype) EmitError!void {
    try writer.writeAll("comptime {\n");
    try writer.writeAll("    @export_symbol(tsir_matrix_ptr, \"tsir_matrix\");\n");
    try writer.writeAll("    @export_symbol(tsir_vector_ptr, \"tsir_vector\");\n");
    try writer.writeAll("    @export_symbol(tsir_output_ptr, \"tsir_output\");\n");
    try writer.writeAll("    @export_symbol(compute);\n");
    try writer.writeAll("}\n");
}

fn writeCslRmsNormExports(writer: anytype) EmitError!void {
    try writer.writeAll("comptime {\n");
    try writer.writeAll("    @export_symbol(tsir_input_ptr, \"tsir_input\");\n");
    try writer.writeAll("    @export_symbol(tsir_scale_ptr, \"tsir_scale\");\n");
    try writer.writeAll("    @export_symbol(tsir_output_ptr, \"tsir_output\");\n");
    try writer.writeAll("    @export_symbol(compute);\n");
    try writer.writeAll("}\n");
}

fn writeCslGatherExports(writer: anytype) EmitError!void {
    try writer.writeAll("comptime {\n");
    try writer.writeAll("    @export_symbol(tsir_indices_ptr, \"tsir_indices\");\n");
    try writer.writeAll("    @export_symbol(tsir_table_ptr, \"tsir_table\");\n");
    try writer.writeAll("    @export_symbol(tsir_output_ptr, \"tsir_output\");\n");
    try writer.writeAll("    @export_symbol(compute);\n");
    try writer.writeAll("}\n");
}
