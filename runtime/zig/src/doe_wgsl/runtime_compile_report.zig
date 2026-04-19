const std = @import("std");
const lean_proof = @import("../lean_proof.zig");
const mod = @import("mod.zig");
const runtime_compile = @import("runtime_compile.zig");

const Config = struct {
    shader_path: []const u8,
    shader_name: ?[]const u8 = null,
    out_path: ?[]const u8 = null,
    emit_msl_path: ?[]const u8 = null,
};

fn parseArgs(allocator: std.mem.Allocator) !Config {
    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);

    var config = Config{
        .shader_path = "",
    };

    var i: usize = 1;
    while (i < args.len) : (i += 1) {
        if (std.mem.eql(u8, args[i], "--shader-path") and i + 1 < args.len) {
            i += 1;
            config.shader_path = try allocator.dupe(u8, args[i]);
        } else if (std.mem.eql(u8, args[i], "--shader-name") and i + 1 < args.len) {
            i += 1;
            config.shader_name = try allocator.dupe(u8, args[i]);
        } else if (std.mem.eql(u8, args[i], "--out") and i + 1 < args.len) {
            i += 1;
            config.out_path = try allocator.dupe(u8, args[i]);
        } else if (std.mem.eql(u8, args[i], "--emit-msl") and i + 1 < args.len) {
            i += 1;
            config.emit_msl_path = try allocator.dupe(u8, args[i]);
        }
    }

    if (config.shader_path.len == 0) return error.MissingShaderPath;
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

fn boolText(value: bool) []const u8 {
    return if (value) "true" else "false";
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const config = parseArgs(allocator) catch |err| {
        const stderr = std.fs.File.stderr().deprecatedWriter();
        try stderr.print(
            "usage: doe-runtime-compile-report --shader-path <path> [--shader-name <name>] [--out <path>] [--emit-msl <path>]\nerror: {s}\n",
            .{@errorName(err)},
        );
        std.process.exit(1);
    };
    defer allocator.free(config.shader_path);
    defer if (config.shader_name) |value| allocator.free(value);
    defer if (config.out_path) |value| allocator.free(value);
    defer if (config.emit_msl_path) |value| allocator.free(value);

    const shader_source = try std.fs.cwd().readFileAlloc(allocator, config.shader_path, 8 * 1024 * 1024);
    defer allocator.free(shader_source);

    const shader_name = if (config.shader_name) |name|
        name
    else
        std.fs.path.stem(std.fs.path.basename(config.shader_path));

    var out_buf = try allocator.alloc(u8, mod.MAX_OUTPUT);
    defer allocator.free(out_buf);

    var translation = try runtime_compile.translateToMslForComputeRuntime(
        allocator,
        shader_source,
        out_buf,
        null,
        0,
    );
    defer translation.info.deinit(allocator);

    const msl = out_buf[0..translation.len];
    const min_count = countSubstring(msl, "min(");
    const doe_sizes_present = std.mem.indexOf(u8, msl, "_doe_sizes") != null;

    if (config.emit_msl_path) |path| {
        const file = try std.fs.cwd().createFile(path, .{});
        defer file.close();
        try file.writeAll(msl);
    }

    const report_fmt = "{{\"kind\":\"runtime_compile_report\",\"shader\":\"{s}\",\"shaderPath\":\"{s}\",\"leanVerified\":{s},\"mslBytes\":{d},\"minCount\":{d},\"doeSizesPresent\":{s},\"needsSizesBuf\":{s},\"dispatchPreconditions\":{d},\"textureDispatchPreconditions\":{d},\"workgroupSize\":[{d},{d},{d}]}}\n";
    const report_args = .{
        shader_name,
        config.shader_path,
        boolText(lean_proof.lean_verified),
        translation.len,
        min_count,
        boolText(doe_sizes_present),
        boolText(translation.info.needs_sizes_buf),
        translation.info.dispatch_preconditions.len,
        translation.info.texture_dispatch_preconditions.len,
        translation.info.workgroup_size[0],
        translation.info.workgroup_size[1],
        translation.info.workgroup_size[2],
    };

    if (config.out_path) |path| {
        const file = try std.fs.cwd().createFile(path, .{});
        defer file.close();
        try file.deprecatedWriter().print(report_fmt, report_args);
    } else {
        try std.fs.File.stdout().deprecatedWriter().print(report_fmt, report_args);
    }
}
