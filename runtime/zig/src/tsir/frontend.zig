// TSIR frontend — minimal WGSL IR → TSIR.Semantic lowering.
//
// This is the first committable increment of Step 4. Scope intentionally
// narrow: walk a `doe_wgsl.ir.Module`, emit one `SemanticFunction` per
// non-builtin function in the module, carry the function name and source
// digest, leave axes / bindings / reductions / collectives empty for now.
// Subsequent iterations add:
//   - buffer-binding extraction from `module.globals`
//   - SSA-friendly control-flow normalization + induction-variable recovery
//   - affine dependence analysis → `IterationAxis` population
//   - reduction-region identification → `ReductionRegion` population
//   - subgroup canonicalization → `CollectiveSemanticNode` population
//   - kernel-family hint inference from IR shape
//
// The minimal lowering here proves the pipeline exists end-to-end: a
// WGSL source string can be parsed, analyzed, built into IR, and then
// lowered to a `Semantic` whose digest participates in the lowering
// identity contract. Every future Step 4 increment adds one pass to
// the body of this function.

const std = @import("std");
const ir = @import("../doe_wgsl/ir.zig");
const family_hint = @import("family_hint.zig");
const tsir = @import("mod.zig");

pub const FrontendError = error{
    OutOfMemory,
};

/// Lower a Doe WGSL IR module into a `tsir.Semantic`. All allocations
/// go through the caller-provided allocator; the caller is responsible
/// for the lifetime of the returned slices (typical usage is an arena
/// scoped to a single convert-time emission).
///
/// `source_digest` should be the SHA-256 of the WGSL source that
/// produced this module so the resulting `SemanticFunction.source_digest`
/// pins identity back to the upstream WGSL.
///
/// `frontend_version` is the caller's declared frontend version
/// identity (per Step 3: `semanticDigest` is stable only under a
/// pinned frontendVersion).
pub fn lowerIrToTsir(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    source_digest: [32]u8,
    frontend_version: []const u8,
) FrontendError!tsir.Semantic {
    const functions = try allocator.alloc(tsir.schema.SemanticFunction, module.functions.items.len);
    errdefer allocator.free(functions);

    var rejections = std.ArrayList(tsir.schema.RejectionEntry){};
    defer rejections.deinit(allocator);

    for (module.functions.items, 0..) |ir_func, i| {
        const name_copy = try allocator.dupe(u8, ir_func.name);
        // Binding extraction is now per-function: only keep the
        // subset of module-scope globals this function's
        // expression list actually references. Two entry points
        // that touch disjoint binding sets therefore no longer
        // collide in the semantic digest's binding portion.
        const per_fn = try extractFunctionBindings(allocator, module, &ir_func);
        const axes = try recoverIterationAxes(allocator, module, &ir_func);
        const reductions = try recoverReductions(
            allocator,
            module,
            &ir_func,
            @intCast(i),
            &rejections,
            per_fn.global_indices,
        );
        const collectives = try collectCollectives(allocator, module, &ir_func, @intCast(i), &rejections);
        try recoverRejections(allocator, &ir_func, @intCast(i), &rejections);
        functions[i] = .{
            .name = name_copy,
            .family_hint = family_hint.infer(&ir_func, axes, reductions),
            .axes = axes,
            .bindings = per_fn.bindings,
            .reductions = reductions,
            .collectives = collectives,
            .source_digest = source_digest,
        };
    }

    const rejections_slice = rejections.toOwnedSlice(allocator) catch return error.OutOfMemory;

    return .{
        .contract_version = tsir.CONTRACT_VERSION,
        .frontend_version = frontend_version,
        .functions = functions,
        .rejections = rejections_slice,
    };
}

const PerFunctionBindings = struct {
    bindings: []tsir.schema.BufferBinding,
    /// Module-`globals` index corresponding to each `bindings[i]`.
    /// Held alongside `bindings` so `mapGlobalIndexToBinding` can
    /// turn a `global_ref` index into a position within the
    /// per-function filtered slice without re-walking the module.
    global_indices: []u32,
};

/// Walk `function.exprs` collecting every `global_ref`, then walk
/// `module.globals` and keep the subset that (1) carry a bound
/// `@group(…) @binding(…)` annotation AND (2) are actually
/// referenced by one of the collected `global_ref` expressions.
/// The returned `bindings` and `global_indices` slices are aligned
/// index-for-index, so `bindings[i]` is the TSIR encoding of the
/// global at `module.globals[global_indices[i]]`.
///
/// Globals whose type the extractor cannot represent are still
/// kept (as `(shape=[], elem=.f32)` placeholder) so the binding
/// slot survives; the per-function reachability filter is about
/// "is this binding used by this function" not "can we fully
/// encode it yet". A future iteration that adds struct /
/// texture / sampler encodings narrows the placeholder without
/// touching the reachability walk.
fn extractFunctionBindings(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
) FrontendError!PerFunctionBindings {
    var referenced = std.AutoHashMap(u32, void).init(allocator);
    defer referenced.deinit();
    for (function.exprs.items) |expr| {
        if (expr.data == .global_ref) {
            try referenced.put(expr.data.global_ref, {});
        }
    }

    var count: usize = 0;
    for (module.globals.items, 0..) |g, gi| {
        if (g.binding == null) continue;
        if (!referenced.contains(@intCast(gi))) continue;
        count += 1;
    }
    const out = try allocator.alloc(tsir.schema.BufferBinding, count);
    errdefer allocator.free(out);
    const indices = try allocator.alloc(u32, count);
    errdefer allocator.free(indices);

    var written: usize = 0;
    for (module.globals.items, 0..) |g, gi| {
        const bp = g.binding orelse continue;
        if (!referenced.contains(@intCast(gi))) continue;
        const name_copy = try allocator.dupe(u8, g.name);
        const shape_and_elem = try extractElemAndShape(allocator, module, g.ty);
        const read_write = blk: {
            if (g.access) |a| break :blk (a == .read_write);
            break :blk false;
        };
        out[written] = .{
            .name = name_copy,
            .group = bp.group,
            .binding = bp.binding,
            .logical_shape = shape_and_elem.shape,
            .elem = shape_and_elem.elem,
            .read_write = read_write,
        };
        indices[written] = @intCast(gi);
        written += 1;
    }
    return .{ .bindings = out, .global_indices = indices };
}

const ShapeAndElem = struct {
    shape: []const u64,
    elem: tsir.schema.ScalarKind,
};

/// Map a Doe IR type onto a TSIR `(logical_shape, elem)` pair.
/// Supported today: bare scalars (shape = empty), `array<T>` of a
/// scalar (shape = `[len]` if known, `[0]` if runtime-sized), and
/// `ref<storage, array<T>>` style indirections. Vectors and matrices
/// are flattened to `[vec_len]` / `[rows, cols]` with the scalar's
/// element type. Structs and textures are not yet lowered; the
/// fallback is `(shape=[], elem=.f32)` so the binding slot is still
/// captured but the shape is clearly placeholder.
fn extractElemAndShape(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    ty: ir.TypeId,
) FrontendError!ShapeAndElem {
    var cursor = ty;
    // Unwrap `ref` if the global carries one.
    const maybe_ref = module.types.get(cursor);
    if (maybe_ref == .ref) cursor = maybe_ref.ref.elem;

    const t = module.types.get(cursor);
    switch (t) {
        .scalar => |s| {
            return .{ .shape = &.{}, .elem = scalarKindFromIr(s) };
        },
        .array => |arr| {
            const elem_ty = module.types.get(arr.elem);
            const kind = switch (elem_ty) {
                .scalar => |s| scalarKindFromIr(s),
                else => .f32,
            };
            const shape = try allocator.alloc(u64, 1);
            shape[0] = if (arr.len) |n| n else 0;
            return .{ .shape = shape, .elem = kind };
        },
        .vector => |vec| {
            const elem_ty = module.types.get(vec.elem);
            const kind = switch (elem_ty) {
                .scalar => |s| scalarKindFromIr(s),
                else => .f32,
            };
            const shape = try allocator.alloc(u64, 1);
            shape[0] = @as(u64, vec.len);
            return .{ .shape = shape, .elem = kind };
        },
        .matrix => |mat| {
            const elem_ty = module.types.get(mat.elem);
            const kind = switch (elem_ty) {
                .scalar => |s| scalarKindFromIr(s),
                else => .f32,
            };
            const shape = try allocator.alloc(u64, 2);
            shape[0] = @as(u64, mat.rows);
            shape[1] = @as(u64, mat.columns);
            return .{ .shape = shape, .elem = kind };
        },
        else => {
            // Structs, textures, samplers, atomics, and unhandled
            // composites fall back to an empty shape with an f32
            // placeholder so the binding slot survives. A future
            // iteration replaces each with the right TSIR encoding.
            return .{ .shape = &.{}, .elem = .f32 };
        },
    }
}

