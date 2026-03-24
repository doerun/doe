// emit_csl_dequant.zig — CSL PE program for Q4K dequantization.
//
// Maps Doppler's dequant_shared.wgsl pattern to CSL. Q4K block format:
//   256 weights per super-block (QK_K)
//   8 sub-blocks of 32 elements each
//   6-bit scale/min per sub-block, nibble-packed quantized values
//
// On CSL each PE dequantizes its assigned super-blocks locally.
// No inter-PE communication needed. Buffer names from IR.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.DequantInfo,
) EmitError!void {
    const qnt = module.globals.items[info.quant_global].name;
    const out = module.globals.items[info.output_global].name;

    try W.write(buf, pos, "// PE program: Q4K dequantization (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Each PE dequantizes its assigned super-blocks locally.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param num_blocks: i16;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n\n");

    // Q4K block layout constants
    try W.write(buf, pos, "const QK_K: u32 = 256;\n");
    try W.write(buf, pos, "const Q4K_BLOCK_BYTES: u32 = 144;\n\n");

    // Buffers
    try emitBuf(buf, pos, qnt, "[num_blocks * Q4K_BLOCK_BYTES]u8");
    try emitBuf(buf, pos, out, "[num_blocks * QK_K]f32");
    try W.write(buf, pos, "\n");
    try emitPtrTyped(buf, pos, qnt, "u8");
    try emitPtrTyped(buf, pos, out, "f32");
    try W.write(buf, pos, "\n");

    // Dequantization function
    try W.write(buf, pos, "fn dequant_block(block_idx: u32) void {\n");
    try W.write(buf, pos, "    const base = block_idx * Q4K_BLOCK_BYTES;\n");
    try W.write(buf, pos, "    const out_base = block_idx * QK_K;\n\n");

    // Unpack super-block scale factors
    try W.write(buf, pos, "    const d_bits = @as(u16, ");
    try W.write(buf, pos, qnt);
    try W.write(buf, pos, "[base]) | (@as(u16, ");
    try W.write(buf, pos, qnt);
    try W.write(buf, pos, "[base + 1]) << 8);\n");
    try W.write(buf, pos, "    const dmin_bits = @as(u16, ");
    try W.write(buf, pos, qnt);
    try W.write(buf, pos, "[base + 2]) | (@as(u16, ");
    try W.write(buf, pos, qnt);
    try W.write(buf, pos, "[base + 3]) << 8);\n");
    try W.write(buf, pos, "    const d = @bitcast(f16, d_bits);\n");
    try W.write(buf, pos, "    const dmin = @bitcast(f16, dmin_bits);\n\n");

    // Per-sub-block scales and mins
    try W.write(buf, pos, "    var scales: [8]f32 = undefined;\n");
    try W.write(buf, pos, "    var mins: [8]f32 = undefined;\n");
    try W.write(buf, pos, "    for (@range(u32, 8)) |sb| {\n");
    try W.write(buf, pos, "        const sc_byte = ");
    try W.write(buf, pos, qnt);
    try W.write(buf, pos, "[base + 4 + sb];\n");
    try W.write(buf, pos, "        scales[sb] = @as(f32, d) * @as(f32, sc_byte & 0x3F);\n");
    try W.write(buf, pos, "        mins[sb] = @as(f32, dmin) * @as(f32, sc_byte >> 6);\n");
    try W.write(buf, pos, "    }\n\n");

    // Dequantize nibble-packed values
    try W.write(buf, pos, "    const data_offset = base + 16;\n");
    try W.write(buf, pos, "    for (@range(u32, 128)) |i| {\n");
    try W.write(buf, pos, "        const byte = ");
    try W.write(buf, pos, qnt);
    try W.write(buf, pos, "[data_offset + i];\n");
    try W.write(buf, pos, "        const lo = byte & 0x0F;\n");
    try W.write(buf, pos, "        const hi = byte >> 4;\n");
    try W.write(buf, pos, "        const elem0 = i * 2;\n");
    try W.write(buf, pos, "        const elem1 = elem0 + 1;\n");
    try W.write(buf, pos, "        const sb0 = elem0 / 32;\n");
    try W.write(buf, pos, "        const sb1 = elem1 / 32;\n");
    try W.write(buf, pos, "        ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[out_base + elem0] = scales[sb0] * @as(f32, lo) - mins[sb0];\n");
    try W.write(buf, pos, "        ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[out_base + elem1] = scales[sb1] * @as(f32, hi) - mins[sb1];\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    for (@range(i16, num_blocks)) |b| {\n");
    try W.write(buf, pos, "        dequant_block(@as(u32, b));\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    try emitExport(buf, pos, qnt);
    try emitExport(buf, pos, out);
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
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

fn emitPtrTyped(buf: []u8, pos: *usize, name: []const u8, elem: []const u8) EmitError!void {
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
