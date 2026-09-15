// Diagnostic WGSL stage timings. Whole-process success requires every selected
// shader/stage to complete; partial NDJSON is never a successful benchmark.

const std = @import("std");
const doe = @import("doe");
const parser_mod = doe.compiler.wgsl_frontend.parser();
const sema_mod = doe.compiler.wgsl_frontend.sema();
const ir_builder_mod = doe.compiler.wgsl_ir.builder();
const ir_opt_rewrite_mod = doe.compiler.wgsl_ir.optimize();
const ir_validate_mod = doe.compiler.wgsl_ir.validate();
const emit_msl_mod = doe.compiler.wgsl_emit.msl();
const emit_spirv_mod = doe.compiler.wgsl_emit.spirv();
const emit_hlsl_mod = doe.compiler.wgsl_emit.hlsl();
const ir_mod = doe.compiler.wgsl_ir.core();
const lean_proof = doe.verification.leanProof();

const DEFAULT_ITERATIONS: u32 = 500;
const DEFAULT_WARMUP: u32 = 20;
const MAX_SAMPLES: u32 = 2000;

const MSL_BUF_SIZE: usize = emit_msl_mod.MAX_OUTPUT;
const SPIRV_BUF_SIZE: usize = emit_spirv_mod.MAX_OUTPUT;
const HLSL_BUF_SIZE: usize = emit_hlsl_mod.MAX_OUTPUT;

const Shader = struct {
    name: []const u8,
    source: []const u8,
};

const SHADERS = [_]Shader{
    .{
        .name = "compute_simple",
        .source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = data[id.x] * 2.0;
        \\}
        ,
    },
    .{
        .name = "compute_matmul",
        .source =
        \\struct Dims { M: u32, N: u32, K: u32, }
        \\@group(0) @binding(0) var<storage, read> a: array<f32>;
        \\@group(0) @binding(1) var<storage, read> b: array<f32>;
        \\@group(0) @binding(2) var<storage, read_write> c: array<f32>;
        \\@group(0) @binding(3) var<uniform> dims: Dims;
        \\@compute @workgroup_size(8, 8) fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    let row = gid.y;
        \\    let col = gid.x;
        \\    if (row >= dims.M) { return; }
        \\    if (col >= dims.N) { return; }
        \\    var acc: f32 = 0.0;
        \\    for (var k: u32 = 0u; k < dims.K; k = k + 1u) {
        \\        acc = acc + a[row * dims.K + k] * b[k * dims.N + col];
        \\    }
        \\    c[row * dims.N + col] = acc;
        \\}
        ,
    },
    .{
        .name = "vertex_struct_io",
        .source =
        \\struct VertIn { @location(0) pos: vec4f, @location(1) uv: vec2f, }
        \\struct VertOut { @builtin(position) clip_pos: vec4f, @location(0) uv: vec2f, }
        \\@vertex fn vs_main(in: VertIn) -> VertOut {
        \\    var out: VertOut;
        \\    out.clip_pos = in.pos;
        \\    out.uv = in.uv;
        \\    return out;
        \\}
        ,
    },
    .{
        .name = "fragment_math",
        .source =
        \\@fragment fn fs_main(@location(0) uv: vec2f, @builtin(position) pos: vec4f) -> @location(0) vec4f {
        \\    let r = uv.x;
        \\    let g = uv.y;
        \\    let b = 1.0 - r * g;
        \\    let a = clamp(pos.z, 0.0, 1.0);
        \\    return vec4f(r, g, b, a);
        \\}
        ,
    },
    .{
        .name = "fragment_discard",
        .source =
        \\@fragment fn fs_main(@builtin(position) pos: vec4f, @builtin(front_facing) ff: bool) -> @location(0) vec4f {
        \\    if (!ff) { discard; }
        \\    return vec4f(pos.x, pos.y, 0.0, 1.0);
        \\}
        ,
    },
};

const Stage = enum {
    analyze_to_ir,
    emit_msl,
    emit_spirv,
    emit_hlsl,
    e2e_msl,
    e2e_spirv,
    e2e_hlsl,
};

const Config = struct {
    iterations: u32 = DEFAULT_ITERATIONS,
    warmup: u32 = DEFAULT_WARMUP,
    out_path: ?[]const u8 = null,
    filter: ?[]const u8 = null,
};

// The argument owner must outlive this borrowed configuration.
fn parseArgs(args: []const []const u8) !Config {
    var config = Config{};
    var index: usize = 0;
    while (index < args.len) : (index += 2) {
        const option = args[index];
        const Option = enum { iterations, warmup, out, filter };
        const selected = if (std.mem.startsWith(u8, option, "--"))
            std.meta.stringToEnum(Option, option[2..])
        else
            null;
        const kind = selected orelse {
            std.debug.print("unknown option '{s}'; expected --iterations, --warmup, --out, or --filter\n", .{option});
            return error.UnknownArgument;
        };
        if (index + 1 == args.len) {
            std.debug.print("missing value for {s}\n", .{option});
            return error.MissingArgumentValue;
        }
        const value = args[index + 1];
        switch (kind) {
            .iterations => config.iterations = try parseCount(option, value),
            .warmup => config.warmup = try parseCount(option, value),
            .out => config.out_path = value,
            .filter => config.filter = value,
        }
    }
    if (config.iterations == 0 or config.iterations > MAX_SAMPLES) {
        std.debug.print("--iterations must be between 1 and {d}; received {d}\n", .{ MAX_SAMPLES, config.iterations });
        return error.InvalidIterations;
    }
    if (config.filter) |name| {
        for (SHADERS) |shader| {
            if (std.mem.eql(u8, name, shader.name)) return config;
        }
        std.debug.print("unknown shader filter '{s}'; expected a built-in corpus name\n", .{name});
        return error.UnknownShader;
    }
    return config;
}