/// Walk the function body recursively and emit one
/// `IterationAxis` per `for_loop` whose init statement is a
/// `local_decl` — the canonical `for (var i = …; …; …) {…}`
/// shape. Axes are recorded in pre-order: a `for i { for k { … } }`
/// shape emits `[i, k]`. This matches how the canonical matmul /
/// GEMV / RMSNorm nested reductions describe their iteration
/// space: the outer axis (M / rows / output index) comes first,
/// the inner axis (K / reduction dimension) second.
///
/// `while` / `loop` forms (no explicit induction variable) still
/// do not emit axes here — `recoverRejections` handles the
/// top-level non-for case by emitting
/// `tsir_dependence_unanalyzable`. Nested `while` / `loop` is
/// still silent this iteration; a future increment extends the
/// rejection pass to descend into loop bodies alongside the
/// axis walker.
fn recoverIterationAxes(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
) FrontendError![]tsir.schema.IterationAxis {
    var axes = std.ArrayList(tsir.schema.IterationAxis){};
    defer axes.deinit(allocator);

    try walkAxesInStmt(allocator, module, function, function.root_stmt, &axes);
    return axes.toOwnedSlice(allocator) catch return error.OutOfMemory;
}

/// Pre-order traversal helper used by `recoverIterationAxes`.
/// Descends into `block`, `if_` (then/else), and `loop_` bodies
/// so nested for loops at arbitrary depth still produce axes.
/// The traversal is depth-first with outer-before-inner ordering:
/// when this function sees a `for_loop`, it records the axis FIRST
/// and then recurses into the body so inner axes appear after
/// their enclosing outer axis in the resulting slice.
fn walkAxesInStmt(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    stmt_id: ir.StmtId,
    axes: *std.ArrayList(tsir.schema.IterationAxis),
) FrontendError!void {
    const stmt = function.stmts.items[stmt_id];
    switch (stmt) {
        .block => |range| {
            var i: u32 = 0;
            while (i < range.len) : (i += 1) {
                const child_id = function.stmt_children.items[range.start + i];
                const child = function.stmts.items[child_id];
                // Dispatch-grid axis: needs sibling context to
                // pick up the `if (i >= bound) return;` guard
                // that refines the placeholder upper bound, so
                // emission lives here in the block case rather
                // than in the recursive per-stmt switch.
                if (child == .local_decl) {
                    const d = child.local_decl;
                    if (tryExtractDispatchAxisLetter(function, d.initializer)) |letter| {
                        if (d.local < function.locals.items.len) {
                            const local_name = function.locals.items[d.local].name;
                            const name_copy = try allocator.dupe(u8, local_name);
                            const lower_copy = try allocator.dupe(u8, "0");
                            const upper_copy = blk: {
                                if (try scanForDispatchGuard(
                                    allocator,
                                    module,
                                    function,
                                    range,
                                    i,
                                    d.local,
                                )) |s| {
                                    break :blk s;
                                }
                                break :blk try std.fmt.allocPrint(
                                    allocator,
                                    "dispatch.{s}",
                                    .{letter},
                                );
                            };
                            const step_copy = try allocator.dupe(u8, "1");
                            try axes.append(allocator, .{
                                .name = name_copy,
                                .lower_bound = lower_copy,
                                .upper_bound = upper_copy,
                                .step = step_copy,
                            });
                        }
                        continue;
                    }
                }
                try walkAxesInStmt(allocator, module, function, child_id, axes);
            }
        },
        .if_ => |node| {
            try walkAxesInStmt(allocator, module, function, node.then_block, axes);
            if (node.else_block) |else_id| {
                try walkAxesInStmt(allocator, module, function, else_id, axes);
            }
        },
        .loop_ => |loop| {
            if (loop.kind == .for_loop) {
                if (loop.init) |init_id| {
                    const init_stmt = function.stmts.items[init_id];
                    if (init_stmt == .local_decl) {
                        const local_index = init_stmt.local_decl.local;
                        // Decreasing for-loops don't fit TSIR's
                        // half-open `[lower, upper)` iteration
                        // model; `recoverRejections` will emit a
                        // `tsir_source_not_affine` entry for
                        // them. Skip emitting an axis here so
                        // the reduction/collective walkers'
                        // axis counters stay in sync.
                        if (detectStepSign(function, loop.continuing, local_index) == .negative) {
                            try walkAxesInStmt(allocator, module, function, loop.body, axes);
                            if (loop.continuing) |cont_id| {
                                try walkAxesInStmt(allocator, module, function, cont_id, axes);
                            }
                            return;
                        }
                        if (local_index < function.locals.items.len) {
                            const local_name = function.locals.items[local_index].name;
                            const name_copy = try allocator.dupe(u8, local_name);
                            const lower_copy = blk: {
                                if (try extractInitBound(
                                    allocator,
                                    module,
                                    function,
                                    init_stmt.local_decl.initializer,
                                )) |s| {
                                    break :blk s;
                                }
                                break :blk try allocator.dupe(u8, "0");
                            };
                            const upper_copy = blk: {
                                if (extractLiteralUpperBound(function, loop.cond, local_index)) |ub| {
                                    break :blk try std.fmt.allocPrint(allocator, "{d}", .{ub});
                                }
                                if (try extractSymbolicUpperBound(
                                    allocator,
                                    module,
                                    function,
                                    loop.cond,
                                    local_index,
                                )) |s| {
                                    break :blk s;
                                }
                                break :blk try allocator.dupe(u8, "upper_bound");
                            };
                            const step_copy = blk: {
                                if (try extractStep(
                                    allocator,
                                    module,
                                    function,
                                    loop.continuing,
                                    local_index,
                                )) |s| {
                                    break :blk s;
                                }
                                break :blk try allocator.dupe(u8, "1");
                            };
                            try axes.append(allocator, .{
                                .name = name_copy,
                                .lower_bound = lower_copy,
                                .upper_bound = upper_copy,
                                .step = step_copy,
                            });
                        }
                    }
                }
            }
            // Descend into the body whether or not this loop was
            // a recognized for: nested for loops inside a while /
            // bare loop should still contribute axes, and the
            // containing non-for will rejection-escalate via a
            // separate future increment that extends
            // `recoverRejections`.
            try walkAxesInStmt(allocator, module, function, loop.body, axes);
            if (loop.continuing) |cont_id| {
                try walkAxesInStmt(allocator, module, function, cont_id, axes);
            }
        },
        else => {},
    }
}

/// Walk the function body recursively and emit one
/// `ReductionRegion` for every `for_loop` whose direct body
/// contains a self-update on a local accumulator. The walk
/// mirrors `walkAxesInStmt`: for_loops are visited in pre-order,
/// with an axis counter that matches the axes slice emitted by
/// `recoverIterationAxes` — so a reduction detected inside the
/// inner loop of a canonical `for i { for k { acc += ... } }`
/// shape reports `axis = 1` (the position of `k` in the axes
/// slice), not `axis = 0`.
///
/// Writeback resolution is done against the for_loop's PARENT
/// block, not the function root: for a nested reduction, the
/// `output[i] = acc` writeback sits in the outer loop's body
/// after the inner for_loop, so the resolver needs that block's
/// range + the inner loop's position within it. The walker
/// threads `(parent_block, position_in_parent)` through
/// recursion for that purpose.
///
/// Patterns recognized are unchanged from the top-level version:
/// compound-assign (`acc += x`) and expanded self-update
/// (`acc = acc + x`), mapped through `detectReductionOp`.
/// Honest-fallback + typed rejections for unresolved writebacks
/// and non-scalar accumulators also carry over unchanged.
fn recoverReductions(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    func_index: u32,
    rejections: *std.ArrayList(tsir.schema.RejectionEntry),
    binding_global_indices: []const u32,
) FrontendError![]tsir.schema.ReductionRegion {
    var reductions = std.ArrayList(tsir.schema.ReductionRegion){};
    defer reductions.deinit(allocator);

    var ctx = ReductionWalkCtx{
        .allocator = allocator,
        .module = module,
        .function = function,
        .func_index = func_index,
        .rejections = rejections,
        .reductions = &reductions,
        .binding_global_indices = binding_global_indices,
        .axis_counter = 0,
    };
    try walkReductionsInStmt(&ctx, function.root_stmt, null, 0);
    return reductions.toOwnedSlice(allocator) catch error.OutOfMemory;
}

const ReductionWalkCtx = struct {
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    func_index: u32,
    rejections: *std.ArrayList(tsir.schema.RejectionEntry),
    reductions: *std.ArrayList(tsir.schema.ReductionRegion),
    binding_global_indices: []const u32,
    /// Counter that increments on each for_loop entry (pre-order).
    /// Must stay in lockstep with `walkAxesInStmt`'s for_loop
    /// visit order so the `axis` field on each emitted
    /// ReductionRegion is a valid index into the axes slice.
    axis_counter: u32,
};

