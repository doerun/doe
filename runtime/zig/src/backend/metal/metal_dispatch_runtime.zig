const std = @import("std");
const common_timing = @import("../common/timing.zig");
const execution_contract = @import("../../contracts/execution.zig");
const webgpu = @import("../../contracts/runtime_types.zig");
const bridge = @import("metal_bridge_decls.zig");
const resources = @import("metal_runtime_resources.zig");

const DEFAULT_DISPATCH_KERNEL = "dispatch_noop.wgsl";
const DISPATCH_INDIRECT_ARGS_BYTES = @sizeOf([3]u32);

pub const DispatchRunMetrics = execution_contract.DispatchMetrics;

const DispatchMode = enum { direct, indirect };

pub fn run_dispatch(runtime: anytype, x: u32, y: u32, z: u32, queue_sync_mode: webgpu.QueueSyncMode) !DispatchRunMetrics {
    return runDispatchWithBridge(runtime, .{ x, y, z }, queue_sync_mode, .direct, bridge);
}

pub fn run_dispatch_indirect(runtime: anytype, x: u32, y: u32, z: u32, queue_sync_mode: webgpu.QueueSyncMode) !DispatchRunMetrics {
    return runDispatchWithBridge(runtime, .{ x, y, z }, queue_sync_mode, .indirect, bridge);
}

fn runDispatchWithBridge(runtime: anytype, dimensions: [3]u32, queue_sync_mode: webgpu.QueueSyncMode, mode: DispatchMode, comptime native: type) !DispatchRunMetrics {
    for (dimensions) |dimension| if (dimension == 0) return error.InvalidArgument;
    const setup_start = common_timing.now_ns();
    // The shared indirect argument bytes cannot change until earlier users retire.
    if (mode == .indirect) _ = try runtime.flush_queue();
    try prepare_dispatch_submission(runtime, queue_sync_mode);
    const program = try runtime.ensure_kernel_pipeline_info(DEFAULT_DISPATCH_KERNEL, null);
    if (program.interface.binding_count != 0 or program.interface.needs_sizes_buf) return error.UnsupportedBindingLayout;
    const indirect_buffer = if (mode == .indirect) blk: {
        const buffer = try ensure_dispatch_indirect_args_buffer(runtime, native);
        try write_dispatch_indirect_args(buffer, dimensions, native);
        break :blk buffer;
    } else null;
    const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
    const encode_start = common_timing.now_ns();
    const cmd_buf = try encodeDispatchWithBridge(runtime.queue, program, dimensions, mode, indirect_buffer, native);
    var encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
    const submission_ns = try finalize_dispatch_submission(runtime, cmd_buf, queue_sync_mode, native);
    if (queue_sync_mode == .deferred) encode_ns +|= submission_ns;
    return .{
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = if (queue_sync_mode == .deferred) 0 else submission_ns,
        .dispatch_count = 1,
        .submit_count = 1,
    };
}

fn encodeDispatchWithBridge(queue: ?*anyopaque, program: resources.KernelPipelineInfo, dimensions: [3]u32, mode: DispatchMode, indirect_buffer: ?*anyopaque, comptime native: type) !*anyopaque {
    const command = native.metal_bridge_create_command_buffer(queue) orelse return error.MetalEncodingFailed;
    errdefer native.metal_bridge_release(command);
    const encoder = native.metal_bridge_cmd_buf_compute_encoder(command) orelse return error.MetalEncodingFailed;
    defer native.metal_bridge_end_compute_encoding(encoder);
    const encoded = switch (mode) {
        .direct => native.metal_bridge_compute_encoder_dispatch_checked(encoder, program.pipeline, &.{null}, &.{0}, &.{0}, 0, std.math.maxInt(u32), &dimensions, &program.workgroup_size, 1),
        .indirect => native.metal_bridge_compute_encoder_dispatch_indirect_checked(encoder, program.pipeline, indirect_buffer, 0, &program.workgroup_size),
    };
    if (encoded == 0) return error.MetalEncodingFailed;
    return command;
}

