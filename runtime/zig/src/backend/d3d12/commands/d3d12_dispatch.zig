const std = @import("std");
const model_compute_types = @import("../../../contracts/model/model_compute_types.zig");
const execution_contract = @import("../../../contracts/execution.zig");
const common_timing = @import("../../common/timing.zig");
const webgpu = @import("../../../contracts/runtime_types.zig");
const dc = @import("../d3d12_constants.zig");
const bridge = @import("../d3d12_bridge_decls.zig");

const DISPATCH_INDIRECT_ARG_BYTES = 3 * @sizeOf(u32);
// Baseline D3D12 dimensions; larger limits require an explicit device capability.
const MAX_DISPATCH_DIMENSION = dc.MAX_DISPATCH_DIMENSION;

pub const DispatchMetrics = execution_contract.DispatchMetrics;

pub const DispatchSubmission = struct {
    metrics: DispatchMetrics = .{},
    cmd_allocator: ?*anyopaque = null,
    cmd_list: ?*anyopaque = null,
    indirect_arg_buffer: ?*anyopaque = null,
};

pub fn validate(cmd: model_compute_types.DispatchCommand, fence_value: u64) !void {
    for ([_]u32{ cmd.x, cmd.y, cmd.z }) |dimension| {
        if (dimension == 0 or dimension > MAX_DISPATCH_DIMENSION) return error.InvalidArgument;
    }
    // UINT64_MAX is the native device-removal sentinel, never a submission ID.
    if (fence_value >= std.math.maxInt(u64) - 1) return error.InvalidState;
}

pub const DispatchState = State(bridge.c);

