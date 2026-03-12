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

    var expectations = std.ArrayList(ReplayExpectation).empty;
    errdefer {
        for (expectations.items) |expectation| {
            freeReplayExpectation(allocator, expectation);
        }
        expectations.deinit(allocator);
    }
    var it = std.mem.splitScalar(u8, artifact_text, '\n');
    while (it.next()) |line| {
        const trimmed = std.mem.trim(u8, line, " \t\r\n");
        if (trimmed.len == 0) continue;
        const parsed = try std.json.parseFromSlice(RawReplayRow, allocator, trimmed, .{ .ignore_unknown_fields = true });
        defer parsed.deinit();
        const validated = try parseReplayLine(allocator, "doe-zig-runtime", &parsed.value);
        errdefer freeReplayExpectation(allocator, validated);
        try expectations.append(allocator, validated);
    }

    return expectations.toOwnedSlice(allocator);
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

test "parseTraceHash parses plain hex string" {
    const result = try parseTraceHash("deadbeef");
    try std.testing.expectEqual(@as(u64, 0xdeadbeef), result);
}

test "parseTraceHash parses 0x-prefixed hex string" {
    const result = try parseTraceHash("0xCAFE");
    try std.testing.expectEqual(@as(u64, 0xCAFE), result);
}

test "parseTraceHash parses 0X-prefixed hex string" {
    const result = try parseTraceHash("0X1a2b");
    try std.testing.expectEqual(@as(u64, 0x1a2b), result);
}

test "parseTraceHash rejects empty string" {
    const result = parseTraceHash("");
    try std.testing.expectError(ReplayValidationError.InvalidReplayHash, result);
}

test "parseTraceHash rejects non-hex content" {
    const result = parseTraceHash("zzzz");
    try std.testing.expectError(ReplayValidationError.InvalidReplayHash, result);
}

test "matchOptionalText returns true for two null values" {
    try std.testing.expect(matchOptionalText(null, null));
}

test "matchOptionalText returns false when only one side is null" {
    try std.testing.expect(!matchOptionalText("abc", null));
    try std.testing.expect(!matchOptionalText(null, "abc"));
}

test "matchOptionalText compares non-null strings" {
    try std.testing.expect(matchOptionalText("hello", "hello"));
    try std.testing.expect(!matchOptionalText("hello", "world"));
}

test "parseReplayLine returns expectation for valid row" {
    const allocator = std.testing.allocator;
    const row = RawReplayRow{
        .seq = 0,
        .command = "buffer_upload",
        .kernel = null,
        .hash = "0xabc",
        .previousHash = "0x0",
        .opCode = "dispatch",
        .module = "doe-zig-runtime",
    };
    const result = try parseReplayLine(allocator, "doe-zig-runtime", &row);
    defer freeReplayExpectation(allocator, result);

    try std.testing.expectEqual(@as(usize, 0), result.seq);
    try std.testing.expect(std.mem.eql(u8, "buffer_upload", result.command));
    try std.testing.expectEqual(@as(?[]const u8, null), result.kernel);
    try std.testing.expectEqual(@as(u64, 0xabc), result.hash);
    try std.testing.expectEqual(@as(u64, 0x0), result.previous_hash);
}

test "parseReplayLine rejects mismatched module" {
    const allocator = std.testing.allocator;
    const row = RawReplayRow{
        .seq = 1,
        .command = "dispatch",
        .hash = "ff",
        .previousHash = "00",
        .module = "wrong-module",
    };
    const result = parseReplayLine(allocator, "doe-zig-runtime", &row);
    try std.testing.expectError(ReplayValidationError.ReplayArtifactModuleMismatch, result);
}

test "parseReplayLine rejects mismatched opCode" {
    const allocator = std.testing.allocator;
    const row = RawReplayRow{
        .seq = 1,
        .command = "dispatch",
        .hash = "ff",
        .previousHash = "00",
        .opCode = "render",
    };
    const result = parseReplayLine(allocator, "doe-zig-runtime", &row);
    try std.testing.expectError(ReplayValidationError.ReplayArtifactOpCodeMismatch, result);
}

test "parseReplayLine returns error for missing required fields" {
    const allocator = std.testing.allocator;

    // missing command
    const no_cmd = RawReplayRow{ .seq = 0, .hash = "aa", .previousHash = "00" };
    try std.testing.expectError(ReplayValidationError.ReplayCommandFieldMissing, parseReplayLine(allocator, "x", &no_cmd));

    // missing hash
    const no_hash = RawReplayRow{ .seq = 0, .command = "c", .previousHash = "00" };
    try std.testing.expectError(ReplayValidationError.ReplayHashFieldMissing, parseReplayLine(allocator, "x", &no_hash));

    // missing previousHash
    const no_prev = RawReplayRow{ .seq = 0, .command = "c", .hash = "aa" };
    try std.testing.expectError(ReplayValidationError.ReplayPreviousHashFieldMissing, parseReplayLine(allocator, "x", &no_prev));

    // missing seq
    const no_seq = RawReplayRow{ .command = "c", .hash = "aa", .previousHash = "00" };
    try std.testing.expectError(ReplayValidationError.ReplaySeqFieldMissing, parseReplayLine(allocator, "x", &no_seq));
}
