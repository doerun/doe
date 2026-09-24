// Fence pool, deferred-submission tracking, and timeline semaphore support
// for the Vulkan backend.
//
// Replaces single-fence + vkQueueWaitIdle with per-submission fence tracking:
//   - FencePool manages a fixed-size ring of VkFence handles
//   - Deferred submissions signal a pool fence instead of VK_NULL_HANDLE
//   - drain waits on all in-flight fences (no vkQueueWaitIdle)
//   - Timeline semaphore detection exposes VK_KHR_timeline_semaphore when available

const std = @import("std");
const c = @import("vk_constants.zig");
const errors = @import("vulkan_errors.zig");
const common_errors = @import("../../contracts/execution.zig");

const VK_NULL_U64 = c.VK_NULL_U64;

/// Maximum fences managed by the pool. Sized for typical pipelined depth
/// (upload batch + dispatch + render) without over-allocating driver objects.
pub const FENCE_POOL_CAPACITY: usize = 128;

/// Timeout for per-fence waits (nanoseconds). Matches vk_upload.WAIT_TIMEOUT_NS.
pub const FENCE_WAIT_TIMEOUT_NS: u64 = std.math.maxInt(u64);
pub const IMMEDIATE_FENCE_POLL_SPINS: usize = 2048;

fn submissionRejected(result: c.VkResult) bool {
    return result == errors.VK_ERROR_OUT_OF_HOST_MEMORY or result == errors.VK_ERROR_OUT_OF_DEVICE_MEMORY;
}

/// Allocation rejection leaves Vulkan submission state unchanged. Device loss
/// or an unknown result cannot authorize forgetting potentially submitted work.
pub fn submitWithFence(queue: c.VkQueue, info: *const c.VkSubmitInfo, fence: c.VkFence, pool: ?*FencePool) common_errors.BackendNativeError!void {
    if (pool) |owner| {
        const index = owner.last_in_flight_index;
        if (index >= owner.count or !owner.in_flight[index] or owner.fences[index] != fence) return error.InvalidState;
    }
    const result = c.vkQueueSubmit(queue, 1, @ptrCast(info), fence);
    if (pool) |owner| return owner.completeSubmit(result);
    return c.check_vk(result);
}

pub fn wait_for_fence_fast(device: c.VkDevice, fence: c.VkFence) common_errors.BackendNativeError!void {
    var spin: usize = 0;
    while (spin < IMMEDIATE_FENCE_POLL_SPINS) : (spin += 1) {
        const status = c.vkGetFenceStatus(device, fence);
        if (status == c.VK_SUCCESS) return;
        if (status != c.VK_NOT_READY) return c.check_vk(status);
        std.atomic.spinLoopHint();
    }
    try c.check_vk(c.vkWaitForFences(device, 1, @ptrCast(&fence), c.VK_TRUE, FENCE_WAIT_TIMEOUT_NS));
}

