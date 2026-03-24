// emit_csl_mem_plan.zig — SRAM memory planning for WSE-3 deployment.
//
// Computes PE↔weight mapping, persistent vs streamed buffer placement,
// KV cache allocation, and per-PE SRAM partitioning.
//
// This is a planning module — it produces a placement plan that the host
// runtime uses to stage data. It does not emit CSL code directly.

const std = @import("std");
const spec = @import("csl_spec.zig");
const host = @import("emit_csl_host.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
};

pub const BufferPlacement = enum {
    /// Statically loaded at init, persists across all launches.
    persistent,
    /// Streamed per-launch via memcpy, overwritten each time.
    streamed,
    /// KV cache: persistent but grows during decode.
    kv_cache,
};

pub const BufferPlan = struct {
    name: []const u8,
    placement: BufferPlacement,
    bytes_per_pe: u64,
    total_bytes: u64,
};

pub const PePlan = struct {
    /// Bytes used by persistent (weight) data on each PE.
    weight_bytes: u64,
    /// Bytes reserved for KV cache growth.
    kv_cache_bytes: u64,
    /// Bytes for streamed activation buffers.
    activation_bytes: u64,
    /// Total = weight + kv_cache + activation.
    total_bytes: u64,
    /// Does this PE's allocation fit in SRAM?
    fits: bool,
};

pub const MemoryPlan = struct {
    pe_count: u32,
    per_pe: PePlan,
    total_sram_used: u64,
    total_sram_available: u64,
    utilization_pct: u32,
    buffers: [MAX_BUFFERS]BufferPlan,
    buffer_count: u32,
};

const MAX_BUFFERS: usize = 64;

/// Plan SRAM placement for a Qwen-class model.
/// This is a coarse upper-bound planner. Fine-grained placement requires
/// per-layer analysis that is not yet implemented.
pub fn planMemory(config: host.ModelConfig, grid_width: u32) MemoryPlan {
    const pe_count = grid_width;
    const hd: u64 = config.hidden_dim;
    const bpw = bytesPerWeight(config.quant_format);

    // Weight distribution: each PE gets 1/pe_count of each weight matrix
    const attn_weight_bytes = 4 * hd * hd * bpw; // Q, K, V, O projections
    const ffn_weight_bytes = 3 * hd * 4 * hd * bpw; // gate, up, down (4x expansion)
    const layer_weight_bytes = attn_weight_bytes + ffn_weight_bytes;
    const total_weight_bytes = layer_weight_bytes * config.num_layers;
    const weight_per_pe = total_weight_bytes / pe_count;

    // KV cache: 2 * num_layers * max_seq_len * head_dim * 2 (f16)
    const head_dim: u64 = config.head_dim;
    const kv_per_head = 2 * @as(u64, config.max_seq_len) * head_dim * 2;
    const kv_total = kv_per_head * config.num_heads * config.num_layers;
    const kv_per_pe = kv_total / pe_count;

    // Activation scratch: one layer's worth of activations
    const act_per_pe = hd * 4 / pe_count * 4; // f32, one hidden vector

    const total_per_pe = weight_per_pe + kv_per_pe + act_per_pe;
    const fits = total_per_pe <= spec.PE_SRAM_BYTES;

    return .{
        .pe_count = pe_count,
        .per_pe = .{
            .weight_bytes = weight_per_pe,
            .kv_cache_bytes = kv_per_pe,
            .activation_bytes = act_per_pe,
            .total_bytes = total_per_pe,
            .fits = fits,
        },
        .total_sram_used = total_per_pe * pe_count,
        .total_sram_available = @as(u64, pe_count) * spec.PE_SRAM_BYTES,
        .utilization_pct = @intCast(@min(100, total_per_pe * 100 / spec.PE_SRAM_BYTES)),
        .buffers = undefined,
        .buffer_count = 0,
    };
}

/// Emit the memory plan as JSON for host-side consumption.
pub fn emitPlanJson(buf: []u8, pos: *usize, plan: MemoryPlan) EmitError!void {
    try write(buf, pos, "{\n  \"peCount\": ");
    try writeInt(buf, pos, plan.pe_count);
    try write(buf, pos, ",\n  \"perPe\": {\n");
    try write(buf, pos, "    \"weightBytes\": ");
    try writeInt(buf, pos, plan.per_pe.weight_bytes);
    try write(buf, pos, ",\n    \"kvCacheBytes\": ");
    try writeInt(buf, pos, plan.per_pe.kv_cache_bytes);
    try write(buf, pos, ",\n    \"activationBytes\": ");
    try writeInt(buf, pos, plan.per_pe.activation_bytes);
    try write(buf, pos, ",\n    \"totalBytes\": ");
    try writeInt(buf, pos, plan.per_pe.total_bytes);
    try write(buf, pos, ",\n    \"fits\": ");
    try write(buf, pos, if (plan.per_pe.fits) "true" else "false");
    try write(buf, pos, ",\n    \"sramCapacity\": ");
    try writeInt(buf, pos, @as(u64, spec.PE_SRAM_BYTES));
    try write(buf, pos, "\n  },\n");
    try write(buf, pos, "  \"totalSramUsed\": ");
    try writeInt(buf, pos, plan.total_sram_used);
    try write(buf, pos, ",\n  \"totalSramAvailable\": ");
    try writeInt(buf, pos, plan.total_sram_available);
    try write(buf, pos, ",\n  \"utilizationPct\": ");
    try writeInt(buf, pos, plan.utilization_pct);
    try write(buf, pos, "\n}\n");
}

fn bytesPerWeight(format: host.ModelConfig.QuantFormat) u64 {
    return switch (format) {
        .f16 => 2,
        .q4k => 1,
        .q8_0 => 1,
    };
}

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}

fn writeInt(buf: []u8, pos: *usize, value: anytype) EmitError!void {
    var tmp: [32]u8 = undefined;
    const slice = std.fmt.bufPrint(&tmp, "{d}", .{value}) catch return error.OutputTooLarge;
    try write(buf, pos, slice);
}

test "memory plan for Qwen 0.5B Q4K" {
    const config = host.ModelConfig{
        .hidden_dim = 1024,
        .num_heads = 16,
        .head_dim = 64,
        .num_layers = 24,
        .vocab_size = 151936,
        .max_seq_len = 2048,
        .quant_format = .q4k,
    };
    const plan = planMemory(config, 256);
    try std.testing.expect(plan.pe_count == 256);
    try std.testing.expect(plan.per_pe.total_bytes > 0);
    try std.testing.expect(plan.per_pe.weight_bytes > 0);
    try std.testing.expect(plan.per_pe.kv_cache_bytes > 0);
}

test "memory plan JSON emits valid structure" {
    const config = host.ModelConfig{
        .hidden_dim = 1024,
        .num_heads = 16,
        .head_dim = 64,
        .num_layers = 24,
        .vocab_size = 151936,
        .max_seq_len = 2048,
        .quant_format = .q4k,
    };
    const plan = planMemory(config, 256);
    var buf: [4096]u8 = undefined;
    var pos: usize = 0;
    try emitPlanJson(&buf, &pos, plan);
    const json = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, json, "\"peCount\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json, "\"fits\"") != null);
}
