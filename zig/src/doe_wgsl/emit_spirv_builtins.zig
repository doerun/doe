const std = @import("std");
const ir = @import("ir.zig");
const spirv = @import("spirv_builder.zig");

pub fn emit_builtin(self: anytype, call: anytype, result_ty: ir.TypeId) !?u32 {
    if (std.mem.eql(u8, call.name, "workgroupBarrier")) {
        try emit_control_barrier(self, spirv.MemorySemantics.AcquireRelease | spirv.MemorySemantics.WorkgroupMemory);
        return 0;
    }
    if (std.mem.eql(u8, call.name, "storageBarrier")) {
        try emit_control_barrier(self, spirv.MemorySemantics.AcquireRelease | spirv.MemorySemantics.UniformMemory | spirv.MemorySemantics.ImageMemory);
        return 0;
    }
    if (std.mem.startsWith(u8, call.name, "atomic")) {
        return try emit_atomic_call(self, call, result_ty);
    }
    if (std.mem.eql(u8, call.name, "arrayLength")) {
        return try emit_array_length(self, call, result_ty);
    }
    if (std.mem.eql(u8, call.name, "textureLoad")) {
        return try emit_texture_load(self, call, result_ty);
    }
    if (std.mem.eql(u8, call.name, "textureSample")) {
        return try emit_texture_sample(self, call, result_ty, false);
    }
    if (std.mem.eql(u8, call.name, "textureSampleLevel")) {
        return try emit_texture_sample(self, call, result_ty, true);
    }
    if (std.mem.eql(u8, call.name, "textureStore")) {
        try emit_texture_store(self, call);
        return 0;
    }
    if (std.mem.eql(u8, call.name, "textureDimensions")) {
        return try emit_texture_dimensions(self, call, result_ty);
    }
    if (std.mem.eql(u8, call.name, "dot")) {
        return try emit_dot(self, call, result_ty);
    }
    if (std.mem.eql(u8, call.name, "bitcast")) {
        if (call.args.len != 1) return error.InvalidIr;
        const result_type = try self.emitter.lower_type(result_ty);
        const result_id = self.emitter.builder.reserve_id();
        try self.emitter.builder.append_function_inst(
            spirv.Opcode.Bitcast,
            &.{ result_type, result_id, try self.emit_value_expr(self.function.expr_args.items[call.args.start]) },
        );
        return result_id;
    }
    if (std.mem.eql(u8, call.name, "pack2x16float")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 60);
    }
    if (std.mem.eql(u8, call.name, "unpack2x16float")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 62);
    }
    if (std.mem.eql(u8, call.name, "pack4x8unorm")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 58);
    }
    if (std.mem.eql(u8, call.name, "pack4x8snorm")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 59);
    }
    if (std.mem.eql(u8, call.name, "unpack4x8snorm")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 63);
    }
    if (std.mem.eql(u8, call.name, "unpack4x8unorm")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 64);
    }
    if (std.mem.eql(u8, call.name, "subgroupAdd")) {
        return try emit_subgroup_reduce(self, call, result_ty, subgroup_arithmetic_opcode(self.scalar_kind(result_ty), .add) orelse return error.UnsupportedConstruct);
    }
    if (std.mem.eql(u8, call.name, "subgroupExclusiveAdd")) {
        return try emit_subgroup_exclusive_scan(self, call, result_ty, subgroup_arithmetic_opcode(self.scalar_kind(result_ty), .add) orelse return error.UnsupportedConstruct);
    }
    if (std.mem.eql(u8, call.name, "subgroupMin")) {
        return try emit_subgroup_reduce(self, call, result_ty, subgroup_arithmetic_opcode(self.scalar_kind(result_ty), .min) orelse return error.UnsupportedConstruct);
    }
    if (std.mem.eql(u8, call.name, "subgroupMax")) {
        return try emit_subgroup_reduce(self, call, result_ty, subgroup_arithmetic_opcode(self.scalar_kind(result_ty), .max) orelse return error.UnsupportedConstruct);
    }
    if (std.mem.eql(u8, call.name, "subgroupBroadcast")) {
        return try emit_subgroup_shuffle_like(self, call, result_ty, spirv.Opcode.GroupNonUniformBroadcast);
    }
    if (std.mem.eql(u8, call.name, "subgroupShuffle")) {
        return try emit_subgroup_shuffle_like(self, call, result_ty, spirv.Opcode.GroupNonUniformShuffle);
    }
    if (std.mem.eql(u8, call.name, "subgroupShuffleXor")) {
        return try emit_subgroup_shuffle_like(self, call, result_ty, spirv.Opcode.GroupNonUniformShuffleXor);
    }
    if (std.mem.eql(u8, call.name, "select")) {
        if (call.args.len != 3) return error.InvalidIr;
        const result_type = try self.emitter.lower_type(result_ty);
        const result_id = self.emitter.builder.reserve_id();
        try self.emitter.builder.append_function_inst(
            spirv.Opcode.Select,
            &.{
                result_type,
                result_id,
                try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]),
                try self.emit_value_expr(self.function.expr_args.items[call.args.start + 1]),
                try self.emit_value_expr(self.function.expr_args.items[call.args.start]),
            },
        );
        return result_id;
    }

    if (builtin_inst_1(call.name, self.scalar_kind(result_ty))) |inst| {
        return try emit_glsl_ext_inst_args(self, call, result_ty, inst);
    }
    if (builtin_inst_2(call.name, self.scalar_kind(result_ty))) |inst| {
        return try emit_glsl_ext_inst_args(self, call, result_ty, inst);
    }
    if (builtin_inst_3(call.name, self.scalar_kind(result_ty))) |inst| {
        return try emit_glsl_ext_inst_args(self, call, result_ty, inst);
    }

    if (std.mem.eql(u8, call.name, "length")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 66);
    }
    if (std.mem.eql(u8, call.name, "distance")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 67);
    }
    if (std.mem.eql(u8, call.name, "cross")) {
        return try emit_glsl_ext_inst_args(self, call, result_ty, 68);
    }

    return null;
}

