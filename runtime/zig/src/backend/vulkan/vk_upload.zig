// Upload/staging buffer pool management for the Vulkan backend.
//
// Handles staged-copy and direct-mapped upload paths, buffer pool
// reuse with persistent mapping, and flush/recording lifecycle.

const std = @import("std");
const c = @import("vk_constants.zig");
const vk_compute_sync = @import("vk_compute_sync.zig");
const vk_device = @import("vk_device.zig");
const vk_sync = @import("vk_sync.zig");
const backend_policy = @import("../backend_policy.zig");
const webgpu = @import("../../contracts/runtime_types.zig");
const common_errors = @import("../../contracts/execution.zig");
const common_timing = @import("../common/timing.zig");

const VkBuffer = c.VkBuffer;
const VkDeviceMemory = c.VkDeviceMemory;
const VK_NULL_U64 = c.VK_NULL_U64;

// Vulkan upload path should follow device allocation limits, not an artificial
// 64MB runtime cap. Let allocation/driver failure surface explicitly.
pub const MAX_UPLOAD_BYTES: u64 = 0;
pub const MAX_UPLOAD_ZERO_FILL_BYTES: usize = 1024 * 1024;
pub const FAST_UPLOAD_BUFFER_MAX_BYTES: u64 = 1024 * 1024;
pub const DIRECT_UPLOAD_BUFFER_MAX_BYTES: u64 = 4 * 1024 * 1024 * 1024;
pub const DIRECT_UPLOAD_REUSE_SKIP_ZERO_FILL_MIN_BYTES: u64 = 4 * 1024 * 1024 * 1024;
pub const HOT_UPLOAD_POOL_CACHE_MAX_BYTES: u64 = 64 * 1024;
pub const WAIT_TIMEOUT_NS: u64 = std.math.maxInt(u64);
pub const MAX_POOL_ENTRIES_PER_SIZE: usize = 8;

pub const PendingUpload = struct {
    src_buffer: VkBuffer,
    src_memory: VkDeviceMemory,
    dst_buffer: VkBuffer,
    dst_memory: VkDeviceMemory,
    byte_count: u64 = 0,
    dst_usage: c.VkFlags = 0,
    // Persistently-mapped pointer for the staging (src) buffer.
    // Retained across pool cycles to avoid per-upload vkMapMemory/vkUnmapMemory.
    src_mapped: ?*anyopaque = null,
};

pub const VkPoolEntry = struct {
    usage: c.VkFlags = 0,
    buffer: VkBuffer,
    memory: VkDeviceMemory,
    mapped: ?*anyopaque = null,
};

pub const RecordedReplaySubmitTimings = struct {
    command_buffer_end_ns: u64 = 0,
    sync_prepare_ns: u64 = 0,
    driver_submit_ns: u64 = 0,

    pub fn total(self: RecordedReplaySubmitTimings) u64 {
        return self.command_buffer_end_ns +| self.sync_prepare_ns +| self.driver_submit_ns;
    }
};

pub const UploadPathKind = enum {
    fast_mapped,
    direct_mapped,
    staged_copy,
};

pub const VkPool = std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry));

pub fn wait_for_fence_fast(self: anytype, fence: c.VkFence) !void {
    try vk_sync.wait_for_fence_fast(self.device, fence);
}