fn parseCount(option: []const u8, value: []const u8) !u32 {
    return std.fmt.parseInt(u32, value, 10) catch |err| {
        std.debug.print("{s} requires an unsigned integer; received '{s}': {s}\n", .{ option, value, @errorName(err) });
        return err;
    };
}

const Stats = struct {
    min_ns: u64,
    max_ns: u64,
    mean_ns: u64,
    p50_ns: u64,
    p95_ns: u64,
    p99_ns: u64,
};

fn computeStats(samples: []u64) !Stats {
    if (samples.len == 0) return error.EmptySamples;
    std.sort.block(u64, samples, {}, std.sort.asc(u64));

    const n = samples.len;
    var sum: u128 = 0;
    for (samples) |s| sum += s;

    const p50_idx = n / 2;
    const p95_idx = (n * 95) / 100;
    const p99_idx = (n * 99) / 100;

    return .{
        .min_ns = samples[0],
        .max_ns = samples[n - 1],
        .mean_ns = @intCast(sum / n),
        .p50_ns = samples[p50_idx],
        .p95_ns = samples[p95_idx],
        .p99_ns = samples[p99_idx],
    };
}

fn writeResult(
    writer: std.fs.File.DeprecatedWriter,
    shader_name: []const u8,
    stage_name: []const u8,
    iterations: u32,
    warmup: u32,
    stats: Stats,
    bytes_out: usize,
) !void {
    try writer.print(
        "{{\"kind\":\"shader_bench\",\"shader\":\"{s}\",\"stage\":\"{s}\"," ++
            "\"iterations\":{d},\"warmup\":{d}," ++
            "\"p50_ns\":{d},\"p95_ns\":{d},\"p99_ns\":{d}," ++
            "\"min_ns\":{d},\"max_ns\":{d},\"mean_ns\":{d},\"bytes_out\":{d}}}\n",
        .{
            shader_name,
            stage_name,
            iterations,
            warmup,
            stats.p50_ns,
            stats.p95_ns,
            stats.p99_ns,
            stats.min_ns,
            stats.max_ns,
            stats.mean_ns,
            bytes_out,
        },
    );
}

// This spelling is referenced by config/lean-proof-patterns.json.
fn maybe_validate_module(module: *const ir_mod.Module) !void {
    if (lean_proof.validator_elimination_available) return;
    try ir_validate_mod.validate(module);
}

fn buildReferenceModule(allocator: std.mem.Allocator, source: []const u8) !ir_mod.Module {
    var tree = try parser_mod.parseSource(allocator, source);
    defer tree.deinit();
    var semantic = try sema_mod.analyze(allocator, &tree);
    defer semantic.deinit();
    var module = try ir_builder_mod.build(allocator, &tree, &semantic);
    errdefer module.deinit();
    try maybe_validate_module(&module);
    _ = try ir_opt_rewrite_mod.apply(allocator, &module);
    return module;
}

fn emitStage(stage: Stage, module: *const ir_mod.Module, output: []u8) !usize {
    return switch (stage) {
        .emit_msl, .e2e_msl => emit_msl_mod.emit(module, output),
        .emit_spirv, .e2e_spirv => emit_spirv_mod.emit(module, output),
        .emit_hlsl, .e2e_hlsl => emit_hlsl_mod.emit(module, output),
        .analyze_to_ir => error.InvalidEmissionStage,
    };
}

fn runStage(
    allocator: std.mem.Allocator,
    source: []const u8,
    stage: Stage,
    reference: *const ir_mod.Module,
    samples: []u64,
) !usize {
    const capacity: usize = switch (stage) {
        .analyze_to_ir => 0,
        .emit_msl, .e2e_msl => MSL_BUF_SIZE,
        .emit_spirv, .e2e_spirv => SPIRV_BUF_SIZE,
        .emit_hlsl, .e2e_hlsl => HLSL_BUF_SIZE,
    };
    const output = try allocator.alloc(u8, capacity);
    defer allocator.free(output);
    var bytes_out: usize = 0;
    for (samples) |*sample| {
        var timer = try std.time.Timer.start();
        switch (stage) {
            .emit_msl, .emit_spirv, .emit_hlsl => {
                bytes_out = try emitStage(stage, reference, output);
                sample.* = timer.read();
            },
            .analyze_to_ir, .e2e_msl, .e2e_spirv, .e2e_hlsl => {
                var tree = try parser_mod.parseSource(allocator, source);
                defer tree.deinit();
                var semantic = try sema_mod.analyze(allocator, &tree);
                defer semantic.deinit();
                var module = try ir_builder_mod.build(allocator, &tree, &semantic);
                defer module.deinit();
                try maybe_validate_module(&module);
                if (stage != .analyze_to_ir) {
                    _ = try ir_opt_rewrite_mod.apply(allocator, &module);
                    bytes_out = try emitStage(stage, &module, output);
                }
                // Preserve the stage scope: cleanup follows the final timestamp.
                sample.* = timer.read();
            },
        }
    }
    return bytes_out;
}

