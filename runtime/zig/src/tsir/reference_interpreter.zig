// TSIR reference interpreter — the parity oracle.
//
// This is the single source of truth for "what counts as correct."
// Every backend (WebGPU SPIR-V, CSL simfabric, CSL hardware, native
// MSL/HLSL) is compared against THIS interpreter, never against each
// other. Drift between backends is not "the other backend is wrong" —
// drift is one-or-both disagreeing with the reference.
//
// Numerical contract (locked):
//   - IEEE-754 round-to-nearest-even for every elementary op.
//   - fp32 accumulation for every reduction regardless of source dtype;
//     a source override must be declared on the TSIR reduction region.
//   - Left-fold reduction order unless the TSIR reduction declares
//     associative_allowed, in which case the interpreter re-runs in
//     the declared tree shape.
//   - Deterministic transcendentals: exp, log, sin, cos, tan, tanh,
//     rsqrt, recip implemented as sollya-bounded minimax polynomials
//     so results are bit-reproducible across hosts. libm is NOT used.
//   - NaN and Inf propagation as declared per reduction region; the
//     default is `propagate`.
//
// This file is scaffolding. Most paths return `NotImplemented`
// against the rejection taxonomy so callers see the gap precisely
// rather than a silent zero. Explicit semantic/realization rejections
// fail early with `RejectedBySemantic`. The one executable case so far
// is the identity lowering: a SemanticFunction with exactly one
// read-only binding and one writable binding of matching shape, no
// reductions, and no collectives is interpreted as a byte-for-byte
// copy from the read input to the write output. This is a degenerate
// case — it proves the plumbing (allocator, output bytes, reference
// hash, Result struct) works end-to-end before any real dispatch lands.

const std = @import("std");
const schema = @import("schema.zig");

pub const InterpretError = error{
    OutOfMemory,
    NotImplemented,
    RejectedBySemantic,
};

pub const Result = struct {
    /// SHA-256 over the canonical byte image of all output buffers
    /// in their declared order. This is the parity hash every backend
    /// is compared against.
    reference_hash: [32]u8,
    /// Per-output-buffer raw bytes in declared order. Caller owns.
    /// Empty slice when interpretation was rejected.
    outputs: [][]const u8,
    rejections: []const schema.RejectionEntry,
};