fn walkReductionsInStmt(
    ctx: *ReductionWalkCtx,
    stmt_id: ir.StmtId,
    parent_block: ?ir.Range,
    position_in_parent: u32,
) FrontendError!void {
    const stmt = ctx.function.stmts.items[stmt_id];
    switch (stmt) {
        .block => |range| {
            var i: u32 = 0;
            while (i < range.len) : (i += 1) {
                const child_id = ctx.function.stmt_children.items[range.start + i];
                try walkReductionsInStmt(ctx, child_id, range, i);
            }
        },
        .if_ => |node| {
            try walkReductionsInStmt(ctx, node.then_block, null, 0);
            if (node.else_block) |else_id| {
                try walkReductionsInStmt(ctx, else_id, null, 0);
            }
        },
        .local_decl => |d| {
            // A `let i = gid.x` declaration contributes one
            // dispatch-grid axis to the axes slice. Keep the
            // reduction walker's axis counter in lockstep so a
            // subsequent for_loop's `my_axis` matches the axes
            // slice built by `walkAxesInStmt`.
            if (tryExtractDispatchAxisLetter(ctx.function, d.initializer) != null) {
                ctx.axis_counter += 1;
            }
        },
        .loop_ => |loop| {
            if (loop.kind == .for_loop and loop.init != null) {
                // Mirror the axis walker: decreasing for-loops
                // contribute no axis, so skip the counter bump
                // and the reduction scan but still descend into
                // the body so nested axes / reductions inside a
                // decreasing outer loop still get picked up.
                const init_stmt = ctx.function.stmts.items[loop.init.?];
                const decreasing = init_stmt == .local_decl and
                    detectStepSign(ctx.function, loop.continuing, init_stmt.local_decl.local) == .negative;
                if (!decreasing) {
                    const my_axis = ctx.axis_counter;
                    ctx.axis_counter += 1;
                    if (parent_block) |pb| {
                        try scanDirectBodyForReduction(
                            ctx,
                            loop.body,
                            my_axis,
                            pb,
                            position_in_parent,
                        );
                    }
                }
            }
            try walkReductionsInStmt(ctx, loop.body, null, 0);
            if (loop.continuing) |cont_id| {
                try walkReductionsInStmt(ctx, cont_id, null, 0);
            }
        },
        else => {},
    }
}

/// Scan the direct (one-level) statements of a for_loop body for
/// the first assign that matches a reduction self-update; emit
/// the `ReductionRegion` and any accompanying rejections.
/// Writeback resolution uses the loop's parent block so nested
/// reductions resolve into the enclosing outer loop's body, not
/// the function root.
fn scanDirectBodyForReduction(
    ctx: *ReductionWalkCtx,
    body_stmt_id: ir.StmtId,
    my_axis: u32,
    parent_block: ir.Range,
    position_in_parent: u32,
) FrontendError!void {
    const body_stmt = ctx.function.stmts.items[body_stmt_id];
    if (body_stmt != .block) return;
    const body_range = body_stmt.block;

    var j: u32 = 0;
    while (j < body_range.len) : (j += 1) {
        const bs_id = ctx.function.stmt_children.items[body_range.start + j];
        const bs = ctx.function.stmts.items[bs_id];
        if (bs != .assign) continue;
        const assign = bs.assign;

        const recovered_op = detectReductionOp(ctx.function, assign);
        if (recovered_op) |op| {
            const lhs_node = ctx.function.exprs.items[assign.lhs];
            const acc_local = lhs_node.data.local_ref;

            const resolved = resolveTargetBinding(
                ctx.function,
                parent_block,
                position_in_parent,
                acc_local,
                ctx.binding_global_indices,
            );
            const target_binding: u32 = resolved orelse 0;
            if (resolved == null) {
                const reduction_index: u32 = @intCast(ctx.reductions.items.len);
                const path = try std.fmt.allocPrint(
                    ctx.allocator,
                    "functions[{d}].reductions[{d}]",
                    .{ ctx.func_index, reduction_index },
                );
                const detail_copy = try ctx.allocator.dupe(
                    u8,
                    "reduction accumulator has no post-loop writeback to a bound global",
                );
                try ctx.rejections.append(ctx.allocator, .{
                    .reason = .tsir_dependence_unanalyzable,
                    .node_path = path,
                    .detail = detail_copy,
                });
            }
            const resolved_kind = resolveAccumulationKind(ctx.module, ctx.function, acc_local);
            const accumulation: tsir.schema.ScalarKind = resolved_kind orelse .f32;
            if (resolved_kind == null) {
                const reduction_index: u32 = @intCast(ctx.reductions.items.len);
                const path = try std.fmt.allocPrint(
                    ctx.allocator,
                    "functions[{d}].reductions[{d}]",
                    .{ ctx.func_index, reduction_index },
                );
                const detail_copy = try ctx.allocator.dupe(
                    u8,
                    "reduction accumulator type is not representable as a single-scalar accumulation",
                );
                try ctx.rejections.append(ctx.allocator, .{
                    .reason = .tsir_dependence_unanalyzable,
                    .node_path = path,
                    .detail = detail_copy,
                });
            }
            try ctx.reductions.append(ctx.allocator, .{
                .axis = my_axis,
                .op = op,
                .contract = .{
                    .accumulation = accumulation,
                    .associativity = .strict_ordered,
                    .nan_inf = .propagate,
                },
                .target_binding = target_binding,
            });
            return;
        }
    }
}

/// Resolve the binding index a reduction's accumulator is written
/// into by scanning top-level statements that come AFTER the
/// reduction loop. Handles both the direct shape
/// `output[...] = load(acc)` and chained one-or-more-hop aliases
/// `let t0 = acc; let t1 = t0; ... output[...] = load(t_n);`. An
/// alias set starts at `{acc_local}` and grows each time a
/// post-loop `local_decl` copies one of the current aliases
/// through `load(local_ref(x))`. The writeback is accepted
/// whenever its rhs is a load of any alias currently in the set.
///
/// Returns `null` when no matching writeback is found. The caller
/// handles that case by emitting a typed
/// `tsir_dependence_unanalyzable` rejection and falling back to
/// `target_binding = 0` — the rejection is the load-bearing
/// signal that downstream consumers must fail closed on, not the
/// fallback index.
fn resolveTargetBinding(
    function: *const ir.Function,
    body_range: ir.Range,
    loop_index: u32,
    acc_local: u32,
    binding_global_indices: []const u32,
) ?u32 {
    // Fixed-size alias buffer; real kernels rarely chain more than
    // one or two copies, and overflow is just "stop tracking new
    // aliases" rather than an error. Existing aliases still
    // resolve.
    var alias_buf: [8]u32 = undefined;
    alias_buf[0] = acc_local;
    var alias_len: u32 = 1;

    var k: u32 = loop_index + 1;
    while (k < body_range.len) : (k += 1) {
        const stmt_id = function.stmt_children.items[body_range.start + k];
        const stmt = function.stmts.items[stmt_id];
        switch (stmt) {
            .local_decl => |d| {
                const init_id = d.initializer orelse continue;
                const init_node = function.exprs.items[init_id];
                if (init_node.data != .load) continue;
                const inner = function.exprs.items[init_node.data.load];
                if (inner.data != .local_ref) continue;
                const src = inner.data.local_ref;
                if (!isInAliasSet(alias_buf[0..alias_len], src)) continue;
                if (alias_len < alias_buf.len) {
                    alias_buf[alias_len] = d.local;
                    alias_len += 1;
                }
            },
            .assign => |assign| {
                // Accept the writeback when the rhs expression
                // tree contains a `load(local_ref(x))` of any
                // current alias — covers pure `output = acc`
                // and post-reduction epilogues like
                // `output = acc * scale`, `output = acc + bias`,
                // or intrinsics (`sqrt(acc)`) whose operand is
                // the accumulator. Attribution stays on the
                // final writeback's binding: the reduction
                // produces acc, the epilogue shapes it, the
                // binding holds the shaped result.
                if (!containsAliasLoad(function, assign.rhs, alias_buf[0..alias_len])) continue;

                const global_index = findGlobalBase(function, assign.lhs) orelse continue;
                if (mapGlobalIndexToBinding(binding_global_indices, global_index)) |bpos| return bpos;
            },
            else => {},
        }
    }
    return null;
}

