// Cross-backend bootstrap canary for the Qwen-specific gated-activation
// op family.
//
// The exec-v1 opToSpec map (runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig)
// routes four paired-gate op identifiers — `gelu_gated` (Gemma GeGLU),
// `silu_gated` (SwiGLU FFN inner; Qwen 3.6 / Llama-style),
// `sigmoid_gated` (attentionOutputGate), and the alias `o_gate` (also
// sigmoid-gated). All four share the (gate, input) -> output binding
// shape and the chunk_size-axis emit pattern dispatched by
// emit_csl_semantic_ops.zig.
//
// This canary pins the op-to-pattern dispatch contract:
//   1) opToSpec returns a non-null spec for each gated op;
//   2) the spec's pattern is one the WGSL→CSL classifier recognizes;
//   3) the spec allows both prefill and decode phases (gated activations
//      ride both paths in Qwen 3.6 27B);
//   4) isPairedGateOp returns true for all four;
//   5) the o_gate alias resolves to the same `sigmoid_gated` pattern;
//   6) opToSpec returns null for an unrelated op string so the dispatch
//      table is closed (no swallow-everything default).
//
// Numeric pinning of the gated emit body lives in
// tsir_emit_kernel_body_test.zig. This file's job is the dispatch
// surface — when a smoke config says `op="silu_gated"`, the lowering
// pipeline must reach the silu_gated CSL emit and not silently fall
// back to a stand-in.

const std = @import("std");
const exec_v1 = @import("../../src/doe_wgsl/emit_csl_exec_v1.zig");
const host = @import("../../src/doe_wgsl/emit_csl_host.zig");
const semantic_ops = @import("../../src/doe_wgsl/emit_csl_semantic_ops.zig");

test "exec-v1 opToSpec routes gelu_gated to gelu_gated pattern" {
    const spec = exec_v1.opToSpec("gelu_gated") orelse return error.OpUnregistered;
    try std.testing.expectEqualStrings("gelu_gated", spec.pattern);
    try std.testing.expect(spec.allow_prefill);
    try std.testing.expect(spec.allow_decode);
    try std.testing.expect(spec.kind == .compute);
    try std.testing.expect(semantic_ops.isSemanticPattern(spec.pattern));
}

test "exec-v1 opToSpec routes silu_gated to silu_gated pattern" {
    const spec = exec_v1.opToSpec("silu_gated") orelse return error.OpUnregistered;
    try std.testing.expectEqualStrings("silu_gated", spec.pattern);
    try std.testing.expect(spec.allow_prefill);
    try std.testing.expect(spec.allow_decode);
    try std.testing.expect(spec.kind == .compute);
    try std.testing.expect(semantic_ops.isSemanticPattern(spec.pattern));
}

test "exec-v1 opToSpec routes sigmoid_gated to sigmoid_gated pattern" {
    const spec = exec_v1.opToSpec("sigmoid_gated") orelse return error.OpUnregistered;
    try std.testing.expectEqualStrings("sigmoid_gated", spec.pattern);
    try std.testing.expect(spec.allow_prefill);
    try std.testing.expect(spec.allow_decode);
    try std.testing.expect(spec.kind == .compute);
    try std.testing.expect(semantic_ops.isSemanticPattern(spec.pattern));
}

test "exec-v1 opToSpec aliases o_gate to sigmoid_gated pattern" {
    const o_gate = exec_v1.opToSpec("o_gate") orelse return error.OpUnregistered;
    const sigmoid = exec_v1.opToSpec("sigmoid_gated") orelse return error.OpUnregistered;
    try std.testing.expectEqualStrings("sigmoid_gated", o_gate.pattern);
    try std.testing.expectEqualStrings(sigmoid.pattern, o_gate.pattern);
    try std.testing.expectEqual(sigmoid.kind, o_gate.kind);
    try std.testing.expectEqual(sigmoid.allow_prefill, o_gate.allow_prefill);
    try std.testing.expectEqual(sigmoid.allow_decode, o_gate.allow_decode);
    try std.testing.expect(semantic_ops.isSemanticPattern(o_gate.pattern));
}

test "exec-v1 isPairedGateOp covers all four gated identifiers" {
    try std.testing.expect(exec_v1.isPairedGateOp("gelu_gated"));
    try std.testing.expect(exec_v1.isPairedGateOp("silu_gated"));
    try std.testing.expect(exec_v1.isPairedGateOp("sigmoid_gated"));
    try std.testing.expect(exec_v1.isPairedGateOp("o_gate"));
}

test "exec-v1 isPairedGateOp rejects non-gated ops" {
    try std.testing.expect(!exec_v1.isPairedGateOp("silu"));
    try std.testing.expect(!exec_v1.isPairedGateOp("gelu"));
    try std.testing.expect(!exec_v1.isPairedGateOp("residual"));
    try std.testing.expect(!exec_v1.isPairedGateOp("rmsnorm"));
    try std.testing.expect(!exec_v1.isPairedGateOp(""));
}