/// Run the reference interpreter against a (semantic, realization)
/// pair and a set of inputs. The realization is consumed only for the
/// declared reduction-tree shape on `algorithm_exact` reductions; all
/// other backend-specific details are ignored here — the reference is
/// deliberately target-independent.
///
/// Caller owns the returned output buffers and the output slice itself
/// and must free them via `freeResult`.
pub fn run(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    realization: schema.Realization,
    inputs: []const []const u8,
) InterpretError!Result {
    if (semantic.rejections.len != 0 or realization.rejections.len != 0) {
        return error.RejectedBySemantic;
    }
    if (tryEmptyKernel(semantic, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (trySimpleReduction(allocator, semantic, realization, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (tryIdentity(allocator, semantic, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    return error.NotImplemented;
}

/// Free the output buffers in a Result produced by `run`. Safe to call
/// with an empty outputs slice. Rejections are const-static and are
/// not freed.
pub fn freeResult(allocator: std.mem.Allocator, result: *Result) void {
    for (result.outputs) |buf| allocator.free(buf);
    if (result.outputs.len > 0) allocator.free(result.outputs);
    result.outputs = &[_][]const u8{};
}

/// Detect the zero-binding nop kernel and interpret it. A
/// SemanticFunction with zero bindings, zero reductions, and zero
/// collectives is observably a nop; the Result has no output buffers
/// and the reference hash is `SHA-256("")`. Returns null when the
/// semantic is not shaped like the nop case, leaving the caller to
/// fall through to other dispatch paths.
///
/// This is the smallest possible real dispatch — no allocator needed,
/// no inputs consumed. It proves the multi-case dispatch pattern in
/// `run()` before any op-body-aware path lands.
fn tryEmptyKernel(
    semantic: schema.Semantic,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.bindings.len != 0) return null;
    if (func.reductions.len != 0) return null;
    if (func.collectives.len != 0) return null;
    // No bindings means no inputs are consumed.
    if (inputs.len != 0) return null;

    var hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(&[_]u8{}, &hash, .{});

    return Result{
        .reference_hash = hash,
        .outputs = &[_][]const u8{},
        .rejections = &[_]schema.RejectionEntry{},
    };
}

/// Detect the identity case and interpret it. Returns null when the
/// semantic is not shaped like identity, leaving the caller to fall
/// through to NotImplemented. Returns an allocated Result when the
/// semantic IS identity-shaped.
fn tryIdentity(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.reductions.len != 0) return null;
    if (func.collectives.len != 0) return null;

    // Exactly one read-only binding and one writable binding.
    var read_index: ?usize = null;
    var write_index: ?usize = null;
    for (func.bindings, 0..) |binding, i| {
        if (binding.read_write) {
            if (write_index != null) return null;
            write_index = i;
        } else {
            if (read_index != null) return null;
            read_index = i;
        }
    }
    const ri = read_index orelse return null;
    const wi = write_index orelse return null;
    const rb = func.bindings[ri];
    const wb = func.bindings[wi];

    // Shape and element type must match for identity.
    if (rb.elem != wb.elem) return null;
    if (rb.logical_shape.len != wb.logical_shape.len) return null;
    for (rb.logical_shape, wb.logical_shape) |r_dim, w_dim| {
        if (r_dim != w_dim) return null;
    }

    // Inputs[0] is the read binding's bytes. Copy it into a freshly
    // allocated output slot at outputs[0] (the write binding).
    if (inputs.len != 1) return null;
    const input_bytes = inputs[0];

    // Validate input buffer size matches declared shape × element size.
    // A wrong-sized input would silently produce a garbage hash; fall
    // through to NotImplemented so the caller sees a precise gap.
    const expected_bytes = computeExpectedBytes(rb) orelse return null;
    if (input_bytes.len != expected_bytes) return null;

    const output_bytes = try allocator.dupe(u8, input_bytes);
    errdefer allocator.free(output_bytes);

    var outputs = try allocator.alloc([]const u8, 1);
    outputs[0] = output_bytes;

    var hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(output_bytes, &hash, .{});

    return Result{
        .reference_hash = hash,
        .outputs = outputs,
        .rejections = &[_]schema.RejectionEntry{},
    };
}

/// Detect the simplest reduction case the oracle can honor in Phase A:
/// a 1-D `strict_ordered` sum over `f32` that reads one `[N]f32` input
/// and writes one `[1]f32` output. Accumulation happens in `f32` with
/// an explicit left-fold over the input's declared byte order, matching
/// the numerical contract in the module header. Other ops, associativity
/// modes, and dtypes fall through to `NotImplemented` so the oracle
/// never silently honors a reduction class it has not yet implemented.
fn trySimpleReduction(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    realization: schema.Realization,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.bindings.len != 2) return null;
    if (func.reductions.len != 1) return null;
    if (func.collectives.len != 0) return null;

    const reduction = func.reductions[0];
    if (reduction.contract.accumulation != .f32) return null;
    // Associativity dispatch:
    //   strict_ordered     → tree shape is always linear (left-fold).
    //   associative_allowed → require a declared Realization tree
    //                        shape. `.linear`, `.ring`, and `.binomial`
    //                        are all accepted; the reference oracle
    //                        runs on a single PE, so `.ring` is
    //                        fold-order-identical to `.linear` here
    //                        (the distinction is fabric topology,
    //                        which a single-PE interpreter cannot
    //                        exercise). `.binomial` pairwise fold is
    //                        rank-1-only this phase.
    var effective_tree_shape: schema.ReductionTreeShape = .linear;
    switch (reduction.contract.associativity) {
        .strict_ordered => {},
        .associative_allowed => {
            if (realization.functions.len != 1) return null;
            const rfunc = realization.functions[0];
            if (rfunc.semantic_index != 0) return null;
            if (rfunc.reductions.len != 1) return null;
            const rnode = rfunc.reductions[0];
            if (rnode.semantic_index != 0) return null;
            effective_tree_shape = rnode.tree_shape;
        },
    }
    // Per-rank branches own axis validation.

    var read_index: ?usize = null;
    var write_index: ?usize = null;
    for (func.bindings, 0..) |binding, i| {
        if (binding.read_write) {
            if (write_index != null) return null;
            write_index = i;
        } else {
            if (read_index != null) return null;
            read_index = i;
        }
    }
    const ri = read_index orelse return null;
    const wi = write_index orelse return null;
    if (reduction.target_binding != wi) return null;

    const rb = func.bindings[ri];
    const wb = func.bindings[wi];

    // Phase A input dtypes: f32 natively, f16 and bf16 upcast to f32
    // per the declared `NumericalContract.accumulation = .f32`. Output
    // dtypes: f32 natively, or f16 / bf16 via downcast from the f32
    // accumulator. Integer dtypes remain future work.
    if (rb.elem != .f32 and rb.elem != .f16 and rb.elem != .bf16) return null;
    if (wb.elem != .f32 and wb.elem != .f16 and wb.elem != .bf16) return null;

    const identity = reductionIdentityF32(reduction.op);
    const rank = rb.logical_shape.len;

    // 1-D input, scalar output.
    if (rank == 1) {
        if (wb.logical_shape.len != 1 or wb.logical_shape[0] != 1) return null;
        if (reduction.axis != 0) return null;

        const n_u64 = rb.logical_shape[0];
        const n: usize = std.math.cast(usize, n_u64) orelse return null;

        if (n == 0) {
            if (inputs.len != 0 and (inputs.len != 1 or inputs[0].len != 0)) return null;
            return try emitScalarFromF32(allocator, identity, wb.elem);
        }

        if (inputs.len != 1) return null;
        const input_bytes = inputs[0];
        const expected_bytes = computeExpectedBytes(rb) orelse return null;
        if (input_bytes.len != expected_bytes) return null;

        switch (effective_tree_shape) {
            .linear, .ring => {
                // On a single-PE reference, ring == linear bit-for-bit.
                var acc: f32 = identity;
                var i: usize = 0;
                while (i < n) : (i += 1) {
                    const val = readF32FromBytes(input_bytes, rb.elem, i);
                    acc = combineF32(reduction.op, acc, val);
                }
                return try emitScalarFromF32(allocator, acc, wb.elem);
            },
            .binomial => {
                // Gather all N values then pairwise-fold, passing
                // through any odd leftover to the next level. Result
                // is the op applied in a power-of-two-shaped tree
                // rather than left-associatively; on
                // non-associative floating-point it can differ bit-
                // for-bit from the linear fold, which is exactly the
                // reason `algorithm_exact` pins `tree_shape` as a
                // declared invariant.
                const vals = try allocator.alloc(f32, n);
                defer allocator.free(vals);
                var i: usize = 0;
                while (i < n) : (i += 1) {
                    vals[i] = readF32FromBytes(input_bytes, rb.elem, i);
                }
                var count: usize = n;
                while (count > 1) {
                    var new_count: usize = 0;
                    var idx: usize = 0;
                    while (idx < count) : (idx += 2) {
                        if (idx + 1 < count) {
                            vals[new_count] = combineF32(reduction.op, vals[idx], vals[idx + 1]);
                        } else {
                            vals[new_count] = vals[idx];
                        }
                        new_count += 1;
                    }
                    count = new_count;
                }
                return try emitScalarFromF32(allocator, vals[0], wb.elem);
            },
        }
    }

    // 2-D input, 1-D output along the non-reduced axis.
    if (rank == 2) {
        if (reduction.axis >= 2) return null;
        const m_u64 = rb.logical_shape[0];
        const n_u64 = rb.logical_shape[1];
        const m: usize = std.math.cast(usize, m_u64) orelse return null;
        const n: usize = std.math.cast(usize, n_u64) orelse return null;
        const non_reduced_u64: u64 = if (reduction.axis == 0) n_u64 else m_u64;
        if (wb.logical_shape.len != 1 or wb.logical_shape[0] != non_reduced_u64) return null;
        const non_reduced: usize = if (reduction.axis == 0) n else m;
        const reduce_len: usize = if (reduction.axis == 0) m else n;

        const expected_bytes = computeExpectedBytes(rb) orelse return null;
        if (inputs.len != 1) return null;
        const input_bytes = inputs[0];
        if (input_bytes.len != expected_bytes) return null;

        const out_elem_bytes: usize = wb.elem.byteSize();
        const output_bytes = try allocator.alloc(u8, non_reduced * out_elem_bytes);
        errdefer allocator.free(output_bytes);

        // Per-output scratch for binomial fold. Allocated once,
        // reused across output positions to keep the hot loop
        // alloc-free.
        var scratch: ?[]f32 = null;
        defer if (scratch) |s| allocator.free(s);
        if (effective_tree_shape == .binomial and reduce_len > 0) {
            scratch = try allocator.alloc(f32, reduce_len);
        }

        var out_i: usize = 0;
        while (out_i < non_reduced) : (out_i += 1) {
            if (effective_tree_shape == .binomial) {
                if (reduce_len == 0) {
                    writeF32AsElem(output_bytes, out_i, identity, wb.elem);
                    continue;
                }
                const vals = scratch.?;
                var r_i: usize = 0;
                while (r_i < reduce_len) : (r_i += 1) {
                    const flat_idx: usize = if (reduction.axis == 0)
                        r_i * n + out_i
                    else
                        out_i * n + r_i;
                    vals[r_i] = readF32FromBytes(input_bytes, rb.elem, flat_idx);
                }
                var count: usize = reduce_len;
                while (count > 1) {
                    var new_count: usize = 0;
                    var idx: usize = 0;
                    while (idx < count) : (idx += 2) {
                        if (idx + 1 < count) {
                            vals[new_count] = combineF32(reduction.op, vals[idx], vals[idx + 1]);
                        } else {
                            vals[new_count] = vals[idx];
                        }
                        new_count += 1;
                    }
                    count = new_count;
                }
                writeF32AsElem(output_bytes, out_i, vals[0], wb.elem);
            } else {
                // Linear / ring left-fold (bit-identical on single PE).
                var acc: f32 = identity;
                var r_i: usize = 0;
                while (r_i < reduce_len) : (r_i += 1) {
                    const flat_idx: usize = if (reduction.axis == 0)
                        r_i * n + out_i
                    else
                        out_i * n + r_i;
                    const val = readF32FromBytes(input_bytes, rb.elem, flat_idx);
                    acc = combineF32(reduction.op, acc, val);
                }
                writeF32AsElem(output_bytes, out_i, acc, wb.elem);
            }
        }

        var outputs = try allocator.alloc([]const u8, 1);
        outputs[0] = output_bytes;

        var hash: [32]u8 = undefined;
        std.crypto.hash.sha2.Sha256.hash(output_bytes, &hash, .{});

        return Result{
            .reference_hash = hash,
            .outputs = outputs,
            .rejections = &[_]schema.RejectionEntry{},
        };
    }

    // 3-D input, 2-D output along the two non-reduced axes.
    if (rank == 3) {
        if (reduction.axis >= 3) return null;
        const axis = reduction.axis;
        const a_u64 = rb.logical_shape[0];
        const b_u64 = rb.logical_shape[1];
        const c_u64 = rb.logical_shape[2];
        const a_us: usize = std.math.cast(usize, a_u64) orelse return null;
        const b_us: usize = std.math.cast(usize, b_u64) orelse return null;
        const c_us: usize = std.math.cast(usize, c_u64) orelse return null;

        // Output shape drops the reduced axis; row-major ordering is
        // preserved for the surviving dims.
        const out_dim0_u64: u64 = if (axis == 0) b_u64 else a_u64;
        const out_dim1_u64: u64 = if (axis == 2) b_u64 else c_u64;
        if (wb.logical_shape.len != 2) return null;
        if (wb.logical_shape[0] != out_dim0_u64) return null;
        if (wb.logical_shape[1] != out_dim1_u64) return null;

        const out_dim0: usize = if (axis == 0) b_us else a_us;
        const out_dim1: usize = if (axis == 2) b_us else c_us;
        const non_reduced: usize = out_dim0 * out_dim1;
        const reduce_len: usize = switch (axis) {
            0 => a_us,
            1 => b_us,
            2 => c_us,
            else => unreachable,
        };

        const expected_bytes = computeExpectedBytes(rb) orelse return null;
        if (inputs.len != 1) return null;
        const input_bytes = inputs[0];
        if (input_bytes.len != expected_bytes) return null;

        const out_elem_bytes: usize = wb.elem.byteSize();
        const output_bytes = try allocator.alloc(u8, non_reduced * out_elem_bytes);
        errdefer allocator.free(output_bytes);

        // Scratch buffer for binomial fold (reused across out_i).
        var scratch: ?[]f32 = null;
        defer if (scratch) |s| allocator.free(s);
        if (effective_tree_shape == .binomial and reduce_len > 0) {
            scratch = try allocator.alloc(f32, reduce_len);
        }

        var out_i: usize = 0;
        while (out_i < non_reduced) : (out_i += 1) {
            const d0 = out_i / out_dim1;
            const d1 = out_i % out_dim1;
            if (effective_tree_shape == .binomial) {
                if (reduce_len == 0) {
                    writeF32AsElem(output_bytes, out_i, identity, wb.elem);
                    continue;
                }
                const vals = scratch.?;
                var r: usize = 0;
                while (r < reduce_len) : (r += 1) {
                    const flat: usize = switch (axis) {
                        0 => r * b_us * c_us + d0 * c_us + d1,
                        1 => d0 * b_us * c_us + r * c_us + d1,
                        2 => d0 * b_us * c_us + d1 * c_us + r,
                        else => unreachable,
                    };
                    vals[r] = readF32FromBytes(input_bytes, rb.elem, flat);
                }
                var count: usize = reduce_len;
                while (count > 1) {
                    var new_count: usize = 0;
                    var idx: usize = 0;
                    while (idx < count) : (idx += 2) {
                        if (idx + 1 < count) {
                            vals[new_count] = combineF32(reduction.op, vals[idx], vals[idx + 1]);
                        } else {
                            vals[new_count] = vals[idx];
                        }
                        new_count += 1;
                    }
                    count = new_count;
                }
                writeF32AsElem(output_bytes, out_i, vals[0], wb.elem);
            } else {
                var acc: f32 = identity;
                var r: usize = 0;
                while (r < reduce_len) : (r += 1) {
                    // Row-major input: [a, b, c] → flat = a*B*C + b*C + c.
                    const flat: usize = switch (axis) {
                        0 => r * b_us * c_us + d0 * c_us + d1,
                        1 => d0 * b_us * c_us + r * c_us + d1,
                        2 => d0 * b_us * c_us + d1 * c_us + r,
                        else => unreachable,
                    };
                    const val = readF32FromBytes(input_bytes, rb.elem, flat);
                    acc = combineF32(reduction.op, acc, val);
                }
                writeF32AsElem(output_bytes, out_i, acc, wb.elem);
            }
        }

        var outputs = try allocator.alloc([]const u8, 1);
        outputs[0] = output_bytes;

        var hash: [32]u8 = undefined;
        std.crypto.hash.sha2.Sha256.hash(output_bytes, &hash, .{});

        return Result{
            .reference_hash = hash,
            .outputs = outputs,
            .rejections = &[_]schema.RejectionEntry{},
        };
    }

    // Rank 4+ fallback: generic N-D reduction. Same row-major layout,
    // same accumulation contract, same op dispatch — the difference is
    // the non-reduced iteration uses an odometer instead of explicit
    // nested loops so any rank works without another per-rank branch.
    if (rank >= 4) {
        if (effective_tree_shape == .binomial) return null;
        const axis = reduction.axis;
        if (axis >= rank) return null;

        // Validate output shape: rank-1, skipping the reduced axis.
        if (wb.logical_shape.len != rank - 1) return null;
        {
            var src_idx: usize = 0;
            for (wb.logical_shape) |w_dim| {
                if (src_idx == axis) src_idx += 1;
                if (src_idx >= rank) return null;
                if (rb.logical_shape[src_idx] != w_dim) return null;
                src_idx += 1;
            }
        }

        // Row-major input strides.
        const shape_us = try allocator.alloc(usize, rank);
        defer allocator.free(shape_us);
        for (rb.logical_shape, 0..) |d, i| {
            shape_us[i] = std.math.cast(usize, d) orelse return null;
        }
        const strides = try allocator.alloc(usize, rank);
        defer allocator.free(strides);
        strides[rank - 1] = 1;
        {
            var i: usize = rank - 1;
            while (i > 0) : (i -= 1) {
                strides[i - 1] = strides[i] * shape_us[i];
            }
        }

        var non_reduced: usize = 1;
        for (shape_us, 0..) |d, i| {
            if (i == axis) continue;
            non_reduced *= d;
        }
        const reduce_len: usize = shape_us[axis];
        const axis_stride: usize = strides[axis];

        const expected_bytes = computeExpectedBytes(rb) orelse return null;
        if (inputs.len != 1) return null;
        const input_bytes = inputs[0];
        if (input_bytes.len != expected_bytes) return null;

        const out_elem_bytes: usize = wb.elem.byteSize();
        const output_bytes = try allocator.alloc(u8, non_reduced * out_elem_bytes);
        errdefer allocator.free(output_bytes);

        const out_rank: usize = rank - 1;
        const out_coords = try allocator.alloc(usize, out_rank);
        defer allocator.free(out_coords);
        for (out_coords) |*c| c.* = 0;

        var out_linear: usize = 0;
        iter: while (true) {
            // Base offset in input from current out_coords.
            var base_offset: usize = 0;
            for (out_coords, 0..) |c, out_pos| {
                const in_dim_idx: usize = if (out_pos < axis) out_pos else out_pos + 1;
                base_offset += c * strides[in_dim_idx];
            }

            var acc: f32 = identity;
            var r: usize = 0;
            while (r < reduce_len) : (r += 1) {
                const flat = base_offset + r * axis_stride;
                const val = readF32FromBytes(input_bytes, rb.elem, flat);
                acc = combineF32(reduction.op, acc, val);
            }
            writeF32AsElem(output_bytes, out_linear, acc, wb.elem);

            out_linear += 1;
            if (out_linear >= non_reduced) break;

            // Increment odometer from rightmost out_pos, carrying left.
            var carry_pos: usize = out_rank - 1;
            while (true) {
                out_coords[carry_pos] += 1;
                const limit_u64 = wb.logical_shape[carry_pos];
                const limit: usize = std.math.cast(usize, limit_u64) orelse return null;
                if (out_coords[carry_pos] < limit) break;
                out_coords[carry_pos] = 0;
                if (carry_pos == 0) break :iter;
                carry_pos -= 1;
            }
        }

        var outputs = try allocator.alloc([]const u8, 1);
        outputs[0] = output_bytes;

        var hash: [32]u8 = undefined;
        std.crypto.hash.sha2.Sha256.hash(output_bytes, &hash, .{});

        return Result{
            .reference_hash = hash,
            .outputs = outputs,
            .rejections = &[_]schema.RejectionEntry{},
        };
    }

    return null;
}

/// Identity element for a reduction op in f32. Left-folding any
/// sequence starting from this value must yield the same result as
/// folding the sequence alone.
fn reductionIdentityF32(op: schema.ReductionOp) f32 {
    return switch (op) {
        .sum => 0.0,
        .product => 1.0,
        .min => std.math.inf(f32),
        .max => -std.math.inf(f32),
    };
}

/// Combine `acc` with `val` under the declared reduction op in f32.
/// `std.math.min` / `std.math.max` honor IEEE-754 min/max semantics
/// including NaN propagation per the `NanInfPolicy.propagate` contract.
fn combineF32(op: schema.ReductionOp, acc: f32, val: f32) f32 {
    return switch (op) {
        .sum => acc + val,
        .product => acc * val,
        .min => @min(acc, val),
        .max => @max(acc, val),
    };
}

/// Read one f32 value from a byte buffer at `elem_idx`, upcasting from
/// the declared element type. Supports:
///   * `.f32`  — read 4 LE bytes, `@bitCast` to f32.
///   * `.f16`  — read 2 LE bytes, `@bitCast` to f16, `@floatCast` to f32.
///   * `.bf16` — read 2 LE bytes, splice into the high 16 bits of a u32,
///               `@bitCast` the result to f32 (bf16 is f32 truncated
///               to its high 16 bits, so this upcast is exact and
///               avoids needing a native Zig bf16 type).
///
/// Unsupported dtypes are guarded at the trySimpleReduction entry so
/// this helper's `else` branch is unreachable in practice.
fn readF32FromBytes(
    bytes: []const u8,
    elem: schema.ScalarKind,
    elem_idx: usize,
) f32 {
    switch (elem) {
        .f32 => {
            const word = std.mem.readInt(u32, bytes[elem_idx * 4 ..][0..4], .little);
            return @bitCast(word);
        },
        .f16 => {
            const word = std.mem.readInt(u16, bytes[elem_idx * 2 ..][0..2], .little);
            const v16: f16 = @bitCast(word);
            return @floatCast(v16);
        },
        .bf16 => {
            const word = std.mem.readInt(u16, bytes[elem_idx * 2 ..][0..2], .little);
            const f32_bits: u32 = @as(u32, word) << 16;
            return @bitCast(f32_bits);
        },
        else => unreachable,
    }
}

/// Emit a single scalar f32 as the declared output dtype. Used by the
/// rank-1 reduction path; the rank-2 path emits a vector element-wise
/// through `writeF32AsElem` directly.
fn emitScalarFromF32(
    allocator: std.mem.Allocator,
    acc: f32,
    elem: schema.ScalarKind,
) InterpretError!Result {
    const out_bytes_len: usize = elem.byteSize();
    const output_bytes = try allocator.alloc(u8, out_bytes_len);
    errdefer allocator.free(output_bytes);
    writeF32AsElem(output_bytes, 0, acc, elem);

    var outputs = try allocator.alloc([]const u8, 1);
    outputs[0] = output_bytes;

    var hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(output_bytes, &hash, .{});

    return Result{
        .reference_hash = hash,
        .outputs = outputs,
        .rejections = &[_]schema.RejectionEntry{},
    };
}

/// Write one f32 value into `bytes` at element index `elem_idx`,
/// downcasting to the declared output dtype. Supports:
///   * `.f32`  — `@bitCast` to u32, write 4 LE bytes.
///   * `.f16`  — `@floatCast` to f16, `@bitCast` to u16, write 2 LE bytes.
///   * `.bf16` — round-to-nearest-even via bias trick on the u32 bit
///               pattern, with explicit NaN preservation (quiet-NaN
///               bit forced on) so a rounding overflow cannot turn
///               a NaN into an Inf. Write 2 LE bytes.
/// Integer outputs remain future work; the caller's entry check
/// guarantees this helper's `else` branch is unreachable in practice.
fn writeF32AsElem(
    bytes: []u8,
    elem_idx: usize,
    val: f32,
    elem: schema.ScalarKind,
) void {
    switch (elem) {
        .f32 => {
            const bits: u32 = @bitCast(val);
            std.mem.writeInt(u32, bytes[elem_idx * 4 ..][0..4], bits, .little);
        },
        .f16 => {
            const v16: f16 = @floatCast(val);
            const bits: u16 = @bitCast(v16);
            std.mem.writeInt(u16, bytes[elem_idx * 2 ..][0..2], bits, .little);
        },
        .bf16 => {
            const bits: u16 = f32ToBf16Rne(val);
            std.mem.writeInt(u16, bytes[elem_idx * 2 ..][0..2], bits, .little);
        },
        else => unreachable,
    }
}

/// Convert f32 → bf16 via round-to-nearest-even on the u32 bit pattern.
/// NaN inputs are propagated with the quiet-NaN bit forced on so that
/// the rounding bias cannot produce an Inf from a NaN.
fn f32ToBf16Rne(val: f32) u16 {
    const bits: u32 = @bitCast(val);
    const exp: u32 = (bits >> 23) & 0xff;
    const mantissa: u32 = bits & 0x7fffff;
    if (exp == 0xff and mantissa != 0) {
        // NaN: take the high 16 bits and ensure the quiet-NaN mantissa
        // bit is set. This avoids turning NaN into Inf via the bias.
        return @as(u16, @intCast((bits >> 16) | 0x40));
    }
    const lsb: u32 = (bits >> 16) & 1;
    const rounding_bias: u32 = 0x7fff + lsb;
    const rounded: u32 = bits +% rounding_bias;
    return @as(u16, @intCast(rounded >> 16));
}

/// Compute the expected total byte count for a buffer binding from its
/// declared shape and element type. Returns null when the shape implies
/// an overflow in u64 arithmetic; the caller treats that as "cannot
/// interpret" rather than silently truncating.
fn computeExpectedBytes(binding: schema.BufferBinding) ?u64 {
    var elems: u64 = 1;
    for (binding.logical_shape) |dim| {
        if (dim == 0) return 0;
        elems = std.math.mul(u64, elems, dim) catch return null;
    }
    return std.math.mul(u64, elems, @as(u64, binding.elem.byteSize())) catch null;
}

/// Return the set of transcendental implementations the interpreter
/// uses. The real table pins each to a sollya-bounded minimax
/// polynomial with a declared worst-case ULP error bound.
pub const TranscendentalTable = struct {
    exp_ulp_bound: u32 = 1,
    log_ulp_bound: u32 = 1,
    sin_ulp_bound: u32 = 1,
    cos_ulp_bound: u32 = 1,
    tan_ulp_bound: u32 = 2,
    tanh_ulp_bound: u32 = 2,
    rsqrt_ulp_bound: u32 = 1,
    recip_ulp_bound: u32 = 1,
};

pub fn transcendentals() TranscendentalTable {
    return .{};
}

test "reference interpreter refuses zero oracle by default" {
    const allocator = std.testing.allocator;
    const semantic = schema.Semantic{ .functions = &.{}, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const inputs = [_][]const u8{};
    const outcome = run(allocator, semantic, realization, &inputs);
    try std.testing.expectError(InterpretError.NotImplemented, outcome);
}

test "reference interpreter rejects semantic or realization rejections before execution" {
    const allocator = std.testing.allocator;
    const semantic_rejections = [_]schema.RejectionEntry{
        .{
            .reason = .tsir_target_unfit,
            .node_path = "functions[0]",
            .detail = "fixture-rejected",
        },
    };
    const semantic = schema.Semantic{
        .functions = &.{},
        .rejections = &semantic_rejections,
    };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const inputs = [_][]const u8{};
    const outcome = run(allocator, semantic, realization, &inputs);
    try std.testing.expectError(InterpretError.RejectedBySemantic, outcome);
}

test "identity kernel copies input bytes and hashes output" {
    const allocator = std.testing.allocator;
    const shape = [_]u64{8};
    const bindings = [_]schema.BufferBinding{
        .{
            .name = "in",
            .group = 0,
            .binding = 0,
            .logical_shape = &shape,
            .elem = .u32,
            .read_write = false,
        },
        .{
            .name = "out",
            .group = 0,
            .binding = 1,
            .logical_shape = &shape,
            .elem = .u32,
            .read_write = true,
        },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "8", .step = "1" },
    };
    const func = schema.SemanticFunction{
        .name = "identity",
        .family_hint = .elementwise,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    const payload = [_]u8{ 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32 };
    const inputs = [_][]const u8{&payload};
    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqualSlices(u8, &payload, result.outputs[0]);

    var expected: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(&payload, &expected, .{});
    try std.testing.expectEqualSlices(u8, &expected, &result.reference_hash);
}

test "identity refuses when input byte count disagrees with declared shape" {
    const allocator = std.testing.allocator;
    const shape = [_]u64{8};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &shape, .elem = .u32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &shape, .elem = .u32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "8", .step = "1" },
    };
    const func = schema.SemanticFunction{
        .name = "identity",
        .family_hint = .elementwise,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    // Declared shape u32[8] = 32 bytes; provide 16 bytes and 64 bytes to
    // verify both under-sized and over-sized inputs are rejected rather
    // than silently hashed.
    const too_small = [_]u8{0} ** 16;
    const inputs_small = [_][]const u8{&too_small};
    try std.testing.expectError(
        InterpretError.NotImplemented,
        run(allocator, semantic, realization, &inputs_small),
    );
    const too_large = [_]u8{0} ** 64;
    const inputs_large = [_][]const u8{&too_large};
    try std.testing.expectError(
        InterpretError.NotImplemented,
        run(allocator, semantic, realization, &inputs_large),
    );
}

test "zero-binding kernel interprets as observable nop with empty-string hash" {
    const allocator = std.testing.allocator;
    const func = schema.SemanticFunction{
        .name = "nop",
        .family_hint = .elementwise,
        .axes = &.{},
        .bindings = &.{},
        .reductions = &.{},
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const inputs = [_][]const u8{};
    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    try std.testing.expectEqual(@as(usize, 0), result.outputs.len);
    var expected: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(&[_]u8{}, &expected, .{});
    try std.testing.expectEqualSlices(u8, &expected, &result.reference_hash);
}

test "zero-binding refuses when non-empty inputs are supplied" {
    const allocator = std.testing.allocator;
    const func = schema.SemanticFunction{
        .name = "nop",
        .family_hint = .elementwise,
        .axes = &.{},
        .bindings = &.{},
        .reductions = &.{},
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    // A nop kernel consumes no inputs; supplying one is a mismatch
    // between declared bindings and caller contract.
    const payload = [_]u8{1};
    const inputs = [_][]const u8{&payload};
    try std.testing.expectError(
        InterpretError.NotImplemented,
        run(allocator, semantic, realization, &inputs),
    );
}

test "strict_ordered f32 sum reduces [4]f32 to [1]f32 with matching hash" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // input = [1.0, 2.0, 3.0, 4.0] as little-endian f32 bytes.
    var input_bytes: [16]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 4), result.outputs[0].len);

    const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
    const out_val: f32 = @bitCast(out_word);
    try std.testing.expectEqual(@as(f32, 10.0), out_val);

    var expected_hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(result.outputs[0], &expected_hash, .{});
    try std.testing.expectEqualSlices(u8, &expected_hash, &result.reference_hash);
}

test "associative_allowed with linear realization tree folds as left-fold" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .associative_allowed,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_assoc",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };

    // Build a matching realization with declared tree shape = linear.
    const red_nodes = [_]schema.ReductionRealizationNode{
        .{ .semantic_index = 0, .tree_shape = .linear },
    };
    const rfuncs = [_]schema.RealizationFunction{
        .{
            .semantic_index = 0,
            .tiles = .{ .per_axis = &.{} },
            .pe_grid = .{ .width = 1, .height = 1 },
            .residency = &.{},
            .collectives = &.{},
            .reductions = &red_nodes,
            .emitter_params_json = "{}",
            .target_descriptor_hash = [_]u8{0} ** 32,
        },
    };
    const realization = schema.Realization{
        .functions = &rfuncs,
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [16]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
    const out_val: f32 = @bitCast(out_word);
    try std.testing.expectEqual(@as(f32, 10.0), out_val);
}

test "associative_allowed without realization tree shape falls through" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .associative_allowed,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_assoc_nodecl",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    // No matching realization function.
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const payload = [_]u8{0} ** 16;
    const inputs = [_][]const u8{&payload};
    try std.testing.expectError(
        InterpretError.NotImplemented,
        run(allocator, semantic, realization, &inputs),
    );
}

test "associative_allowed with binomial tree folds rank-1 pairwise" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };

    const red_nodes = [_]schema.ReductionRealizationNode{
        .{ .semantic_index = 0, .tree_shape = .binomial },
    };
    const rfuncs = [_]schema.RealizationFunction{
        .{
            .semantic_index = 0,
            .tiles = .{ .per_axis = &.{} },
            .pe_grid = .{ .width = 1, .height = 1 },
            .residency = &.{},
            .collectives = &.{},
            .reductions = &red_nodes,
            .emitter_params_json = "{}",
            .target_descriptor_hash = [_]u8{0} ** 32,
        },
    };
    const realization = schema.Realization{
        .functions = &rfuncs,
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Cover sum, product, min, max on small integers where both tree
    // shapes must agree bit-for-bit (integer values representable exactly).
    const cases = [_]struct { op: schema.ReductionOp, expected: f32 }{
        .{ .op = .sum, .expected = 10.0 },
        .{ .op = .product, .expected = 24.0 },
        .{ .op = .min, .expected = 1.0 },
        .{ .op = .max, .expected = 4.0 },
    };

    var input_bytes: [16]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    for (cases) |case| {
        const reductions = [_]schema.ReductionRegion{
            .{
                .axis = 0,
                .op = case.op,
                .contract = .{
                    .accumulation = .f32,
                    .associativity = .associative_allowed,
                    .nan_inf = .propagate,
                },
                .target_binding = 1,
            },
        };
        const func = schema.SemanticFunction{
            .name = "reduce4_binomial",
            .family_hint = .reduction,
            .axes = &axes,
            .bindings = &bindings,
            .reductions = &reductions,
            .collectives = &.{},
            .source_digest = [_]u8{0} ** 32,
        };
        const funcs = [_]schema.SemanticFunction{func};
        const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };

        var result = try run(allocator, semantic, realization, &inputs);
        defer freeResult(allocator, &result);
        const word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(case.expected, v);
    }
}