/// Return true when the expression tree rooted at `expr_id`
/// contains at least one `load(local_ref(X))` where `X` is in
/// the alias set. Walks unary / binary / index / member /
/// construct / call argument trees; non-matching leaves
/// (literals, global/param refs, unrelated local refs) return
/// false. Used by `resolveTargetBinding` to accept writebacks
/// whose rhs is an arithmetic expression built from the
/// accumulator (e.g. post-reduction epilogues like
/// `output = acc * scale`).
fn containsAliasLoad(
    function: *const ir.Function,
    expr_id: ir.ExprId,
    aliases: []const u32,
) bool {
    const node = function.exprs.items[expr_id];
    switch (node.data) {
        .load => |inner| {
            const inner_node = function.exprs.items[inner];
            if (inner_node.data == .local_ref and isInAliasSet(aliases, inner_node.data.local_ref)) {
                return true;
            }
            return containsAliasLoad(function, inner, aliases);
        },
        .unary => |u| return containsAliasLoad(function, u.operand, aliases),
        .binary => |b| {
            return containsAliasLoad(function, b.lhs, aliases) or
                containsAliasLoad(function, b.rhs, aliases);
        },
        .index => |idx| {
            return containsAliasLoad(function, idx.base, aliases) or
                containsAliasLoad(function, idx.index, aliases);
        },
        .member => |m| return containsAliasLoad(function, m.base, aliases),
        .construct => |c| {
            var i: u32 = 0;
            while (i < c.args.len) : (i += 1) {
                const arg_id = function.expr_args.items[c.args.start + i];
                if (containsAliasLoad(function, arg_id, aliases)) return true;
            }
            return false;
        },
        .call => |c| {
            var i: u32 = 0;
            while (i < c.args.len) : (i += 1) {
                const arg_id = function.expr_args.items[c.args.start + i];
                if (containsAliasLoad(function, arg_id, aliases)) return true;
            }
            return false;
        },
        else => return false,
    }
}

fn isInAliasSet(aliases: []const u32, needle: u32) bool {
    for (aliases) |a| {
        if (a == needle) return true;
    }
    return false;
}

/// Resolve the reduction accumulator's declared IR type to the
/// matching TSIR `ScalarKind`. The accumulator's `TypeId` is
/// `function.locals[acc_local].ty`; after unwrapping a `ref<…>`
/// layer (locals declared via `var` carry `ref` in the IR type
/// table), the underlying type is expected to be a scalar.
///
/// Returns `null` when the accumulator is non-scalar (vector,
/// matrix, array, struct) — the current `NumericalContract`
/// can't represent those faithfully, so the caller emits a
/// typed rejection and keeps `.f32` as the shape-preserving
/// default. A future increment either extends the contract to
/// represent vector-typed accumulators or keeps rejecting them
/// under a more specific reason.
fn resolveAccumulationKind(
    module: *const ir.Module,
    function: *const ir.Function,
    acc_local: u32,
) ?tsir.schema.ScalarKind {
    if (acc_local >= function.locals.items.len) return null;
    var cursor = function.locals.items[acc_local].ty;
    const maybe_ref = module.types.get(cursor);
    if (maybe_ref == .ref) cursor = maybe_ref.ref.elem;
    const t = module.types.get(cursor);
    return switch (t) {
        .scalar => |s| scalarKindFromIr(s),
        else => null,
    };
}

/// Walk an lhs chain (index / member / bare global_ref) down to
/// the first `global_ref` and return the global's module index.
/// Returns `null` if the chain terminates at something other than
/// a global reference (e.g. a local variable, parameter, or
/// function call result).
fn findGlobalBase(function: *const ir.Function, expr_id: ir.ExprId) ?u32 {
    var cursor = expr_id;
    while (true) {
        const node = function.exprs.items[cursor];
        switch (node.data) {
            .global_ref => |idx| return idx,
            .index => |idx_expr| cursor = idx_expr.base,
            .member => |m| cursor = m.base,
            .load => |inner| cursor = inner,
            else => return null,
        }
    }
}

/// Convert a `module.globals` index into a position within the
/// per-function filtered `bindings` slice. `binding_global_indices`
/// is held alongside `bindings`, with `bindings[i]` encoding the
/// global at `binding_global_indices[i]`, so a linear search
/// returns the aligned position directly. Returns `null` when the
/// global is not in the per-function binding set — either because
/// it has no `@binding` annotation OR because the function does
/// not reference it.
fn mapGlobalIndexToBinding(
    binding_global_indices: []const u32,
    global_index: u32,
) ?u32 {
    for (binding_global_indices, 0..) |gi, pos| {
        if (gi == global_index) return @intCast(pos);
    }
    return null;
}

/// Extract a literal upper bound from a for-loop condition
/// shaped as any of `i < N`, `i <= N`, `N > i`, or `N >= i`
/// where `i` is the induction variable and `N` is an integer
/// literal. Returns `null` when the condition isn't one of
/// these — the caller falls back to the placeholder string
/// so non-literal bounds don't lie about being analyzable.
///
/// Convention: `upper_bound` is exclusive. The mapping mirrors
/// the polarity:
///   - `i < N` or `N > i` (strict)      → `N`
///   - `i <= N` or `N >= i` (non-strict) → `N + 1`
///
/// Rationale for the mirror forms: some authors write
/// `for (var i: u32 = 0u; 4u > i; i = i + 1u)` instead of the
/// canonical `i < 4u`. Semantically identical; without mirror
/// handling the second form collapses to the
/// `"upper_bound"` placeholder and a digest-wise-distinct
/// kernel is created where none should exist.
fn extractLiteralUpperBound(
    function: *const ir.Function,
    cond_opt: ?ir.ExprId,
    induction_local: u32,
) ?u64 {
    const cond_id = cond_opt orelse return null;
    const cond_node = function.exprs.items[cond_id];
    if (cond_node.data != .binary) return null;
    const binary = cond_node.data.binary;

    const Shape = struct { op: ir.BinaryOp, literal: u64 };
    const shape: Shape = switch (binary.op) {
        .less, .less_equal => blk: {
            const lhs_node = function.exprs.items[binary.lhs];
            if (lhs_node.data != .load) return null;
            const lhs_ref = function.exprs.items[lhs_node.data.load];
            if (lhs_ref.data != .local_ref) return null;
            if (lhs_ref.data.local_ref != induction_local) return null;
            const rhs_node = function.exprs.items[binary.rhs];
            if (rhs_node.data != .int_lit) return null;
            break :blk .{ .op = binary.op, .literal = rhs_node.data.int_lit };
        },
        .greater, .greater_equal => blk: {
            // Mirror: `N > i` or `N >= i`. Induction is on the
            // rhs, literal on the lhs. Translate to equivalent
            // `i < N` / `i <= N` bounds.
            const rhs_node = function.exprs.items[binary.rhs];
            if (rhs_node.data != .load) return null;
            const rhs_ref = function.exprs.items[rhs_node.data.load];
            if (rhs_ref.data != .local_ref) return null;
            if (rhs_ref.data.local_ref != induction_local) return null;
            const lhs_node = function.exprs.items[binary.lhs];
            if (lhs_node.data != .int_lit) return null;
            const mirrored: ir.BinaryOp = switch (binary.op) {
                .greater => .less,
                .greater_equal => .less_equal,
                else => unreachable,
            };
            break :blk .{ .op = mirrored, .literal = lhs_node.data.int_lit };
        },
        else => return null,
    };

    return switch (shape.op) {
        .less => shape.literal,
        .less_equal => shape.literal +% 1,
        else => unreachable,
    };
}

/// Decide whether an assign statement inside a loop body looks like
/// a reduction update on a local accumulator. Returns the mapped
/// `ReductionOp` when the pattern is recognized, `null` otherwise.
/// Resolve a for-loop condition shaped `i < X` or `i <= X` where
/// `X` is a module-scope `override` or `const` global reference.
/// Emits a symbolic bound string so the axis digest distinguishes
/// kernels that differ only in the named bound. Returns `null`
/// when the rhs doesn't resolve to an override/const reference —
/// uniform buffer loads and arithmetic expressions stay on the
/// placeholder path until a later increment extends the grammar.
///
/// Output shape: `"override:<name>"` for `i < N`, `"override:<name>+1"`
/// for `i <= N` (exclusive-bound convention mirroring the literal
/// path). Same convention applied for `const_` globals with the
/// `"const:"` prefix so consumers can distinguish rebindable
/// overrides from immutable constants. Returned slice is owned
/// by the caller (allocated via `allocator`).
fn extractSymbolicUpperBound(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    cond_opt: ?ir.ExprId,
    induction_local: u32,
) FrontendError!?[]const u8 {
    const cond_id = cond_opt orelse return null;
    const cond_node = function.exprs.items[cond_id];
    if (cond_node.data != .binary) return null;
    const binary = cond_node.data.binary;

    // Accept both canonical forms (`i <? name`) and mirror forms
    // (`name >? i`); translate both into a (name_expr_id,
    // effective_op) pair where effective_op is `.less` or
    // `.less_equal` so the symbolic-emit logic below can stay
    // polarity-agnostic.
    const effective_op: ir.BinaryOp = switch (binary.op) {
        .less, .less_equal => blk: {
            const lhs_node = function.exprs.items[binary.lhs];
            if (lhs_node.data != .load) return null;
            const lhs_ref = function.exprs.items[lhs_node.data.load];
            if (lhs_ref.data != .local_ref) return null;
            if (lhs_ref.data.local_ref != induction_local) return null;
            break :blk binary.op;
        },
        .greater, .greater_equal => blk: {
            const rhs_node = function.exprs.items[binary.rhs];
            if (rhs_node.data != .load) return null;
            const rhs_ref = function.exprs.items[rhs_node.data.load];
            if (rhs_ref.data != .local_ref) return null;
            if (rhs_ref.data.local_ref != induction_local) return null;
            break :blk switch (binary.op) {
                .greater => .less,
                .greater_equal => .less_equal,
                else => unreachable,
            };
        },
        else => return null,
    };
    const name_expr_id = switch (binary.op) {
        .less, .less_equal => binary.rhs,
        .greater, .greater_equal => binary.lhs,
        else => unreachable,
    };

    const suffix: []const u8 = if (effective_op == .less_equal) "+1" else "";

    // Uniform struct-field path: `i < params.count` where params is
    // a module-scope uniform. Preferred over the bare global path
    // because the field name carries semantic identity the plain
    // struct name would lose.
    if (extractUniformFieldAccess(function, name_expr_id)) |mem| {
        if (mem.global_index < module.globals.items.len) {
            const g = module.globals.items[mem.global_index];
            if (g.class == .var_ and g.addr_space == .uniform) {
                return try std.fmt.allocPrint(
                    allocator,
                    "uniform:{s}.{s}{s}",
                    .{ g.name, mem.field_name, suffix },
                );
            }
        }
    }

    const global_index = findGlobalBase(function, name_expr_id) orelse return null;
    if (global_index >= module.globals.items.len) return null;
    const g = module.globals.items[global_index];
    const base = (try writeOverrideOrConstName(allocator, g)) orelse return null;
    defer allocator.free(base);
    return try std.fmt.allocPrint(allocator, "{s}{s}", .{ base, suffix });
}

