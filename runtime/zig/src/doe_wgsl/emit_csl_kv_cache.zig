// emit_csl_kv_cache.zig — CSL PE programs for KV cache read/write.
//
// KV write: appends projected K/V vectors to the cache at the current
// decode position. Each PE holds a chunk of the head dimension.
//
// KV read: reads a slice of cached K/V for a range of positions.
// Each PE outputs its local chunk. No fabric needed for either.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const spec = @import("csl_spec.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

pub fn emitWrite(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.KvWriteInfo,
) EmitError!void {
    const kp = module.globals.items[info.key_proj_global].name;
    const vp = module.globals.items[info.val_proj_global].name;
    const kc = module.globals.items[info.key_cache_global].name;
    const vc = module.globals.items[info.val_cache_global].name;

    try W.write(buf, pos, "// PE program: KV cache write (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Appends projected K/V to cache at current position.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param head_dim: i16;\n");
    try W.write(buf, pos, "param max_seq_len: i16;\n");
    try W.write(buf, pos, "\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n\n");

    try emitStoragePtrs(buf, pos, module);
    try emitDecodePositionState(buf, pos);

    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    const base = decode_position[0] * @as(u32, head_dim);\n");
    try W.write(buf, pos, "    for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "        const idx = base + @as(u32, d);\n");
    try W.write(buf, pos, "        ");
    try W.write(buf, pos, kc);
    try W.write(buf, pos, "[idx] = ");
    try W.write(buf, pos, kp);
    try W.write(buf, pos, "[@as(u32, d)];\n");
    try W.write(buf, pos, "        ");
    try W.write(buf, pos, vc);
    try W.write(buf, pos, "[idx] = ");
    try W.write(buf, pos, vp);
    try W.write(buf, pos, "[@as(u32, d)];\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try emitComptime(buf, pos, module, true);
}

pub fn emitRead(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.KvReadInfo,
) EmitError!void {
    const kc = module.globals.items[info.key_cache_global].name;
    const vc = module.globals.items[info.val_cache_global].name;
    const ko = module.globals.items[info.key_out_global].name;
    const vo = module.globals.items[info.val_out_global].name;

    try W.write(buf, pos, "// PE program: KV cache read (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Reads a slice of cached K/V for the requested position range.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param head_dim: i16;\n");
    try W.write(buf, pos, "param read_start: i16 = 0;\n");
    try W.write(buf, pos, "param read_len: i16;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n\n");

    try emitStoragePtrs(buf, pos, module);

    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    for (@range(i16, read_len)) |i| {\n");
    try W.write(buf, pos, "        const src_base = @as(u32, read_start + i) * @as(u32, head_dim);\n");
    try W.write(buf, pos, "        const dst_base = @as(u32, i) * @as(u32, head_dim);\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            ");
    try W.write(buf, pos, ko);
    try W.write(buf, pos, "[dst_base + @as(u32, d)] = ");
    try W.write(buf, pos, kc);
    try W.write(buf, pos, "[src_base + @as(u32, d)];\n");
    try W.write(buf, pos, "            ");
    try W.write(buf, pos, vo);
    try W.write(buf, pos, "[dst_base + @as(u32, d)] = ");
    try W.write(buf, pos, vc);
    try W.write(buf, pos, "[src_base + @as(u32, d)];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try emitComptime(buf, pos, module, false);
}

fn emitStoragePtrs(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        try W.write(buf, pos, "var ");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, ": [*]");
        try writeScalarType(buf, pos, module, global.ty);
        try W.write(buf, pos, " = undefined;\n");
        try W.write(buf, pos, "var ");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, "_ptr: [*]");
        try writeScalarType(buf, pos, module, global.ty);
        try W.write(buf, pos, " = &");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, ";\n");
    }
    try W.write(buf, pos, "\n");
}

fn emitDecodePositionState(buf: []u8, pos: *usize) EmitError!void {
    try W.write(buf, pos, "var decode_position: [1]u32 = @zeros([1]u32);\n");
    try W.write(buf, pos, "var decode_position_ptr: [*]u32 = &decode_position;\n\n");
}

fn emitComptime(buf: []u8, pos: *usize, module: *const ir.Module, include_position: bool) EmitError!void {
    try W.write(buf, pos, "comptime {\n");
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        try W.write(buf, pos, "    @export_symbol(");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, "_ptr, \"");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, "\");\n");
    }
    if (include_position) {
        try W.write(buf, pos, "    @export_symbol(decode_position_ptr, \"position\");\n");
    }
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
}

fn writeScalarType(buf: []u8, pos: *usize, module: *const ir.Module, ty: ir.TypeId) EmitError!void {
    const resolved = module.types.get(ty);
    switch (resolved) {
        .scalar => |scalar| try W.write(buf, pos, spec.scalarTypeName(scalar)),
        .array => |array| try writeScalarType(buf, pos, module, array.elem),
        else => try W.write(buf, pos, "u32"),
    }
}