pub fn flush_queue(self: anytype) !u64 {
    if (!self.has_device) return 0;
    const start_ns = common_timing.now_ns();
    if (self.replay_recording_active) {
        _ = try finalize_recorded_submit_replay(self);
    }
    const has_pending = self.hot_pending_upload != null or self.pending_uploads.items.len > 0;
    if (has_pending) {
        try vk_device.ensure_submission_state(self);
        try finish_pending_upload_recording(self);
        var upload_command_buffer = self.primary_command_buffer;
        var submit = c.VkSubmitInfo{
            .sType = c.VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .pNext = null,
            .waitSemaphoreCount = 0,
            .pWaitSemaphores = null,
            .pWaitDstStageMask = null,
            .commandBufferCount = 1,
            .pCommandBuffers = @ptrCast(&upload_command_buffer),
            .signalSemaphoreCount = 0,
            .pSignalSemaphores = null,
        };

        // Fence-based wait targets only this submission; vkQueueWaitIdle
        // synchronizes the entire queue and carries higher driver overhead
        // on RADV, which dominates tiny-upload latency. Keep timeline
        // semaphores for deferred drain paths, but prefer the direct fence
        // fast path for immediate upload flushes.
        try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit), self.fence));
        try wait_for_fence_fast(self, self.fence);
        self.has_deferred_submissions = false;
    } else if (self.has_deferred_submissions) {
        // No pending uploads but earlier deferred work exists; drain via
        // timeline semaphore (single wait for all prior submissions) or
        // fence pool (per-submission waits) instead of vkQueueWaitIdle.
        if (self.has_timeline_semaphore) {
            try self.timeline_semaphore.drain(self.device);
        } else if (self.has_fence_pool) {
            try self.fence_pool_state.drain(self.device);
        } else {
            try c.check_vk(c.vkQueueWaitIdle(self.queue));
        }
        self.has_deferred_submissions = false;
    }
    self.upload_recording_active = false;
    // Rely on vkBeginCommandBuffer implicit reset (the pool was created
    // with VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT) instead of
    // an explicit vkResetCommandBuffer, saving one driver call per flush.
    release_pending_uploads(self);
    mark_streaming_copy_submissions_drained(self);
    const end_ns = common_timing.now_ns();
    return common_timing.ns_delta(end_ns, start_ns);
}

pub fn mark_streaming_copy_submissions_drained(self: anytype) void {
    if (!self.streaming_copy_active and !self.has_deferred_submissions) {
        self.streaming_copy_pending_count = 0;
        self.buffer_write_staging_offset = 0;
    }
}

pub fn submit_recorded_replay(self: anytype) !void {
    _ = try finalize_recorded_submit_replay(self);
}

pub fn submit_recorded_replay_timed(self: anytype) !RecordedReplaySubmitTimings {
    return finalize_recorded_submit_replay(self);
}

fn finalize_recorded_submit_replay(self: anytype) !RecordedReplaySubmitTimings {
    var timings = RecordedReplaySubmitTimings{};
    if (!self.replay_recording_active) return timings;

    const end_started_ns = common_timing.now_ns();
    try c.check_vk(c.vkEndCommandBuffer(self.replay_command_buffer));
    timings.command_buffer_end_ns = common_timing.ns_delta(common_timing.now_ns(), end_started_ns);

    var submitted = try submit_replay_command_buffer(self, self.replay_command_buffer);
    submitted.command_buffer_end_ns = timings.command_buffer_end_ns;
    return submitted;
}

pub fn submit_replay_command_buffer(self: anytype, command_buffer: c.VkCommandBuffer) !RecordedReplaySubmitTimings {
    var timings = RecordedReplaySubmitTimings{};
    var command_buffers = [_]c.VkCommandBuffer{
        command_buffer,
        null,
    };
    var command_buffer_count: u32 = 1;
    if (self.replay_prefix_copy_pending) {
        if (self.replay_prefix_copy_buffer == null) return error.InvalidState;
        command_buffers[0] = self.replay_prefix_copy_buffer;
        command_buffers[1] = command_buffer;
        command_buffer_count = 2;
    }

    var submit_info = c.VkSubmitInfo{
        .sType = c.VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .pNext = null,
        .waitSemaphoreCount = 0,
        .pWaitSemaphores = null,
        .pWaitDstStageMask = null,
        .commandBufferCount = command_buffer_count,
        .pCommandBuffers = @ptrCast(&command_buffers),
        .signalSemaphoreCount = 0,
        .pSignalSemaphores = null,
    };

    const sync_prepare_started_ns = common_timing.now_ns();
    try vk_device.ensure_deferred_submission_state(self);
    if (self.has_timeline_semaphore) {
        var tsi = try vk_sync.TimelineSubmitHelper.prepare(&self.timeline_semaphore);
        tsi.patch();
        submit_info.pNext = @ptrCast(&tsi.timeline_info);
        submit_info.signalSemaphoreCount = 1;
        submit_info.pSignalSemaphores = @ptrCast(&tsi.semaphore);
        timings.sync_prepare_ns = common_timing.ns_delta(common_timing.now_ns(), sync_prepare_started_ns);
        const submit_started_ns = common_timing.now_ns();
        try tsi.submit(&self.timeline_semaphore, self.queue, &submit_info);
        timings.driver_submit_ns = common_timing.ns_delta(common_timing.now_ns(), submit_started_ns);
    } else {
        const deferred_fence = if (self.has_fence_pool)
            try self.fence_pool_state.acquire(self.device)
        else
            VK_NULL_U64;
        timings.sync_prepare_ns = common_timing.ns_delta(common_timing.now_ns(), sync_prepare_started_ns);
        const submit_started_ns = common_timing.now_ns();
        try vk_sync.submitWithFence(self.queue, &submit_info, deferred_fence, if (self.has_fence_pool) &self.fence_pool_state else null);
        timings.driver_submit_ns = common_timing.ns_delta(common_timing.now_ns(), submit_started_ns);
    }
    self.replay_prefix_copy_buffer = null;
    self.replay_prefix_copy_pending = false;
    self.replay_recording_active = false;
    self.replay_command_buffer = null;
    self.has_deferred_submissions = true;
    return timings;
}