test "exec-v1 opToSpec returns null for an unrelated op so the table is closed" {
    try std.testing.expect(exec_v1.opToSpec("definitely_not_a_real_op") == null);
    try std.testing.expect(exec_v1.opToSpec("") == null);
}

test "exec-v1 opToPattern matches opToSpec.pattern for every gated op" {
    const ops = [_][]const u8{ "gelu_gated", "silu_gated", "sigmoid_gated", "o_gate" };
    for (ops) |op| {
        const spec = exec_v1.opToSpec(op) orelse return error.OpUnregistered;
        const pattern = exec_v1.opToPattern(op) orelse return error.OpUnregistered;
        try std.testing.expectEqualStrings(spec.pattern, pattern);
    }
}

test "lowerJsonToHostPlan accepts paired-gate ops with inputsFrom" {
    // Qwen 3.6 27B smoke shape: silu_gated FFN + o_gate (sigmoid_gated)
    // attention output gate. Both are paired-input ops; inputsFrom must
    // be present with two upstream step names.
    const json_payload =
        \\{
        \\  "grid": { "width": 8, "height": 1 },
        \\  "steps": [
        \\    { "phase": "prefill", "op": "embed", "kernelKey": "embed" },
        \\    { "phase": "prefill", "op": "matmul", "kernelKey": "tiled_q", "weightsKey": "q_proj" },
        \\    { "phase": "prefill", "op": "attention_prefill", "kernelKey": "attn_prefill" },
        \\    { "phase": "prefill", "op": "o_gate", "kernelKey": "o_gate", "inputsFrom": ["tiled_q", "attn_prefill"] },
        \\    { "phase": "prefill", "op": "matmul", "kernelKey": "tiled_gate", "weightsKey": "gate_proj" },
        \\    { "phase": "prefill", "op": "matmul", "kernelKey": "tiled_up", "weightsKey": "up_proj" },
        \\    { "phase": "prefill", "op": "silu_gated", "kernelKey": "silu_gated", "inputsFrom": ["tiled_gate", "tiled_up"] },
        \\    { "phase": "decode", "op": "attention", "kernelKey": "attn_decode" },
        \\    { "phase": "decode", "op": "sample", "kernelKey": "sampler", "kind": "sample" }
        \\  ]
        \\}
    ;

    var kernels: [32]host.KernelSpec = undefined;
    var prefill: [32]host.LaunchSpec = undefined;
    var decode: [32]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    const plan = try exec_v1.lowerJsonToHostPlan(arena.allocator(), json_payload, &kernels, &prefill, &decode);
    try std.testing.expect(plan.prefill_launches.len == 7);
    try std.testing.expect(plan.decode_launches.len == 2);

    var saw_o_gate = false;
    var saw_silu_gated = false;
    for (plan.kernels) |k| {
        if (std.mem.eql(u8, k.name, "o_gate")) {
            try std.testing.expectEqualStrings("sigmoid_gated", k.pattern);
            saw_o_gate = true;
        }
        if (std.mem.eql(u8, k.name, "silu_gated")) {
            try std.testing.expectEqualStrings("silu_gated", k.pattern);
            saw_silu_gated = true;
        }
    }
    try std.testing.expect(saw_o_gate);
    try std.testing.expect(saw_silu_gated);
}

test "lowerJsonToHostPlan rejects paired-gate op missing inputsFrom" {
    const json_payload =
        \\{
        \\  "grid": { "width": 8, "height": 1 },
        \\  "steps": [
        \\    { "phase": "prefill", "op": "embed", "kernelKey": "embed" },
        \\    { "phase": "prefill", "op": "silu_gated", "kernelKey": "silu_gated" }
        \\  ]
        \\}
    ;

    var kernels: [4]host.KernelSpec = undefined;
    var prefill: [4]host.LaunchSpec = undefined;
    var decode: [4]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    try std.testing.expectError(
        error.MalformedStep,
        exec_v1.lowerJsonToHostPlan(arena.allocator(), json_payload, &kernels, &prefill, &decode),
    );
}

test "lowerJsonToHostPlan rejects paired-gate op with wrong inputsFrom arity" {
    const json_payload =
        \\{
        \\  "grid": { "width": 8, "height": 1 },
        \\  "steps": [
        \\    { "phase": "prefill", "op": "embed", "kernelKey": "embed" },
        \\    { "phase": "prefill", "op": "matmul", "kernelKey": "g", "weightsKey": "w" },
        \\    { "phase": "prefill", "op": "silu_gated", "kernelKey": "silu_gated", "inputsFrom": ["g"] }
        \\  ]
        \\}
    ;

    var kernels: [4]host.KernelSpec = undefined;
    var prefill: [4]host.LaunchSpec = undefined;
    var decode: [4]host.LaunchSpec = undefined;
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();

    try std.testing.expectError(
        error.MalformedStep,
        exec_v1.lowerJsonToHostPlan(arena.allocator(), json_payload, &kernels, &prefill, &decode),
    );
}
