const std = @import("std");
const common_timing = @import("../common/timing.zig");
const model = @import("../../model_webgpu_types.zig");
const bridge = @import("metal_bridge_decls.zig");

const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_release = bridge.metal_bridge_release;

const MAX_MAP_BYTES: usize = 256 * 1024 * 1024;

pub fn execute_map_async(runtime: anytype, cmd: model.MapAsyncCommand) !u64 {
    if (cmd.bytes == 0) return error.InvalidArgument;
    if (cmd.bytes > MAX_MAP_BYTES) return error.UnsupportedFeature;
    if (runtime.streaming_cmd_buf != null or runtime.has_deferred_submissions or runtime.outstanding_cmd_buf != null) {
        _ = try runtime.flush_queue();
    }

    const encode_start = common_timing.now_ns();
    const buffer = metal_bridge_device_new_buffer_shared(runtime.device, cmd.bytes) orelse return error.InvalidState;
    defer metal_bridge_release(buffer);

    const mapped = metal_bridge_buffer_contents(buffer) orelse return error.InvalidState;
    const bytes = mapped[0..cmd.bytes];
    switch (cmd.mode) {
        .write => bytes[0] = 0,
        .read => std.mem.doNotOptimizeAway(bytes[0]),
    }
    return common_timing.ns_delta(common_timing.now_ns(), encode_start);
}
