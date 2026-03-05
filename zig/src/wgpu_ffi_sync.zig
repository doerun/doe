const std = @import("std");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const WebGPUBackend = @import("webgpu_ffi.zig").WebGPUBackend;

const QUEUE_SYNC_RETRY_LIMIT: u32 = 3;
const QUEUE_SYNC_RETRY_BACKOFF_NS: u64 = 1_000_000;
const TIMESTAMP_MAP_RETRY_LIMIT: u32 = 3;
const TIMESTAMP_MAP_RETRY_BACKOFF_NS: u64 = 1_000_000;

pub fn syncAfterSubmit(self: *WebGPUBackend) !void {
    if (self.queue_sync_mode == .per_command) {
        try self.waitForQueue();
    }
}

pub fn submitEmpty(self: *WebGPUBackend) !u64 {
    return try self.submitInternal(0, null);
}

pub fn submitCommandBuffers(self: *WebGPUBackend, command_buffers: []types.WGPUCommandBuffer) !u64 {
    return try self.submitInternal(command_buffers.len, command_buffers.ptr);
}

pub fn submitInternal(
    self: *WebGPUBackend,
    command_count: usize,
    command_ptr: ?[*]types.WGPUCommandBuffer,
) !u64 {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const submit_start_ns = std.time.nanoTimestamp();
    procs.wgpuQueueSubmit(self.queue.?, command_count, if (command_count == 0) null else command_ptr.?);
    try self.syncAfterSubmit();
    const submit_end_ns = std.time.nanoTimestamp();
    return if (submit_end_ns > submit_start_ns)
        @as(u64, @intCast(submit_end_ns - submit_start_ns))
    else
        0;
}

pub fn flushQueue(self: *WebGPUBackend) !u64 {
    const start = std.time.nanoTimestamp();
    try self.waitForQueue();
    const end = std.time.nanoTimestamp();
    return if (end > start) @as(u64, @intCast(end - start)) else 0;
}

pub fn waitForQueue(self: *WebGPUBackend) !void {
    var attempt: u32 = 0;
    while (attempt < QUEUE_SYNC_RETRY_LIMIT) : (attempt += 1) {
        if (self.waitForQueueOnce()) |_| {
            return;
        } else |err| {
            if (attempt + 1 < QUEUE_SYNC_RETRY_LIMIT and shouldRetryQueueWait(err)) {
                std.Thread.sleep(QUEUE_SYNC_RETRY_BACKOFF_NS);
                continue;
            }
            return err;
        }
    }
    return error.QueueSubmitTimeout;
}

pub fn waitForQueueOnce(self: *WebGPUBackend) !void {
    switch (self.queue_wait_mode) {
        .process_events => try self.waitForQueueProcessEvents(),
        .wait_any => try self.waitForQueueWaitAny(),
    }
}

pub fn shouldRetryQueueWait(err: anyerror) bool {
    return switch (err) {
        error.WaitTimedOut,
        error.QueueSubmitTimeout,
        error.WaitAnyIncomplete,
        => true,
        else => false,
    };
}

pub fn waitForQueueProcessEvents(self: *WebGPUBackend) !void {
    if (self.procs == null) return error.ProceduralNotReady;

    var done_state = types.QueueSubmitState{};

    const queue_done_callback_info = types.WGPUQueueWorkDoneCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_AllowProcessEvents,
        .callback = loader.queueWorkDoneCallback,
        .userdata1 = &done_state,
        .userdata2 = null,
    };
    const queue_done_future = self.procs.?.wgpuQueueOnSubmittedWorkDone(
        self.queue.?,
        queue_done_callback_info,
    );
    if (queue_done_future.id == 0) return error.QueueFutureUnavailable;
    try self.processEventsUntil(&done_state.done, loader.QUEUE_WAIT_TIMEOUT_NS);
    if (!done_state.done) return error.QueueSubmitTimeout;
    if (done_state.status == .@"error") {
        return error.QueueSubmissionError;
    }
}

