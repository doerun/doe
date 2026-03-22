const std = @import("std");
const ir = @import("ir.zig");
const lean_proof = @import("../lean_proof.zig");
const mod = @import("mod.zig");

pub const TranslationInfo = struct {
    workgroup_size: [3]u32 = .{ 1, 1, 1 },
    needs_sizes_buf: bool = false,
    dispatch_preconditions: []const ir.DispatchPrecondition = &.{},
    texture_dispatch_preconditions: []const ir.TextureDispatchPrecondition = &.{},

    pub fn deinit(self: *TranslationInfo, allocator: std.mem.Allocator) void {
        if (self.dispatch_preconditions.len > 0) allocator.free(self.dispatch_preconditions);
        if (self.texture_dispatch_preconditions.len > 0) allocator.free(self.texture_dispatch_preconditions);
        self.* = .{};
    }
};

pub const TranslationResult = struct {
    len: usize,
    info: TranslationInfo,
};

pub fn compute_runtime_robustness_config() mod.ir_transform_robustness.Config {
    return .{
        .elide_proven_bounds = lean_proof.bounds_elimination_available,
    };
}

pub fn translateToMslForComputeRuntime(
    allocator: std.mem.Allocator,
    wgsl: []const u8,
    out: []u8,
    overrides: ?[*]const ir.OverrideEntry,
    override_count: usize,
) mod.TranslateError!TranslationResult {
    var module_ir = try mod.analyzeToIrWithConfig(allocator, wgsl, compute_runtime_robustness_config());
    defer module_ir.deinit();

    if (overrides != null and override_count > 0) {
        mod.applyOverrides(&module_ir, overrides.?[0..override_count]);
    }

    const len = mod.emit_msl.emit(&module_ir, out) catch |err| return switch (err) {
        error.OutputTooLarge => mod.TranslateError.OutputTooLarge,
        error.InvalidIr => mod.TranslateError.InvalidIr,
    };
    return .{
        .len = len,
        .info = try build_translation_info(allocator, &module_ir),
    };
}

pub fn translateToSpirvForComputeRuntime(
    allocator: std.mem.Allocator,
    wgsl: []const u8,
    out: []u8,
) mod.TranslateError!TranslationResult {
    var module_ir = try mod.analyzeToIrWithConfig(allocator, wgsl, compute_runtime_robustness_config());
    defer module_ir.deinit();

    const len = mod.emit_spirv.emit(&module_ir, out) catch |err| return switch (err) {
        error.OutputTooLarge => mod.TranslateError.OutputTooLarge,
        error.UnsupportedConstruct => mod.TranslateError.UnsupportedConstruct,
        error.InvalidIr => mod.TranslateError.InvalidIr,
        error.OutOfMemory => mod.TranslateError.OutOfMemory,
    };
    return .{
        .len = len,
        .info = try build_translation_info(allocator, &module_ir),
    };
}

/// Vertex input attribute extracted from the IR for pipeline reflection.
pub const VertexInputAttr = struct {
    location: u32,
    builtin: ir.Builtin,
};

/// Inter-stage I/O variable extracted from the IR for pipeline reflection.
pub const InterStageVar = struct {
    location: u32,
    interpolation: ?ir.Interpolation,
    builtin: ir.Builtin,
};

/// Result of translating a WGSL module containing vertex and/or fragment entry
/// points into per-stage SPIR-V binaries. Caller owns all heap allocations and
/// must call deinit to release them.
pub const GraphicsTranslationResult = struct {
    vertex_spirv: ?[]const u32 = null,
    fragment_spirv: ?[]const u32 = null,
    vertex_input_attrs: []const VertexInputAttr = &.{},
    inter_stage_vars: []const InterStageVar = &.{},
    has_vertex: bool = false,
    has_fragment: bool = false,

    pub fn deinit(self: *GraphicsTranslationResult, allocator: std.mem.Allocator) void {
        if (self.vertex_spirv) |s| allocator.free(s);
        if (self.fragment_spirv) |s| allocator.free(s);
        if (self.vertex_input_attrs.len > 0) allocator.free(self.vertex_input_attrs);
        if (self.inter_stage_vars.len > 0) allocator.free(self.inter_stage_vars);
        self.* = .{};
    }
};