fn ensure_dispatch_indirect_args_buffer(runtime: anytype, comptime native: type) !?*anyopaque {
    if (runtime.dispatch_indirect_args_buffer == null) {
        runtime.dispatch_indirect_args_buffer = native.metal_bridge_device_new_buffer_shared(runtime.device, DISPATCH_INDIRECT_ARGS_BYTES) orelse return error.InvalidState;
    }
    return runtime.dispatch_indirect_args_buffer.?;
}

fn write_dispatch_indirect_args(buffer: ?*anyopaque, dimensions: [3]u32, comptime native: type) !void {
    if (native.metal_bridge_buffer_length(buffer) < DISPATCH_INDIRECT_ARGS_BYTES) return error.InvalidBindingRange;
    const mapped = native.metal_bridge_buffer_contents(buffer) orelse return error.InvalidState;
    const dispatch_arg_bytes = std.mem.asBytes(&dimensions);
    @memcpy(mapped[0..dispatch_arg_bytes.len], dispatch_arg_bytes);
}

fn prepare_dispatch_submission(runtime: anytype, queue_sync_mode: webgpu.QueueSyncMode) !void {
    try runtime.completion.check();
    if (queue_sync_mode == .deferred) {
        if (runtime.streaming_cmd_buf != null) {
            try runtime.transition_streaming_submission_deferred();
        }
        try runtime.completion.reserve(runtime.allocator);
        return;
    }
    if (runtime.streaming_cmd_buf != null or runtime.has_deferred_submissions or runtime.completion.pending.items.len != 0) {
        _ = try runtime.flush_queue();
    }
    try runtime.completion.reserve(runtime.allocator);
}

fn finalize_dispatch_submission(runtime: anytype, cmd_buf: *anyopaque, queue_sync_mode: webgpu.QueueSyncMode, comptime native: type) !u64 {
    const submit_start = common_timing.now_ns();
    runtime.completion.prepare(runtime.allocator, cmd_buf, native) catch |err| {
        native.metal_bridge_release(cmd_buf);
        return err;
    };
    if (queue_sync_mode == .deferred) {
        runtime.fence_value +%= 1;
        if (runtime.shared_event) |ev| {
            native.metal_bridge_command_buffer_encode_signal_event(cmd_buf, ev, runtime.fence_value);
        }
        native.metal_bridge_command_buffer_commit(cmd_buf);
        runtime.has_deferred_submissions = true;
        runtime.completion.retainSubmitted(cmd_buf);
        return common_timing.ns_delta(common_timing.now_ns(), submit_start);
    }
    native.metal_bridge_command_buffer_commit(cmd_buf);
    runtime.completion.retainSubmitted(cmd_buf);
    try runtime.completion.retire();
    const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start);
    try runtime.completion.check();
    return submit_wait_ns;
}

