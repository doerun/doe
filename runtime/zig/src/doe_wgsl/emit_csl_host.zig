// emit_csl_host.zig — Host-plan emission for CSL execution scaffolds.
//
// This module does not lower Doppler execution-v1 directly. It renders host-side
// artifacts from an explicit HostPlan that a caller must derive from a higher-level
// execution contract.
//
// Generates:
//   1. A compilation manifest JSON listing kernels and launch phases.
//   2. A Python runner scaffold using Cerebras SDK conventions.
//   3. A conservative SRAM estimate for sizing discussion.

const std = @import("std");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
};

/// WSE-3 hardware constants used for conservative capacity estimates only.
pub const WSE3 = struct {
    pub const PE_COUNT: u32 = 900_000;
    pub const PE_SRAM_BYTES: u32 = 48 * 1024;
    pub const TOTAL_SRAM_BYTES: u64 = @as(u64, PE_COUNT) * PE_SRAM_BYTES;
};

/// Model configuration used for emitted constants and coarse SRAM estimates.
pub const ModelConfig = struct {
    hidden_dim: u32,
    num_heads: u32,
    head_dim: u32,
    num_layers: u32,
    vocab_size: u32,
    max_seq_len: u32,
    quant_format: QuantFormat,

    pub const QuantFormat = enum { f16, q4k, q8_0 };
};

pub const KernelSpec = struct {
    name: []const u8,
    pattern: []const u8,
    count: u32 = 1,
};

pub const LaunchSpec = struct {
    kernel_name: []const u8,
    repeat: u32 = 1,
};

/// Explicit host-side execution scaffold. Callers are responsible for deriving
/// this plan from execution-v1 or any other higher-level contract.
pub const HostPlan = struct {
    pe_grid_width: u32,
    pe_grid_height: u32 = 1,
    kernels: []const KernelSpec,
    prefill_launches: []const LaunchSpec,
    decode_launches: []const LaunchSpec,
    eos_token_id: ?u32 = null,
};

pub const SramEstimate = struct {
    per_layer_estimated_bytes: u64,
    embedding_estimated_bytes: u64,
    total_estimated_bytes: u64,
    capacity_bytes: u64,
    fits_within_capacity: bool,
    estimate_kind: []const u8,
};

const Q4K_UPPER_BOUND_BYTES_PER_WEIGHT: u64 = 1;
const Q8_0_BYTES_PER_WEIGHT: u64 = 1;
const F16_BYTES_PER_WEIGHT: u64 = 2;
const KV_CACHE_F16_BYTES_PER_VALUE: u64 = 2;
const FFN_EXPANSION_FACTOR: u64 = 4;
const PROJECTION_COUNT: u64 = 4;
const FFN_WEIGHT_MATRICES: u64 = 2;

fn conservativeBytesPerWeight(format: ModelConfig.QuantFormat) u64 {
    return switch (format) {
        .f16 => F16_BYTES_PER_WEIGHT,
        .q4k => Q4K_UPPER_BOUND_BYTES_PER_WEIGHT,
        .q8_0 => Q8_0_BYTES_PER_WEIGHT,
    };
}

/// Conservative per-layer estimate. This is not a placement proof.
pub fn estimateLayerSramBytes(config: ModelConfig) u64 {
    const hd: u64 = config.hidden_dim;
    const bytes_per_weight = conservativeBytesPerWeight(config.quant_format);
    const proj_bytes = PROJECTION_COUNT * hd * hd * bytes_per_weight;
    const ffn_bytes = FFN_WEIGHT_MATRICES * hd * FFN_EXPANSION_FACTOR * hd * bytes_per_weight;
    const kv_bytes = 2 * @as(u64, config.max_seq_len) * hd * KV_CACHE_F16_BYTES_PER_VALUE;
    return proj_bytes + ffn_bytes + kv_bytes;
}

pub fn estimateModelSram(config: ModelConfig) SramEstimate {
    const per_layer = estimateLayerSramBytes(config);
    const embed_bytes: u64 = @as(u64, config.vocab_size) * config.hidden_dim * F16_BYTES_PER_WEIGHT;
    const total = per_layer * config.num_layers + embed_bytes;
    return .{
        .per_layer_estimated_bytes = per_layer,
        .embedding_estimated_bytes = embed_bytes,
        .total_estimated_bytes = total,
        .capacity_bytes = WSE3.TOTAL_SRAM_BYTES,
        .fits_within_capacity = total <= WSE3.TOTAL_SRAM_BYTES,
        .estimate_kind = "conservative_upper_bound",
    };
}

