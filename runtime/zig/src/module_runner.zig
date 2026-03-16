const std = @import("std");
const compute_services = @import("full/modules/services/compute_services.zig");
const effects_pipeline = @import("full/modules/rendering/effects_pipeline.zig");
const path_engine = @import("full/modules/rendering/path_engine.zig");
const resource_scheduler = @import("full/modules/services/resource_scheduler.zig");
const sdf_renderer = @import("full/modules/rendering/sdf_renderer.zig");
const common = @import("full/modules/common.zig");

const RunnerError = error{
    MissingValue,
    MissingRequest,
    MissingPolicy,
    UnsupportedModule,
};

fn readFileAlloc(allocator: std.mem.Allocator, path: []const u8) ![]u8 {
    return try std.fs.cwd().readFileAlloc(allocator, path, 16 * 1024 * 1024);
}

fn getOptionValue(args: [][:0]u8, index: *usize) ![]const u8 {
    if (index.* + 1 >= args.len) return RunnerError.MissingValue;
    index.* += 1;
    return args[index.*];
}

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    var request_path: ?[]const u8 = null;
    var policy_path: ?[]const u8 = null;
    var module_id: ?[]const u8 = null;

    var idx: usize = 1;
    while (idx < argv.len) : (idx += 1) {
        if (std.mem.eql(u8, argv[idx], "--request")) {
            request_path = try getOptionValue(argv, &idx);
        } else if (std.mem.eql(u8, argv[idx], "--policy")) {
            policy_path = try getOptionValue(argv, &idx);
        } else if (std.mem.eql(u8, argv[idx], "--module")) {
            module_id = try getOptionValue(argv, &idx);
        }
    }

    const resolved_request = request_path orelse return RunnerError.MissingRequest;
    const resolved_policy = policy_path orelse return RunnerError.MissingPolicy;
    const request_bytes = try readFileAlloc(allocator, resolved_request);
    defer allocator.free(request_bytes);
    const policy_bytes = try readFileAlloc(allocator, resolved_policy);
    defer allocator.free(policy_bytes);

    var stdout = std.fs.File.stdout().deprecatedWriter();

    if (module_id != null and std.mem.eql(u8, module_id.?, compute_services.MODULE_ID)) {
        var parsed_request = try compute_services.parseRequest(allocator, request_bytes);
        defer parsed_request.deinit();
        var parsed_policy = try compute_services.parsePolicy(allocator, policy_bytes);
        defer parsed_policy.deinit();
        const result = try compute_services.execute(allocator, parsed_request.value, parsed_policy.value);
        const payload = try common.jsonStringifyAlloc(allocator, result);
        defer allocator.free(payload);
        try stdout.writeAll(payload);
        try stdout.writeAll("\n");
        return;
    }
    if (module_id != null and std.mem.eql(u8, module_id.?, effects_pipeline.MODULE_ID)) {
        var parsed_request = try effects_pipeline.parseRequest(allocator, request_bytes);
        defer parsed_request.deinit();
        var parsed_policy = try effects_pipeline.parsePolicy(allocator, policy_bytes);
        defer parsed_policy.deinit();
        const result = try effects_pipeline.execute(allocator, parsed_request.value, parsed_policy.value);
        const payload = try common.jsonStringifyAlloc(allocator, result);
        defer allocator.free(payload);
        try stdout.writeAll(payload);
        try stdout.writeAll("\n");
        return;
    }
    if (module_id != null and std.mem.eql(u8, module_id.?, path_engine.MODULE_ID)) {
        var parsed_request = try path_engine.parseRequest(allocator, request_bytes);
        defer parsed_request.deinit();
        var parsed_policy = try path_engine.parsePolicy(allocator, policy_bytes);
        defer parsed_policy.deinit();
        const result = try path_engine.execute(allocator, parsed_request.value, parsed_policy.value);
        const payload = try common.jsonStringifyAlloc(allocator, result);
        defer allocator.free(payload);
        try stdout.writeAll(payload);
        try stdout.writeAll("\n");
        return;
    }
    if (module_id != null and std.mem.eql(u8, module_id.?, resource_scheduler.MODULE_ID)) {
        var parsed_request = try resource_scheduler.parseRequest(allocator, request_bytes);
        defer parsed_request.deinit();
        var parsed_policy = try resource_scheduler.parsePolicy(allocator, policy_bytes);
        defer parsed_policy.deinit();
        const result = try resource_scheduler.execute(allocator, parsed_request.value, parsed_policy.value);
        const payload = try common.jsonStringifyAlloc(allocator, result);
        defer allocator.free(payload);
        try stdout.writeAll(payload);
        try stdout.writeAll("\n");
        return;
    }
    if (module_id != null and std.mem.eql(u8, module_id.?, sdf_renderer.MODULE_ID)) {
        var parsed_request = try sdf_renderer.parseRequest(allocator, request_bytes);
        defer parsed_request.deinit();
        var parsed_policy = try sdf_renderer.parsePolicy(allocator, policy_bytes);
        defer parsed_policy.deinit();
        const result = try sdf_renderer.execute(allocator, parsed_request.value, parsed_policy.value);
        const payload = try common.jsonStringifyAlloc(allocator, result);
        defer allocator.free(payload);
        try stdout.writeAll(payload);
        try stdout.writeAll("\n");
        return;
    }

    _ = common;
    return RunnerError.UnsupportedModule;
}