test "associative_allowed with binomial on rank-2 folds per output position" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{ 2, 4 };
    const out_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "j", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .associative_allowed,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum24_binomial",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const red_nodes = [_]schema.ReductionRealizationNode{
        .{ .semantic_index = 0, .tree_shape = .binomial },
    };
    const rfuncs = [_]schema.RealizationFunction{
        .{
            .semantic_index = 0,
            .tiles = .{ .per_axis = &.{} },
            .pe_grid = .{ .width = 1, .height = 1 },
            .residency = &.{},
            .collectives = &.{},
            .reductions = &red_nodes,
            .emitter_params_json = "{}",
            .target_descriptor_hash = [_]u8{0} ** 32,
        },
    };
    const realization = schema.Realization{
        .functions = &rfuncs,
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Row 0: [1,2,3,4] binomial-sum → (1+2) + (3+4) = 10.
    // Row 1: [5,6,7,8] binomial-sum → (5+6) + (7+8) = 26.
    var input_bytes: [32]u8 = undefined;
    const vals = [_]f32{ 1, 2, 3, 4, 5, 6, 7, 8 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    const expected = [_]f32{ 10.0, 26.0 };
    for (expected, 0..) |e, i| {
        const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(e, v);
    }
}

test "associative_allowed with binomial on rank-3 folds per output position" {
    const allocator = std.testing.allocator;
    // Shape [2, 2, 4], reduce axis 2 → [2, 2] of binomial row-sums.
    // Each [4]-element row binomial-sums as (v0+v1)+(v2+v3).
    // Row 0: 1+2,3+4 → 3,7 → 10. Row 1: 5+6,7+8 → 11,15 → 26.
    // Row 2: 9+10,11+12 → 19,23 → 42. Row 3: 13+14,15+16 → 27,31 → 58.
    const in_shape = [_]u64{ 2, 2, 4 };
    const out_shape = [_]u64{ 2, 2 };
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "a", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "b", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "c", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 2,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .associative_allowed,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum3d_binomial_axis2",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const red_nodes = [_]schema.ReductionRealizationNode{
        .{ .semantic_index = 0, .tree_shape = .binomial },
    };
    const rfuncs = [_]schema.RealizationFunction{
        .{
            .semantic_index = 0,
            .tiles = .{ .per_axis = &.{} },
            .pe_grid = .{ .width = 1, .height = 1 },
            .residency = &.{},
            .collectives = &.{},
            .reductions = &red_nodes,
            .emitter_params_json = "{}",
            .target_descriptor_hash = [_]u8{0} ** 32,
        },
    };
    const realization = schema.Realization{
        .functions = &rfuncs,
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [64]u8 = undefined;
    for (0..16) |i| {
        const v: f32 = @floatFromInt(i + 1);
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[i * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    const expected = [_]f32{ 10.0, 26.0, 42.0, 58.0 };
    for (expected, 0..) |e, i| {
        const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(e, v);
    }
}

test "associative_allowed with ring tree shape folds identically to linear on a single PE" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .associative_allowed,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_assoc_ring",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const red_nodes = [_]schema.ReductionRealizationNode{
        .{ .semantic_index = 0, .tree_shape = .ring },
    };
    const rfuncs = [_]schema.RealizationFunction{
        .{
            .semantic_index = 0,
            .tiles = .{ .per_axis = &.{} },
            .pe_grid = .{ .width = 1, .height = 1 },
            .residency = &.{},
            .collectives = &.{},
            .reductions = &red_nodes,
            .emitter_params_json = "{}",
            .target_descriptor_hash = [_]u8{0} ** 32,
        },
    };
    const realization = schema.Realization{
        .functions = &rfuncs,
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [16]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
    const out_val: f32 = @bitCast(out_word);
    try std.testing.expectEqual(@as(f32, 10.0), out_val);
}

test "associative_allowed with ring tree shape works on rank-2" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{ 2, 3 };
    const out_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "j", .lower_bound = "0", .upper_bound = "3", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .associative_allowed,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum23_ring",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const red_nodes = [_]schema.ReductionRealizationNode{
        .{ .semantic_index = 0, .tree_shape = .ring },
    };
    const rfuncs = [_]schema.RealizationFunction{
        .{
            .semantic_index = 0,
            .tiles = .{ .per_axis = &.{} },
            .pe_grid = .{ .width = 1, .height = 1 },
            .residency = &.{},
            .collectives = &.{},
            .reductions = &red_nodes,
            .emitter_params_json = "{}",
            .target_descriptor_hash = [_]u8{0} ** 32,
        },
    };
    const realization = schema.Realization{
        .functions = &rfuncs,
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [24]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0, 5.0, 6.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    const expected = [_]f32{ 6.0, 15.0 };
    for (expected, 0..) |e, i| {
        const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(e, v);
    }
}

test "simple reduction refuses non-strict associativity" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .associative_allowed,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_assoc",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const payload = [_]u8{0} ** 16;
    const inputs = [_][]const u8{&payload};
    try std.testing.expectError(
        InterpretError.NotImplemented,
        run(allocator, semantic, realization, &inputs),
    );
}

