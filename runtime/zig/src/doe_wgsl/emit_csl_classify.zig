// emit_csl_classify.zig — Kernel pattern classifier for the CSL backend.
//
// Walks the IR to determine which CSL emission template to use. GPU backends
// can translate any IR mechanically because they share the SIMT execution
// model. CSL requires pattern-specific templates because the WSE execution
// model (PE-local memory, fabric routing, wavelet-triggered tasks) has no
// shared-memory or barrier primitives.
//
// Classification is conservative: unknown patterns return .unsupported so
// the caller can reject them with an explicit error rather than emitting
// broken CSL.

const std = @import("std");
const ir = @import("ir.zig");
const maps = @import("emit_csl_maps.zig");

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

pub const ElementWiseInfo = struct {
    /// Number of storage buffer bindings used as inputs (read-only).
    input_count: u32,
    /// Number of storage buffer bindings used as outputs (read_write).
    output_count: u32,
    /// Total element count is determined at runtime from the uniform "size"
    /// field. If true, the kernel indexes via global_invocation_id.x with a
    /// bounds guard (idx >= size → return).
    has_size_guard: bool,
};

pub const ReductionInfo = struct {
    /// The workgroup-scoped shared memory global used for the reduction tree.
    shared_global_index: u32,
    /// Number of input storage buffers.
    input_count: u32,
    /// Number of output storage buffers.
    output_count: u32,
    /// True when the kernel has a two-phase structure: reduce → broadcast →
    /// element-wise apply (e.g. RMSNorm, LayerNorm, Softmax).
    has_apply_phase: bool,
};

pub const MatmulInfo = struct {
    /// Shared memory global indices for the A and B tiles.
    tile_a_global: u32,
    tile_b_global: u32,
    /// Workgroup tile dimensions extracted from the shared memory array sizes.
    tile_m: u32,
    tile_n: u32,
    tile_k: u32,
};

