// Upload/staging buffer pool management for the Vulkan backend.
//
// Handles staged-copy and direct-mapped upload paths, buffer pool
// reuse with persistent mapping, and flush/recording lifecycle.

const std = @import("std");
const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const backend_policy = @import("../backend_policy.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const common_errors = @import("../common/errors.zig");
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
    // Persistently-mapped pointer for the staging (src) buffer.
    // Retained across pool cycles to avoid per-upload vkMapMemory/vkUnmapMemory.
    src_mapped: ?*anyopaque = null,
};

pub const VkPoolEntry = struct {
    buffer: VkBuffer,
    memory: VkDeviceMemory,
    mapped: ?*anyopaque = null,
};

pub const UploadPathKind = enum {
    fast_mapped,
    direct_mapped,
    staged_copy,
};

pub const VkPool = std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry));

const Runtime = @import("native_runtime.zig").NativeVulkanRuntime;

pub fn flush_queue(self: *Runtime) !u64 {
    if (!self.has_device) return 0;
    const start_ns = common_timing.now_ns();
    if (self.pending_uploads.items.len > 0) {
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
        // on RADV, which dominates tiny-upload latency.
        try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit), self.fence));
        try c.check_vk(c.vkWaitForFences(self.device, 1, @ptrCast(&self.fence), c.VK_TRUE, WAIT_TIMEOUT_NS));
        self.has_deferred_submissions = false;
    } else if (self.has_deferred_submissions) {
        // No pending uploads but earlier deferred work exists; drain fully.
        try c.check_vk(c.vkQueueWaitIdle(self.queue));
        self.has_deferred_submissions = false;
    }
    self.upload_recording_active = false;
    try c.check_vk(c.vkResetCommandBuffer(self.primary_command_buffer, 0));
    self.command_buffer_reset_clean = true;
    release_pending_uploads(self);
    const end_ns = common_timing.now_ns();
    return common_timing.ns_delta(end_ns, start_ns);
}

