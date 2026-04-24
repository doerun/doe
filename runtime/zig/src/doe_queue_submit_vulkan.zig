// doe_queue_submit_vulkan.zig — process submitted command buffers on the
// Vulkan backend.
//
// Before this file existed, `doeNativeQueueSubmit` early-returned for
// Vulkan backends (see `doe_queue_submit_native.zig`). That meant every
// compute dispatch recorded into a DoeCommandEncoder was never replayed
// through the Vulkan runtime: the pipeline recorded the dispatch, the
// command buffer "finished", and submit silently did nothing. The minimum
// repro at `bench/repros/doe-runtime-zero-dispatch/repro.mjs` (a 3-line
// WGSL kernel writing u32(42)) observed readback=0 because of this path.
//
// Mirrors `submit_d3d12_commands` (`doe_queue_submit_d3d12.zig`) and
// `submit_metal_commands` (`doe_queue_submit_metal.zig`) in structure:
// iterate cmd_bufs, iterate each cb.cmds.items, dispatch each entry to
// the appropriate Vulkan replay helper, then flush the queue so
// subsequent `mapAsync` observes the written bytes.

const std = @import("std");
const builtin = @import("builtin");
const native_types = @import("doe_native_object_types.zig");
const native_helpers = @import("doe_native_object_helpers.zig");
const native_rt_helpers = @import("doe_native_runtime_helpers.zig");
const shared = @import("doe_queue_submit_shared.zig");
const vulkan_compute = @import("doe_vulkan_compute_native.zig");

const cast = native_helpers.cast;
const DoeCommandBuffer = native_types.DoeCommandBuffer;
const DoeQueue = native_types.DoeQueue;

const has_vulkan = (builtin.os.tag == .linux);

pub fn submit_vulkan_commands(q: *DoeQueue, count: usize, cmd_bufs: [*]const ?*anyopaque) void {
    if (comptime !has_vulkan) return;
    const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return;

    var executed_any_dispatch = false;
    for (cmd_bufs[0..count]) |raw| {
        const cb = cast(DoeCommandBuffer, raw) orelse continue;
        for (cb.cmds.items) |cmd| {
            switch (cmd) {
                .dispatch => |dispatch_cmd| {
                    vulkan_compute.vulkan_submit_recorded_dispatch(rt, dispatch_cmd);
                    executed_any_dispatch = true;
                },
                .dispatch_indirect => |dispatch_indirect_cmd| {
                    vulkan_compute.vulkan_submit_recorded_dispatch_indirect(rt, dispatch_indirect_cmd);
                    executed_any_dispatch = true;
                },
                // copy_buf on Vulkan is handled at record-time by
                // doeNativeCopyBufferToBuffer (immediate host-memcpy for
                // host-visible buffers). Nothing to do at submit-time.
                .copy_buf => {},
                // Other command kinds (texture copies, clear_buffer,
                // render passes, timestamps, query resolves) are not
                // currently routed through the Vulkan queue by the
                // existing encoder paths; they either no-op on this
                // backend or are handled elsewhere. Leave as no-ops
                // here for now — if a caller records one and relies on
                // queue.submit executing it, that's a separate gap
                // that would surface as its own zero/missing output.
                .copy_buffer_to_texture => {},
                .copy_texture_to_buffer => {},
                .clear_buffer => {},
                .copy_texture_to_texture => {},
                .render_pass => {},
                .write_timestamp => {},
                .resolve_query_set => {},
            }
        }
    }

    if (executed_any_dispatch) {
        _ = rt.flush_queue() catch |err| {
            shared.deliverInternalError(
                q.dev,
                "doe_queue_submit: vulkan flush after dispatch replay: {s}",
                .{@errorName(err)},
            );
        };
    }
}
