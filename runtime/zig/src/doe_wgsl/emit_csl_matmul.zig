// emit_csl_matmul.zig — CSL PE program template for SUMMA tiled matmul.
//
// Maps Doppler's tiled matmul WGSL pattern to the SUMMA algorithm on a
// P × P PE grid using Cerebras collectives_2d for row/column broadcasts.
//
// WGSL model:  16×16 workgroup, shared memory tiles, barrier-synchronized
//              K-loop, 4×4 register tiling per thread.
//
// CSL model:   P×P PE grid, each PE holds Mt×Kt tile of A, Kt×Nt tile of B,
//              Mt×Nt accumulator tile of C. P steps: at step i, column i
//              broadcasts A tiles along its row, row i broadcasts B tiles
//              down its column. After each broadcast, local GEMM via @fmacs.
//
// Based on: sdk.cerebras.net/csl/code-examples/benchmark-gemm-collectives

const std = @import("std");
const ir = @import("ir.zig");
const spec = @import("csl_spec.zig");
const classify = @import("emit_csl_classify.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
    UnsupportedBuiltin,
    UnsupportedConstruct,
};

/// Emit a CSL PE program implementing SUMMA matmul.
pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    entry: ir.EntryPoint,
    info: classify.MatmulInfo,
) EmitError!void {
    _ = entry;
    _ = module;
    _ = info;

    try write(buf, pos, "// PE program: SUMMA tiled matmul (auto-generated from WGSL)\n");
    try write(buf, pos, "// P×P PE grid, collectives_2d for row/column broadcasts.\n");
    try write(buf, pos, "// C[M,N] = A[M,K] * B^T[N,K]\n\n");

    // Params from layout
    try write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try write(buf, pos, "param Mt: u16;\n");
    try write(buf, pos, "param Kt: u16;\n");
    try write(buf, pos, "param Nt: u16;\n");
    try write(buf, pos, "param P: u16;\n\n");

    // Imports
    try write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try write(buf, pos, "const mpi_x = @import_module(\"<collectives_2d/pe>\", .{\n");
    try write(buf, pos, "    .dim = .x,\n");
    try write(buf, pos, "});\n");
    try write(buf, pos, "const mpi_y = @import_module(\"<collectives_2d/pe>\", .{\n");
    try write(buf, pos, "    .dim = .y,\n");
    try write(buf, pos, "});\n\n");

    // Data tiles
    try write(buf, pos, "var A_tile = @zeros([Mt * Kt]f32);\n");
    try write(buf, pos, "var B_tile = @zeros([Kt * Nt]f32);\n");
    try write(buf, pos, "var C_tile = @zeros([Mt * Nt]f32);\n");
    try write(buf, pos, "var A_buf  = @zeros([Mt * Kt]f32);\n");
    try write(buf, pos, "var B_buf  = @zeros([Kt * Nt]f32);\n\n");

    // Pointers for export
    try write(buf, pos, "var A_ptr: [*]f32 = &A_tile;\n");
    try write(buf, pos, "var B_ptr: [*]f32 = &B_tile;\n");
    try write(buf, pos, "var C_ptr: [*]f32 = &C_tile;\n\n");

    // State
    try write(buf, pos, "var step: u16 = 0;\n");
    try write(buf, pos, "var px: u16 = 0;\n");
    try write(buf, pos, "var py: u16 = 0;\n\n");

    // Task IDs
    try write(buf, pos, "const x_done_id: local_task_id = @get_local_task_id(10);\n");
    try write(buf, pos, "const y_done_id: local_task_id = @get_local_task_id(11);\n");
    try write(buf, pos, "const compute_task_id: local_task_id = @get_local_task_id(12);\n");
    try write(buf, pos, "const exit_task_id: local_task_id = @get_local_task_id(13);\n\n");

    // Synchronization flags
    try write(buf, pos, "var x_done: bool = false;\n");
    try write(buf, pos, "var y_done: bool = false;\n\n");

    // Main entry — called by host
    try write(buf, pos, "fn compute() void {\n");
    try write(buf, pos, "    if (step == 0) {\n");
    try write(buf, pos, "        mpi_x.init();\n");
    try write(buf, pos, "        mpi_y.init();\n");
    try write(buf, pos, "        px = mpi_x.pe_id;\n");
    try write(buf, pos, "        py = mpi_y.pe_id;\n");
    try write(buf, pos, "    }\n\n");

    try write(buf, pos, "    const Ap = if (px == step) &A_tile else &A_buf;\n");
    try write(buf, pos, "    const Bp = if (py == step) &B_tile else &B_buf;\n\n");

    try write(buf, pos, "    x_done = false;\n");
    try write(buf, pos, "    y_done = false;\n\n");

    try write(buf, pos, "    mpi_x.broadcast(step, @ptrcast([*]u32, Ap), Mt * Kt, x_done_id);\n");
    try write(buf, pos, "    mpi_y.broadcast(step, @ptrcast([*]u32, Bp), Kt * Nt, y_done_id);\n");
    try write(buf, pos, "}\n\n");

    // Broadcast done handlers
    try write(buf, pos, "task x_done_task() void {\n");
    try write(buf, pos, "    x_done = true;\n");
    try write(buf, pos, "    if (y_done) @activate(compute_task_id);\n");
    try write(buf, pos, "}\n\n");

    try write(buf, pos, "task y_done_task() void {\n");
    try write(buf, pos, "    y_done = true;\n");
    try write(buf, pos, "    if (x_done) @activate(compute_task_id);\n");
    try write(buf, pos, "}\n\n");

    // Local GEMM + step advance
    try write(buf, pos, "task compute_step() void {\n");
    try write(buf, pos, "    const Ap = if (px == step) &A_tile else &A_buf;\n");
    try write(buf, pos, "    const Bp = if (py == step) &B_tile else &B_buf;\n\n");

    try write(buf, pos, "    // Local GEMM: C_tile += Ap * Bp^T via @fmacs\n");
    try write(buf, pos, "    for (@range(i16, Kt)) |k| {\n");
    try write(buf, pos, "        var C_dsd = @get_dsd(mem1d_dsd, .{\n");
    try write(buf, pos, "            .base_address = &C_tile,\n");
    try write(buf, pos, "            .extent = Mt,\n");
    try write(buf, pos, "        });\n");
    try write(buf, pos, "        var A_dsd = @get_dsd(mem1d_dsd, .{\n");
    try write(buf, pos, "            .base_address = Ap,\n");
    try write(buf, pos, "            .extent = Mt,\n");
    try write(buf, pos, "            .offset = @as(i16, k) * @as(i16, Mt),\n");
    try write(buf, pos, "        });\n");
    try write(buf, pos, "        for (@range(i16, Nt)) |j| {\n");
    try write(buf, pos, "            const b_val = Bp.*[@as(u32, j) * Kt + @as(u32, k)];\n");
    try write(buf, pos, "            @fmacs(C_dsd, C_dsd, A_dsd, b_val);\n");
    try write(buf, pos, "            C_dsd = @increment_dsd_offset(C_dsd, Mt, f32);\n");
    try write(buf, pos, "        }\n");
    try write(buf, pos, "    }\n\n");

    try write(buf, pos, "    step += 1;\n");
    try write(buf, pos, "    if (step != P) {\n");
    try write(buf, pos, "        compute();\n");
    try write(buf, pos, "    } else {\n");
    try write(buf, pos, "        @activate(exit_task_id);\n");
    try write(buf, pos, "    }\n");
    try write(buf, pos, "}\n\n");

    // Exit
    try write(buf, pos, "task exit_task() void {\n");
    try write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try write(buf, pos, "}\n\n");

    // Comptime bindings
    try write(buf, pos, "comptime {\n");
    try write(buf, pos, "    @bind_local_task(x_done_task, x_done_id);\n");
    try write(buf, pos, "    @bind_local_task(y_done_task, y_done_id);\n");
    try write(buf, pos, "    @bind_local_task(compute_step, compute_task_id);\n");
    try write(buf, pos, "    @bind_local_task(exit_task, exit_task_id);\n\n");

    try write(buf, pos, "    @export_symbol(A_ptr, \"A\");\n");
    try write(buf, pos, "    @export_symbol(B_ptr, \"B\");\n");
    try write(buf, pos, "    @export_symbol(C_ptr, \"C\");\n");
    try write(buf, pos, "    @export_symbol(compute);\n");
    try write(buf, pos, "}\n");
}

// ---------------------------------------------------------------------------
// Write helper
// ---------------------------------------------------------------------------

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}
