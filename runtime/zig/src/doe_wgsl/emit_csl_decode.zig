// emit_csl_decode.zig — Decode-loop correctness primitives for CSL emission.
//
// Provides position tracking, KV cache append coordination, EOS detection,
// and batch sequence management for autoregressive decode on WSE-3.
//
// These are emitted as CSL helper functions and state variables that the
// pattern emitters (attention, RoPE, sample) reference during decode steps.

const std = @import("std");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

/// Decode configuration governing position tracking and sequence limits.
pub const DecodeConfig = struct {
    max_seq_len: u32,
    num_layers: u32,
    head_dim: u32,
    num_kv_heads: u32 = 0,
    eos_token_id: ?u32 = null,
    batch_size: u32 = 1,
};

/// Emit position-tracking state variables for the decode loop.
/// These are referenced by RoPE (for cos/sin lookup) and KV cache (for append index).
pub fn emitPositionState(buf: []u8, pos: *usize, config: DecodeConfig) EmitError!void {
    try W.write(buf, pos, "// --- Decode position tracking ---\n");
    try W.write(buf, pos, "var seq_position: u32 = 0;\n");
    try W.write(buf, pos, "const MAX_SEQ_LEN: u32 = ");
    try W.writeInt(buf, pos, config.max_seq_len);
    try W.write(buf, pos, ";\n");
    if (config.batch_size > 1) {
        try W.write(buf, pos, "var batch_positions: [");
        try W.writeInt(buf, pos, config.batch_size);
        try W.write(buf, pos, "]u32 = @zeros([");
        try W.writeInt(buf, pos, config.batch_size);
        try W.write(buf, pos, "]u32);\n");
    }
    try W.write(buf, pos, "\n");
}

/// Emit KV cache append logic that writes projected K/V at the current position.
/// Each layer has its own K and V cache buffers indexed by seq_position.
pub fn emitKvCacheAppend(buf: []u8, pos: *usize, config: DecodeConfig) EmitError!void {
    try W.write(buf, pos, "// --- KV cache append ---\n");
    try W.write(buf, pos, "fn kv_cache_append(\n");
    try W.write(buf, pos, "    layer: u32,\n");
    try W.write(buf, pos, "    k_proj: [*]const f16,\n");
    try W.write(buf, pos, "    v_proj: [*]const f16,\n");
    try W.write(buf, pos, "    position: u32,\n");
    try W.write(buf, pos, ") void {\n");
    try W.write(buf, pos, "    const HEAD_DIM: u32 = ");
    try W.writeInt(buf, pos, config.head_dim);
    try W.write(buf, pos, ";\n");
    try W.write(buf, pos, "    const offset = position * HEAD_DIM;\n");
    try W.write(buf, pos, "    // K cache: layer * MAX_SEQ_LEN * HEAD_DIM + offset\n");
    try W.write(buf, pos, "    const k_base = layer * MAX_SEQ_LEN * HEAD_DIM + offset;\n");
    try W.write(buf, pos, "    const v_base = k_base;\n");
    try W.write(buf, pos, "    for (@range(u32, HEAD_DIM)) |d| {\n");
    try W.write(buf, pos, "        kv_cache_k[k_base + d] = k_proj[d];\n");
    try W.write(buf, pos, "        kv_cache_v[v_base + d] = v_proj[d];\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");
}

/// Emit position advance + sequence length check.
pub fn emitPositionAdvance(buf: []u8, pos: *usize) EmitError!void {
    try W.write(buf, pos, "// --- Position advance ---\n");
    try W.write(buf, pos, "fn advance_position() bool {\n");
    try W.write(buf, pos, "    seq_position += 1;\n");
    try W.write(buf, pos, "    return seq_position < MAX_SEQ_LEN;\n");
    try W.write(buf, pos, "}\n\n");
}

/// Emit EOS detection helper.
pub fn emitEosCheck(buf: []u8, pos: *usize, config: DecodeConfig) EmitError!void {
    if (config.eos_token_id) |eos| {
        try W.write(buf, pos, "// --- EOS detection ---\n");
        try W.write(buf, pos, "const EOS_TOKEN_ID: u32 = ");
        try W.writeInt(buf, pos, eos);
        try W.write(buf, pos, ";\n\n");
        try W.write(buf, pos, "fn is_eos(token_id: u32) bool {\n");
        try W.write(buf, pos, "    return token_id == EOS_TOKEN_ID;\n");
        try W.write(buf, pos, "}\n\n");
    }
}

