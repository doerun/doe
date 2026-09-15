// In-process WGSL translation diagnostics. Comparison harnesses own matched
// timing scopes, validation, trace identity, and performance claims.

const std = @import("std");
const wgsl = @import("doe").compiler.wgsl();

const DEFAULT_ITERATIONS: u32 = 500;
const DEFAULT_WARMUP: u32 = 50;
const MAX_SAMPLES: u32 = 5000;
const MSL_BUF_SIZE: usize = wgsl.MAX_OUTPUT;
const HLSL_BUF_SIZE: usize = wgsl.MAX_HLSL_OUTPUT;
const SPIRV_BUF_SIZE: usize = wgsl.MAX_SPIRV_OUTPUT;
const BENCH_VERSION: u32 = 2;
const MAX_SHADER_SOURCE_BYTES: usize = 8 * 1024 * 1024;
const NS_PER_MICROSECOND: u64 = std.time.ns_per_us;
const TIMER_CALIBRATION_ITERATIONS: u32 = 1000;

const Shader = struct {
    name: []const u8,
    tier: []const u8,
    source: []const u8,
    source_lines: u32,
};

fn countLines(src: []const u8) u32 {
    @setEvalBranchQuota(10_000);
    if (src.len == 0) return 0;
    var n: u32 = if (src[src.len - 1] == '\n') 0 else 1;
    for (src) |c| {
        if (c == '\n') n += 1;
    }
    return n;
}

const ShaderSources = struct {
    // -- Tier: trivial --
    const empty_compute =
        \\@compute @workgroup_size(1)
        \\fn main() {}
    ;
    const passthrough_vertex =
        \\@vertex
        \\fn main(@location(0) pos: vec4f) -> @builtin(position) vec4f {
        \\    return pos;
        \\}
    ;

    // -- Tier: simple --
    const scale_compute =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = data[id.x] * 2.0;
        \\}
    ;
    const color_fragment =
        \\@fragment
        \\fn main(@location(0) uv: vec2f, @builtin(position) pos: vec4f) -> @location(0) vec4f {
        \\    let r = uv.x;
        \\    let g = uv.y;
        \\    let b = 1.0 - r * g;
        \\    let a = clamp(pos.z, 0.0, 1.0);
        \\    return vec4f(r, g, b, a);
        \\}
    ;

    // -- Tier: moderate --
    const matmul_compute =
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
    ;
    const vertex_transform =
        \\@vertex
        \\fn main(
        \\    @builtin(vertex_index) vid: u32,
        \\    @builtin(instance_index) iid: u32,
        \\) -> @builtin(position) vec4f {
        \\    let x = f32(vid) * 0.1 - 1.0;
        \\    let y = f32(iid) * 0.1 - 1.0;
        \\    return vec4f(x, y, 0.0, 1.0);
        \\}
    ;

    // -- Tier: complex --
    const texture_compute =
        \\@group(0) @binding(0) var tex: texture_2d<f32>;
        \\@group(0) @binding(1) var out_tex: texture_storage_2d<rgba8unorm, write>;
        \\@group(0) @binding(2) var<storage, read_write> data: array<f32>;
        \\@compute @workgroup_size(8, 8)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let sample = textureLoad(tex, vec2u(id.xy), 0);
        \\    textureStore(out_tex, vec2u(id.xy), sample);
        \\    data[id.x] = sample.x;
        \\}
    ;
    const multi_binding_compute =
        \\struct Params { scale: f32, bias: f32, }
        \\@group(0) @binding(0) var<storage, read> input: array<f32>;
        \\@group(0) @binding(1) var<storage, read_write> output: array<f32>;
        \\@group(0) @binding(2) var<uniform> params: Params;
        \\@group(0) @binding(3) var<storage, read> weights: array<f32>;
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    let idx = gid.x;
        \\    let w = weights[idx];
        \\    let x = input[idx];
        \\    var acc: f32 = x * w * params.scale + params.bias;
        \\    acc = clamp(acc, 0.0, 1.0);
        \\    output[idx] = acc;
        \\}
    ;
    const fragment_discard =
        \\@fragment fn fs_main(@builtin(position) pos: vec4f, @builtin(front_facing) ff: bool) -> @location(0) vec4f {
        \\    if (!ff) { discard; }
        \\    return vec4f(pos.x, pos.y, 0.0, 1.0);
        \\}
    ;
};