fn State(comptime native: type) type {
    return struct {
        const Self = @This();

        root_signature: ?*anyopaque = null,
        noop_pipeline: ?*anyopaque = null,
        cmd_allocator: ?*anyopaque = null,
        cmd_list: ?*anyopaque = null,
        dispatch_cmd_sig: ?*anyopaque = null,
        indirect_arg_buffer: ?*anyopaque = null,

        pub fn prepare_pipeline(self: *Self, device: ?*anyopaque, bytecode: []const u8) !void {
            if (self.noop_pipeline != null) return;
            if (device == null or bytecode.len == 0) return error.InvalidArgument;
            const root = native.d3d12_bridge_device_create_root_signature_empty(device) orelse return error.InvalidState;
            errdefer native.d3d12_bridge_release(root);
            const pipeline = native.d3d12_bridge_device_create_compute_pipeline(device, root, bytecode.ptr, bytecode.len) orelse return error.ShaderCompileFailed;
            self.root_signature = root;
            self.noop_pipeline = pipeline;
        }

        pub fn execute_dispatch(self: *Self, device: ?*anyopaque, queue: ?*anyopaque, fence: ?*anyopaque, fence_value: *u64, cmd: model_compute_types.DispatchCommand, queue_sync_mode: webgpu.QueueSyncMode) !DispatchSubmission {
            return self.execute(device, queue, fence, fence_value, cmd, queue_sync_mode, false);
        }

        pub fn execute_dispatch_indirect(self: *Self, device: ?*anyopaque, queue: ?*anyopaque, fence: ?*anyopaque, fence_value: *u64, cmd: model_compute_types.DispatchIndirectCommand, queue_sync_mode: webgpu.QueueSyncMode) !DispatchSubmission {
            return self.execute(device, queue, fence, fence_value, cmd, queue_sync_mode, true);
        }

        fn execute(self: *Self, device: ?*anyopaque, queue: ?*anyopaque, fence: ?*anyopaque, fence_value: *u64, cmd: model_compute_types.DispatchCommand, queue_sync_mode: webgpu.QueueSyncMode, indirect: bool) !DispatchSubmission {
            try validate(cmd, fence_value.*);
            if (device == null or queue == null or fence == null or self.noop_pipeline == null) return error.InvalidState;
            const setup_start = common_timing.now_ns();
            const deferred = queue_sync_mode != .per_command;
            var commands = if (deferred) try Commands.create(device) else blk: {
                if (self.cmd_list == null) {
                    const owned = try Commands.create(device);
                    self.cmd_allocator = owned.allocator;
                    self.cmd_list = owned.list;
                }
                break :blk Commands{ .allocator = self.cmd_allocator, .list = self.cmd_list };
            };
            errdefer {
                commands.deinit();
                if (!deferred) {
                    self.cmd_allocator = null;
                    self.cmd_list = null;
                }
            }

            var argument_buffer: ?*anyopaque = null;
            errdefer if (deferred) {
                if (argument_buffer) |buffer| native.d3d12_bridge_release(buffer);
            };
            if (indirect) {
                if (self.dispatch_cmd_sig == null) {
                    self.dispatch_cmd_sig = native.d3d12_bridge_device_create_command_signature_dispatch(device, null) orelse return error.InvalidState;
                }
                if (deferred) {
                    argument_buffer = native.d3d12_bridge_device_create_buffer(device, DISPATCH_INDIRECT_ARG_BYTES, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
                } else {
                    if (self.indirect_arg_buffer == null) {
                        self.indirect_arg_buffer = native.d3d12_bridge_device_create_buffer(device, DISPATCH_INDIRECT_ARG_BYTES, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
                    }
                    argument_buffer = self.indirect_arg_buffer;
                }
                const mapped = native.d3d12_bridge_resource_map(argument_buffer) orelse return error.InvalidState;
                const bytes: [*]u8 = @ptrCast(mapped);
                std.mem.writeInt(u32, bytes[0..4], cmd.x, .little);
                std.mem.writeInt(u32, bytes[4..8], cmd.y, .little);
                std.mem.writeInt(u32, bytes[8..12], cmd.z, .little);
                native.d3d12_bridge_resource_unmap(argument_buffer);
            }
            const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
            const encode_start = common_timing.now_ns();
            if (native.d3d12_bridge_command_allocator_reset(commands.allocator) != 0) return error.InvalidState;
            if (native.d3d12_bridge_command_list_reset(commands.list, commands.allocator) != 0) return error.InvalidState;
            native.d3d12_bridge_command_list_set_compute_root_signature(commands.list, self.root_signature);
            native.d3d12_bridge_command_list_set_pipeline_state(commands.list, self.noop_pipeline);
            if (indirect) {
                native.d3d12_bridge_command_list_execute_indirect(commands.list, self.dispatch_cmd_sig, 1, argument_buffer, 0);
            } else {
                native.d3d12_bridge_command_list_dispatch(commands.list, cmd.x, cmd.y, cmd.z);
            }
            if (native.d3d12_bridge_command_list_close_checked(commands.list) != 0) return error.InvalidState;
            const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
            const submit_start = common_timing.now_ns();
            native.d3d12_bridge_queue_execute_command_list(queue, commands.list);
            fence_value.* += 1;
            native.d3d12_bridge_queue_signal(queue, fence, fence_value.*);
            if (!deferred) native.d3d12_bridge_fence_wait(fence, fence_value.*);
            return .{
                .metrics = .{
                    .setup_ns = setup_ns,
                    .encode_ns = encode_ns,
                    .submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start),
                    .dispatch_count = 1,
                    .submit_count = 1,
                },
                .cmd_allocator = if (deferred) commands.allocator else null,
                .cmd_list = if (deferred) commands.list else null,
                .indirect_arg_buffer = if (deferred) argument_buffer else null,
            };
        }

        const Commands = struct {
            allocator: ?*anyopaque,
            list: ?*anyopaque,

            fn create(device: ?*anyopaque) !Commands {
                const allocator = native.d3d12_bridge_device_create_command_allocator(device) orelse return error.InvalidState;
                errdefer native.d3d12_bridge_release(allocator);
                const list = native.d3d12_bridge_device_create_command_list(device, allocator) orelse return error.InvalidState;
                errdefer native.d3d12_bridge_release(list);
                if (native.d3d12_bridge_command_list_close_checked(list) != 0) return error.InvalidState;
                return .{ .allocator = allocator, .list = list };
            }

            fn deinit(self: *Commands) void {
                if (self.list) |list| native.d3d12_bridge_release(list);
                if (self.allocator) |allocator| native.d3d12_bridge_release(allocator);
                self.* = .{ .allocator = null, .list = null };
            }
        };

        // The runtime drains submissions before releasing pipeline and signature state.
        pub fn deinit(self: *Self) void {
            if (self.cmd_list) |list| native.d3d12_bridge_release(list);
            if (self.cmd_allocator) |allocator| native.d3d12_bridge_release(allocator);
            if (self.noop_pipeline) |pipeline| native.d3d12_bridge_release(pipeline);
            if (self.root_signature) |root| native.d3d12_bridge_release(root);
            if (self.dispatch_cmd_sig) |signature| native.d3d12_bridge_release(signature);
            if (self.indirect_arg_buffer) |buffer| native.d3d12_bridge_release(buffer);
            self.* = .{};
        }
    };
}

const RecordingNative = struct {
    const Object = struct { live: bool = false, bytes: [DISPATCH_INDIRECT_ARG_BYTES]u8 = @splat(0xa5) };
    var objects: [64]Object = undefined;
    var count: usize = 0;
    var calls: usize = 0;
    var fail_at: usize = 0;
    var submissions: usize = 0;
    var waits: usize = 0;
    var last_dimensions: [3]u32 = .{ 0, 0, 0 };
    var external: u8 = 0;

    fn reset(failure: usize) void {
        objects = @splat(.{});
        count = 0;
        calls = 0;
        fail_at = failure;
        submissions = 0;
        waits = 0;
        last_dimensions = .{ 0, 0, 0 };
    }
    fn fails() bool {
        calls += 1;
        return calls == fail_at;
    }
    fn create() ?*anyopaque {
        if (fails()) return null;
        const entry = &objects[count];
        count += 1;
        entry.live = true;
        return entry;
    }
    fn object(handle: ?*anyopaque) *Object {
        return @ptrCast(@alignCast(handle.?));
    }
    fn live_count() usize {
        var result: usize = 0;
        for (objects[0..count]) |entry| result += @intFromBool(entry.live);
        return result;
    }
    fn d3d12_bridge_release(handle: ?*anyopaque) void {
        const entry = object(handle);
        std.debug.assert(entry.live);
        entry.live = false;
    }
    fn d3d12_bridge_device_create_root_signature_empty(_: ?*anyopaque) ?*anyopaque {
        return create();
    }
    fn d3d12_bridge_device_create_compute_pipeline(_: ?*anyopaque, _: ?*anyopaque, _: [*]const u8, _: usize) ?*anyopaque {
        return create();
    }
    fn d3d12_bridge_device_create_command_allocator(_: ?*anyopaque) ?*anyopaque {
        return create();
    }
    fn d3d12_bridge_device_create_command_list(_: ?*anyopaque, _: ?*anyopaque) ?*anyopaque {
        return create();
    }
    fn d3d12_bridge_command_list_close_checked(_: ?*anyopaque) c_int {
        return if (fails()) -1 else 0;
    }
    fn d3d12_bridge_command_allocator_reset(_: ?*anyopaque) c_int {
        return if (fails()) -1 else 0;
    }
    fn d3d12_bridge_command_list_reset(_: ?*anyopaque, _: ?*anyopaque) c_int {
        return if (fails()) -1 else 0;
    }
    fn d3d12_bridge_device_create_command_signature_dispatch(_: ?*anyopaque, root: ?*anyopaque) ?*anyopaque {
        std.debug.assert(root == null);
        return create();
    }
    fn d3d12_bridge_device_create_buffer(_: ?*anyopaque, size: usize, heap: c_int) ?*anyopaque {
        std.debug.assert(size == DISPATCH_INDIRECT_ARG_BYTES and heap == dc.HEAP_TYPE_UPLOAD);
        return create();
    }
    fn d3d12_bridge_resource_map(handle: ?*anyopaque) ?*anyopaque {
        if (fails()) return null;
        return &object(handle).bytes;
    }
    fn d3d12_bridge_resource_unmap(_: ?*anyopaque) void {}
    fn d3d12_bridge_command_list_set_compute_root_signature(_: ?*anyopaque, _: ?*anyopaque) void {}
    fn d3d12_bridge_command_list_set_pipeline_state(_: ?*anyopaque, _: ?*anyopaque) void {}
    fn d3d12_bridge_command_list_dispatch(_: ?*anyopaque, x: u32, y: u32, z: u32) void {
        last_dimensions = .{ x, y, z };
    }
    fn d3d12_bridge_command_list_execute_indirect(_: ?*anyopaque, _: ?*anyopaque, max_count: u32, handle: ?*anyopaque, offset: u64) void {
        std.debug.assert(max_count == 1 and offset == 0);
        const bytes = &object(handle).bytes;
        last_dimensions = .{
            std.mem.readInt(u32, bytes[0..4], .little),
            std.mem.readInt(u32, bytes[4..8], .little),
            std.mem.readInt(u32, bytes[8..12], .little),
        };
    }
    fn d3d12_bridge_queue_execute_command_list(_: ?*anyopaque, _: ?*anyopaque) void {
        submissions += 1;
    }
    fn d3d12_bridge_queue_signal(_: ?*anyopaque, _: ?*anyopaque, _: u64) void {}
    fn d3d12_bridge_fence_wait(_: ?*anyopaque, _: u64) void {
        waits += 1;
    }
    fn retire(submission: DispatchSubmission) void {
        if (submission.indirect_arg_buffer) |buffer| d3d12_bridge_release(buffer);
        if (submission.cmd_list) |list| d3d12_bridge_release(list);
        if (submission.cmd_allocator) |allocator| d3d12_bridge_release(allocator);
    }
};

test "D3D12 dispatch rejects invalid dimensions and exhausted fence IDs before native work" {
    const testing = std.testing;
    RecordingNative.reset(0);
    var state: State(RecordingNative) = .{};
    var fence_value: u64 = 0;
    for ([_]model_compute_types.DispatchCommand{
        .{ .x = 0, .y = 1, .z = 1 },
        .{ .x = 1, .y = MAX_DISPATCH_DIMENSION + 1, .z = 1 },
        .{ .x = 1, .y = 1, .z = 0 },
    }) |cmd| {
        try testing.expectError(error.InvalidArgument, state.execute_dispatch(null, null, null, &fence_value, cmd, .per_command));
        try testing.expectError(error.InvalidArgument, state.execute_dispatch_indirect(null, null, null, &fence_value, cmd, .per_command));
    }
    fence_value = std.math.maxInt(u64) - 1;
    try testing.expectError(error.InvalidState, state.execute_dispatch(null, null, null, &fence_value, .{ .x = 1, .y = 1, .z = 1 }, .per_command));
    try testing.expectEqual(@as(usize, 0), RecordingNative.calls);
    try testing.expectEqual(@as(usize, 0), RecordingNative.submissions);
}

test "D3D12 dispatch rolls back pipeline acquisition and permits retry" {
    const testing = std.testing;
    for (1..3) |failure| {
        RecordingNative.reset(failure);
        var state: State(RecordingNative) = .{};
        const result = state.prepare_pipeline(&RecordingNative.external, "compiled-test-fixture");
        if (failure == 1) try testing.expectError(error.InvalidState, result) else try testing.expectError(error.ShaderCompileFailed, result);
        try testing.expectEqual(@as(usize, 0), RecordingNative.live_count());
        try testing.expect(state.root_signature == null and state.noop_pipeline == null);
        RecordingNative.fail_at = 0;
        try state.prepare_pipeline(&RecordingNative.external, "compiled-test-fixture");
        state.deinit();
        try testing.expectEqual(@as(usize, 0), RecordingNative.live_count());
    }
}

test "D3D12 dispatch releases every pre-submission failure and retries cached commands" {
    const testing = std.testing;
    for ([_]webgpu.QueueSyncMode{ .per_command, .deferred }) |mode| {
        for ([_]bool{ false, true }) |indirect| {
            var failure: usize = 1;
            while (true) : (failure += 1) {
                RecordingNative.reset(0);
                var state: State(RecordingNative) = .{};
                const handle = &RecordingNative.external;
                try state.prepare_pipeline(handle, "compiled-test-fixture");
                RecordingNative.calls = 0;
                RecordingNative.fail_at = failure;
                var fence_value: u64 = 0;
                const submission = state.execute(handle, handle, handle, &fence_value, .{ .x = 7, .y = 3, .z = 2 }, mode, indirect) catch |err| {
                    try testing.expectEqual(error.InvalidState, err);
                    try testing.expectEqual(@as(usize, 0), RecordingNative.submissions);
                    try testing.expectEqual(@as(u64, 0), fence_value);
                    RecordingNative.fail_at = 0;
                    const retry = try state.execute(handle, handle, handle, &fence_value, .{ .x = 7, .y = 3, .z = 2 }, mode, indirect);
                    RecordingNative.retire(retry);
                    state.deinit();
                    try testing.expectEqual(@as(usize, 0), RecordingNative.live_count());
                    continue;
                };
                try testing.expectEqual(@as(u32, 1), submission.metrics.submit_count);
                try testing.expectEqual(@as(u32, 1), submission.metrics.dispatch_count);
                try testing.expectEqual([_]u32{ 7, 3, 2 }, RecordingNative.last_dimensions);
                RecordingNative.retire(submission);
                state.deinit();
                try testing.expectEqual(@as(usize, 0), RecordingNative.live_count());
                break;
            }
        }
    }
}

test "D3D12 indirect deferred submissions own immutable distinct argument buffers" {
    const testing = std.testing;
    RecordingNative.reset(0);
    var state: State(RecordingNative) = .{};
    const handle = &RecordingNative.external;
    try state.prepare_pipeline(handle, "compiled-test-fixture");
    var fence_value: u64 = 0;
    const first = try state.execute_dispatch_indirect(handle, handle, handle, &fence_value, .{ .x = 7, .y = 3, .z = 2 }, .deferred);
    const bytes = RecordingNative.object(first.indirect_arg_buffer).bytes;
    const second = try state.execute_dispatch_indirect(handle, handle, handle, &fence_value, .{ .x = 19, .y = 5, .z = 11 }, .deferred);
    try testing.expect(first.indirect_arg_buffer != second.indirect_arg_buffer);
    try testing.expectEqual(bytes, RecordingNative.object(first.indirect_arg_buffer).bytes);
    try testing.expectEqual([_]u32{ 19, 5, 11 }, RecordingNative.last_dimensions);
    try testing.expectEqual(@as(usize, 2), RecordingNative.submissions);
    try testing.expectEqual(@as(usize, 0), RecordingNative.waits);
    try testing.expectEqual(@as(u64, 2), fence_value);
    RecordingNative.retire(first);
    RecordingNative.retire(second);
    state.deinit();
    try testing.expectEqual(@as(usize, 0), RecordingNative.live_count());
}

test "D3D12 synchronous dispatch reuses completed commands and updates arguments" {
    const testing = std.testing;
    RecordingNative.reset(0);
    var state: State(RecordingNative) = .{};
    const handle = &RecordingNative.external;
    try state.prepare_pipeline(handle, "compiled-test-fixture");
    var fence_value: u64 = 0;
    _ = try state.execute_dispatch_indirect(handle, handle, handle, &fence_value, .{ .x = 1, .y = 2, .z = 3 }, .per_command);
    const created = RecordingNative.count;
    _ = try state.execute_dispatch_indirect(handle, handle, handle, &fence_value, .{ .x = 5, .y = 7, .z = 11 }, .per_command);
    try testing.expectEqual(created, RecordingNative.count);
    try testing.expectEqual([_]u32{ 5, 7, 11 }, RecordingNative.last_dimensions);
    try testing.expectEqual(@as(usize, 2), RecordingNative.waits);
    state.deinit();
    try testing.expectEqual(@as(usize, 0), RecordingNative.live_count());
}
