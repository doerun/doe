// emit_csl_kv_cache.zig — CSL PE programs for KV cache read/write.
//
// KV write: appends projected K/V vectors to the cache at the current
// decode position. Each PE holds a chunk of the head dimension.
//
// KV read: reads a slice of cached K/V for a range of positions.
// Each PE outputs its local chunk. No fabric needed for either.

const std = @import("std");
const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const spec = @import("csl_spec.zig");
const W = @import("emit_csl_ir_walk.zig");
const tsir_kernel_body = @import("../tsir/emit_kernel_body.zig");
const tsir_schema = @import("../tsir/schema.zig");

pub const EmitError = W.EmitError;

pub fn emitWrite(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.KvWriteInfo,
) EmitError!void {
    // Delegate to TSIR. The WGSL globals dictate the symbol names the
    // host plan binds (kp / vp / kc / vc); decode_position is a runtime
    // state buffer always exported under the literal symbol "position".
    // TSIR's `kv_write` body matches the prior hand-written control
    // flow; the live wrapper just plumbs the WGSL-derived names into
    // the SemanticFunction and asks TSIR to emit with no `tsir_` var
    // prefix.
    const kp = module.globals.items[info.key_proj_global].name;
    const vp = module.globals.items[info.val_proj_global].name;
    const kc = module.globals.items[info.key_cache_global].name;
    const vc = module.globals.items[info.val_cache_global].name;

    const axes = [_]tsir_schema.IterationAxis{
        .{ .name = "d", .lower_bound = "0", .upper_bound = "head_dim", .step = "1" },
    };
    const bindings = [_]tsir_schema.BufferBinding{
        .{ .name = kp, .group = 0, .binding = 0, .logical_shape = &.{0}, .elem = .f32, .read_write = false },
        .{ .name = vp, .group = 0, .binding = 1, .logical_shape = &.{0}, .elem = .f32, .read_write = false },
        .{ .name = kc, .group = 0, .binding = 2, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = true },
        .{ .name = vc, .group = 0, .binding = 3, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = true },
        .{ .name = "position", .group = 0, .binding = 4, .logical_shape = &.{1}, .elem = .u32, .read_write = false },
    };
    const body_bindings = [_]tsir_schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .key_projection },
        .{ .binding_index = 1, .role = .value_projection },
        .{ .binding_index = 2, .role = .key_cache },
        .{ .binding_index = 3, .role = .value_cache },
        .{ .binding_index = 4, .role = .decode_position },
    };
    const body_axes = [_]tsir_schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .hidden },
    };
    const semantic = tsir_schema.SemanticFunction{
        .name = "main",
        .family_hint = .elementwise,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = .{
            .op = .kv_write,
            .binding_roles = &body_bindings,
            .axis_roles = &body_axes,
        },
        .source_digest = [_]u8{0} ** 32,
    };
    const config = tsir_kernel_body.Config{
        .var_prefix = "",
        .head_dim_default = 256,
        .max_seq_len_default = 4096,
    };
    var fixed: [4096]u8 = undefined;
    var fba = std.heap.FixedBufferAllocator.init(&fixed);
    var sink = std.ArrayList(u8){};
    defer sink.deinit(fba.allocator());
    tsir_kernel_body.emitWithConfig(sink.writer(fba.allocator()), semantic, .csl, &config) catch |err| switch (err) {
        error.OutOfMemory => return error.OutputTooLarge,
        error.InvalidBodyContract,
        error.MissingBindingRole,
        error.UnsupportedKernelBody,
        error.UnsupportedScalarKind,
        => return error.InvalidIr,
    };
    try W.write(buf, pos, sink.items);
}

pub fn emitRead(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.KvReadInfo,
) EmitError!void {
    // Symmetric to emitWrite — delegate to TSIR using the WGSL-derived
    // storage names. No `position` state buffer for the read side; the
    // `read_start` / `read_len` params come from the host plan.
    const kc = module.globals.items[info.key_cache_global].name;
    const vc = module.globals.items[info.val_cache_global].name;
    const ko = module.globals.items[info.key_out_global].name;
    const vo = module.globals.items[info.val_out_global].name;

    const axes = [_]tsir_schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "read_len", .step = "1" },
        .{ .name = "d", .lower_bound = "0", .upper_bound = "head_dim", .step = "1" },
    };
    const bindings = [_]tsir_schema.BufferBinding{
        .{ .name = kc, .group = 0, .binding = 0, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = false },
        .{ .name = vc, .group = 0, .binding = 1, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = false },
        .{ .name = ko, .group = 0, .binding = 2, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = true },
        .{ .name = vo, .group = 0, .binding = 3, .logical_shape = &.{ 0, 0 }, .elem = .f32, .read_write = true },
    };
    const body_bindings = [_]tsir_schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .key_cache },
        .{ .binding_index = 1, .role = .value_cache },
        .{ .binding_index = 2, .role = .key_output },
        .{ .binding_index = 3, .role = .value_output },
    };
    const body_axes = [_]tsir_schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .token },
        .{ .axis_index = 1, .role = .hidden },
    };
    const semantic = tsir_schema.SemanticFunction{
        .name = "main",
        .family_hint = .gather,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = .{
            .op = .kv_read,
            .binding_roles = &body_bindings,
            .axis_roles = &body_axes,
        },
        .source_digest = [_]u8{0} ** 32,
    };
    const config = tsir_kernel_body.Config{
        .var_prefix = "",
        .head_dim_default = 256,
        .max_seq_len_default = 4096,
        .read_len_default = 1,
    };
    var fixed: [4096]u8 = undefined;
    var fba = std.heap.FixedBufferAllocator.init(&fixed);
    var sink = std.ArrayList(u8){};
    defer sink.deinit(fba.allocator());
    tsir_kernel_body.emitWithConfig(sink.writer(fba.allocator()), semantic, .csl, &config) catch |err| switch (err) {
        error.OutOfMemory => return error.OutputTooLarge,
        error.InvalidBodyContract,
        error.MissingBindingRole,
        error.UnsupportedKernelBody,
        error.UnsupportedScalarKind,
        => return error.InvalidIr,
    };
    try W.write(buf, pos, sink.items);
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