/// Graphics shaders use the same robustness config as compute — Lean proof
/// elimination applies to any array bounds regardless of pipeline stage.
fn graphics_runtime_robustness_config() mod.ir_transform_robustness.Config {
    return .{
        .elide_proven_bounds = lean_proof.bounds_elimination_available,
    };
}

/// Translate WGSL source containing vertex and/or fragment entry points into
/// separate per-stage SPIR-V binaries. Returns heap-allocated u32 word slices
/// for each stage found, plus extracted vertex input and inter-stage interface
/// metadata for pipeline reflection.
pub fn translateToSpirvForGraphicsRuntime(
    allocator: std.mem.Allocator,
    wgsl: []const u8,
) mod.TranslateError!GraphicsTranslationResult {
    var module_ir = try mod.analyzeToIrWithConfig(allocator, wgsl, graphics_runtime_robustness_config());
    defer module_ir.deinit();

    var result = GraphicsTranslationResult{};
    errdefer result.deinit(allocator);

    for (module_ir.entry_points.items) |entry| {
        switch (entry.stage) {
            .vertex => {
                result.has_vertex = true;
                result.vertex_spirv = try emit_stage_spirv_words(allocator, &module_ir, .vertex);
            },
            .fragment => {
                result.has_fragment = true;
                result.fragment_spirv = try emit_stage_spirv_words(allocator, &module_ir, .fragment);
            },
            .compute => {},
        }
    }

    result.vertex_input_attrs = try extract_vertex_inputs(allocator, &module_ir);
    result.inter_stage_vars = try extract_inter_stage_vars(allocator, &module_ir);

    return result;
}

/// Emit SPIR-V for a single stage and convert the byte output to heap-allocated u32 words.
fn emit_stage_spirv_words(
    allocator: std.mem.Allocator,
    module_ir: *const ir.Module,
    stage: ir.ShaderStage,
) mod.TranslateError![]const u32 {
    var spirv_buf = allocator.alloc(u8, mod.MAX_SPIRV_OUTPUT) catch return mod.TranslateError.OutOfMemory;
    defer allocator.free(spirv_buf);

    const len = mod.emit_spirv.emitForStage(module_ir, stage, spirv_buf) catch |err| return switch (err) {
        error.OutputTooLarge => mod.TranslateError.OutputTooLarge,
        error.UnsupportedConstruct => mod.TranslateError.UnsupportedConstruct,
        error.InvalidIr => mod.TranslateError.InvalidIr,
        error.OutOfMemory => mod.TranslateError.OutOfMemory,
    };

    if (len == 0 or (len % 4) != 0) return mod.TranslateError.InvalidIr;

    const word_count = len / 4;
    const words = allocator.alloc(u32, word_count) catch return mod.TranslateError.OutOfMemory;
    for (words, 0..) |*w, i| {
        const offset = i * 4;
        const chunk: *const [4]u8 = @ptrCast(spirv_buf[offset .. offset + 4].ptr);
        w.* = std.mem.readInt(u32, chunk, .little);
    }
    return words;
}

const MAX_VERTEX_INPUT_ATTRS: usize = 32;
const MAX_INTER_STAGE_VARS: usize = 32;