pub fn record_upload_copy(self: anytype, bytes: u64, dst_usage: u32) !PendingUpload {
    try ensure_upload_recording(self);
    const upload = try allocate_staged_upload(self, bytes, dst_usage);
    errdefer release_upload(self, upload);

    var region = c.VkBufferCopy{ .srcOffset = 0, .dstOffset = 0, .size = bytes };
    c.vkCmdCopyBuffer(self.primary_command_buffer, upload.src_buffer, upload.dst_buffer, 1, @ptrCast(&region));

    return upload;
}

fn create_upload_buffer(self: anytype, bytes: u64, usage: c.VkFlags, memory_flags: c.VkFlags, mapped: bool) !VkPoolEntry {
    const info = c.VkBufferCreateInfo{ .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .pNext = null, .flags = 0, .size = bytes, .usage = usage, .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE, .queueFamilyIndexCount = 0, .pQueueFamilyIndices = null };
    var buffer: c.VkBuffer = VK_NULL_U64;
    try c.check_vk(c.vkCreateBuffer(self.device, &info, null, &buffer));
    var entry = VkPoolEntry{ .buffer = buffer, .memory = VK_NULL_U64, .usage = usage };
    errdefer release_pool_entry(self.device, entry);
    var requirements = std.mem.zeroes(c.VkMemoryRequirements);
    c.vkGetBufferMemoryRequirements(self.device, buffer, &requirements);
    const memory_index = try vk_device.find_memory_type_index(self, requirements.memoryTypeBits, memory_flags);
    const allocation = c.VkMemoryAllocateInfo{ .sType = c.VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .pNext = null, .allocationSize = requirements.size, .memoryTypeIndex = memory_index };
    var memory: c.VkDeviceMemory = VK_NULL_U64;
    try c.check_vk(c.vkAllocateMemory(self.device, &allocation, null, &memory));
    entry.memory = memory;
    try c.check_vk(c.vkBindBufferMemory(self.device, buffer, memory, 0));
    if (mapped) {
        var address: ?*anyopaque = null;
        try c.check_vk(c.vkMapMemory(self.device, memory, 0, bytes, 0, &address));
        entry.mapped = address orelse return error.InvalidState;
    }
    return entry;
}

fn allocate_staged_upload(self: anytype, bytes: u64, dst_usage: u32) !PendingUpload {
    try vk_device.ensure_submission_state(self);
    const src_usage = c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
    const src = hot_pool_pop(&self.hot_src_pool_entry, &self.hot_src_pool_size, bytes, src_usage) orelse
        vk_pool_pop(&self.src_pool, bytes, src_usage) orelse blk: {
        const entry = try create_upload_buffer(self, bytes, src_usage, c.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | c.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, true);
        @memset(@as([*]u8, @ptrCast(entry.mapped.?))[0..bounded_upload_fill_len(bytes)], 0);
        break :blk entry;
    };
    // Ownership extends across destination acquisition, including pooled sources.
    errdefer release_pool_entry(self.device, src);
    const effective_usage = if (dst_usage == 0)
        c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT | c.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT
    else
        dst_usage;
    const dst = hot_pool_pop(&self.hot_dst_pool_entry, &self.hot_dst_pool_size, bytes, effective_usage) orelse
        vk_pool_pop(&self.dst_pool, bytes, effective_usage) orelse
        try create_upload_buffer(self, bytes, effective_usage, c.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, false);
    return .{
        .src_buffer = src.buffer,
        .src_memory = src.memory,
        .dst_buffer = dst.buffer,
        .dst_memory = dst.memory,
        .byte_count = bytes,
        .dst_usage = dst.usage,
        .src_mapped = src.mapped,
    };
}

