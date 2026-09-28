const std = @import("std");
const model_gpu_types = @import("../../contracts/model/model_texture_value_types.zig");
const model_surface_control_types = @import("../../contracts/model/model_surface_control_types.zig");
const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const vk_resources = @import("vk_resources.zig");
const vk_sync = @import("vk_sync.zig");
const vulkan_surface = @import("vulkan_surface.zig");

pub const SurfaceState = vulkan_surface.VulkanSurface;
pub const SurfaceConfigureCommand = model_surface_control_types.SurfaceConfigureCommand;
pub const WGPUTextureFormat = model_gpu_types.WGPUTextureFormat;

pub fn create_surface(self: anytype, handle: u64) !void {
    if (handle == 0) return error.InvalidArgument;
    const result = try self.surfaces.getOrPut(self.allocator, handle);
    if (result.found_existing) return error.InvalidState;
    result.value_ptr.* = .{};
}

pub fn get_surface_capabilities(self: anytype, handle: u64) !void {
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

pub fn preferred_canvas_format(self: anytype) model_gpu_types.WGPUTextureFormat {
    var it = self.surfaces.valueIterator();
    while (it.next()) |surface| {
        if (!surface.capabilities_queried or surface.cached_capabilities.format_count == 0) continue;
        return vulkan_surface.preferred_canvas_format_from_surface_formats(
            surface.cached_capabilities.formats[0..@as(usize, surface.cached_capabilities.format_count)],
        );
    }
    return model_gpu_types.WGPUTextureFormat_BGRA8Unorm;
}

pub fn configure_surface(self: anytype, cmd_arg: model_surface_control_types.SurfaceConfigureCommand) !void {
    try self.retirement.requireActive();
    if (!self.has_surface_completion) return error.UnsupportedFeature;
    if (cmd_arg.width == 0 or cmd_arg.height == 0) return error.InvalidArgument;
    const surface = self.surfaces.getPtr(cmd_arg.handle) orelse return error.SurfaceUnavailable;
    if (surface.vk_surface == 0) return error.SurfaceUnavailable;
    _ = try self.flush_queue();
    if (surface.swapchain != 0) {
        surface.completion.device_lost = surface.completion.device_lost or self.retirement.observed_device_loss;
        vulkan_surface.destroy_swapchain(self.device, surface);
    }
    surface.configured = false;
    surface.acquired = false;
    surface.width = cmd_arg.width;
    surface.height = cmd_arg.height;
    surface.requested_format = if (cmd_arg.format == 0) preferred_canvas_format(self) else cmd_arg.format;
    surface.format = surface.requested_format;
    surface.usage = if (cmd_arg.usage == 0) model_gpu_types.WGPUTextureUsage_RenderAttachment else cmd_arg.usage;
    surface.alpha_mode = if (cmd_arg.alpha_mode == 0) c.VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR else cmd_arg.alpha_mode;
    surface.present_mode = if (cmd_arg.present_mode == 0) c.VK_PRESENT_MODE_FIFO_KHR else cmd_arg.present_mode;
    surface.tone_mapping_mode = if (cmd_arg.tone_mapping_mode == 0)
        model_surface_control_types.WGPUCanvasToneMappingMode_Standard
    else
        cmd_arg.tone_mapping_mode;
    surface.desired_maximum_frame_latency = if (cmd_arg.desired_maximum_frame_latency == 0)
        c.DEFAULT_SURFACE_MAX_FRAME_LATENCY
    else
        cmd_arg.desired_maximum_frame_latency;
    try get_surface_capabilities(self, cmd_arg.handle);
    try vulkan_surface.create_swapchain(
        self.device,
        self.physical_device,
        surface,
        self.queue_family_index,
    );
    surface.configured = true;
}

pub fn acquire_surface(self: anytype, handle: u64) !void {
    const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
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

pub fn present_surface(self: anytype, handle: u64) !void {
    const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
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
fn prepare_present(self: anytype, surface: *SurfaceState) !void {
    _ = try self.flush_queue();
    try vk_device.ensure_submission_state(self);
    const image = surface.swapchain_images[surface.current_image_index];
    var target = self.textures.get(surface.acquired_texture_handle) orelse return error.InvalidState;
    if (target.image != image) return error.InvalidState;
    if (target.layout == c.VK_IMAGE_LAYOUT_UNDEFINED) {
        _ = try self.run_render_clear(.{
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
    try c.check_vk(c.vkResetCommandBuffer(self.primary_command_buffer, 0));
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin));
    vk_resources.transition_texture_layout(self.primary_command_buffer, target, target.layout, c.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, c.VK_ACCESS_MEMORY_READ_BIT | c.VK_ACCESS_MEMORY_WRITE_BIT, 0, c.VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, c.VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    const submit = c.VkSubmitInfo{
        .sType = c.VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .pNext = null,
        .waitSemaphoreCount = 0,
        .pWaitSemaphores = null,
        .pWaitDstStageMask = null,
        .commandBufferCount = 1,
        .pCommandBuffers = @ptrCast(&self.primary_command_buffer),
        .signalSemaphoreCount = 1,
        .pSignalSemaphores = @ptrCast(&surface.completion.render_finished),
    };
    try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
    const result = c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit), self.fence);
    c.check_vk(result) catch |err| {
        if (!vk_sync.submissionRejected(result)) {
            self.retirement.failed(err);
            self.retirement.waitForDestruction(self.device);
        }
        return err;
    };
    surface.completion.present_ready = true;
    c.check_vk(c.vkWaitForFences(self.device, 1, @ptrCast(&self.fence), c.VK_TRUE, std.math.maxInt(u64))) catch |err| {
        self.retirement.failed(err);
        self.retirement.waitForDestruction(self.device);
        return err;
    };
    vk_resources.mark_texture_image_layout(self, image, c.VK_IMAGE_LAYOUT_PRESENT_SRC_KHR);
}

pub fn unconfigure_surface(self: anytype, handle: u64) !void {
    self.waitForDestruction();
    const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
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

pub fn release_surface(self: anytype, handle: u64) !void {
    self.waitForDestruction();
    const removed = self.surfaces.fetchRemove(handle) orelse return error.SurfaceUnavailable;
    var surface_copy = removed.value;
    surface_copy.completion.device_lost = surface_copy.completion.device_lost or self.retirement.observed_device_loss;
    if (surface_copy.vk_surface != 0 or surface_copy.swapchain != 0) {
        vulkan_surface.destroy_all(self.instance, self.device, &surface_copy);
    }
}

pub fn release_all_surfaces(self: anytype) void {
    var it = self.surfaces.valueIterator();
    while (it.next()) |surface| {
        if (surface.vk_surface != 0 or surface.swapchain != 0) {
            surface.completion.device_lost = surface.completion.device_lost or self.retirement.observed_device_loss;
            vulkan_surface.destroy_all(self.instance, self.device, surface);
        }
    }
    self.surfaces.deinit(self.allocator);
}

test "surface capability queries require a native surface" {
    const Fixture = struct {
        allocator: std.mem.Allocator = std.testing.allocator,
        surfaces: std.AutoHashMapUnmanaged(u64, SurfaceState) = .{},
        physical_device: c.VkPhysicalDevice = null,
        queue_family_index: u32 = 0,
    };
    var fixture = Fixture{};
    defer fixture.surfaces.deinit(fixture.allocator);
    try std.testing.expectError(error.SurfaceUnavailable, get_surface_capabilities(&fixture, 1));
    try create_surface(&fixture, 1);
    try std.testing.expectError(error.SurfaceUnavailable, get_surface_capabilities(&fixture, 1));
    try std.testing.expect(!fixture.surfaces.get(1).?.capabilities_queried);
    try std.testing.expectError(error.InvalidState, create_surface(&fixture, 1));
}
