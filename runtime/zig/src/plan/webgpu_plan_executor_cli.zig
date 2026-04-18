const std = @import("std");
const config = @import("webgpu_plan_executor_config.zig");

const Allocator = std.mem.Allocator;

pub const RunOptions = config.RunOptions;
pub const CliRunFn = *const fn (Allocator, RunOptions) anyerror!void;

fn tryConsumeStringArg(
    arg: []const u8,
    argv: []const [:0]u8,
    i: *usize,
    flag: []const u8,
    allocator: Allocator,
    out: *?[]const u8,
) !bool {
    if (!std.mem.eql(u8, arg, flag)) return false;
    if (i.* + 1 >= argv.len) return false;
    i.* += 1;
    out.* = try allocator.dupe(u8, argv[i.*]);
    return true;
}

fn parseArgs(allocator: Allocator) !RunOptions {
    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    var plan_path: ?[]const u8 = null;
    var trace_meta_path: ?[]const u8 = null;
    var trace_jsonl_path: ?[]const u8 = null;
    var workload_id: ?[]const u8 = null;
    var dry_run = false;
    var backend_id_override: ?[]const u8 = null;

    var i: usize = 1;
    while (i < argv.len) : (i += 1) {
        const arg = argv[i];
        if (std.mem.eql(u8, arg, "--dry-run")) {
            dry_run = true;
            continue;
        }
        if (try tryConsumeStringArg(arg, argv, &i, "--plan", allocator, &plan_path)) continue;
        if (try tryConsumeStringArg(arg, argv, &i, "--trace-meta", allocator, &trace_meta_path)) continue;
        if (try tryConsumeStringArg(arg, argv, &i, "--trace-jsonl", allocator, &trace_jsonl_path)) continue;
        if (try tryConsumeStringArg(arg, argv, &i, "--workload", allocator, &workload_id)) continue;
        if (try tryConsumeStringArg(arg, argv, &i, "--backend-id", allocator, &backend_id_override)) continue;
        return error.InvalidCommandLine;
    }

    return .{
        .plan_path = plan_path orelse return error.MissingField,
        .trace_meta_path = trace_meta_path orelse return error.MissingField,
        .trace_jsonl_path = trace_jsonl_path orelse return error.MissingField,
        .workload_id = workload_id orelse return error.MissingField,
        .dry_run = dry_run,
        .backend_id_override = backend_id_override,
    };
}

pub fn runCli(run_fn: CliRunFn) !void {
    const allocator = std.heap.page_allocator;
    const options = try parseArgs(allocator);
    try run_fn(allocator, options);
}