const DispatchProbe = struct {
    var command: u8 = 0;
    var encoder: u8 = 0;
    var arguments: [DISPATCH_INDIRECT_ARGS_BYTES]u8 = @splat(0);
    var failure: enum { none, command, encoder, encoding, preparation } = .none;
    var created: usize = 0;
    var ended: usize = 0;
    var released: usize = 0;
    var committed: usize = 0;
    var dimensions: [3]u32 = undefined;
    var workgroup: [3]u32 = undefined;

    fn reset() void {
        failure = .none;
        created = 0;
        ended = 0;
        released = 0;
        committed = 0;
        arguments = @splat(0);
    }
    pub fn metal_bridge_create_command_buffer(_: ?*anyopaque) ?*anyopaque {
        if (failure == .command) return null;
        created += 1;
        return &command;
    }
    pub fn metal_bridge_cmd_buf_compute_encoder(_: ?*anyopaque) ?*anyopaque {
        return if (failure == .encoder) null else &encoder;
    }
    pub fn metal_bridge_end_compute_encoding(_: ?*anyopaque) void {
        ended += 1;
    }
    pub fn metal_bridge_release(_: ?*anyopaque) void {
        released += 1;
    }
    pub fn metal_bridge_command_buffer_prepare_wait(_: ?*anyopaque) c_int {
        std.testing.expectEqual(@as(usize, 0), committed) catch @panic("notification registered after commit");
        return if (failure == .preparation) 0 else 1;
    }
    pub fn metal_bridge_command_buffer_commit(_: ?*anyopaque) void {
        std.testing.expectEqual(@as(usize, 1), ended) catch @panic("commit before encoder end");
        committed += 1;
    }
    pub fn metal_bridge_command_buffer_encode_signal_event(_: ?*anyopaque, _: ?*anyopaque, _: u64) void {}
    pub fn metal_bridge_device_new_buffer_shared(_: ?*anyopaque, size: usize) ?*anyopaque {
        std.testing.expectEqual(arguments.len, size) catch @panic("invalid indirect allocation");
        return &arguments;
    }
    pub fn metal_bridge_buffer_contents(_: ?*anyopaque) ?[*]u8 {
        return &arguments;
    }
    pub fn metal_bridge_buffer_length(_: ?*anyopaque) usize {
        return arguments.len;
    }
    pub fn metal_bridge_compute_encoder_dispatch_checked(_: ?*anyopaque, _: ?*anyopaque, _: [*]const ?*anyopaque, _: [*]const u64, _: [*]const u32, count: u32, sizes_slot: u32, grid: [*]const u32, group: [*]const u32, repeat: u32) c_int {
        std.testing.expectEqual(@as(u32, 0), count) catch @panic("unexpected binding");
        std.testing.expectEqual(std.math.maxInt(u32), sizes_slot) catch @panic("unexpected sizes slot");
        std.testing.expectEqual(@as(u32, 1), repeat) catch @panic("unexpected repeat");
        dimensions = grid[0..3].*;
        workgroup = group[0..3].*;
        return if (failure == .encoding) 0 else 1;
    }
    pub fn metal_bridge_compute_encoder_dispatch_indirect_checked(_: ?*anyopaque, _: ?*anyopaque, buffer: ?*anyopaque, offset: u64, group: [*]const u32) c_int {
        std.testing.expect(buffer == @as(?*anyopaque, &arguments) and offset == 0) catch @panic("wrong indirect binding");
        @memcpy(std.mem.asBytes(&dimensions), &arguments);
        workgroup = group[0..3].*;
        return if (failure == .encoding) 0 else 1;
    }
};

const ProbeRuntime = struct {
    allocator: std.mem.Allocator = std.testing.allocator,
    completion: @import("metal_completion.zig").Completion = .{},
    device: ?*anyopaque = null,
    queue: ?*anyopaque = null,
    streaming_cmd_buf: ?*anyopaque = null,
    shared_event: ?*anyopaque = null,
    fence_value: u64 = 0,
    has_deferred_submissions: bool = false,
    dispatch_indirect_args_buffer: ?*anyopaque = null,
    binding_count: usize = 0,
    flushes: usize = 0,

    pub fn ensure_kernel_pipeline_info(self: *@This(), kernel: []const u8, _: ?[]const u8) !resources.KernelPipelineInfo {
        try std.testing.expectEqualStrings(DEFAULT_DISPATCH_KERNEL, kernel);
        return .{ .pipeline = &DispatchProbe.command, .workgroup_size = .{ 7, 2, 1 }, .interface = .{ .binding_count = self.binding_count } };
    }
    pub fn flush_queue(self: *@This()) !u64 {
        // Simulate an independent earlier user of the shared argument bytes.
        try std.testing.expectEqualSlices(u8, &(@as([DISPATCH_INDIRECT_ARGS_BYTES]u8, @splat(0))), &DispatchProbe.arguments);
        self.flushes += 1;
        return 0;
    }
    pub fn transition_streaming_submission_deferred(_: *@This()) !void {}
    fn deinit(self: *@This()) void {
        // Probe references are host tokens, never native Metal objects.
        for (self.completion.pending.items) |command| DispatchProbe.metal_bridge_release(command);
        self.completion.pending.deinit(self.allocator);
    }
};