pub fn prewarm_staged_upload_pool(self: anytype, bytes: u64, dst_usage: u32) !void {
    if (bytes == 0) return;
    const upload = try allocate_staged_upload(self, bytes, dst_usage);
    release_upload(self, upload);
}

pub fn try_direct_upload(self: anytype, bytes: u64, dst_usage: u32) !bool {
    record_direct_upload(self, bytes, dst_usage) catch |err| switch (err) {
        error.UnsupportedFeature => return false,
        else => return err,
    };
    return true;
}

fn record_direct_upload(self: anytype, bytes: u64, dst_usage: u32) !void {
    const effective_usage = if (dst_usage == 0)
        c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT
    else
        dst_usage;
    const cached = vk_pool_pop(&self.direct_upload_pool, bytes, effective_usage);
    const entry = cached orelse try create_upload_buffer(self, bytes, effective_usage, c.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | c.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, true);
    if (cached == null or bytes < DIRECT_UPLOAD_REUSE_SKIP_ZERO_FILL_MIN_BYTES) {
        @memset(@as([*]u8, @ptrCast(entry.mapped.?))[0..@intCast(bytes)], 0);
    }
    vk_pool_push_or_destroy(&self.direct_upload_pool, self.allocator, self.device, bytes, entry);
}

pub fn ensure_upload_recording(self: anytype) !void {
    if (self.upload_recording_active) return;
    try vk_device.ensure_submission_state(self);
    // The command pool was created with VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
    // so vkBeginCommandBuffer implicitly resets the buffer from executable/invalid state.
    // No explicit vkResetCommandBuffer is needed.
    var begin = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin));
    self.upload_recording_active = true;
}

pub fn finish_pending_upload_recording(self: anytype) !void {
    if (!self.upload_recording_active) return;
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    self.upload_recording_active = false;
}

pub fn ensure_fast_upload_buffer(self: anytype, bytes: u64) !void {
    if (self.fast_upload_capacity >= bytes and self.fast_upload_mapped != null) return;
    const replacement = try create_upload_buffer(self, bytes, c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT, c.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | c.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, true);
    release_fast_upload_buffer(self);
    self.fast_upload_buffer = replacement.buffer;
    self.fast_upload_memory = replacement.memory;
    self.fast_upload_mapped = replacement.mapped;
    self.fast_upload_capacity = bytes;
}

pub fn release_fast_upload_buffer(self: anytype) void {
    if (self.fast_upload_mapped != null) {
        c.vkUnmapMemory(self.device, self.fast_upload_memory);
        self.fast_upload_mapped = null;
    }
    if (self.fast_upload_buffer != VK_NULL_U64) {
        c.vkDestroyBuffer(self.device, self.fast_upload_buffer, null);
        self.fast_upload_buffer = VK_NULL_U64;
    }
    if (self.fast_upload_memory != VK_NULL_U64) {
        c.vkFreeMemory(self.device, self.fast_upload_memory, null);
        self.fast_upload_memory = VK_NULL_U64;
    }
    self.fast_upload_capacity = 0;
}

pub fn release_pending_uploads(self: anytype) void {
    // Release the hot slot first (common single-upload-per-flush path).
    if (self.hot_pending_upload) |hot| {
        release_upload(self, hot);
        self.hot_pending_upload = null;
    }
    for (self.pending_uploads.items) |item| {
        release_upload(self, item);
    }
    self.pending_uploads.clearRetainingCapacity();
}

