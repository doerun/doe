const std = @import("std");

pub const ReplayValidationError = error{
    InvalidReplayHash,
    ReplayArtifactModuleMismatch,
    ReplayArtifactOpCodeMismatch,
    ReplayMissingRow,
    ReplayRowCountMismatch,
    ReplaySeqFieldMissing,
    ReplaySeqMismatch,
    ReplayCommandMismatch,
    ReplayKernelMismatch,
    ReplayHashFieldMissing,
    ReplayCommandFieldMissing,
    ReplayPreviousHashFieldMissing,
    ReplayPreviousHashMismatch,
    ReplayHashMismatch,
};

pub const ReplayExpectation = struct {
    seq: usize,
    command: []const u8,
    kernel: ?[]const u8 = null,
    hash: u64,
    previous_hash: u64,
};

pub const RawReplayRow = struct {
    seq: ?usize = null,
    command: ?[]const u8 = null,
    kernel: ?[]const u8 = null,
    hash: ?[]const u8 = null,
    previousHash: ?[]const u8 = null,
    opCode: ?[]const u8 = null,
    module: ?[]const u8 = null,
};

pub fn parseTraceHash(value: []const u8) ReplayValidationError!u64 {
    if (value.len == 0) return ReplayValidationError.InvalidReplayHash;

    if (value.len >= 2 and value[0] == '0' and (value[1] == 'x' or value[1] == 'X')) {
        return std.fmt.parseInt(u64, value[2..], 16) catch return ReplayValidationError.InvalidReplayHash;
    }
    return std.fmt.parseInt(u64, value, 16) catch return ReplayValidationError.InvalidReplayHash;
}

pub fn parseReplayLine(allocator: std.mem.Allocator, expected_module: []const u8, parsed: *const RawReplayRow) !ReplayExpectation {
    if (parsed.opCode) |op_code| {
        if (!std.mem.eql(u8, op_code, "dispatch")) return ReplayValidationError.ReplayArtifactOpCodeMismatch;
    }
    if (parsed.module) |module_name| {
        if (!std.mem.eql(u8, module_name, expected_module)) {
            return ReplayValidationError.ReplayArtifactModuleMismatch;
        }
    }

    const command = parsed.command orelse return ReplayValidationError.ReplayCommandFieldMissing;
    const hash = parsed.hash orelse return ReplayValidationError.ReplayHashFieldMissing;
    const previous_hash = parsed.previousHash orelse return ReplayValidationError.ReplayPreviousHashFieldMissing;
    const seq = parsed.seq orelse return ReplayValidationError.ReplaySeqFieldMissing;
    const command_copy = try allocator.dupe(u8, command);
    errdefer allocator.free(command_copy);
    const kernel_copy = if (parsed.kernel) |kernel| try allocator.dupe(u8, kernel) else null;
    errdefer if (kernel_copy) |kernel| allocator.free(kernel);
    const hash_parsed = try parseTraceHash(hash);
    const previous_hash_parsed = try parseTraceHash(previous_hash);

    return .{
        .seq = seq,
        .command = command_copy,
        .kernel = kernel_copy,
        .hash = hash_parsed,
        .previous_hash = previous_hash_parsed,
    };
}

pub fn loadReplayExpectations(allocator: std.mem.Allocator, path: []const u8) ![]ReplayExpectation {
    const artifact_text = try readFileAlloc(allocator, path);
    defer allocator.free(artifact_text);

    var expectations = std.ArrayList(ReplayExpectation).init(allocator);
    errdefer {
        for (expectations.items) |expectation| {
            freeReplayExpectation(allocator, expectation);
        }
        expectations.deinit();
    }
    var it = std.mem.splitScalar(u8, artifact_text, '\n');
    while (it.next()) |line| {
        const trimmed = std.mem.trim(u8, line, " \t\r\n");
        if (trimmed.len == 0) continue;
        const parsed = try std.json.parseFromSlice(RawReplayRow, allocator, trimmed, .{ .ignore_unknown_fields = true });
        defer parsed.deinit();
        const validated = try parseReplayLine(allocator, "doe-zig-runtime", &parsed.value);
        errdefer freeReplayExpectation(allocator, validated);
        try expectations.append(validated);
    }

    return expectations.toOwnedSlice();
}

pub fn freeReplayExpectations(allocator: std.mem.Allocator, expectations: []ReplayExpectation) void {
    for (expectations) |expectation| {
        freeReplayExpectation(allocator, expectation);
    }
    allocator.free(expectations);
}

pub fn matchOptionalText(lhs: ?[]const u8, rhs: ?[]const u8) bool {
    if (lhs == null and rhs == null) return true;
    if (lhs == null or rhs == null) return false;
    return std.mem.eql(u8, lhs.?, rhs.?);
}

fn readFileAlloc(allocator: std.mem.Allocator, path: []const u8) ![]const u8 {
    const file = try std.fs.cwd().openFile(path, .{});
    defer file.close();
    return try file.readToEndAlloc(allocator, 16 * 1024 * 1024);
}

fn freeReplayExpectation(allocator: std.mem.Allocator, expectation: ReplayExpectation) void {
    allocator.free(expectation.command);
    if (expectation.kernel) |kernel| allocator.free(kernel);
}