test "Metal direct and indirect dispatch reject encoding without submission or leaked commands" {
    for ([_]DispatchMode{ .direct, .indirect }) |mode| {
        for ([_]webgpu.QueueSyncMode{ .per_command, .deferred }) |sync| {
            for ([_]@TypeOf(DispatchProbe.failure){ .command, .encoder, .encoding }) |failure| {
                DispatchProbe.reset();
                DispatchProbe.failure = failure;
                var runtime = ProbeRuntime{};
                defer runtime.deinit();
                try std.testing.expectError(error.MetalEncodingFailed, runDispatchWithBridge(&runtime, .{ 3, 4, 5 }, sync, mode, DispatchProbe));
                try std.testing.expectEqual(@as(usize, 0), DispatchProbe.committed);
                try std.testing.expectEqual(DispatchProbe.created, DispatchProbe.released);
                try std.testing.expectEqual(@as(usize, if (failure == .encoding) 1 else 0), DispatchProbe.ended);
                try std.testing.expectEqual(@as(usize, 0), runtime.completion.pending.items.len);
                try std.testing.expect(!runtime.has_deferred_submissions);
            }
        }
    }
}

test "Metal dispatch reserves before encoding and rejects undeclared program resources" {
    for ([_]DispatchMode{ .direct, .indirect }) |mode| {
        for ([_]webgpu.QueueSyncMode{ .per_command, .deferred }) |sync| {
            DispatchProbe.reset();
            var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
            var runtime = ProbeRuntime{ .allocator = failing.allocator() };
            defer runtime.deinit();
            try std.testing.expectError(error.OutOfMemory, runDispatchWithBridge(&runtime, .{ 3, 4, 5 }, sync, mode, DispatchProbe));
            try std.testing.expectEqual(@as(usize, 0), DispatchProbe.created);
            try std.testing.expectEqual(@as(usize, 0), DispatchProbe.committed);
        }
        var runtime = ProbeRuntime{ .binding_count = 1 };
        defer runtime.deinit();
        try std.testing.expectError(error.UnsupportedBindingLayout, runDispatchWithBridge(&runtime, .{ 3, 4, 5 }, .deferred, mode, DispatchProbe));
        try std.testing.expectEqual(@as(usize, 0), DispatchProbe.created);
    }
}

test "Metal deferred dispatch transfers exactly one encoded command and preserves dimensions" {
    for ([_]DispatchMode{ .direct, .indirect }) |mode| {
        DispatchProbe.reset();
        var runtime = ProbeRuntime{};
        defer runtime.deinit();
        const metrics = try runDispatchWithBridge(&runtime, .{ 3, 4, 5 }, .deferred, mode, DispatchProbe);
        try std.testing.expectEqualDeep(@as([3]u32, .{ 3, 4, 5 }), DispatchProbe.dimensions);
        try std.testing.expectEqualDeep(@as([3]u32, .{ 7, 2, 1 }), DispatchProbe.workgroup);
        try std.testing.expectEqual(@as(usize, 1), DispatchProbe.committed);
        try std.testing.expectEqual(@as(usize, 0), DispatchProbe.released);
        try std.testing.expectEqual(@as(usize, 1), runtime.completion.pending.items.len);
        try std.testing.expectEqual(@as(usize, if (mode == .indirect) 1 else 0), runtime.flushes);
        try std.testing.expect(runtime.has_deferred_submissions);
        try std.testing.expectEqual(@as(u32, 1), metrics.dispatch_count);
        try std.testing.expectEqual(@as(u32, 1), metrics.submit_count);
        try std.testing.expectEqual(@as(u64, 0), metrics.submit_wait_ns);
    }
}

test "Metal dispatch notification rejection releases unsubmitted direct and indirect commands" {
    for ([_]DispatchMode{ .direct, .indirect }) |mode| {
        for ([_]webgpu.QueueSyncMode{ .per_command, .deferred }) |sync| {
            DispatchProbe.reset();
            DispatchProbe.failure = .preparation;
            var runtime = ProbeRuntime{};
            defer runtime.deinit();
            try std.testing.expectError(error.MetalWaitPreparationFailed, runDispatchWithBridge(&runtime, .{ 3, 4, 5 }, sync, mode, DispatchProbe));
            try std.testing.expectEqual(@as(usize, 0), DispatchProbe.committed);
            try std.testing.expectEqual(@as(usize, 1), DispatchProbe.released);
            try std.testing.expectEqual(@as(usize, 0), runtime.completion.pending.items.len);
        }
    }
}