/// Extract the step string from a for-loop's `continuing` clause.
/// Recognized shapes mirror `detectReductionOp`'s two self-update
/// patterns applied to the induction variable:
///
///   - **Compound assign** (`i += N` / `i -= N`): the IR's
///     `AssignOp` is `.add` / `.sub` with lhs `local_ref(i)`.
///   - **Expanded self-update** (`i = i + N` / `i = i - N`): the
///     assign op is `.assign` and the rhs is a `.binary` whose
///     left side is a `.load` of the induction variable.
///
/// `N` is emitted as:
///   - decimal literal for `int_lit`,
///   - `uniform:<struct>.<field>` for a uniform struct field,
///   - `override:<name>` / `const:<name>` for module-scope
///     overrides / consts.
///
/// Returns `null` when the continuing clause doesn't match these
/// shapes; the caller falls through to `"1"` so the canonical
/// `i = i + 1u` kernel stays digest-stable (it also flows
/// through the int_lit path and still emits `"1"`).
fn extractStep(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    cont_opt: ?ir.StmtId,
    induction_local: u32,
) FrontendError!?[]const u8 {
    const cont_id = cont_opt orelse return null;
    const cont_stmt = function.stmts.items[cont_id];
    if (cont_stmt != .assign) return null;
    const assign = cont_stmt.assign;

    // lhs must resolve to the induction local_ref (no load — this
    // is an assign target, not a value load).
    const lhs_node = function.exprs.items[assign.lhs];
    if (lhs_node.data != .local_ref) return null;
    if (lhs_node.data.local_ref != induction_local) return null;

    // Pick the expression whose value is `N`:
    //   - Compound assign (`i += N`): `assign.rhs` IS `N`.
    //   - Expanded (`i = i + N`): `assign.rhs` is `binary`, take
    //     `rhs.rhs` as the literal `N` side (after confirming the
    //     binary's lhs is `load(local_ref(i))`).
    var value_expr_id = assign.rhs;
    const prefix: []const u8 = switch (assign.op) {
        .add => "",
        .sub => "-",
        .assign => blk: {
            const rhs_node = function.exprs.items[assign.rhs];
            if (rhs_node.data != .binary) return null;
            const binary = rhs_node.data.binary;
            const binary_lhs_node = function.exprs.items[binary.lhs];
            if (binary_lhs_node.data != .load) return null;
            const inner = function.exprs.items[binary_lhs_node.data.load];
            if (inner.data != .local_ref) return null;
            if (inner.data.local_ref != induction_local) return null;
            value_expr_id = binary.rhs;
            break :blk switch (binary.op) {
                .add => "",
                .sub => "-",
                else => return null,
            };
        },
        else => return null,
    };

    const value_node = function.exprs.items[value_expr_id];
    if (value_node.data == .int_lit) {
        return try std.fmt.allocPrint(
            allocator,
            "{s}{d}",
            .{ prefix, value_node.data.int_lit },
        );
    }

    if (extractUniformFieldAccess(function, value_expr_id)) |mem| {
        if (mem.global_index < module.globals.items.len) {
            const g = module.globals.items[mem.global_index];
            if (g.class == .var_ and g.addr_space == .uniform) {
                return try std.fmt.allocPrint(
                    allocator,
                    "{s}uniform:{s}.{s}",
                    .{ prefix, g.name, mem.field_name },
                );
            }
        }
    }

    if (findGlobalBase(function, value_expr_id)) |global_index| {
        if (global_index < module.globals.items.len) {
            const g = module.globals.items[global_index];
            if (try writeOverrideOrConstName(allocator, g)) |base| {
                defer allocator.free(base);
                return try std.fmt.allocPrint(allocator, "{s}{s}", .{ prefix, base });
            }
        }
    }

    return null;
}

/// Resolve the initializer expression of a for-loop's induction
/// variable into a lower-bound string. Handles integer literals
/// directly (`for (var i: u32 = 4u; ...)` → `"4"`), uniform
/// struct fields (`for (var i: u32 = params.offset; ...)` →
/// `"uniform:params.offset"`), and module-scope override / const
/// references (`for (var i: u32 = start; ...)` →
/// `"override:start"` / `"const:start"`). Returns `null` for
/// anything else so the caller falls through to the `"0"`
/// default, which matches the canonical `i = 0u` init the axis
/// walker historically assumed.
fn extractInitBound(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    init_expr_opt: ?ir.ExprId,
) FrontendError!?[]const u8 {
    const init_id = init_expr_opt orelse return null;
    const init_node = function.exprs.items[init_id];

    if (init_node.data == .int_lit) {
        return try std.fmt.allocPrint(allocator, "{d}", .{init_node.data.int_lit});
    }

    if (extractUniformFieldAccess(function, init_id)) |mem| {
        if (mem.global_index < module.globals.items.len) {
            const g = module.globals.items[mem.global_index];
            if (g.class == .var_ and g.addr_space == .uniform) {
                return try std.fmt.allocPrint(
                    allocator,
                    "uniform:{s}.{s}",
                    .{ g.name, mem.field_name },
                );
            }
        }
    }

    if (findGlobalBase(function, init_id)) |global_index| {
        if (global_index < module.globals.items.len) {
            const g = module.globals.items[global_index];
            if (try writeOverrideOrConstName(allocator, g)) |base| {
                return base;
            }
        }
    }

    return null;
}

/// Scan forward in a block looking for the early-return guard
/// that bounds `dispatch_local`. Multi-axis dispatch kernels
/// commonly interleave several `let X = gid.*` decls with
/// sibling guards:
///
/// ```
/// let t = gid.y;
/// let h = gid.x;
/// if (t >= u.num_tokens) { return; }
/// if (h >= u.hidden) { return; }
/// ```
///
/// The single-sibling peek used to match only the first case —
/// the one whose guard sits immediately after its decl. Scanning
/// past skip-safe siblings (other local_decls; early-return
/// guards for OTHER axes) lets every dispatch axis still resolve
/// its real bound. Anything that isn't a skip-safe shape
/// (arithmetic assigns, returns, for-loops, non-guard ifs) stops
/// the scan and falls through to the placeholder.
fn scanForDispatchGuard(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    body_range: ir.Range,
    start_pos: u32,
    dispatch_local: u32,
) FrontendError!?[]const u8 {
    var k: u32 = start_pos + 1;
    while (k < body_range.len) : (k += 1) {
        const stmt_id = function.stmt_children.items[body_range.start + k];
        const stmt = function.stmts.items[stmt_id];
        switch (stmt) {
            .local_decl => continue,
            .if_ => |if_node| {
                if (try extractDispatchBoundFromGuard(
                    allocator,
                    module,
                    function,
                    stmt_id,
                    dispatch_local,
                )) |s| return s;

                // Not our guard. Skip past it only when it's a
                // bare early-return for SOME OTHER local — any
                // structural divergence (else branch, multi-stmt
                // then-body without a return) stops the scan
                // since we can't reason about execution paths
                // that survive past it.
                if (if_node.else_block != null) return null;
                const then_stmt = function.stmts.items[if_node.then_block];
                const is_early_return = switch (then_stmt) {
                    .return_ => true,
                    .block => |r| blk: {
                        if (r.len != 1) break :blk false;
                        const inner_id = function.stmt_children.items[r.start];
                        break :blk function.stmts.items[inner_id] == .return_;
                    },
                    else => false,
                };
                if (!is_early_return) return null;
            },
            else => return null,
        }
    }
    return null;
}

