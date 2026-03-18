const bridge = @import("metal_bridge_decls.zig");

// Number of timestamp query slots: index 0 = begin, index 1 = end.
const QUERY_COUNT: u32 = 2;
const BEGIN_INDEX: u32 = 0;
const END_INDEX: u32 = 1;

pub const TimestampState = struct {
    counter_sample_buffer: ?*anyopaque = null,
    supported: bool = false,

    // Attempt to create the counter sample buffer for GPU timestamp queries.
    // Idempotent: returns immediately if already initialized.
    // Sets supported=false and leaves counter_sample_buffer null when the
    // device does not support MTLCounterSamplingPointAtStageBoundary or the
    // MTLCommonCounterTimestamp counter set is absent.
    pub fn init_resources(self: *TimestampState, device: ?*anyopaque) void {
        if (self.counter_sample_buffer != null) return;
        if (device == null) return;
        if (bridge.metal_bridge_supports_timestamp_query(device) == 0) {
            self.supported = false;
            return;
        }
        self.counter_sample_buffer = bridge.metal_bridge_create_counter_sample_buffer(device, QUERY_COUNT);
        self.supported = self.counter_sample_buffer != null;
    }

    // Sample a begin timestamp on the command buffer. Must be called before
    // the GPU work of interest. Creates a blit encoder, samples the counter,
    // and ends encoding — the sample point is at the stage boundary just
    // before subsequent encoders.
    pub fn record_begin(self: *TimestampState, cmd_buf: ?*anyopaque) void {
        if (self.counter_sample_buffer == null or cmd_buf == null) return;
        bridge.metal_bridge_sample_timestamp(cmd_buf, self.counter_sample_buffer, BEGIN_INDEX);
    }

    // Sample an end timestamp on the command buffer. Must be called after
    // the GPU work of interest. Same mechanics as record_begin.
    pub fn record_end(self: *TimestampState, cmd_buf: ?*anyopaque) void {
        if (self.counter_sample_buffer == null or cmd_buf == null) return;
        bridge.metal_bridge_sample_timestamp(cmd_buf, self.counter_sample_buffer, END_INDEX);
    }

    // Resolve the begin/end timestamps and return the elapsed time in
    // nanoseconds. Must be called after the command buffer has completed
    // (commit + waitUntilCompleted). Returns 0 on failure or if end <= begin.
    pub fn resolve_elapsed_ns(self: *TimestampState) u64 {
        if (self.counter_sample_buffer == null) return 0;
        var timestamps: [QUERY_COUNT]u64 = .{ 0, 0 };
        const ok = bridge.metal_bridge_resolve_timestamps_ns(
            self.counter_sample_buffer,
            0,
            QUERY_COUNT,
            &timestamps,
        );
        if (ok == 0) return 0;
        const begin_ns = timestamps[BEGIN_INDEX];
        const end_ns = timestamps[END_INDEX];
        if (end_ns <= begin_ns) return 0;
        return end_ns - begin_ns;
    }

    pub fn deinit(self: *TimestampState) void {
        if (self.counter_sample_buffer) |csb| {
            bridge.metal_bridge_destroy_counter_sample_buffer(csb);
        }
        self.* = .{};
    }
};
