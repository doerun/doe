const std = @import("std");
const ir = @import("../ir/ir.zig");
const analysis = @import("../pipeline/analysis.zig");
const emit_msl = @import("../emit/msl/emit_msl.zig");
const reflection = @import("../pipeline/binding_reflection.zig");

pub const EntryPointBindings = struct {
    name: []const u8,
    bindings: []const reflection.BindingMeta,

    pub fn deinit(self: *EntryPointBindings, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        if (self.bindings.len > 0) allocator.free(self.bindings);
    }
};

pub fn deinitEntryPointBindings(allocator: std.mem.Allocator, entries: []const EntryPointBindings) void {
    for (entries) |entry| {
        var owned = entry;
        owned.deinit(allocator);
    }
    if (entries.len > 0) allocator.free(entries);
}

pub fn buildEntryPointBindings(allocator: std.mem.Allocator, module_ir: *const ir.Module) analysis.TranslateError![]const EntryPointBindings {
    var compute_count: usize = 0;
    for (module_ir.entry_points.items) |entry| if (entry.stage == .compute) {
        compute_count += 1;
    };
    if (compute_count == 0) return &.{};
    const entries = try allocator.alloc(EntryPointBindings, compute_count);
    var initialized: usize = 0;
    errdefer {
        for (entries[0..initialized]) |entry| {
            var owned = entry;
            owned.deinit(allocator);
        }
        allocator.free(entries);
    }
    for (module_ir.entry_points.items) |entry| {
        if (entry.stage != .compute) continue;
        const name = module_ir.functions.items[entry.function].name;
        var bindings: [reflection.MAX_BINDINGS]reflection.BindingMeta = undefined;
        const count = try reflection.extractEntryPointBindings(allocator, module_ir, name, &bindings);
        const owned_name = try allocator.dupe(u8, name);
        errdefer allocator.free(owned_name);
        const owned_bindings = if (count == 0) &.{} else try allocator.dupe(reflection.BindingMeta, bindings[0..count]);
        entries[initialized] = .{ .name = owned_name, .bindings = owned_bindings };
        initialized += 1;
    }
    return entries;
}

pub const TranslationInfo = struct {
    workgroup_size: [3]u32 = .{ 1, 1, 1 },
    needs_sizes_buf: bool = false,
    dispatch_preconditions: []const ir.DispatchPrecondition = &.{},
    texture_dispatch_preconditions: []const ir.TextureDispatchPrecondition = &.{},
    entry_point_bindings: []const EntryPointBindings = &.{},

    pub fn clone(self: *const TranslationInfo, allocator: std.mem.Allocator) error{OutOfMemory}!TranslationInfo {
        var result = TranslationInfo{ .workgroup_size = self.workgroup_size, .needs_sizes_buf = self.needs_sizes_buf };
        errdefer result.deinit(allocator);
        if (self.dispatch_preconditions.len > 0) result.dispatch_preconditions = try allocator.dupe(ir.DispatchPrecondition, self.dispatch_preconditions);
        if (self.texture_dispatch_preconditions.len > 0) result.texture_dispatch_preconditions = try allocator.dupe(ir.TextureDispatchPrecondition, self.texture_dispatch_preconditions);
        if (self.entry_point_bindings.len > 0) {
            const entries = try allocator.alloc(EntryPointBindings, self.entry_point_bindings.len);
            var initialized: usize = 0;
            errdefer {
                for (entries[0..initialized]) |entry| {
                    var owned = entry;
                    owned.deinit(allocator);
                }
                allocator.free(entries);
            }
            for (self.entry_point_bindings) |entry| {
                const name = try allocator.dupe(u8, entry.name);
                errdefer allocator.free(name);
                const bindings = if (entry.bindings.len == 0) &.{} else try allocator.dupe(reflection.BindingMeta, entry.bindings);
                entries[initialized] = .{ .name = name, .bindings = bindings };
                initialized += 1;
            }
            result.entry_point_bindings = entries;
        }
        return result;
    }

    pub fn deinit(self: *TranslationInfo, allocator: std.mem.Allocator) void {
        if (self.dispatch_preconditions.len > 0) allocator.free(self.dispatch_preconditions);
        if (self.texture_dispatch_preconditions.len > 0) allocator.free(self.texture_dispatch_preconditions);
        deinitEntryPointBindings(allocator, self.entry_point_bindings);
        self.* = .{};
    }
};

pub const TranslationResult = struct {
    len: usize,
    info: TranslationInfo,
};

pub const TimedTranslationResult = struct {
    len: usize,
    info: TranslationInfo,
    phase_timings_ns: analysis.CompilePhaseTimingsNs,
};

pub fn buildTranslationInfo(
    allocator: std.mem.Allocator,
    module_ir: *const ir.Module,
) analysis.TranslateError!TranslationInfo {
    const borrowed = TranslationInfo{
        .workgroup_size = compute_workgroup_size(module_ir),
        .needs_sizes_buf = emit_msl.moduleNeedsSizesParam(module_ir),
        .dispatch_preconditions = module_ir.dispatch_preconditions.items,
        .texture_dispatch_preconditions = module_ir.texture_dispatch_preconditions.items,
    };
    return borrowed.clone(allocator);
}

fn compute_workgroup_size(module_ir: *const ir.Module) [3]u32 {
    for (module_ir.entry_points.items) |entry| {
        if (entry.stage == .compute) return entry.workgroup_size;
    }
    return .{ 1, 1, 1 };
}

test "Vulkan entry point metadata keeps distinct resource sets" {
    const source =
        \\@group(0) @binding(0) var<storage, read> input: array<u32>;
        \\@group(0) @binding(1) var<storage, read_write> output: array<u32>;
        \\@compute @workgroup_size(1) fn read_only() { let value = input[0]; }
        \\@compute @workgroup_size(1) fn write_only() { output[0] = 7u; }
    ;
    var diagnostic = analysis.Diagnostic{};
    var analyzed = try analysis.analyze(.{
        .allocator = std.testing.allocator,
        .source = source,
        .robustness = analysis.default_translation_robustness_config(),
        .diagnostic = &diagnostic,
    });
    defer analyzed.module.deinit();
    const entries = try buildEntryPointBindings(std.testing.allocator, &analyzed.module);
    defer deinitEntryPointBindings(std.testing.allocator, entries);
    try std.testing.expectEqual(@as(usize, 2), entries.len);
    try std.testing.expectEqualStrings("read_only", entries[0].name);
    try std.testing.expectEqual(@as(u32, 0), entries[0].bindings[0].binding);
    try std.testing.expectEqualStrings("write_only", entries[1].name);
    try std.testing.expectEqual(@as(u32, 1), entries[1].bindings[0].binding);
}
