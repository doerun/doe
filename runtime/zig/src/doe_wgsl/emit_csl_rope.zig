// emit_csl_rope.zig — CSL PE program for rotary position embeddings.
//
// Maps Doppler's rope.wgsl pattern to CSL. RoPE applies 2D rotations to
// pairs of dimensions using precomputed cos/sin frequency tables.
// Each PE holds a chunk of the Q/K vector and applies rotations locally.
//
// Supports both interleaved (Qwen mRoPE) and rotate-half layouts.
// Buffer names are resolved from the IR module.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.RoPEInfo,
) EmitError!void {
    const inp = module.globals.items[info.input_global].name;
    const cos = module.globals.items[info.cos_global].name;
    const sin = module.globals.items[info.sin_global].name;

    try W.write(buf, pos, "// PE program: rotary position embeddings (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Each PE applies RoPE rotations to its local Q/K chunk.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param head_dim: i16;\n");
    try W.write(buf, pos, "param num_pairs: i16;\n");
    try W.write(buf, pos, "param interleaved: bool = true;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    // Buffers — in-place modification of input
    try emitBuf(buf, pos, inp, "[head_dim]f32");
    try emitBuf(buf, pos, cos, "[num_pairs]f32");
    try emitBuf(buf, pos, sin, "[num_pairs]f32");
    try W.write(buf, pos, "\n");
    try emitPtr(buf, pos, inp, "f32");
    try emitPtr(buf, pos, cos, "f32");
    try emitPtr(buf, pos, sin, "f32");
    try W.write(buf, pos, "\n");

    // RoPE rotation: for each pair (x0, x1), apply rotation
    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    for (@range(i16, num_pairs)) |p| {\n");
    try W.write(buf, pos, "        const cos_val = ");
    try W.write(buf, pos, cos);
    try W.write(buf, pos, "[@as(u32, p)];\n");
    try W.write(buf, pos, "        const sin_val = ");
    try W.write(buf, pos, sin);
    try W.write(buf, pos, "[@as(u32, p)];\n\n");

    try W.write(buf, pos, "        if (interleaved) {\n");
    try W.write(buf, pos, "            const i0 = @as(u32, p) * 2;\n");
    try W.write(buf, pos, "            const i1 = i0 + 1;\n");
    try emitRoPEPair(buf, pos, inp);
    try W.write(buf, pos, "        } else {\n");
    try W.write(buf, pos, "            const i0 = @as(u32, p);\n");
    try W.write(buf, pos, "            const i1 = i0 + @as(u32, num_pairs);\n");
    try emitRoPEPair(buf, pos, inp);
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    try emitExport(buf, pos, inp);
    try emitExport(buf, pos, cos);
    try emitExport(buf, pos, sin);
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
}

fn emitRoPEPair(buf: []u8, pos: *usize, inp: []const u8) EmitError!void {
    try W.write(buf, pos, "            const x0 = ");
    try W.write(buf, pos, inp);
    try W.write(buf, pos, "[i0];\n");
    try W.write(buf, pos, "            const x1 = ");
    try W.write(buf, pos, inp);
    try W.write(buf, pos, "[i1];\n");
    try W.write(buf, pos, "            ");
    try W.write(buf, pos, inp);
    try W.write(buf, pos, "[i0] = x0 * cos_val - x1 * sin_val;\n");
    try W.write(buf, pos, "            ");
    try W.write(buf, pos, inp);
    try W.write(buf, pos, "[i1] = x0 * sin_val + x1 * cos_val;\n");
}

fn emitBuf(buf: []u8, pos: *usize, name: []const u8, ty: []const u8) EmitError!void {
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, name);
    try W.write(buf, pos, ": ");
    try W.write(buf, pos, ty);
    try W.write(buf, pos, " = @zeros(");
    try W.write(buf, pos, ty);
    try W.write(buf, pos, ");\n");
}

fn emitPtr(buf: []u8, pos: *usize, name: []const u8, elem: []const u8) EmitError!void {
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "_ptr: [*]");
    try W.write(buf, pos, elem);
    try W.write(buf, pos, " = &");
    try W.write(buf, pos, name);
    try W.write(buf, pos, ";\n");
}

fn emitExport(buf: []u8, pos: *usize, name: []const u8) EmitError!void {
    try W.write(buf, pos, "    @export_symbol(");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "_ptr, \"");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "\");\n");
}