const TextureOpcode = struct {
    const SampledImage: u16 = 86;
    const ImageSampleImplicitLod: u16 = 87;
    const ImageSampleExplicitLod: u16 = 88;
    const ImageGather: u16 = 96;
    const ImageQuerySizeLod: u16 = 103;
    const ImageQuerySize: u16 = 104;
};

const SubgroupArithmeticOp = enum { add, min, max };

fn emit_glsl_ext_inst_args(self: anytype, call: anytype, result_ty: ir.TypeId, inst: u32) !u32 {
    const result_type = try self.emitter.lower_type(result_ty);
    const result_id = self.emitter.builder.reserve_id();
    const import_id = try self.emitter.builder.glsl450_import_id();

    var operands = std.ArrayListUnmanaged(u32){};
    defer operands.deinit(self.emitter.alloc);
    try operands.append(self.emitter.alloc, result_type);
    try operands.append(self.emitter.alloc, result_id);
    try operands.append(self.emitter.alloc, import_id);
    try operands.append(self.emitter.alloc, inst);

    var i: u32 = 0;
    while (i < call.args.len) : (i += 1) {
        try operands.append(self.emitter.alloc, try self.emit_value_expr(self.function.expr_args.items[call.args.start + i]));
    }

    try self.emitter.builder.append_function_inst(spirv.Opcode.ExtInst, operands.items);
    return result_id;
}

fn emit_subgroup_reduce(self: anytype, call: anytype, result_ty: ir.TypeId, opcode: u16) !u32 {
    if (call.args.len != 1) return error.InvalidIr;
    try self.emitter.builder.emit_capability(spirv.Capability.GroupNonUniform);
    try self.emitter.builder.emit_capability(spirv.Capability.GroupNonUniformArithmetic);
    const scope_id = try self.emitter.builder.const_u32(spirv.Scope.Subgroup);
    const op_id = try self.emitter.builder.const_u32(spirv.GroupOperation.Reduce);
    return try emit_result_inst(
        self,
        opcode,
        try self.emitter.lower_type(result_ty),
        &.{
            scope_id,
            op_id,
            try self.emit_value_expr(self.function.expr_args.items[call.args.start]),
        },
    );
}

