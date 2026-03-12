// Buffer and texture resource management for the Vulkan backend.
//
// Handles compute buffer lifecycle, texture creation/destroy/layout
// transitions, and format helpers.

const std = @import("std");
const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const vk_upload = @import("vk_upload.zig");
const model = @import("../../model.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");

const VkBuffer = c.VkBuffer;
const VkDeviceMemory = c.VkDeviceMemory;
const VkImage = c.VkImage;
const VkImageView = c.VkImageView;
const VK_NULL_U64 = c.VK_NULL_U64;

pub const DEFAULT_RUNTIME_TEXTURE_USAGE: model.WGPUFlags =
    model.WGPUTextureUsage_TextureBinding |
    model.WGPUTextureUsage_StorageBinding |
    model.WGPUTextureUsage_CopyDst;
pub const REQUIRED_TEXTURE_UPLOAD_USAGE: model.WGPUFlags = model.WGPUTextureUsage_CopyDst;

pub const ComputeBuffer = struct {
    buffer: VkBuffer,
    memory: VkDeviceMemory,
    mapped: ?*anyopaque,
    size: u64,
};

pub const TextureResource = struct {
    image: VkImage,
    memory: VkDeviceMemory,
    view: VkImageView,
    width: u32,
    height: u32,
    mip_levels: u32,
    format: model.WGPUTextureFormat,
    usage: model.WGPUFlags,
    layout: u32,
};

const TextureTransitionSource = struct {
    src_access_mask: u32,
    src_stage: u32,
};

const Runtime = @import("native_runtime.zig").NativeVulkanRuntime;

pub fn ensure_compute_buffer(
    self: *Runtime,
    handle: u64,
    required_size: u64,
    initialize_buffers_on_create: bool,
) !ComputeBuffer {
    if (handle == 0 or required_size == 0) return error.InvalidArgument;
    if (self.compute_buffers.getPtr(handle)) |existing| {
        if (existing.size >= required_size) return existing.*;
        if (self.has_deferred_submissions) _ = try vk_upload.flush_queue(self);
        release_compute_buffer(self, existing.*);
        existing.* = try create_compute_buffer(self, required_size, initialize_buffers_on_create);
        return existing.*;
    }

    const compute_buffer = try create_compute_buffer(self, required_size, initialize_buffers_on_create);
    try self.compute_buffers.put(self.allocator, handle, compute_buffer);
    return self.compute_buffers.get(handle).?;
}

pub fn required_compute_buffer_size(
    self: *const Runtime,
    binding: model.KernelBinding,
) !u64 {
    if (binding.resource_kind != .buffer) return error.UnsupportedFeature;
    if (binding.buffer_size == model.WGPUWholeSize) {
        if (self.compute_buffers.get(binding.resource_handle)) |existing| {
            return existing.size;
        }
        return error.InvalidArgument;
    }
    return std.math.add(u64, binding.buffer_offset, binding.buffer_size) catch error.InvalidArgument;
}

pub fn create_compute_buffer(
    self: *Runtime,
    bytes: u64,
    initialize_buffers_on_create: bool,
) !ComputeBuffer {
    var buffer: VkBuffer = VK_NULL_U64;
    var memory: VkDeviceMemory = VK_NULL_U64;
    var mapped: ?*anyopaque = null;

    var buffer_info = c.VkBufferCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .size = bytes,
        .usage = c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
            c.VK_BUFFER_USAGE_TRANSFER_DST_BIT |
            c.VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT |
            c.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,
        .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE,
        .queueFamilyIndexCount = 0,
        .pQueueFamilyIndices = null,
    };
    try c.check_vk(c.vkCreateBuffer(self.device, &buffer_info, null, &buffer));
    errdefer if (buffer != VK_NULL_U64) c.vkDestroyBuffer(self.device, buffer, null);

    var requirements = std.mem.zeroes(c.VkMemoryRequirements);
    c.vkGetBufferMemoryRequirements(self.device, buffer, &requirements);
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
    try c.check_vk(c.vkAllocateMemory(self.device, &alloc_info, null, &memory));
    errdefer if (memory != VK_NULL_U64) c.vkFreeMemory(self.device, memory, null);

    try c.check_vk(c.vkBindBufferMemory(self.device, buffer, memory, 0));
    try c.check_vk(c.vkMapMemory(self.device, memory, 0, bytes, 0, &mapped));
    errdefer if (mapped != null) c.vkUnmapMemory(self.device, memory);

    if (initialize_buffers_on_create and mapped != null) {
        @memset(@as([*]u8, @ptrCast(mapped.?))[0..@intCast(bytes)], 0);
    }

    return .{
        .buffer = buffer,
        .memory = memory,
        .mapped = mapped,
        .size = bytes,
    };
}