const SHADERS = [_]Shader{
    .{ .name = "empty_compute", .tier = "trivial", .source = ShaderSources.empty_compute, .source_lines = countLines(ShaderSources.empty_compute) },
    .{ .name = "passthrough_vertex", .tier = "trivial", .source = ShaderSources.passthrough_vertex, .source_lines = countLines(ShaderSources.passthrough_vertex) },
    .{ .name = "scale_compute", .tier = "simple", .source = ShaderSources.scale_compute, .source_lines = countLines(ShaderSources.scale_compute) },
    .{ .name = "color_fragment", .tier = "simple", .source = ShaderSources.color_fragment, .source_lines = countLines(ShaderSources.color_fragment) },
    .{ .name = "matmul_compute", .tier = "moderate", .source = ShaderSources.matmul_compute, .source_lines = countLines(ShaderSources.matmul_compute) },
    .{ .name = "vertex_transform", .tier = "moderate", .source = ShaderSources.vertex_transform, .source_lines = countLines(ShaderSources.vertex_transform) },
    .{ .name = "texture_compute", .tier = "complex", .source = ShaderSources.texture_compute, .source_lines = countLines(ShaderSources.texture_compute) },
    .{ .name = "multi_binding_compute", .tier = "complex", .source = ShaderSources.multi_binding_compute, .source_lines = countLines(ShaderSources.multi_binding_compute) },
    .{ .name = "fragment_discard", .tier = "complex", .source = ShaderSources.fragment_discard, .source_lines = countLines(ShaderSources.fragment_discard) },
};

const Target = enum {
    msl,
    hlsl,
    spirv,
};

const ALL_TARGETS = std.enums.values(Target);

const Config = struct {
    iterations: u32 = DEFAULT_ITERATIONS,
    warmup: u32 = DEFAULT_WARMUP,
    out_path: ?[]const u8 = null,
    filter: ?[]const u8 = null,
    shader_path: ?[]const u8 = null,
    shader_name: ?[]const u8 = null,
    shader_tier: ?[]const u8 = null,
    target: ?Target = null,
};

// All string fields borrow from the process argument owner through execution.
fn parseArgs(args: []const []const u8) !Config {
    var config = Config{};
    var index: usize = 0;
    while (index < args.len) : (index += 2) {
        const option = args[index];
        const Option = enum { iterations, warmup, out, filter, @"shader-path", @"shader-name", @"shader-tier", target };
        const selected = if (std.mem.startsWith(u8, option, "--"))
            std.meta.stringToEnum(Option, option[2..])
        else
            null;
        const kind = selected orelse {
            std.debug.print("unknown compilation benchmark option '{s}'\n", .{option});
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
            .@"shader-path" => config.shader_path = value,
            .@"shader-name" => config.shader_name = value,
            .@"shader-tier" => config.shader_tier = value,
            .target => config.target = if (std.mem.eql(u8, value, "all")) null else std.meta.stringToEnum(Target, value) orelse {
                std.debug.print("--target expects msl, hlsl, spirv, or all; received '{s}'\n", .{value});
                return error.InvalidTarget;
            },
        }
    }
    if (config.iterations == 0 or config.iterations > MAX_SAMPLES) {
        std.debug.print("--iterations must be between 1 and {d}; received {d}\n", .{ MAX_SAMPLES, config.iterations });
        return error.InvalidIterations;
    }
    if (config.shader_path == null and (config.shader_name != null or config.shader_tier != null)) {
        std.debug.print("--shader-name and --shader-tier require --shader-path\n", .{});
        return error.InvalidShaderSelection;
    }
    if (config.shader_path) |path| {
        const name = config.shader_name orelse std.fs.path.stem(std.fs.path.basename(path));
        const tier = config.shader_tier orelse "external";
        if (!std.unicode.utf8ValidateSlice(name) or !std.unicode.utf8ValidateSlice(tier)) {
            std.debug.print("shader name and tier must be valid UTF-8 for JSON output\n", .{});
            return error.InvalidShaderMetadata;
        }
        if (config.filter) |filter| {
            if (!std.mem.eql(u8, filter, name)) return unknownShader(filter);
        }
    } else if (config.filter) |filter| {
        for (SHADERS) |shader| {
            if (std.mem.eql(u8, filter, shader.name)) return config;
        }
        return unknownShader(filter);
    }
    return config;
}