fn emit_subgroup_exclusive_scan(self: anytype, call: anytype, result_ty: ir.TypeId, opcode: u16) !u32 {
    if (call.args.len != 1) return error.InvalidIr;
    try self.emitter.builder.emit_capability(spirv.Capability.GroupNonUniform);
    try self.emitter.builder.emit_capability(spirv.Capability.GroupNonUniformArithmetic);
    const scope_id = try self.emitter.builder.const_u32(spirv.Scope.Subgroup);
    const op_id = try self.emitter.builder.const_u32(spirv.GroupOperation.ExclusiveScan);
    return try emit_result_inst(
        self,
        opcode,
        try self.emitter.lower_type(result_ty),
        &.{
            scope_id,
            op_id,
            try self.emit_value_expr(self.function.expr_args.items[call.args.start]),
        },
    );
}

fn emit_subgroup_shuffle_like(self: anytype, call: anytype, result_ty: ir.TypeId, opcode: u16) !u32 {
    if (call.args.len != 2) return error.InvalidIr;
    try self.emitter.builder.emit_capability(spirv.Capability.GroupNonUniform);
    try self.emitter.builder.emit_capability(spirv.Capability.GroupNonUniformShuffle);
    const scope_id = try self.emitter.builder.const_u32(spirv.Scope.Subgroup);
    return try emit_result_inst(
        self,
        opcode,
        try self.emitter.lower_type(result_ty),
        &.{
            scope_id,
            try self.emit_value_expr(self.function.expr_args.items[call.args.start]),
            try self.emit_value_expr(self.function.expr_args.items[call.args.start + 1]),
        },
    );
}

fn subgroup_arithmetic_opcode(kind: anytype, op: SubgroupArithmeticOp) ?u16 {
    return switch (op) {
        .add => switch (kind) {
            .float => spirv.Opcode.GroupNonUniformFAdd,
            .signed, .unsigned => spirv.Opcode.GroupNonUniformIAdd,
            else => null,
        },
        .min => switch (kind) {
            .float => spirv.Opcode.GroupNonUniformFMin,
            .signed => spirv.Opcode.GroupNonUniformSMin,
            .unsigned => spirv.Opcode.GroupNonUniformUMin,
            else => null,
        },
        .max => switch (kind) {
            .float => spirv.Opcode.GroupNonUniformFMax,
            .signed => spirv.Opcode.GroupNonUniformSMax,
            .unsigned => spirv.Opcode.GroupNonUniformUMax,
            else => null,
        },
    };
}

fn emit_result_inst(self: anytype, opcode: u16, result_type: u32, operands: []const u32) !u32 {
    const result_id = self.emitter.builder.reserve_id();
    var words = std.ArrayListUnmanaged(u32){};
    defer words.deinit(self.emitter.alloc);
    try words.append(self.emitter.alloc, result_type);
    try words.append(self.emitter.alloc, result_id);
    try words.appendSlice(self.emitter.alloc, operands);
    try self.emitter.builder.append_function_inst(opcode, words.items);
    return result_id;
}

fn emit_texture_sample(self: anytype, call: anytype, result_ty: ir.TypeId, explicit_lod: bool) !u32 {
    const expected_arg_count: u32 = if (explicit_lod) 4 else 3;
    if (call.args.len != expected_arg_count) return error.InvalidIr;

    const texture_expr = self.function.expr_args.items[call.args.start];
    const sampler_expr = self.function.expr_args.items[call.args.start + 1];
    const image_id = try self.emit_value_expr(texture_expr);
    const sampler_id = try self.emit_value_expr(sampler_expr);
    const image_type = try self.emitter.lower_type(self.function.exprs.items[texture_expr].ty);
    const sampled_image_type = try self.emitter.lower_sampled_image_type(image_type);
    const sampled_image_id = try emit_result_inst(
        self,
        TextureOpcode.SampledImage,
        sampled_image_type,
        &.{ image_id, sampler_id },
    );

    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]);
    if (!explicit_lod) {
        return try emit_result_inst(
            self,
            TextureOpcode.ImageSampleImplicitLod,
            try self.emitter.lower_type(result_ty),
            &.{ sampled_image_id, coords_id },
        );
    }

    return try emit_result_inst(
        self,
        TextureOpcode.ImageSampleExplicitLod,
        try self.emitter.lower_type(result_ty),
        &.{
            sampled_image_id,
            coords_id,
            spirv.ImageOperandsMask.Lod,
            try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]),
        },
    );
}

