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
// This file is still intentionally narrow. Unsupported paths return
// `NotImplemented` against the rejection taxonomy so callers see the
// gap precisely rather than a silent zero. Explicit semantic/realization
// rejections fail early with `RejectedBySemantic`. Executable bootstrap
// paths cover empty kernels, simple reductions, fused GEMV, gather, and
// byte-for-byte identity. Each path is guarded by strict TSIR shape checks
// so no backend gets an implicit semantic rescue.

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
    if (tryFusedGemv(allocator, semantic, realization, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (tryRmsNorm(allocator, semantic, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (tryGather(allocator, semantic, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (tryIdentity(allocator, semantic, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (tryResidualAdd(allocator, semantic, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (tryGated(allocator, semantic, inputs)) |maybe_result| {
        if (maybe_result) |result| return result;
    } else |err| return err;
    if (tryAttentionScores(allocator, semantic, inputs)) |maybe_result| {
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

/// Detect the fused_gemv bootstrap-family case and interpret it.
///
/// Shape this recognizer matches (strict; anything else falls through):
///   * one function, zero collectives
///   * exactly three bindings (matrix, vector, output) with declared
///     `SemanticBody` roles matching binding indices
///   * exactly two axes (output, reduction) with declared roles
///   * exactly one reduction region: sum, along the reduction axis,
///     target = the output binding, accumulation = f32,
///     associativity = strict_ordered, NaN/Inf = propagate
///   * matrix shape `[M, K]` row-major, vector shape `[K]`, output
///     shape `[M]`; element kinds across all three bindings are equal
///     and one of {f32, f16, bf16}
///
/// Computation: `y[i] = Σ_k  W[i, k] · x[k]` with a left-fold f32
/// accumulator over k (strict_ordered honors the byte-order sum). The
/// f32 output is then written back through the declared output dtype
/// via `writeF32AsElem`, which matches the trySimpleReduction path.
///
/// `associative_allowed` with a declared tree shape is explicitly out
/// of scope for this recognizer; it falls through so a future wedge
/// can add it without retrofitting the strict path.
fn tryFusedGemv(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    realization: schema.Realization,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.collectives.len != 0) return null;
    if (func.bindings.len != 3) return null;
    if (func.reductions.len != 1) return null;
    if (func.axes.len != 2) return null;

    // Body must declare the fused_gemv family with role assignments.
    if (func.body.op != .fused_gemv) return null;
    if (func.body.binding_roles.len != 3) return null;
    if (func.body.axis_roles.len != 2) return null;

    var matrix_index: ?u32 = null;
    var vector_index: ?u32 = null;
    var output_index: ?u32 = null;
    for (func.body.binding_roles) |role| {
        switch (role.role) {
            .matrix => {
                if (matrix_index != null) return null;
                matrix_index = role.binding_index;
            },
            .vector => {
                if (vector_index != null) return null;
                vector_index = role.binding_index;
            },
            .output => {
                if (output_index != null) return null;
                output_index = role.binding_index;
            },
            else => return null,
        }
    }
    const mi = matrix_index orelse return null;
    const vi = vector_index orelse return null;
    const oi = output_index orelse return null;
    if (mi >= func.bindings.len or vi >= func.bindings.len or oi >= func.bindings.len) return null;
    if (mi == vi or vi == oi or mi == oi) return null;

    var output_axis: ?u32 = null;
    var reduction_axis: ?u32 = null;
    for (func.body.axis_roles) |role| {
        switch (role.role) {
            .output => {
                if (output_axis != null) return null;
                output_axis = role.axis_index;
            },
            .reduction => {
                if (reduction_axis != null) return null;
                reduction_axis = role.axis_index;
            },
            else => return null,
        }
    }
    const out_axis = output_axis orelse return null;
    const red_axis = reduction_axis orelse return null;
    if (out_axis == red_axis) return null;
    if (out_axis >= func.axes.len or red_axis >= func.axes.len) return null;

    const reduction = func.reductions[0];
    if (reduction.op != .sum) return null;
    if (reduction.axis != red_axis) return null;
    if (reduction.target_binding != oi) return null;
    if (reduction.contract.accumulation != .f32) return null;

    // Associativity dispatch:
    //   strict_ordered     → left-fold is the only legal order.
    //   associative_allowed → tree shape is declared on the matching
    //                        Realization.ReductionRealizationNode. On a
    //                        single-PE reference, `.ring` is fold-order-
    //                        identical to `.linear`; `.binomial` is a
    //                        pairwise-tree fold that can differ bit-for-
    //                        bit from left-fold. Matches the
    //                        `trySimpleReduction` precedent. Falls
    //                        through when the realization does not
    //                        declare a matching reduction node.
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

    const mb = func.bindings[mi];
    const vb = func.bindings[vi];
    const ob = func.bindings[oi];

    // Dtype must match across all three bindings; one of the Phase A set.
    if (mb.elem != vb.elem or vb.elem != ob.elem) return null;
    if (mb.elem != .f32 and mb.elem != .f16 and mb.elem != .bf16) return null;

    // Shape guards: matrix [M, K], vector [K], output [M].
    if (mb.logical_shape.len != 2) return null;
    if (vb.logical_shape.len != 1) return null;
    if (ob.logical_shape.len != 1) return null;
    const m_u64 = mb.logical_shape[0];
    const k_u64 = mb.logical_shape[1];
    if (vb.logical_shape[0] != k_u64) return null;
    if (ob.logical_shape[0] != m_u64) return null;

    // Read/write flags: matrix + vector read-only, output read_write.
    if (mb.read_write or vb.read_write) return null;
    if (!ob.read_write) return null;

    const m: usize = std.math.cast(usize, m_u64) orelse return null;
    const k: usize = std.math.cast(usize, k_u64) orelse return null;

    // Phase A: matrix is row-major with axes [output, reduction]. The
    // axis-role declaration must agree with that layout; otherwise the
    // body doesn't describe the row-major W[M, K] this recognizer
    // assumes, and we fall through rather than silently reinterpret.
    if (out_axis != 0 or red_axis != 1) return null;

    // Inputs: [matrix_bytes, vector_bytes] in binding-index order of
    // the read-only bindings. The oracle contract is that the caller
    // orders inputs by ascending binding index of the read-only
    // bindings; with mi < vi that's matrix first, else vector first.
    if (inputs.len != 2) return null;
    const matrix_first = mi < vi;
    const matrix_bytes = if (matrix_first) inputs[0] else inputs[1];
    const vector_bytes = if (matrix_first) inputs[1] else inputs[0];

    const expected_matrix_bytes = computeExpectedBytes(mb) orelse return null;
    const expected_vector_bytes = computeExpectedBytes(vb) orelse return null;
    if (matrix_bytes.len != expected_matrix_bytes) return null;
    if (vector_bytes.len != expected_vector_bytes) return null;

    const out_elem_bytes: usize = ob.elem.byteSize();
    const output_bytes = try allocator.alloc(u8, m * out_elem_bytes);
    errdefer allocator.free(output_bytes);

    // Per-output scratch for binomial fold. Allocated once, reused
    // across output positions so the hot loop is alloc-free. Matches
    // the trySimpleReduction rank-2 pattern.
    var scratch: ?[]f32 = null;
    defer if (scratch) |s| allocator.free(s);
    if (effective_tree_shape == .binomial and k > 0) {
        scratch = try allocator.alloc(f32, k);
    }

    // Zero-K edge case: output is the reduction identity for sum (0.0)
    // written through the declared output dtype. Tree shape is
    // irrelevant when the axis is empty.
    if (k == 0) {
        var i: usize = 0;
        while (i < m) : (i += 1) writeF32AsElem(output_bytes, i, 0.0, ob.elem);
    } else {
        var i: usize = 0;
        while (i < m) : (i += 1) {
            switch (effective_tree_shape) {
                .linear, .ring => {
                    var acc: f32 = 0.0;
                    var kk: usize = 0;
                    while (kk < k) : (kk += 1) {
                        const w_val = readF32FromBytes(matrix_bytes, mb.elem, i * k + kk);
                        const x_val = readF32FromBytes(vector_bytes, vb.elem, kk);
                        acc += w_val * x_val;
                    }
                    writeF32AsElem(output_bytes, i, acc, ob.elem);
                },
                .binomial => {
                    // Materialize k products, then pairwise-fold. Result
                    // can differ from left-fold bit-for-bit on
                    // non-associative floating-point, which is exactly
                    // why `algorithm_exact` pins `tree_shape` as a
                    // declared invariant.
                    const vals = scratch.?;
                    var kk: usize = 0;
                    while (kk < k) : (kk += 1) {
                        const w_val = readF32FromBytes(matrix_bytes, mb.elem, i * k + kk);
                        const x_val = readF32FromBytes(vector_bytes, vb.elem, kk);
                        vals[kk] = w_val * x_val;
                    }
                    var count: usize = k;
                    while (count > 1) {
                        var new_count: usize = 0;
                        var idx: usize = 0;
                        while (idx < count) : (idx += 2) {
                            if (idx + 1 < count) {
                                vals[new_count] = vals[idx] + vals[idx + 1];
                            } else {
                                vals[new_count] = vals[idx];
                            }
                            new_count += 1;
                        }
                        count = new_count;
                    }
                    writeF32AsElem(output_bytes, i, vals[0], ob.elem);
                },
            }
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

/// Detect the RMSNorm bootstrap-family case and interpret it for explicit
/// epsilon contracts.
///
/// Shape this recognizer matches:
///   * one function, zero collectives
///   * at least three bindings with declared roles: input, scale, output
///   * exactly two axes with declared roles: hidden, reduction
///   * exactly one sum reduction over the reduction axis with f32
///     accumulation, strict ordering, and an intermediate scalar target
///   * equal `[H]` shapes and equal dtype over {f32, f16, bf16}
///   * `body.rmsNorm.epsilon.source` is either a literal f32 or a
///     uniform-field path with explicit binding index and byte offset.
fn tryRmsNorm(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.collectives.len != 0) return null;
    if (func.bindings.len < 3) return null;
    if (func.reductions.len != 1) return null;
    if (func.axes.len != 2) return null;

    if (func.body.op != .rms_norm) return null;
    const rms_norm = func.body.rms_norm orelse return null;
    if (rms_norm.formula != .sum_squares_mean_epsilon_rsqrt_scale) return null;
    if (rms_norm.reduction_target != .intermediate_scalar) return null;
    if (inputs.len != countReadOnlyBindings(func)) return null;
    const epsilon = resolveRmsNormEpsilon(func, inputs, rms_norm.epsilon) orelse return null;

    if (func.body.binding_roles.len != 3) return null;
    if (func.body.axis_roles.len != 2) return null;

    var input_index: ?u32 = null;
    var scale_index: ?u32 = null;
    var output_index: ?u32 = null;
    for (func.body.binding_roles) |role| {
        switch (role.role) {
            .input => {
                if (input_index != null) return null;
                input_index = role.binding_index;
            },
            .scale => {
                if (scale_index != null) return null;
                scale_index = role.binding_index;
            },
            .output => {
                if (output_index != null) return null;
                output_index = role.binding_index;
            },
            else => return null,
        }
    }
    const ii = input_index orelse return null;
    const si = scale_index orelse return null;
    const oi = output_index orelse return null;
    if (ii >= func.bindings.len or si >= func.bindings.len or oi >= func.bindings.len) return null;
    if (ii == si or si == oi or ii == oi) return null;

    var hidden_axis: ?u32 = null;
    var reduction_axis: ?u32 = null;
    for (func.body.axis_roles) |role| {
        switch (role.role) {
            .hidden => {
                if (hidden_axis != null) return null;
                hidden_axis = role.axis_index;
            },
            .reduction => {
                if (reduction_axis != null) return null;
                reduction_axis = role.axis_index;
            },
            else => return null,
        }
    }
    const hid_axis = hidden_axis orelse return null;
    const red_axis = reduction_axis orelse return null;
    if (hid_axis == red_axis) return null;
    if (hid_axis >= func.axes.len or red_axis >= func.axes.len) return null;
    if (rms_norm.hidden_extent_axis != hid_axis) return null;
    if (hid_axis != 0 or red_axis != 1) return null;

    const reduction = func.reductions[0];
    if (reduction.op != .sum) return null;
    if (reduction.axis != red_axis) return null;
    if (reduction.contract.accumulation != .f32) return null;
    if (reduction.contract.associativity != .strict_ordered) return null;
    if (reduction.contract.nan_inf != .propagate) return null;

    const ib = func.bindings[ii];
    const sb = func.bindings[si];
    const ob = func.bindings[oi];
    if (ib.read_write or sb.read_write) return null;
    if (!ob.read_write) return null;
    if (ib.elem != sb.elem or sb.elem != ob.elem) return null;
    if (ib.elem != .f32 and ib.elem != .f16 and ib.elem != .bf16) return null;
    if (ib.logical_shape.len != 1) return null;
    if (sb.logical_shape.len != 1) return null;
    if (ob.logical_shape.len != 1) return null;

    const hidden_u64 = ib.logical_shape[0];
    if (sb.logical_shape[0] != hidden_u64) return null;
    if (ob.logical_shape[0] != hidden_u64) return null;
    const hidden: usize = std.math.cast(usize, hidden_u64) orelse return null;

    const input_bytes = inputBytesForReadOnlyBinding(func, inputs, ii) orelse return null;
    const scale_bytes = inputBytesForReadOnlyBinding(func, inputs, si) orelse return null;
    const expected_input_bytes = computeExpectedBytes(ib) orelse return null;
    const expected_scale_bytes = computeExpectedBytes(sb) orelse return null;
    if (input_bytes.len != expected_input_bytes) return null;
    if (scale_bytes.len != expected_scale_bytes) return null;

    const expected_output_bytes = computeExpectedBytes(ob) orelse return null;
    const output_len = std.math.cast(usize, expected_output_bytes) orelse return null;
    const output_bytes = try allocator.alloc(u8, output_len);
    errdefer allocator.free(output_bytes);

    if (hidden != 0) {
        var sum_sq: f32 = 0.0;
        var r: usize = 0;
        while (r < hidden) : (r += 1) {
            const x = readF32FromBytes(input_bytes, ib.elem, r);
            sum_sq += x * x;
        }
        const mean_sq = sum_sq / @as(f32, @floatFromInt(hidden));
        const inv_rms = 1.0 / @sqrt(mean_sq + epsilon);

        var d: usize = 0;
        while (d < hidden) : (d += 1) {
            const x = readF32FromBytes(input_bytes, ib.elem, d);
            const scale = readF32FromBytes(scale_bytes, sb.elem, d);
            writeF32AsElem(output_bytes, d, x * inv_rms * scale, ob.elem);
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

fn resolveRmsNormEpsilon(
    func: schema.SemanticFunction,
    inputs: []const []const u8,
    epsilon: schema.RmsNormEpsilon,
) ?f32 {
    return switch (epsilon.source) {
        .literal_f32 => blk: {
            if (epsilon.path.len != 0) return null;
            if (epsilon.binding_index != null or epsilon.byte_offset != null) return null;
            const epsilon_f64 = epsilon.literal_f32 orelse return null;
            if (std.math.isNan(epsilon_f64) or std.math.isInf(epsilon_f64)) return null;
            break :blk @floatCast(epsilon_f64);
        },
        .uniform_field => blk: {
            const path = splitUniformFieldPath(epsilon.path) orelse return null;
            if (!std.mem.eql(u8, path.field_name, "eps")) return null;
            if (epsilon.literal_f32 != null) return null;
            const binding_index = epsilon.binding_index orelse return null;
            const byte_offset_u32 = epsilon.byte_offset orelse return null;
            const binding_idx: usize = std.math.cast(usize, binding_index) orelse return null;
            if (binding_idx >= func.bindings.len) return null;
            if (func.bindings[binding_idx].read_write) return null;
            if (!std.mem.eql(u8, path.binding_name, func.bindings[binding_idx].name)) return null;
            const uniform_bytes = inputBytesForReadOnlyBinding(
                func,
                inputs,
                binding_index,
            ) orelse return null;
            const byte_offset: usize = std.math.cast(usize, byte_offset_u32) orelse return null;
            if (byte_offset > uniform_bytes.len) return null;
            if (uniform_bytes.len - byte_offset < 4) return null;
            const bits = std.mem.readInt(u32, uniform_bytes[byte_offset..][0..4], .little);
            const value: f32 = @bitCast(bits);
            if (std.math.isNan(value) or std.math.isInf(value)) return null;
            break :blk value;
        },
    };
}

const UniformFieldPath = struct {
    binding_name: []const u8,
    field_name: []const u8,
};

fn splitUniformFieldPath(path: []const u8) ?UniformFieldPath {
    const prefix = "uniform:";
    if (!std.mem.startsWith(u8, path, prefix)) return null;
    const rest = path[prefix.len..];
    const dot = std.mem.indexOfScalar(u8, rest, '.') orelse return null;
    if (dot == 0 or dot + 1 >= rest.len) return null;
    return .{
        .binding_name = rest[0..dot],
        .field_name = rest[dot + 1 ..],
    };
}

fn countReadOnlyBindings(func: schema.SemanticFunction) usize {
    var count: usize = 0;
    for (func.bindings) |binding| {
        if (!binding.read_write) count += 1;
    }
    return count;
}

fn inputBytesForReadOnlyBinding(
    func: schema.SemanticFunction,
    inputs: []const []const u8,
    binding_index: u32,
) ?[]const u8 {
    const idx: usize = std.math.cast(usize, binding_index) orelse return null;
    if (idx >= func.bindings.len) return null;
    if (func.bindings[idx].read_write) return null;
    var input_slot: usize = 0;
    for (func.bindings[0..idx]) |binding| {
        if (!binding.read_write) input_slot += 1;
    }
    if (input_slot >= inputs.len) return null;
    return inputs[input_slot];
}

/// Detect the gather bootstrap-family case and interpret it.
///
/// Shape this recognizer matches:
///   * one function, zero reductions, zero collectives
///   * exactly three bindings with declared roles: indices, table, output
///   * exactly two axes with declared roles: token, hidden
///   * indices shape `[T]` with `u32` elements
///   * table shape `[V, H]`, output shape `[T, H]`
///   * table/output dtype equal and one of {f32, f16, bf16}
///
/// Computation copies `table[indices[t], h]` to `output[t, h]` in row-major
/// element order. Index bounds are dynamic input facts rather than static
/// TSIR shape facts; an out-of-vocabulary index falls through so the caller
/// sees `NotImplemented` instead of a wrapped or clamped result.
fn tryGather(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.collectives.len != 0) return null;
    if (func.reductions.len != 0) return null;
    if (func.bindings.len != 3) return null;
    if (func.axes.len != 2) return null;

    if (func.body.op != .gather) return null;
    if (func.body.binding_roles.len != 3) return null;
    if (func.body.axis_roles.len != 2) return null;

    var indices_index: ?u32 = null;
    var table_index: ?u32 = null;
    var output_index: ?u32 = null;
    for (func.body.binding_roles) |role| {
        switch (role.role) {
            .indices => {
                if (indices_index != null) return null;
                indices_index = role.binding_index;
            },
            .table => {
                if (table_index != null) return null;
                table_index = role.binding_index;
            },
            .output => {
                if (output_index != null) return null;
                output_index = role.binding_index;
            },
            else => return null,
        }
    }
    const ii = indices_index orelse return null;
    const ti = table_index orelse return null;
    const oi = output_index orelse return null;
    if (ii >= func.bindings.len or ti >= func.bindings.len or oi >= func.bindings.len) return null;
    if (ii == ti or ti == oi or ii == oi) return null;

    var token_axis: ?u32 = null;
    var hidden_axis: ?u32 = null;
    for (func.body.axis_roles) |role| {
        switch (role.role) {
            .token => {
                if (token_axis != null) return null;
                token_axis = role.axis_index;
            },
            .hidden => {
                if (hidden_axis != null) return null;
                hidden_axis = role.axis_index;
            },
            else => return null,
        }
    }
    const tok_axis = token_axis orelse return null;
    const hid_axis = hidden_axis orelse return null;
    if (tok_axis == hid_axis) return null;
    if (tok_axis >= func.axes.len or hid_axis >= func.axes.len) return null;
    if (tok_axis != 0 or hid_axis != 1) return null;

    const ib = func.bindings[ii];
    const tb = func.bindings[ti];
    const ob = func.bindings[oi];

    if (ib.read_write or tb.read_write) return null;
    if (!ob.read_write) return null;
    if (ib.elem != .u32) return null;
    if (tb.elem != ob.elem) return null;
    if (tb.elem != .f32 and tb.elem != .f16 and tb.elem != .bf16) return null;

    if (ib.logical_shape.len != 1) return null;
    if (tb.logical_shape.len != 2) return null;
    if (ob.logical_shape.len != 2) return null;

    const tokens_u64 = ib.logical_shape[0];
    const vocab_u64 = tb.logical_shape[0];
    const hidden_u64 = tb.logical_shape[1];
    if (ob.logical_shape[0] != tokens_u64) return null;
    if (ob.logical_shape[1] != hidden_u64) return null;

    const tokens: usize = std.math.cast(usize, tokens_u64) orelse return null;
    const vocab: usize = std.math.cast(usize, vocab_u64) orelse return null;
    const hidden: usize = std.math.cast(usize, hidden_u64) orelse return null;

    if (inputs.len != 2) return null;
    const indices_first = ii < ti;
    const indices_bytes = if (indices_first) inputs[0] else inputs[1];
    const table_bytes = if (indices_first) inputs[1] else inputs[0];

    const expected_indices_bytes = computeExpectedBytes(ib) orelse return null;
    const expected_table_bytes = computeExpectedBytes(tb) orelse return null;
    if (indices_bytes.len != expected_indices_bytes) return null;
    if (table_bytes.len != expected_table_bytes) return null;

    var validate_t: usize = 0;
    while (validate_t < tokens) : (validate_t += 1) {
        const index_off = std.math.mul(usize, validate_t, 4) catch return null;
        const row_u32 = std.mem.readInt(u32, indices_bytes[index_off..][0..4], .little);
        const row: usize = std.math.cast(usize, row_u32) orelse return null;
        if (row >= vocab) return null;
    }

    const expected_output_bytes = computeExpectedBytes(ob) orelse return null;
    const output_len = std.math.cast(usize, expected_output_bytes) orelse return null;
    const output_bytes = try allocator.alloc(u8, output_len);
    errdefer allocator.free(output_bytes);

    const elem_bytes: usize = ob.elem.byteSize();
    var t: usize = 0;
    while (t < tokens) : (t += 1) {
        const index_off = std.math.mul(usize, t, 4) catch unreachable;
        const row_u32 = std.mem.readInt(u32, indices_bytes[index_off..][0..4], .little);
        const row: usize = std.math.cast(usize, row_u32) orelse unreachable;
        const table_row = std.math.mul(usize, row, hidden) catch unreachable;
        const output_row = std.math.mul(usize, t, hidden) catch unreachable;

        var h: usize = 0;
        while (h < hidden) : (h += 1) {
            const table_elem = std.math.add(usize, table_row, h) catch unreachable;
            const output_elem = std.math.add(usize, output_row, h) catch unreachable;
            const table_off = std.math.mul(usize, table_elem, elem_bytes) catch unreachable;
            const output_off = std.math.mul(usize, output_elem, elem_bytes) catch unreachable;
            @memcpy(output_bytes[output_off..][0..elem_bytes], table_bytes[table_off..][0..elem_bytes]);
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

/// Detect and interpret the residual-add bootstrap-family case:
///   `output[i] = summand_a[i] + summand_b[i]` over a single hidden
///   axis. Shape this recognizer matches:
///   * one function, zero reductions, zero collectives, one axis
///   * exactly three bindings with declared roles:
///     `summand_a`, `summand_b`, `output`
///   * axis role is `hidden`
///   * `f32` element type across all three bindings (matches the live
///     emit_csl_semantic_ops.emitResidualPe wrapper)
///   * one-dimensional `logical_shape` matching across the three bindings
fn tryResidualAdd(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.collectives.len != 0) return null;
    if (func.reductions.len != 0) return null;
    if (func.bindings.len != 3) return null;
    if (func.axes.len != 1) return null;
    if (func.body.op != .residual_add) return null;
    if (func.body.binding_roles.len != 3) return null;
    if (func.body.axis_roles.len != 1) return null;

    if (func.body.axis_roles[0].role != .hidden) return null;

    var a_index: ?u32 = null;
    var b_index: ?u32 = null;
    var output_index: ?u32 = null;
    for (func.body.binding_roles) |role| {
        switch (role.role) {
            .summand_a => {
                if (a_index != null) return null;
                a_index = role.binding_index;
            },
            .summand_b => {
                if (b_index != null) return null;
                b_index = role.binding_index;
            },
            .output => {
                if (output_index != null) return null;
                output_index = role.binding_index;
            },
            else => return null,
        }
    }
    const ai = a_index orelse return null;
    const bi = b_index orelse return null;
    const oi = output_index orelse return null;
    if (ai >= func.bindings.len or bi >= func.bindings.len or oi >= func.bindings.len) return null;
    if (ai == bi or bi == oi or ai == oi) return null;

    const ab = func.bindings[ai];
    const bb = func.bindings[bi];
    const ob = func.bindings[oi];
    if (ab.read_write or bb.read_write) return null;
    if (!ob.read_write) return null;
    if (ab.elem != .f32 or bb.elem != .f32 or ob.elem != .f32) return null;
    if (ab.logical_shape.len != 1 or bb.logical_shape.len != 1 or ob.logical_shape.len != 1) return null;

    const len_u64 = ab.logical_shape[0];
    if (bb.logical_shape[0] != len_u64) return null;
    if (ob.logical_shape[0] != len_u64) return null;
    const len: usize = std.math.cast(usize, len_u64) orelse return null;

    if (inputs.len != countReadOnlyBindings(func)) return null;
    const a_bytes = inputBytesForReadOnlyBinding(func, inputs, ai) orelse return null;
    const b_bytes = inputBytesForReadOnlyBinding(func, inputs, bi) orelse return null;
    const expected_input_bytes = computeExpectedBytes(ab) orelse return null;
    if (a_bytes.len != expected_input_bytes) return null;
    if (b_bytes.len != expected_input_bytes) return null;

    const expected_output_bytes = computeExpectedBytes(ob) orelse return null;
    const output_len = std.math.cast(usize, expected_output_bytes) orelse return null;
    const output_bytes = try allocator.alloc(u8, output_len);
    errdefer allocator.free(output_bytes);

    var i: usize = 0;
    while (i < len) : (i += 1) {
        const a = readF32FromBytes(a_bytes, ab.elem, i);
        const b = readF32FromBytes(b_bytes, bb.elem, i);
        writeF32AsElem(output_bytes, i, a + b, ob.elem);
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

/// Detect and interpret the gated-activation family
/// (`gelu_gated`, `silu_gated`, `sigmoid_gated`):
///   `output[i] = act(gate[i]) * input[i]` where `act` is one of:
///     gelu    : tanh-approximation form Doppler's MLP block emits
///       inner = clamp(GELU_A * (x + GELU_B * x³), -15, 15)
///       gelu(x) = 0.5 * x * (1 + tanh(inner))
///       with `GELU_A = sqrt(2/π)` and `GELU_B = 0.044715`
///     silu    : `silu(x) = x / (1 + exp(z))` with `z = clamp(-x, -15, 15)`
///     sigmoid : `sigmoid(x) = 1 / (1 + exp(z))` with `z = clamp(-x, -15, 15)`
///   The clamps match the live emit body in
///   `emit_kernel_body_gated.zig` so the interpreter mirrors live
///   numerical behavior (algorithm-exact).
///
/// Shape this recognizer matches:
///   * one function, zero reductions, zero collectives, one axis
///   * exactly three bindings with declared roles: `gate`, `input`,
///     `output`
///   * axis role is `hidden`
///   * `f32` element type across all three bindings
///   * one-dimensional `logical_shape` matching across the three bindings
fn tryGated(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.collectives.len != 0) return null;
    if (func.reductions.len != 0) return null;
    if (func.bindings.len != 3) return null;
    if (func.axes.len != 1) return null;
    const gated_kind: enum { gelu, silu, sigmoid } = switch (func.body.op) {
        .gelu_gated => .gelu,
        .silu_gated => .silu,
        .sigmoid_gated => .sigmoid,
        else => return null,
    };
    if (func.body.binding_roles.len != 3) return null;
    if (func.body.axis_roles.len != 1) return null;

    if (func.body.axis_roles[0].role != .hidden) return null;

    var gate_index: ?u32 = null;
    var input_index: ?u32 = null;
    var output_index: ?u32 = null;
    for (func.body.binding_roles) |role| {
        switch (role.role) {
            .gate => {
                if (gate_index != null) return null;
                gate_index = role.binding_index;
            },
            .input => {
                if (input_index != null) return null;
                input_index = role.binding_index;
            },
            .output => {
                if (output_index != null) return null;
                output_index = role.binding_index;
            },
            else => return null,
        }
    }
    const gi = gate_index orelse return null;
    const ii = input_index orelse return null;
    const oi = output_index orelse return null;
    if (gi >= func.bindings.len or ii >= func.bindings.len or oi >= func.bindings.len) return null;
    if (gi == ii or ii == oi or gi == oi) return null;

    const gb = func.bindings[gi];
    const ib = func.bindings[ii];
    const ob = func.bindings[oi];
    if (gb.read_write or ib.read_write) return null;
    if (!ob.read_write) return null;
    if (gb.elem != .f32 or ib.elem != .f32 or ob.elem != .f32) return null;
    if (gb.logical_shape.len != 1 or ib.logical_shape.len != 1 or ob.logical_shape.len != 1) return null;

    const len_u64 = gb.logical_shape[0];
    if (ib.logical_shape[0] != len_u64) return null;
    if (ob.logical_shape[0] != len_u64) return null;
    const len: usize = std.math.cast(usize, len_u64) orelse return null;

    if (inputs.len != countReadOnlyBindings(func)) return null;
    const gate_bytes = inputBytesForReadOnlyBinding(func, inputs, gi) orelse return null;
    const input_bytes = inputBytesForReadOnlyBinding(func, inputs, ii) orelse return null;
    const expected_input_bytes = computeExpectedBytes(gb) orelse return null;
    if (gate_bytes.len != expected_input_bytes) return null;
    if (input_bytes.len != expected_input_bytes) return null;

    const expected_output_bytes = computeExpectedBytes(ob) orelse return null;
    const output_len = std.math.cast(usize, expected_output_bytes) orelse return null;
    const output_bytes = try allocator.alloc(u8, output_len);
    errdefer allocator.free(output_bytes);

    const gelu_a: f32 = 0.7978845608028654;
    const gelu_b: f32 = 0.044715;

    var i: usize = 0;
    while (i < len) : (i += 1) {
        const x = readF32FromBytes(gate_bytes, gb.elem, i);
        const v = readF32FromBytes(input_bytes, ib.elem, i);
        const act_x: f32 = switch (gated_kind) {
            .gelu => blk: {
                var inner = gelu_a * (x + gelu_b * x * x * x);
                if (inner < -15.0) inner = -15.0;
                if (inner > 15.0) inner = 15.0;
                break :blk 0.5 * x * (1.0 + std.math.tanh(inner));
            },
            .silu => blk: {
                var z = -x;
                if (z < -15.0) z = -15.0;
                if (z > 15.0) z = 15.0;
                break :blk x / (1.0 + std.math.exp(z));
            },
            .sigmoid => blk: {
                var z = -x;
                if (z < -15.0) z = -15.0;
                if (z > 15.0) z = 15.0;
                break :blk 1.0 / (1.0 + std.math.exp(z));
            },
        };
        writeF32AsElem(output_bytes, i, act_x * v, ob.elem);
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

/// Detect and interpret the `attention_scores` body op.
///
/// Mirrors the CSL emit body in `emit_kernel_body_attention.zig`. Same
/// scope: bootstrap-canary surface only:
///   * softmax_mode = .two_pass_stable
///   * causal_mode  = .none
///   * has_softcap  = false
///   * scale_source = .literal_f32
///   * Q / K / V / output bindings declared via SemanticBindingRole
///   * f32 element type on every binding
///
/// The math follows the same two-pass-stable softmax form the emit body
/// produces:
///   scores[k]  = (sum_d Q[d] * K[k, d]) * scale
///   m          = max_k scores[k]
///   weights[k] = exp(scores[k] - m); sum_e = sum_k weights[k]
///   O[d]       = sum_k V[k, d] * (weights[k] / sum_e)
///
/// This makes the canary's CSL hash comparable to a Zig-side numerical
/// reference for non-zero Q/K/V inputs, lifting the bootstrap-fixture
/// constraint that real attention closure required all-zero inputs.
fn tryAttentionScores(
    allocator: std.mem.Allocator,
    semantic: schema.Semantic,
    inputs: []const []const u8,
) InterpretError!?Result {
    if (semantic.functions.len != 1) return null;
    const func = semantic.functions[0];
    if (func.collectives.len != 0) return null;
    if (func.body.op != .attention_scores) return null;
    const attn = func.body.attention_scores orelse return null;
    if (attn.softmax_mode != .two_pass_stable) return null;
    if (attn.causal_mode != .none) return null;
    if (attn.has_softcap) return null;
    if (attn.scale_source != .literal_f32) return null;
    const scale_f64 = attn.scale_literal_f32 orelse return null;
    const scale: f32 = @floatCast(scale_f64);

    if (inputs.len != countReadOnlyBindings(func)) return null;

    var query_index: ?u32 = null;
    var key_index: ?u32 = null;
    var value_index: ?u32 = null;
    var output_index: ?u32 = null;
    for (func.body.binding_roles) |role| {
        switch (role.role) {
            .query => {
                if (query_index != null) return null;
                query_index = role.binding_index;
            },
            .key => {
                if (key_index != null) return null;
                key_index = role.binding_index;
            },
            .value => {
                if (value_index != null) return null;
                value_index = role.binding_index;
            },
            .output => {
                if (output_index != null) return null;
                output_index = role.binding_index;
            },
            // Optional bindings (kv_len_buffer / page_table) are tolerated
            // here; the bootstrap-canary surface ignores them and lets
            // shapes drive kv_len.
            .kv_len_buffer, .page_table => {},
            else => return null,
        }
    }
    const qi = query_index orelse return null;
    const ki = key_index orelse return null;
    const vi = value_index orelse return null;
    const oi = output_index orelse return null;
    if (qi >= func.bindings.len or ki >= func.bindings.len or
        vi >= func.bindings.len or oi >= func.bindings.len) return null;

    const qb = func.bindings[qi];
    const kb = func.bindings[ki];
    const vb = func.bindings[vi];
    const ob = func.bindings[oi];
    if (qb.read_write or kb.read_write or vb.read_write) return null;
    if (!ob.read_write) return null;
    if (qb.elem != .f32 or kb.elem != .f32 or vb.elem != .f32 or ob.elem != .f32) return null;

    const head_dim_u32 = attn.head_dim;
    if (head_dim_u32 == 0) return null;
    const head_dim: usize = head_dim_u32;

    // Q is [head_dim]; K/V are [kv_len * head_dim]; O is [head_dim].
    if (qb.logical_shape.len != 1) return null;
    if (qb.logical_shape[0] != head_dim_u32) return null;
    if (ob.logical_shape.len != 1) return null;
    if (ob.logical_shape[0] != head_dim_u32) return null;
    if (kb.logical_shape.len < 1) return null;
    var k_total: u64 = 1;
    for (kb.logical_shape) |dim| k_total *= dim;
    if (k_total == 0 or k_total % head_dim_u32 != 0) return null;
    const kv_len_u64 = k_total / head_dim_u32;
    var v_total: u64 = 1;
    for (vb.logical_shape) |dim| v_total *= dim;
    if (v_total != k_total) return null;
    const kv_len: usize = std.math.cast(usize, kv_len_u64) orelse return null;
    if (kv_len == 0) return null;

    const q_bytes = inputBytesForReadOnlyBinding(func, inputs, qi) orelse return null;
    const k_bytes = inputBytesForReadOnlyBinding(func, inputs, ki) orelse return null;
    const v_bytes = inputBytesForReadOnlyBinding(func, inputs, vi) orelse return null;
    if (q_bytes.len != head_dim * 4) return null;
    if (k_bytes.len != kv_len * head_dim * 4) return null;
    if (v_bytes.len != kv_len * head_dim * 4) return null;

    const output_len = head_dim * 4;
    const output_bytes = try allocator.alloc(u8, output_len);
    errdefer allocator.free(output_bytes);

    var scores = try allocator.alloc(f32, kv_len);
    defer allocator.free(scores);

    // Pass 1: scores[k] = (Q · K[k]) * scale; track max.
    var max_score: f32 = -std.math.inf(f32);
    {
        var k: usize = 0;
        while (k < kv_len) : (k += 1) {
            var dot: f32 = 0.0;
            var d: usize = 0;
            while (d < head_dim) : (d += 1) {
                const q_val = readF32FromBytes(q_bytes, .f32, d);
                const k_val = readF32FromBytes(k_bytes, .f32, k * head_dim + d);
                dot += q_val * k_val;
            }
            const sc = dot * scale;
            scores[k] = sc;
            if (sc > max_score) max_score = sc;
        }
    }

    // Pass 2: weights[k] = exp(scores[k] - max); sum.
    var sum_exp: f32 = 0.0;
    {
        var k: usize = 0;
        while (k < kv_len) : (k += 1) {
            const e = @exp(scores[k] - max_score);
            scores[k] = e;
            sum_exp += e;
        }
    }
    if (sum_exp == 0.0) return null;

    // Output: O[d] = sum_k V[k, d] * (weights[k] / sum_exp).
    {
        var d: usize = 0;
        while (d < head_dim) : (d += 1) {
            var acc: f32 = 0.0;
            var k: usize = 0;
            while (k < kv_len) : (k += 1) {
                const v_val = readF32FromBytes(v_bytes, .f32, k * head_dim + d);
                acc += v_val * (scores[k] / sum_exp);
            }
            writeF32AsElem(output_bytes, d, acc, .f32);
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

/// Detect and interpret simple one-binding reductions. Phase A coverage:
///   * 2 bindings (one read-only input, one read-write output).
///   * 1 reduction with `f32` accumulation; `sum`, `product`, `min`, or
///     `max` op; `NaN/Inf = propagate`.
///   * Associativity: `strict_ordered` (left-fold) or
///     `associative_allowed` (tree shape from the matching
///     Realization reduction node; `.linear` / `.ring` single-PE-
///     identical, `.binomial` pairwise).
///   * Ranks 1, 2, 3, and 4+ (generic N-D fallback). Binomial fold is
///     supported for ranks 1, 2, 3; rank 4+ rejects binomial and
///     returns null so the caller can emit `NotImplemented`.
///   * Input dtypes `{f32, f16, bf16}` via upcast to f32; output dtypes
///     `{f32, f16, bf16}` via downcast from the f32 accumulator.
///
/// Anything outside this envelope falls through to `NotImplemented` so
/// the oracle never silently honors a reduction class it has not yet
/// implemented.
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
    //                        supported for ranks 1–3; rank 4+ rejects
    //                        binomial and falls through.
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
        // softmax_stable is a compound (max-then-sum-exp) op; it does
        // not have a left-fold identity and must not be dispatched
        // through the scalar simple-fold helpers. Attention semantic
        // evaluation happens outside this path.
        .softmax_stable => unreachable,
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
        // See `reductionIdentityF32` — softmax_stable is handled
        // outside the scalar simple-fold path.
        .softmax_stable => unreachable,
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

test "fused_gemv f32 strict_ordered computes y[i] = sum_k W[i,k] * x[k]" {
    const allocator = std.testing.allocator;
    const matrix_shape = [_]u64{ 2, 3 };
    const vector_shape = [_]u64{3};
    const output_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "W", .group = 0, .binding = 0, .logical_shape = &matrix_shape, .elem = .f32, .read_write = false },
        .{ .name = "x", .group = 0, .binding = 1, .logical_shape = &vector_shape, .elem = .f32, .read_write = false },
        .{ .name = "y", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "k", .lower_bound = "0", .upper_bound = "3", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .matrix },
        .{ .binding_index = 1, .role = .vector },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .output },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .fused_gemv,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gemv",
        .family_hint = .fused_gemv,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // W = [[1,2,3],[4,5,6]] row-major; x = [10,100,1000].
    var matrix_bytes: [24]u8 = undefined;
    writeF32AsElem(&matrix_bytes, 0, 1.0, .f32);
    writeF32AsElem(&matrix_bytes, 1, 2.0, .f32);
    writeF32AsElem(&matrix_bytes, 2, 3.0, .f32);
    writeF32AsElem(&matrix_bytes, 3, 4.0, .f32);
    writeF32AsElem(&matrix_bytes, 4, 5.0, .f32);
    writeF32AsElem(&matrix_bytes, 5, 6.0, .f32);
    var vector_bytes: [12]u8 = undefined;
    writeF32AsElem(&vector_bytes, 0, 10.0, .f32);
    writeF32AsElem(&vector_bytes, 1, 100.0, .f32);
    writeF32AsElem(&vector_bytes, 2, 1000.0, .f32);
    // Inputs are ordered by ascending read-only binding index: matrix (0), vector (1).
    const inputs = [_][]const u8{ &matrix_bytes, &vector_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 8), result.outputs[0].len);

    const y0 = readF32FromBytes(result.outputs[0], .f32, 0);
    const y1 = readF32FromBytes(result.outputs[0], .f32, 1);
    try std.testing.expectEqual(@as(f32, 3210.0), y0);
    try std.testing.expectEqual(@as(f32, 6540.0), y1);

    // Reference hash is SHA-256 of the output bytes verbatim.
    var expected: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(result.outputs[0], &expected, .{});
    try std.testing.expectEqualSlices(u8, &expected, &result.reference_hash);
}

test "fused_gemv associative_allowed consumes realization tree shape" {
    const allocator = std.testing.allocator;
    const matrix_shape = [_]u64{ 1, 4 };
    const vector_shape = [_]u64{4};
    const output_shape = [_]u64{1};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "W", .group = 0, .binding = 0, .logical_shape = &matrix_shape, .elem = .f32, .read_write = false },
        .{ .name = "x", .group = 0, .binding = 1, .logical_shape = &vector_shape, .elem = .f32, .read_write = false },
        .{ .name = "y", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "1", .step = "1" },
        .{ .name = "k", .lower_bound = "0", .upper_bound = "4", .step = "1" },
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
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .matrix },
        .{ .binding_index = 1, .role = .vector },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .output },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .fused_gemv,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gemv_assoc",
        .family_hint = .fused_gemv,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };

    var matrix_bytes: [16]u8 = undefined;
    writeF32AsElem(&matrix_bytes, 0, 1.0e20, .f32);
    writeF32AsElem(&matrix_bytes, 1, 3.0, .f32);
    writeF32AsElem(&matrix_bytes, 2, -1.0e20, .f32);
    writeF32AsElem(&matrix_bytes, 3, 4.0, .f32);
    var vector_bytes: [16]u8 = undefined;
    writeF32AsElem(&vector_bytes, 0, 1.0, .f32);
    writeF32AsElem(&vector_bytes, 1, 1.0, .f32);
    writeF32AsElem(&vector_bytes, 2, 1.0, .f32);
    writeF32AsElem(&vector_bytes, 3, 1.0, .f32);
    const inputs = [_][]const u8{ &matrix_bytes, &vector_bytes };

    const missing_realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    try std.testing.expectError(
        InterpretError.NotImplemented,
        run(allocator, semantic, missing_realization, &inputs),
    );

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
    const binomial_realization = schema.Realization{
        .functions = &rfuncs,
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var result = try run(allocator, semantic, binomial_realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(f32, 0.0), readF32FromBytes(result.outputs[0], .f32, 0));
}

test "fused_gemv recognizer falls through on wrong body op" {
    const allocator = std.testing.allocator;
    const matrix_shape = [_]u64{ 2, 3 };
    const vector_shape = [_]u64{3};
    const output_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "W", .group = 0, .binding = 0, .logical_shape = &matrix_shape, .elem = .f32, .read_write = false },
        .{ .name = "x", .group = 0, .binding = 1, .logical_shape = &vector_shape, .elem = .f32, .read_write = false },
        .{ .name = "y", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "k", .lower_bound = "0", .upper_bound = "3", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    // Body op left at `.unknown`; fused_gemv recognizer must fall
    // through, and no other dispatch path matches a 3-binding kernel,
    // so `run` returns NotImplemented rather than silently honoring an
    // undeclared body.
    const func = schema.SemanticFunction{
        .name = "gemv_unlabeled",
        .family_hint = .fused_gemv,
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

    const matrix_bytes = [_]u8{0} ** 24;
    const vector_bytes = [_]u8{0} ** 12;
    const inputs = [_][]const u8{ &matrix_bytes, &vector_bytes };
    const outcome = run(allocator, semantic, realization, &inputs);
    try std.testing.expectError(InterpretError.NotImplemented, outcome);
}

test "gather f32 copies table rows selected by u32 token indices" {
    const allocator = std.testing.allocator;
    const index_shape = [_]u64{3};
    const table_shape = [_]u64{ 4, 2 };
    const output_shape = [_]u64{ 3, 2 };
    const bindings = [_]schema.BufferBinding{
        .{ .name = "indices", .group = 0, .binding = 0, .logical_shape = &index_shape, .elem = .u32, .read_write = false },
        .{ .name = "table", .group = 0, .binding = 1, .logical_shape = &table_shape, .elem = .f32, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "t", .lower_bound = "0", .upper_bound = "3", .step = "1" },
        .{ .name = "h", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .indices },
        .{ .binding_index = 1, .role = .table },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .token },
        .{ .axis_index = 1, .role = .hidden },
    };
    const body = schema.SemanticBody{
        .op = .gather,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gather",
        .family_hint = .gather,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var indices_bytes: [12]u8 = undefined;
    std.mem.writeInt(u32, indices_bytes[0..4], 2, .little);
    std.mem.writeInt(u32, indices_bytes[4..8], 0, .little);
    std.mem.writeInt(u32, indices_bytes[8..12], 3, .little);

    var table_bytes: [32]u8 = undefined;
    writeF32AsElem(&table_bytes, 0, 10.0, .f32);
    writeF32AsElem(&table_bytes, 1, 11.0, .f32);
    writeF32AsElem(&table_bytes, 2, 20.0, .f32);
    writeF32AsElem(&table_bytes, 3, 21.0, .f32);
    writeF32AsElem(&table_bytes, 4, 30.0, .f32);
    writeF32AsElem(&table_bytes, 5, 31.0, .f32);
    writeF32AsElem(&table_bytes, 6, 40.0, .f32);
    writeF32AsElem(&table_bytes, 7, 41.0, .f32);

    const inputs = [_][]const u8{ &indices_bytes, &table_bytes };
    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 24), result.outputs[0].len);
    const expected = [_]f32{ 30.0, 31.0, 10.0, 11.0, 40.0, 41.0 };
    for (expected, 0..) |want, i| {
        const got = readF32FromBytes(result.outputs[0], .f32, i);
        try std.testing.expectEqual(want, got);
    }

    var expected_hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(result.outputs[0], &expected_hash, .{});
    try std.testing.expectEqualSlices(u8, &expected_hash, &result.reference_hash);
}

test "gather rejects out-of-range token index instead of clamping" {
    const allocator = std.testing.allocator;
    const index_shape = [_]u64{1};
    const table_shape = [_]u64{ 2, 1 };
    const output_shape = [_]u64{ 1, 1 };
    const bindings = [_]schema.BufferBinding{
        .{ .name = "indices", .group = 0, .binding = 0, .logical_shape = &index_shape, .elem = .u32, .read_write = false },
        .{ .name = "table", .group = 0, .binding = 1, .logical_shape = &table_shape, .elem = .f32, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "t", .lower_bound = "0", .upper_bound = "1", .step = "1" },
        .{ .name = "h", .lower_bound = "0", .upper_bound = "1", .step = "1" },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .indices },
        .{ .binding_index = 1, .role = .table },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .token },
        .{ .axis_index = 1, .role = .hidden },
    };
    const body = schema.SemanticBody{
        .op = .gather,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gather_oob",
        .family_hint = .gather,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    var indices_bytes: [4]u8 = undefined;
    std.mem.writeInt(u32, indices_bytes[0..4], 2, .little);
    var table_bytes: [8]u8 = undefined;
    writeF32AsElem(&table_bytes, 0, 1.0, .f32);
    writeF32AsElem(&table_bytes, 1, 2.0, .f32);
    const inputs = [_][]const u8{ &indices_bytes, &table_bytes };

    const outcome = run(allocator, semantic, realization, &inputs);
    try std.testing.expectError(InterpretError.NotImplemented, outcome);
}

test "rms_norm f32 literal epsilon computes normalized scaled output" {
    const allocator = std.testing.allocator;
    const hidden_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "input", .group = 0, .binding = 0, .logical_shape = &hidden_shape, .elem = .f32, .read_write = false },
        .{ .name = "weight", .group = 0, .binding = 1, .logical_shape = &hidden_shape, .elem = .f32, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &hidden_shape, .elem = .f32, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "d", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .input },
        .{ .binding_index = 1, .role = .scale },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .hidden },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .rms_norm,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
        .rms_norm = .{
            .formula = .sum_squares_mean_epsilon_rsqrt_scale,
            .epsilon = .{ .source = .literal_f32, .path = "", .literal_f32 = 0.0 },
            .hidden_extent_axis = 0,
            .reduction_target = .intermediate_scalar,
        },
    };
    const func = schema.SemanticFunction{
        .name = "rms_norm",
        .family_hint = .rms_norm,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // input = [2, 2], mean(square(input)) = 4, inv_rms = 0.5.
    // weight = [3, 4], so output = [3, 4].
    var input_bytes: [8]u8 = undefined;
    writeF32AsElem(&input_bytes, 0, 2.0, .f32);
    writeF32AsElem(&input_bytes, 1, 2.0, .f32);
    var scale_bytes: [8]u8 = undefined;
    writeF32AsElem(&scale_bytes, 0, 3.0, .f32);
    writeF32AsElem(&scale_bytes, 1, 4.0, .f32);
    const inputs = [_][]const u8{ &input_bytes, &scale_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 8), result.outputs[0].len);
    try std.testing.expectEqual(@as(f32, 3.0), readF32FromBytes(result.outputs[0], .f32, 0));
    try std.testing.expectEqual(@as(f32, 4.0), readF32FromBytes(result.outputs[0], .f32, 1));

    var expected_hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(result.outputs[0], &expected_hash, .{});
    try std.testing.expectEqualSlices(u8, &expected_hash, &result.reference_hash);
}

test "rms_norm uniform epsilon reads explicit binding bytes" {
    const allocator = std.testing.allocator;
    const hidden_shape = [_]u64{2};
    const uniform_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "input", .group = 0, .binding = 0, .logical_shape = &hidden_shape, .elem = .f32, .read_write = false },
        .{ .name = "weight", .group = 0, .binding = 1, .logical_shape = &hidden_shape, .elem = .f32, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &hidden_shape, .elem = .f32, .read_write = true },
        .{ .name = "u", .group = 0, .binding = 3, .logical_shape = &uniform_shape, .elem = .u32, .read_write = false },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "d", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .input },
        .{ .binding_index = 1, .role = .scale },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .hidden },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .rms_norm,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
        .rms_norm = .{
            .formula = .sum_squares_mean_epsilon_rsqrt_scale,
            .epsilon = .{
                .source = .uniform_field,
                .path = "uniform:u.eps",
                .binding_index = 3,
                .byte_offset = 4,
                .literal_f32 = null,
            },
            .hidden_extent_axis = 0,
            .reduction_target = .intermediate_scalar,
        },
    };
    const func = schema.SemanticFunction{
        .name = "rms_norm_uniform_eps",
        .family_hint = .rms_norm,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    var input_bytes: [8]u8 = undefined;
    writeF32AsElem(&input_bytes, 0, 2.0, .f32);
    writeF32AsElem(&input_bytes, 1, 2.0, .f32);
    var scale_bytes: [8]u8 = undefined;
    writeF32AsElem(&scale_bytes, 0, 3.0, .f32);
    writeF32AsElem(&scale_bytes, 1, 4.0, .f32);
    var uniform_bytes: [8]u8 = undefined;
    std.mem.writeInt(u32, uniform_bytes[0..4], 2, .little);
    writeF32AsElem(&uniform_bytes, 1, 0.0, .f32);
    const inputs = [_][]const u8{ &input_bytes, &scale_bytes, &uniform_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 8), result.outputs[0].len);
    try std.testing.expectEqual(@as(f32, 3.0), readF32FromBytes(result.outputs[0], .f32, 0));
    try std.testing.expectEqual(@as(f32, 4.0), readF32FromBytes(result.outputs[0], .f32, 1));

    var expected_hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(result.outputs[0], &expected_hash, .{});
    try std.testing.expectEqualSlices(u8, &expected_hash, &result.reference_hash);

    const missing_uniform_inputs = [_][]const u8{ &input_bytes, &scale_bytes };
    const missing = run(allocator, semantic, realization, &missing_uniform_inputs);
    try std.testing.expectError(InterpretError.NotImplemented, missing);
}

test "fused_gemv f16 strict_ordered exercises upcast/downcast path" {
    const allocator = std.testing.allocator;
    const matrix_shape = [_]u64{ 2, 2 };
    const vector_shape = [_]u64{2};
    const output_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "W", .group = 0, .binding = 0, .logical_shape = &matrix_shape, .elem = .f16, .read_write = false },
        .{ .name = "x", .group = 0, .binding = 1, .logical_shape = &vector_shape, .elem = .f16, .read_write = false },
        .{ .name = "y", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .f16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "k", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .matrix },
        .{ .binding_index = 1, .role = .vector },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .output },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .fused_gemv,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gemv_f16",
        .family_hint = .fused_gemv,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // W = [[1,2],[4,8]] f16; x = [1, 2] f16. Values picked to be exactly
    // representable in f16 so the test pins an exact output, not a
    // tolerance-bounded one — the intent is to exercise the f16
    // upcast/downcast path, not test rounding.
    var matrix_bytes: [8]u8 = undefined;
    writeF32AsElem(&matrix_bytes, 0, 1.0, .f16);
    writeF32AsElem(&matrix_bytes, 1, 2.0, .f16);
    writeF32AsElem(&matrix_bytes, 2, 4.0, .f16);
    writeF32AsElem(&matrix_bytes, 3, 8.0, .f16);
    var vector_bytes: [4]u8 = undefined;
    writeF32AsElem(&vector_bytes, 0, 1.0, .f16);
    writeF32AsElem(&vector_bytes, 1, 2.0, .f16);
    const inputs = [_][]const u8{ &matrix_bytes, &vector_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 4), result.outputs[0].len);

    // y[0] = 1*1 + 2*2 = 5; y[1] = 4*1 + 8*2 = 20.
    const y0 = readF32FromBytes(result.outputs[0], .f16, 0);
    const y1 = readF32FromBytes(result.outputs[0], .f16, 1);
    try std.testing.expectEqual(@as(f32, 5.0), y0);
    try std.testing.expectEqual(@as(f32, 20.0), y1);
}

test "fused_gemv bf16 strict_ordered exercises upcast/downcast path" {
    const allocator = std.testing.allocator;
    const matrix_shape = [_]u64{ 2, 2 };
    const vector_shape = [_]u64{2};
    const output_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "W", .group = 0, .binding = 0, .logical_shape = &matrix_shape, .elem = .bf16, .read_write = false },
        .{ .name = "x", .group = 0, .binding = 1, .logical_shape = &vector_shape, .elem = .bf16, .read_write = false },
        .{ .name = "y", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .bf16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "k", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .matrix },
        .{ .binding_index = 1, .role = .vector },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .output },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .fused_gemv,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gemv_bf16",
        .family_hint = .fused_gemv,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Exactly-representable bf16 values (small powers of two × small
    // odd integers). bf16 has f32's exponent range but only 7 mantissa
    // bits; values here all have a mantissa that fits.
    var matrix_bytes: [8]u8 = undefined;
    writeF32AsElem(&matrix_bytes, 0, 1.0, .bf16);
    writeF32AsElem(&matrix_bytes, 1, 2.0, .bf16);
    writeF32AsElem(&matrix_bytes, 2, 4.0, .bf16);
    writeF32AsElem(&matrix_bytes, 3, 8.0, .bf16);
    var vector_bytes: [4]u8 = undefined;
    writeF32AsElem(&vector_bytes, 0, 1.0, .bf16);
    writeF32AsElem(&vector_bytes, 1, 2.0, .bf16);
    const inputs = [_][]const u8{ &matrix_bytes, &vector_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 4), result.outputs[0].len);

    const y0 = readF32FromBytes(result.outputs[0], .bf16, 0);
    const y1 = readF32FromBytes(result.outputs[0], .bf16, 1);
    try std.testing.expectEqual(@as(f32, 5.0), y0);
    try std.testing.expectEqual(@as(f32, 20.0), y1);
}

test "gather f16 copies table rows in the declared element dtype" {
    const allocator = std.testing.allocator;
    const indices_shape = [_]u64{2};
    const table_shape = [_]u64{ 2, 2 };
    const output_shape = [_]u64{ 2, 2 };
    const bindings = [_]schema.BufferBinding{
        .{ .name = "indices", .group = 0, .binding = 0, .logical_shape = &indices_shape, .elem = .u32, .read_write = false },
        .{ .name = "table", .group = 0, .binding = 1, .logical_shape = &table_shape, .elem = .f16, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .f16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "t", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "h", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .indices },
        .{ .binding_index = 1, .role = .table },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .token },
        .{ .axis_index = 1, .role = .hidden },
    };
    const body = schema.SemanticBody{
        .op = .gather,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gather_f16",
        .family_hint = .gather,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Indices = [1, 0]; Table = [[1.5, 2.5], [3.5, 4.5]] f16.
    // Expected output = [[3.5, 4.5], [1.5, 2.5]] f16.
    var indices_bytes: [8]u8 = undefined;
    std.mem.writeInt(u32, indices_bytes[0..4], 1, .little);
    std.mem.writeInt(u32, indices_bytes[4..8], 0, .little);
    var table_bytes: [8]u8 = undefined;
    writeF32AsElem(&table_bytes, 0, 1.5, .f16);
    writeF32AsElem(&table_bytes, 1, 2.5, .f16);
    writeF32AsElem(&table_bytes, 2, 3.5, .f16);
    writeF32AsElem(&table_bytes, 3, 4.5, .f16);
    const inputs = [_][]const u8{ &indices_bytes, &table_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 8), result.outputs[0].len);
    try std.testing.expectEqual(@as(f32, 3.5), readF32FromBytes(result.outputs[0], .f16, 0));
    try std.testing.expectEqual(@as(f32, 4.5), readF32FromBytes(result.outputs[0], .f16, 1));
    try std.testing.expectEqual(@as(f32, 1.5), readF32FromBytes(result.outputs[0], .f16, 2));
    try std.testing.expectEqual(@as(f32, 2.5), readF32FromBytes(result.outputs[0], .f16, 3));
}

test "gather bf16 copies table rows in the declared element dtype" {
    const allocator = std.testing.allocator;
    const indices_shape = [_]u64{2};
    const table_shape = [_]u64{ 2, 2 };
    const output_shape = [_]u64{ 2, 2 };
    const bindings = [_]schema.BufferBinding{
        .{ .name = "indices", .group = 0, .binding = 0, .logical_shape = &indices_shape, .elem = .u32, .read_write = false },
        .{ .name = "table", .group = 0, .binding = 1, .logical_shape = &table_shape, .elem = .bf16, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &output_shape, .elem = .bf16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "t", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "h", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .indices },
        .{ .binding_index = 1, .role = .table },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .token },
        .{ .axis_index = 1, .role = .hidden },
    };
    const body = schema.SemanticBody{
        .op = .gather,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
    };
    const func = schema.SemanticFunction{
        .name = "gather_bf16",
        .family_hint = .gather,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &.{},
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Integer-valued bf16 (exactly representable): 1, 2, 3, 4.
    var indices_bytes: [8]u8 = undefined;
    std.mem.writeInt(u32, indices_bytes[0..4], 1, .little);
    std.mem.writeInt(u32, indices_bytes[4..8], 0, .little);
    var table_bytes: [8]u8 = undefined;
    writeF32AsElem(&table_bytes, 0, 1.0, .bf16);
    writeF32AsElem(&table_bytes, 1, 2.0, .bf16);
    writeF32AsElem(&table_bytes, 2, 3.0, .bf16);
    writeF32AsElem(&table_bytes, 3, 4.0, .bf16);
    const inputs = [_][]const u8{ &indices_bytes, &table_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 8), result.outputs[0].len);
    try std.testing.expectEqual(@as(f32, 3.0), readF32FromBytes(result.outputs[0], .bf16, 0));
    try std.testing.expectEqual(@as(f32, 4.0), readF32FromBytes(result.outputs[0], .bf16, 1));
    try std.testing.expectEqual(@as(f32, 1.0), readF32FromBytes(result.outputs[0], .bf16, 2));
    try std.testing.expectEqual(@as(f32, 2.0), readF32FromBytes(result.outputs[0], .bf16, 3));
}

