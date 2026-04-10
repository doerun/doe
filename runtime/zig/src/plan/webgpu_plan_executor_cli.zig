const std = @import("std");
const config = @import("webgpu_plan_executor_config.zig");

const Allocator = std.mem.Allocator;

pub const RunOptions = config.RunOptions;
pub const CliRunFn = *const fn (Allocator, RunOptions) anyerror!void;

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
        if (std.mem.eql(u8, arg, "--plan") and i + 1 < argv.len) {
            i += 1;
            plan_path = try allocator.dupe(u8, argv[i]);
            continue;
        }
        if (std.mem.eql(u8, arg, "--trace-meta") and i + 1 < argv.len) {
            i += 1;
            trace_meta_path = try allocator.dupe(u8, argv[i]);
            continue;
        }
        if (std.mem.eql(u8, arg, "--trace-jsonl") and i + 1 < argv.len) {
            i += 1;
            trace_jsonl_path = try allocator.dupe(u8, argv[i]);
            continue;
        }
        if (std.mem.eql(u8, arg, "--workload") and i + 1 < argv.len) {
            i += 1;
            workload_id = try allocator.dupe(u8, argv[i]);
            continue;
        }
        if (std.mem.eql(u8, arg, "--backend-id") and i + 1 < argv.len) {
            i += 1;
            backend_id_override = try allocator.dupe(u8, argv[i]);
            continue;
        }
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
