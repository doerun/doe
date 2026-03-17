const std = @import("std");
const ir = @import("ir.zig");
const spirv = @import("spirv_builder.zig");

const TextureOpcode = struct {
    const SampledImage: u16 = 86;
    const ImageSampleImplicitLod: u16 = 87;
    const ImageSampleExplicitLod: u16 = 88;
    const ImageSampleDrefImplicitLod: u16 = 90;
    const ImageSampleDrefExplicitLod: u16 = 91;
    const ImageGather: u16 = 96;
    const ImageDrefGather: u16 = 97;
    const ImageQuerySizeLod: u16 = 103;
    const ImageQuerySize: u16 = 104;
};

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

fn emit_sampled_image(self: anytype, call: anytype, texture_arg: u32, sampler_arg: u32) !struct { id: u32, texture_expr: ir.ExprId } {
    const texture_expr = self.function.expr_args.items[call.args.start + texture_arg];
    const sampler_expr = self.function.expr_args.items[call.args.start + sampler_arg];
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
    return .{ .id = sampled_image_id, .texture_expr = texture_expr };
}

pub fn emit_texture_sample(self: anytype, call: anytype, result_ty: ir.TypeId, explicit_lod: bool) !u32 {
    const expected_arg_count: u32 = if (explicit_lod) 4 else 3;
    if (call.args.len != expected_arg_count) return error.InvalidIr;

    const si = try emit_sampled_image(self, call, 0, 1);
    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]);
    if (!explicit_lod) {
        return try emit_result_inst(
            self,
            TextureOpcode.ImageSampleImplicitLod,
            try self.emitter.lower_type(result_ty),
            &.{ si.id, coords_id },
        );
    }

    return try emit_result_inst(
        self,
        TextureOpcode.ImageSampleExplicitLod,
        try self.emitter.lower_type(result_ty),
        &.{
            si.id,
            coords_id,
            spirv.ImageOperandsMask.Lod,
            try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]),
        },
    );
}

pub fn emit_texture_sample_compare(self: anytype, call: anytype, result_ty: ir.TypeId, explicit_lod: bool) !u32 {
    if (call.args.len != 4) return error.InvalidIr;

    const si = try emit_sampled_image(self, call, 0, 1);
    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]);
    const dref_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]);

    if (!explicit_lod) {
        return try emit_result_inst(
            self,
            TextureOpcode.ImageSampleDrefImplicitLod,
            try self.emitter.lower_type(result_ty),
            &.{ si.id, coords_id, dref_id },
        );
    }

    const lod_zero = try self.emitter.builder.const_f32_bits(@as(u32, @bitCast(@as(f32, 0.0))));
    return try emit_result_inst(
        self,
        TextureOpcode.ImageSampleDrefExplicitLod,
        try self.emitter.lower_type(result_ty),
        &.{ si.id, coords_id, dref_id, spirv.ImageOperandsMask.Lod, lod_zero },
    );
}

pub fn emit_texture_gather(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 4) return error.InvalidIr;

    const component_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start]);
    const si = try emit_sampled_image(self, call, 1, 2);
    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]);
    return try emit_result_inst(
        self,
        TextureOpcode.ImageGather,
        try self.emitter.lower_type(result_ty),
        &.{ si.id, coords_id, component_id },
    );
}

pub fn emit_texture_gather_compare(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 4) return error.InvalidIr;

    const si = try emit_sampled_image(self, call, 0, 1);
    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]);
    const dref_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]);
    return try emit_result_inst(
        self,
        TextureOpcode.ImageDrefGather,
        try self.emitter.lower_type(result_ty),
        &.{ si.id, coords_id, dref_id },
    );
}

pub fn emit_texture_sample_grad(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 5) return error.InvalidIr;

    const si = try emit_sampled_image(self, call, 0, 1);
    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]);
    const ddx_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]);
    const ddy_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 4]);
    return try emit_result_inst(
        self,
        TextureOpcode.ImageSampleExplicitLod,
        try self.emitter.lower_type(result_ty),
        &.{ si.id, coords_id, spirv.ImageOperandsMask.Grad, ddx_id, ddy_id },
    );
}

pub fn emit_texture_sample_offset(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 4) return error.InvalidIr;

    const si = try emit_sampled_image(self, call, 0, 1);
    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]);
    const offset_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]);
    return try emit_result_inst(
        self,
        TextureOpcode.ImageSampleImplicitLod,
        try self.emitter.lower_type(result_ty),
        &.{ si.id, coords_id, spirv.ImageOperandsMask.ConstOffset, offset_id },
    );
}

pub fn emit_texture_sample_level_offset(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
    if (call.args.len != 5) return error.InvalidIr;

    const si = try emit_sampled_image(self, call, 0, 1);
    const coords_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]);
    const level_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 3]);
    const offset_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 4]);
    return try emit_result_inst(
        self,
        TextureOpcode.ImageSampleExplicitLod,
        try self.emitter.lower_type(result_ty),
        &.{
            si.id,
            coords_id,
            spirv.ImageOperandsMask.Lod | spirv.ImageOperandsMask.ConstOffset,
            level_id,
            offset_id,
        },
    );
}

pub fn emit_texture_dimensions(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
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

pub fn emit_texture_load(self: anytype, call: anytype, result_ty: ir.TypeId) !u32 {
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

pub fn emit_texture_store(self: anytype, call: anytype) !void {
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