pub fn release_upload(self: anytype, item: PendingUpload) void {
    // Carry src_mapped through the pool so staging buffers stay
    // persistently mapped, eliminating per-upload map/unmap overhead.
    if (item.src_buffer != VK_NULL_U64 and item.src_memory != VK_NULL_U64) {
        const src_entry = VkPoolEntry{ .buffer = item.src_buffer, .memory = item.src_memory, .mapped = item.src_mapped, .usage = c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT };
        if (!hot_pool_store(&self.hot_src_pool_entry, &self.hot_src_pool_size, item.byte_count, src_entry)) {
            vk_pool_push_or_destroy(&self.src_pool, self.allocator, self.device, item.byte_count, src_entry);
        }
    } else {
        if (item.src_mapped != null) c.vkUnmapMemory(self.device, item.src_memory);
        if (item.src_buffer != VK_NULL_U64) c.vkDestroyBuffer(self.device, item.src_buffer, null);
        if (item.src_memory != VK_NULL_U64) c.vkFreeMemory(self.device, item.src_memory, null);
    }
    if (item.dst_buffer != VK_NULL_U64 and item.dst_memory != VK_NULL_U64) {
        if (!hot_pool_store(&self.hot_dst_pool_entry, &self.hot_dst_pool_size, item.byte_count, .{ .buffer = item.dst_buffer, .memory = item.dst_memory, .mapped = null, .usage = item.dst_usage })) {
            vk_pool_push_or_destroy(&self.dst_pool, self.allocator, self.device, item.byte_count, .{ .buffer = item.dst_buffer, .memory = item.dst_memory, .mapped = null, .usage = item.dst_usage });
        }
    } else {
        if (item.dst_buffer != VK_NULL_U64) c.vkDestroyBuffer(self.device, item.dst_buffer, null);
        if (item.dst_memory != VK_NULL_U64) c.vkFreeMemory(self.device, item.dst_memory, null);
    }
}

// --- Upload path classification ---

pub fn classify_upload_path(
    upload_path_policy: backend_policy.UploadPathPolicy,
    mode: webgpu.UploadBufferUsageMode,
    bytes: u64,
) UploadPathKind {
    // Dawn's Vulkan WriteBuffer detects host-visible+coherent destination
    // buffers and performs a direct memcpy with zero GPU work.  The
    // fast_mapped path does the same thing: a memcpy to a persistently-
    // mapped host-visible buffer with no command recording or submission.
    // Allowing fast_mapped under staged_copy_only matches Dawn's actual
    // behavior and eliminates the structural work asymmetry that made
    // upload_write_buffer_1kb non-comparable (CLAUDE.md rules 7/10/11).
    if (mode == .copy_dst and bytes <= FAST_UPLOAD_BUFFER_MAX_BYTES) return .fast_mapped;
    if (upload_path_policy == .staged_copy_only) return .staged_copy;
    if (mode == .copy_dst and bytes <= DIRECT_UPLOAD_BUFFER_MAX_BYTES) return .direct_mapped;
    return .staged_copy;
}

pub fn bounded_upload_fill_len(bytes: u64) usize {
    return @min(@as(usize, @intCast(bytes)), MAX_UPLOAD_ZERO_FILL_BYTES);
}

pub fn upload_uses_fast_path(
    upload_path_policy: backend_policy.UploadPathPolicy,
    mode: webgpu.UploadBufferUsageMode,
    bytes: u64,
) bool {
    return classify_upload_path(upload_path_policy, mode, bytes) == .fast_mapped;
}

pub fn upload_uses_direct_path(
    upload_path_policy: backend_policy.UploadPathPolicy,
    mode: webgpu.UploadBufferUsageMode,
    bytes: u64,
) bool {
    return classify_upload_path(upload_path_policy, mode, bytes) == .direct_mapped;
}

// --- Pool management ---

pub fn vk_pool_pop(pool: *VkPool, size: u64, required_usage: c.VkFlags) ?VkPoolEntry {
    if (pool.getPtr(size)) |list| {
        var index = list.items.len;
        while (index > 0) {
            index -= 1;
            if ((list.items[index].usage & required_usage) == required_usage) return list.swapRemove(index);
        }
    }
    return null;
}