pub fn release_compute_buffer(self: *Runtime, compute_buffer: ComputeBuffer) void {
    if (compute_buffer.mapped != null) {
        c.vkUnmapMemory(self.device, compute_buffer.memory);
    }
    c.vkDestroyBuffer(self.device, compute_buffer.buffer, null);
    c.vkFreeMemory(self.device, compute_buffer.memory, null);
}

pub fn release_compute_buffers(self: *Runtime) void {
    var iterator = self.compute_buffers.valueIterator();
    while (iterator.next()) |buffer| {
        release_compute_buffer(self, buffer.*);
    }
    self.compute_buffers.deinit(self.allocator);
}

pub fn create_host_visible_buffer(self: *Runtime, bytes: u64, usage: u32) !ComputeBuffer {
    var buffer: VkBuffer = VK_NULL_U64;
    var memory: VkDeviceMemory = VK_NULL_U64;
    var mapped: ?*anyopaque = null;

    var buffer_info = c.VkBufferCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .size = bytes,
        .usage = usage,
        .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE,
        .queueFamilyIndexCount = 0,
        .pQueueFamilyIndices = null,
    };
    try c.check_vk(c.vkCreateBuffer(self.device, &buffer_info, null, &buffer));
    errdefer if (buffer != VK_NULL_U64) c.vkDestroyBuffer(self.device, buffer, null);

    var requirements = std.mem.zeroes(c.VkMemoryRequirements);
    c.vkGetBufferMemoryRequirements(self.device, buffer, &requirements);
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
    try c.check_vk(c.vkAllocateMemory(self.device, &alloc_info, null, &memory));
    errdefer if (memory != VK_NULL_U64) c.vkFreeMemory(self.device, memory, null);

    try c.check_vk(c.vkBindBufferMemory(self.device, buffer, memory, 0));
    try c.check_vk(c.vkMapMemory(self.device, memory, 0, bytes, 0, &mapped));
    errdefer if (mapped != null) c.vkUnmapMemory(self.device, memory);

    return .{
        .buffer = buffer,
        .memory = memory,
        .mapped = mapped,
        .size = bytes,
    };
}

pub fn destroy_host_visible_buffer(self: *Runtime, buffer: ComputeBuffer) void {
    release_compute_buffer(self, buffer);
}

pub fn create_destroy_lifecycle_buffer(self: *Runtime, bytes: u64) !void {
    var buffer: VkBuffer = VK_NULL_U64;
    var memory: VkDeviceMemory = VK_NULL_U64;
    var buffer_info = c.VkBufferCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .size = bytes,
        .usage = c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT | c.VK_BUFFER_USAGE_TRANSFER_DST_BIT,
        .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE,
        .queueFamilyIndexCount = 0,
        .pQueueFamilyIndices = null,
    };
    try c.check_vk(c.vkCreateBuffer(self.device, &buffer_info, null, &buffer));
    defer if (buffer != VK_NULL_U64) c.vkDestroyBuffer(self.device, buffer, null);

    var requirements = std.mem.zeroes(c.VkMemoryRequirements);
    c.vkGetBufferMemoryRequirements(self.device, buffer, &requirements);
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
    try c.check_vk(c.vkAllocateMemory(self.device, &alloc_info, null, &memory));
    defer if (memory != VK_NULL_U64) c.vkFreeMemory(self.device, memory, null);
    try c.check_vk(c.vkBindBufferMemory(self.device, buffer, memory, 0));
}

// --- Texture resource management ---

pub fn ensure_texture_resource(self: *Runtime, texture: model.CopyTextureResource) !*TextureResource {
    if (texture.handle == 0) return error.InvalidArgument;
    if (texture.width == 0 or texture.height == 0) return error.InvalidArgument;
    const mip_levels: u32 = if (texture.mip_level > 0) texture.mip_level + 1 else 1;
    if (self.textures.getPtr(texture.handle)) |existing| {
        if (existing.width == texture.width and
            existing.height == texture.height and
            existing.mip_levels == mip_levels and
            existing.format == texture.format and
            existing.usage == texture.usage)
        {
            return existing;
        }
        if (self.has_deferred_submissions) _ = try vk_upload.flush_queue(self);
        release_texture_resource(self, existing.*);
        existing.* = try create_texture_resource(self, texture, mip_levels);
        return existing;
    }

    try self.textures.put(self.allocator, texture.handle, try create_texture_resource(self, texture, mip_levels));
    return self.textures.getPtr(texture.handle).?;
}

