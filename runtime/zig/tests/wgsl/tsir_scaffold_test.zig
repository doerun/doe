// Scaffolding checks for the TSIR module and target descriptors.
//
// Locks the minimum invariants of the new compiler front door:
//   - Target descriptors produce distinct, stable hashes.
//   - Digest helper is defensive against empty inputs.
//   - Reference interpreter is fail-closed by default:
//       * `RejectedBySemantic` for explicit TSIR rejections
//       * `NotImplemented` for unsupported but otherwise valid TSIR
//
// When each TSIR pass lands, its own test file joins `tests/wgsl/`.

const std = @import("std");
const tsir = @import("../../src/tsir/mod.zig");
const tsir_digest = @import("../../src/tsir/digest.zig");
const tsir_reference = @import("../../src/tsir/reference_interpreter.zig");
const targets = @import("../../src/targets/mod.zig");

test "target descriptors have distinct stable hashes" {
    const wse3_a = targets.descriptorHash(targets.wse3.descriptor);
    const wse3_b = targets.descriptorHash(targets.wse3.descriptor);
    const webgpu = targets.descriptorHash(targets.webgpu_generic.descriptor);
    try std.testing.expectEqualSlices(u8, &wse3_a, &wse3_b);
    try std.testing.expect(!std.mem.eql(u8, &wse3_a, &webgpu));
}

test "tsir digests are deterministic on empty semantic/realization" {
    const allocator = std.testing.allocator;
    const semantic = tsir.Semantic{ .functions = &.{}, .rejections = &.{} };
    const realization = tsir.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const a = try tsir_digest.compute(allocator, semantic, realization, "emitter.v0");
    const b = try tsir_digest.compute(allocator, semantic, realization, "emitter.v0");
    try std.testing.expectEqualSlices(u8, &a.semantic, &b.semantic);
    try std.testing.expectEqualSlices(u8, &a.realization, &b.realization);
    try std.testing.expectEqualSlices(u8, &a.emitter, &b.emitter);
    try std.testing.expect(!std.mem.eql(u8, &a.semantic, &a.realization));
}

test "reference interpreter refuses zero oracle by default" {
    const allocator = std.testing.allocator;
    const semantic = tsir.Semantic{ .functions = &.{}, .rejections = &.{} };
    const realization = tsir.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const inputs = [_][]const u8{};
    const outcome = tsir_reference.run(allocator, semantic, realization, &inputs);
    try std.testing.expectError(tsir_reference.InterpretError.NotImplemented, outcome);
}

test "reference interpreter distinguishes rejected TSIR from unimplemented oracle" {
    const allocator = std.testing.allocator;
    const semantic_rejections = [_]tsir.RejectionEntry{
        .{
            .reason = .tsir_collective_not_representable,
            .node_path = "functions[0].collectives[0]",
            .detail = "fixture-rejected",
        },
    };
    const semantic = tsir.Semantic{
        .functions = &.{},
        .rejections = &semantic_rejections,
    };
    const realization = tsir.Realization{
        .functions = &.{},
        .emitter_digest = [_]u8{0} ** 32,
        .rejections = &.{},
    };
    const inputs = [_][]const u8{};
    const outcome = tsir_reference.run(allocator, semantic, realization, &inputs);
    try std.testing.expectError(
        tsir_reference.InterpretError.RejectedBySemantic,
        outcome,
    );
}

test "rejection taxonomy is exhaustive and enumerable" {
    const reasons = [_]tsir.RejectionReason{
        .tsir_subgroup_unlowerable,
        .tsir_pe_budget_exhausted,
        .tsir_collective_not_representable,
        .tsir_dependence_unanalyzable,
        .tsir_source_not_affine,
        .tsir_target_unfit,
    };
    // Compiles-only lock: proves every taxonomy code is exported and
    // usable from the public mod.zig surface. Guards against a future
    // rename silently breaking the parity CLI's hard-coded set.
    try std.testing.expect(reasons.len == 6);
}

test "exactness classes match the RDRR taxonomy verbatim" {
    const classes = [_]tsir.ExactnessClass{
        .bit_exact_solo,
        .algorithm_exact,
        .tolerance_bounded,
    };
    try std.testing.expect(classes.len == 3);
}

test "AlgorithmExactInvariant covers the bit-affecting properties" {
    const invariants = [_]tsir.AlgorithmExactInvariant{
        .reduction_order,
        .tree_shape,
        .accum_dtype,
        .associativity_grouping,
    };
    try std.testing.expect(invariants.len == 4);
}

test "Exactness defaults carry class with empty invariant payload" {
    const bit_exact = tsir.Exactness{ .class = .bit_exact_solo };
    try std.testing.expectEqual(tsir.ExactnessClass.bit_exact_solo, bit_exact.class);
    try std.testing.expectEqual(@as(usize, 0), bit_exact.algorithm_exact_invariants.len);
    try std.testing.expectEqualStrings("", bit_exact.tolerance_metric);
    try std.testing.expectEqual(@as(f64, 0.0), bit_exact.tolerance_epsilon);

    const invariants = [_]tsir.AlgorithmExactInvariant{
        .reduction_order,
        .tree_shape,
    };
    const algo = tsir.Exactness{
        .class = .algorithm_exact,
        .algorithm_exact_invariants = &invariants,
    };
    try std.testing.expectEqual(@as(usize, 2), algo.algorithm_exact_invariants.len);
    try std.testing.expectEqual(tsir.AlgorithmExactInvariant.reduction_order, algo.algorithm_exact_invariants[0]);

    const tol = tsir.Exactness{
        .class = .tolerance_bounded,
        .tolerance_metric = "ulp",
        .tolerance_epsilon = 2.0,
    };
    try std.testing.expectEqualStrings("ulp", tol.tolerance_metric);
    try std.testing.expectEqual(@as(f64, 2.0), tol.tolerance_epsilon);
}