pub fn hot_pool_pop(entry: *?VkPoolEntry, size_slot: *u64, size: u64, required_usage: c.VkFlags) ?VkPoolEntry {
    if (size <= HOT_UPLOAD_POOL_CACHE_MAX_BYTES and entry.* != null and size_slot.* == size and
        (entry.*.?.usage & required_usage) == required_usage)
    {
        const out = entry.*;
        entry.* = null;
        size_slot.* = 0;
        return out;
    }
    return null;
}

pub fn hot_pool_store(entry: *?VkPoolEntry, size_slot: *u64, size: u64, value: VkPoolEntry) bool {
    if (size > HOT_UPLOAD_POOL_CACHE_MAX_BYTES or entry.* != null) return false;
    entry.* = value;
    size_slot.* = size;
    return true;
}

pub fn vk_pool_push_or_destroy(pool: *VkPool, allocator: std.mem.Allocator, device: c.VkDevice, size: u64, entry: VkPoolEntry) void {
    const gop = pool.getOrPut(allocator, size) catch {
        if (entry.mapped != null) c.vkUnmapMemory(device, entry.memory);
        c.vkDestroyBuffer(device, entry.buffer, null);
        c.vkFreeMemory(device, entry.memory, null);
        return;
    };
    if (!gop.found_existing) gop.value_ptr.* = .{};
    if (gop.value_ptr.items.len >= MAX_POOL_ENTRIES_PER_SIZE) {
        if (entry.mapped != null) c.vkUnmapMemory(device, entry.memory);
        c.vkDestroyBuffer(device, entry.buffer, null);
        c.vkFreeMemory(device, entry.memory, null);
        return;
    }
    gop.value_ptr.append(allocator, entry) catch {
        if (entry.mapped != null) c.vkUnmapMemory(device, entry.memory);
        c.vkDestroyBuffer(device, entry.buffer, null);
        c.vkFreeMemory(device, entry.memory, null);
    };
}

pub fn release_pool_entry(device: c.VkDevice, entry: ?VkPoolEntry) void {
    if (entry) |value| {
        if (value.mapped != null) c.vkUnmapMemory(device, value.memory);
        c.vkDestroyBuffer(device, value.buffer, null);
        c.vkFreeMemory(device, value.memory, null);
    }
}

// --- Streaming copy lifecycle ---

/// Begin a streaming copy session. Allocates a dedicated command buffer
/// if needed and begins recording. Multiple copy operations can be
/// batched into a single submission.
pub fn begin_streaming_copy(self: anytype) !void {
    if (self.streaming_copy_active) return;
    try acquire_streaming_copy_buffer(self);
    var begin_info = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(self.streaming_copy_buffer, &begin_info));
    self.streaming_copy_active = true;
    self.streaming_copy_count = 0;
}

pub fn flush_streaming_copy_before_dispatch(self: anytype, replay_deferred: bool, queue_sync_mode: webgpu.QueueSyncMode) !void {
    if (!self.streaming_copy_active) return;
    if (replay_deferred) {
        try finalize_streaming_copy_for_replay_prefix(self);
    } else {
        try flush_streaming_copy(self, queue_sync_mode == .per_command);
    }
}

fn acquire_streaming_copy_buffer(self: anytype) !void {
    if (self.streaming_copy_buffer == null) {
        const reusable_index = self.streaming_copy_pending_count;
        if (reusable_index < self.streaming_copy_buffers.items.len) {
            self.streaming_copy_buffer = self.streaming_copy_buffers.items[reusable_index];
        } else {
            var command_buffer: c.VkCommandBuffer = null;
            var alloc_info = c.VkCommandBufferAllocateInfo{
                .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
                .pNext = null,
                .commandPool = self.command_pool,
                .level = c.VK_COMMAND_BUFFER_LEVEL_PRIMARY,
                .commandBufferCount = 1,
            };
            try c.check_vk(c.vkAllocateCommandBuffers(self.device, &alloc_info, @ptrCast(&command_buffer)));
            errdefer c.vkFreeCommandBuffers(self.device, self.command_pool, 1, @ptrCast(&command_buffer));
            try self.streaming_copy_buffers.append(self.allocator, command_buffer);
            self.streaming_copy_buffer = command_buffer;
        }
    }
    try c.check_vk(c.vkResetCommandBuffer(self.streaming_copy_buffer, 0));
}

