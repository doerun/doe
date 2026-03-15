const std = @import("std");
const ast_mod = @import("ast.zig");
const ir = @import("ir.zig");
const sema_helpers = @import("sema_helpers.zig");

const Ast = ast_mod.Ast;
const decode_packed_span = sema_helpers.decode_packed_span;
const parse_single_int_attr = sema_helpers.parse_single_int_attr;
const parse_builtin_attr = sema_helpers.parse_builtin_attr;
const parse_wgsl_int_literal = sema_helpers.parse_wgsl_int_literal;

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
            result[i] = try parse_wgsl_int_literal(u32, self.module.tree.tokenSlice(arg_node.main_token));
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
        } else if (std.mem.eql(u8, name, "blend_src")) {
            result.blend_src = try parse_single_int_attr(self.module.tree, attr_idx);
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
    if (std.mem.eql(u8, name, "textureSample")) {
        return try infer_texture_sample_call(self, arg_types, false);
    }
    if (std.mem.eql(u8, name, "textureSampleLevel")) {
        return try infer_texture_sample_call(self, arg_types, true);
    }
    if (std.mem.eql(u8, name, "textureDimensions")) {
        return try infer_texture_dimensions_call(self, arg_types);
    }
    if (std.mem.eql(u8, name, "textureStore")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return switch (self.module.types.get(arg_types[0])) {
            .storage_texture_2d => self.module.void_type,
            else => error.UnsupportedBuiltin,
        };
    }
    if (std.mem.eql(u8, name, "unpack2x16float")) {
        if (arg_types.len != 1 or arg_types[0] != self.module.u32_type) return error.UnsupportedBuiltin;
        return try self.module.types.intern(.{ .vector = .{ .elem = self.module.f32_type, .len = 2 } });
    }
    if (std.mem.eql(u8, name, "pack2x16float")) {
        if (arg_types.len != 1) return error.UnsupportedBuiltin;
        return switch (self.module.types.get(arg_types[0])) {
            .vector => |vec| if (vec.len == 2 and vec.elem == self.module.f32_type) self.module.u32_type else error.UnsupportedBuiltin,
            else => error.UnsupportedBuiltin,
        };
    }
    if (std.mem.eql(u8, name, "unpack4x8snorm") or std.mem.eql(u8, name, "unpack4x8unorm")) {
        if (arg_types.len != 1 or arg_types[0] != self.module.u32_type) return error.UnsupportedBuiltin;
        return try self.module.types.intern(.{ .vector = .{ .elem = self.module.f32_type, .len = 4 } });
    }
    if (std.mem.eql(u8, name, "pack4x8snorm") or std.mem.eql(u8, name, "pack4x8unorm")) {
        if (arg_types.len != 1) return error.UnsupportedBuiltin;
        return switch (self.module.types.get(arg_types[0])) {
            .vector => |vec| if (vec.len == 4 and vec.elem == self.module.f32_type) self.module.u32_type else error.UnsupportedBuiltin,
            else => error.UnsupportedBuiltin,
        };
    }
    if (std.mem.eql(u8, name, "subgroupAdd") or std.mem.eql(u8, name, "subgroupMin") or std.mem.eql(u8, name, "subgroupMax") or std.mem.eql(u8, name, "subgroupExclusiveAdd")) {
        if (arg_types.len != 1) return error.UnsupportedBuiltin;
        if (!is_subgroup_numeric_type(self, arg_types[0])) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    if (std.mem.eql(u8, name, "subgroupBroadcast") or std.mem.eql(u8, name, "subgroupShuffle") or std.mem.eql(u8, name, "subgroupShuffleXor")) {
        if (arg_types.len != 2) return error.UnsupportedBuiltin;
        if (!is_subgroup_numeric_type(self, arg_types[0])) return error.UnsupportedBuiltin;
        if (arg_types[1] != self.module.u32_type) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    if (std.mem.eql(u8, name, "atomicLoad") or std.mem.eql(u8, name, "atomicStore") or std.mem.eql(u8, name, "atomicAdd") or std.mem.eql(u8, name, "atomicSub") or std.mem.eql(u8, name, "atomicMax") or std.mem.eql(u8, name, "atomicMin") or std.mem.eql(u8, name, "atomicAnd") or std.mem.eql(u8, name, "atomicOr") or std.mem.eql(u8, name, "atomicXor") or std.mem.eql(u8, name, "atomicExchange")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return switch (self.module.types.get(arg_types[0])) {
            .atomic => |inner| inner,
            else => arg_types[0],
        };
    }
    if (std.mem.eql(u8, name, "min") or std.mem.eql(u8, name, "max") or std.mem.eql(u8, name, "clamp") or std.mem.eql(u8, name, "select") or std.mem.eql(u8, name, "abs") or std.mem.eql(u8, name, "sqrt") or std.mem.eql(u8, name, "sin") or std.mem.eql(u8, name, "cos") or std.mem.eql(u8, name, "tan") or std.mem.eql(u8, name, "acos") or std.mem.eql(u8, name, "asin") or std.mem.eql(u8, name, "atan") or std.mem.eql(u8, name, "cosh") or std.mem.eql(u8, name, "sinh") or std.mem.eql(u8, name, "sign") or std.mem.eql(u8, name, "fract") or std.mem.eql(u8, name, "floor") or std.mem.eql(u8, name, "ceil") or std.mem.eql(u8, name, "round") or std.mem.eql(u8, name, "trunc") or std.mem.eql(u8, name, "exp") or std.mem.eql(u8, name, "log") or std.mem.eql(u8, name, "exp2") or std.mem.eql(u8, name, "log2") or std.mem.eql(u8, name, "inverseSqrt") or std.mem.eql(u8, name, "tanh") or std.mem.eql(u8, name, "normalize") or std.mem.eql(u8, name, "degrees") or std.mem.eql(u8, name, "radians")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    if (std.mem.eql(u8, name, "pow") or std.mem.eql(u8, name, "step") or std.mem.eql(u8, name, "atan2") or std.mem.eql(u8, name, "ldexp")) {
        if (arg_types.len != 2) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    if (std.mem.eql(u8, name, "mix") or std.mem.eql(u8, name, "smoothstep") or std.mem.eql(u8, name, "fma")) {
        if (arg_types.len != 3) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    if (std.mem.eql(u8, name, "length") or std.mem.eql(u8, name, "distance")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return scalar_result_type(self, arg_types[0]);
    }
    if (std.mem.eql(u8, name, "cross")) {
        if (arg_types.len != 2) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    return error.UnsupportedBuiltin;
}

fn scalar_result_type(self: anytype, ty: ir.TypeId) !ir.TypeId {
    return switch (self.module.types.get(ty)) {
        .vector => |vec| vec.elem,
        .scalar => ty,
        else => error.UnsupportedBuiltin,
    };
}

fn infer_texture_sample_call(self: anytype, arg_types: []const ir.TypeId, explicit_level: bool) !ir.TypeId {
    const expected_arg_count: usize = if (explicit_level) 4 else 3;
    if (arg_types.len != expected_arg_count) return error.UnsupportedBuiltin;
    const sample_ty = switch (self.module.types.get(arg_types[0])) {
        .texture_2d => |inner| inner,
        else => return error.UnsupportedBuiltin,
    };
    if (!is_sampler_type(self, arg_types[1])) return error.UnsupportedBuiltin;
    if (!is_float_coord_2d(self, arg_types[2])) return error.UnsupportedBuiltin;
    if (explicit_level and !is_float_scalar(self, arg_types[3])) return error.UnsupportedBuiltin;
    return try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } });
}

fn infer_texture_dimensions_call(self: anytype, arg_types: []const ir.TypeId) !ir.TypeId {
    if (arg_types.len == 0) return error.UnsupportedBuiltin;
    switch (self.module.types.get(arg_types[0])) {
        .texture_2d => {
            if (arg_types.len != 2 or !is_integer_scalar(self, arg_types[1])) return error.UnsupportedBuiltin;
        },
        .storage_texture_2d => {
            if (arg_types.len != 1) return error.UnsupportedBuiltin;
        },
        else => return error.UnsupportedBuiltin,
    }
    return try self.module.types.intern(.{ .vector = .{ .elem = self.module.u32_type, .len = 2 } });
}

fn is_sampler_type(self: anytype, ty: ir.TypeId) bool {
    return switch (self.module.types.get(ty)) {
        .sampler => true,
        else => false,
    };
}

fn is_float_coord_2d(self: anytype, ty: ir.TypeId) bool {
    return switch (self.module.types.get(ty)) {
        .vector => |vec| vec.len == 2 and is_float_scalar(self, vec.elem),
        else => false,
    };
}

fn is_float_scalar(self: anytype, ty: ir.TypeId) bool {
    return switch (self.module.types.get(ty)) {
        .scalar => |scalar| switch (scalar) {
            .f32, .f16, .abstract_float => true,
            else => false,
        },
        else => false,
    };
}

fn is_integer_scalar(self: anytype, ty: ir.TypeId) bool {
    return switch (self.module.types.get(ty)) {
        .scalar => |scalar| switch (scalar) {
            .u32, .i32, .abstract_int => true,
            else => false,
        },
        else => false,
    };
}

fn is_subgroup_numeric_type(self: anytype, ty: ir.TypeId) bool {
    return switch (self.module.types.get(ty)) {
        .scalar => |scalar| switch (scalar) {
            .u32, .i32, .f16, .f32, .abstract_int, .abstract_float => true,
            else => false,
        },
        .vector => |vec| switch (self.module.types.get(vec.elem)) {
            .scalar => |scalar| switch (scalar) {
                .u32, .i32, .f16, .f32, .abstract_int, .abstract_float => true,
                else => false,
            },
            else => false,
        },
        else => false,
    };
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
