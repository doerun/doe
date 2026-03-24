const std = @import("std");
const wgsl = @import("doe_wgsl/mod.zig");
const exec_v1 = wgsl.emit_csl_exec_v1;
const host = wgsl.emit_csl_host;
const host_plan = wgsl.emit_csl_host_plan;

const Mode = enum {
    steps,
    manifest,
};

const Args = struct {
    input_path: []const u8,
    output_path: []const u8,
    mode: Mode = .manifest,
};

const GEMMA_270M_COMPILE_TARGETS = [_]host_plan.CompileTarget{
    .{ .kernel_name = "embed", .layout_path = "embed/layout.csl", .pe_program_path = "embed/pe_program.csl" },
    .{ .kernel_name = "rmsnorm", .layout_path = "rmsnorm/layout.csl", .pe_program_path = "rmsnorm/pe_program.csl" },
    .{ .kernel_name = "tiled", .layout_path = "tiled/layout.csl", .pe_program_path = "tiled/pe_program.csl" },
    .{ .kernel_name = "rope", .layout_path = "rope/layout.csl", .pe_program_path = "rope/pe_program.csl" },
    .{ .kernel_name = "attn_small", .layout_path = "attn_small/layout.csl", .pe_program_path = "attn_small/pe_program.csl" },
    .{ .kernel_name = "residual", .layout_path = "residual/layout.csl", .pe_program_path = "residual/pe_program.csl" },
    .{ .kernel_name = "gelu", .layout_path = "gelu/layout.csl", .pe_program_path = "gelu/pe_program.csl" },
    .{ .kernel_name = "gemv", .layout_path = "gemv/layout.csl", .pe_program_path = "gemv/pe_program.csl" },
    .{ .kernel_name = "attn_decode", .layout_path = "attn_decode/layout.csl", .pe_program_path = "attn_decode/pe_program.csl" },
    .{ .kernel_name = "sample", .layout_path = "sample/layout.csl", .pe_program_path = "sample/pe_program.csl" },
};

fn printUsage() void {
    std.debug.print(
        "usage: doe-csl-host-plan-tool --input <execution.json> --output <host-plan.json> [--mode manifest|steps]\n",
        .{},
    );
}

fn parseArgs(allocator: std.mem.Allocator) !Args {
    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    var args = Args{
        .input_path = "",
        .output_path = "",
    };

    var idx: usize = 1;
    while (idx < argv.len) : (idx += 1) {
        const arg = argv[idx];
        if (std.mem.eql(u8, arg, "--input")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            args.input_path = try allocator.dupe(u8, argv[idx]);
        } else if (std.mem.eql(u8, arg, "--output")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            args.output_path = try allocator.dupe(u8, argv[idx]);
        } else if (std.mem.eql(u8, arg, "--mode")) {
            idx += 1;
            if (idx >= argv.len) return error.InvalidArgument;
            if (std.mem.eql(u8, argv[idx], "manifest")) {
                args.mode = .manifest;
            } else if (std.mem.eql(u8, argv[idx], "steps")) {
                args.mode = .steps;
            } else {
                return error.InvalidArgument;
            }
        } else if (std.mem.eql(u8, arg, "--help")) {
            printUsage();
            return error.HelpShown;
        } else {
            return error.InvalidArgument;
        }
    }

    if (args.input_path.len == 0 or args.output_path.len == 0) {
        return error.InvalidArgument;
    }
    return args;
}

fn ensureParent(path: []const u8) !void {
    if (std.fs.path.dirname(path)) |dir_name| {
        if (std.fs.path.isAbsolute(dir_name)) {
            var root = try std.fs.openDirAbsolute("/", .{});
            defer root.close();
            const relative = std.mem.trimLeft(u8, dir_name, "/");
            if (relative.len > 0) {
                try root.makePath(relative);
            }
        } else {
            try std.fs.cwd().makePath(dir_name);
        }
    }
}

fn readFileAllocAbsoluteAware(allocator: std.mem.Allocator, path: []const u8, max_bytes: usize) ![]u8 {
    const resolved_path = if (std.fs.path.isAbsolute(path))
        path
    else blk: {
        const cwd = try std.process.getCwdAlloc(allocator);
        break :blk try std.fs.path.join(allocator, &.{ cwd, path });
    };
    const file = try std.fs.openFileAbsolute(resolved_path, .{});
    defer file.close();
    return try file.readToEndAlloc(allocator, max_bytes);
}

fn createFileAbsoluteAware(path: []const u8) !std.fs.File {
    const resolved_path = if (std.fs.path.isAbsolute(path))
        path
    else blk: {
        const cwd = try std.process.getCwdAlloc(std.heap.page_allocator);
        defer std.heap.page_allocator.free(cwd);
        break :blk try std.fs.path.join(std.heap.page_allocator, &.{ cwd, path });
    };
    defer if (!std.fs.path.isAbsolute(path)) std.heap.page_allocator.free(resolved_path);
    return try std.fs.createFileAbsolute(resolved_path, .{ .truncate = true });
}

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    const args = parseArgs(allocator) catch |err| switch (err) {
        error.HelpShown => return,
        else => {
            printUsage();
            return err;
        },
    };

    const input_bytes = try readFileAllocAbsoluteAware(allocator, args.input_path, 1 << 20);

    var kernel_buf: [32]host.KernelSpec = undefined;
    var prefill_buf: [64]host.LaunchSpec = undefined;
    var decode_buf: [64]host.LaunchSpec = undefined;

    const plan = switch (args.mode) {
        .manifest => try exec_v1.lowerManifestExecutionToHostPlan(
            allocator,
            input_bytes,
            &kernel_buf,
            &prefill_buf,
            &decode_buf,
        ),
        .steps => try exec_v1.lowerJsonToHostPlan(
            allocator,
            input_bytes,
            &kernel_buf,
            &prefill_buf,
            &decode_buf,
        ),
    };

    const cslc_plan = try host_plan.makeCslcPlan(null);
    var out_buf: [32 * 1024]u8 = undefined;
    var out_pos: usize = 0;
    try host_plan.emitHostPlanArtifactJson(
        &out_buf,
        &out_pos,
        plan,
        GEMMA_270M_COMPILE_TARGETS[0..],
        cslc_plan,
    );
    try host_plan.validateHostPlanArtifactJson(std.heap.page_allocator, out_buf[0..out_pos]);

    try ensureParent(args.output_path);
    const file = try createFileAbsoluteAware(args.output_path);
    defer file.close();
    try file.writeAll(out_buf[0..out_pos]);
}