/// Extract vertex input attributes (location-decorated parameters) from all
/// vertex entry points in the module.
fn extract_vertex_inputs(
    allocator: std.mem.Allocator,
    module_ir: *const ir.Module,
) mod.TranslateError![]const VertexInputAttr {
    var attrs_buf: [MAX_VERTEX_INPUT_ATTRS]VertexInputAttr = undefined;
    var count: usize = 0;

    for (module_ir.entry_points.items) |entry| {
        if (entry.stage != .vertex) continue;
        const function = &module_ir.functions.items[entry.function];
        for (function.params.items) |param| {
            // Struct-typed params: each field is a separate vertex input.
            switch (module_ir.types.get(param.ty)) {
                .struct_ => |struct_id| {
                    const struct_def = module_ir.structs.items[struct_id];
                    for (struct_def.fields.items) |field| {
                        if (count >= MAX_VERTEX_INPUT_ATTRS) break;
                        const io = field.io orelse continue;
                        attrs_buf[count] = .{
                            .location = io.location orelse 0,
                            .builtin = io.builtin,
                        };
                        count += 1;
                    }
                },
                else => {
                    if (count >= MAX_VERTEX_INPUT_ATTRS) break;
                    const io = param.io orelse continue;
                    attrs_buf[count] = .{
                        .location = io.location orelse 0,
                        .builtin = io.builtin,
                    };
                    count += 1;
                },
            }
        }
    }

    if (count == 0) return &.{};
    return allocator.dupe(VertexInputAttr, attrs_buf[0..count]) catch return mod.TranslateError.OutOfMemory;
}

/// Extract inter-stage interface variables from vertex output / fragment input.
/// These are the location-decorated fields of the vertex entry point return type.
fn extract_inter_stage_vars(
    allocator: std.mem.Allocator,
    module_ir: *const ir.Module,
) mod.TranslateError![]const InterStageVar {
    var vars_buf: [MAX_INTER_STAGE_VARS]InterStageVar = undefined;
    var count: usize = 0;

    for (module_ir.entry_points.items) |entry| {
        if (entry.stage != .vertex) continue;
        const function = &module_ir.functions.items[entry.function];
        switch (module_ir.types.get(function.return_type)) {
            .struct_ => |struct_id| {
                const struct_def = module_ir.structs.items[struct_id];
                for (struct_def.fields.items) |field| {
                    if (count >= MAX_INTER_STAGE_VARS) break;
                    const io = field.io orelse continue;
                    // Skip builtins like @builtin(position) — they are not user inter-stage vars.
                    if (io.builtin != .none and io.location == null) continue;
                    vars_buf[count] = .{
                        .location = io.location orelse 0,
                        .interpolation = io.interpolation,
                        .builtin = io.builtin,
                    };
                    count += 1;
                }
            },
            else => {
                // Non-struct return with IO attr (e.g. @location(0) vec4f).
                if (function.return_io) |io| {
                    if (count < MAX_INTER_STAGE_VARS and (io.builtin == .none or io.location != null)) {
                        vars_buf[count] = .{
                            .location = io.location orelse 0,
                            .interpolation = io.interpolation,
                            .builtin = io.builtin,
                        };
                        count += 1;
                    }
                }
            },
        }
    }

    if (count == 0) return &.{};
    return allocator.dupe(InterStageVar, vars_buf[0..count]) catch return mod.TranslateError.OutOfMemory;
}

fn build_translation_info(
    allocator: std.mem.Allocator,
    module_ir: *const ir.Module,
) mod.TranslateError!TranslationInfo {
    return .{
        .workgroup_size = compute_workgroup_size(module_ir),
        .needs_sizes_buf = mod.emit_msl.moduleNeedsSizesParam(module_ir),
        .dispatch_preconditions = if (module_ir.dispatch_preconditions.items.len == 0)
            &.{}
        else
            allocator.dupe(ir.DispatchPrecondition, module_ir.dispatch_preconditions.items) catch return mod.TranslateError.OutOfMemory,
        .texture_dispatch_preconditions = if (module_ir.texture_dispatch_preconditions.items.len == 0)
            &.{}
        else
            allocator.dupe(ir.TextureDispatchPrecondition, module_ir.texture_dispatch_preconditions.items) catch return mod.TranslateError.OutOfMemory,
    };
}

fn compute_workgroup_size(module_ir: *const ir.Module) [3]u32 {
    for (module_ir.entry_points.items) |entry| {
        if (entry.stage == .compute) return entry.workgroup_size;
    }
    return .{ 1, 1, 1 };
}