fn emit_texture_dimensions(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len < 1 or call.args.len > 2) return error.InvalidIr;
    const texture_expr = self.function.expr_args.items[call.args.start];
    const image_id = try self.emit_value_expr(texture_expr);
    const opcode: u16 = if (call.args.len == 2) TextureOpcode.ImageQuerySizeLod else TextureOpcode.ImageQuerySize;
    if (call.args.len == 2) {
        return try emit_result_inst(
            self,
            opcode,
            try self.emitter.lower_type(result_ty),
            &.{
                image_id,
                try self.emit_value_expr(self.function.expr_args.items[call.args.start + 1]),
            },
        );
    }
    return try emit_result_inst(
        self,
        opcode,
        try self.emitter.lower_type(result_ty),
        &.{image_id},
    );
}

fn builtin_inst_1(name: []const u8, kind: anytype) ?u32 {
    if (std.mem.eql(u8, name, "sin")) return 13;
    if (std.mem.eql(u8, name, "fract")) return 10;
    if (std.mem.eql(u8, name, "cos")) return 14;
    if (std.mem.eql(u8, name, "exp")) return 27;
    if (std.mem.eql(u8, name, "log")) return 28;
    if (std.mem.eql(u8, name, "exp2")) return 29;
    if (std.mem.eql(u8, name, "log2")) return 30;
    if (std.mem.eql(u8, name, "sqrt")) return 31;
    if (std.mem.eql(u8, name, "inverseSqrt")) return 32;
    if (std.mem.eql(u8, name, "floor")) return 8;
    if (std.mem.eql(u8, name, "ceil")) return 9;
    if (std.mem.eql(u8, name, "round")) return 1;
    if (std.mem.eql(u8, name, "trunc")) return 3;
    if (std.mem.eql(u8, name, "tanh")) return 21;
    if (std.mem.eql(u8, name, "normalize")) return 69;
    if (std.mem.eql(u8, name, "degrees")) return 11;
    if (std.mem.eql(u8, name, "radians")) return 12;
    if (std.mem.eql(u8, name, "tan")) return 15;
    if (std.mem.eql(u8, name, "asin")) return 16;
    if (std.mem.eql(u8, name, "acos")) return 17;
    if (std.mem.eql(u8, name, "atan")) return 18;
    if (std.mem.eql(u8, name, "sinh")) return 19;
    if (std.mem.eql(u8, name, "cosh")) return 20;
    if (std.mem.eql(u8, name, "sign")) return switch (kind) {
        .float => 6,
        .signed => 7,
        else => null,
    };
    if (std.mem.eql(u8, name, "abs")) return switch (kind) {
        .float => 4,
        .signed => 5,
        else => null,
    };
    return null;
}

fn builtin_inst_2(name: []const u8, kind: anytype) ?u32 {
    if (std.mem.eql(u8, name, "pow")) return 26;
    if (std.mem.eql(u8, name, "step")) return 48;
    if (std.mem.eql(u8, name, "atan2")) return 25;
    if (std.mem.eql(u8, name, "ldexp")) return 71;
    if (std.mem.eql(u8, name, "min")) return switch (kind) {
        .float => 37,
        .unsigned => 38,
        .signed => 39,
        else => null,
    };
    if (std.mem.eql(u8, name, "max")) return switch (kind) {
        .float => 40,
        .unsigned => 41,
        .signed => 42,
        else => null,
    };
    return null;
}

fn builtin_inst_3(name: []const u8, kind: anytype) ?u32 {
    if (std.mem.eql(u8, name, "clamp")) return switch (kind) {
        .float => 43,
        .unsigned => 44,
        .signed => 45,
        else => null,
    };
    if (std.mem.eql(u8, name, "mix")) return 46;
    if (std.mem.eql(u8, name, "smoothstep")) return 49;
    if (std.mem.eql(u8, name, "fma")) return 50;
    return null;
}

fn emit_control_barrier(self: anytype, memory_semantics: u32) !void {
    const scope_id = try self.emitter.builder.const_u32(spirv.Scope.Workgroup);
    const semantics_id = try self.emitter.builder.const_u32(memory_semantics);
    try self.emitter.builder.append_function_inst(
        spirv.Opcode.ControlBarrier,
        &.{ scope_id, scope_id, semantics_id },
    );
}