/// Detect `if (i >= bound) { return; }` / `if (i > bound) ...`
/// early-return guard statements immediately following a
/// dispatch-axis `local_decl`. Returns the resolved upper_bound
/// string when the shape matches — literal, uniform-struct
/// field, override, or const — or `null` otherwise so the
/// caller falls back to the `"dispatch.x"` placeholder.
///
/// Semantic mapping: the guard early-returns when the condition
/// is true, so the VALID range of the dispatch local is the
/// complement of the guard. `i >= M` → valid range `[0, M)` →
/// upper_bound = `M` (no suffix). `i > M` → valid range
/// `[0, M]` → upper_bound = `M + 1` under the exclusive-bound
/// convention (suffix `"+1"`).
///
/// Structural checks: the statement must be an `if` with no
/// else branch whose then-body is either a bare `return` or a
/// single-statement block containing a return. This is narrow
/// on purpose — other guard shapes (side effects, multi-stmt
/// then, conditional writes) keep the axis on the placeholder
/// until the walker grows richer.
fn extractDispatchBoundFromGuard(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    guard_stmt_id: ir.StmtId,
    dispatch_local: u32,
) FrontendError!?[]const u8 {
    const stmt = function.stmts.items[guard_stmt_id];
    if (stmt != .if_) return null;
    const if_ = stmt.if_;
    if (if_.else_block != null) return null;

    // then must be a bare return or a block containing one return
    const then_stmt = function.stmts.items[if_.then_block];
    switch (then_stmt) {
        .return_ => {},
        .block => |r| {
            if (r.len != 1) return null;
            const inner_id = function.stmt_children.items[r.start];
            const inner = function.stmts.items[inner_id];
            if (inner != .return_) return null;
        },
        else => return null,
    }

    const cond_node = function.exprs.items[if_.cond];
    if (cond_node.data != .binary) return null;
    const binary = cond_node.data.binary;
    if (binary.op != .greater and binary.op != .greater_equal) return null;

    // lhs must be `load(local_ref(dispatch_local))`
    const lhs_node = function.exprs.items[binary.lhs];
    if (lhs_node.data != .load) return null;
    const lhs_ref = function.exprs.items[lhs_node.data.load];
    if (lhs_ref.data != .local_ref) return null;
    if (lhs_ref.data.local_ref != dispatch_local) return null;

    const suffix: []const u8 = if (binary.op == .greater) "+1" else "";

    // Literal bound
    const rhs_node = function.exprs.items[binary.rhs];
    if (rhs_node.data == .int_lit) {
        return try std.fmt.allocPrint(
            allocator,
            "{d}{s}",
            .{ rhs_node.data.int_lit, suffix },
        );
    }

    // Uniform struct-field bound
    if (extractUniformFieldAccess(function, binary.rhs)) |mem| {
        if (mem.global_index < module.globals.items.len) {
            const g = module.globals.items[mem.global_index];
            if (g.class == .var_ and g.addr_space == .uniform) {
                return try std.fmt.allocPrint(
                    allocator,
                    "uniform:{s}.{s}{s}",
                    .{ g.name, mem.field_name, suffix },
                );
            }
        }
    }

    // Override / const bound
    if (findGlobalBase(function, binary.rhs)) |global_index| {
        if (global_index < module.globals.items.len) {
            const g = module.globals.items[global_index];
            if (try writeOverrideOrConstName(allocator, g)) |base| {
                defer allocator.free(base);
                return try std.fmt.allocPrint(allocator, "{s}{s}", .{ base, suffix });
            }
        }
    }

    return null;
}

const StepSign = enum { positive, negative, unknown };

/// Classify a for-loop's `continuing` clause as increasing,
/// decreasing, or unknown WITHOUT allocating a step string. The
/// axis, reduction, and collective walkers all call this to
/// decide whether to emit/increment for the loop, and the
/// rejection pass uses it to escalate decreasing loops to a
/// typed rejection.
///
/// Recognized shapes mirror `extractStep`: compound
/// `i += N` / `i -= N` and expanded `i = i + N` / `i = i - N`.
/// Anything else returns `.unknown` — treated as positive by
/// the axis/reduction/collective walkers (so "can't prove it's
/// decreasing" doesn't reject an otherwise-recognizable loop),
/// but the rejection pass uses strict `.negative` checks so it
/// never emits a false-positive rejection either.
fn detectStepSign(
    function: *const ir.Function,
    cont_opt: ?ir.StmtId,
    induction_local: u32,
) StepSign {
    const cont_id = cont_opt orelse return .unknown;
    const cont_stmt = function.stmts.items[cont_id];
    if (cont_stmt != .assign) return .unknown;
    const assign = cont_stmt.assign;

    const lhs_node = function.exprs.items[assign.lhs];
    if (lhs_node.data != .local_ref) return .unknown;
    if (lhs_node.data.local_ref != induction_local) return .unknown;

    switch (assign.op) {
        .add => return .positive,
        .sub => return .negative,
        .assign => {
            const rhs_node = function.exprs.items[assign.rhs];
            if (rhs_node.data != .binary) return .unknown;
            const binary = rhs_node.data.binary;
            const binary_lhs_node = function.exprs.items[binary.lhs];
            if (binary_lhs_node.data != .load) return .unknown;
            const inner = function.exprs.items[binary_lhs_node.data.load];
            if (inner.data != .local_ref) return .unknown;
            if (inner.data.local_ref != induction_local) return .unknown;
            return switch (binary.op) {
                .add => .positive,
                .sub => .negative,
                else => .unknown,
            };
        },
        else => return .unknown,
    }
}

/// Format a module-scope `override` or `const` global as a
/// symbolic identifier used in axis bound strings. Prefer the
/// `@id(N)` pipeline constant id over the textual name when it's
/// present — the id is the stable identity across renames, so
/// the resulting digest does not fork when a kernel's override
/// is renamed. Returns `null` for globals that aren't symbolic
/// bound candidates (var_ / input / output classes). Returned
/// slice is owned by the caller (allocated via `allocator`).
fn writeOverrideOrConstName(
    allocator: std.mem.Allocator,
    g: ir.Global,
) FrontendError!?[]const u8 {
    return switch (g.class) {
        .override_ => blk: {
            if (g.override_id) |id| {
                break :blk try std.fmt.allocPrint(allocator, "override@id:{d}", .{id});
            }
            break :blk try std.fmt.allocPrint(allocator, "override:{s}", .{g.name});
        },
        .const_ => try std.fmt.allocPrint(allocator, "const:{s}", .{g.name}),
        else => null,
    };
}

/// Detect `let i: u32 = gid.x` / `.y` / `.z` shaped
/// initializers: `member(param_ref(N), "x"|"y"|"z")` where the
/// referenced parameter is annotated
/// `@builtin(global_invocation_id)`. Returns the member field
/// name (`"x"`, `"y"`, or `"z"`) so the caller can emit a
/// dispatch-grid `IterationAxis` with an `upper_bound` string
/// like `"dispatch.x"` that downstream residency planning
/// recognizes. Returns `null` otherwise so non-dispatch locals
/// stay out of the axes slice.
fn tryExtractDispatchAxisLetter(
    function: *const ir.Function,
    init_expr_opt: ?ir.ExprId,
) ?[]const u8 {
    const init_id = init_expr_opt orelse return null;

    // Unwrap a leading `.load` — single-component vector
    // swizzles like `gid.x` can be ref-category in sema, in
    // which case `lower_value_expr` wraps the member access
    // with a load before storing it in a `let`.
    var cursor = init_id;
    while (true) {
        const node = function.exprs.items[cursor];
        switch (node.data) {
            .load => |inner| cursor = inner,
            .member => break,
            else => return null,
        }
    }
    const member_node = function.exprs.items[cursor];
    const m = member_node.data.member;

    var base = m.base;
    while (true) {
        const bn = function.exprs.items[base];
        switch (bn.data) {
            .load => |inner| base = inner,
            .param_ref => |pidx| {
                if (pidx >= function.params.items.len) return null;
                const p = function.params.items[pidx];
                const io = p.io orelse return null;
                if (io.builtin != .global_invocation_id) return null;
                return m.field_name;
            },
            else => return null,
        }
    }
}