pub const FencePool = struct {
    fences: [FENCE_POOL_CAPACITY]c.VkFence = [_]c.VkFence{VK_NULL_U64} ** FENCE_POOL_CAPACITY,
    in_flight: [FENCE_POOL_CAPACITY]bool = [_]bool{false} ** FENCE_POOL_CAPACITY,
    count: u32 = 0,
    next_index: u32 = 0,
    in_flight_count: u32 = 0,
    last_in_flight_index: u32 = 0,

    /// Initialize the ring. Individual VkFence handles are created on first use.
    pub fn init(device: c.VkDevice) common_errors.BackendNativeError!FencePool {
        _ = device;
        var pool = FencePool{};
        pool.count = FENCE_POOL_CAPACITY;
        return pool;
    }

    /// Acquire the next available fence for a queue submission. If the fence
    /// at the current ring position is still in-flight, wait for it first
    /// so it can be reused. Returns the fence handle to pass to vkQueueSubmit.
    pub fn acquire(self: *FencePool, device: c.VkDevice) common_errors.BackendNativeError!c.VkFence {
        const idx = self.next_index;
        if (self.fences[idx] == VK_NULL_U64) {
            var fence_info = c.VkFenceCreateInfo{
                .sType = c.VK_STRUCTURE_TYPE_FENCE_CREATE_INFO,
                .pNext = null,
                .flags = 0,
            };
            try c.check_vk(c.vkCreateFence(device, &fence_info, null, &self.fences[idx]));
        }
        const fence = self.fences[idx];

        // If this slot was in-flight from a previous submission, wait + reset
        if (self.in_flight[idx]) {
            try wait_for_fence_fast(device, fence);
            self.in_flight[idx] = false;
            self.in_flight_count -|= 1;
        }

        try c.check_vk(c.vkResetFences(device, 1, @ptrCast(&fence)));
        self.in_flight[idx] = true;
        self.in_flight_count +|= 1;
        self.last_in_flight_index = idx;
        self.next_index = (idx + 1) % self.count;
        return fence;
    }

    fn completeSubmit(self: *FencePool, result: c.VkResult) common_errors.BackendNativeError!void {
        if (submissionRejected(result)) {
            const index = self.last_in_flight_index;
            std.debug.assert(index < self.count and self.in_flight[index]);
            self.in_flight[index] = false;
            self.in_flight_count -= 1;
            self.next_index = index;
        }
        try c.check_vk(result);
    }

    /// Wait for all in-flight fences and mark them reusable. Used to drain all
    /// deferred/pipelined submissions without vkQueueWaitIdle.
    pub fn drain(self: *FencePool, device: c.VkDevice) common_errors.BackendNativeError!void {
        if (self.in_flight_count == 0) return;
        if (self.in_flight_count == 1) {
            var idx = self.last_in_flight_index;
            if (idx >= self.count or !self.in_flight[idx]) {
                idx = 0;
                while (idx < self.count and !self.in_flight[idx]) : (idx += 1) {}
                if (idx >= self.count) {
                    self.in_flight_count = 0;
                    return;
                }
            }
            if (self.fences[idx] == VK_NULL_U64) return error.InvalidState;
            try wait_for_fence_fast(device, self.fences[idx]);
            self.in_flight[idx] = false;
            self.in_flight_count = 0;
            return;
        }

        var handles: [FENCE_POOL_CAPACITY]c.VkFence = undefined;
        var handle_count: u32 = 0;

        var i: u32 = 0;
        while (i < self.count) : (i += 1) {
            if (!self.in_flight[i]) continue;
            if (self.fences[i] == VK_NULL_U64) return error.InvalidState;
            handles[handle_count] = self.fences[i];
            handle_count += 1;
        }

        if (handle_count == 0) return;
        try c.check_vk(c.vkWaitForFences(
            device,
            handle_count,
            @ptrCast(&handles),
            c.VK_TRUE,
            FENCE_WAIT_TIMEOUT_NS,
        ));

        i = 0;
        while (i < self.count) : (i += 1) {
            if (self.in_flight[i]) self.in_flight[i] = false;
        }
        self.in_flight_count = 0;
    }

    /// True when at least one fence is in-flight (deferred work outstanding).
    pub fn has_in_flight(self: *const FencePool) bool {
        return self.in_flight_count != 0;
    }

    /// Destroy all pool fences. Call before device destruction.
    pub fn deinit(self: *FencePool, device: c.VkDevice) void {
        var i: u32 = 0;
        while (i < self.count) : (i += 1) {
            if (self.fences[i] != VK_NULL_U64) {
                // Best-effort wait before destroy to avoid validation errors
                if (self.in_flight[i]) {
                    wait_for_fence_fast(device, self.fences[i]) catch {};
                    self.in_flight[i] = false;
                }
                c.vkDestroyFence(device, self.fences[i], null);
                self.fences[i] = VK_NULL_U64;
            }
        }
        self.count = 0;
        self.next_index = 0;
        self.in_flight_count = 0;
        self.last_in_flight_index = 0;
    }
};

// --- Timeline semaphore support (VK_KHR_timeline_semaphore / Vulkan 1.2) ---

/// VK_STRUCTURE_TYPE values for timeline semaphore structs
const VK_STRUCTURE_TYPE_TIMELINE_SEMAPHORE_FEATURES: i32 = 1000207000;
const VK_STRUCTURE_TYPE_SEMAPHORE_TYPE_CREATE_INFO: i32 = 1000207002;
const VK_STRUCTURE_TYPE_SEMAPHORE_WAIT_INFO: i32 = 1000207004;
const VK_STRUCTURE_TYPE_SEMAPHORE_SIGNAL_INFO: i32 = 1000207005;
pub const VK_STRUCTURE_TYPE_TIMELINE_SEMAPHORE_SUBMIT_INFO: i32 = 1000207003;

/// VK_SEMAPHORE_TYPE_TIMELINE = 1
pub const VK_SEMAPHORE_TYPE_TIMELINE: u32 = 1;

/// VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2
const VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2: i32 = 1000059000;

/// VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO
const VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO: i32 = 9;