test "strict_ordered f32 product / min / max reductions match their op semantics" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Input [1.0, 2.0, 3.0, 4.0]
    var input_bytes: [16]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    const cases = [_]struct { op: schema.ReductionOp, expected: f32 }{
        .{ .op = .product, .expected = 24.0 },
        .{ .op = .min, .expected = 1.0 },
        .{ .op = .max, .expected = 4.0 },
    };

    for (cases) |case| {
        const reductions = [_]schema.ReductionRegion{
            .{
                .axis = 0,
                .op = case.op,
                .contract = .{
                    .accumulation = .f32,
                    .associativity = .strict_ordered,
                    .nan_inf = .propagate,
                },
                .target_binding = 1,
            },
        };
        const func = schema.SemanticFunction{
            .name = "reduce4",
            .family_hint = .reduction,
            .axes = &axes,
            .bindings = &bindings,
            .reductions = &reductions,
            .collectives = &.{},
            .source_digest = [_]u8{0} ** 32,
        };
        const funcs = [_]schema.SemanticFunction{func};
        const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };

        var result = try run(allocator, semantic, realization, &inputs);
        defer freeResult(allocator, &result);

        const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
        const out_val: f32 = @bitCast(out_word);
        try std.testing.expectEqual(case.expected, out_val);
    }
}

