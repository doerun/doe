// Acquisition and presentation completion belong to the swapchain, not a draw.
const std = @import("std");
const c = @import("vk_constants.zig");
const errors = @import("vulkan_errors.zig");
const Error = @import("../../contracts/execution.zig").BackendNativeError;

const STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO: u32 = 9;
const STRUCTURE_TYPE_SWAPCHAIN_MAINTENANCE_FEATURES: u32 = 1000275000;
const STRUCTURE_TYPE_PRESENT_FENCE_INFO: u32 = 1000275001;
const SemaphoreInfo = extern struct { sType: u32 = STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO, pNext: ?*const anyopaque = null, flags: u32 = 0 };
extern fn vkCreateSemaphore(device: c.VkDevice, info: *const SemaphoreInfo, allocator: ?*const c.VkAllocationCallbacks, semaphore: *c.VkSemaphore) callconv(.c) c.VkResult;
extern fn vkDestroySemaphore(device: c.VkDevice, semaphore: c.VkSemaphore, allocator: ?*const c.VkAllocationCallbacks) callconv(.c) void;

pub const extension: [*:0]const u8 = "VK_EXT_swapchain_maintenance1";
pub const Features = extern struct {
    sType: u32 = STRUCTURE_TYPE_SWAPCHAIN_MAINTENANCE_FEATURES,
    pNext: ?*anyopaque = null,
    swapchainMaintenance1: u32 = 0,
};
pub const PresentFenceInfo = extern struct {
    sType: u32 = STRUCTURE_TYPE_PRESENT_FENCE_INFO,
    pNext: ?*const anyopaque = null,
    swapchainCount: u32 = 1,
    pFences: *const c.VkFence,
};

pub const Completion = struct {
    acquire_fence: c.VkFence = 0,
    present_fence: c.VkFence = 0,
    render_finished: c.VkSemaphore = 0,
    acquire_pending: bool = false,
    present_pending: bool = false,
    present_ready: bool = false,
    device_lost: bool = false,

    pub fn init(device: c.VkDevice) Error!Completion {
        var result = Completion{};
        errdefer result.deinit(device);
        const fence_info = c.VkFenceCreateInfo{ .sType = c.VK_STRUCTURE_TYPE_FENCE_CREATE_INFO, .pNext = null, .flags = 0 };
        try c.check_vk(c.vkCreateFence(device, &fence_info, null, &result.acquire_fence));
        try c.check_vk(c.vkCreateFence(device, &fence_info, null, &result.present_fence));
        const sem_info = SemaphoreInfo{};
        try c.check_vk(vkCreateSemaphore(device, &sem_info, null, &result.render_finished));
        return result;
    }

    pub fn waitAcquire(self: *Completion, device: c.VkDevice) Error!void {
        try self.wait(device, self.acquire_fence, &self.acquire_pending);
    }

    pub fn waitPresent(self: *Completion, device: c.VkDevice) Error!void {
        try self.wait(device, self.present_fence, &self.present_pending);
    }

    fn wait(self: *Completion, device: c.VkDevice, fence: c.VkFence, pending: *bool) Error!void {
        if (self.device_lost) return error.DeviceLost;
        if (!pending.*) return;
        const result = c.vkWaitForFences(device, 1, @ptrCast(&fence), c.VK_TRUE, std.math.maxInt(u64));
        try self.acceptWaitResult(pending, result);
    }

    fn acceptWaitResult(self: *Completion, pending: *bool, result: c.VkResult) Error!void {
        if (result == errors.VK_ERROR_DEVICE_LOST) self.device_lost = true;
        if (result == c.VK_TIMEOUT) return error.SyncUnavailable;
        try c.check_vk(result);
        pending.* = false;
    }

    pub fn deinit(self: *Completion, device: c.VkDevice) void {
        // Device idle is not proof that the presentation engine released its
        // references. Unknown fence completion keeps this owner alive.
        while (!self.device_lost and (self.acquire_pending or self.present_pending)) {
            self.waitAcquire(device) catch {};
            self.waitPresent(device) catch {};
            if (!self.device_lost and (self.acquire_pending or self.present_pending))
                std.Thread.sleep(@import("build_options").vulkan_unresolved_completion_retry_ns);
        }
        if (self.render_finished != 0) vkDestroySemaphore(device, self.render_finished, null);
        if (self.present_fence != 0) c.vkDestroyFence(device, self.present_fence, null);
        if (self.acquire_fence != 0) c.vkDestroyFence(device, self.acquire_fence, null);
        self.* = .{};
    }
};

test "surface completion retains pending ownership on failed waits and distinguishes device loss" {
    var completion = Completion{ .acquire_pending = true, .present_pending = true };
    try std.testing.expectError(error.InvalidState, completion.acceptWaitResult(&completion.acquire_pending, c.VK_NOT_READY));
    try std.testing.expect(completion.acquire_pending and completion.present_pending);
    try std.testing.expectError(error.SyncUnavailable, completion.acceptWaitResult(&completion.acquire_pending, c.VK_TIMEOUT));
    try completion.acceptWaitResult(&completion.acquire_pending, c.VK_SUCCESS);
    try std.testing.expect(!completion.acquire_pending and completion.present_pending);
    try std.testing.expectError(error.DeviceLost, completion.acceptWaitResult(&completion.present_pending, errors.VK_ERROR_DEVICE_LOST));
    try std.testing.expect(completion.device_lost and completion.present_pending);
}
