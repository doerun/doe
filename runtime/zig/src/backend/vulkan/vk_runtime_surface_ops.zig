const std = @import("std");
const model_render_types = @import("../../contracts/model/model_render_types.zig");
const model_gpu_types = @import("../../contracts/model/model_texture_value_types.zig");
const model_surface_control_types = @import("../../contracts/model/model_surface_control_types.zig");
const c = @import("vk_constants.zig");
const vk_resources = @import("vk_resources.zig");
const vk_sync = @import("vk_sync.zig");
const vulkan_surface = @import("vulkan_surface.zig");

pub const SurfaceState = vulkan_surface.VulkanSurface;
pub const SurfaceConfigureCommand = model_surface_control_types.SurfaceConfigureCommand;
pub const WGPUTextureFormat = model_gpu_types.WGPUTextureFormat;

pub const Registry = struct {
    allocator: std.mem.Allocator,
    surfaces: *std.AutoHashMapUnmanaged(u64, SurfaceState),
    physical_device: c.VkPhysicalDevice,
    queue_family_index: u32,
};

pub const Submission = struct {
    owner: *anyopaque,
    flush: *const fn (*anyopaque) anyerror!void,
    ensure: *const fn (*anyopaque) anyerror!void,
    clear: *const fn (*anyopaque, model_render_types.RenderDrawCommand) anyerror!void,
    wait_for_destruction: *const fn (*anyopaque) void,
};

pub const Execution = struct {
    registry: Registry,
    instance: c.VkInstance,
    device: c.VkDevice,
    queue: c.VkQueue,
    retirement: *vk_sync.Retirement,
    has_surface_completion: bool,
    textures: *std.AutoHashMapUnmanaged(u64, vk_resources.TextureResource),
    primary_command_buffer: *c.VkCommandBuffer,
    fence: *c.VkFence,
    submission: Submission,
};

pub fn create_surface(self: Registry, handle: u64) !void {
    if (handle == 0) return error.InvalidArgument;
    const result = try self.surfaces.getOrPut(self.allocator, handle);
    if (result.found_existing) return error.InvalidState;
    result.value_ptr.* = .{};
}

pub fn get_surface_capabilities(self: Registry, handle: u64) !void {
    const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
    if (surface.vk_surface == 0) return error.SurfaceUnavailable;
    const caps = try vulkan_surface.query_surface_capabilities(
        self.physical_device,
        self.queue_family_index,
        surface.vk_surface,
    );
    surface.cached_capabilities = caps;
    surface.capabilities_queried = true;
}

pub fn preferred_canvas_format(self: Registry) model_gpu_types.WGPUTextureFormat {
    var it = self.surfaces.valueIterator();
    while (it.next()) |surface| {
        if (!surface.capabilities_queried or surface.cached_capabilities.format_count == 0) continue;
        return vulkan_surface.preferred_canvas_format_from_surface_formats(
            surface.cached_capabilities.formats[0..@as(usize, surface.cached_capabilities.format_count)],
        );
    }
    return model_gpu_types.WGPUTextureFormat_BGRA8Unorm;
}

pub fn configure_surface(self: Execution, cmd_arg: model_surface_control_types.SurfaceConfigureCommand) !void {
    try self.retirement.requireActive();
    if (!self.has_surface_completion) return error.UnsupportedFeature;
    if (cmd_arg.width == 0 or cmd_arg.height == 0) return error.InvalidArgument;
    const surface = self.registry.surfaces.getPtr(cmd_arg.handle) orelse return error.SurfaceUnavailable;
    if (surface.vk_surface == 0) return error.SurfaceUnavailable;
    try get_surface_capabilities(self.registry, cmd_arg.handle);
    const admitted = try vulkan_surface.admitConfiguration(surface.cached_capabilities, cmd_arg);
    try self.submission.flush(self.submission.owner);
    if (surface.swapchain != 0) {
        surface.completion.device_lost = surface.completion.device_lost or self.retirement.observed_device_loss;
        vulkan_surface.destroy_swapchain(self.device, surface);
    }
    surface.configured = false;
    surface.acquired = false;
    surface.width = cmd_arg.width;
    surface.height = cmd_arg.height;
    surface.requested_format = cmd_arg.format;
    surface.format = surface.requested_format;
    surface.usage = cmd_arg.usage;
    surface.alpha_mode = cmd_arg.alpha_mode;
    surface.present_mode = cmd_arg.present_mode;
    surface.tone_mapping_mode = if (cmd_arg.tone_mapping_mode == 0)
        model_surface_control_types.WGPUCanvasToneMappingMode_Standard
    else
        cmd_arg.tone_mapping_mode;
    surface.desired_maximum_frame_latency = if (cmd_arg.desired_maximum_frame_latency == 0)
        c.DEFAULT_SURFACE_MAX_FRAME_LATENCY
    else
        cmd_arg.desired_maximum_frame_latency;
    try vulkan_surface.create_swapchain(
        self.device,
        surface,
        self.registry.queue_family_index,
        admitted,
    );
    surface.configured = true;
}

pub fn acquire_surface(self: Execution, handle: u64) !void {
    const surface = self.registry.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
    try self.retirement.requireActive();
    if (!surface.configured) return error.SurfaceUnavailable;
    if (surface.swapchain == 0) return error.SurfaceUnavailable;
    _ = vulkan_surface.acquire_next_image(self.device, surface) catch |err| {
        if (err == error.DeviceLost) {
            self.retirement.failed(err);
            self.retirement.waitForDestruction(self.device);
        }
        return err;
    };
}