test "f16 input sum reduces to f32 scalar under fp32 accumulation" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f16, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_f16",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Input [1.0, 2.0, 3.0, 4.0] as f16 bytes (2 bytes each = 8 bytes total).
    var input_bytes: [8]u8 = undefined;
    const vals = [_]f16{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u16 = @bitCast(v);
        std.mem.writeInt(u16, input_bytes[idx * 2 ..][0..2], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 4), result.outputs[0].len);
    const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
    const out_val: f32 = @bitCast(out_word);
    // f16 representations of 1/2/3/4 are exact; sum = 10 exactly.
    try std.testing.expectEqual(@as(f32, 10.0), out_val);
}

test "bf16 input sum reduces to f32 scalar under fp32 accumulation" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .bf16, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_bf16",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // bf16 encoding: take the high 16 bits of the f32 bit pattern.
    // Integers 1/2/3/4 as f32 have mantissa low bits zero, so
    // truncating to bf16 and back is exact; sum = 10 bit-identical.
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    var input_bytes: [8]u8 = undefined;
    for (vals, 0..) |v, idx| {
        const f32_bits: u32 = @bitCast(v);
        const high16: u16 = @intCast(f32_bits >> 16);
        std.mem.writeInt(u16, input_bytes[idx * 2 ..][0..2], high16, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
    const out_val: f32 = @bitCast(out_word);
    try std.testing.expectEqual(@as(f32, 10.0), out_val);
}

test "f16 output downcasts f32 accumulator to [1]f16" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_out_f16",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [16]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    try std.testing.expectEqual(@as(usize, 2), result.outputs[0].len);

    const out_word = std.mem.readInt(u16, result.outputs[0][0..2], .little);
    const out_val: f16 = @bitCast(out_word);
    try std.testing.expectEqual(@as(f16, 10.0), out_val);
}

