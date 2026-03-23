// emit_csl_layout.zig — Generates the CSL layout file for a classified kernel.
//
// The layout file defines the PE grid rectangle, assigns tile code to each PE,
// configures fabric routing (colors and switch positions), and exports symbols
// for host↔device data transfer via the memcpy framework.
//
// Each kernel pattern produces a different grid topology:
//   element_wise → 1-D row of PEs (width = PE count, height = 1)
//   reduction    → 1-D row with east→west reduce chain
//   tiled_matmul → 2-D grid with row/column broadcast for SUMMA

const std = @import("std");
const ir = @import("ir.zig");
const spec = @import("csl_spec.zig");
const classify = @import("emit_csl_classify.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
};

/// Emit the layout.csl section for an element-wise kernel.
/// Grid: width × 1 (one row of PEs, no inter-PE communication).
pub fn emitElementWiseLayout(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    entry: ir.EntryPoint,
    info: classify.ElementWiseInfo,
) EmitError!void {
    _ = info;
    const function = &module.functions.items[entry.function];

    // Header
    try write(buf, pos, "// Layout: element-wise kernel distributed across a 1-D PE row.\n");
    try write(buf, pos, "// Each PE processes a contiguous chunk of the input array.\n\n");

    // Params
    try write(buf, pos, "// Grid width is set at compile time via --params=width:<N>.\n");
    try write(buf, pos, "param width: i16;\n\n");

    // Memcpy import
    try write(buf, pos, "const memcpy = @import_module(\"<memcpy/get_params>\", .{\n");
    try write(buf, pos, "    .width = width,\n");
    try write(buf, pos, "    .height = 1,\n");
    try write(buf, pos, "});\n\n");

    // Layout block
    try write(buf, pos, "layout {\n");
    try write(buf, pos, "    @set_rectangle(width, 1);\n\n");

    // Assign tile code to each PE
    try write(buf, pos, "    for (@range(i16, width)) |pe_x| {\n");
    try write(buf, pos, "        @set_tile_code(pe_x, 0, \"");
    try write(buf, pos, spec.PE_PROGRAM_FILENAME);
    try write(buf, pos, "\", .{\n");
    try write(buf, pos, "            .memcpy_params = memcpy.get_params(pe_x),\n");
    try write(buf, pos, "            .pe_id = pe_x,\n");
    try write(buf, pos, "            .num_pes = width,\n");
    try write(buf, pos, "        });\n");
    try write(buf, pos, "    }\n\n");

    // Export storage buffer symbols for host memcpy
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage and space != .uniform) continue;
        try write(buf, pos, "    @export_name(\"");
        try write(buf, pos, global.name);
        try write(buf, pos, "\", [*]");
        try writeScalarType(buf, pos, module, global.ty);
        try write(buf, pos, ", true);\n");
    }

    // Export compute function
    try write(buf, pos, "    @export_name(\"compute\", fn()void);\n");
    _ = function;

    try write(buf, pos, "}\n");
}

/// Emit the layout.csl section for a reduction kernel.
/// Grid: width × 1 with fabric routing for east→west allreduce.
pub fn emitReductionLayout(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    entry: ir.EntryPoint,
    info: classify.ReductionInfo,
) EmitError!void {
    _ = entry;
    _ = info;

    try write(buf, pos, "// Layout: reduction kernel with east-west allreduce chain.\n\n");
    try write(buf, pos, "param width: i16;\n\n");

    try write(buf, pos, "const memcpy = @import_module(\"<memcpy/get_params>\", .{\n");
    try write(buf, pos, "    .width = width,\n");
    try write(buf, pos, "    .height = 1,\n");
    try write(buf, pos, "});\n\n");

    // Reduce color for partial-sum accumulation along the row.
    try write(buf, pos, "const reduce_color: color = @get_color(");
    try writeInt(buf, pos, spec.MEMCPY_RESERVED_COLORS);
    try write(buf, pos, ");\n\n");

    try write(buf, pos, "layout {\n");
    try write(buf, pos, "    @set_rectangle(width, 1);\n\n");

    try write(buf, pos, "    for (@range(i16, width)) |pe_x| {\n");
    try write(buf, pos, "        @set_tile_code(pe_x, 0, \"");
    try write(buf, pos, spec.PE_PROGRAM_FILENAME);
    try write(buf, pos, "\", .{\n");
    try write(buf, pos, "            .memcpy_params = memcpy.get_params(pe_x),\n");
    try write(buf, pos, "            .pe_id = pe_x,\n");
    try write(buf, pos, "            .num_pes = width,\n");
    try write(buf, pos, "            .reduce_color = reduce_color,\n");
    try write(buf, pos, "        });\n\n");

    // Route reduce color: RAMP → EAST for all PEs except last,
    // WEST → RAMP for all PEs except first.
    try write(buf, pos, "        if (pe_x == 0) {\n");
    try write(buf, pos, "            @set_color_config(pe_x, 0, reduce_color, .{\n");
    try write(buf, pos, "                .routes = .{ .rx = .{RAMP}, .tx = .{EAST} },\n");
    try write(buf, pos, "            });\n");
    try write(buf, pos, "        } else if (pe_x == width - 1) {\n");
    try write(buf, pos, "            @set_color_config(pe_x, 0, reduce_color, .{\n");
    try write(buf, pos, "                .routes = .{ .rx = .{WEST}, .tx = .{RAMP} },\n");
    try write(buf, pos, "            });\n");
    try write(buf, pos, "        } else {\n");
    try write(buf, pos, "            @set_color_config(pe_x, 0, reduce_color, .{\n");
    try write(buf, pos, "                .routes = .{ .rx = .{WEST, RAMP}, .tx = .{EAST} },\n");
    try write(buf, pos, "            });\n");
    try write(buf, pos, "        }\n");
    try write(buf, pos, "    }\n\n");

    // Exports
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage and space != .uniform) continue;
        try write(buf, pos, "    @export_name(\"");
        try write(buf, pos, global.name);
        try write(buf, pos, "\", [*]");
        try writeScalarType(buf, pos, module, global.ty);
        try write(buf, pos, ", true);\n");
    }
    try write(buf, pos, "    @export_name(\"compute\", fn()void);\n");
    try write(buf, pos, "}\n");
}

