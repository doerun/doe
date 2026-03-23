// emit_csl_core.zig — Core CSL emitter: classifies the kernel and dispatches
// to the appropriate template emitter.
//
// Output format: a single buffer containing two sections separated by
// `//--- <filename> ---` markers. The host or build tool splits on these
// markers to produce the layout.csl and pe_program.csl files that `cslc`
// expects.
//
// Pipeline:
//   ir.Module → classify → layout emitter + PE program emitter → buffer

const std = @import("std");
const ir = @import("ir.zig");
const spec = @import("csl_spec.zig");
const classify = @import("emit_csl_classify.zig");
const layout = @import("emit_csl_layout.zig");
const elementwise = @import("emit_csl_elementwise.zig");
const reduction = @import("emit_csl_reduction.zig");
const matmul = @import("emit_csl_matmul.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
    UnsupportedBuiltin,
    UnsupportedConstruct,
    UnsupportedPattern,
};

pub const MAX_OUTPUT: usize = 512 * 1024;

pub fn emit(module: *const ir.Module, out: []u8) EmitError!usize {
    var pos: usize = 0;

    // CSL only supports compute shaders.
    if (module.entry_points.items.len == 0) {
        return error.InvalidIr;
    }

    // Process the first compute entry point (CSL programs have one kernel).
    const entry = module.entry_points.items[0];
    if (entry.stage != .compute) {
        return error.UnsupportedConstruct;
    }

    // Classify the kernel pattern.
    const pattern = classify.classify(module, entry);

    // Emit layout section.
    try writeSection(out, &pos, spec.LAYOUT_FILENAME);
    switch (pattern) {
        .element_wise => |info| try layout.emitElementWiseLayout(out, &pos, module, entry, info),
        .reduction => |info| try layout.emitReductionLayout(out, &pos, module, entry, info),
        .tiled_matmul => |info| try layout.emitMatmulLayout(out, &pos, module, entry, info),
        .unsupported => return error.UnsupportedPattern,
    }

    // Emit PE program section.
    try writeSection(out, &pos, spec.PE_PROGRAM_FILENAME);
    switch (pattern) {
        .element_wise => |info| try elementwise.emit(out, &pos, module, entry, info),
        .reduction => |info| try reduction.emit(out, &pos, module, entry, info),
        .tiled_matmul => |info| try matmul.emit(out, &pos, module, entry, info),
        .unsupported => return error.UnsupportedPattern,
    }

    return pos;
}

fn writeSection(buf: []u8, pos: *usize, filename: []const u8) EmitError!void {
    try write(buf, pos, spec.SECTION_SEPARATOR);
    try write(buf, pos, filename);
    try write(buf, pos, spec.SECTION_SEPARATOR_END);
}

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}
