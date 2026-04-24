// Mechanical TSIR-to-MSL skeleton emitter.

const std = @import("std");
const targets = @import("../targets/mod.zig");
const schema = @import("schema.zig");
const common = @import("emit_text_skeleton.zig");

const EMITTER_SOURCE = @embedFile("emit_msl.zig");
const COMMON_SOURCE = @embedFile("emit_text_skeleton.zig");
const SPEC = common.BackendTextSpec{
    .version_key = "doe.tsir.msl_skeleton.version",
    .body_comment = "// tsir mechanical skeleton: MSL kernel body is emitted by later lowering.",
};

pub const EmitError = common.EmitError;

pub fn emitterCodeDigest() [32]u8 {
    var h = std.crypto.hash.sha2.Sha256.init(.{});
    h.update(EMITTER_SOURCE);
    h.update(COMMON_SOURCE);
    var out: [32]u8 = undefined;
    h.final(&out);
    return out;
}

pub fn emit(
    allocator: std.mem.Allocator,
    realization: schema.Realization,
    function_index: usize,
    descriptor: targets.TargetDescriptor,
) EmitError![]const u8 {
    return common.emit(allocator, realization, function_index, descriptor, SPEC);
}

pub fn emitFunction(
    allocator: std.mem.Allocator,
    function: schema.RealizationFunction,
    descriptor: targets.TargetDescriptor,
) EmitError![]const u8 {
    return common.emitFunction(allocator, function, descriptor, SPEC);
}