pub fn emitCompilationManifest(
    buf: []u8,
    pos: *usize,
    config: ModelConfig,
    plan: HostPlan,
) EmitError!void {
    const estimate = estimateModelSram(config);

    try write(buf, pos, "{\n  \"target\": \"wse3\",\n");
    try write(buf, pos, "  \"contract\": \"explicit_host_plan\",\n");
    try write(buf, pos, "  \"pe_grid\": { \"width\": ");
    try writeInt(buf, pos, plan.pe_grid_width);
    try write(buf, pos, ", \"height\": ");
    try writeInt(buf, pos, plan.pe_grid_height);
    try write(buf, pos, " },\n");

    try write(buf, pos, "  \"sramEstimate\": {\n");
    try write(buf, pos, "    \"kind\": ");
    try writeJsonString(buf, pos, estimate.estimate_kind);
    try write(buf, pos, ",\n    \"perLayerEstimatedBytes\": ");
    try writeInt(buf, pos, estimate.per_layer_estimated_bytes);
    try write(buf, pos, ",\n    \"embeddingEstimatedBytes\": ");
    try writeInt(buf, pos, estimate.embedding_estimated_bytes);
    try write(buf, pos, ",\n    \"totalEstimatedBytes\": ");
    try writeInt(buf, pos, estimate.total_estimated_bytes);
    try write(buf, pos, ",\n    \"capacityBytes\": ");
    try writeInt(buf, pos, estimate.capacity_bytes);
    try write(buf, pos, ",\n    \"fitsWithinCapacity\": ");
    try writeBool(buf, pos, estimate.fits_within_capacity);
    try write(buf, pos, "\n  },\n");

    try write(buf, pos, "  \"kernels\": [\n");
    for (plan.kernels, 0..) |kernel, idx| {
        try write(buf, pos, "    { \"name\": ");
        try writeJsonString(buf, pos, kernel.name);
        try write(buf, pos, ", \"pattern\": ");
        try writeJsonString(buf, pos, kernel.pattern);
        try write(buf, pos, ", \"count\": ");
        try writeInt(buf, pos, kernel.count);
        try write(buf, pos, " }");
        if (idx + 1 < plan.kernels.len) try write(buf, pos, ",");
        try write(buf, pos, "\n");
    }
    try write(buf, pos, "  ],\n");

    try write(buf, pos, "  \"phases\": {\n    \"prefill\": [\n");
    try emitLaunchSpecsJson(buf, pos, plan.prefill_launches);
    try write(buf, pos, "    ],\n    \"decode\": [\n");
    try emitLaunchSpecsJson(buf, pos, plan.decode_launches);
    try write(buf, pos, "    ]\n  },\n");

    try write(buf, pos, "  \"eosTokenId\": ");
    if (plan.eos_token_id) |eos_token_id| {
        try writeInt(buf, pos, eos_token_id);
    } else {
        try write(buf, pos, "null");
    }
    try write(buf, pos, "\n}\n");
}