test "bf16 output downcasts f32 accumulator with round-to-nearest-even" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{4};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .bf16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4_out_bf16",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [16]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    try std.testing.expectEqual(@as(usize, 2), result.outputs[0].len);

    // bf16(10.0) = high 16 bits of f32(10.0) = 0x41200000 >> 16 = 0x4120.
    // Reading back: 0x4120 << 16 = 0x41200000 = 10.0 f32 exact.
    const out_bits = std.mem.readInt(u16, result.outputs[0][0..2], .little);
    try std.testing.expectEqual(@as(u16, 0x4120), out_bits);
}

test "f32ToBf16Rne handles NaN without turning into Inf" {
    // Quiet NaN f32 bits: exponent all ones, mantissa non-zero with
    // high bit set.
    const nan_bits: u32 = 0x7fc00001;
    const nan_val: f32 = @bitCast(nan_bits);
    const out = f32ToBf16Rne(nan_val);
    // Expand the bf16 back to f32 and verify it's still NaN.
    const reconstructed_bits: u32 = @as(u32, out) << 16;
    const reconstructed: f32 = @bitCast(reconstructed_bits);
    try std.testing.expect(std.math.isNan(reconstructed));
}

test "f32ToBf16Rne rounds ties-to-even on exact half values" {
    // Value with low 16 bits = 0x8000 (exact half) and bit 16 of bit
    // pattern = 0 should round DOWN (even).
    // Pick bits = 0x3F808000 → value between 1.0 and 1.0078..., mid.
    // Bit 16 is 0 (high bits 0x3F80 ends with 0), so RTNE rounds down.
    const down_bits: u32 = 0x3f808000;
    const down_val: f32 = @bitCast(down_bits);
    const out_down = f32ToBf16Rne(down_val);
    try std.testing.expectEqual(@as(u16, 0x3f80), out_down);

    // Value with low 16 bits = 0x8000 and bit 16 = 1 should round UP (even).
    // Pick bits = 0x3F818000 → bit 16 = 1, so RTNE rounds up to 0x3F82.
    const up_bits: u32 = 0x3f818000;
    const up_val: f32 = @bitCast(up_bits);
    const out_up = f32ToBf16Rne(up_val);
    try std.testing.expectEqual(@as(u16, 0x3f82), out_up);
}