/// Feature struct chained via pNext during device creation to detect support.
pub const VkPhysicalDeviceTimelineSemaphoreFeatures = extern struct {
    sType: c.VkStructureType = VK_STRUCTURE_TYPE_TIMELINE_SEMAPHORE_FEATURES,
    pNext: ?*anyopaque = null,
    timelineSemaphore: c.VkBool32 = c.VK_FALSE,
};

/// Chained into VkSemaphoreCreateInfo to create a timeline semaphore.
pub const VkSemaphoreTypeCreateInfo = extern struct {
    sType: c.VkStructureType = VK_STRUCTURE_TYPE_SEMAPHORE_TYPE_CREATE_INFO,
    pNext: ?*const anyopaque = null,
    semaphoreType: u32 = VK_SEMAPHORE_TYPE_TIMELINE,
    initialValue: u64 = 0,
};

/// Submit info extension for timeline semaphore wait/signal values.
pub const VkTimelineSemaphoreSubmitInfo = extern struct {
    sType: c.VkStructureType = VK_STRUCTURE_TYPE_TIMELINE_SEMAPHORE_SUBMIT_INFO,
    pNext: ?*const anyopaque = null,
    waitSemaphoreValueCount: u32 = 0,
    pWaitSemaphoreValues: ?[*]const u64 = null,
    signalSemaphoreValueCount: u32 = 0,
    pSignalSemaphoreValues: ?[*]const u64 = null,
};

/// Wait info for vkWaitSemaphores.
pub const VkSemaphoreWaitInfo = extern struct {
    sType: c.VkStructureType = VK_STRUCTURE_TYPE_SEMAPHORE_WAIT_INFO,
    pNext: ?*const anyopaque = null,
    flags: u32 = 0,
    semaphoreCount: u32 = 0,
    pSemaphores: ?[*]const c.VkSemaphore = null,
    pValues: ?[*]const u64 = null,
};

/// VkSemaphoreCreateInfo (sType=9). Declared locally; used only for timeline
/// semaphore creation with a pNext chain to VkSemaphoreTypeCreateInfo.
const VkSemaphoreCreateInfo = extern struct {
    sType: c.VkStructureType,
    pNext: ?*const anyopaque,
    flags: u32,
};

// Vulkan entry points for semaphore and timeline operations.
// These link against the Vulkan loader; timeline functions require
// Vulkan 1.2+ or VK_KHR_timeline_semaphore.
extern fn vkCreateSemaphore(device: c.VkDevice, pCreateInfo: *const VkSemaphoreCreateInfo, pAllocator: ?*const c.VkAllocationCallbacks, pSemaphore: *c.VkSemaphore) callconv(.c) c.VkResult;
extern fn vkDestroySemaphore(device: c.VkDevice, semaphore: c.VkSemaphore, pAllocator: ?*const c.VkAllocationCallbacks) callconv(.c) void;
extern fn vkWaitSemaphores(device: c.VkDevice, pWaitInfo: *const VkSemaphoreWaitInfo, timeout: u64) callconv(.c) c.VkResult;
extern fn vkGetSemaphoreCounterValue(device: c.VkDevice, semaphore: c.VkSemaphore, pValue: *u64) callconv(.c) c.VkResult;
extern fn vkGetPhysicalDeviceFeatures2(physicalDevice: c.VkPhysicalDevice, pFeatures: *anyopaque) callconv(.c) void;