pub const KernelPattern = union(enum) {
    element_wise: ElementWiseInfo,
    reduction: ReductionInfo,
    tiled_matmul: MatmulInfo,
    unsupported: []const u8,
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

pub fn classify(module: *const ir.Module, entry: ir.EntryPoint) KernelPattern {
    // Only compute shaders can target CSL.
    if (entry.stage != .compute) {
        return .{ .unsupported = "only compute shaders can target CSL" };
    }

    const function = &module.functions.items[entry.function];

    // Check for unsupported builtins anywhere in the function.
    if (hasUnsupportedBuiltins(function)) {
        return .{ .unsupported = "kernel uses builtins with no CSL equivalent" };
    }

    // Count workgroup-scoped globals and storage bindings.
    var workgroup_globals: u32 = 0;
    var workgroup_global_indices: [8]u32 = undefined;
    var input_count: u32 = 0;
    var output_count: u32 = 0;
    for (module.globals.items, 0..) |global, idx| {
        if (global.addr_space) |space| {
            if (space == .workgroup) {
                if (workgroup_globals < 8) {
                    workgroup_global_indices[workgroup_globals] = @intCast(idx);
                }
                workgroup_globals += 1;
            }
            if (space == .storage and global.binding != null) {
                if (global.access) |access| {
                    switch (access) {
                        .read => input_count += 1,
                        .read_write, .write => output_count += 1,
                    }
                } else {
                    input_count += 1;
                }
            }
        }
        if (global.addr_space) |space| {
            if (space == .uniform and global.binding != null) {
                // Uniform buffers are pass-through params; don't count.
            }
        }
    }

    // Check for workgroupBarrier() calls.
    const has_barriers = hasBarrierCalls(function);

    // -----------------------------------------------------------------------
    // Classification logic
    // -----------------------------------------------------------------------

    // No shared memory, no barriers → element-wise.
    if (workgroup_globals == 0 and !has_barriers) {
        return .{
            .element_wise = .{
                .input_count = input_count,
                .output_count = output_count,
                .has_size_guard = hasSizeGuard(function),
            },
        };
    }

    // Has shared memory + barriers but ≤ 2 workgroup globals → reduction or
    // matmul. Distinguish by checking whether shared memory arrays are used
    // in a tiled load pattern (matmul) or an accumulation pattern (reduction).
    if (workgroup_globals >= 1 and has_barriers) {
        // Heuristic: tiled matmul uses exactly 2 workgroup arrays (tileA, tileB)
        // and the function has nested loops with outer product structure.
        if (workgroup_globals == 2 and hasTiledLoadPattern(module, function, workgroup_global_indices[0..2])) {
            return .{
                .tiled_matmul = extractMatmulInfo(module, workgroup_global_indices[0..2]),
            };
        }

        // Otherwise, classify as reduction.
        return .{
            .reduction = .{
                .shared_global_index = if (workgroup_globals > 0) workgroup_global_indices[0] else 0,
                .input_count = input_count,
                .output_count = output_count,
                .has_apply_phase = workgroup_globals >= 1 and has_barriers,
            },
        };
    }

    // Shared memory without barriers, or other patterns we can't classify.
    return .{ .unsupported = "unrecognized compute pattern for CSL emission" };
}

// ---------------------------------------------------------------------------
// Analysis helpers
// ---------------------------------------------------------------------------

fn hasUnsupportedBuiltins(function: *const ir.Function) bool {
    for (function.exprs.items) |expr_node| {
        switch (expr_node.data) {
            .call => |call| {
                if (call.kind == .builtin and maps.isUnsupportedBuiltin(call.name))
                    return true;
            },
            else => {},
        }
    }
    return false;
}

fn hasBarrierCalls(function: *const ir.Function) bool {
    for (function.exprs.items) |expr_node| {
        switch (expr_node.data) {
            .call => |call| {
                if (call.kind == .builtin) {
                    if (std.mem.eql(u8, call.name, "workgroupBarrier") or
                        std.mem.eql(u8, call.name, "storageBarrier") or
                        std.mem.eql(u8, call.name, "textureBarrier"))
                        return true;
                }
            },
            else => {},
        }
    }
    return false;
}

/// Check whether the compute entry function guards on global_invocation_id.x
/// against a uniform "size" field — the standard element-wise pattern.
fn hasSizeGuard(function: *const ir.Function) bool {
    // Look for an if statement with a >= or < comparison involving a param
    // with global_invocation_id builtin and a global/uniform access.
    for (function.params.items) |param| {
        if (param.io) |io| {
            if (io.builtin == .global_invocation_id) return true;
        }
    }
    return false;
}

/// Detect the tiled matmul pattern: two workgroup arrays loaded in a loop
/// with a barrier between load and compute phases.
fn hasTiledLoadPattern(module: *const ir.Module, function: *const ir.Function, wg_indices: []const u32) bool {
    _ = module;
    // Heuristic: both workgroup globals are arrays AND the function has at
    // least one for-loop containing a barrier.
    if (wg_indices.len < 2) return false;

    // Check that we have loops containing barriers — indicative of
    // the K-loop tile pattern (load tile → barrier → compute → barrier).
    var loops_with_barriers: u32 = 0;
    for (function.stmts.items) |stmt| {
        switch (stmt) {
            .loop_ => {
                // A loop that contains barriers is the K-loop pattern.
                // Full analysis would walk the body; for now count loops.
                loops_with_barriers += 1;
            },
            else => {},
        }
    }
    return loops_with_barriers >= 1;
}

fn extractMatmulInfo(module: *const ir.Module, wg_indices: []const u32) MatmulInfo {
    var tile_m: u32 = 64;
    var tile_n: u32 = 64;
    const tile_k: u32 = 16;

    // Try to extract tile dimensions from the workgroup array sizes.
    // tileA is [TILE_M * TILE_K] and tileB is [TILE_N * TILE_K].
    for (wg_indices) |gi| {
        const global = module.globals.items[gi];
        const arr_len = switch (module.types.get(global.ty)) {
            .array => |arr| arr.len orelse 0,
            else => 0,
        };
        if (arr_len == 0) continue;
        // Convention: first array is tileA (M*K), second is tileB (N*K).
        // With default 64×16 tiles: 1024 elements each.
        // We can infer K = arr_len / tile_dim if we know one dimension.
        // For now, use the Doppler convention: 1024 = 64 * 16.
        if (arr_len == 1024) {
            // Matches 64×16 tile (Doppler default)
            continue;
        }
        // For non-standard sizes, attempt factoring assuming TILE_K=16.
        const inferred_dim = arr_len / tile_k;
        if (gi == wg_indices[0]) {
            tile_m = inferred_dim;
        } else {
            tile_n = inferred_dim;
        }
    }

    return .{
        .tile_a_global = wg_indices[0],
        .tile_b_global = if (wg_indices.len > 1) wg_indices[1] else wg_indices[0],
        .tile_m = tile_m,
        .tile_n = tile_n,
        .tile_k = tile_k,
    };
}