fn unknownShader(filter: []const u8) error{UnknownShader} {
    std.debug.print("shader filter '{s}' does not match the selected corpus or external shader\n", .{filter});
    return error.UnknownShader;
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
    stddev_ns: u64,
};

fn computeStats(samples: []u64) !Stats {
    if (samples.len == 0) return error.EmptySamples;
    std.sort.block(u64, samples, {}, std.sort.asc(u64));

    const n = samples.len;
    var sum: u128 = 0;
    for (samples) |s| sum += s;
    const mean: u64 = @intCast(sum / n);

    var squared_difference_sum: u256 = 0;
    for (samples) |sample| {
        const difference: u128 = if (sample >= mean) sample - mean else mean - sample;
        squared_difference_sum += difference * difference;
    }
    const variance: u128 = @intCast(squared_difference_sum / n);
    const stddev: u64 = @intCast(std.math.sqrt(variance));

    return .{
        .min_ns = samples[0],
        .max_ns = samples[n - 1],
        .mean_ns = mean,
        .p50_ns = samples[n / 2],
        .p95_ns = samples[(n * 95) / 100],
        .p99_ns = samples[(n * 99) / 100],
        .stddev_ns = stddev,
    };
}

fn translateOnce(
    allocator: std.mem.Allocator,
    source: []const u8,
    target: Target,
    out_buf: []u8,
) !usize {
    return switch (target) {
        .msl => wgsl.translateToMsl(allocator, source, out_buf),
        .hlsl => wgsl.translateToHlsl(allocator, source, out_buf),
        .spirv => wgsl.translateToSpirv(allocator, source, out_buf),
    };
}

fn bufferSizeFor(target: Target) usize {
    return switch (target) {
        .msl => MSL_BUF_SIZE,
        .hlsl => HLSL_BUF_SIZE,
        .spirv => SPIRV_BUF_SIZE,
    };
}

fn writeResult(
    allocator: std.mem.Allocator,
    writer: std.fs.File.DeprecatedWriter,
    shader: Shader,
    target: Target,
    iterations: u32,
    warmup: u32,
    stats: Stats,
    bytes_out: usize,
) !void {
    const shader_name = try std.json.Stringify.valueAlloc(allocator, shader.name, .{});
    defer allocator.free(shader_name);
    const shader_tier = try std.json.Stringify.valueAlloc(allocator, shader.tier, .{});
    defer allocator.free(shader_tier);
    try writer.print(
        "{{\"kind\":\"compilation_bench\",\"version\":{d}," ++
            "\"shader\":{s},\"tier\":{s}," ++
            "\"target\":\"{s}\",\"sourceLines\":{d}," ++
            "\"iterations\":{d},\"warmup\":{d}," ++
            "\"p50_ns\":{d},\"p95_ns\":{d},\"p99_ns\":{d}," ++
            "\"min_ns\":{d},\"max_ns\":{d},\"mean_ns\":{d}," ++
            "\"stddev_ns\":{d},\"bytesOut\":{d}," ++
            "\"p50_us\":{d}.{d:0>3},\"compiler\":\"doe_wgsl\"}}\n",
        .{
            BENCH_VERSION,
            shader_name,
            shader_tier,
            @tagName(target),
            shader.source_lines,
            iterations,
            warmup,
            stats.p50_ns,
            stats.p95_ns,
            stats.p99_ns,
            stats.min_ns,
            stats.max_ns,
            stats.mean_ns,
            stats.stddev_ns,
            bytes_out,
            stats.p50_ns / NS_PER_MICROSECOND,
            stats.p50_ns % NS_PER_MICROSECOND,
        },
    );
}

