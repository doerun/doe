const std = @import("std");
const ir = @import("ir.zig");
const lean_proof = @import("../lean_proof.zig");
const mod = @import("mod.zig");

pub const TranslationInfo = struct {
    workgroup_size: [3]u32 = .{ 1, 1, 1 },
    needs_sizes_buf: bool = false,
    dispatch_preconditions: []const ir.DispatchPrecondition = &.{},

    pub fn deinit(self: *TranslationInfo, allocator: std.mem.Allocator) void {
        if (self.dispatch_preconditions.len > 0) allocator.free(self.dispatch_preconditions);
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
    };
}

fn compute_workgroup_size(module_ir: *const ir.Module) [3]u32 {
    for (module_ir.entry_points.items) |entry| {
        if (entry.stage == .compute) return entry.workgroup_size;
    }
    return .{ 1, 1, 1 };
}
