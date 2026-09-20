const std = @import("std");
const bridge = struct {
    var lost_failed_submission = false;
    var commits: usize = 0;
    fn metal_bridge_release(_: ?*anyopaque) void { lost_failed_submission = true; }
    fn metal_bridge_command_buffer_commit(_: ?*anyopaque) void { commits += 1; }
    fn metal_bridge_command_buffer_encode_signal_event(_: ?*anyopaque, _: ?*anyopaque, _: u64) void {}
    fn metal_bridge_end_compute_encoding(_: ?*anyopaque) void {}
    fn metal_bridge_render_encoder_end(_: ?*anyopaque) void {}
    fn metal_bridge_end_blit_encoding(_: ?*anyopaque) void {}
};
fn flush_queue(_: anytype) !u64 { return 0; }
const Owner = struct {
    streaming_cmd_buf: ?*anyopaque = null,
    outstanding_cmd_buf: ?*anyopaque = null,
    streaming_compute_encoder: ?*anyopaque = null,
    streaming_render_encoder: ?*anyopaque = null,
    streaming_blit_encoder: ?*anyopaque = null,
    streaming_gpu_timestamps_active: bool = false,
    streaming_compute_dispatch_count: u32 = 0,
    streaming_has_render: bool = false,
    streaming_has_copy: bool = false,
    streaming_max_upload_bytes: usize = 0,
    shared_event: ?*anyopaque = null,
    fence_value: u64 = 0,
    has_deferred_submissions: bool = false,
};
fn retire_outstanding_handle(self: anytype) void {
    if (self.outstanding_cmd_buf) |cb| {
        bridge.metal_bridge_release(cb);
        self.outstanding_cmd_buf = null;
    }
}
fn finalize_streaming_encoders(self: anytype) void {
    if (self.streaming_compute_encoder) |enc| {
        bridge.metal_bridge_end_compute_encoding(enc);
        self.streaming_compute_encoder = null;
    }
    if (self.streaming_render_encoder) |enc| {
        bridge.metal_bridge_render_encoder_end(enc);
        bridge.metal_bridge_release(enc);
        self.streaming_render_encoder = null;
    }
    if (self.streaming_blit_encoder) |enc| {
        bridge.metal_bridge_end_blit_encoding(enc);
        self.streaming_blit_encoder = null;
    }
}
fn transition_streaming_submission_deferred(self: anytype) !void {
    if (self.streaming_cmd_buf == null) return;
    if (self.streaming_gpu_timestamps_active) {
        _ = try flush_queue(self);
        return;
    }
    finalize_streaming_encoders(self);
    const cmd_buf = self.streaming_cmd_buf.?;

    self.fence_value +%= 1;
    if (self.shared_event) |ev| {
        bridge.metal_bridge_command_buffer_encode_signal_event(cmd_buf, ev, self.fence_value);
    }
    bridge.metal_bridge_command_buffer_commit(cmd_buf);

    // A later wait on the successor command buffer covers this committed work
    // too because both buffers execute in-order on the same Metal queue.
    retire_outstanding_handle(self);
    self.outstanding_cmd_buf = cmd_buf;
    self.has_deferred_submissions = true;
    self.streaming_cmd_buf = null;
    self.streaming_compute_dispatch_count = 0;
    self.streaming_has_render = false;
    self.streaming_has_copy = false;
    self.streaming_max_upload_bytes = 0;
    self.streaming_gpu_timestamps_active = false;
}
test "rollover must preserve the earlier failed submission for status inspection" {
    var first: u8 = 0;
    var second: u8 = 0;
    var owner = Owner{ .streaming_cmd_buf = &first };
    try transition_streaming_submission_deferred(&owner);
    owner.streaming_cmd_buf = &second;
    try transition_streaming_submission_deferred(&owner);
    try std.testing.expectEqual(@as(usize, 2), bridge.commits);
    try std.testing.expect(!bridge.lost_failed_submission);
}
