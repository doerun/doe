const std = @import("std");
const ast_mod = @import("ast.zig");
const ir = @import("ir.zig");
const sema_helpers = @import("sema_helpers.zig");

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
            result[i] = try sema_helpers.parse_wgsl_int_literal(u32, self.module.tree.tokenSlice(arg_node.main_token));
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
        } else if (std.mem.eql(u8, name, "blend_src")) {
            result.blend_src = try parse_single_int_attr(self.module.tree, attr_idx);
            seen = true;
        } else if (std.mem.eql(u8, name, "flat")) {
            result.interpolation = .flat;
            seen = true;
        } else if (std.mem.eql(u8, name, "interpolate")) {
            result.interpolation = try parse_interpolation_attr(self.module.tree, attr_idx);
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
    if (std.mem.eql(u8, name, "textureStore")) return self.module.void_type;
    if (std.mem.eql(u8, name, "textureSample") or std.mem.eql(u8, name, "textureSampleLevel") or std.mem.eql(u8, name, "textureSampleGrad") or std.mem.eql(u8, name, "textureSampleOffset") or std.mem.eql(u8, name, "textureSampleLevelOffset")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return switch (self.module.types.get(arg_types[0])) {
            .texture_2d => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            .texture_3d => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            .texture_cube => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            .texture_2d_array => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            else => error.UnsupportedBuiltin,
        };
    }
    if (std.mem.eql(u8, name, "textureSampleCompare") or std.mem.eql(u8, name, "textureSampleCompareLevel")) {
        return try self.module.types.intern(.{ .scalar = .f32 });
    }
    if (std.mem.eql(u8, name, "textureGather")) {
        if (arg_types.len < 2) return error.UnsupportedBuiltin;
        // textureGather(component, texture, sampler, coords) — first arg is component u32
        return switch (self.module.types.get(arg_types[1])) {
            .texture_2d => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            .texture_cube => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            .texture_2d_array => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
            else => error.UnsupportedBuiltin,
        };
    }
    if (std.mem.eql(u8, name, "textureGatherCompare")) {
        return try self.module.types.intern(.{ .vector = .{ .elem = try self.module.types.intern(.{ .scalar = .f32 }), .len = 4 } });
    }
    if (std.mem.eql(u8, name, "textureDimensions")) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return switch (self.module.types.get(arg_types[0])) {
            .texture_2d, .texture_2d_array, .texture_depth_2d, .texture_multisampled_2d, .storage_texture_2d => blk: {
                const u32_ty = try self.module.types.intern(.{ .scalar = .u32 });
                break :blk try self.module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 2 } });
            },
            .texture_3d, .texture_cube, .texture_depth_cube => blk: {
                const u32_ty = try self.module.types.intern(.{ .scalar = .u32 });
                break :blk try self.module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 3 } });
            },
            else => error.UnsupportedBuiltin,
        };
    }
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
            // storage_texture_2d textureLoad returns a vec4 of the format's element type.
            .storage_texture_2d => |storage| {
                const elem_scalar = storage_format_scalar(storage.format);
                const elem_ty = try self.module.types.intern(.{ .scalar = elem_scalar });
                return try self.module.types.intern(.{ .vector = .{ .elem = elem_ty, .len = 4 } });
            },
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
    if (is_passthrough_math(name)) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    // Subgroup reduction/scan built-ins return the same type as their input.
    if (is_subgroup_value_op(name)) {
        if (arg_types.len == 0) return error.UnsupportedBuiltin;
        return arg_types[0];
    }
    // subgroupBallot returns vec4<u32> (128-bit ballot result).
    if (std.mem.eql(u8, name, "subgroupBallot")) {
        const u32_ty = try self.module.types.intern(.{ .scalar = .u32 });
        return try self.module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 4 } });
    }
    // subgroupAll / subgroupAny return bool.
    if (std.mem.eql(u8, name, "subgroupAll") or std.mem.eql(u8, name, "subgroupAny")) {
        return try self.module.types.intern(.{ .scalar = .bool });
    }
    // Pack builtins return u32.
    if (is_pack_builtin(name)) {
        return try self.module.types.intern(.{ .scalar = .u32 });
    }
    // Unpack builtins return vec2f or vec4f.
    if (is_unpack_2_builtin(name)) {
        const f32_ty = try self.module.types.intern(.{ .scalar = .f32 });
        return try self.module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 2 } });
    }
    if (is_unpack_4_builtin(name)) {
        const f32_ty = try self.module.types.intern(.{ .scalar = .f32 });
        return try self.module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    }
    return error.UnsupportedBuiltin;
}