pub fn waitForQueueWaitAny(self: *WebGPUBackend) !void {
    const procs = self.procs orelse return error.ProceduralNotReady;

    var done_state = types.QueueSubmitState{};
    const queue_done_callback_info = types.WGPUQueueWorkDoneCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_WaitAnyOnly,
        .callback = loader.queueWorkDoneCallback,
        .userdata1 = &done_state,
        .userdata2 = null,
    };
    const queue_done_future = procs.wgpuQueueOnSubmittedWorkDone(
        self.queue.?,
        queue_done_callback_info,
    );
    if (queue_done_future.id == 0) return error.QueueFutureUnavailable;

    var wait_infos = [_]types.WGPUFutureWaitInfo{
        .{
            .future = queue_done_future,
            .completed = types.WGPU_FALSE,
        },
    };
    const wait_status = procs.wgpuInstanceWaitAny(
        self.instance.?,
        wait_infos.len,
        wait_infos[0..].ptr,
        loader.QUEUE_WAIT_TIMEOUT_NS,
    );
    switch (wait_status) {
        .success => {},
        .timedOut => return error.WaitTimedOut,
        .@"error" => return error.WaitAnyFailed,
        else => return error.WaitAnyUnsupported,
    }

    if (!done_state.done) {
        try self.processEventsUntil(&done_state.done, loader.DEFAULT_WAIT_SLICE_NS);
    }
    if (!done_state.done) return error.WaitAnyIncomplete;
    if (done_state.status == .@"error") {
        return error.QueueSubmissionError;
    }
}

pub fn readTimestampBuffer(self: *WebGPUBackend, readback_buffer: types.WGPUBuffer) !u64 {
    const procs = self.procs orelse return error.ProceduralNotReady;
    var attempt: u32 = 0;
    while (attempt < TIMESTAMP_MAP_RETRY_LIMIT) : (attempt += 1) {
        if (self.readTimestampBufferOnce(procs, readback_buffer)) |delta| {
            return delta;
        } else |err| {
            if (attempt + 1 < TIMESTAMP_MAP_RETRY_LIMIT and shouldRetryTimestampMap(err)) {
                self.timestampLog(
                    "timestamp_readback_retry attempt={} error={s}\n",
                    .{ attempt + 1, @errorName(err) },
                );
                std.Thread.sleep(TIMESTAMP_MAP_RETRY_BACKOFF_NS);
                continue;
            }
            return err;
        }
    }
    return error.BufferMapFailed;
}

pub fn readTimestampBufferOnce(
    self: *WebGPUBackend,
    procs: types.Procs,
    readback_buffer: types.WGPUBuffer,
) !u64 {
    var map_state = types.BufferMapState{};
    const map_callback_info = types.WGPUBufferMapCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_AllowProcessEvents,
        .callback = loader.bufferMapCallback,
        .userdata1 = &map_state,
        .userdata2 = null,
    };
    const map_future = procs.wgpuBufferMapAsync(
        readback_buffer,
        types.WGPUMapMode_Read,
        0,
        types.TIMESTAMP_BUFFER_SIZE,
        map_callback_info,
    );
    if (map_future.id == 0) {
        self.timestampLog("map_async_future_id=0\n", .{});
        return error.BufferMapFailed;
    }
    try self.processEventsUntil(&map_state.done, loader.DEFAULT_TIMEOUT_NS);
    if (!map_state.done) {
        self.timestampLog("map_async_timeout\n", .{});
        return error.BufferMapTimeout;
    }
    if (map_state.status != types.WGPUMapAsyncStatus_Success) {
        self.timestampLog("map_async_status={}\n", .{map_state.status});
        return error.BufferMapFailed;
    }

    const mapped_ptr = procs.wgpuBufferGetConstMappedRange(readback_buffer, 0, types.TIMESTAMP_BUFFER_SIZE);
    if (mapped_ptr == null) {
        self.timestampLog("mapped_range=null\n", .{});
        return error.BufferMapFailed;
    }
    const timestamps = @as(*const [2]u64, @ptrCast(@alignCast(mapped_ptr)));
    const begin_ts = timestamps[0];
    const end_ts = timestamps[1];
    procs.wgpuBufferUnmap(readback_buffer);
    if (end_ts < begin_ts) {
        self.timestampLog("mapped_invalid_range begin={} end={}\n", .{ begin_ts, end_ts });
        return error.TimestampRangeInvalid;
    }
    const delta = end_ts - begin_ts;
    self.timestampLog("mapped_begin={} mapped_end={} mapped_delta={}\n", .{ begin_ts, end_ts, delta });
    return delta;
}

pub fn shouldRetryTimestampMap(err: anyerror) bool {
    return switch (err) {
        error.BufferMapTimeout,
        error.BufferMapFailed,
        => true,
        else => false,
    };
}

pub fn processEventsUntil(self: *WebGPUBackend, done: *const bool, timeout_ns: u64) !void {
    const start = std.time.nanoTimestamp();
    var spins: u32 = 0;
    while (!done.*) {
        self.procs.?.wgpuInstanceProcessEvents(self.instance.?);
        const elapsed = std.time.nanoTimestamp() - start;
        if (elapsed >= timeout_ns) return error.WaitTimedOut;
        spins += 1;
        if (spins > 1000) {
            std.Thread.sleep(1_000);
        }
    }
}