pub fn ensure_texture_shader_layout(self: *Runtime, texture: *TextureResource) !void {
    if (texture.layout == c.VK_IMAGE_LAYOUT_GENERAL) return;
    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
        _ = try vk_upload.flush_queue(self);
    }

    try c.check_vk(c.vkResetCommandPool(self.device, self.command_pool, 0));
    var begin_info = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
    const source = texture_transition_source(texture.layout);
    transition_texture_layout(
        self.primary_command_buffer,
        texture.*,
        texture.layout,
        c.VK_IMAGE_LAYOUT_GENERAL,
        source.src_access_mask,
        c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT,
        source.src_stage,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
    );
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));

    var submit_info = c.VkSubmitInfo{
        .sType = c.VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .pNext = null,
        .waitSemaphoreCount = 0,
        .pWaitSemaphores = null,
        .pWaitDstStageMask = null,
        .commandBufferCount = 1,
        .pCommandBuffers = @ptrCast(&self.primary_command_buffer),
        .signalSemaphoreCount = 0,
        .pSignalSemaphores = null,
    };
    try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
    try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
    try c.check_vk(c.vkWaitForFences(self.device, 1, @ptrCast(&self.fence), c.VK_TRUE, vk_upload.WAIT_TIMEOUT_NS));
    texture.layout = c.VK_IMAGE_LAYOUT_GENERAL;
}

pub fn create_texture_resource(
    self: *Runtime,
    texture: model.CopyTextureResource,
    mip_levels: u32,
) !TextureResource {
    var image: VkImage = VK_NULL_U64;
    var memory: VkDeviceMemory = VK_NULL_U64;
    var view: VkImageView = VK_NULL_U64;
    const usage = effective_texture_usage(texture.usage);

    var image_info = c.VkImageCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .imageType = c.VK_IMAGE_TYPE_2D,
        .format = try texture_format_to_vk(texture.format),
        .extent = .{ .width = texture.width, .height = texture.height, .depth = 1 },
        .mipLevels = mip_levels,
        .arrayLayers = 1,
        .samples = c.VK_SAMPLE_COUNT_1_BIT,
        .tiling = c.VK_IMAGE_TILING_OPTIMAL,
        .usage = image_usage_for_texture(usage),
        .sharingMode = c.VK_SHARING_MODE_EXCLUSIVE,
        .queueFamilyIndexCount = 0,
        .pQueueFamilyIndices = null,
        .initialLayout = c.VK_IMAGE_LAYOUT_UNDEFINED,
    };
    try c.check_vk(c.vkCreateImage(self.device, &image_info, null, &image));
    errdefer if (image != VK_NULL_U64) c.vkDestroyImage(self.device, image, null);

    var requirements = std.mem.zeroes(c.VkMemoryRequirements);
    c.vkGetImageMemoryRequirements(self.device, image, &requirements);
    const memory_index = try vk_device.find_memory_type_index(
        self,
        requirements.memoryTypeBits,
        c.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,
    );
    var alloc_info = c.VkMemoryAllocateInfo{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .pNext = null,
        .allocationSize = requirements.size,
        .memoryTypeIndex = memory_index,
    };
    try c.check_vk(c.vkAllocateMemory(self.device, &alloc_info, null, &memory));
    errdefer if (memory != VK_NULL_U64) c.vkFreeMemory(self.device, memory, null);

    try c.check_vk(c.vkBindImageMemory(self.device, image, memory, 0));

    var view_info = c.VkImageViewCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .image = image,
        .viewType = c.VK_IMAGE_VIEW_TYPE_2D,
        .format = try texture_format_to_vk(texture.format),
        .components = .{
            .r = c.VK_COMPONENT_SWIZZLE_IDENTITY,
            .g = c.VK_COMPONENT_SWIZZLE_IDENTITY,
            .b = c.VK_COMPONENT_SWIZZLE_IDENTITY,
            .a = c.VK_COMPONENT_SWIZZLE_IDENTITY,
        },
        .subresourceRange = .{
            .aspectMask = c.VK_IMAGE_ASPECT_COLOR_BIT,
            .baseMipLevel = 0,
            .levelCount = mip_levels,
            .baseArrayLayer = 0,
            .layerCount = 1,
        },
    };
    try c.check_vk(c.vkCreateImageView(self.device, &view_info, null, &view));
    errdefer if (view != VK_NULL_U64) c.vkDestroyImageView(self.device, view, null);

    return .{
        .image = image,
        .memory = memory,
        .view = view,
        .width = texture.width,
        .height = texture.height,
        .mip_levels = mip_levels,
        .format = texture.format,
        .usage = usage,
        .layout = c.VK_IMAGE_LAYOUT_UNDEFINED,
    };
}