/// Detect the WGSL shape `param_struct.field` in an IR rhs
/// expression. Walks through outer `load` wrappers, then expects
/// a `member` whose base chain terminates at a `global_ref`.
/// Returns the global's index and the member's field name when the
/// pattern matches, `null` otherwise. The caller still has to
/// verify the global's `addr_space` / `class` to decide whether
/// the access is valid as a symbolic bound.
fn extractUniformFieldAccess(
    function: *const ir.Function,
    expr_id: ir.ExprId,
) ?struct { global_index: u32, field_name: []const u8 } {
    var cursor = expr_id;
    while (true) {
        const node = function.exprs.items[cursor];
        switch (node.data) {
            .load => |inner| cursor = inner,
            .member => |m| {
                var base = m.base;
                while (true) {
                    const bn = function.exprs.items[base];
                    switch (bn.data) {
                        .load => |inner| base = inner,
                        .global_ref => |gi| return .{
                            .global_index = gi,
                            .field_name = m.field_name,
                        },
                        else => return null,
                    }
                }
            },
            else => return null,
        }
    }
}

fn detectReductionOp(
    function: *const ir.Function,
    assign: anytype,
) ?tsir.schema.ReductionOp {
    const lhs_node = function.exprs.items[assign.lhs];
    if (lhs_node.data != .local_ref) return null;
    const acc_local = lhs_node.data.local_ref;

    // Compound-assign path: `acc += x` / `acc *= x`.
    switch (assign.op) {
        .add => return .sum,
        .mul => return .product,
        else => {},
    }
    if (assign.op != .assign) return null;

    const rhs_node = function.exprs.items[assign.rhs];

    // Expanded-self-update path: `acc = acc <op> x`.
    if (rhs_node.data == .binary) {
        const binary = rhs_node.data.binary;
        const binary_lhs_node = function.exprs.items[binary.lhs];
        if (binary_lhs_node.data == .load) {
            const inner_ref_node = function.exprs.items[binary_lhs_node.data.load];
            if (inner_ref_node.data == .local_ref and inner_ref_node.data.local_ref == acc_local) {
                return switch (binary.op) {
                    .add => .sum,
                    .mul => .product,
                    else => null,
                };
            }
        }
    }

    // Intrinsic-call self-update: `acc = max(acc, x)` /
    // `min(acc, x)` or the commutative-swapped `max(x, acc)` /
    // `min(x, acc)`. Recognized when the rhs is a builtin call
    // to `max` / `min` and at least one argument is a load of
    // the accumulator. Since min and max are commutative, either
    // argument position counts as a valid self-update match.
    // The other argument is the per-iteration input; its shape
    // doesn't affect the reduction-region contract, so no
    // structural verification is needed.
    if (rhs_node.data == .call) {
        const c = rhs_node.data.call;
        const is_max = std.mem.eql(u8, c.name, "max");
        const is_min = std.mem.eql(u8, c.name, "min");
        if (c.kind == .builtin and (is_max or is_min) and c.args.len >= 2) {
            var ai: u32 = 0;
            while (ai < c.args.len) : (ai += 1) {
                const arg_id = function.expr_args.items[c.args.start + ai];
                const arg_node = function.exprs.items[arg_id];
                if (arg_node.data != .load) continue;
                const inner = function.exprs.items[arg_node.data.load];
                if (inner.data != .local_ref) continue;
                if (inner.data.local_ref != acc_local) continue;
                return if (is_max) .max else .min;
            }
        }
    }

    return null;
}

/// Walk the function body recursively and append one
/// `RejectionEntry` for every `while` / bare `loop` encountered
/// at any depth. Emitting these rejections is how the frontend
/// stays honest: per Step 4 of the TSIR plan, a source that
/// cannot be represented faithfully must reject with a typed
/// taxonomy reason rather than have its semantics silently
/// dropped. This pass mirrors `walkAxesInStmt` — both descend
/// through `block`, `if_` (then/else), and `loop_` bodies —
/// so a `while` nested inside a `for_loop` body still produces
/// a rejection instead of being invisibly absorbed.
///
/// `node_path` is a structured dot-delimited form. Top-level
/// non-for loops produce `functions[<i>].body[<k>]`; a non-for
/// nested inside an outer for at root position `k0` produces
/// `functions[<i>].body[<k0>].body[<k1>]`, and so on. Each
/// `.body[...]` segment corresponds to a block scope entered
/// during traversal. `detail` stays as a short noun phrase:
/// `"while loop"` or `"unstructured loop"`.
fn recoverRejections(
    allocator: std.mem.Allocator,
    function: *const ir.Function,
    func_index: u32,
    rejections: *std.ArrayList(tsir.schema.RejectionEntry),
) FrontendError!void {
    const root_prefix = try std.fmt.allocPrint(allocator, "functions[{d}]", .{func_index});
    defer allocator.free(root_prefix);
    try walkRejectionsInStmt(
        allocator,
        function,
        function.root_stmt,
        root_prefix,
        rejections,
    );
}

fn walkRejectionsInStmt(
    allocator: std.mem.Allocator,
    function: *const ir.Function,
    stmt_id: ir.StmtId,
    path_prefix: []const u8,
    rejections: *std.ArrayList(tsir.schema.RejectionEntry),
) FrontendError!void {
    const stmt = function.stmts.items[stmt_id];
    switch (stmt) {
        .block => |range| {
            var i: u32 = 0;
            while (i < range.len) : (i += 1) {
                const child_id = function.stmt_children.items[range.start + i];
                const child_path = try std.fmt.allocPrint(
                    allocator,
                    "{s}.body[{d}]",
                    .{ path_prefix, i },
                );
                defer allocator.free(child_path);
                try walkRejectionsInStmt(allocator, function, child_id, child_path, rejections);
            }
        },
        .if_ => |node| {
            const then_prefix = try std.fmt.allocPrint(
                allocator,
                "{s}.then",
                .{path_prefix},
            );
            defer allocator.free(then_prefix);
            try walkRejectionsInStmt(allocator, function, node.then_block, then_prefix, rejections);
            if (node.else_block) |else_id| {
                const else_prefix = try std.fmt.allocPrint(
                    allocator,
                    "{s}.else",
                    .{path_prefix},
                );
                defer allocator.free(else_prefix);
                try walkRejectionsInStmt(allocator, function, else_id, else_prefix, rejections);
            }
        },
        .loop_ => |loop| {
            if (loop.kind != .for_loop) {
                const detail_literal: []const u8 = switch (loop.kind) {
                    .while_loop => "while loop",
                    .loop => "unstructured loop",
                    .for_loop => unreachable,
                };
                const detail_copy = try allocator.dupe(u8, detail_literal);
                const path_copy = try allocator.dupe(u8, path_prefix);
                try rejections.append(allocator, .{
                    .reason = .tsir_dependence_unanalyzable,
                    .node_path = path_copy,
                    .detail = detail_copy,
                });
            } else if (loop.init) |init_id| {
                const init_stmt = function.stmts.items[init_id];
                if (init_stmt == .local_decl and
                    detectStepSign(function, loop.continuing, init_stmt.local_decl.local) == .negative)
                {
                    const detail_copy = try allocator.dupe(
                        u8,
                        "decreasing for-loop does not fit half-open iteration model",
                    );
                    const path_copy = try allocator.dupe(u8, path_prefix);
                    try rejections.append(allocator, .{
                        .reason = .tsir_source_not_affine,
                        .node_path = path_copy,
                        .detail = detail_copy,
                    });
                }
            }
            try walkRejectionsInStmt(allocator, function, loop.body, path_prefix, rejections);
            if (loop.continuing) |cont_id| {
                try walkRejectionsInStmt(allocator, function, cont_id, path_prefix, rejections);
            }
        },
        else => {},
    }
}

/// Walk `function.exprs` for builtin calls that correspond to
/// WGSL subgroup / workgroup collectives and emit one
/// `CollectiveSemanticNode` per call site. This is the Step 4
/// "subgroup canonicalization" pass: downstream lowering can
/// stop interpreting subgroup semantics per-emitter, because
/// the frontend already declares them as collective nodes.
///
/// Per the plan, the frontend cannot pin the full numerical
/// contract for these collectives — tree shape and fabric
/// mapping are realization decisions. So this pass records the
/// collective's existence with a deliberately pessimistic
/// default exactness (`algorithm_exact` with `reduction_order`
/// and `associativity_grouping` as required invariants) that
/// forces any downstream realization to declare those
/// properties. Step 6's collective-synthesis pass refines the
/// class and invariants when it knows the real tree shape.
///
/// `axis = -1` is the "whole-workgroup / subgroup" sentinel
/// defined in `CollectiveSemanticNode` — subgroup ops are not
/// scoped to a TSIR iteration axis.
///
/// `dtype` resolves from the call's return type through
/// `scalarKindFromIr` after a `ref<…>` unwrap. Non-scalar
/// return types (e.g. `subgroupBallot` returning `vec4<u32>`)
/// fall back to `.u32` this iteration — a future increment
/// either extends `ScalarKind` or rejection-escalates the
/// fall-back path the same way non-scalar accumulators do.
fn collectCollectives(
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    func_index: u32,
    rejections: *std.ArrayList(tsir.schema.RejectionEntry),
) FrontendError![]tsir.schema.CollectiveSemanticNode {
    var out = std.ArrayList(tsir.schema.CollectiveSemanticNode){};
    defer out.deinit(allocator);
    var axis_stack = std.ArrayList(u32){};
    defer axis_stack.deinit(allocator);

    var ctx = CollectiveWalkCtx{
        .allocator = allocator,
        .module = module,
        .function = function,
        .func_index = func_index,
        .rejections = rejections,
        .out = &out,
        .axis_counter = 0,
        .axis_stack = &axis_stack,
    };
    try walkCollectivesInStmt(&ctx, function.root_stmt);

    return out.toOwnedSlice(allocator) catch error.OutOfMemory;
}

