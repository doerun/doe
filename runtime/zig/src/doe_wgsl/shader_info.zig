const std = @import("std");
const mod = @import("mod.zig");

pub fn mslNeedsSizesBuffer(
    allocator: std.mem.Allocator,
    wgsl: []const u8,
) mod.TranslateError!bool {
    return mslNeedsSizesBufferWithConfig(
        allocator,
        wgsl,
        mod.default_translation_robustness_config(),
    );
}

pub fn mslNeedsSizesBufferWithConfig(
    allocator: std.mem.Allocator,
    wgsl: []const u8,
    config: mod.ir_transform_robustness.Config,
) mod.TranslateError!bool {
    var module = try mod.analyzeToIrWithConfig(allocator, wgsl, config);
    defer module.deinit();
    return mod.emit_msl.moduleNeedsSizesParam(&module);
}
