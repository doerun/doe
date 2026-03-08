const std = @import("std");
const ast_mod = @import("ast.zig");
const ir = @import("ir.zig");

const Ast = ast_mod.Ast;

pub fn parse_stage(self: anytype, attrs_start: u32, attrs_len: u32) !?ir.ShaderStage {
    var stage: ?ir.ShaderStage = null;
    for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
        const attr = self.module.tree.nodes.items[attr_idx];
        const name = self.module.tree.tokenSlice(attr.data.lhs);
        if (std.mem.eql(u8, name, "compute")) stage = .compute;
        if (std.mem.eql(u8, name, "vertex")) stage = .vertex;
        if (std.mem.eql(u8, name, "fragment")) stage = .fragment;
    }
    return stage;
}

pub fn parse_workgroup_size(self: anytype, attrs_start: u32, attrs_len: u32) ![3]u32 {
    var result: [3]u32 = .{ 1, 1, 1 };
    for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
        const attr = self.module.tree.nodes.items[attr_idx];
        if (!std.mem.eql(u8, self.module.tree.tokenSlice(attr.data.lhs), "workgroup_size")) continue;
        const span = decode_packed_span(attr.data.rhs);
        var i: usize = 0;
        while (i < span.len and i < result.len) : (i += 1) {
            const arg_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[span.start + i]];
            if (arg_node.tag != .int_literal) return error.InvalidAttribute;
            result[i] = try std.fmt.parseInt(u32, self.module.tree.tokenSlice(arg_node.main_token), 10);
        }
    }
    return result;
}

pub fn parse_binding(self: anytype, attrs_start: u32, attrs_len: u32) !?ir.BindingPoint {
    var group: ?u32 = null;
    var binding: ?u32 = null;
    for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
        const attr = self.module.tree.nodes.items[attr_idx];
        const name = self.module.tree.tokenSlice(attr.data.lhs);
        const value = try parse_single_int_attr(self.module.tree, attr_idx);
        if (std.mem.eql(u8, name, "group")) group = value;
        if (std.mem.eql(u8, name, "binding")) binding = value;
    }
    if (group != null and binding != null) return .{ .group = group.?, .binding = binding.? };
    return null;
}

pub fn parse_io_attr(self: anytype, attrs_start: u32, attrs_len: u32) !?ir.IoAttr {
    if (attrs_len == 0) return null;
    var result = ir.IoAttr{};
    var seen = false;
    for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
        const attr = self.module.tree.nodes.items[attr_idx];
        const name = self.module.tree.tokenSlice(attr.data.lhs);
        if (std.mem.eql(u8, name, "builtin")) {
            result.builtin = try parse_builtin_attr(self.module.tree, attr_idx);
            seen = true;
        } else if (std.mem.eql(u8, name, "location")) {
            result.location = try parse_single_int_attr(self.module.tree, attr_idx);
            seen = true;
        } else if (std.mem.eql(u8, name, "flat")) {
            result.interpolation = .flat;
            seen = true;
        } else if (std.mem.eql(u8, name, "invariant")) {
            result.invariant = true;
            seen = true;
        }
    }
    return if (seen) result else null;
}

pub fn infer_builtin_call(self: anytype, name: []const u8, arg_types: []const ir.TypeId) !ir.TypeId {
    if (std.mem.eql(u8, name, "workgroupBarrier") or std.mem.eql(u8, name, "storageBarrier")) return self.module.void_type;
    if (std.mem.eql(u8, name, "arrayLength")) return self.module.u32_type;
    if (std.mem.eql(u8, name, "dot")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        const first = self.module.types.get(arg_types[0]);
        return switch (first) {
            .vector => |vec| vec.elem,
            else => error.UnsupportedBuiltin,
        };
    }
    if (std.mem.eql(u8, name, "textureLoad")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        const first = self.module.types.get(arg_types[0]);
        return switch (first) {
            .texture_2d => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            else => error.UnsupportedBuiltin,
        };
    }
    if (std.mem.eql(u8, name, "atomicLoad") or std.mem.eql(u8, name, "atomicStore") or std.mem.eql(u8, name, "atomicAdd") or std.mem.eql(u8, name, "atomicSub") or std.mem.eql(u8, name, "atomicMax") or std.mem.eql(u8, name, "atomicMin") or std.mem.eql(u8, name, "atomicAnd") or std.mem.eql(u8, name, "atomicOr") or std.mem.eql(u8, name, "atomicXor") or std.mem.eql(u8, name, "atomicExchange")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return switch (self.module.types.get(arg_types[0])) {
            .atomic => |inner| inner,
            else => arg_types[0],
        };
    }
    if (std.mem.eql(u8, name, "min") or std.mem.eql(u8, name, "max") or std.mem.eql(u8, name, "clamp") or std.mem.eql(u8, name, "select") or std.mem.eql(u8, name, "abs") or std.mem.eql(u8, name, "sqrt") or std.mem.eql(u8, name, "sin") or std.mem.eql(u8, name, "cos") or std.mem.eql(u8, name, "normalize") or std.mem.eql(u8, name, "length") or std.mem.eql(u8, name, "distance")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    return error.UnsupportedBuiltin;
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

fn decode_packed_span(raw: u32) struct { start: u32, len: u32 } {
    return .{ .start = raw & 0xFFFF, .len = raw >> 16 };
}

fn parse_single_int_attr(tree: *const Ast, attr_idx: u32) !u32 {
    const attr = tree.nodes.items[attr_idx];
    const span = decode_packed_span(attr.data.rhs);
    if (span.len == 0) return error.InvalidAttribute;
    const arg = tree.nodes.items[tree.extra_data.items[span.start]];
    if (arg.tag != .int_literal) return error.InvalidAttribute;
    return try std.fmt.parseInt(u32, tree.tokenSlice(arg.main_token), 10);
}

fn parse_builtin_attr(tree: *const Ast, attr_idx: u32) !ir.Builtin {
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