const AtomicMemoryOperands = struct {
    scope_id: u32,
    semantics_id: u32,
};

fn emit_atomic_call(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len == 0) return error.InvalidIr;
    const ptr_expr = self.function.expr_args.items[call.args.start];
    const ptr_id = try self.emit_ref_expr(ptr_expr);
    const memory = try atomic_memory_operands(self, ptr_expr);

    if (std.mem.eql(u8, call.name, "atomicLoad")) {
        return try emit_result_inst(
            self,
            spirv.Opcode.AtomicLoad,
            try self.emitter.lower_type(result_ty),
            &.{ ptr_id, memory.scope_id, memory.semantics_id },
        );
    }

    if (call.args.len < 2) return error.InvalidIr;
    const value_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 1]);

    if (std.mem.eql(u8, call.name, "atomicStore")) {
        try self.emitter.builder.append_function_inst(
            spirv.Opcode.AtomicStore,
            &.{ ptr_id, memory.scope_id, memory.semantics_id, value_id },
        );
        return 0;
    }

    const opcode: u16 = if (std.mem.eql(u8, call.name, "atomicAdd"))
        spirv.Opcode.AtomicIAdd
    else if (std.mem.eql(u8, call.name, "atomicSub"))
        spirv.Opcode.AtomicISub
    else if (std.mem.eql(u8, call.name, "atomicMax")) switch (self.scalar_kind(result_ty)) {
        .signed => spirv.Opcode.AtomicSMax,
        .unsigned => spirv.Opcode.AtomicUMax,
        else => return error.UnsupportedConstruct,
    } else if (std.mem.eql(u8, call.name, "atomicMin")) switch (self.scalar_kind(result_ty)) {
        .signed => spirv.Opcode.AtomicSMin,
        .unsigned => spirv.Opcode.AtomicUMin,
        else => return error.UnsupportedConstruct,
    } else if (std.mem.eql(u8, call.name, "atomicAnd"))
        spirv.Opcode.AtomicAnd
    else if (std.mem.eql(u8, call.name, "atomicOr"))
        spirv.Opcode.AtomicOr
    else if (std.mem.eql(u8, call.name, "atomicXor"))
        spirv.Opcode.AtomicXor
    else if (std.mem.eql(u8, call.name, "atomicExchange"))
        spirv.Opcode.AtomicExchange
    else
        return error.UnsupportedConstruct;

    return try emit_result_inst(
        self,
        opcode,
        try self.emitter.lower_type(result_ty),
        &.{ ptr_id, memory.scope_id, memory.semantics_id, value_id },
    );
}

fn emit_texture_load(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 3) return error.InvalidIr;

    const texture_expr = self.function.expr_args.items[call.args.start];
    const coords_expr = self.function.expr_args.items[call.args.start + 1];
    const level_expr = self.function.expr_args.items[call.args.start + 2];

    switch (self.emitter.module.types.get(self.function.exprs.items[texture_expr].ty)) {
        .texture_2d => |sample_ty| switch (self.emitter.module.types.get(sample_ty)) {
            .scalar => |scalar| {
                if (scalar != .f32) return error.UnsupportedConstruct;
            },
            else => return error.UnsupportedConstruct,
        },
        else => return error.UnsupportedConstruct,
    }

    return try emit_result_inst(
        self,
        spirv.Opcode.ImageFetch,
        try self.emitter.lower_type(result_ty),
        &.{
            try self.emit_value_expr(texture_expr),
            try self.emit_value_expr(coords_expr),
            spirv.ImageOperandsMask.Lod,
            try self.emit_value_expr(level_expr),
        },
    );
}

fn emit_texture_store(self: anytype, call: anytype) !void {
    if (call.args.len != 3) return error.InvalidIr;

    const texture_expr = self.function.expr_args.items[call.args.start];
    switch (self.emitter.module.types.get(self.function.exprs.items[texture_expr].ty)) {
        .storage_texture_2d => |storage_tex| {
            if (storage_tex.format != .rgba8unorm or storage_tex.access == .read) {
                return error.UnsupportedConstruct;
            }
        },
        else => return error.UnsupportedConstruct,
    }

    try self.emitter.builder.append_function_inst(
        spirv.Opcode.ImageWrite,
        &.{
            try self.emit_value_expr(texture_expr),
            try self.emit_value_expr(self.function.expr_args.items[call.args.start + 1]),
            try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]),
        },
    );
}

