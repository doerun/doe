// doe_wgsl/mod.zig — WGSL compiler module entry point.
//
// Public API for parsing WGSL source and emitting target shading languages.
// Currently supports MSL emission; SPIR-V and HLSL are planned.

pub const token = @import("token.zig");
pub const lexer = @import("lexer.zig");
pub const ast = @import("ast.zig");
pub const parser = @import("parser.zig");
pub const emit_msl = @import("emit_msl.zig");

const std = @import("std");

pub const TranslateError = error{
    InvalidWgsl,
    OutputTooLarge,
    OutOfMemory,
    UnexpectedToken,
};

pub const MAX_OUTPUT: usize = emit_msl.MAX_OUTPUT;
pub const MAX_BINDINGS: usize = 16;

pub const BindingMeta = struct {
    group: u32,
    binding: u32,
};

/// Extract @group(N) @binding(M) metadata from WGSL source. Returns binding count.
pub fn extractBindings(allocator: std.mem.Allocator, wgsl: []const u8, out: []BindingMeta) TranslateError!usize {
    var tree = parser.parseSource(allocator, wgsl) catch |err| {
        return switch (err) {
            error.OutOfMemory => TranslateError.OutOfMemory,
            error.UnexpectedToken => TranslateError.UnexpectedToken,
        };
    };
    defer tree.deinit();
    return extractBindingsFromAst(&tree, out);
}

fn extractBindingsFromAst(tree: *const ast.Ast, out: []BindingMeta) usize {
    var count: usize = 0;
    for (tree.nodes.items) |node| {
        if (node.tag != .global_var) continue;
        // GlobalVarExtra layout: [name, addr_space, access_mode, init, attrs_start, attrs_len]
        const extra_base = node.data.rhs;
        const attrs_start = tree.extra_data.items[extra_base + 4];
        const attrs_len = tree.extra_data.items[extra_base + 5];

        var group: ?u32 = null;
        var binding: ?u32 = null;
        for (tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
            const attr = tree.nodes.items[attr_idx];
            if (attr.tag != .attribute) continue;
            const name = tree.tokenSlice(attr.data.lhs);
            const args_start_packed = attr.data.rhs;
            const args_start_val = args_start_packed & 0xFFFF;
            const args_len_val = args_start_packed >> 16;
            if (args_len_val < 1) continue;
            const arg_node = tree.nodes.items[tree.extra_data.items[args_start_val]];
            if (arg_node.tag != .int_literal) continue;
            const val = std.fmt.parseInt(u32, tree.tokenSlice(arg_node.main_token), 10) catch continue;
            if (std.mem.eql(u8, name, "group")) group = val;
            if (std.mem.eql(u8, name, "binding")) binding = val;
        }
        if (group != null and binding != null) {
            if (count < out.len) {
                out[count] = .{ .group = group.?, .binding = binding.? };
                count += 1;
            }
        }
    }
    return count;
}

/// Parse WGSL source and emit MSL. Returns the number of bytes written.
/// This is the drop-in replacement for the old doe_wgsl_msl.translate().
pub fn translateToMsl(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var tree = parser.parseSource(allocator, wgsl) catch |err| {
        return switch (err) {
            error.OutOfMemory => TranslateError.OutOfMemory,
            error.UnexpectedToken => TranslateError.UnexpectedToken,
        };
    };
    defer tree.deinit();

    return emit_msl.emit(&tree, out) catch |err| {
        return switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.InvalidAst => TranslateError.InvalidWgsl,
        };
    };
}

test {
    _ = token;
    _ = lexer;
    _ = ast;
    _ = parser;
    _ = emit_msl;
}