fn writeSummary(
    writer: std.fs.File.DeprecatedWriter,
    target: Target,
    shader_count: u32,
    total_p50_ns: u64,
    min_p50_ns: u64,
    max_p50_ns: u64,
) !void {
    if (shader_count == 0) return error.NoShadersSelected;
    try writer.print(
        "{{\"kind\":\"compilation_bench_summary\",\"version\":{d}," ++
            "\"target\":\"{s}\",\"shaderCount\":{d}," ++
            "\"totalP50_ns\":{d},\"avgP50_ns\":{d}," ++
            "\"minP50_ns\":{d},\"maxP50_ns\":{d}," ++
            "\"totalP50_us\":{d}.{d:0>3}," ++
            "\"compiler\":\"doe_wgsl\"}}\n",
        .{
            BENCH_VERSION,
            @tagName(target),
            shader_count,
            total_p50_ns,
            total_p50_ns / shader_count,
            min_p50_ns,
            max_p50_ns,
            total_p50_ns / NS_PER_MICROSECOND,
            total_p50_ns % NS_PER_MICROSECOND,
        },
    );
}

fn benchShaderTarget(
    allocator: std.mem.Allocator,
    shader: Shader,
    target: Target,
    config: Config,
    writer: std.fs.File.DeprecatedWriter,
) !u64 {
    const samples = try allocator.alloc(u64, config.iterations);
    defer allocator.free(samples);
    const output = try allocator.alloc(u8, bufferSizeFor(target));
    defer allocator.free(output);
    for (0..config.warmup) |_| {
        _ = try translateOnce(allocator, shader.source, target, output);
    }
    var last_bytes: usize = 0;
    for (samples) |*sample| {
        var timer = try std.time.Timer.start();
        last_bytes = try translateOnce(allocator, shader.source, target, output);
        sample.* = timer.read();
    }
    const stats = try computeStats(samples);
    try writeResult(allocator, writer, shader, target, config.iterations, config.warmup, stats, last_bytes);
    printStderrRow(shader.name, target, stats, last_bytes);
    return stats.p50_ns;
}

fn printStderrHeader() void {
    std.debug.print("\n{s:<25} {s:<8} {s:>10} {s:>10} {s:>10} {s:>8}\n", .{
        "shader", "target", "p50(us)", "p95(us)", "p99(us)", "out(B)",
    });
    std.debug.print("{s}\n", .{"-" ** 78});
}