fn emit_array_length(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 1) return error.InvalidIr;
    const ref_expr_id = self.function.expr_args.items[call.args.start];
    const ref_expr = self.function.exprs.items[ref_expr_id];

    const struct_ptr_id, const member_index = switch (ref_expr.data) {
        .global_ref => |global_index| blk: {
            if (!self.emitter.global_buffer_wrapped[global_index]) return error.UnsupportedConstruct;
            const global = self.emitter.module.globals.items[global_index];
            switch (self.emitter.module.types.get(global.ty)) {
                .array => |arr| {
                    if (arr.len != null) return error.UnsupportedConstruct;
                },
                else => return error.UnsupportedConstruct,
            }
            break :blk .{ self.emitter.global_ids[global_index], @as(u32, 0) };
        },
        .member => |member| blk: {
            const base_expr = self.function.exprs.items[member.base];
            const base_ref = switch (self.emitter.module.types.get(base_expr.ty)) {
                .ref => |ref_ty| ref_ty,
                else => return error.InvalidIr,
            };
            switch (self.emitter.module.types.get(base_ref.elem)) {
                .struct_ => {},
                else => return error.UnsupportedConstruct,
            }
            break :blk .{ try self.emit_ref_expr(member.base), member.field_index };
        },
        else => return error.UnsupportedConstruct,
    };

    return try emit_result_inst(
        self,
        spirv.Opcode.ArrayLength,
        try self.emitter.lower_type(result_ty),
        &.{ struct_ptr_id, member_index },
    );
}

fn emit_dot(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 2) return error.InvalidIr;

    const lhs_expr = self.function.expr_args.items[call.args.start];
    const rhs_expr = self.function.expr_args.items[call.args.start + 1];
    const lhs_ty = self.function.exprs.items[lhs_expr].ty;
    const rhs_ty = self.function.exprs.items[rhs_expr].ty;

    switch (self.emitter.module.types.get(lhs_ty)) {
        .vector => |lhs_vec| {
            const rhs_vec = switch (self.emitter.module.types.get(rhs_ty)) {
                .vector => |vec| vec,
                else => return error.UnsupportedConstruct,
            };
            if (lhs_vec.len != rhs_vec.len) return error.UnsupportedConstruct;
            if (lhs_vec.elem != rhs_vec.elem) return error.UnsupportedConstruct;
            switch (self.emitter.module.types.get(lhs_vec.elem)) {
                .scalar => |scalar| if (scalar != .f32 and scalar != .abstract_float) return error.UnsupportedConstruct,
                else => return error.UnsupportedConstruct,
            }
        },
        else => return error.UnsupportedConstruct,
    }

    return try emit_result_inst(
        self,
        spirv.Opcode.Dot,
        try self.emitter.lower_type(result_ty),
        &.{
            try self.emit_value_expr(lhs_expr),
            try self.emit_value_expr(rhs_expr),
        },
    );
}

fn atomic_memory_operands(self: anytype, ref_expr_id: ir.ExprId) !AtomicMemoryOperands {
    const storage_class = try self.ref_storage_class(ref_expr_id);
    const scope = switch (storage_class) {
        spirv.StorageClass.Workgroup => spirv.Scope.Workgroup,
        spirv.StorageClass.StorageBuffer => spirv.Scope.Device,
        else => return error.UnsupportedConstruct,
    };
    const semantics = switch (storage_class) {
        spirv.StorageClass.Workgroup => spirv.MemorySemantics.SequentiallyConsistent | spirv.MemorySemantics.WorkgroupMemory,
        spirv.StorageClass.StorageBuffer => spirv.MemorySemantics.SequentiallyConsistent | spirv.MemorySemantics.UniformMemory,
        else => return error.UnsupportedConstruct,
    };
    return .{
        .scope_id = try self.emitter.builder.const_u32(scope),
        .semantics_id = try self.emitter.builder.const_u32(semantics),
    };
}