/// Manages a single timeline semaphore for monotonic GPU->CPU signaling.
/// Each queue submission increments the timeline value; the CPU can wait
/// on any past value without needing per-submission fence objects.
pub const TimelineSemaphore = struct {
    semaphore: c.VkSemaphore = VK_NULL_U64,
    current_value: u64 = 0,
    available: bool = false,

    /// Attempt to create a timeline semaphore. Returns a struct with
    /// available=false if the device does not support the extension
    /// (caller should fall back to fence pool).
    pub fn init(device: c.VkDevice, timeline_supported: bool) common_errors.BackendNativeError!TimelineSemaphore {
        if (!timeline_supported) return .{};

        var type_info = VkSemaphoreTypeCreateInfo{};
        var sem_info = VkSemaphoreCreateInfo{
            .sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO,
            .pNext = @ptrCast(&type_info),
            .flags = 0,
        };

        var sem: c.VkSemaphore = VK_NULL_U64;
        try c.check_vk(vkCreateSemaphore(device, &sem_info, null, &sem));

        return .{
            .semaphore = sem,
            .current_value = 0,
            .available = true,
        };
    }

    /// Wait on the CPU until the timeline reaches `value`.
    pub fn wait(self: *const TimelineSemaphore, device: c.VkDevice, value: u64) common_errors.BackendNativeError!void {
        if (!self.available) return error.UnsupportedFeature;
        var wait_info = VkSemaphoreWaitInfo{
            .semaphoreCount = 1,
            .pSemaphores = @ptrCast(&self.semaphore),
            .pValues = @ptrCast(&value),
        };
        try c.check_vk(vkWaitSemaphores(device, &wait_info, FENCE_WAIT_TIMEOUT_NS));
    }

    /// Wait for all submissions up to the current value.
    pub fn drain(self: *const TimelineSemaphore, device: c.VkDevice) common_errors.BackendNativeError!void {
        if (!self.available or self.current_value == 0) return;
        try self.wait(device, self.current_value);
    }

    /// Query the current GPU-side counter value (non-blocking).
    pub fn query(self: *const TimelineSemaphore, device: c.VkDevice) common_errors.BackendNativeError!u64 {
        if (!self.available) return error.UnsupportedFeature;
        var value: u64 = 0;
        try c.check_vk(vkGetSemaphoreCounterValue(device, self.semaphore, &value));
        return value;
    }

    pub fn deinit(self: *TimelineSemaphore, device: c.VkDevice) void {
        if (self.semaphore != VK_NULL_U64) {
            if (self.available and self.current_value > 0) {
                self.drain(device) catch {};
            }
            vkDestroySemaphore(device, self.semaphore, null);
            self.semaphore = VK_NULL_U64;
        }
        self.available = false;
        self.current_value = 0;
    }
};

/// Pre-built chain of VkTimelineSemaphoreSubmitInfo + semaphore/value arrays
/// ready to attach to a VkSubmitInfo. Callers set `submit.pNext`,
/// `submit.signalSemaphoreCount`, and `submit.pSignalSemaphores` from the
/// returned fields before calling vkQueueSubmit.
///
/// Usage:
///   var tsi = try TimelineSubmitHelper.prepare(&timeline_sem);
///   if (tsi.ready) {
///       submit.pNext = @ptrCast(&tsi.timeline_info);
///       submit.signalSemaphoreCount = 1;
///       submit.pSignalSemaphores = @ptrCast(&tsi.semaphore);
///   }
pub const TimelineSubmitHelper = struct {
    timeline_info: VkTimelineSemaphoreSubmitInfo = .{},
    semaphore: c.VkSemaphore = VK_NULL_U64,
    signal_value: u64 = 0,
    ready: bool = false,

    /// Prepare a timeline signal for the next queue submission.
    /// Reserves a value without publishing an unsubmitted drain target.
    /// Returns a helper with ready=false if the timeline is unavailable.
    pub fn prepare(ts: *const TimelineSemaphore) common_errors.BackendNativeError!TimelineSubmitHelper {
        if (!ts.available) return .{};
        const value = std.math.add(u64, ts.current_value, 1) catch return error.InvalidState;
        return .{
            .timeline_info = .{
                .waitSemaphoreValueCount = 0,
                .pWaitSemaphoreValues = null,
                .signalSemaphoreValueCount = 1,
                .pSignalSemaphoreValues = null, // patched below
            },
            .semaphore = ts.semaphore,
            .signal_value = value,
            .ready = true,
        };
    }

    /// Patch the signal value pointer to point at our own signal_value field.
    /// Must be called after prepare() and before passing to vkQueueSubmit,
    /// since the struct address is stable only after the caller has placed it.
    pub fn patch(self: *TimelineSubmitHelper) void {
        if (!self.ready) return;
        self.timeline_info.pSignalSemaphoreValues = @ptrCast(&self.signal_value);
    }

    pub fn submit(self: *const TimelineSubmitHelper, ts: *TimelineSemaphore, queue: c.VkQueue, info: *const c.VkSubmitInfo) common_errors.BackendNativeError!void {
        if (!self.ready or !ts.available or self.semaphore != ts.semaphore or
            self.signal_value == 0 or self.signal_value - 1 != ts.current_value) return error.InvalidState;
        return self.completeSubmit(ts, c.vkQueueSubmit(queue, 1, @ptrCast(info), VK_NULL_U64));
    }

    fn completeSubmit(self: *const TimelineSubmitHelper, ts: *TimelineSemaphore, result: c.VkResult) common_errors.BackendNativeError!void {
        if (!submissionRejected(result)) ts.current_value = self.signal_value;
        try c.check_vk(result);
    }
};