fn printStderrRow(name: []const u8, target: Target, stats: Stats, bytes: usize) void {
    std.debug.print("{s:<25} {s:<8} {d:>7}.{d:0>3} {d:>7}.{d:0>3} {d:>7}.{d:0>3} {d:>8}\n", .{
        name,
        @tagName(target),
        stats.p50_ns / NS_PER_MICROSECOND,
        stats.p50_ns % NS_PER_MICROSECOND,
        stats.p95_ns / NS_PER_MICROSECOND,
        stats.p95_ns % NS_PER_MICROSECOND,
        stats.p99_ns / NS_PER_MICROSECOND,
        stats.p99_ns % NS_PER_MICROSECOND,
        bytes,
    });
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();
    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);
    const config = try parseArgs(args[1..]);

    var dynamic_source: ?[]u8 = null;
    defer if (dynamic_source) |source| allocator.free(source);
    var external_shader: [1]Shader = undefined;
    const shaders: []const Shader = if (config.shader_path) |path| blk: {
        const source = std.fs.cwd().readFileAlloc(allocator, path, MAX_SHADER_SOURCE_BYTES) catch |err| {
            std.debug.print("cannot read shader '{s}': {s}\n", .{ path, @errorName(err) });
            return err;
        };
        dynamic_source = source;
        external_shader[0] = .{
            .name = config.shader_name orelse std.fs.path.stem(std.fs.path.basename(path)),
            .tier = config.shader_tier orelse "external",
            .source = source,
            .source_lines = countLines(source),
        };
        break :blk &external_shader;
    } else &SHADERS;

    const output = if (config.out_path) |path|
        try std.fs.cwd().createFile(path, .{})
    else
        std.fs.File.stdout();
    defer if (config.out_path != null) output.close();
    std.debug.print("doe_wgsl compilation benchmark v{d}\n", .{BENCH_VERSION});
    try runAll(allocator, config, shaders, output.deprecatedWriter());
}

fn measureTimerOverheadNs(allocator: std.mem.Allocator) !u64 {
    const samples = try allocator.alloc(u64, TIMER_CALIBRATION_ITERATIONS);
    defer allocator.free(samples);
    for (samples) |*slot| {
        var t = try std.time.Timer.start();
        slot.* = t.read();
    }
    std.sort.block(u64, samples, {}, std.sort.asc(u64));
    return samples[samples.len / 2];
}

fn writeCalibration(writer: std.fs.File.DeprecatedWriter, timer_overhead_ns: u64) !void {
    try writer.print(
        "{{\"kind\":\"compilation_bench_calibration\",\"version\":{d}," ++
            "\"timerOverheadP50Ns\":{d}," ++
            "\"timerOverheadIterations\":{d}," ++
            "\"timerSource\":\"std.time.Timer\"," ++
            "\"timerScope\":\"per-translation in-process\"}}\n",
        .{ BENCH_VERSION, timer_overhead_ns, TIMER_CALIBRATION_ITERATIONS },
    );
}

fn runAll(allocator: std.mem.Allocator, config: Config, shaders: []const Shader, writer: std.fs.File.DeprecatedWriter) !void {
    printStderrHeader();
    try writeCalibration(writer, try measureTimerOverheadNs(allocator));
    for (ALL_TARGETS) |target| {
        if (config.target) |selected| {
            if (selected != target) continue;
        }
        var total_p50: u64 = 0;
        var min_p50: u64 = std.math.maxInt(u64);
        var max_p50: u64 = 0;
        var shader_count: u32 = 0;
        for (shaders) |shader| {
            if (config.filter) |filter| {
                if (!std.mem.eql(u8, filter, shader.name)) continue;
            }
            const p50 = benchShaderTarget(allocator, shader, target, config, writer) catch |err| {
                std.debug.print("compilation failed for {s}/{s}: {s}\n", .{ shader.name, @tagName(target), @errorName(err) });
                return err;
            };
            total_p50 = try std.math.add(u64, total_p50, p50);
            min_p50 = @min(min_p50, p50);
            max_p50 = @max(max_p50, p50);
            shader_count += 1;
        }
        if (shader_count == 0) return error.NoShadersSelected;
        try writeSummary(writer, target, shader_count, total_p50, min_p50, max_p50);
    }
}

