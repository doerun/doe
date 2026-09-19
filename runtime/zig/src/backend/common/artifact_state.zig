const std = @import("std");
const artifact = @import("../../contracts/artifact.zig");

pub const Output = struct {
    directory: []const u8 = "bench/out/shader-artifacts",
    toolchain_path: []const u8 = "config/shader-toolchain.json",
};

pub const Snapshot = struct {
    module: []u8,
    status: []u8,
    meta: artifact.ArtifactMeta,
    spirv: ?[]u8,
    source_hash: ?artifact.Sha256Hex,
};

/// One provider owns this state and its allocator. Do not copy it after capture.
/// Output paths are borrowed for the owner's lifetime; pending inputs are copied.
pub const State = struct {
    allocator: std.mem.Allocator,
    output: Output = .{},
    pending: ?Snapshot = null,
    capture_error: ?anyerror = null,
    manifest_path: ?[]u8 = null,
    manifest_hash: ?artifact.Sha256Hex = null,
    last_signature: ?artifact.Sha256Hex = null,
    manifest_emit_count: u64 = 0,

    pub fn capture(self: *State, module: []const u8, meta: artifact.ArtifactMeta, status: []const u8, spirv: ?[]const u8, source_hash: ?artifact.Sha256Hex) !void {
        if (self.pending != null) return error.ArtifactPending;
        self.capture_error = null;
        errdefer |err| self.capture_error = err;
        const owned_module = try self.allocator.dupe(u8, module);
        errdefer self.allocator.free(owned_module);
        const owned_status = try self.allocator.dupe(u8, status);
        errdefer self.allocator.free(owned_status);
        const owned_spirv = if (spirv) |bytes| try self.allocator.dupe(u8, bytes) else null;
        self.pending = .{ .module = owned_module, .status = owned_status, .meta = meta, .spirv = owned_spirv, .source_hash = source_hash };
        self.capture_error = null;
    }

    pub fn clearPending(self: *State) void {
        if (self.pending) |snapshot| {
            self.allocator.free(snapshot.module);
            self.allocator.free(snapshot.status);
            if (snapshot.spirv) |bytes| self.allocator.free(bytes);
            self.pending = null;
        }
    }

    pub fn path(self: *const State) ?[]const u8 {
        if (self.pending != null or self.capture_error != null) return null;
        return self.manifest_path;
    }

    pub fn hash(self: *const State) ?[]const u8 {
        if (self.pending != null or self.capture_error != null) return null;
        if (self.manifest_hash) |*value| return value;
        return null;
    }

    pub fn deinit(self: *State) void {
        self.clearPending();
        if (self.manifest_path) |path_owned| self.allocator.free(path_owned);
        self.* = undefined;
    }
};

const TEST_META: artifact.ArtifactMeta = .{
    .backend_kind = .native_vulkan,
    .timing_source = .cpu_submit_wait,
    .comparability = .directional,
};

fn exerciseCapture(allocator: std.mem.Allocator) !void {
    var state = State{ .allocator = allocator };
    defer state.deinit();
    var module = [_]u8{'a'} ** 1024;
    var status = [_]u8{'b'} ** 512;
    var spirv = [_]u8{ 1, 2, 3, 4 };
    try state.capture(&module, TEST_META, &status, &spirv, null);
    @memset(&module, 'x');
    @memset(&status, 'y');
    @memset(&spirv, 0);
    try std.testing.expectEqual(@as(u8, 'a'), state.pending.?.module[0]);
    try std.testing.expectEqual(@as(u8, 'b'), state.pending.?.status[0]);
    try std.testing.expectEqualSlices(u8, &.{ 1, 2, 3, 4 }, state.pending.?.spirv.?);
    try std.testing.expectError(error.ArtifactPending, state.capture("other", TEST_META, "ok", null, null));
    try std.testing.expect(state.path() == null);
    state.clearPending();
    try state.capture("next", TEST_META, "ok", null, null);
}

test "artifact snapshots own long inputs and unwind every allocation failure" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseCapture, .{});
}
