const std = @import("std");
const builtin = @import("builtin");
const doe = @import("doe");
const model_profile = doe.contracts.model.profile();
const execution = doe.runtime.execution();

const DEFAULT_ITERATIONS: u32 = 8;
const MAX_ITERATIONS: u32 = 128;
const DEFAULT_BYTE_COUNT: usize = 2 * 1024 * 1024;
const MAX_BYTE_COUNT: usize = 64 * 1024 * 1024;
const BUFFER_HANDLE_BASE: u64 = 4101;
const PATTERN_ITERATION_STRIDE: usize = 17;
const PATTERN_BYTE_STRIDE: usize = 131;
const PATTERN_SHIFT = 7;
const PATTERN_SALT: u8 = 0x5a;

const Config = struct {
    iterations: u32 = DEFAULT_ITERATIONS,
    byte_count: usize = DEFAULT_BYTE_COUNT,
    inject_corruption: bool = false,
};

const Correctness = struct {
    oracleId: []const u8 = "metal/staged-write-exact-bytes-v2",
    expectedOutcomeSatisfied: bool,
    observedContentMatchesExpected: bool,
    mismatchedBytes: u64,
    firstMismatchByte: ?u64,
    deferredSubmitWaitNs: u64,
    everyFlushCompleted: bool,
};

const Timing = struct {
    class: []const u8 = "diagnostic",
    wallNs: u64,
    writeSetupNs: u64,
    flushNs: u64,
    captureNs: u64,
};

const Artifact = struct {
    schemaVersion: u32 = 1,
    artifactKind: []const u8 = "doe_correctness_benchmark",
    workloadId: []const u8 = "metal_staged_write_exact_bytes",
    backend: []const u8 = "apple-metal",
    status: []const u8,
    iterations: u32,
    bytesPerIteration: usize,
    totalBytes: u64,
    faultInjection: bool,
    performanceClaimEligible: bool = false,
    correctness: Correctness,
    timing: Timing,
};

fn deviceProfile() model_profile.DeviceProfile {
    return .{
        .vendor = "apple",
        .api = .metal,
        .device_family = "m3",
        .driver_version = .{ .major = 1, .minor = 0, .patch = 0 },
    };
}

fn parsePositive(comptime T: type, option: []const u8, value: []const u8) !T {
    const parsed = std.fmt.parseUnsigned(T, value, 10) catch |err| {
        std.debug.print("{s} requires an unsigned count; received '{s}': {s}\n", .{ option, value, @errorName(err) });
        return err;
    };
    if (parsed == 0) {
        std.debug.print("{s} requires a positive count; received 0\n", .{option});
        return error.InvalidArgument;
    }
    return parsed;
}

fn parseArgs(argv: []const []const u8) !Config {
    var config = Config{};
    var index: usize = 0;
    while (index < argv.len) : (index += 1) {
        const arg = argv[index];
        if (std.mem.eql(u8, arg, "--inject-corruption")) {
            config.inject_corruption = true;
            continue;
        }
        if (std.mem.eql(u8, arg, "--iterations")) {
            index += 1;
            if (index >= argv.len) {
                std.debug.print("--iterations requires a count\n", .{});
                return error.MissingArgument;
            }
            config.iterations = try parsePositive(u32, arg, argv[index]);
            continue;
        }
        if (std.mem.eql(u8, arg, "--bytes")) {
            index += 1;
            if (index >= argv.len) {
                std.debug.print("--bytes requires a count\n", .{});
                return error.MissingArgument;
            }
            config.byte_count = try parsePositive(usize, arg, argv[index]);
            continue;
        }
        std.debug.print("unknown Metal staged-write option '{s}'; expected --iterations, --bytes, or --inject-corruption\n", .{arg});
        return error.UnknownArgument;
    }
    if (config.iterations > MAX_ITERATIONS or config.byte_count > MAX_BYTE_COUNT) {
        std.debug.print("Metal staged-write limits are {d} iterations and {d} bytes; received {d} iterations and {d} bytes\n", .{ MAX_ITERATIONS, MAX_BYTE_COUNT, config.iterations, config.byte_count });
        return error.InvalidArgument;
    }
    return config;
}

fn fillExpected(bytes: []u8, iteration: u32) void {
    const iteration_salt: usize = @as(usize, iteration) *% PATTERN_ITERATION_STRIDE;
    for (bytes, 0..) |*byte, index| {
        byte.* = @truncate((index *% PATTERN_BYTE_STRIDE) ^ (index >> PATTERN_SHIFT) ^ iteration_salt ^ PATTERN_SALT);
    }
}