fn detach_pending_streaming_copy_buffer(self: anytype) void {
    if (self.streaming_copy_buffer == null) return;
    self.streaming_copy_pending_count += 1;
    self.streaming_copy_buffer = null;
    self.streaming_copy_count = 0;
}

/// Record a buffer-to-buffer copy into the streaming command buffer.
pub fn streaming_copy_buffer_region(self: anytype, src: c.VkBuffer, src_offset: u64, dst: c.VkBuffer, dst_offset: u64, size: u64) !void {
    if (!self.streaming_copy_active) try begin_streaming_copy(self);
    var region = c.VkBufferCopy{
        .srcOffset = src_offset,
        .dstOffset = dst_offset,
        .size = size,
    };
    c.vkCmdCopyBuffer(self.streaming_copy_buffer, src, dst, 1, @ptrCast(&region));
    self.streaming_copy_count += 1;
}

pub fn record_replay_buffer_copy(
    self: anytype,
    src: anytype,
    src_offset: u64,
    dst: anytype,
    dst_offset: u64,
    size: u64,
) !void {
    if (size == 0) return;
    _ = try self.begin_prepared_dispatch_replay();

    // A copy-only submission must also order reads and writes from earlier
    // submissions. Mapped memory does not make an in-flight producer complete.
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_SHADER_WRITE_BIT | c.VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_TRANSFER_READ_BIT | c.VK_ACCESS_TRANSFER_WRITE_BIT,
    };
    c.vkCmdPipelineBarrier(self.replay_command_buffer, c.VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, c.VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, @ptrCast(&barrier), 0, null, 0, null);

    var region = c.VkBufferCopy{
        .srcOffset = src_offset,
        .dstOffset = dst_offset,
        .size = size,
    };
    c.vkCmdCopyBuffer(self.replay_command_buffer, src.buffer, dst.buffer, 1, @ptrCast(&region));
    self.has_pending_transfer_writes = true;

    if (dst.memory_kind != .device_local) {
        vk_compute_sync.make_transfer_writes_visible_for_host_read(self.replay_command_buffer);
    }
}

/// Record a whole-buffer copy into the streaming command buffer.
pub fn streaming_copy_buffer_to_buffer(self: anytype, src: c.VkBuffer, dst: c.VkBuffer, size: u64) !void {
    try streaming_copy_buffer_region(self, src, 0, dst, 0, size);
}

pub fn streaming_fill_buffer(self: anytype, dst: c.VkBuffer, dst_offset: u64, size: u64, data: u32) !void {
    if (size == 0) return;
    if (!self.streaming_copy_active) try begin_streaming_copy(self);
    c.vkCmdFillBuffer(self.streaming_copy_buffer, dst, dst_offset, size, data);
    self.streaming_copy_count += 1;
}

/// A recorded clear is ordered against preceding reads as well as writes.
pub fn record_replay_buffer_clear(self: anytype, dst: c.VkBuffer, offset: u64, size: u64) !void {
    if (size == 0) return;
    const command_buffer = try self.begin_prepared_dispatch_replay();
    var barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_SHADER_WRITE_BIT | c.VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_TRANSFER_WRITE_BIT,
    };
    c.vkCmdPipelineBarrier(command_buffer, c.VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, c.VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, @ptrCast(&barrier), 0, null, 0, null);
    c.vkCmdFillBuffer(command_buffer, dst, offset, size, 0);
    self.has_pending_transfer_writes = true;
    barrier.srcAccessMask = c.VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.dstAccessMask = c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT |
        c.VK_ACCESS_TRANSFER_READ_BIT | c.VK_ACCESS_TRANSFER_WRITE_BIT | c.VK_ACCESS_HOST_READ_BIT;
    c.vkCmdPipelineBarrier(command_buffer, c.VK_PIPELINE_STAGE_TRANSFER_BIT, c.VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | c.VK_PIPELINE_STAGE_HOST_BIT, 0, 1, @ptrCast(&barrier), 0, null, 0, null);
}