test "rejected fence submissions preserve earlier work and permit retry" {
    for ([_]c.VkResult{ errors.VK_ERROR_OUT_OF_HOST_MEMORY, errors.VK_ERROR_OUT_OF_DEVICE_MEMORY }) |result| {
        var pool = try FencePool.init(null);
        pool.fences[0] = 11;
        pool.fences[1] = 12;
        pool.in_flight[0] = true;
        pool.in_flight[1] = true;
        pool.in_flight_count = 2;
        pool.last_in_flight_index = 1;
        pool.next_index = 2;
        try std.testing.expectError(error.InvalidState, pool.completeSubmit(result));
        try std.testing.expect(pool.in_flight[0]);
        try std.testing.expect(!pool.in_flight[1]);
        try std.testing.expectEqual(@as(u32, 1), pool.in_flight_count);
        try std.testing.expectEqual(@as(u32, 1), pool.next_index);
        pool.in_flight[1] = true;
        pool.in_flight_count += 1;
        try pool.completeSubmit(c.VK_SUCCESS);
        try std.testing.expectEqual(@as(u32, 2), pool.in_flight_count);
    }
}

test "rejected sole fence submission does not enter a native wait" {
    var pool = try FencePool.init(null);
    pool.fences[0] = 11;
    pool.in_flight[0] = true;
    pool.in_flight_count = 1;
    try std.testing.expectError(error.InvalidState, pool.completeSubmit(errors.VK_ERROR_OUT_OF_HOST_MEMORY));
    try pool.drain(null);
    try std.testing.expect(!pool.has_in_flight());
}

test "timeline submission reserves then publishes only potentially submitted values" {
    var timeline = TimelineSemaphore{ .semaphore = 11, .available = true, .current_value = 7 };
    const pending = try TimelineSubmitHelper.prepare(&timeline);
    try std.testing.expectEqual(@as(u64, 7), timeline.current_value);
    for ([_]c.VkResult{ errors.VK_ERROR_OUT_OF_HOST_MEMORY, errors.VK_ERROR_OUT_OF_DEVICE_MEMORY }) |result| {
        try std.testing.expectError(error.InvalidState, pending.completeSubmit(&timeline, result));
        try std.testing.expectEqual(@as(u64, 7), timeline.current_value);
    }
    const retry = try TimelineSubmitHelper.prepare(&timeline);
    try std.testing.expectEqual(pending.signal_value, retry.signal_value);
    try retry.completeSubmit(&timeline, c.VK_SUCCESS);
    try std.testing.expectEqual(@as(u64, 8), timeline.current_value);
    timeline.current_value = std.math.maxInt(u64);
    try std.testing.expectError(error.InvalidState, TimelineSubmitHelper.prepare(&timeline));
}

test "device loss and unknown submission errors retain synchronization obligations" {
    for ([_]c.VkResult{ errors.VK_ERROR_DEVICE_LOST, errors.VK_ERROR_UNKNOWN }) |result| {
        var pool = try FencePool.init(null);
        pool.in_flight[0] = true;
        pool.in_flight_count = 1;
        try std.testing.expectError(errors.map_vk_result(result), pool.completeSubmit(result));
        try std.testing.expect(pool.has_in_flight());
        var timeline = TimelineSemaphore{ .semaphore = 11, .available = true };
        const pending = try TimelineSubmitHelper.prepare(&timeline);
        try std.testing.expectError(errors.map_vk_result(result), pending.completeSubmit(&timeline, result));
        try std.testing.expectEqual(@as(u64, 1), timeline.current_value);
    }
}

/// Detect timeline semaphore support by querying
/// VkPhysicalDeviceTimelineSemaphoreFeatures via the Vulkan 1.1+
/// vkGetPhysicalDeviceFeatures2 entry point.
pub fn detect_timeline_semaphore_support(physical_device: c.VkPhysicalDevice) bool {
    var timeline_features = VkPhysicalDeviceTimelineSemaphoreFeatures{};
    // VkPhysicalDeviceFeatures2 with pNext chain to timeline features
    const Features2 = extern struct {
        sType: c.VkStructureType,
        pNext: ?*anyopaque,
        // VkPhysicalDeviceFeatures is a large struct (56 bools).
        // We only care about the pNext chain; zero-init the features.
        features: [224]u8,
    };
    var features2 = Features2{
        .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,
        .pNext = @ptrCast(&timeline_features),
        .features = std.mem.zeroes([224]u8),
    };
    vkGetPhysicalDeviceFeatures2(physical_device, @ptrCast(&features2));
    return timeline_features.timelineSemaphore == c.VK_TRUE;
}