fn writeArtifact(allocator: std.mem.Allocator, artifact: Artifact, output: std.fs.File) !void {
    const payload = try std.json.Stringify.valueAlloc(allocator, artifact, .{ .whitespace = .indent_2 });
    defer allocator.free(payload);
    try output.writeAll(payload);
    try output.writeAll("\n");
}

const Mismatches = struct {
    bytes: u64 = 0,
    first_byte: ?u64 = null,

    fn observe(self: *Mismatches, expected: []const u8, actual: []const u8, offset: u64) !void {
        if (actual.len != expected.len) {
            std.debug.print("Metal staged-write capture expected {d} bytes; received {d}\n", .{ expected.len, actual.len });
            return error.CaptureSizeMismatch;
        }
        for (expected, actual, 0..) |expected_byte, actual_byte, byte_index| {
            if (expected_byte == actual_byte) continue;
            self.bytes +|= 1;
            if (self.first_byte == null) self.first_byte = offset + byte_index;
        }
    }
};

fn run(allocator: std.mem.Allocator, config: Config) !u8 {
    if (builtin.os.tag != .macos) return error.UnsupportedPlatform;

    var session = try doe.composition.ExecutionSession.init(
        allocator,
        .native,
        deviceProfile(),
        null,
        .metal_doe_comparable,
        .{},
    );
    defer session.deinit();
    const runtime = session.contextPtr();

    runtime.configureUploadBehavior(.copy_dst, 1);
    runtime.configureQueueSyncMode(.deferred);

    var wall_timer = try std.time.Timer.start();
    var write_setup_ns: u64 = 0;
    var flush_ns: u64 = 0;
    var capture_ns: u64 = 0;
    var deferred_submit_wait_ns: u64 = 0;
    var mismatches: Mismatches = .{};
    var every_flush_completed = true;

    for (0..config.iterations) |iteration_raw| {
        const iteration: u32 = @intCast(iteration_raw);
        const handle = BUFFER_HANDLE_BASE + iteration;
        const expected = try allocator.alloc(u8, config.byte_count);
        defer allocator.free(expected);
        fillExpected(expected, iteration);

        const write_result = try runtime.execute_buffer_write_bytes_with_semantic(
            handle,
            0,
            config.byte_count,
            expected,
            .{},
        );
        if (write_result.status != execution.ExecutionStatus.ok) {
            return error.WriteFailed;
        }
        write_setup_ns +|= write_result.setup_ns;
        deferred_submit_wait_ns +|= write_result.submit_wait_ns;
        const completed_flush_ns = try runtime.flushQueue();
        flush_ns +|= completed_flush_ns;
        every_flush_completed = every_flush_completed and completed_flush_ns > 0;

        if (config.inject_corruption and iteration == 0) {
            var corrupt = [_]u8{expected[0] ^ 0xff};
            const corrupt_result = try runtime.execute_buffer_write_bytes_with_semantic(
                handle,
                0,
                config.byte_count,
                corrupt[0..],
                .{},
            );
            if (corrupt_result.status != execution.ExecutionStatus.ok) {
                return error.WriteFailed;
            }
            write_setup_ns +|= corrupt_result.setup_ns;
            deferred_submit_wait_ns +|= corrupt_result.submit_wait_ns;
            const corrupt_flush_ns = try runtime.flushQueue();
            flush_ns +|= corrupt_flush_ns;
            every_flush_completed = every_flush_completed and corrupt_flush_ns > 0;
        }

        var capture_timer = try std.time.Timer.start();
        const actual = try runtime.captureBuffer(allocator, handle, 0, config.byte_count);
        capture_ns +|= capture_timer.read();
        defer allocator.free(actual);

        try mismatches.observe(expected, actual, @as(u64, iteration) * config.byte_count);
    }

    const observed_matches = mismatches.bytes == 0;
    const content_outcome_satisfied = if (config.inject_corruption)
        !observed_matches
    else
        observed_matches;
    const outcome_satisfied = content_outcome_satisfied and
        deferred_submit_wait_ns == 0 and every_flush_completed;
    const artifact = Artifact{
        .status = if (outcome_satisfied)
            (if (config.inject_corruption) "oracle_rejected_corruption" else "pass")
        else
            "fail",
        .iterations = config.iterations,
        .bytesPerIteration = config.byte_count,
        .totalBytes = @as(u64, config.iterations) * config.byte_count,
        .faultInjection = config.inject_corruption,
        .correctness = .{
            .expectedOutcomeSatisfied = outcome_satisfied,
            .observedContentMatchesExpected = observed_matches,
            .mismatchedBytes = mismatches.bytes,
            .firstMismatchByte = mismatches.first_byte,
            .deferredSubmitWaitNs = deferred_submit_wait_ns,
            .everyFlushCompleted = every_flush_completed,
        },
        .timing = .{
            .wallNs = wall_timer.read(),
            .writeSetupNs = write_setup_ns,
            .flushNs = flush_ns,
            .captureNs = capture_ns,
        },
    };
    try writeArtifact(allocator, artifact, std.fs.File.stdout());

    if (!outcome_satisfied) return 3;
    return if (config.inject_corruption) 2 else 0;
}