pub fn release_texture_resource(self: *Runtime, texture: TextureResource) void {
    if (texture.view != VK_NULL_U64) c.vkDestroyImageView(self.device, texture.view, null);
    if (texture.image != VK_NULL_U64) c.vkDestroyImage(self.device, texture.image, null);
    if (texture.memory != VK_NULL_U64) c.vkFreeMemory(self.device, texture.memory, null);
}

pub fn release_textures(self: *Runtime) void {
    var iterator = self.textures.valueIterator();
    while (iterator.next()) |texture| {
        release_texture_resource(self, texture.*);
    }
    self.textures.deinit(self.allocator);
}

pub fn transition_texture_layout(
    command_buffer: c.VkCommandBuffer,
    texture: TextureResource,
    old_layout: u32,
    new_layout: u32,
    src_access_mask: u32,
    dst_access_mask: u32,
    src_stage: u32,
    dst_stage: u32,
) void {
    var image_barrier = c.VkImageMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = src_access_mask,
        .dstAccessMask = dst_access_mask,
        .oldLayout = old_layout,
        .newLayout = new_layout,
        .srcQueueFamilyIndex = std.math.maxInt(u32),
        .dstQueueFamilyIndex = std.math.maxInt(u32),
        .image = texture.image,
        .subresourceRange = .{
            .aspectMask = c.VK_IMAGE_ASPECT_COLOR_BIT,
            .baseMipLevel = 0,
            .levelCount = texture.mip_levels,
            .baseArrayLayer = 0,
            .layerCount = 1,
        },
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        src_stage,
        dst_stage,
        0,
        0,
        null,
        0,
        null,
        1,
        @ptrCast(&image_barrier),
    );
}

// --- Pure texture helpers ---

pub fn texture_transition_source(layout: u32) TextureTransitionSource {
    return switch (layout) {
        c.VK_IMAGE_LAYOUT_UNDEFINED => .{
            .src_access_mask = 0,
            .src_stage = c.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
        },
        c.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL => .{
            .src_access_mask = c.VK_ACCESS_TRANSFER_WRITE_BIT,
            .src_stage = c.VK_PIPELINE_STAGE_TRANSFER_BIT,
        },
        c.VK_IMAGE_LAYOUT_GENERAL => .{
            .src_access_mask = c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT,
            .src_stage = c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        },
        else => .{
            .src_access_mask = 0,
            .src_stage = c.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
        },
    };
}

pub fn effective_texture_usage(requested: model.WGPUFlags) model.WGPUFlags {
    if (requested == 0) return DEFAULT_RUNTIME_TEXTURE_USAGE;
    return requested | REQUIRED_TEXTURE_UPLOAD_USAGE;
}

pub fn texture_format_to_vk(format: model.WGPUTextureFormat) !u32 {
    return switch (format) {
        model.WGPUTextureFormat_RGBA8Unorm => c.VK_FORMAT_R8G8B8A8_UNORM,
        else => error.UnsupportedFeature,
    };
}

pub fn image_usage_for_texture(usage: model.WGPUFlags) u32 {
    var out: u32 = c.VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    if ((usage & model.WGPUTextureUsage_TextureBinding) != 0) out |= c.VK_IMAGE_USAGE_SAMPLED_BIT;
    if ((usage & model.WGPUTextureUsage_StorageBinding) != 0) out |= c.VK_IMAGE_USAGE_STORAGE_BIT;
    if ((usage & model.WGPUTextureUsage_CopySrc) != 0) out |= c.VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    if ((usage & model.WGPUTextureUsage_CopyDst) != 0) out |= c.VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    return out;
}

pub fn bytes_per_pixel_for_texture_format(format: model.WGPUTextureFormat) u32 {
    return switch (format) {
        model.WGPUTextureFormat_RGBA8Unorm => 4,
        else => 4,
    };
}
