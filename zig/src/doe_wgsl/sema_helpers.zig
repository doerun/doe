const std = @import("std");
const ast_mod = @import("ast.zig");
const ir = @import("ir.zig");
const sema_types = @import("sema_types.zig");

const Ast = ast_mod.Ast;
const SemanticModule = sema_types.SemanticModule;

pub fn init_builtin_types(module: *SemanticModule) !void {
    module.void_type = try module.types.intern(.{ .scalar = .void });
    module.bool_type = try module.types.intern(.{ .scalar = .bool });
    module.abstract_int_type = try module.types.intern(.{ .scalar = .abstract_int });
    module.abstract_float_type = try module.types.intern(.{ .scalar = .abstract_float });
    module.i32_type = try module.types.intern(.{ .scalar = .i32 });
    module.u32_type = try module.types.intern(.{ .scalar = .u32 });
    module.f32_type = try module.types.intern(.{ .scalar = .f32 });
    module.f16_type = try module.types.intern(.{ .scalar = .f16 });
    module.sampler_type = try module.types.intern(.{ .sampler = {} });
}

pub fn concrete_numeric_type(module: *SemanticModule, lhs: ir.TypeId, rhs: ir.TypeId) ir.TypeId {
    if (lhs == rhs) return lhs;
    if (lhs == module.abstract_int_type) return rhs;
    if (rhs == module.abstract_int_type) return lhs;
    if (lhs == module.abstract_float_type) return rhs;
    if (rhs == module.abstract_float_type) return lhs;
    return lhs;
}

pub fn decode_packed_span(raw: u32) struct { start: u32, len: u32 } {
    return .{ .start = raw & 0xFFFF, .len = raw >> 16 };
}

pub fn parse_single_int_attr(tree: *const Ast, attr_idx: u32) !u32 {
    const attr = tree.nodes.items[attr_idx];
    const span = decode_packed_span(attr.data.rhs);
    if (span.len == 0) return error.InvalidAttribute;
    const arg = tree.nodes.items[tree.extra_data.items[span.start]];
    if (arg.tag != .int_literal) return error.InvalidAttribute;
    return try std.fmt.parseInt(u32, tree.tokenSlice(arg.main_token), 10);
}

pub fn parse_builtin_attr(tree: *const Ast, attr_idx: u32) !ir.Builtin {
    const attr = tree.nodes.items[attr_idx];
    const span = decode_packed_span(attr.data.rhs);
    if (span.len == 0) return error.InvalidAttribute;
    const arg = tree.nodes.items[tree.extra_data.items[span.start]];
    if (arg.tag != .ident_expr) return error.InvalidAttribute;
    const name = tree.tokenSlice(arg.main_token);
    if (std.mem.eql(u8, name, "position")) return .position;
    if (std.mem.eql(u8, name, "frag_depth")) return .frag_depth;
    if (std.mem.eql(u8, name, "front_facing")) return .front_facing;
    if (std.mem.eql(u8, name, "global_invocation_id")) return .global_invocation_id;
    if (std.mem.eql(u8, name, "local_invocation_id")) return .local_invocation_id;
    if (std.mem.eql(u8, name, "local_invocation_index")) return .local_invocation_index;
    if (std.mem.eql(u8, name, "workgroup_id")) return .workgroup_id;
    if (std.mem.eql(u8, name, "num_workgroups")) return .num_workgroups;
    if (std.mem.eql(u8, name, "sample_index")) return .sample_index;
    if (std.mem.eql(u8, name, "sample_mask")) return .sample_mask;
    if (std.mem.eql(u8, name, "vertex_index")) return .vertex_index;
    if (std.mem.eql(u8, name, "instance_index")) return .instance_index;
    return error.InvalidAttribute;
}

pub fn parse_address_space(name: []const u8) !ir.AddressSpace {
    if (std.mem.eql(u8, name, "function")) return .function;
    if (std.mem.eql(u8, name, "private")) return .private;
    if (std.mem.eql(u8, name, "workgroup")) return .workgroup;
    if (std.mem.eql(u8, name, "uniform")) return .uniform;
    if (std.mem.eql(u8, name, "storage")) return .storage;
    return error.InvalidAttribute;
}

pub fn parse_access(name: []const u8) !ir.AccessMode {
    if (std.mem.eql(u8, name, "read")) return .read;
    if (std.mem.eql(u8, name, "write")) return .write;
    if (std.mem.eql(u8, name, "read_write")) return .read_write;
    return error.InvalidAttribute;
}

pub fn parse_storage_texture_format(name: []const u8) !ir.TextureFormat {
    if (std.mem.eql(u8, name, "rgba8unorm")) return .rgba8unorm;
    return error.InvalidAttribute;
}