pub fn main() !u8 {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();
    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);
    return run(allocator, try parseArgs(args[1..]));
}

test "Metal staged write capture rejects inconsistent lengths before reading bytes" {
    var mismatches: Mismatches = .{};
    try std.testing.expectError(error.CaptureSizeMismatch, mismatches.observe(&.{ 1, 2 }, &.{1}, 0));
    try std.testing.expectError(error.CaptureSizeMismatch, mismatches.observe(&.{1}, &.{ 1, 2 }, 0));
    try std.testing.expectEqual(@as(u64, 0), mismatches.bytes);
    try std.testing.expectEqual(null, mismatches.first_byte);
}

test "Metal staged write mismatch evidence retains first absolute byte across captures" {
    var mismatches: Mismatches = .{};
    try mismatches.observe(&.{ 1, 2, 3 }, &.{ 1, 2, 3 }, 0);
    try std.testing.expectEqual(@as(u64, 0), mismatches.bytes);
    try mismatches.observe(&.{ 1, 2, 3 }, &.{ 1, 4, 3 }, 3);
    try mismatches.observe(&.{ 1, 2, 3 }, &.{ 9, 2, 8 }, 6);
    try std.testing.expectEqual(@as(u64, 3), mismatches.bytes);
    try std.testing.expectEqual(@as(?u64, 4), mismatches.first_byte);
}

test "Metal staged write CLI preserves byte and sample bounds" {
    try std.testing.expectError(error.MissingArgument, parseArgs(&.{"--bytes"}));
    try std.testing.expectError(error.InvalidArgument, parseArgs(&.{ "--iterations", "0" }));
    try std.testing.expectError(error.InvalidArgument, parseArgs(&.{ "--bytes", "0" }));
    try std.testing.expectError(error.InvalidArgument, parseArgs(&.{ "--iterations", "129" }));
    try std.testing.expectError(error.InvalidArgument, parseArgs(&.{ "--bytes", "67108865" }));
    try std.testing.expectError(error.UnknownArgument, parseArgs(&.{"--typo"}));
    const config = try parseArgs(&.{ "--bytes", "1", "--bytes", "67108864", "--iterations", "128", "--inject-corruption" });
    try std.testing.expectEqual(MAX_ITERATIONS, config.iterations);
    try std.testing.expectEqual(MAX_BYTE_COUNT, config.byte_count);
    try std.testing.expect(config.inject_corruption);
}

fn exerciseArtifactAllocations(allocator: std.mem.Allocator, output: std.fs.File) !void {
    const artifact: Artifact = .{
        .status = "fail",
        .iterations = 1,
        .bytesPerIteration = 1,
        .totalBytes = 1,
        .faultInjection = false,
        .correctness = .{
            .expectedOutcomeSatisfied = false,
            .observedContentMatchesExpected = false,
            .mismatchedBytes = 1,
            .firstMismatchByte = 0,
            .deferredSubmitWaitNs = 0,
            .everyFlushCompleted = false,
        },
        .timing = .{ .wallNs = 1, .writeSetupNs = 1, .flushNs = 1, .captureNs = 1 },
    };
    try writeArtifact(allocator, artifact, output);
}

test "Metal staged write artifact releases allocations and preserves allocation errors" {
    var temp = std.testing.tmpDir(.{});
    defer temp.cleanup();
    const output = try temp.dir.createFile("fixture.json", .{});
    defer output.close();
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseArtifactAllocations, .{output});
}

test "Metal staged write rejects unsupported hosts without allocation or execution" {
    if (builtin.os.tag == .macos) return error.SkipZigTest;
    try std.testing.expectError(error.UnsupportedPlatform, run(std.testing.failing_allocator, .{}));
}

test "Metal staged write artifact preserves output errors and releases serialized storage" {
    if (builtin.os.tag != .linux) return error.SkipZigTest;
    const output = try std.fs.openFileAbsolute("/dev/full", .{ .mode = .write_only });
    defer output.close();
    try std.testing.expectError(error.NoSpaceLeft, exerciseArtifactAllocations(std.testing.allocator, output));
}