test "4-D f32 sum reduces via generic N-D fallback" {
    const allocator = std.testing.allocator;
    // Input shape [2, 2, 2, 2] with values 1..16. axis 3 (innermost)
    // → output [2, 2, 2] of pairwise sums: (1+2, 3+4, ...) = [3,7,11,15,19,23,27,31].
    const in_shape = [_]u64{ 2, 2, 2, 2 };
    const out_shape = [_]u64{ 2, 2, 2 };
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "a", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "b", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "c", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "d", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 3,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4d_axis3",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [64]u8 = undefined;
    for (0..16) |i| {
        const v: f32 = @floatFromInt(i + 1);
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[i * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    try std.testing.expectEqual(@as(usize, 32), result.outputs[0].len);

    const expected = [_]f32{ 3.0, 7.0, 11.0, 15.0, 19.0, 23.0, 27.0, 31.0 };
    for (expected, 0..) |e, i| {
        const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(e, v);
    }
}

test "4-D f32 sum reduces along a non-innermost axis" {
    const allocator = std.testing.allocator;
    // Shape [2, 3, 1, 2], reduce axis 1 → [2, 1, 2] of column sums
    // per (a, c, d). Input values 1..12.
    // in[a, b, c, d]: stride [6, 2, 2, 1], so flat = 6a + 2b + 2c + d.
    // Wait: actually with shape [2, 3, 1, 2]:
    //   strides: last=1, then 1*2=2 (c), 2*1=2 (b), 2*3=6 (a). So
    //   flat = a*6 + b*2 + c*2 + d.
    // For a=0, c=0, d=0: b=0→in[0]=1, b=1→in[2]=3, b=2→in[4]=5; sum=9.
    // For a=0, c=0, d=1: b=0→in[1]=2, b=1→in[3]=4, b=2→in[5]=6; sum=12.
    // For a=1, c=0, d=0: b=0→in[6]=7, b=1→in[8]=9, b=2→in[10]=11; sum=27.
    // For a=1, c=0, d=1: b=0→in[7]=8, b=1→in[9]=10, b=2→in[11]=12; sum=30.
    const in_shape = [_]u64{ 2, 3, 1, 2 };
    const out_shape = [_]u64{ 2, 1, 2 };
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "a", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "b", .lower_bound = "0", .upper_bound = "3", .step = "1" },
        .{ .name = "c", .lower_bound = "0", .upper_bound = "1", .step = "1" },
        .{ .name = "d", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum4d_axis1",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [48]u8 = undefined;
    for (0..12) |i| {
        const v: f32 = @floatFromInt(i + 1);
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[i * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    const expected = [_]f32{ 9.0, 12.0, 27.0, 30.0 };
    for (expected, 0..) |e, i| {
        const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(e, v);
    }
}

test "3-D f32 sum reduces over each axis with correct row-major offsets" {
    const allocator = std.testing.allocator;
    // Input [[[1,2],[3,4]],[[5,6],[7,8]]] shape [2, 2, 2].
    const in_shape = [_]u64{ 2, 2, 2 };
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0 };
    var input_bytes: [32]u8 = undefined;
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "a", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "b", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "c", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };

    // axis=0: reduce first dim → [2,2].
    // out[b,c] = in[0,b,c] + in[1,b,c]
    // out[0,0]=1+5=6, out[0,1]=2+6=8, out[1,0]=3+7=10, out[1,1]=4+8=12.
    // axis=1: reduce middle dim → [2,2].
    // out[a,c] = in[a,0,c] + in[a,1,c]
    // out[0,0]=1+3=4, out[0,1]=2+4=6, out[1,0]=5+7=12, out[1,1]=6+8=14.
    // axis=2: reduce last dim → [2,2].
    // out[a,b] = in[a,b,0] + in[a,b,1]
    // out[0,0]=1+2=3, out[0,1]=3+4=7, out[1,0]=5+6=11, out[1,1]=7+8=15.
    const cases = [_]struct {
        axis: u32,
        out_shape: [2]u64,
        expected: [4]f32,
    }{
        .{ .axis = 0, .out_shape = .{ 2, 2 }, .expected = .{ 6.0, 8.0, 10.0, 12.0 } },
        .{ .axis = 1, .out_shape = .{ 2, 2 }, .expected = .{ 4.0, 6.0, 12.0, 14.0 } },
        .{ .axis = 2, .out_shape = .{ 2, 2 }, .expected = .{ 3.0, 7.0, 11.0, 15.0 } },
    };

    for (cases) |case| {
        const out_shape = case.out_shape;
        const bindings = [_]schema.BufferBinding{
            .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
            .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
        };
        const reductions = [_]schema.ReductionRegion{
            .{
                .axis = case.axis,
                .op = .sum,
                .contract = .{
                    .accumulation = .f32,
                    .associativity = .strict_ordered,
                    .nan_inf = .propagate,
                },
                .target_binding = 1,
            },
        };
        const func = schema.SemanticFunction{
            .name = "sum3d",
            .family_hint = .reduction,
            .axes = &axes,
            .bindings = &bindings,
            .reductions = &reductions,
            .collectives = &.{},
            .source_digest = [_]u8{0} ** 32,
        };
        const funcs = [_]schema.SemanticFunction{func};
        const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };

        var result = try run(allocator, semantic, realization, &inputs);
        defer freeResult(allocator, &result);
        try std.testing.expectEqual(@as(usize, 16), result.outputs[0].len);

        for (case.expected, 0..) |e, i| {
            const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
            const v: f32 = @bitCast(word);
            try std.testing.expectEqual(e, v);
        }
    }
}

test "2-D f32 sum reduces over axis 0 yielding per-column sums" {
    const allocator = std.testing.allocator;
    // Input [[1,2,3],[4,5,6]] shape [2,3]; axis 0 → [5,7,9] shape [3].
    const in_shape = [_]u64{ 2, 3 };
    const out_shape = [_]u64{3};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "j", .lower_bound = "0", .upper_bound = "3", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum_axis0",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [24]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0, 5.0, 6.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 12), result.outputs[0].len);

    const expected = [_]f32{ 5.0, 7.0, 9.0 };
    for (expected, 0..) |e, i| {
        const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(e, v);
    }
}

test "2-D f32 sum reduces over axis 1 yielding per-row sums" {
    const allocator = std.testing.allocator;
    // Same input; axis 1 → [6, 15] shape [2].
    const in_shape = [_]u64{ 2, 3 };
    const out_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "j", .lower_bound = "0", .upper_bound = "3", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum_axis1",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var input_bytes: [24]u8 = undefined;
    const vals = [_]f32{ 1.0, 2.0, 3.0, 4.0, 5.0, 6.0 };
    for (vals, 0..) |v, idx| {
        const word: u32 = @bitCast(v);
        std.mem.writeInt(u32, input_bytes[idx * 4 ..][0..4], word, .little);
    }
    const inputs = [_][]const u8{&input_bytes};

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 8), result.outputs[0].len);

    const expected = [_]f32{ 6.0, 15.0 };
    for (expected, 0..) |e, i| {
        const word = std.mem.readInt(u32, result.outputs[0][i * 4 ..][0..4], .little);
        const v: f32 = @bitCast(word);
        try std.testing.expectEqual(e, v);
    }
}