pub fn present_surface(self: Execution, handle: u64) !void {
    const surface = self.registry.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
    if (!surface.configured or !surface.acquired) return error.SurfaceUnavailable;
    if (surface.swapchain == 0) return error.SurfaceUnavailable;
    try self.retirement.requireActive();
    if (!surface.completion.present_ready) try prepare_present(self, surface);
    vulkan_surface.present_image(self.device, self.queue, surface) catch |err| {
        if (err == error.DeviceLost) {
            self.retirement.failed(err);
            self.retirement.waitForDestruction(self.device);
        }
        return err;
    };
}

// The final transition and semaphore signal cover every operation on this image,
// including copies. Individual draws do not own acquire or present synchronization.
fn prepare_present(self: Execution, surface: *SurfaceState) !void {
    try self.submission.flush(self.submission.owner);
    try self.submission.ensure(self.submission.owner);
    const image = surface.swapchain_images[surface.current_image_index];
    var target = self.textures.get(surface.acquired_texture_handle) orelse return error.InvalidState;
    if (target.image != image) return error.InvalidState;
    if (target.layout == c.VK_IMAGE_LAYOUT_UNDEFINED) {
        try self.submission.clear(self.submission.owner, .{
            .draw_count = 0,
            .target_handle = surface.acquired_texture_handle,
            .target_width = target.width,
            .target_height = target.height,
            .target_format = target.format,
            .clear_color = .{ 0, 0, 0, 0 },
        });
        target = self.textures.get(surface.acquired_texture_handle) orelse return error.InvalidState;
    }
    const begin = c.VkCommandBufferBeginInfo{ .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO, .pNext = null, .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT, .pInheritanceInfo = null };
    try c.check_vk(c.vkResetCommandBuffer(self.primary_command_buffer.*, 0));
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer.*, &begin));
    vk_resources.transition_texture_layout(self.primary_command_buffer.*, target, target.layout, c.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, c.VK_ACCESS_MEMORY_READ_BIT | c.VK_ACCESS_MEMORY_WRITE_BIT, 0, c.VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, c.VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer.*));
    const submit = c.VkSubmitInfo{
        .sType = c.VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .pNext = null,
        .waitSemaphoreCount = 0,
        .pWaitSemaphores = null,
        .pWaitDstStageMask = null,
        .commandBufferCount = 1,
        .pCommandBuffers = @ptrCast(self.primary_command_buffer),
        .signalSemaphoreCount = 1,
        .pSignalSemaphores = @ptrCast(&surface.completion.render_finished),
    };
    try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(self.fence)));
    const result = c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit), self.fence.*);
    c.check_vk(result) catch |err| {
        if (!vk_sync.submissionRejected(result)) {
            self.retirement.failed(err);
            self.retirement.waitForDestruction(self.device);
        }
        return err;
    };
    surface.completion.present_ready = true;
    c.check_vk(c.vkWaitForFences(self.device, 1, @ptrCast(self.fence), c.VK_TRUE, std.math.maxInt(u64))) catch |err| {
        self.retirement.failed(err);
        self.retirement.waitForDestruction(self.device);
        return err;
    };
    var it = self.textures.valueIterator();
    while (it.next()) |texture| {
        if (texture.image == image) texture.layout = c.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    }
}

pub fn unconfigure_surface(self: Execution, handle: u64) !void {
    self.submission.wait_for_destruction(self.submission.owner);
    const surface = self.registry.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
    if (surface.swapchain != 0) {
        surface.completion.device_lost = surface.completion.device_lost or self.retirement.observed_device_loss;
        vulkan_surface.destroy_swapchain(self.device, surface);
    }
    surface.configured = false;
    surface.acquired = false;
    surface.width = 0;
    surface.height = 0;
    surface.last_acquire_suboptimal = false;
    surface.last_present_suboptimal = false;
}

pub fn release_surface(self: Execution, handle: u64) !void {
    self.submission.wait_for_destruction(self.submission.owner);
    const removed = self.registry.surfaces.fetchRemove(handle) orelse return error.SurfaceUnavailable;
    var surface_copy = removed.value;
    surface_copy.completion.device_lost = surface_copy.completion.device_lost or self.retirement.observed_device_loss;
    if (surface_copy.vk_surface != 0 or surface_copy.swapchain != 0) {
        vulkan_surface.destroy_all(self.instance, self.device, &surface_copy);
    }
}

pub fn release_all_surfaces(self: Execution) void {
    var it = self.registry.surfaces.valueIterator();
    while (it.next()) |surface| {
        if (surface.vk_surface != 0 or surface.swapchain != 0) {
            surface.completion.device_lost = surface.completion.device_lost or self.retirement.observed_device_loss;
            vulkan_surface.destroy_all(self.instance, self.device, surface);
        }
    }
    self.registry.surfaces.deinit(self.registry.allocator);
}

test "surface capability queries require a native surface" {
    var surfaces: std.AutoHashMapUnmanaged(u64, SurfaceState) = .{};
    defer surfaces.deinit(std.testing.allocator);
    const registry = Registry{ .allocator = std.testing.allocator, .surfaces = &surfaces, .physical_device = null, .queue_family_index = 0 };
    try std.testing.expectError(error.SurfaceUnavailable, get_surface_capabilities(registry, 1));
    try create_surface(registry, 1);
    try std.testing.expectError(error.SurfaceUnavailable, get_surface_capabilities(registry, 1));
    try std.testing.expect(!surfaces.get(1).?.capabilities_queried);
    try std.testing.expectError(error.InvalidState, create_surface(registry, 1));
}
