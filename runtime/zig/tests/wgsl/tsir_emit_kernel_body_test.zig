// TSIR executable kernel-body emitter tests.

const std = @import("std");
const tsir = @import("../../src/tsir/mod.zig");
const targets = @import("../../src/targets/mod.zig");

test "tsir emitters produce executable fused_gemv bodies" {
    const allocator = std.testing.allocator;
    const semantic = fusedGemvSemantic();

    const webgpu = try tsir.emit_webgpu.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(webgpu);
    try expectContains(webgpu, "acc = acc + tsir_matrix[row * cols + k] * tsir_vector[k];");
    try expectContains(webgpu, "tsir_output[row] = acc;");
    try expectNotContains(webgpu, "mechanical skeleton");

    const csl = try tsir.emit_csl.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.wse3.descriptor),
        targets.wse3.descriptor,
    );
    defer allocator.free(csl);
    try expectContains(csl, "for (@range(i16, M)) |row|");
    try expectContains(csl, "sys_mod.unblock_cmd_stream();");
    try expectNotContains(csl, "mechanical skeleton");

    const msl = try tsir.emit_msl.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(msl);
    try expectContains(msl, "kernel void main0");
    try expectContains(msl, "tsir_output[row] = acc;");

    const dxil = try tsir.emit_dxil.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(dxil);
    try expectContains(dxil, "[numthreads(1, 1, 1)]");
    try expectContains(dxil, "RWStructuredBuffer<float> tsir_output");

    const spir_v = try tsir.emit_spir_v.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(spir_v);
    try expectContains(spir_v, "#version 450");
    try expectContains(spir_v, "gl_GlobalInvocationID.x");
}

test "tsir emitters produce executable rms_norm bodies" {
    const allocator = std.testing.allocator;
    const semantic = rmsNormSemantic();

    const webgpu = try tsir.emit_webgpu.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(webgpu);
    try expectContains(webgpu, "struct TsirRmsNormUniforms");
    try expectContains(webgpu, "inverseSqrt(mean_sq + tsir_dims.epsilon)");
    try expectContains(webgpu, "tsir_output[d] = tsir_input[d] * inv_rms * tsir_scale[d];");

    const csl = try tsir.emit_csl.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.wse3.descriptor),
        targets.wse3.descriptor,
    );
    defer allocator.free(csl);
    try expectContains(csl, "const inv_rms = 1.0 / @sqrt(mean_sq + epsilon);");

    const msl = try tsir.emit_msl.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(msl);
    try expectContains(msl, "float inv_rms = rsqrt");

    const dxil = try tsir.emit_dxil.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(dxil);
    try expectContains(dxil, "float inv_rms = rsqrt");

    const spir_v = try tsir.emit_spir_v.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(spir_v);
    try expectContains(spir_v, "inversesqrt");
}

test "tsir emitters produce executable gather bodies" {
    const allocator = std.testing.allocator;
    const semantic = gatherSemantic();

    const webgpu = try tsir.emit_webgpu.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(webgpu);
    try expectContains(webgpu, "let row = tsir_indices[token];");
    try expectContains(webgpu, "tsir_output[token * hidden + h] = tsir_table[row * hidden + h];");

    const csl = try tsir.emit_csl.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.wse3.descriptor),
        targets.wse3.descriptor,
    );
    defer allocator.free(csl);
    try expectContains(csl, "param num_tokens: i16;");
    try expectContains(csl, "tsir_output[dst] = tsir_table[row * @as(u32, hidden) + @as(u32, h)];");

    const msl = try tsir.emit_msl.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(msl);
    try expectContains(msl, "uint2 gid [[thread_position_in_grid]]");

    const dxil = try tsir.emit_dxil.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(dxil);
    try expectContains(dxil, "StructuredBuffer<uint> tsir_indices");

    const spir_v = try tsir.emit_spir_v.emitSemanticFunction(
        allocator,
        semantic,
        fixtureFunction(targets.webgpu_generic.descriptor),
        targets.webgpu_generic.descriptor,
    );
    defer allocator.free(spir_v);
    try expectContains(spir_v, "uint token = gl_GlobalInvocationID.y");
}

fn fusedGemvSemantic() tsir.schema.SemanticFunction {
    const data = struct {
        const axes = [_]tsir.schema.IterationAxis{
            .{ .name = "i", .lower_bound = "0", .upper_bound = "M", .step = "1" },
            .{ .name = "k", .lower_bound = "0", .upper_bound = "K", .step = "1" },
        };
        const bindings = [_]tsir.schema.BufferBinding{
            .{ .name = "W", .group = 0, .binding = 0, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = false },
            .{ .name = "x", .group = 0, .binding = 1, .logical_shape = &.{0}, .elem = .f32, .read_write = false },
            .{ .name = "y", .group = 0, .binding = 2, .logical_shape = &.{0}, .elem = .f32, .read_write = true },
        };
        const body_bindings = [_]tsir.schema.SemanticBodyBinding{
            .{ .binding_index = 0, .role = .matrix },
            .{ .binding_index = 1, .role = .vector },
            .{ .binding_index = 2, .role = .output },
        };
        const body_axes = [_]tsir.schema.SemanticBodyAxis{
            .{ .axis_index = 0, .role = .output },
            .{ .axis_index = 1, .role = .reduction },
        };
    };
    return .{
        .name = "main",
        .family_hint = .fused_gemv,
        .axes = &data.axes,
        .bindings = &data.bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = .{ .op = .fused_gemv, .binding_roles = &data.body_bindings, .axis_roles = &data.body_axes },
        .source_digest = [_]u8{0} ** 32,
    };
}