test "rms_norm f16 literal epsilon exercises upcast/downcast path" {
    const allocator = std.testing.allocator;
    const hidden_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "input", .group = 0, .binding = 0, .logical_shape = &hidden_shape, .elem = .f16, .read_write = false },
        .{ .name = "weight", .group = 0, .binding = 1, .logical_shape = &hidden_shape, .elem = .f16, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &hidden_shape, .elem = .f16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "d", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .input },
        .{ .binding_index = 1, .role = .scale },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .hidden },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .rms_norm,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
        .rms_norm = .{
            .formula = .sum_squares_mean_epsilon_rsqrt_scale,
            .epsilon = .{ .source = .literal_f32, .path = "", .literal_f32 = 0.0 },
            .hidden_extent_axis = 0,
            .reduction_target = .intermediate_scalar,
        },
    };
    const func = schema.SemanticFunction{
        .name = "rms_norm_f16",
        .family_hint = .rms_norm,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // input = [2, 2] f16 → mean_sq = 4.0 exactly, inv_rms = 0.5 exactly.
    // scale = [3, 4] f16 → output = [3, 4] f16, all exactly representable.
    var input_bytes: [4]u8 = undefined;
    writeF32AsElem(&input_bytes, 0, 2.0, .f16);
    writeF32AsElem(&input_bytes, 1, 2.0, .f16);
    var scale_bytes: [4]u8 = undefined;
    writeF32AsElem(&scale_bytes, 0, 3.0, .f16);
    writeF32AsElem(&scale_bytes, 1, 4.0, .f16);
    const inputs = [_][]const u8{ &input_bytes, &scale_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 4), result.outputs[0].len);
    try std.testing.expectEqual(@as(f32, 3.0), readF32FromBytes(result.outputs[0], .f16, 0));
    try std.testing.expectEqual(@as(f32, 4.0), readF32FromBytes(result.outputs[0], .f16, 1));
}