pub fn record_upload_copy(self: *Runtime, bytes: u64, dst_usage: u32) !PendingUpload {
    try ensure_upload_recording(self);

    var src_buffer: VkBuffer = VK_NULL_U64;
    var dst_buffer: VkBuffer = VK_NULL_U64;
    var src_memory: VkDeviceMemory = VK_NULL_U64;
    var dst_memory: VkDeviceMemory = VK_NULL_U64;
    var src_mapped: ?*anyopaque = null;
    var src_fresh = true;

    // Try pool first for src (host-visible staging buffer).
    if (hot_pool_pop(&self.hot_src_pool_entry, &self.hot_src_pool_size, bytes)) |entry| {
        src_buffer = entry.buffer;
        src_memory = entry.memory;
        src_mapped = entry.mapped;
        src_fresh = false;
    } else if (vk_pool_pop(&self.src_pool, bytes)) |entry| {
        src_buffer = entry.buffer;
        src_memory = entry.memory;
        src_mapped = entry.mapped;
        src_fresh = false;
    } else {
        var src_info = c.VkBufferCreateInfo{ .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .pNext = null, .flags = 0, .size = bytes, .usage = c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT, .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE, .queueFamilyIndexCount = 0, .pQueueFamilyIndices = null };
        try c.check_vk(c.vkCreateBuffer(self.device, &src_info, null, &src_buffer));
        errdefer c.vkDestroyBuffer(self.device, src_buffer, null);

        var src_req = std.mem.zeroes(c.VkMemoryRequirements);
        c.vkGetBufferMemoryRequirements(self.device, src_buffer, &src_req);
        const src_mem_index = try vk_device.find_memory_type_index(self, src_req.memoryTypeBits, c.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | c.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        var src_alloc_info = c.VkMemoryAllocateInfo{ .sType = c.VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .pNext = null, .allocationSize = src_req.size, .memoryTypeIndex = src_mem_index };
        try c.check_vk(c.vkAllocateMemory(self.device, &src_alloc_info, null, &src_memory));
        errdefer c.vkFreeMemory(self.device, src_memory, null);
        try c.check_vk(c.vkBindBufferMemory(self.device, src_buffer, src_memory, 0));
    }

    // Try pool for dst (device-local storage buffer).
    if (hot_pool_pop(&self.hot_dst_pool_entry, &self.hot_dst_pool_size, bytes)) |entry| {
        dst_buffer = entry.buffer;
        dst_memory = entry.memory;
    } else if (vk_pool_pop(&self.dst_pool, bytes)) |entry| {
        dst_buffer = entry.buffer;
        dst_memory = entry.memory;
    } else {
        const permissive_dst_usage = c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT | c.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
        const effective_usage = if (dst_usage == 0) permissive_dst_usage else dst_usage;
        var dst_info = c.VkBufferCreateInfo{ .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .pNext = null, .flags = 0, .size = bytes, .usage = effective_usage, .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE, .queueFamilyIndexCount = 0, .pQueueFamilyIndices = null };
        try c.check_vk(c.vkCreateBuffer(self.device, &dst_info, null, &dst_buffer));
        errdefer c.vkDestroyBuffer(self.device, dst_buffer, null);

        var dst_req = std.mem.zeroes(c.VkMemoryRequirements);
        c.vkGetBufferMemoryRequirements(self.device, dst_buffer, &dst_req);
        const dst_mem_index = try vk_device.find_memory_type_index(self, dst_req.memoryTypeBits, c.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        var dst_alloc_info = c.VkMemoryAllocateInfo{ .sType = c.VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .pNext = null, .allocationSize = dst_req.size, .memoryTypeIndex = dst_mem_index };
        try c.check_vk(c.vkAllocateMemory(self.device, &dst_alloc_info, null, &dst_memory));
        errdefer c.vkFreeMemory(self.device, dst_memory, null);
        try c.check_vk(c.vkBindBufferMemory(self.device, dst_buffer, dst_memory, 0));
    }
    // Zero-fill fresh src allocations; keep the mapping persistent to
    // avoid per-upload vkMapMemory/vkUnmapMemory on pool reuse cycles.
    if (src_fresh) {
        var mapped: ?*anyopaque = null;
        try c.check_vk(c.vkMapMemory(self.device, src_memory, 0, bytes, 0, &mapped));
        if (mapped) |raw| {
            const fill_len = @min(@as(usize, @intCast(bytes)), MAX_UPLOAD_ZERO_FILL_BYTES);
            @memset(@as([*]u8, @ptrCast(raw))[0..fill_len], 0);
        }
        src_mapped = mapped;
    }

    var region = c.VkBufferCopy{ .srcOffset = 0, .dstOffset = 0, .size = bytes };
    c.vkCmdCopyBuffer(self.primary_command_buffer, src_buffer, dst_buffer, 1, @ptrCast(&region));

    return .{
        .src_buffer = src_buffer,
        .src_memory = src_memory,
        .dst_buffer = dst_buffer,
        .dst_memory = dst_memory,
        .byte_count = bytes,
        .src_mapped = src_mapped,
    };
}

pub fn try_direct_upload(self: *Runtime, bytes: u64, dst_usage: u32) !bool {
    record_direct_upload(self, bytes, dst_usage) catch |err| switch (err) {
        error.UnsupportedFeature => return false,
        else => return err,
    };
    return true;
}

fn record_direct_upload(self: *Runtime, bytes: u64, dst_usage: u32) !void {
    var dst_buffer: VkBuffer = VK_NULL_U64;
    var dst_memory: VkDeviceMemory = VK_NULL_U64;
    var dst_mapped: ?*anyopaque = null;
    var dst_fresh = false;

    if (vk_pool_pop(&self.direct_upload_pool, bytes)) |entry| {
        dst_buffer = entry.buffer;
        dst_memory = entry.memory;
        dst_mapped = entry.mapped;
    } else {
        const effective_usage = if (dst_usage == 0)
            c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT
        else
            dst_usage;
        var dst_info = c.VkBufferCreateInfo{
            .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .size = bytes,
            .usage = effective_usage,
            .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE,
            .queueFamilyIndexCount = 0,
            .pQueueFamilyIndices = null,
        };
        try c.check_vk(c.vkCreateBuffer(self.device, &dst_info, null, &dst_buffer));
        errdefer c.vkDestroyBuffer(self.device, dst_buffer, null);

        var dst_req = std.mem.zeroes(c.VkMemoryRequirements);
        c.vkGetBufferMemoryRequirements(self.device, dst_buffer, &dst_req);
        const dst_mem_index = try vk_device.find_memory_type_index(
            self,
            dst_req.memoryTypeBits,
            c.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | c.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        );
        var dst_alloc_info = c.VkMemoryAllocateInfo{
            .sType = c.VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .pNext = null,
            .allocationSize = dst_req.size,
            .memoryTypeIndex = dst_mem_index,
        };
        try c.check_vk(c.vkAllocateMemory(self.device, &dst_alloc_info, null, &dst_memory));
        errdefer c.vkFreeMemory(self.device, dst_memory, null);
        try c.check_vk(c.vkBindBufferMemory(self.device, dst_buffer, dst_memory, 0));
        try c.check_vk(c.vkMapMemory(self.device, dst_memory, 0, bytes, 0, &dst_mapped));
        dst_fresh = true;
    }

    errdefer {
        if (dst_buffer != VK_NULL_U64 and dst_memory != VK_NULL_U64) {
            vk_pool_push_or_destroy(
                &self.direct_upload_pool,
                self.allocator,
                self.device,
                bytes,
                .{ .buffer = dst_buffer, .memory = dst_memory, .mapped = dst_mapped },
            );
        } else {
            if (dst_buffer != VK_NULL_U64) c.vkDestroyBuffer(self.device, dst_buffer, null);
            if (dst_memory != VK_NULL_U64) c.vkFreeMemory(self.device, dst_memory, null);
        }
    }

    if (dst_fresh or bytes < DIRECT_UPLOAD_REUSE_SKIP_ZERO_FILL_MIN_BYTES) {
        const fill_len: usize = @intCast(bytes);
        if (dst_mapped) |raw| {
            @memset(@as([*]u8, @ptrCast(raw))[0..fill_len], 0);
        }
    }

    vk_pool_push_or_destroy(
        &self.direct_upload_pool,
        self.allocator,
        self.device,
        bytes,
        .{ .buffer = dst_buffer, .memory = dst_memory, .mapped = dst_mapped },
    );
}

pub fn ensure_upload_recording(self: *Runtime) !void {
    if (self.upload_recording_active) return;
    // Skip reset when flush_queue already left the buffer in reset state.
    if (!self.has_deferred_submissions and !self.command_buffer_reset_clean) {
        try c.check_vk(c.vkResetCommandBuffer(self.primary_command_buffer, 0));
    }
    self.command_buffer_reset_clean = false;
    var begin = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin));
    self.upload_recording_active = true;
}