fn is_subgroup_value_op(name: []const u8) bool {
    const ops = [_][]const u8{
        "subgroupAdd",          "subgroupMin",       "subgroupMax",            "subgroupMul",
        "subgroupAnd",          "subgroupOr",        "subgroupXor",            "subgroupExclusiveAdd",
        "subgroupInclusiveAdd", "subgroupShuffle",   "subgroupShuffleDown",    "subgroupShuffleUp",
        "subgroupShuffleXor",   "subgroupBroadcast", "subgroupBroadcastFirst",
    };
    for (ops) |op| {
        if (std.mem.eql(u8, name, op)) return true;
    }
    return false;
}

/// Math/comparison builtins that return the same type as their first argument.
fn is_passthrough_math(name: []const u8) bool {
    const ops = [_][]const u8{
        "min",          "max",          "clamp",        "select",       "abs",
        "sqrt",         "sin",          "cos",          "normalize",    "length",
        "distance",     "fract",        "mix",          "inverseSqrt",  "degrees",
        "radians",      "atan2",        "ldexp",        "fma",          "smoothstep",
        "sign",         "floor",        "ceil",         "round",        "trunc",
        "exp",          "exp2",         "log",          "log2",         "pow",
        "step",         "tan",          "asin",         "acos",         "atan",
        "sinh",         "cosh",         "tanh",         "saturate",     "dot",
        "cross",        "reflect",      "refract",      "modf",         "frexp",
    };
    for (ops) |op| {
        if (std.mem.eql(u8, name, op)) return true;
    }
    return false;
}

fn is_pack_builtin(name: []const u8) bool {
    const ops = [_][]const u8{ "pack2x16float", "pack4x8unorm", "pack4x8snorm", "pack2x16snorm", "pack2x16unorm" };
    for (ops) |op| {
        if (std.mem.eql(u8, name, op)) return true;
    }
    return false;
}

fn is_unpack_2_builtin(name: []const u8) bool {
    const ops = [_][]const u8{ "unpack2x16float", "unpack2x16snorm", "unpack2x16unorm" };
    for (ops) |op| {
        if (std.mem.eql(u8, name, op)) return true;
    }
    return false;
}

fn is_unpack_4_builtin(name: []const u8) bool {
    const ops = [_][]const u8{ "unpack4x8unorm", "unpack4x8snorm" };
    for (ops) |op| {
        if (std.mem.eql(u8, name, op)) return true;
    }
    return false;
}

fn storage_format_scalar(format: ir.TextureFormat) ir.ScalarType {
    return switch (format) {
        .rgba8unorm, .rgba8snorm, .rgba16float, .r32float, .rg32float, .rgba32float => .f32,
        .rgba8uint, .rgba16uint, .r32uint, .rg32uint, .rgba32uint => .u32,
        .rgba8sint, .rgba16sint, .r32sint, .rg32sint, .rgba32sint => .i32,
    };
}

pub fn parse_override_id(self: anytype, attrs_start: u32, attrs_len: u32) !?u32 {
    for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
        const attr = self.module.tree.nodes.items[attr_idx];
        const name = self.module.tree.tokenSlice(attr.data.lhs);
        if (std.mem.eql(u8, name, "id")) {
            return try parse_single_int_attr(self.module.tree, attr_idx);
        }
    }
    return null;
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
    return try sema_helpers.parse_wgsl_int_literal(u32, tree.tokenSlice(arg.main_token));
}

fn parse_interpolation_attr(tree: *const Ast, attr_idx: u32) !ir.Interpolation {
    const attr = tree.nodes.items[attr_idx];
    const span = decode_packed_span(attr.data.rhs);
    if (span.len == 0) return error.InvalidAttribute;
    const arg = tree.nodes.items[tree.extra_data.items[span.start]];
    if (arg.tag != .ident_expr) return error.InvalidAttribute;
    const name = tree.tokenSlice(arg.main_token);
    if (std.mem.eql(u8, name, "flat")) return .flat;
    if (std.mem.eql(u8, name, "linear")) return .linear;
    if (std.mem.eql(u8, name, "perspective")) return .perspective;
    return error.InvalidAttribute;
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
    if (std.mem.eql(u8, name, "subgroup_size")) return .subgroup_size;
    if (std.mem.eql(u8, name, "subgroup_invocation_id")) return .subgroup_invocation_id;
    if (std.mem.eql(u8, name, "clip_distances")) return .clip_distances;
    if (std.mem.eql(u8, name, "primitive_index")) return .primitive_index;
    return error.InvalidAttribute;
}