/// Emit RoPE position-aware cos/sin lookup helpers.
/// These compute cos(pos * freq) and sin(pos * freq) for rotary embeddings.
pub fn emitRopePositionLookup(buf: []u8, pos: *usize, config: DecodeConfig) EmitError!void {
    try W.write(buf, pos, "// --- RoPE position-aware frequency computation ---\n");
    try W.write(buf, pos, "const ROPE_BASE: f32 = 10000.0;\n");
    try W.write(buf, pos, "const ROPE_HEAD_DIM: u32 = ");
    try W.writeInt(buf, pos, config.head_dim);
    try W.write(buf, pos, ";\n\n");
    try W.write(buf, pos, "fn rope_freq(dim_idx: u32) f32 {\n");
    try W.write(buf, pos, "    const exp = @as(f32, dim_idx * 2) / @as(f32, ROPE_HEAD_DIM);\n");
    try W.write(buf, pos, "    return 1.0 / @exp2(exp * @log2(ROPE_BASE));\n");
    try W.write(buf, pos, "}\n\n");
    try W.write(buf, pos, "fn rope_apply(\n");
    try W.write(buf, pos, "    x0: f32, x1: f32,\n");
    try W.write(buf, pos, "    position: u32, dim_idx: u32,\n");
    try W.write(buf, pos, ") struct { r0: f32, r1: f32 } {\n");
    try W.write(buf, pos, "    const freq = rope_freq(dim_idx);\n");
    try W.write(buf, pos, "    const angle = @as(f32, position) * freq;\n");
    try W.write(buf, pos, "    const cos_a = @cos(angle);\n");
    try W.write(buf, pos, "    const sin_a = @sin(angle);\n");
    try W.write(buf, pos, "    return .{\n");
    try W.write(buf, pos, "        .r0 = x0 * cos_a - x1 * sin_a,\n");
    try W.write(buf, pos, "        .r1 = x0 * sin_a + x1 * cos_a,\n");
    try W.write(buf, pos, "    };\n");
    try W.write(buf, pos, "}\n\n");
}

/// Emit the full decode-step orchestration function that coordinates
/// position tracking, KV append, and step advancement.
pub fn emitDecodeStepOrchestrator(buf: []u8, pos: *usize, config: DecodeConfig) EmitError!void {
    try W.write(buf, pos, "// --- Decode step orchestrator ---\n");
    try W.write(buf, pos, "fn decode_step() void {\n");
    try W.write(buf, pos, "    // Apply RoPE at current position (cos/sin computed from seq_position)\n");
    try W.write(buf, pos, "    // Append K/V projections to cache at seq_position\n");
    for (0..config.num_layers) |layer_idx| {
        try W.write(buf, pos, "    kv_cache_append(");
        try W.writeInt(buf, pos, @as(u32, @intCast(layer_idx)));
        try W.write(buf, pos, ", &k_proj, &v_proj, seq_position);\n");
    }
    try W.write(buf, pos, "    // Advance position for next step\n");
    try W.write(buf, pos, "    _ = advance_position();\n");
    try W.write(buf, pos, "}\n\n");
}

/// Emit all decode primitives as a combined block.
pub fn emitAllDecodePrimitives(buf: []u8, pos: *usize, config: DecodeConfig) EmitError!void {
    try emitPositionState(buf, pos, config);
    try emitKvCacheAppend(buf, pos, config);
    try emitPositionAdvance(buf, pos);
    try emitEosCheck(buf, pos, config);
    try emitRopePositionLookup(buf, pos, config);
}

test "decode position state emits seq_position and MAX_SEQ_LEN" {
    const config = DecodeConfig{
        .max_seq_len = 2048,
        .num_layers = 24,
        .head_dim = 64,
    };
    var buf: [4096]u8 = undefined;
    var pos: usize = 0;
    try emitPositionState(&buf, &pos, config);
    const text = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, text, "seq_position") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "2048") != null);
}

test "decode position state emits batch_positions for batch > 1" {
    const config = DecodeConfig{
        .max_seq_len = 2048,
        .num_layers = 24,
        .head_dim = 64,
        .batch_size = 4,
    };
    var buf: [4096]u8 = undefined;
    var pos: usize = 0;
    try emitPositionState(&buf, &pos, config);
    const text = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, text, "batch_positions") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "[4]u32") != null);
}

test "KV cache append references head_dim and position" {
    const config = DecodeConfig{
        .max_seq_len = 2048,
        .num_layers = 24,
        .head_dim = 64,
    };
    var buf: [4096]u8 = undefined;
    var pos: usize = 0;
    try emitKvCacheAppend(&buf, &pos, config);
    const text = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, text, "kv_cache_k") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "kv_cache_v") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "HEAD_DIM") != null);
}

test "EOS check emitted only when eos_token_id is set" {
    var buf: [4096]u8 = undefined;
    var pos: usize = 0;
    const no_eos = DecodeConfig{ .max_seq_len = 2048, .num_layers = 24, .head_dim = 64 };
    try emitEosCheck(&buf, &pos, no_eos);
    try std.testing.expect(pos == 0);

    pos = 0;
    const with_eos = DecodeConfig{ .max_seq_len = 2048, .num_layers = 24, .head_dim = 64, .eos_token_id = 151645 };
    try emitEosCheck(&buf, &pos, with_eos);
    try std.testing.expect(std.mem.indexOf(u8, buf[0..pos], "151645") != null);
    try std.testing.expect(std.mem.indexOf(u8, buf[0..pos], "is_eos") != null);
}

test "RoPE position lookup emits freq computation" {
    const config = DecodeConfig{ .max_seq_len = 2048, .num_layers = 24, .head_dim = 128 };
    var buf: [4096]u8 = undefined;
    var pos: usize = 0;
    try emitRopePositionLookup(&buf, &pos, config);
    const text = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, text, "rope_freq") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "rope_apply") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "10000.0") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "128") != null);
}

test "all decode primitives emit combined block" {
    const config = DecodeConfig{
        .max_seq_len = 4096,
        .num_layers = 32,
        .head_dim = 64,
        .eos_token_id = 2,
    };
    var buf: [16384]u8 = undefined;
    var pos: usize = 0;
    try emitAllDecodePrimitives(&buf, &pos, config);
    const text = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, text, "seq_position") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "kv_cache_append") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "advance_position") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "is_eos") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "rope_apply") != null);
}
