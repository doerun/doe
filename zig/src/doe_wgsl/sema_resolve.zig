const std = @import("std");
const ast_mod = @import("ast.zig");
const ir = @import("ir.zig");
const sema_helpers = @import("sema_helpers.zig");

const Node = ast_mod.Node;

const parse_access = sema_helpers.parse_access;
const parse_address_space = sema_helpers.parse_address_space;
const parse_wgsl_int_literal = sema_helpers.parse_wgsl_int_literal;
const parse_storage_texture_format = sema_helpers.parse_storage_texture_format;

pub fn resolve_type_parameterized(self: anytype, node: Node) !ir.TypeId {
    const name = self.module.tree.tokenSlice(node.main_token);
    const params_start = node.data.lhs;
    const params_len = node.data.rhs;
    if (std.mem.eql(u8, name, "vec2") or std.mem.eql(u8, name, "vec3") or std.mem.eql(u8, name, "vec4")) {
        if (params_len != 1) return error.InvalidType;
        const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]);
        const len: u8 = if (std.mem.eql(u8, name, "vec2")) 2 else if (std.mem.eql(u8, name, "vec3")) 3 else 4;
        return try self.module.types.intern(.{ .vector = .{ .elem = elem, .len = len } });
    }
    if (std.mem.eql(u8, name, "mat2x2") or std.mem.eql(u8, name, "mat3x3") or std.mem.eql(u8, name, "mat4x4")) {
        if (params_len != 1) return error.InvalidType;
        const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]);
        const dim: u8 = if (std.mem.eql(u8, name, "mat2x2")) 2 else if (std.mem.eql(u8, name, "mat3x3")) 3 else 4;
        return try self.module.types.intern(.{ .matrix = .{ .elem = elem, .columns = dim, .rows = dim } });
    }
    if (std.mem.eql(u8, name, "array")) {
        if (params_len < 1 or params_len > 2) return error.InvalidType;
        const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]);
        var len: ?u32 = null;
        if (params_len == 2) {
            const len_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start + 1]];
            if (len_node.tag != .int_literal) return error.InvalidType;
            len = parse_wgsl_int_literal(u32, self.module.tree.tokenSlice(len_node.main_token)) catch return error.InvalidType;
        }
        return try self.module.types.intern(.{ .array = .{ .elem = elem, .len = len } });
    }
    if (std.mem.eql(u8, name, "atomic")) {
        if (params_len != 1) return error.InvalidType;
        return try self.module.types.intern(.{ .atomic = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]) });
    }
    if (std.mem.eql(u8, name, "texture_2d")) {
        if (params_len != 1) return error.InvalidType;
        return try self.module.types.intern(.{ .texture_2d = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]) });
    }
    if (std.mem.eql(u8, name, "texture_storage_2d")) {
        if (params_len != 2) return error.InvalidType;
        const format_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start]];
        if (format_node.tag != .type_name) return error.InvalidType;
        const access_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start + 1]];
        if (access_node.tag != .type_name) return error.InvalidType;
        const access = try parse_access(self.module.tree.tokenSlice(access_node.main_token));
        if (access != .write) return error.InvalidType;
        return try self.module.types.intern(.{ .storage_texture_2d = .{
            .format = try parse_storage_texture_format(self.module.tree.tokenSlice(format_node.main_token)),
            .access = access,
        } });
    }
    if (std.mem.eql(u8, name, "ptr")) {
        if (params_len < 2 or params_len > 3) return error.InvalidType;
        const addr_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start]];
        if (addr_node.tag != .type_name) return error.InvalidType;
        const addr_space = try parse_address_space(self.module.tree.tokenSlice(addr_node.main_token));
        const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start + 1]);
        const access = if (params_len == 3) blk: {
            const access_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start + 2]];
            if (access_node.tag != .type_name) return error.InvalidType;
            break :blk try parse_access(self.module.tree.tokenSlice(access_node.main_token));
        } else .read_write;
        return try self.module.types.intern(.{ .ref = .{ .elem = elem, .addr_space = addr_space, .access = access } });
    }
    return error.UnknownType;
}