const CollectiveWalkCtx = struct {
    allocator: std.mem.Allocator,
    module: *const ir.Module,
    function: *const ir.Function,
    func_index: u32,
    rejections: *std.ArrayList(tsir.schema.RejectionEntry),
    out: *std.ArrayList(tsir.schema.CollectiveSemanticNode),
    /// Counter that increments on each for_loop entry, matching the
    /// axis index each for_loop contributes to the axes slice.
    axis_counter: u32,
    /// Stack of enclosing for_loop axis indices. `axis_stack.items[top]`
    /// is the innermost scope; empty means "no enclosing for loop"
    /// which maps to the schema's `-1` whole-workgroup sentinel.
    axis_stack: *std.ArrayList(u32),
};

fn walkCollectivesInStmt(ctx: *CollectiveWalkCtx, stmt_id: ir.StmtId) FrontendError!void {
    const stmt = ctx.function.stmts.items[stmt_id];
    switch (stmt) {
        .block => |range| {
            var i: u32 = 0;
            while (i < range.len) : (i += 1) {
                const child = ctx.function.stmt_children.items[range.start + i];
                try walkCollectivesInStmt(ctx, child);
            }
        },
        .local_decl => |d| {
            if (tryExtractDispatchAxisLetter(ctx.function, d.initializer) != null) {
                ctx.axis_counter += 1;
            }
            if (d.initializer) |e| try walkCollectivesInExpr(ctx, e);
        },
        .expr => |e| try walkCollectivesInExpr(ctx, e),
        .assign => |a| {
            try walkCollectivesInExpr(ctx, a.lhs);
            try walkCollectivesInExpr(ctx, a.rhs);
        },
        .return_ => |opt| if (opt) |e| try walkCollectivesInExpr(ctx, e),
        .if_ => |node| {
            try walkCollectivesInExpr(ctx, node.cond);
            try walkCollectivesInStmt(ctx, node.then_block);
            if (node.else_block) |e| try walkCollectivesInStmt(ctx, e);
        },
        .loop_ => |loop| {
            // Decreasing for-loops don't contribute an axis;
            // mirror the axis walker so the counter and stack
            // stay in sync with the axes slice.
            var is_recognized_for = loop.kind == .for_loop and loop.init != null;
            if (is_recognized_for) {
                const init_stmt = ctx.function.stmts.items[loop.init.?];
                if (init_stmt == .local_decl and
                    detectStepSign(ctx.function, loop.continuing, init_stmt.local_decl.local) == .negative)
                {
                    is_recognized_for = false;
                }
            }
            if (is_recognized_for) {
                const my_axis = ctx.axis_counter;
                ctx.axis_counter += 1;
                try ctx.axis_stack.append(ctx.allocator, my_axis);
            }
            if (loop.init) |init_id| try walkCollectivesInStmt(ctx, init_id);
            if (loop.cond) |cond| try walkCollectivesInExpr(ctx, cond);
            try walkCollectivesInStmt(ctx, loop.body);
            if (loop.continuing) |cont| try walkCollectivesInStmt(ctx, cont);
            if (is_recognized_for) _ = ctx.axis_stack.pop();
        },
        .switch_ => |s| try walkCollectivesInExpr(ctx, s.expr),
        else => {},
    }
}

fn walkCollectivesInExpr(ctx: *CollectiveWalkCtx, expr_id: ir.ExprId) FrontendError!void {
    const expr = ctx.function.exprs.items[expr_id];
    switch (expr.data) {
        .call => |c| {
            if (c.kind == .builtin) {
                if (builtinNameToCollectiveKind(c.name)) |kind| {
                    try emitCollectiveNode(ctx, expr, kind);
                }
            }
            var ai: u32 = 0;
            while (ai < c.args.len) : (ai += 1) {
                const arg_id = ctx.function.expr_args.items[c.args.start + ai];
                try walkCollectivesInExpr(ctx, arg_id);
            }
        },
        .load => |inner| try walkCollectivesInExpr(ctx, inner),
        .unary => |u| try walkCollectivesInExpr(ctx, u.operand),
        .binary => |b| {
            try walkCollectivesInExpr(ctx, b.lhs);
            try walkCollectivesInExpr(ctx, b.rhs);
        },
        .construct => |c| {
            var ai: u32 = 0;
            while (ai < c.args.len) : (ai += 1) {
                const arg_id = ctx.function.expr_args.items[c.args.start + ai];
                try walkCollectivesInExpr(ctx, arg_id);
            }
        },
        .member => |m| try walkCollectivesInExpr(ctx, m.base),
        .index => |idx| {
            try walkCollectivesInExpr(ctx, idx.base);
            try walkCollectivesInExpr(ctx, idx.index);
        },
        else => {},
    }
}

fn emitCollectiveNode(
    ctx: *CollectiveWalkCtx,
    expr: ir.ExprNode,
    kind: tsir.schema.CollectiveKind,
) FrontendError!void {
    var dtype: tsir.schema.ScalarKind = .u32;
    if (kind != .workgroup_barrier) {
        if (collectiveDtypeFromReturn(ctx.module, expr.ty)) |t| {
            dtype = t;
        } else {
            const collective_index: u32 = @intCast(ctx.out.items.len);
            const path = try std.fmt.allocPrint(
                ctx.allocator,
                "functions[{d}].collectives[{d}]",
                .{ ctx.func_index, collective_index },
            );
            const detail_copy = try ctx.allocator.dupe(
                u8,
                "collective return type is not representable as a single-scalar dtype",
            );
            try ctx.rejections.append(ctx.allocator, .{
                .reason = .tsir_collective_not_representable,
                .node_path = path,
                .detail = detail_copy,
            });
        }
    }
    const axis: i32 = if (ctx.axis_stack.items.len > 0)
        @intCast(ctx.axis_stack.items[ctx.axis_stack.items.len - 1])
    else
        -1;
    try ctx.out.append(ctx.allocator, .{
        .kind = kind,
        .axis = axis,
        .exactness = .{
            .class = .algorithm_exact,
            .algorithm_exact_invariants = &[_]tsir.schema.AlgorithmExactInvariant{
                .reduction_order,
                .associativity_grouping,
            },
        },
        .dtype = dtype,
    });
}

fn builtinNameToCollectiveKind(name: []const u8) ?tsir.schema.CollectiveKind {
    const eq = std.mem.eql;
    if (eq(u8, name, "subgroupAdd")) return .subgroup_add;
    if (eq(u8, name, "subgroupMin")) return .subgroup_min;
    if (eq(u8, name, "subgroupMax")) return .subgroup_max;
    if (eq(u8, name, "subgroupMul")) return .subgroup_mul;
    if (eq(u8, name, "subgroupBroadcast")) return .subgroup_broadcast;
    if (eq(u8, name, "subgroupShuffle")) return .subgroup_shuffle;
    if (eq(u8, name, "subgroupBallot")) return .subgroup_ballot;
    if (eq(u8, name, "subgroupInclusiveAdd")) return .subgroup_inclusive_scan;
    if (eq(u8, name, "subgroupInclusiveMul")) return .subgroup_inclusive_scan;
    if (eq(u8, name, "subgroupExclusiveAdd")) return .subgroup_exclusive_scan;
    if (eq(u8, name, "subgroupExclusiveMul")) return .subgroup_exclusive_scan;
    if (eq(u8, name, "workgroupBarrier")) return .workgroup_barrier;
    return null;
}

fn collectiveDtypeFromReturn(
    module: *const ir.Module,
    return_ty: ir.TypeId,
) ?tsir.schema.ScalarKind {
    var cursor = return_ty;
    const maybe_ref = module.types.get(cursor);
    if (maybe_ref == .ref) cursor = maybe_ref.ref.elem;
    const t = module.types.get(cursor);
    return switch (t) {
        .scalar => |s| scalarKindFromIr(s),
        else => null,
    };
}

fn scalarKindFromIr(s: ir.ScalarType) tsir.schema.ScalarKind {
    return switch (s) {
        .f32 => .f32,
        .f16 => .f16,
        .i32 => .i32,
        .u32 => .u32,
        .abstract_int => .i32,
        .abstract_float => .f32,
        .bool, .void => .u32, // placeholder; bool/void are not resource dtypes in practice
    };
}
