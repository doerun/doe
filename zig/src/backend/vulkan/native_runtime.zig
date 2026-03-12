// NativeVulkanRuntime: top-level struct and public API for the Doe Vulkan backend.
//
// Sub-modules handle cohesive feature groups:
//   vk_constants  — Vulkan API types, constants, extern functions, error mapping
//   vk_device     — instance/adapter/device/queue bootstrap
//   vk_upload     — upload staging, pool management, flush lifecycle
//   vk_pipeline   — compute pipeline, shader, descriptor set management
//   vk_resources  — buffer/texture resource lifecycle and format helpers

const std = @import("std");
const model = @import("../../model.zig");
const backend_policy = @import("../backend_policy.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const vulkan_surface = @import("vulkan_surface.zig");

const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const vk_upload = @import("vk_upload.zig");
const vk_pipeline = @import("vk_pipeline.zig");
const vk_resources = @import("vk_resources.zig");

const VK_NULL_U64 = c.VK_NULL_U64;

// Re-export public helpers used by mod.zig
pub const upload_uses_fast_path = vk_upload.upload_uses_fast_path;
pub const upload_uses_direct_path = vk_upload.upload_uses_direct_path;

pub const DispatchMetrics = struct {
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    gpu_timestamp_ns: u64 = 0,
    gpu_timestamp_attempted: bool = false,
    gpu_timestamp_valid: bool = false,
};

pub const NativeVulkanRuntime = struct {
    allocator: std.mem.Allocator,
    kernel_root: ?[]const u8,

    instance: c.VkInstance = null,
    physical_device: c.VkPhysicalDevice = null,
    device: c.VkDevice = null,
    queue: c.VkQueue = null,

    adapter_ordinal_value: ?u32 = null,
    queue_family_index: u32 = 0,
    queue_family_index_value_cache: ?u32 = null,
    present_capable_value: ?bool = null,
    timestamp_query_supported_value: bool = false,
    command_pool: c.VkCommandPool = VK_NULL_U64,
    primary_command_buffer: c.VkCommandBuffer = null,
    fence: c.VkFence = VK_NULL_U64,

    shader_module: c.VkShaderModule = VK_NULL_U64,
    pipeline_layout: c.VkPipelineLayout = VK_NULL_U64,
    pipeline: c.VkPipeline = VK_NULL_U64,
    descriptor_pool: c.VkDescriptorPool = VK_NULL_U64,
    descriptor_set_layouts: [c.MAX_DESCRIPTOR_SETS]c.VkDescriptorSetLayout = [_]c.VkDescriptorSetLayout{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS,
    descriptor_sets: [c.MAX_DESCRIPTOR_SETS]c.VkDescriptorSet = [_]c.VkDescriptorSet{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS,
    descriptor_set_count: u32 = 0,
    current_pipeline_hash: u64 = 0,
    current_layout_hash: u64 = 0,
    current_entry_point_owned: ?[:0]u8 = null,
    fast_upload_buffer: c.VkBuffer = VK_NULL_U64,
    fast_upload_memory: c.VkDeviceMemory = VK_NULL_U64,
    fast_upload_capacity: u64 = 0,
    fast_upload_mapped: ?*anyopaque = null,

    pending_uploads: std.ArrayListUnmanaged(vk_upload.PendingUpload) = .{},
    surfaces: std.AutoHashMapUnmanaged(u64, vulkan_surface.VulkanSurface) = .{},

    src_pool: vk_upload.VkPool = .{},
    dst_pool: vk_upload.VkPool = .{},
    direct_upload_pool: vk_upload.VkPool = .{},
    hot_src_pool_entry: ?vk_upload.VkPoolEntry = null,
    hot_src_pool_size: u64 = 0,
    hot_dst_pool_entry: ?vk_upload.VkPoolEntry = null,
    hot_dst_pool_size: u64 = 0,
    compute_buffers: std.AutoHashMapUnmanaged(u64, vk_resources.ComputeBuffer) = .{},
    textures: std.AutoHashMapUnmanaged(u64, vk_resources.TextureResource) = .{},

    has_instance: bool = false,
    has_device: bool = false,
    has_command_pool: bool = false,
    has_primary_command_buffer: bool = false,
    has_fence: bool = false,
    has_shader_module: bool = false,
    has_pipeline_layout: bool = false,
    has_pipeline: bool = false,
    has_descriptor_pool: bool = false,
    has_deferred_submissions: bool = false,
    upload_recording_active: bool = false,
    // Tracks whether flush_queue left the command buffer in reset state,
    // avoiding a redundant vkResetCommandBuffer in ensure_upload_recording.
    command_buffer_reset_clean: bool = false,

    pub fn init(allocator: std.mem.Allocator, kernel_root: ?[]const u8) !NativeVulkanRuntime {
        var self = NativeVulkanRuntime{ .allocator = allocator, .kernel_root = kernel_root };
        errdefer self.deinit();
        try vk_device.bootstrap(&self);
        return self;
    }

    pub fn deinit(self: *NativeVulkanRuntime) void {
        _ = self.flush_queue() catch {};
        vk_upload.release_pending_uploads(self);
        self.pending_uploads.deinit(self.allocator);
        self.release_all_surfaces();
        vk_upload.release_pool_entry(self.device, self.hot_src_pool_entry);
        vk_upload.release_pool_entry(self.device, self.hot_dst_pool_entry);
        self.hot_src_pool_entry = null;
        self.hot_dst_pool_entry = null;
        vk_upload.vk_release_pool(&self.src_pool, self.allocator, self.device);
        vk_upload.vk_release_pool(&self.dst_pool, self.allocator, self.device);
        vk_upload.vk_release_pool(&self.direct_upload_pool, self.allocator, self.device);
        vk_upload.release_fast_upload_buffer(self);
        vk_pipeline.destroy_pipeline_objects(self);
        vk_pipeline.destroy_descriptor_state(self);
        vk_resources.release_compute_buffers(self);
        vk_resources.release_textures(self);
        if (self.has_fence) {
            c.vkDestroyFence(self.device, self.fence, null);
            self.has_fence = false;
            self.fence = VK_NULL_U64;
        }
        if (self.has_command_pool) {
            c.vkDestroyCommandPool(self.device, self.command_pool, null);
            self.has_command_pool = false;
            self.has_primary_command_buffer = false;
            self.command_pool = VK_NULL_U64;
            self.primary_command_buffer = null;
        }
        if (self.has_device) {
            c.vkDestroyDevice(self.device, null);
            self.has_device = false;
            self.device = null;
            self.queue = null;
        }
        if (self.has_instance) {
            c.vkDestroyInstance(self.instance, null);
            self.has_instance = false;
            self.instance = null;
            self.physical_device = null;
        }
    }

    // --- Kernel/shader API ---

    pub fn load_kernel_source(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
        return vk_pipeline.load_kernel_source(self, allocator, kernel_name);
    }

    pub fn load_kernel_spirv(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
        return vk_pipeline.load_kernel_spirv(self, allocator, kernel_name);
    }

    pub fn set_compute_shader_spirv(
        self: *NativeVulkanRuntime,
        words: []const u32,
        entry_point: ?[]const u8,
        bindings: ?[]const model.KernelBinding,
        initialize_buffers_on_create: bool,
    ) !void {
        return vk_pipeline.set_compute_shader_spirv(self, words, entry_point, bindings, initialize_buffers_on_create);
    }

    pub fn rebuild_compute_shader_spirv(self: *NativeVulkanRuntime, words: []const u32) !void {
        return vk_pipeline.rebuild_compute_shader_spirv(self, words);
    }

    // --- Upload API ---

    pub fn upload_bytes(
        self: *NativeVulkanRuntime,
        bytes: u64,
        mode: webgpu.UploadBufferUsageMode,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !void {
        if (bytes == 0) return error.InvalidArgument;

        switch (vk_upload.classify_upload_path(upload_path_policy, mode, bytes)) {
            .fast_mapped => {
                try vk_upload.ensure_fast_upload_buffer(self, bytes);
                if (self.fast_upload_mapped) |raw| {
                    const fill_len = vk_upload.bounded_upload_fill_len(bytes);
                    @memset(@as([*]u8, @ptrCast(raw))[0..fill_len], 0);
                }
                return;
            },
            .direct_mapped => {
                if (try vk_upload.try_direct_upload(self, bytes, c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_STORAGE_BUFFER_BIT)) {
                    return;
                }
            },
            .staged_copy => {},
        }

        const dst_usage: u32 = switch (mode) {
            .copy_dst_copy_src => c.VK_BUFFER_USAGE_TRANSFER_DST_BIT | c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
            .copy_dst => c.VK_BUFFER_USAGE_TRANSFER_DST_BIT,
        };

        const upload = try vk_upload.record_upload_copy(self, bytes, dst_usage);
        errdefer vk_upload.release_upload(self, upload);
        try self.pending_uploads.append(self.allocator, upload);
        self.has_deferred_submissions = true;
    }

    pub fn barrier(self: *NativeVulkanRuntime, queue_wait_mode: webgpu.QueueWaitMode) !u64 {
        const start_ns = common_timing.now_ns();
        switch (queue_wait_mode) {
            .process_events, .wait_any => {
                if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
                    _ = try self.flush_queue();
                }
            },
        }
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    // --- Dispatch ---

    pub fn run_dispatch(
        self: *NativeVulkanRuntime,
        x: u32,
        y: u32,
        z: u32,
        queue_sync_mode: webgpu.QueueSyncMode,
        queue_wait_mode: webgpu.QueueWaitMode,
        gpu_timestamp_mode: webgpu.GpuTimestampMode,
    ) !DispatchMetrics {
        if (x == 0 or y == 0 or z == 0) return error.InvalidArgument;
        if (!self.has_pipeline) return error.Unsupported;

        const encode_start = common_timing.now_ns();
        var command_buffer: c.VkCommandBuffer = null;

        if (queue_sync_mode == .per_command) {
            if (self.has_deferred_submissions) _ = try self.flush_queue();
            try c.check_vk(c.vkResetCommandPool(self.device, self.command_pool, 0));
            command_buffer = self.primary_command_buffer;
        } else {
            var alloc_info = c.VkCommandBufferAllocateInfo{
                .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
                .pNext = null,
                .commandPool = self.command_pool,
                .level = c.VK_COMMAND_BUFFER_LEVEL_PRIMARY,
                .commandBufferCount = 1,
            };
            try c.check_vk(c.vkAllocateCommandBuffers(self.device, &alloc_info, @ptrCast(&command_buffer)));
        }

        var begin_info = c.VkCommandBufferBeginInfo{
            .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try c.check_vk(c.vkBeginCommandBuffer(command_buffer, &begin_info));
        c.vkCmdBindPipeline(command_buffer, c.VK_PIPELINE_BIND_POINT_COMPUTE, self.pipeline);
        vk_pipeline.bind_descriptor_sets(self, command_buffer);
        c.vkCmdDispatch(command_buffer, x, y, z);
        try c.check_vk(c.vkEndCommandBuffer(command_buffer));

        const encode_end = common_timing.now_ns();
        const encode_ns = common_timing.ns_delta(encode_end, encode_start);

        var submit_info = c.VkSubmitInfo{
            .sType = c.VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .pNext = null,
            .waitSemaphoreCount = 0,
            .pWaitSemaphores = null,
            .pWaitDstStageMask = null,
            .commandBufferCount = 1,
            .pCommandBuffers = @ptrCast(&command_buffer),
            .signalSemaphoreCount = 0,
            .pSignalSemaphores = null,
        };

        const submit_start = common_timing.now_ns();
        if (queue_sync_mode == .per_command) {
            try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
            try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
            const wait_all: c.VkBool32 = if (queue_wait_mode == .wait_any) c.VK_FALSE else c.VK_TRUE;
            try c.check_vk(c.vkWaitForFences(self.device, 1, @ptrCast(&self.fence), wait_all, vk_upload.WAIT_TIMEOUT_NS));
        } else {
            try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), VK_NULL_U64));
            self.has_deferred_submissions = true;
        }
        const submit_end = common_timing.now_ns();

        var gpu_timestamp_ns: u64 = 0;
        var gpu_timestamp_attempted = false;
        var gpu_timestamp_valid = false;
        if (gpu_timestamp_mode != .off) {
            if (queue_sync_mode != .per_command) {
                if (gpu_timestamp_mode == .require) return error.TimingPolicyMismatch;
            } else if (self.timestamp_query_supported()) {
                gpu_timestamp_attempted = true;
                gpu_timestamp_ns = try self.collect_dispatch_gpu_timestamp();
                gpu_timestamp_valid = gpu_timestamp_ns > 0;
                if (gpu_timestamp_mode == .require and !gpu_timestamp_valid) return error.TimingPolicyMismatch;
            } else if (gpu_timestamp_mode == .require) {
                return error.TimingPolicyMismatch;
            }
        }
        return .{
            .encode_ns = encode_ns,
            .submit_wait_ns = common_timing.ns_delta(submit_end, submit_start),
            .gpu_timestamp_ns = gpu_timestamp_ns,
            .gpu_timestamp_attempted = gpu_timestamp_attempted,
            .gpu_timestamp_valid = gpu_timestamp_valid,
        };
    }

    // --- Queue management ---

    pub fn flush_queue(self: *NativeVulkanRuntime) !u64 {
        return vk_upload.flush_queue(self);
    }

    pub fn prewarm_upload_path(
        self: *NativeVulkanRuntime,
        max_upload_bytes: u64,
        mode: webgpu.UploadBufferUsageMode,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !void {
        if (max_upload_bytes == 0) return;
        const prewarm_bytes = if (vk_upload.MAX_UPLOAD_BYTES == 0)
            max_upload_bytes
        else
            @min(max_upload_bytes, vk_upload.MAX_UPLOAD_BYTES);
        try self.upload_bytes(prewarm_bytes, mode, upload_path_policy);
        _ = try self.flush_queue();
    }

    // --- Async diagnostics probes ---

    pub fn lifecycle_probe(self: *NativeVulkanRuntime, iterations: u32) !u64 {
        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try vk_resources.create_destroy_lifecycle_buffer(self, 256);
        }
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    pub fn pipeline_async_probe(self: *NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8, iterations: u32) !u64 {
        const spirv_words = try self.load_kernel_spirv(allocator, kernel_name);
        defer allocator.free(spirv_words);

        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try self.rebuild_compute_shader_spirv(spirv_words);
        }
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    pub fn resource_table_immediates_emulation_probe(
        self: *NativeVulkanRuntime,
        iterations: u32,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !u64 {
        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try vk_resources.create_destroy_lifecycle_buffer(self, 256);
            try self.upload_bytes(64, .copy_dst, upload_path_policy);
            _ = try self.flush_queue();
        }
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    pub fn pixel_local_storage_emulation_probe(
        self: *NativeVulkanRuntime,
        iterations: u32,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !u64 {
        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try vk_resources.create_destroy_lifecycle_buffer(self, 512);
            try self.upload_bytes(128, .copy_dst, upload_path_policy);
            _ = try self.barrier(.process_events);
        }
        _ = try self.flush_queue();
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    // --- Adapter info ---

    pub fn adapter_ordinal(self: *const NativeVulkanRuntime) ?u32 {
        return self.adapter_ordinal_value;
    }

    pub fn queue_family_index_value(self: *const NativeVulkanRuntime) ?u32 {
        return self.queue_family_index_value_cache;
    }

    pub fn present_capable(self: *const NativeVulkanRuntime) ?bool {
        return self.present_capable_value;
    }

    // --- Texture commands ---

    pub fn texture_write(self: *NativeVulkanRuntime, cmd_arg: model.TextureWriteCommand) !void {
        const resource = try vk_resources.ensure_texture_resource(self, cmd_arg.texture);
        if (cmd_arg.data.len == 0) {
            try vk_resources.ensure_texture_shader_layout(self, resource);
            return;
        }
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            _ = try self.flush_queue();
        }

        const staging = try vk_resources.create_host_visible_buffer(self, @intCast(cmd_arg.data.len), c.VK_BUFFER_USAGE_TRANSFER_SRC_BIT);
        defer vk_resources.destroy_host_visible_buffer(self, staging);
        if (staging.mapped) |raw| {
            @memcpy(@as([*]u8, @ptrCast(raw))[0..cmd_arg.data.len], cmd_arg.data);
        }

        try c.check_vk(c.vkResetCommandPool(self.device, self.command_pool, 0));
        var begin_info = c.VkCommandBufferBeginInfo{
            .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
        vk_resources.transition_texture_layout(
            self.primary_command_buffer,
            resource.*,
            resource.layout,
            c.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            0,
            c.VK_ACCESS_TRANSFER_WRITE_BIT,
            c.VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
            c.VK_PIPELINE_STAGE_TRANSFER_BIT,
        );

        var region = c.VkBufferImageCopy{
            .bufferOffset = 0,
            .bufferRowLength = if (cmd_arg.texture.bytes_per_row > 0)
                cmd_arg.texture.bytes_per_row / vk_resources.bytes_per_pixel_for_texture_format(cmd_arg.texture.format)
            else
                0,
            .bufferImageHeight = cmd_arg.texture.rows_per_image,
            .imageSubresource = .{
                .aspectMask = c.VK_IMAGE_ASPECT_COLOR_BIT,
                .mipLevel = cmd_arg.texture.mip_level,
                .baseArrayLayer = 0,
                .layerCount = 1,
            },
            .imageOffset = .{ .x = 0, .y = 0, .z = 0 },
            .imageExtent = .{
                .width = @max(cmd_arg.texture.width >> @intCast(cmd_arg.texture.mip_level), 1),
                .height = @max(cmd_arg.texture.height >> @intCast(cmd_arg.texture.mip_level), 1),
                .depth = 1,
            },
        };
        c.vkCmdCopyBufferToImage(
            self.primary_command_buffer,
            staging.buffer,
            resource.image,
            c.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            1,
            @ptrCast(&region),
        );

        vk_resources.transition_texture_layout(
            self.primary_command_buffer,
            resource.*,
            c.VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            c.VK_IMAGE_LAYOUT_GENERAL,
            c.VK_ACCESS_TRANSFER_WRITE_BIT,
            c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT,
            c.VK_PIPELINE_STAGE_TRANSFER_BIT,
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
        resource.layout = c.VK_IMAGE_LAYOUT_GENERAL;
    }

    pub fn texture_query(self: *NativeVulkanRuntime, cmd_arg: model.TextureQueryCommand) !void {
        const texture = self.textures.get(cmd_arg.handle) orelse return error.InvalidState;
        if (cmd_arg.expected_width) |width| if (texture.width != width) return error.InvalidState;
        if (cmd_arg.expected_height) |height| if (texture.height != height) return error.InvalidState;
        if (cmd_arg.expected_depth_or_array_layers) |layers| if (layers != 1) return error.InvalidState;
        if (cmd_arg.expected_format) |format| if (texture.format != format) return error.InvalidState;
        if (cmd_arg.expected_dimension) |dimension| if (dimension != model.WGPUTextureDimension_2D) return error.InvalidState;
        if (cmd_arg.expected_view_dimension) |view_dimension| if (view_dimension != model.WGPUTextureViewDimension_2D) return error.InvalidState;
        if (cmd_arg.expected_sample_count) |sample_count| if (sample_count != 1) return error.InvalidState;
        if (cmd_arg.expected_usage) |usage| if ((texture.usage & usage) != usage) return error.InvalidState;
    }

    pub fn texture_destroy(self: *NativeVulkanRuntime, cmd_arg: model.TextureDestroyCommand) !void {
        if (self.textures.fetchRemove(cmd_arg.handle)) |entry| {
            vk_resources.release_texture_resource(self, entry.value);
        }
    }

    // --- Surface lifecycle ---

    pub fn create_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        if (handle == 0) return error.InvalidArgument;
        const result = try self.surfaces.getOrPut(self.allocator, handle);
        if (result.found_existing) return error.InvalidState;
        result.value_ptr.* = .{};
    }

    pub fn get_surface_capabilities(self: *NativeVulkanRuntime, handle: u64) !void {
        const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
        if (surface.vk_surface != 0) {
            const caps = vulkan_surface.query_surface_capabilities(
                self.physical_device,
                self.queue_family_index,
                surface.vk_surface,
            ) catch |err| {
                return err;
            };
            surface.cached_capabilities = caps;
            surface.capabilities_queried = true;
        }
    }

    pub fn configure_surface(self: *NativeVulkanRuntime, cmd_arg: model.SurfaceConfigureCommand) !void {
        if (cmd_arg.width == 0 or cmd_arg.height == 0) return error.InvalidArgument;
        const surface = self.surfaces.getPtr(cmd_arg.handle) orelse return error.SurfaceUnavailable;
        // Unconfigure before reconfiguring to release stale swapchain state
        if (surface.configured and surface.swapchain != 0) {
            vulkan_surface.destroy_swapchain(self.device, surface);
        }
        surface.configured = true;
        surface.acquired = false;
        surface.width = cmd_arg.width;
        surface.height = cmd_arg.height;
        surface.format = cmd_arg.format;
        surface.usage = if (cmd_arg.usage == 0) model.WGPUTextureUsage_RenderAttachment else cmd_arg.usage;
        surface.alpha_mode = if (cmd_arg.alpha_mode == 0) c.VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR else cmd_arg.alpha_mode;
        surface.present_mode = if (cmd_arg.present_mode == 0) c.VK_PRESENT_MODE_FIFO_KHR else cmd_arg.present_mode;
        surface.desired_maximum_frame_latency = if (cmd_arg.desired_maximum_frame_latency == 0) c.DEFAULT_SURFACE_MAX_FRAME_LATENCY else cmd_arg.desired_maximum_frame_latency;
        // Create a real swapchain when a VkSurfaceKHR is available
        if (surface.vk_surface != 0) {
            try vulkan_surface.create_swapchain(
                self.device,
                self.physical_device,
                surface,
                self.queue_family_index,
            );
        }
    }

    pub fn acquire_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
        if (!surface.configured or surface.acquired) return error.SurfaceUnavailable;
        if (surface.swapchain != 0) {
            _ = try vulkan_surface.acquire_next_image(self.device, surface);
        } else {
            surface.acquired = true;
        }
    }

    pub fn present_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
        if (!surface.configured or !surface.acquired) return error.SurfaceUnavailable;
        if (surface.swapchain != 0) {
            try vulkan_surface.present_image(self.queue, surface);
        } else {
            surface.acquired = false;
            _ = try self.flush_queue();
        }
    }

    pub fn unconfigure_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
        if (surface.swapchain != 0) {
            vulkan_surface.destroy_swapchain(self.device, surface);
        }
        surface.configured = false;
        surface.acquired = false;
        surface.width = 0;
        surface.height = 0;
    }

    pub fn release_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        const removed = self.surfaces.fetchRemove(handle) orelse return error.SurfaceUnavailable;
        var surface_copy = removed.value;
        if (surface_copy.vk_surface != 0 or surface_copy.swapchain != 0) {
            vulkan_surface.destroy_all(self.instance, self.device, &surface_copy);
        }
    }

    fn release_all_surfaces(self: *NativeVulkanRuntime) void {
        var it = self.surfaces.valueIterator();
        while (it.next()) |surface| {
            if (surface.vk_surface != 0 or surface.swapchain != 0) {
                vulkan_surface.destroy_all(self.instance, self.device, surface);
            }
        }
        self.surfaces.deinit(self.allocator);
    }

    // --- Internal ---

    fn timestamp_query_supported(self: *const NativeVulkanRuntime) bool {
        if (!self.has_device or self.queue == null) return false;
        return self.queue_family_index_value_cache != null and self.timestamp_query_supported_value;
    }

    fn collect_dispatch_gpu_timestamp(self: *NativeVulkanRuntime) !u64 {
        var query_pool: c.VkQueryPool = VK_NULL_U64;
        defer if (query_pool != VK_NULL_U64) c.vkDestroyQueryPool(self.device, query_pool, null);

        var create_info = c.VkQueryPoolCreateInfo{
            .sType = c.VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .queryType = c.VK_QUERY_TYPE_TIMESTAMP,
            .queryCount = 2,
            .pipelineStatistics = 0,
        };
        try c.check_vk(c.vkCreateQueryPool(self.device, &create_info, null, &query_pool));

        try c.check_vk(c.vkResetCommandPool(self.device, self.command_pool, 0));
        var begin_info = c.VkCommandBufferBeginInfo{
            .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
        c.vkCmdWriteTimestamp(self.primary_command_buffer, c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, query_pool, 0);
        c.vkCmdBindPipeline(self.primary_command_buffer, c.VK_PIPELINE_BIND_POINT_COMPUTE, self.pipeline);
        vk_pipeline.bind_descriptor_sets(self, self.primary_command_buffer);
        c.vkCmdDispatch(self.primary_command_buffer, 1, 1, 1);
        c.vkCmdWriteTimestamp(self.primary_command_buffer, c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, query_pool, 1);
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

        var results: [2]u64 = .{ 0, 0 };
        try c.check_vk(c.vkGetQueryPoolResults(
            self.device,
            query_pool,
            0,
            2,
            @sizeOf(@TypeOf(results)),
            &results,
            @sizeOf(u64),
            c.VK_QUERY_RESULT_64_BIT | c.VK_QUERY_RESULT_WAIT_BIT,
        ));
        if (results[1] <= results[0]) return 0;
        return results[1] - results[0];
    }
};