test "compilation benchmark rejects invalid and ineffective inputs" {
    try std.testing.expectError(error.InvalidIterations, parseArgs(&.{ "--iterations", "0" }));
    try std.testing.expectError(error.InvalidIterations, parseArgs(&.{ "--iterations", "5001" }));
    try std.testing.expectError(error.MissingArgumentValue, parseArgs(&.{"--target"}));
    try std.testing.expectError(error.InvalidTarget, parseArgs(&.{ "--target", "bad" }));
    try std.testing.expectError(error.UnknownArgument, parseArgs(&.{ "--typo", "1" }));
    try std.testing.expectError(error.UnknownShader, parseArgs(&.{ "--filter", "absent" }));
    try std.testing.expectError(error.InvalidShaderSelection, parseArgs(&.{ "--shader-name", "absent" }));
    try std.testing.expectError(error.InvalidShaderMetadata, parseArgs(&.{ "--shader-path", "shader.wgsl", "--shader-name", "\xff" }));
    const config = try parseArgs(&.{ "--target", "msl", "--target", "all", "--filter", "empty_compute", "--warmup", "0" });
    try std.testing.expectEqual(null, config.target);
    try std.testing.expectEqual(@as(u32, 0), config.warmup);
}

test "compilation benchmark sample arithmetic and physical source lines" {
    try std.testing.expectError(error.EmptySamples, computeStats(&.{}));
    var maximum = [_]u64{ std.math.maxInt(u64), std.math.maxInt(u64) };
    const maximum_stats = try computeStats(&maximum);
    try std.testing.expectEqual(std.math.maxInt(u64), maximum_stats.mean_ns);
    try std.testing.expectEqual(@as(u64, 0), maximum_stats.stddev_ns);
    var extremes = [_]u64{ 0, std.math.maxInt(u64) };
    const extremes_stats = try computeStats(&extremes);
    try std.testing.expectEqual(std.math.maxInt(u64) / 2, extremes_stats.mean_ns);
    try std.testing.expectEqual(std.math.maxInt(u64) / 2, extremes_stats.stddev_ns);
    try std.testing.expectEqual(@as(u32, 0), countLines(""));
    try std.testing.expectEqual(@as(u32, 1), countLines("one"));
    try std.testing.expectEqual(@as(u32, 1), countLines("one\n"));
    try std.testing.expectEqual(@as(u32, 2), countLines("one\n\n"));
}

test "compilation benchmark escapes external metadata" {
    var temp = std.testing.tmpDir(.{});
    defer temp.cleanup();
    const file = try temp.dir.createFile("rows.ndjson", .{ .read = true });
    defer file.close();
    const name = "quote\"line\nslash\\";
    const tier = "tier\t\r\x00";
    var sample = [_]u64{1000};
    try writeResult(std.testing.allocator, file.deprecatedWriter(), .{
        .name = name,
        .tier = tier,
        .source = "",
        .source_lines = 0,
    }, .msl, 1, 0, try computeStats(&sample), 1);
    try file.seekTo(0);
    const bytes = try file.readToEndAlloc(std.testing.allocator, 4096);
    defer std.testing.allocator.free(bytes);
    const record = try std.json.parseFromSlice(std.json.Value, std.testing.allocator, bytes, .{});
    defer record.deinit();
    try std.testing.expectEqualStrings(name, record.value.object.get("shader").?.string);
    try std.testing.expectEqualStrings(tier, record.value.object.get("tier").?.string);
    try std.testing.expect(record.value.object.get("compilerLoc") == null);
}

fn exerciseCompilationAllocations(allocator: std.mem.Allocator, writer: std.fs.File.DeprecatedWriter) !void {
    _ = try benchShaderTarget(allocator, SHADERS[0], .msl, .{ .iterations = 1, .warmup = 1 }, writer);
}

test "compilation benchmark releases failed translation and output allocations" {
    var temp = std.testing.tmpDir(.{});
    defer temp.cleanup();
    const file = try temp.dir.createFile("rows.ndjson", .{});
    defer file.close();
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseCompilationAllocations, .{file.deprecatedWriter()});
    const invalid: Shader = .{ .name = "invalid", .tier = "test", .source = "@", .source_lines = 1 };
    for (ALL_TARGETS) |target| {
        try std.testing.expectError(error.UnexpectedToken, benchShaderTarget(
            std.testing.allocator,
            invalid,
            target,
            .{ .iterations = 1, .warmup = 0 },
            file.deprecatedWriter(),
        ));
    }
}