pub fn emitPythonRunner(
    buf: []u8,
    pos: *usize,
    config: ModelConfig,
    plan: HostPlan,
) EmitError!void {
    try write(buf, pos, "#!/usr/bin/env python3\n");
    try write(buf, pos, "\"\"\"CSL host runner scaffold generated from an explicit host plan.\"\"\"\n\n");
    try write(buf, pos, "import subprocess\nimport numpy as np\nimport json\n\n");

    try write(buf, pos, "HIDDEN_DIM = ");
    try writeInt(buf, pos, config.hidden_dim);
    try write(buf, pos, "\nNUM_HEADS = ");
    try writeInt(buf, pos, config.num_heads);
    try write(buf, pos, "\nHEAD_DIM = ");
    try writeInt(buf, pos, config.head_dim);
    try write(buf, pos, "\nNUM_LAYERS = ");
    try writeInt(buf, pos, config.num_layers);
    try write(buf, pos, "\nVOCAB_SIZE = ");
    try writeInt(buf, pos, config.vocab_size);
    try write(buf, pos, "\nPE_GRID_WIDTH = ");
    try writeInt(buf, pos, plan.pe_grid_width);
    try write(buf, pos, "\nPE_GRID_HEIGHT = ");
    try writeInt(buf, pos, plan.pe_grid_height);
    try write(buf, pos, "\nEOS_TOKEN_ID = ");
    if (plan.eos_token_id) |eos_token_id| {
        try writeInt(buf, pos, eos_token_id);
    } else {
        try write(buf, pos, "None");
    }
    try write(buf, pos, "\n\n");

    try write(buf, pos, "KERNELS = [\n");
    for (plan.kernels) |kernel| {
        try write(buf, pos, "    ");
        try writeJsonString(buf, pos, kernel.name);
        try write(buf, pos, ",\n");
    }
    try write(buf, pos, "]\n\n");

    try write(buf, pos, "PREFILL_LAUNCHES = [\n");
    try emitLaunchSpecsPython(buf, pos, plan.prefill_launches);
    try write(buf, pos, "]\n\n");

    try write(buf, pos, "DECODE_LAUNCHES = [\n");
    try emitLaunchSpecsPython(buf, pos, plan.decode_launches);
    try write(buf, pos, "]\n\n");

    try write(buf, pos,
        \\def compile_kernels():
        \\    """Compile kernels declared by the explicit host plan."""
        \\    for kernel_name in KERNELS:
        \\        subprocess.run([
        \\            'cslc', f'{kernel_name}/layout.csl',
        \\
    );
    try write(buf, pos, "            f'--fabric-dims={PE_GRID_WIDTH},{PE_GRID_HEIGHT}',\n");
    try write(buf, pos,
        \\            f'--params=width:{PE_GRID_WIDTH}',
        \\            '-o', f'{kernel_name}/out'
        \\        ], check=True)
        \\
        \\
    );

    try write(buf, pos,
        \\def load_shards(rdrr_path):
        \\    """Load RDRR shards using Doppler's shard schema fields."""
        \\    manifest = json.load(open(f'{rdrr_path}/manifest.json'))
        \\    shard_blobs = []
        \\    for shard in manifest['shards']:
        \\        filename = shard['filename']
        \\        blob = np.fromfile(f"{rdrr_path}/{filename}", dtype=np.uint8)
        \\        shard_blobs.append({
        \\            'index': shard.get('index'),
        \\            'filename': filename,
        \\            'offset': shard.get('offset'),
        \\            'size': shard.get('size'),
        \\            'data': blob,
        \\        })
        \\    return shard_blobs
        \\
        \\
    );

    try write(buf, pos,
        \\def run_launches(runner, launches):
        \\    for kernel_name, repeat in launches:
        \\        for _ in range(repeat):
        \\            runner.launch(kernel_name)
        \\
        \\
    );

    try write(buf, pos,
        \\def run_prefill(runner, token_ids):
        \\    runner.memcpy_h2d('indices', np.array(token_ids, dtype=np.uint32))
        \\    run_launches(runner, PREFILL_LAUNCHES)
        \\
        \\
    );

    try write(buf, pos,
        \\def run_decode_step(runner, token_id):
        \\    runner.memcpy_h2d('indices', np.array([token_id], dtype=np.uint32))
        \\    run_launches(runner, DECODE_LAUNCHES)
        \\    return runner.memcpy_d2h('output', dtype=np.uint32)
        \\
        \\
    );

    try write(buf, pos,
        \\def decode_loop(runner, prompt_ids, max_tokens=128):
        \\    """Autoregressive decode scaffold from the explicit host plan."""
        \\    generated = list(prompt_ids)
        \\    run_prefill(runner, prompt_ids)
        \\    while len(generated) < len(prompt_ids) + max_tokens:
        \\        token = run_decode_step(runner, generated[-1])
        \\        next_token = int(token[0])
        \\        if EOS_TOKEN_ID is not None and next_token == EOS_TOKEN_ID:
        \\            break
        \\        generated.append(next_token)
        \\    return generated
        \\
        \\
    );

    try write(buf, pos,
        \\if __name__ == '__main__':
        \\    compile_kernels()
        \\    shards = load_shards('model_rdrr')
        \\    try:
        \\        import cerebras.sdk.runtime as csl_rt
        \\        runner = csl_rt.SdkRunner()
        \\    except ImportError:
        \\        print('Cerebras SDK not available; emitted host scaffold only.')
        \\        raise SystemExit(0)
        \\    result = decode_loop(runner, [1])
        \\    print(f'Generated {len(result)} tokens from {len(shards)} shards')
        \\
    );
}

fn emitLaunchSpecsJson(buf: []u8, pos: *usize, launches: []const LaunchSpec) EmitError!void {
    for (launches, 0..) |launch, idx| {
        try write(buf, pos, "      { \"kernel\": ");
        try writeJsonString(buf, pos, launch.kernel_name);
        try write(buf, pos, ", \"repeat\": ");
        try writeInt(buf, pos, launch.repeat);
        try write(buf, pos, " }");
        if (idx + 1 < launches.len) try write(buf, pos, ",");
        try write(buf, pos, "\n");
    }
}