test "rms_norm bf16 literal epsilon exercises upcast/downcast path" {
    const allocator = std.testing.allocator;
    const hidden_shape = [_]u64{2};
    const bindings = [_]schema.BufferBinding{
        .{ .name = "input", .group = 0, .binding = 0, .logical_shape = &hidden_shape, .elem = .bf16, .read_write = false },
        .{ .name = "weight", .group = 0, .binding = 1, .logical_shape = &hidden_shape, .elem = .bf16, .read_write = false },
        .{ .name = "output", .group = 0, .binding = 2, .logical_shape = &hidden_shape, .elem = .bf16, .read_write = true },
    };
    const axes = [_]schema.IterationAxis{
        .{ .name = "d", .lower_bound = "0", .upper_bound = "2", .step = "1" },
        .{ .name = "i", .lower_bound = "0", .upper_bound = "2", .step = "1" },
    };
    const reductions = [_]schema.ReductionRegion{
        .{
            .axis = 1,
            .op = .sum,
            .contract = .{ .accumulation = .f32, .associativity = .strict_ordered, .nan_inf = .propagate },
            .target_binding = 2,
        },
    };
    const body_bindings = [_]schema.SemanticBodyBinding{
        .{ .binding_index = 0, .role = .input },
        .{ .binding_index = 1, .role = .scale },
        .{ .binding_index = 2, .role = .output },
    };
    const body_axes = [_]schema.SemanticBodyAxis{
        .{ .axis_index = 0, .role = .hidden },
        .{ .axis_index = 1, .role = .reduction },
    };
    const body = schema.SemanticBody{
        .op = .rms_norm,
        .binding_roles = &body_bindings,
        .axis_roles = &body_axes,
        .rms_norm = .{
            .formula = .sum_squares_mean_epsilon_rsqrt_scale,
            .epsilon = .{ .source = .literal_f32, .path = "", .literal_f32 = 0.0 },
            .hidden_extent_axis = 0,
            .reduction_target = .intermediate_scalar,
        },
    };
    const func = schema.SemanticFunction{
        .name = "rms_norm_bf16",
        .family_hint = .rms_norm,
        .axes = &axes,
        .bindings = &bindings,
        .reductions = &reductions,
        .collectives = &.{},
        .body = body,
        .source_digest = [_]u8{0} ** 32,
    };
    const funcs = [_]schema.SemanticFunction{func};
    const semantic = schema.Semantic{ .functions = &funcs, .rejections = &.{} };
    const realization = schema.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };

    // Same small-integer shape: input = [2, 2] bf16 → mean_sq = 4.0
    // exactly (the f32 accumulator doesn't lose precision on two bf16 2.0
    // squared-and-summed), inv_rms = 0.5 exactly; scale = [3, 4] bf16 →
    // output = [3, 4] bf16, all exactly representable.
    var input_bytes: [4]u8 = undefined;
    writeF32AsElem(&input_bytes, 0, 2.0, .bf16);
    writeF32AsElem(&input_bytes, 1, 2.0, .bf16);
    var scale_bytes: [4]u8 = undefined;
    writeF32AsElem(&scale_bytes, 0, 3.0, .bf16);
    writeF32AsElem(&scale_bytes, 1, 4.0, .bf16);
    const inputs = [_][]const u8{ &input_bytes, &scale_bytes };

    var result = try run(allocator, semantic, realization, &inputs);
    defer freeResult(allocator, &result);

    try std.testing.expectEqual(@as(usize, 1), result.outputs.len);
    try std.testing.expectEqual(@as(usize, 4), result.outputs[0].len);
    try std.testing.expectEqual(@as(f32, 3.0), readF32FromBytes(result.outputs[0], .bf16, 0));
    try std.testing.expectEqual(@as(f32, 4.0), readF32FromBytes(result.outputs[0], .bf16, 1));
}
