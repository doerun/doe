const std = @import("std");
const lean_proof = @import("../../../verification/lean_proof.zig");
const msl_translation = @import("../pipeline/translate_msl.zig");
const spirv_translation = @import("../pipeline/translate_spirv.zig");
const runtime_compile = @import("runtime_compute_translation.zig");
const MAX_SHADER_BYTES: usize = 8 * 1024 * 1024;

const Config = struct {
    shader_path: []const u8,
    shader_name: ?[]const u8 = null,
    out_path: ?[]const u8 = null,
    target: Target = .msl,
    emit_msl_path: ?[]const u8 = null,
    emit_spirv_path: ?[]const u8 = null,
};

const Target = enum {
    msl,
    spirv,
};

fn parseArgs(args: []const []const u8) !Config {
    var config = Config{
        .shader_path = "",
    };

    const Option = enum { @"shader-path", @"shader-name", out, target, @"emit-msl", @"emit-spirv" };
    var i: usize = 0;
    while (i < args.len) : (i += 2) {
        const argument = args[i];
        const option = if (std.mem.startsWith(u8, argument, "--"))
            std.meta.stringToEnum(Option, argument[2..])
        else
            null;
        const selected = option orelse {
            std.debug.print("unknown runtime compile report option '{s}'\n", .{argument});
            return error.UnknownArgument;
        };
        if (i + 1 == args.len) {
            std.debug.print("{s} requires a value\n", .{argument});
            return error.MissingArgumentValue;
        }
        const value = args[i + 1];
        switch (selected) {
            .@"shader-path" => config.shader_path = value,
            .@"shader-name" => config.shader_name = value,
            .out => config.out_path = value,
            .@"emit-msl" => config.emit_msl_path = value,
            .@"emit-spirv" => config.emit_spirv_path = value,
            .target => config.target = std.meta.stringToEnum(Target, value) orelse {
                std.debug.print("--target expects msl or spirv; received '{s}'\n", .{value});
                return error.InvalidTarget;
            },
        }
    }

    if (config.shader_path.len == 0) return error.MissingShaderPath;
    if (!std.unicode.utf8ValidateSlice(config.shader_path)) return error.InvalidShaderPath;
    if (config.shader_name) |name| {
        if (name.len == 0 or !std.unicode.utf8ValidateSlice(name)) return error.InvalidShaderName;
    }
    if ((config.emit_msl_path != null and config.target != .msl) or
        (config.emit_spirv_path != null and config.target != .spirv)) return error.EmitTargetMismatch;
    return config;
}

fn countSubstring(haystack: []const u8, needle: []const u8) usize {
    if (needle.len == 0 or haystack.len < needle.len) return 0;
    var count: usize = 0;
    var start: usize = 0;
    while (start <= haystack.len - needle.len) {
        if (std.mem.indexOfPos(u8, haystack, start, needle)) |pos| {
            count += 1;
            start = pos + needle.len;
        } else {
            break;
        }
    }
    return count;
}

const Report = struct {
    kind: []const u8 = "runtime_compile_report",
    schemaVersion: u32 = 1,
    shader: []const u8,
    shaderPath: []const u8,
    target: Target,
    leanVerified: bool,
    outputBytes: usize,
    mslBytes: usize,
    spirvBytes: usize,
    minCount: usize,
    doeSizesPresent: bool,
    needsSizesBuf: bool,
    dispatchPreconditions: usize,
    textureDispatchPreconditions: usize,
    workgroupSize: [3]u32,
    phaseTimingsNs: @FieldType(runtime_compile.TimedTranslationResult, "phase_timings_ns"),
};

fn writeReport(allocator: std.mem.Allocator, report: Report, output: std.fs.File) !void {
    const payload = try std.json.Stringify.valueAlloc(allocator, report, .{});
    defer allocator.free(payload);
    try output.writeAll(payload);
    try output.writeAll("\n");
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();
    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);

    const config = parseArgs(args[1..]) catch |err| {
        const stderr = std.fs.File.stderr().deprecatedWriter();
        try stderr.print(
            "usage: doe-runtime-compile-report --shader-path <path> [--shader-name <name>] [--out <path>] [--target msl|spirv] [--emit-msl <path>] [--emit-spirv <path>]\nerror: {s}\n",
            .{@errorName(err)},
        );
        return err;
    };
    try run(allocator, config);
}

