const common_timing = @import("../common/timing.zig");
const std = @import("std");
const webgpu = @import("../runtime_types.zig");
const bridge = @import("metal_bridge_decls.zig");
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_command_buffer_commit = bridge.metal_bridge_command_buffer_commit;
const metal_bridge_create_command_buffer = bridge.metal_bridge_create_command_buffer;
const metal_bridge_cmd_buf_encode_compute_dispatch_indirect = bridge.metal_bridge_cmd_buf_encode_compute_dispatch_indirect;
const metal_bridge_command_buffer_wait_completed = bridge.metal_bridge_command_buffer_wait_completed;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_encode_compute_dispatch = bridge.metal_bridge_encode_compute_dispatch;
const metal_bridge_release = bridge.metal_bridge_release;

const DEFAULT_DISPATCH_KERNEL = "dispatch_noop.metal";
const DISPATCH_INDIRECT_ARGS_BYTES = @sizeOf([3]u32);

pub const DispatchRunMetrics = struct {
    encode_ns: u64,
    submit_wait_ns: u64,
    dispatch_count: u32,
};

pub fn run_dispatch(runtime: anytype, x: u32, y: u32, z: u32, queue_sync_mode: webgpu.QueueSyncMode) !DispatchRunMetrics {
    if (x == 0 or y == 0 or z == 0) return error.InvalidArgument;
    if (queue_sync_mode == .deferred) return error.UnsupportedFeature;
    if (runtime.streaming_cmd_buf != null or runtime.has_deferred_submissions or runtime.outstanding_cmd_buf != null) {
        _ = try runtime.flush_queue();
    }
    const pipeline = try runtime.ensure_kernel_pipeline(DEFAULT_DISPATCH_KERNEL, null);
    const encode_start = common_timing.now_ns();
    const cmd_buf = metal_bridge_encode_compute_dispatch(runtime.queue, pipeline, null, 0, x, y, z) orelse return error.InvalidState;
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
    metal_bridge_command_buffer_commit(cmd_buf);
    const submit_start = common_timing.now_ns();
    metal_bridge_command_buffer_wait_completed(cmd_buf);
    const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start);
    metal_bridge_release(cmd_buf);
    return .{ .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns, .dispatch_count = 1 };
}

pub fn run_dispatch_indirect(runtime: anytype, x: u32, y: u32, z: u32, queue_sync_mode: webgpu.QueueSyncMode) !DispatchRunMetrics {
    if (x == 0 or y == 0 or z == 0) return error.InvalidArgument;
    if (queue_sync_mode == .deferred) return error.UnsupportedFeature;
    if (runtime.streaming_cmd_buf != null or runtime.has_deferred_submissions or runtime.outstanding_cmd_buf != null) {
        _ = try runtime.flush_queue();
    }
    const pipeline = try runtime.ensure_kernel_pipeline(DEFAULT_DISPATCH_KERNEL, null);
    const indirect_buffer = try ensure_dispatch_indirect_args_buffer(runtime);
    try write_dispatch_indirect_args(indirect_buffer, x, y, z);
    const encode_start = common_timing.now_ns();
    const cmd_buf = metal_bridge_create_command_buffer(runtime.queue) orelse return error.InvalidState;
    metal_bridge_cmd_buf_encode_compute_dispatch_indirect(cmd_buf, pipeline, null, 0, indirect_buffer, 0, 0, 0, 0);
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
    metal_bridge_command_buffer_commit(cmd_buf);
    const submit_start = common_timing.now_ns();
    metal_bridge_command_buffer_wait_completed(cmd_buf);
    const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start);
    metal_bridge_release(cmd_buf);
    return .{ .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns, .dispatch_count = 1 };
}

fn ensure_dispatch_indirect_args_buffer(runtime: anytype) !?*anyopaque {
    if (runtime.dispatch_indirect_args_buffer == null) {
        runtime.dispatch_indirect_args_buffer = metal_bridge_device_new_buffer_shared(runtime.device, DISPATCH_INDIRECT_ARGS_BYTES) orelse return error.InvalidState;
    }
    return runtime.dispatch_indirect_args_buffer.?;
}

fn write_dispatch_indirect_args(buffer: ?*anyopaque, x: u32, y: u32, z: u32) !void {
    const mapped = metal_bridge_buffer_contents(buffer) orelse return error.InvalidState;
    const dispatch_args = [3]u32{ x, y, z };
    const dispatch_arg_bytes = std.mem.asBytes(&dispatch_args);
    @memcpy(mapped[0..dispatch_arg_bytes.len], dispatch_arg_bytes);
}