/// Submit a single copy region and wait for completion.
pub fn copy_buffer_region_and_wait(
    self: anytype,
    src: c.VkBuffer,
    src_offset: u64,
    dst: c.VkBuffer,
    dst_offset: u64,
    size: u64,
) !void {
    if (size == 0) return;
    if (self.hot_pending_upload != null or self.pending_uploads.items.len > 0 or self.has_deferred_submissions) {
        _ = try flush_queue(self);
    }
    try vk_device.ensure_submission_state(self);
    if (self.streaming_copy_active) {
        try flush_streaming_copy(self, true);
    }
    try streaming_copy_buffer_region(self, src, src_offset, dst, dst_offset, size);
    try flush_streaming_copy(self, true);
}

/// Finish recording and submit the streaming copy command buffer.
/// Uses a fence-pool fence for deferred tracking or the primary fence
/// for immediate wait, depending on `wait`.
pub fn flush_streaming_copy(self: anytype, wait: bool) !void {
    if (!self.streaming_copy_active) return;
    try c.check_vk(c.vkEndCommandBuffer(self.streaming_copy_buffer));
    self.streaming_copy_active = false;

    if (self.streaming_copy_count == 0) {
        self.streaming_copy_count = 0;
        return;
    }

    var submit_info = c.VkSubmitInfo{
        .sType = c.VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .pNext = null,
        .waitSemaphoreCount = 0,
        .pWaitSemaphores = null,
        .pWaitDstStageMask = null,
        .commandBufferCount = 1,
        .pCommandBuffers = @ptrCast(&self.streaming_copy_buffer),
        .signalSemaphoreCount = 0,
        .pSignalSemaphores = null,
    };

    if (self.has_timeline_semaphore and !wait) {
        // Timeline path: signal the semaphore on every submission.
        // For immediate-wait, follow with a CPU wait on the signaled value.
        var tsi = try vk_sync.TimelineSubmitHelper.prepare(&self.timeline_semaphore);
        tsi.patch();
        submit_info.pNext = @ptrCast(&tsi.timeline_info);
        submit_info.signalSemaphoreCount = 1;
        submit_info.pSignalSemaphores = @ptrCast(&tsi.semaphore);
        try tsi.submit(&self.timeline_semaphore, self.queue, &submit_info);
        if (wait) {
            try self.timeline_semaphore.wait(self.device, tsi.signal_value);
        } else {
            self.has_deferred_submissions = true;
        }
    } else if (wait) {
        try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
        try wait_for_fence_fast(self, self.fence);
    } else {
        const VK_NULL_FENCE = c.VK_NULL_U64;
        const deferred_fence = if (self.has_fence_pool)
            try self.fence_pool_state.acquire(self.device)
        else
            VK_NULL_FENCE;
        try vk_sync.submitWithFence(self.queue, &submit_info, deferred_fence, if (self.has_fence_pool) &self.fence_pool_state else null);
        self.has_deferred_submissions = true;
    }
    self.has_pending_transfer_writes = true;
    if (wait) {
        self.streaming_copy_count = 0;
        self.buffer_write_staging_offset = 0;
    } else {
        detach_pending_streaming_copy_buffer(self);
    }
}

pub fn finalize_streaming_copy_for_replay_prefix(self: anytype) !void {
    if (!self.streaming_copy_active) return;
    try c.check_vk(c.vkEndCommandBuffer(self.streaming_copy_buffer));
    self.streaming_copy_active = false;

    if (self.streaming_copy_count == 0) {
        self.streaming_copy_count = 0;
        return;
    }
    if (self.replay_prefix_copy_pending) return error.InvalidState;
    if (self.streaming_copy_buffer == null) return error.InvalidState;

    self.replay_prefix_copy_buffer = self.streaming_copy_buffer;
    self.replay_prefix_copy_pending = true;
    self.has_pending_transfer_writes = true;
    detach_pending_streaming_copy_buffer(self);
}

pub fn vk_release_pool(pool: *VkPool, allocator: std.mem.Allocator, device: c.VkDevice) void {
    var it = pool.valueIterator();
    while (it.next()) |list| {
        for (list.items) |entry| {
            if (entry.mapped != null) c.vkUnmapMemory(device, entry.memory);
            c.vkDestroyBuffer(device, entry.buffer, null);
            c.vkFreeMemory(device, entry.memory, null);
        }
        var m = list.*;
        m.deinit(allocator);
    }
    pool.deinit(allocator);
}