/// Emit the layout.csl section for a SUMMA tiled matmul.
/// Grid: P × P with row and column broadcast via collectives_2d.
pub fn emitMatmulLayout(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    entry: ir.EntryPoint,
    info: classify.MatmulInfo,
) EmitError!void {
    _ = entry;
    _ = info;

    try write(buf, pos, "// Layout: SUMMA tiled matmul on a P x P PE grid.\n\n");
    try write(buf, pos, "param P: u16;\n");
    try write(buf, pos, "param Mt: u16;\n");
    try write(buf, pos, "param Kt: u16;\n");
    try write(buf, pos, "param Nt: u16;\n\n");

    try write(buf, pos, "const memcpy = @import_module(\"<memcpy/get_params>\", .{\n");
    try write(buf, pos, "    .width = P,\n");
    try write(buf, pos, "    .height = P,\n");
    try write(buf, pos, "});\n\n");

    try write(buf, pos, "const c2d = @import_module(\"<collectives_2d/params>\");\n\n");

    try write(buf, pos, "layout {\n");
    try write(buf, pos, "    @set_rectangle(P, P);\n\n");

    try write(buf, pos, "    for (@range(u16, P)) |pe_y| {\n");
    try write(buf, pos, "        for (@range(u16, P)) |pe_x| {\n");
    try write(buf, pos, "            @set_tile_code(pe_x, pe_y, \"");
    try write(buf, pos, spec.PE_PROGRAM_FILENAME);
    try write(buf, pos, "\", .{\n");
    try write(buf, pos, "                .memcpy_params = memcpy.get_params(pe_x),\n");
    try write(buf, pos, "                .Mt = Mt,\n");
    try write(buf, pos, "                .Kt = Kt,\n");
    try write(buf, pos, "                .Nt = Nt,\n");
    try write(buf, pos, "                .P = P,\n");
    try write(buf, pos, "            });\n");
    try write(buf, pos, "        }\n");
    try write(buf, pos, "    }\n\n");

    // Exports
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        try write(buf, pos, "    @export_name(\"");
        try write(buf, pos, global.name);
        try write(buf, pos, "\", [*]f32, true);\n");
    }
    try write(buf, pos, "    @export_name(\"compute\", fn()void);\n");
    try write(buf, pos, "}\n");
}

// ---------------------------------------------------------------------------
// Write helpers
// ---------------------------------------------------------------------------

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}

fn writeInt(buf: []u8, pos: *usize, value: anytype) EmitError!void {
    var tmp: [20]u8 = undefined;
    const slice = std.fmt.bufPrint(&tmp, "{d}", .{value}) catch return error.OutputTooLarge;
    try write(buf, pos, slice);
}

fn writeScalarType(buf: []u8, pos: *usize, module: *const ir.Module, ty: ir.TypeId) EmitError!void {
    const resolved = module.types.get(ty);
    switch (resolved) {
        .scalar => |s| try write(buf, pos, spec.scalarTypeName(s)),
        .array => |arr| try writeScalarType(buf, pos, module, arr.elem),
        else => try write(buf, pos, "u32"),
    }
}
