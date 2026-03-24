// metal_copy_queue.zig — Dedicated copy queue encoder and lifecycle management.
// Sharded from metal_native_runtime.zig to stay under the 777-line limit.

const bridge = @import("metal_bridge_decls.zig");
const metal_bridge_begin_blit_encoding = bridge.metal_bridge_begin_blit_encoding;
const metal_bridge_cmd_buf_blit_encoder = bridge.metal_bridge_cmd_buf_blit_encoder;
const metal_bridge_end_blit_encoding = bridge.metal_bridge_end_blit_encoding;
const metal_bridge_command_buffer_commit = bridge.metal_bridge_command_buffer_commit;
const metal_bridge_command_buffer_encode_signal_event = bridge.metal_bridge_command_buffer_encode_signal_event;
const metal_bridge_release = bridge.metal_bridge_release;
const cleanup = @import("metal_cleanup.zig");
const release_ref = cleanup.release_ref;

pub fn ensure_copy_blit_encoder(self: anytype) !void {
    if (self.copy_blit_encoder != null) return;
    if (self.copy_cmd_buf == null) {
        var encoder: ?*anyopaque = null;
        self.copy_cmd_buf = metal_bridge_begin_blit_encoding(self.copy_queue, &encoder) orelse return error.InvalidState;
        self.copy_blit_encoder = encoder;
    } else {
        self.copy_blit_encoder = metal_bridge_cmd_buf_blit_encoder(self.copy_cmd_buf) orelse return error.InvalidState;
    }
}

/// Commit the copy queue's command buffer with a signal event, then reset
/// copy queue state. The copy_fence_value is left set so that the next
/// main-queue commit can encode a GPU wait on it.
pub fn flush_copy_queue(self: anytype) void {
    if (self.copy_blit_encoder) |enc| {
        metal_bridge_end_blit_encoding(enc);
        self.copy_blit_encoder = null;
    }
    if (self.copy_cmd_buf) |cb| {
        self.copy_fence_value +%= 1;
        if (self.shared_event) |ev| {
            metal_bridge_command_buffer_encode_signal_event(cb, ev, self.copy_fence_value);
        }
        metal_bridge_command_buffer_commit(cb);
        // Do not wait — the main queue will encode a GPU-side wait.
        metal_bridge_release(cb);
        self.copy_cmd_buf = null;
    }
    self.has_pending_copies = false;
}

pub fn release_copy_queue_resources(self: anytype) void {
    if (self.copy_blit_encoder) |enc| {
        metal_bridge_end_blit_encoding(enc);
        self.copy_blit_encoder = null;
    }
    if (self.copy_cmd_buf) |cb| {
        metal_bridge_release(cb);
        self.copy_cmd_buf = null;
    }
    release_ref(&self.copy_queue);
    self.has_pending_copies = false;
}