pub fn finish_pending_upload_recording(self: *Runtime) !void {
    if (!self.upload_recording_active) return;
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    self.upload_recording_active = false;
}

pub fn ensure_fast_upload_buffer(self: *Runtime, bytes: u64) !void {
    if (self.fast_upload_capacity >= bytes and self.fast_upload_mapped != null) return;
    release_fast_upload_buffer(self);

    var buffer_info = c.VkBufferCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .size = bytes,
        .usage = c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
        .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE,
        .queueFamilyIndexCount = 0,
        .pQueueFamilyIndices = null,
    };
    try c.check_vk(c.vkCreateBuffer(self.device, &buffer_info, null, &self.fast_upload_buffer));
    errdefer release_fast_upload_buffer(self);

    var requirements = std.mem.zeroes(c.VkMemoryRequirements);
    c.vkGetBufferMemoryRequirements(self.device, self.fast_upload_buffer, &requirements);
    const memory_index = try vk_device.find_memory_type_index(
        self,
        requirements.memoryTypeBits,
        c.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | c.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
    );
    var alloc_info = c.VkMemoryAllocateInfo{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .pNext = null,
        .allocationSize = requirements.size,
        .memoryTypeIndex = memory_index,
    };
    try c.check_vk(c.vkAllocateMemory(self.device, &alloc_info, null, &self.fast_upload_memory));
    try c.check_vk(c.vkBindBufferMemory(self.device, self.fast_upload_buffer, self.fast_upload_memory, 0));
    try c.check_vk(c.vkMapMemory(self.device, self.fast_upload_memory, 0, bytes, 0, &self.fast_upload_mapped));
    self.fast_upload_capacity = bytes;
}

pub fn release_fast_upload_buffer(self: *Runtime) void {
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

pub fn release_pending_uploads(self: *Runtime) void {
    for (self.pending_uploads.items) |item| {
        release_upload(self, item);
    }
    self.pending_uploads.clearRetainingCapacity();
}

pub fn release_upload(self: *Runtime, item: PendingUpload) void {
    // Carry src_mapped through the pool so staging buffers stay
    // persistently mapped, eliminating per-upload map/unmap overhead.
    if (item.src_buffer != VK_NULL_U64 and item.src_memory != VK_NULL_U64) {
        const src_entry = VkPoolEntry{ .buffer = item.src_buffer, .memory = item.src_memory, .mapped = item.src_mapped };
        if (!hot_pool_store(&self.hot_src_pool_entry, &self.hot_src_pool_size, item.byte_count, src_entry)) {
            vk_pool_push_or_destroy(&self.src_pool, self.allocator, self.device, item.byte_count, src_entry);
        }
    } else {
        if (item.src_mapped != null) c.vkUnmapMemory(self.device, item.src_memory);
        if (item.src_buffer != VK_NULL_U64) c.vkDestroyBuffer(self.device, item.src_buffer, null);
        if (item.src_memory != VK_NULL_U64) c.vkFreeMemory(self.device, item.src_memory, null);
    }
    if (item.dst_buffer != VK_NULL_U64 and item.dst_memory != VK_NULL_U64) {
        if (!hot_pool_store(&self.hot_dst_pool_entry, &self.hot_dst_pool_size, item.byte_count, .{ .buffer = item.dst_buffer, .memory = item.dst_memory, .mapped = null })) {
            vk_pool_push_or_destroy(&self.dst_pool, self.allocator, self.device, item.byte_count, .{ .buffer = item.dst_buffer, .memory = item.dst_memory, .mapped = null });
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
    if (upload_path_policy == .staged_copy_only) return .staged_copy;
    if (mode == .copy_dst and bytes <= FAST_UPLOAD_BUFFER_MAX_BYTES) return .fast_mapped;
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

pub fn vk_pool_pop(pool: *VkPool, size: u64) ?VkPoolEntry {
    if (pool.getPtr(size)) |list| {
        if (list.items.len > 0) return list.pop();
    }
    return null;
}

pub fn hot_pool_pop(entry: *?VkPoolEntry, size_slot: *u64, size: u64) ?VkPoolEntry {
    if (size <= HOT_UPLOAD_POOL_CACHE_MAX_BYTES and entry.* != null and size_slot.* == size) {
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