fn run(allocator: std.mem.Allocator, config: Config) !void {
    const shader_source = try std.fs.cwd().readFileAlloc(allocator, config.shader_path, MAX_SHADER_BYTES);
    defer allocator.free(shader_source);

    const shader_name = if (config.shader_name) |name|
        name
    else
        std.fs.path.stem(std.fs.path.basename(config.shader_path));

    const out_buf_len = switch (config.target) {
        .msl => msl_translation.MAX_OUTPUT,
        .spirv => spirv_translation.MAX_OUTPUT,
    };
    const out_buf = try allocator.alloc(u8, out_buf_len);
    defer allocator.free(out_buf);

    var translation = switch (config.target) {
        .msl => try runtime_compile.translateToMslForComputeRuntimeTimed(
            allocator,
            shader_source,
            out_buf,
            null,
            0,
        ),
        .spirv => try runtime_compile.translateToSpirvTimed(
            allocator,
            shader_source,
            out_buf,
        ),
    };
    defer translation.info.deinit(allocator);

    const output = out_buf[0..translation.len];
    const min_count = if (config.target == .msl) countSubstring(output, "min(") else 0;
    const doe_sizes_present = config.target == .msl and std.mem.indexOf(u8, output, "_doe_sizes") != null;

    if (config.emit_msl_path) |path| {
        const file = try std.fs.cwd().createFile(path, .{});
        defer file.close();
        try file.writeAll(output);
    }
    if (config.emit_spirv_path) |path| {
        const file = try std.fs.cwd().createFile(path, .{});
        defer file.close();
        try file.writeAll(output);
    }

    const msl_bytes = if (config.target == .msl) translation.len else 0;
    const spirv_bytes = if (config.target == .spirv) translation.len else 0;
    const report: Report = .{
        .shader = shader_name,
        .shaderPath = config.shader_path,
        .target = config.target,
        .leanVerified = lean_proof.lean_verified,
        .outputBytes = translation.len,
        .mslBytes = msl_bytes,
        .spirvBytes = spirv_bytes,
        .minCount = min_count,
        .doeSizesPresent = doe_sizes_present,
        .needsSizesBuf = translation.info.needs_sizes_buf,
        .dispatchPreconditions = translation.info.dispatch_preconditions.len,
        .textureDispatchPreconditions = translation.info.texture_dispatch_preconditions.len,
        .workgroupSize = translation.info.workgroup_size,
        .phaseTimingsNs = translation.phase_timings_ns,
    };

    if (config.out_path) |path| {
        const file = try std.fs.cwd().createFile(path, .{});
        defer file.close();
        try writeReport(allocator, report, file);
    } else {
        try writeReport(allocator, report, std.fs.File.stdout());
    }
}

test "runtime compile report rejects incomplete and incompatible arguments before work" {
    try std.testing.expectError(error.MissingShaderPath, parseArgs(&.{}));
    try std.testing.expectError(error.UnknownArgument, parseArgs(&.{"--typo"}));
    try std.testing.expectError(error.MissingArgumentValue, parseArgs(&.{"--shader-name"}));
    try std.testing.expectError(error.InvalidTarget, parseArgs(&.{ "--target", "hlsl" }));
    try std.testing.expectError(error.EmitTargetMismatch, parseArgs(&.{ "--shader-path", "source.wgsl", "--emit-msl", "first", "--emit-spirv", "second" }));
    try std.testing.expectError(error.InvalidShaderName, parseArgs(&.{ "--shader-path", "source.wgsl", "--shader-name", "\xff" }));
    try std.testing.expectError(error.InvalidShaderName, parseArgs(&.{ "--shader-path", "source.wgsl", "--shader-name", "" }));
    try std.testing.expectError(error.InvalidShaderPath, parseArgs(&.{ "--shader-path", "\xff" }));
    const name = "second";
    const config = try parseArgs(&.{ "--shader-path", "source.wgsl", "--shader-name", "first", "--shader-name", name });
    try std.testing.expectEqual(name.ptr, config.shader_name.?.ptr);
}

fn fixtureReport() Report {
    return .{
        .shader = "quote\"name\n",
        .shaderPath = "path\\shader.wgsl",
        .target = .msl,
        .leanVerified = false,
        .outputBytes = 0,
        .mslBytes = 0,
        .spirvBytes = 0,
        .minCount = 0,
        .doeSizesPresent = false,
        .needsSizesBuf = false,
        .dispatchPreconditions = 0,
        .textureDispatchPreconditions = 0,
        .workgroupSize = .{ 1, 1, 1 },
        .phaseTimingsNs = .{},
    };
}

fn exerciseReportAllocations(allocator: std.mem.Allocator, output: std.fs.File) !void {
    try writeReport(allocator, fixtureReport(), output);
}

test "runtime compile report serialization escapes metadata and releases allocation failures" {
    var temp = std.testing.tmpDir(.{});
    defer temp.cleanup();
    const output = try temp.dir.createFile("report.json", .{ .read = true });
    defer output.close();
    try writeReport(std.testing.allocator, fixtureReport(), output);
    try output.seekTo(0);
    const payload = try output.readToEndAlloc(std.testing.allocator, 4096);
    defer std.testing.allocator.free(payload);
    const parsed = try std.json.parseFromSlice(std.json.Value, std.testing.allocator, payload, .{});
    defer parsed.deinit();
    try std.testing.expectEqualStrings(fixtureReport().shader, parsed.value.object.get("shader").?.string);
    try std.testing.expectEqualStrings(fixtureReport().shaderPath, parsed.value.object.get("shaderPath").?.string);
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseReportAllocations, .{output});
}

fn exerciseTranslationAllocations(allocator: std.mem.Allocator, path: []const u8, output: []const u8, target: Target) !void {
    try run(allocator, .{ .shader_path = path, .out_path = output, .target = target });
}

test "runtime compile report releases source translation metadata and output on allocation failure" {
    var temp = std.testing.tmpDir(.{});
    defer temp.cleanup();
    try temp.dir.writeFile(.{ .sub_path = "source.wgsl", .data = "@compute @workgroup_size(1) fn main() {}" });
    const directory = try temp.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(directory);
    const path = try std.fs.path.join(std.testing.allocator, &.{ directory, "source.wgsl" });
    defer std.testing.allocator.free(path);
    const output = try std.fs.path.join(std.testing.allocator, &.{ directory, "report.json" });
    defer std.testing.allocator.free(output);
    for (std.enums.values(Target)) |target| {
        try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseTranslationAllocations, .{ path, output, target });
    }
}

test "runtime compile report preserves output errors and releases serialized storage" {
    if (@import("builtin").os.tag != .linux) return error.SkipZigTest;
    const output = try std.fs.openFileAbsolute("/dev/full", .{ .mode = .write_only });
    defer output.close();
    try std.testing.expectError(error.NoSpaceLeft, exerciseReportAllocations(std.testing.allocator, output));
}