fn rmsNormSemantic() tsir.schema.SemanticFunction {
    const data = struct {
        const axes = [_]tsir.schema.IterationAxis{
            .{ .name = "d", .lower_bound = "0", .upper_bound = "hidden_size", .step = "1" },
            .{ .name = "i", .lower_bound = "0", .upper_bound = "hidden_size", .step = "1" },
        };
        const bindings = [_]tsir.schema.BufferBinding{
            .{ .name = "input", .group = 0, .binding = 0, .logical_shape = &.{0}, .elem = .f32, .read_write = false },
            .{ .name = "weight", .group = 0, .binding = 1, .logical_shape = &.{0}, .elem = .f32, .read_write = false },
            .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &.{0}, .elem = .f32, .read_write = true },
            .{ .name = "u", .group = 0, .binding = 3, .logical_shape = &.{2}, .elem = .u32, .read_write = false },
        };
        const body_bindings = [_]tsir.schema.SemanticBodyBinding{
            .{ .binding_index = 0, .role = .input },
            .{ .binding_index = 1, .role = .scale },
            .{ .binding_index = 2, .role = .output },
        };
        const body_axes = [_]tsir.schema.SemanticBodyAxis{
            .{ .axis_index = 0, .role = .hidden },
            .{ .axis_index = 1, .role = .reduction },
        };
    };
    return .{
        .name = "main",
        .family_hint = .rms_norm,
        .axes = &data.axes,
        .bindings = &data.bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = .{
            .op = .rms_norm,
            .binding_roles = &data.body_bindings,
            .axis_roles = &data.body_axes,
            .rms_norm = .{
                .formula = .sum_squares_mean_epsilon_rsqrt_scale,
                .epsilon = .{
                    .source = .uniform_field,
                    .path = "uniform:u.eps",
                    .binding_index = 3,
                    .byte_offset = 4,
                },
                .hidden_extent_axis = 0,
                .reduction_target = .intermediate_scalar,
            },
        },
        .source_digest = [_]u8{0} ** 32,
    };
}

fn gatherSemantic() tsir.schema.SemanticFunction {
    const data = struct {
        const axes = [_]tsir.schema.IterationAxis{
            .{ .name = "t", .lower_bound = "0", .upper_bound = "num_tokens", .step = "1" },
            .{ .name = "h", .lower_bound = "0", .upper_bound = "hidden", .step = "1" },
        };
        const bindings = [_]tsir.schema.BufferBinding{
            .{ .name = "indices", .group = 0, .binding = 0, .logical_shape = &.{0}, .elem = .u32, .read_write = false },
            .{ .name = "table", .group = 0, .binding = 1, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = false },
            .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = true },
        };
        const body_bindings = [_]tsir.schema.SemanticBodyBinding{
            .{ .binding_index = 0, .role = .indices },
            .{ .binding_index = 1, .role = .table },
            .{ .binding_index = 2, .role = .output },
        };
        const body_axes = [_]tsir.schema.SemanticBodyAxis{
            .{ .axis_index = 0, .role = .token },
            .{ .axis_index = 1, .role = .hidden },
        };
    };
    return .{
        .name = "main",
        .family_hint = .gather,
        .axes = &data.axes,
        .bindings = &data.bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = .{ .op = .gather, .binding_roles = &data.body_bindings, .axis_roles = &data.body_axes },
        .source_digest = [_]u8{0} ** 32,
    };
}

fn fixtureFunction(descriptor: targets.TargetDescriptor) tsir.schema.RealizationFunction {
    return .{
        .semantic_index = 0,
        .tiles = .{ .per_axis = &.{ 1, 1 } },
        .pe_grid = .{ .width = 1, .height = 1 },
        .residency = &.{},
        .collectives = &.{},
        .reductions = &.{},
        .emitter_params_json = "{}",
        .target_descriptor_hash = targets.descriptorHash(descriptor),
    };
}

fn expectContains(haystack: []const u8, needle: []const u8) !void {
    if (std.mem.indexOf(u8, haystack, needle) == null) {
        std.debug.print("missing expected fragment:\n{s}\nfull output:\n{s}\n", .{ needle, haystack });
        return error.ExpectedFragmentMissing;
    }
}

fn expectNotContains(haystack: []const u8, needle: []const u8) !void {
    if (std.mem.indexOf(u8, haystack, needle) != null) {
        std.debug.print("unexpected fragment:\n{s}\nfull output:\n{s}\n", .{ needle, haystack });
        return error.UnexpectedFragmentPresent;
    }
}