fn emitLaunchSpecsPython(buf: []u8, pos: *usize, launches: []const LaunchSpec) EmitError!void {
    for (launches) |launch| {
        try write(buf, pos, "    (");
        try writeJsonString(buf, pos, launch.kernel_name);
        try write(buf, pos, ", ");
        try writeInt(buf, pos, launch.repeat);
        try write(buf, pos, "),\n");
    }
}

fn writeJsonString(buf: []u8, pos: *usize, value: []const u8) EmitError!void {
    try write(buf, pos, "\"");
    for (value) |ch| {
        switch (ch) {
            '"' => try write(buf, pos, "\\\""),
            '\\' => try write(buf, pos, "\\\\"),
            '\n' => try write(buf, pos, "\\n"),
            else => {
                if (pos.* + 1 > buf.len) return error.OutputTooLarge;
                buf[pos.*] = ch;
                pos.* += 1;
            },
        }
    }
    try write(buf, pos, "\"");
}

fn writeBool(buf: []u8, pos: *usize, value: bool) EmitError!void {
    try write(buf, pos, if (value) "true" else "false");
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

test "SRAM estimate is explicit and conservative" {
    const qwen_08b = ModelConfig{
        .hidden_dim = 1024,
        .num_heads = 16,
        .head_dim = 64,
        .num_layers = 24,
        .vocab_size = 151936,
        .max_seq_len = 2048,
        .quant_format = .q4k,
    };
    const estimate = estimateModelSram(qwen_08b);
    try std.testing.expect(estimate.total_estimated_bytes > 0);
    try std.testing.expectEqualStrings("conservative_upper_bound", estimate.estimate_kind);
    try std.testing.expectEqual(WSE3.TOTAL_SRAM_BYTES, estimate.capacity_bytes);
}

test "compilation manifest emits explicit host plan phases" {
    const config = ModelConfig{
        .hidden_dim = 1024,
        .num_heads = 16,
        .head_dim = 64,
        .num_layers = 24,
        .vocab_size = 151936,
        .max_seq_len = 2048,
        .quant_format = .q4k,
    };
    const kernels = [_]KernelSpec{
        .{ .name = "embed_gather", .pattern = "gather", .count = 1 },
        .{ .name = "attention_decode", .pattern = "attention_decode", .count = 24 },
        .{ .name = "sample", .pattern = "sample", .count = 1 },
    };
    const prefill = [_]LaunchSpec{
        .{ .kernel_name = "embed_gather", .repeat = 1 },
        .{ .kernel_name = "attention_decode", .repeat = 24 },
    };
    const decode = [_]LaunchSpec{
        .{ .kernel_name = "attention_decode", .repeat = 24 },
        .{ .kernel_name = "sample", .repeat = 1 },
    };
    const plan = HostPlan{
        .pe_grid_width = 16,
        .pe_grid_height = 1,
        .kernels = &kernels,
        .prefill_launches = &prefill,
        .decode_launches = &decode,
        .eos_token_id = 151645,
    };
    var buf: [8192]u8 = undefined;
    var pos: usize = 0;
    try emitCompilationManifest(&buf, &pos, config, plan);
    const json_str = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, json_str, "\"explicit_host_plan\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json_str, "\"prefill\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json_str, "\"decode\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json_str, "\"attention_decode\"") != null);
}

test "Python runner uses filename-based shard loading and explicit launches" {
    const config = ModelConfig{
        .hidden_dim = 1024,
        .num_heads = 16,
        .head_dim = 64,
        .num_layers = 24,
        .vocab_size = 151936,
        .max_seq_len = 2048,
        .quant_format = .q4k,
    };
    const kernels = [_]KernelSpec{
        .{ .name = "embed_gather", .pattern = "gather", .count = 1 },
        .{ .name = "sample", .pattern = "sample", .count = 1 },
    };
    const prefill = [_]LaunchSpec{
        .{ .kernel_name = "embed_gather", .repeat = 1 },
    };
    const decode = [_]LaunchSpec{
        .{ .kernel_name = "sample", .repeat = 1 },
    };
    const plan = HostPlan{
        .pe_grid_width = 16,
        .pe_grid_height = 1,
        .kernels = &kernels,
        .prefill_launches = &prefill,
        .decode_launches = &decode,
        .eos_token_id = null,
    };
    var buf: [16384]u8 = undefined;
    var pos: usize = 0;
    try emitPythonRunner(&buf, &pos, config, plan);
    const script = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, script, "filename = shard['filename']") != null);
    try std.testing.expect(std.mem.indexOf(u8, script, "PREFILL_LAUNCHES") != null);
    try std.testing.expect(std.mem.indexOf(u8, script, "DECODE_LAUNCHES") != null);
    try std.testing.expect(std.mem.indexOf(u8, script, "EOS_TOKEN_ID = None") != null);
}
