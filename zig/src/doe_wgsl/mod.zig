// doe_wgsl/mod.zig — WGSL compiler module entry point.
//
// Public API for parsing WGSL source, validating it through semantic analysis,
// lowering it to typed IR, and then invoking legacy backend emitters.

pub const token = @import("token.zig");
pub const lexer = @import("lexer.zig");
pub const ast = @import("ast.zig");
pub const parser = @import("parser.zig");
pub const sema = @import("sema.zig");
pub const ir = @import("ir.zig");
pub const ir_builder = @import("ir_builder.zig");
pub const ir_validate = @import("ir_validate.zig");
pub const emit_msl = @import("emit_msl.zig");
pub const emit_hlsl = @import("emit_hlsl.zig");
pub const emit_spirv = @import("emit_spirv.zig");
pub const emit_spirv_fn = @import("emit_spirv_fn.zig");
pub const emit_spirv_stages = @import("emit_spirv_stages.zig");
pub const emit_dxil = @import("emit_dxil.zig");

const std = @import("std");

pub const TranslateError = error{
    InvalidWgsl,
    OutputTooLarge,
    OutOfMemory,
    ShaderToolchainUnavailable,
    UnexpectedToken,
    UnsupportedWgsl,
};

pub const MAX_OUTPUT: usize = emit_msl.MAX_OUTPUT;
pub const MAX_HLSL_OUTPUT: usize = emit_hlsl.MAX_OUTPUT;
pub const MAX_SPIRV_OUTPUT: usize = emit_spirv.MAX_OUTPUT;
pub const MAX_DXIL_OUTPUT: usize = emit_dxil.MAX_OUTPUT;
pub const MAX_BINDINGS: usize = 16;

pub const BindingMeta = struct {
    group: u32,
    binding: u32,
};

pub fn analyzeToIr(allocator: std.mem.Allocator, wgsl: []const u8) TranslateError!ir.Module {
    var tree = parser.parseSource(allocator, wgsl) catch |err| {
        return switch (err) {
            error.OutOfMemory => TranslateError.OutOfMemory,
            error.UnexpectedToken => TranslateError.UnexpectedToken,
        };
    };
    defer tree.deinit();

    var semantic = sema.analyze(allocator, &tree) catch |err| {
        return mapSemanticError(err);
    };
    defer semantic.deinit();

    var module = ir_builder.build(allocator, &tree, &semantic) catch |err| {
        return mapIrBuildError(err);
    };
    errdefer module.deinit();
    ir_validate.validate(&module) catch return TranslateError.InvalidWgsl;
    return module;
}

pub fn extractBindings(allocator: std.mem.Allocator, wgsl: []const u8, out: []BindingMeta) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    var count: usize = 0;
    for (module_ir.globals.items) |global| {
        if (global.binding == null) continue;
        if (count >= out.len) break;
        out[count] = .{
            .group = global.binding.?.group,
            .binding = global.binding.?.binding,
        };
        count += 1;
    }
    return count;
}

pub fn translateToMsl(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_msl.emit(&module_ir, out) catch |err| {
        return switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.InvalidIr => TranslateError.InvalidWgsl,
        };
    };
}

pub fn translateToHlsl(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_hlsl.emit(&module_ir, out) catch |err| {
        return switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.InvalidIr => TranslateError.InvalidWgsl,
        };
    };
}

pub fn translateToSpirv(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_spirv.emit(&module_ir, out) catch |err| {
        return switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.UnsupportedConstruct, error.InvalidIr => TranslateError.UnsupportedWgsl,
            error.OutOfMemory => TranslateError.OutOfMemory,
        };
    };
}

pub fn translateToDxil(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_dxil.emit(&module_ir, out) catch |err| {
        return switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.UnsupportedConstruct, error.InvalidIr => TranslateError.UnsupportedWgsl,
            error.OutOfMemory => TranslateError.OutOfMemory,
        };
    };
}

fn mapSemanticError(err: anyerror) TranslateError {
    return switch (err) {
        error.OutOfMemory => TranslateError.OutOfMemory,
        error.UnsupportedConstruct, error.UnsupportedBuiltin => TranslateError.UnsupportedWgsl,
        error.DuplicateSymbol,
        error.InvalidAttribute,
        error.InvalidType,
        error.InvalidWgsl,
        error.TypeMismatch,
        error.UnknownIdentifier,
        error.UnknownType,
        => TranslateError.InvalidWgsl,
        else => TranslateError.InvalidWgsl,
    };
}

fn mapIrBuildError(err: anyerror) TranslateError {
    return switch (err) {
        error.OutOfMemory => TranslateError.OutOfMemory,
        error.UnsupportedConstruct => TranslateError.UnsupportedWgsl,
        error.InvalidWgsl => TranslateError.InvalidWgsl,
        else => TranslateError.InvalidWgsl,
    };
}

test {
    _ = token;
    _ = lexer;
    _ = ast;
    _ = parser;
    _ = sema;
    _ = ir;
    _ = ir_builder;
    _ = ir_validate;
    _ = emit_msl;
    _ = emit_hlsl;
    _ = emit_spirv;
    _ = emit_spirv_fn;
    _ = emit_spirv_stages;
    _ = emit_dxil;
}

test "translate simple compute shader with builtin vector member access to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = data[id.x] * 2.0;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "main_kernel") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "thread_position_in_grid") != null);
}

test "translate vertex shader with struct input to SPIR-V" {
    const source =
        \\struct VsIn {
        \\    @builtin(vertex_index) vertex_index: u32,
        \\    @location(0) uv: vec2f,
        \\};
        \\
        \\struct VsOut {
        \\    @builtin(position) position: vec4f,
        \\    @location(0) uv: vec2f,
        \\};
        \\
        \\@vertex
        \\fn main(input: VsIn) -> VsOut {
        \\    var out: VsOut;
        \\    return out;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate fragment shader with struct input to SPIR-V" {
    const source =
        \\struct FsIn {
        \\    @location(0) uv: vec2f,
        \\};
        \\
        \\struct FsOut {
        \\    @location(0) color: vec4f,
        \\};
        \\
        \\@fragment
        \\fn main(input: FsIn) -> FsOut {
        \\    var out: FsOut;
        \\    return out;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate vec4f constructor to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = vec4f(1.0, 2.0, 3.0, 4.0);
        \\    data[id.x] = value.x;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate vec4 generic constructor to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = vec4<f32>(1.0, 2.0, 3.0, 4.0);
        \\    data[id.x] = value.x;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}