fn benchShader(
    allocator: std.mem.Allocator,
    shader: Shader,
    config: Config,
    writer: std.fs.File.DeprecatedWriter,
) !void {
    const samples = try allocator.alloc(u64, config.iterations);
    defer allocator.free(samples);
    var reference = try buildReferenceModule(allocator, shader.source);
    defer reference.deinit();

    for (std.enums.values(Stage)) |stage| {
        var warmup_sample: [1]u64 = undefined;
        for (0..config.warmup) |_| {
            _ = runStage(allocator, shader.source, stage, &reference, &warmup_sample) catch |err| {
                std.debug.print("bench: {s}/{s} warmup failed: {s}\n", .{ shader.name, @tagName(stage), @errorName(err) });
                return err;
            };
        }
        const bytes_out = runStage(allocator, shader.source, stage, &reference, samples) catch |err| {
            std.debug.print("bench: {s}/{s} timed run failed: {s}\n", .{ shader.name, @tagName(stage), @errorName(err) });
            return err;
        };
        try writeResult(writer, shader.name, @tagName(stage), config.iterations, config.warmup, try computeStats(samples), bytes_out);
    }
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();
    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);
    const config = try parseArgs(args[1..]);
    const output = if (config.out_path) |path|
        try std.fs.cwd().createFile(path, .{})
    else
        std.fs.File.stdout();
    defer if (config.out_path != null) output.close();

    for (SHADERS) |shader| {
        if (config.filter) |name| {
            if (!std.mem.eql(u8, name, shader.name)) continue;
        }
        std.debug.print("bench: {s}\n", .{shader.name});
        benchShader(allocator, shader, config, output.deprecatedWriter()) catch |err| {
            std.debug.print("bench: {s} failed: {s}\n", .{ shader.name, @errorName(err) });
            return err;
        };
    }
}

test "stage benchmark rejects invalid sampling and selection" {
    try std.testing.expectError(error.InvalidIterations, parseArgs(&.{ "--iterations", "0" }));
    try std.testing.expectError(error.InvalidIterations, parseArgs(&.{ "--iterations", "2001" }));
    try std.testing.expectError(error.MissingArgumentValue, parseArgs(&.{"--iterations"}));
    try std.testing.expectError(error.UnknownArgument, parseArgs(&.{ "--typo", "1" }));
    try std.testing.expectError(error.InvalidCharacter, parseArgs(&.{ "--warmup", "bad" }));
    try std.testing.expectError(error.Overflow, parseArgs(&.{ "--iterations", "4294967296" }));
    try std.testing.expectError(error.UnknownShader, parseArgs(&.{ "--filter", "absent" }));
    const config = try parseArgs(&.{ "--filter", "compute_simple", "--filter", "compute_matmul", "--warmup", "0" });
    try std.testing.expectEqualStrings("compute_matmul", config.filter.?);
    try std.testing.expectEqual(@as(u32, 0), config.warmup);
}

test "stage benchmark statistics handle empty and large samples" {
    try std.testing.expectError(error.EmptySamples, computeStats(&.{}));
    var large = [_]u64{ std.math.maxInt(u64), std.math.maxInt(u64) };
    try std.testing.expectEqual(std.math.maxInt(u64), (try computeStats(&large)).mean_ns);
    var samples = [_]u64{ 30, 10, 20 };
    const stats = try computeStats(&samples);
    try std.testing.expectEqual(@as(u64, 10), stats.min_ns);
    try std.testing.expectEqual(@as(u64, 20), stats.p50_ns);
    try std.testing.expectEqual(@as(u64, 30), stats.p95_ns);
    try std.testing.expectEqual(@as(u64, 30), stats.p99_ns);
    try std.testing.expectEqual(@as(u64, 20), stats.mean_ns);
}

fn exerciseStageAllocations(allocator: std.mem.Allocator) !void {
    var reference = try buildReferenceModule(allocator, SHADERS[0].source);
    defer reference.deinit();
    var sample: [1]u64 = undefined;
    for (std.enums.values(Stage)) |stage| {
        _ = try runStage(allocator, SHADERS[0].source, stage, &reference, &sample);
    }
}

test "stage benchmark releases reference and stage allocation failures" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseStageAllocations, .{});
}

test "stage benchmark preserves source failures" {
    try std.testing.expectError(error.UnexpectedToken, benchShader(
        std.testing.allocator,
        .{ .name = "invalid", .source = "@" },
        .{ .iterations = 1, .warmup = 0 },
        std.fs.File.stdout().deprecatedWriter(),
    ));
}