test "empty f32 reduction returns identity for each op" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{0};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "0", .step = "1" },
    };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const empty_bytes = [_]u8{};
    const inputs = [_][]const u8{&empty_bytes};

    const cases = [_]struct { op: schema.ReductionOp, expected: f32 }{
        .{ .op = .sum, .expected = 0.0 },
        .{ .op = .product, .expected = 1.0 },
        .{ .op = .min, .expected = std.math.inf(f32) },
        .{ .op = .max, .expected = -std.math.inf(f32) },
    };

    for (cases) |case| {
        const reductions = [_]schema.ReductionRegion{
            .{
                .axis = 0,
                .op = case.op,
                .contract = .{
                    .accumulation = .f32,
                    .associativity = .strict_ordered,
                    .nan_inf = .propagate,
                },
                .target_binding = 1,
            },
        };
        const func = schema.SemanticFunction{
            .name = "empty_reduce",
            .family_hint = .reduction,
            .axes = &axes,
            .bindings = &bindings,
            .reductions = &reductions,
            .collectives = &.{},
            .source_digest = [_]u8{0} ** 32,
        };
        const funcs = [_]schema.SemanticFunction{func};
        const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };

        var result = try run(allocator, semantic, realization, &inputs);
        defer freeResult(allocator, &result);

        const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
        const out_val: f32 = @bitCast(out_word);
        try std.testing.expectEqual(case.expected, out_val);
    }
}

test "simple reduction over empty input returns sum identity 0.0" {
    const allocator = std.testing.allocator;
    const in_shape = [_]u64{0};
    const out_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &in_shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &out_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "0", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .op = .sum,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "sum0",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const empty_bytes = [_]u8{};
    const inputs = [_][]const u8{&empty_bytes};
    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);
    const out_word = std.mem.readInt(u32, result.outputs[0][0..4], .little);
    const out_val: f32 = @bitCast(out_word);
    try std.testing.expectEqual(@as(f32, 0.0), out_val);
}

test "ReductionOp covers the four cases the interpreter must dispatch" {
    const ops = [_]schema.ReductionOp{ .sum, .product, .min, .max };
    try std.testing.expectEqual(@as(usize, 4), ops.len);
}

test "ReductionRegion defaults op to sum for backwards-compatible fixtures" {
    const region = schema.ReductionRegion{
        .axis = 0,
        .contract = .{
            .accumulation = .f32,
            .associativity = .strict_ordered,
            .nan_inf = .propagate,
        },
        .target_binding = 1,
    };
    try std.testing.expectEqual(schema.ReductionOp.sum, region.op);
}

test "ReductionRegion accepts explicit op override" {
    const region = schema.ReductionRegion{
        .axis = 1,
        .op = .max,
        .contract = .{
            .accumulation = .f32,
            .associativity = .associative_allowed,
            .nan_inf = .propagate,
        },
        .target_binding = 0,
    };
    try std.testing.expectEqual(schema.ReductionOp.max, region.op);
}

test "ScalarKind byte sizes match the declared numerical contract" {
    try std.testing.expectEqual(@as(u8, 4), schema.ScalarKind.f32.byteSize());
    try std.testing.expectEqual(@as(u8, 4), schema.ScalarKind.i32.byteSize());
    try std.testing.expectEqual(@as(u8, 4), schema.ScalarKind.u32.byteSize());
    try std.testing.expectEqual(@as(u8, 2), schema.ScalarKind.f16.byteSize());
    try std.testing.expectEqual(@as(u8, 2), schema.ScalarKind.bf16.byteSize());
}

test "identity refuses when reductions are present" {
    const allocator = std.testing.allocator;
    const shape = [_]u64{4};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "in", .group = 0, .binding = 0, .logical_shape = &shape, .elem = .f32, .read_write = false },
        .{ .name = "out", .group = 0, .binding = 1, .logical_shape = &shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "4", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 0,
            .contract = .{
                .accumulation = .f32,
                .associativity = .strict_ordered,
                .nan_inf = .propagate,
            },
            .target_binding = 1,
        },
    };
    const func = schema.SemanticFunction{
        .name = "reduce",
        .family_hint = .reduction,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const payload = [_]u8{0} ** 16;
    const inputs = [_][]const u8{&payload};
    const outcome = run(allocator, semantic, realization, &inputs);
    try std.testing.expectError(InterpretError.NotImplemented, outcome);
}
