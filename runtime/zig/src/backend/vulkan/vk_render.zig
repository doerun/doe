// Render pass creation, draw call execution, and render bundle replay.
// Pipeline creation in vk_render_pipeline.zig.
const std = @import("std");
const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const vk_sync = @import("vk_sync.zig");
const vk_formats = @import("vk_formats.zig");
const vk_upload = @import("vk_upload.zig");
const vk_resources = @import("vk_resources.zig");
const BackendNativeError = @import("../../contracts/execution.zig").BackendNativeError;
const model_resource_types = @import("../../contracts/model/model_resource_types.zig");
const model_gpu_types = @import("../../contracts/model/model_texture_value_types.zig");
const model_render_types = @import("../../contracts/model/model_render_types.zig");
const common_timing = @import("../common/timing.zig");
const render_bundle = @import("../../runtime/render/render_bundle.zig");
const draw_recording = @import("vk_draw_recording.zig");
const vk_render_pipeline = @import("vk_render_pipeline.zig");
const DispatchMetrics = @import("vk_metrics.zig").DispatchMetrics;
const VK_NULL_U64 = c.VK_NULL_U64;
const VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT: u32 = 0x00000020;
const VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL = c.VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
const VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT = c.VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT;
const VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT = c.VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT;
const VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT = c.VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT;
const VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT = c.VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;
const WGPU_INDEX_FORMAT_UINT16: u32 = 0x00000001;
const VK_PIPELINE_STAGE_GRAPHICS_SHADER_BITS: u32 = c.VK_PIPELINE_STAGE_VERTEX_SHADER_BIT | c.VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;

pub const RenderState = struct {
    render_pass: c.VkRenderPass = VK_NULL_U64,
    framebuffer: c.VkFramebuffer = VK_NULL_U64,
    graphics_pipeline: c.VkPipeline = VK_NULL_U64,
    graphics_pipeline_layout: c.VkPipelineLayout = VK_NULL_U64,
    vertex_shader: c.VkShaderModule = VK_NULL_U64,
    fragment_shader: c.VkShaderModule = VK_NULL_U64,
    descriptor_set_layout: u64 = VK_NULL_U64,
    descriptor_pool: u64 = VK_NULL_U64,
    descriptor_set: u64 = VK_NULL_U64,
    render_target: ?vk_resources.TextureResource = null,
    depth_stencil_target: ?vk_resources.TextureResource = null,
    target_width: u32 = 0,
    target_height: u32 = 0,
    target_format: u32 = 0,
    owns_render_target: bool = false,
    owns_depth_stencil_target: bool = false,
    index_buffer: ?vk_resources.ComputeBuffer = null,
};

fn destroyVkHandle(device: c.VkDevice, handle: *u64, destroy_fn: anytype) void {
    if (handle.* != VK_NULL_U64) {
        destroy_fn(device, handle.*, null);
        handle.* = VK_NULL_U64;
    }
}

pub fn release_render_state(device: c.VkDevice, state: *RenderState) void {
    if (state.index_buffer) |buffer| {
        if (buffer.mapped != null) c.vkUnmapMemory(device, buffer.memory);
        c.vkDestroyBuffer(device, buffer.buffer, null);
        c.vkFreeMemory(device, buffer.memory, null);
        state.index_buffer = null;
    }
    destroyVkHandle(device, &state.descriptor_pool, c.vkDestroyDescriptorPool);
    state.descriptor_set = VK_NULL_U64;
    destroyVkHandle(device, &state.descriptor_set_layout, c.vkDestroyDescriptorSetLayout);
    destroyVkHandle(device, &state.graphics_pipeline, c.vkDestroyPipeline);
    destroyVkHandle(device, &state.graphics_pipeline_layout, c.vkDestroyPipelineLayout);
    destroyVkHandle(device, &state.fragment_shader, c.vkDestroyShaderModule);
    destroyVkHandle(device, &state.vertex_shader, c.vkDestroyShaderModule);
    destroyVkHandle(device, &state.framebuffer, c.vkDestroyFramebuffer);
    destroyVkHandle(device, &state.render_pass, c.vkDestroyRenderPass);
    if (state.owns_render_target) {
        if (state.render_target) |target|
            vk_resources.release_texture_resource_with_device(device, target);
    }
    state.render_target = null;
    if (state.owns_depth_stencil_target) {
        if (state.depth_stencil_target) |target|
            vk_resources.release_texture_resource_with_device(device, target);
    }
    state.depth_stencil_target = null;
}
pub fn execute_render_draw(
    self: anytype,
    cmd: model_render_types.RenderDrawCommand,
) !DispatchMetrics {
    try self.retirement.requireActive();
    const draw_count = if (cmd.draw_count > 0) cmd.draw_count else 1;
    const target_width = if (cmd.target_width > 0) cmd.target_width else model_render_types.DEFAULT_RENDER_TARGET_WIDTH;
    const target_height = if (cmd.target_height > 0) cmd.target_height else model_render_types.DEFAULT_RENDER_TARGET_HEIGHT;
    const vk_format = try vk_resources.texture_format_to_vk(cmd.target_format);

    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
        _ = try vk_upload.flush_queue(self);
    }
    try vk_device.ensure_submission_state(self);

    var render_state = RenderState{};
    defer release_render_state(self.device, &render_state);
    const encode_start = common_timing.now_ns();
    try ensure_render_target(self, &render_state, cmd, target_width, target_height, cmd.target_format, cmd.depth_stencil_format);
    const has_depth_stencil = cmd.depth_stencil_format != model_gpu_types.WGPUTextureFormat_Undefined;
    const depth_stencil_vk_format = if (has_depth_stencil) try vk_resources.texture_format_to_vk(cmd.depth_stencil_format) else 0;
    try create_render_pass(
        self,
        &render_state,
        vk_format,
        has_depth_stencil,
        depth_stencil_vk_format,
        c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
        cmd,
    );
    try create_framebuffer(self, &render_state, target_width, target_height);
    try create_graphics_pipeline(self, &render_state, vk_format, cmd);
    const encode_end = common_timing.now_ns();
    const setup_ns = common_timing.ns_delta(encode_end, encode_start);
    const draw_start = common_timing.now_ns();
    try record_and_submit_draws(self, &render_state, cmd, draw_count, target_width, target_height);
    const draw_end = common_timing.now_ns();
    return .{
        .encode_ns = setup_ns,
        .submit_wait_ns = common_timing.ns_delta(draw_end, draw_start),
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

pub fn execute_render_clear(
    self: anytype,
    cmd: model_render_types.RenderDrawCommand,
) !DispatchMetrics {
    try self.retirement.requireActive();
    const target_width = if (cmd.target_width > 0) cmd.target_width else model_render_types.DEFAULT_RENDER_TARGET_WIDTH;
    const target_height = if (cmd.target_height > 0) cmd.target_height else model_render_types.DEFAULT_RENDER_TARGET_HEIGHT;
    const vk_format = try vk_resources.texture_format_to_vk(cmd.target_format);

    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
        _ = try vk_upload.flush_queue(self);
    }
    try vk_device.ensure_submission_state(self);

    var render_state = RenderState{};
    defer release_render_state(self.device, &render_state);

    const encode_start = common_timing.now_ns();
    try ensure_render_target(
        self,
        &render_state,
        cmd,
        target_width,
        target_height,
        cmd.target_format,
        cmd.depth_stencil_format,
    );
    const color_final_layout = c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    const has_depth_stencil = cmd.depth_stencil_format != model_gpu_types.WGPUTextureFormat_Undefined;
    const depth_stencil_vk_format = if (has_depth_stencil) try vk_resources.texture_format_to_vk(cmd.depth_stencil_format) else 0;
    try create_render_pass(
        self,
        &render_state,
        vk_format,
        has_depth_stencil,
        depth_stencil_vk_format,
        color_final_layout,
        cmd,
    );
    try create_framebuffer(self, &render_state, target_width, target_height);
    const encode_end = common_timing.now_ns();

    const submit_start = common_timing.now_ns();
    try record_and_submit_clear(self, &render_state, cmd, target_width, target_height);
    const submit_end = common_timing.now_ns();
    mark_attachment_layouts(self, &render_state, color_final_layout);
    return .{
        .encode_ns = common_timing.ns_delta(encode_end, encode_start),
        .submit_wait_ns = common_timing.ns_delta(submit_end, submit_start),
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
        .submit_count = 1,
    };
}

fn ensure_render_target(
    self: anytype,
    state: *RenderState,
    cmd: model_render_types.RenderDrawCommand,
    width: u32,
    height: u32,
    format: model_gpu_types.WGPUTextureFormat,
    depth_stencil_format: model_gpu_types.WGPUTextureFormat,
) !void {
    if (!try bind_existing_render_target(self, state, cmd, width, height, format)) {
        const texture_spec = model_resource_types.CopyTextureResource{
            .handle = 0,
            .width = width,
            .height = height,
            .format = format,
            .usage = model_gpu_types.WGPUTextureUsage_RenderAttachment | model_gpu_types.WGPUTextureUsage_CopyDst,
            .mip_level = 0,
            .bytes_per_row = 0,
            .rows_per_image = 0,
        };
        state.render_target = try create_render_target_texture(self, texture_spec);
        state.owns_render_target = true;
    }
    if (cmd.depth_target_handle != 0) {
        const texture = self.textures.get(cmd.depth_target_handle) orelse return error.InvalidState;
        const view = if (cmd.depth_target_view_handle != 0)
            self.textures.get(cmd.depth_target_view_handle) orelse return error.InvalidState
        else
            texture;
        if (!vk_formats.is_depth_stencil(view.format) or view.format != depth_stencil_format or
            !vk_resources.texture_view_matches_parent(view, cmd.depth_target_handle, texture))
            return error.InvalidArgument;
        var attachment = texture;
        attachment.view = view.view;
        state.depth_stencil_target = attachment;
    } else if (depth_stencil_format != model_gpu_types.WGPUTextureFormat_Undefined) {
        const depth_texture_spec = model_resource_types.CopyTextureResource{
            .handle = 0,
            .width = width,
            .height = height,
            .format = depth_stencil_format,
            .usage = model_gpu_types.WGPUTextureUsage_RenderAttachment,
            .mip_level = 0,
            .bytes_per_row = 0,
            .rows_per_image = 0,
        };
        state.depth_stencil_target = try create_render_target_texture(self, depth_texture_spec);
        state.owns_depth_stencil_target = true;
    }
    state.target_width = width;
    state.target_height = height;
}

fn bind_existing_render_target(
    self: anytype,
    state: *RenderState,
    cmd: model_render_types.RenderDrawCommand,
    width: u32,
    height: u32,
    format: model_gpu_types.WGPUTextureFormat,
) !bool {
    if (cmd.target_handle == 0 or cmd.target_handle == model_render_types.DEFAULT_RENDER_TARGET_HANDLE) return false;
    const texture = self.textures.get(cmd.target_handle) orelse return error.InvalidState;
    const view_resource = if (cmd.target_view_handle != 0)
        self.textures.get(cmd.target_view_handle) orelse return error.InvalidState
    else
        texture;
    if (!vk_resources.texture_view_matches_parent(view_resource, cmd.target_handle, texture)) return error.InvalidState;
    state.render_target = .{
        .image = texture.image,
        .memory = texture.memory,
        .view = view_resource.view,
        .width = if (width > 0) width else texture.width,
        .height = if (height > 0) height else texture.height,
        .depth_or_array_layers = texture.depth_or_array_layers,
        .mip_levels = texture.mip_levels,
        .sample_count = texture.sample_count,
        .dimension = texture.dimension,
        .view_dimension = view_resource.view_dimension,
        .aspect = view_resource.aspect,
        .format = if (format != 0) format else texture.format,
        .usage = texture.usage,
        .layout = texture.layout,
    };
    return true;
}

fn create_render_target_texture(
    self: anytype,
    spec: model_resource_types.CopyTextureResource,
) !vk_resources.TextureResource {
    var image: c.VkImage = VK_NULL_U64;
    var memory: c.VkDeviceMemory = VK_NULL_U64;
    var view: c.VkImageView = VK_NULL_U64;
    const vk_format = try vk_resources.texture_format_to_vk(spec.format);

    const is_depth_stencil = vk_formats.is_depth_stencil(spec.format);
    var image_info = c.VkImageCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .imageType = c.VK_IMAGE_TYPE_2D,
        .format = vk_format,
        .extent = .{ .width = spec.width, .height = spec.height, .depth = 1 },
        .mipLevels = 1,
        .arrayLayers = 1,
        .samples = c.VK_SAMPLE_COUNT_1_BIT,
        .tiling = c.VK_IMAGE_TILING_OPTIMAL,
        .usage = if (is_depth_stencil)
            VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT
        else
            c.VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | c.VK_IMAGE_USAGE_TRANSFER_DST_BIT,
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
        .format = vk_format,
        .components = .{
            .r = c.VK_COMPONENT_SWIZZLE_IDENTITY,
            .g = c.VK_COMPONENT_SWIZZLE_IDENTITY,
            .b = c.VK_COMPONENT_SWIZZLE_IDENTITY,
            .a = c.VK_COMPONENT_SWIZZLE_IDENTITY,
        },
        .subresourceRange = .{
            .aspectMask = vk_formats.aspect_mask_for_format(spec.format),
            .baseMipLevel = 0,
            .levelCount = 1,
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
        .width = spec.width,
        .height = spec.height,
        .depth_or_array_layers = if (spec.depth_or_array_layers > 0) spec.depth_or_array_layers else 1,
        .mip_levels = 1,
        .sample_count = if (spec.sample_count > 0) spec.sample_count else 1,
        .dimension = if (spec.dimension != 0) spec.dimension else model_gpu_types.WGPUTextureDimension_2D,
        .view_dimension = if (spec.view_dimension != 0) spec.view_dimension else model_gpu_types.WGPUTextureViewDimension_2D,
        .aspect = if (spec.aspect != 0) spec.aspect else model_gpu_types.WGPUTextureAspect_All,
        .format = spec.format,
        .usage = spec.usage,
        .layout = c.VK_IMAGE_LAYOUT_UNDEFINED,
    };
}

fn create_render_pass(
    self: anytype,
    state: *RenderState,
    vk_format: u32,
    has_depth_stencil: bool,
    depth_stencil_vk_format: u32,
    color_final_layout: u32,
    cmd: model_render_types.RenderDrawCommand,
) !void {
    const color_initial_layout = if (state.render_target) |target| target.layout else c.VK_IMAGE_LAYOUT_UNDEFINED;
    const depth_initial_layout = if (state.depth_stencil_target) |target| target.layout else c.VK_IMAGE_LAYOUT_UNDEFINED;
    var attachments = [_]c.VkAttachmentDescription{
        .{
            .flags = 0,
            .format = vk_format,
            .samples = c.VK_SAMPLE_COUNT_1_BIT,
            .loadOp = switch (cmd.color_load) {
                .clear => c.VK_ATTACHMENT_LOAD_OP_CLEAR,
                .load => c.VK_ATTACHMENT_LOAD_OP_LOAD,
            },
            .storeOp = c.VK_ATTACHMENT_STORE_OP_STORE,
            .stencilLoadOp = c.VK_ATTACHMENT_LOAD_OP_DONT_CARE,
            .stencilStoreOp = c.VK_ATTACHMENT_STORE_OP_DONT_CARE,
            .initialLayout = color_initial_layout,
            .finalLayout = color_final_layout,
        },
        .{
            .flags = 0,
            .format = depth_stencil_vk_format,
            .samples = c.VK_SAMPLE_COUNT_1_BIT,
            .loadOp = switch (cmd.depth_load) {
                .clear => c.VK_ATTACHMENT_LOAD_OP_CLEAR,
                .load => c.VK_ATTACHMENT_LOAD_OP_LOAD,
            },
            .storeOp = c.VK_ATTACHMENT_STORE_OP_STORE,
            .stencilLoadOp = switch (cmd.stencil_load) {
                .clear => c.VK_ATTACHMENT_LOAD_OP_CLEAR,
                .load => c.VK_ATTACHMENT_LOAD_OP_LOAD,
            },
            .stencilStoreOp = c.VK_ATTACHMENT_STORE_OP_STORE,
            .initialLayout = depth_initial_layout,
            .finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,
        },
    };

    var color_ref = c.VkAttachmentReference{
        .attachment = 0,
        .layout = c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
    };
    var depth_stencil_ref = c.VkAttachmentReference{
        .attachment = 1,
        .layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL,
    };

    var subpass = c.VkSubpassDescription{
        .flags = 0,
        .pipelineBindPoint = c.VK_PIPELINE_BIND_POINT_GRAPHICS,
        .inputAttachmentCount = 0,
        .pInputAttachments = null,
        .colorAttachmentCount = 1,
        .pColorAttachments = @ptrCast(&color_ref),
        .pResolveAttachments = null,
        .pDepthStencilAttachment = if (has_depth_stencil) @ptrCast(&depth_stencil_ref) else null,
        .preserveAttachmentCount = 0,
        .pPreserveAttachments = null,
    };

    const color_source = vk_resources.texture_transition_source(color_initial_layout);
    const depth_source = vk_resources.texture_transition_source(depth_initial_layout);
    var dependency = c.VkSubpassDependency{
        .srcSubpass = c.VK_SUBPASS_EXTERNAL,
        .dstSubpass = 0,
        .srcStageMask = color_source.src_stage | depth_source.src_stage,
        .dstStageMask = if (has_depth_stencil)
            c.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT |
                VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT |
                VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT
        else
            c.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
        .srcAccessMask = color_source.src_access_mask | depth_source.src_access_mask,
        .dstAccessMask = if (has_depth_stencil)
            c.VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | c.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT |
                VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT |
                VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT
        else
            c.VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | c.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
        .dependencyFlags = 0,
    };

    var render_pass_info = c.VkRenderPassCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .attachmentCount = if (has_depth_stencil) 2 else 1,
        .pAttachments = attachments[0..if (has_depth_stencil) 2 else 1].ptr,
        .subpassCount = 1,
        .pSubpasses = @ptrCast(&subpass),
        .dependencyCount = 1,
        .pDependencies = @ptrCast(&dependency),
    };
    try c.check_vk(c.vkCreateRenderPass(self.device, &render_pass_info, null, &state.render_pass));
}

fn create_framebuffer(
    self: anytype,
    state: *RenderState,
    width: u32,
    height: u32,
) !void {
    const target = state.render_target orelse return error.InvalidState;
    var attachments = [_]c.VkImageView{
        target.view,
        if (state.depth_stencil_target) |depth| depth.view else VK_NULL_U64,
    };

    var fb_info = c.VkFramebufferCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .renderPass = state.render_pass,
        .attachmentCount = if (state.depth_stencil_target != null) 2 else 1,
        .pAttachments = attachments[0..if (state.depth_stencil_target != null) 2 else 1].ptr,
        .width = width,
        .height = height,
        .layers = 1,
    };
    try c.check_vk(c.vkCreateFramebuffer(self.device, &fb_info, null, &state.framebuffer));
}

fn create_graphics_pipeline(
    self: anytype,
    state: *RenderState,
    vk_format: u32,
    cmd: model_render_types.RenderDrawCommand,
) !void {
    return vk_render_pipeline.create_graphics_pipeline(self, state, vk_format, cmd);
}

fn resolve_vk_buffer_handle(self: anytype, handle: ?*anyopaque) ?c.VkBuffer {
    const ptr = handle orelse return null;
    const cb = self.compute_buffers.get(@intFromPtr(ptr)) orelse return null;
    return cb.buffer;
}

fn transition_bound_textures(self: anytype, cmd: model_render_types.RenderDrawCommand) void {
    var ti: u32 = 0;
    while (ti < cmd.bind_texture_count and ti < model_render_types.MAX_RENDER_BIND_ENTRIES) : (ti += 1) {
        const texture = self.textures.get(cmd.bind_texture_handles[ti]) orelse continue;
        const is_storage = cmd.bind_texture_storage[ti];
        const destination_layout = vk_render_pipeline.render_texture_image_layout(is_storage);
        if (texture.layout == destination_layout) continue;
        const source = vk_resources.texture_transition_source(texture.layout);
        vk_resources.transition_texture_layout(
            self.primary_command_buffer,
            texture,
            texture.layout,
            destination_layout,
            source.src_access_mask,
            if (is_storage)
                c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT
            else
                c.VK_ACCESS_SHADER_READ_BIT,
            source.src_stage,
            VK_PIPELINE_STAGE_GRAPHICS_SHADER_BITS,
        );
        vk_resources.mark_texture_image_layout(self, texture.image, destination_layout);
    }
}

fn record_and_submit_draws(
    self: anytype,
    state: *RenderState,
    cmd: model_render_types.RenderDrawCommand,
    draw_count: u32,
    target_width: u32,
    target_height: u32,
) !void {
    const index = try prepare_index_binding(self, state, cmd);
    try begin_primary_recording(self);
    transition_bound_textures(self, cmd);

    const recording = draw_recording.DrawRecording{
        .command_buffer = self.primary_command_buffer,
        .buffers = &self.compute_buffers,
        .render_pass = state.render_pass,
        .framebuffer = state.framebuffer,
        .pipeline = state.graphics_pipeline,
        .pipeline_layout = state.graphics_pipeline_layout,
        .descriptor_set = state.descriptor_set,
        .has_depth_stencil = state.depth_stencil_target != null,
    };
    try recording.record(cmd, index, draw_count, target_width, target_height);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    try submit_and_wait(self);
    mark_attachment_layouts(self, state, c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL);
}

fn mark_attachment_layouts(self: anytype, state: *const RenderState, color_layout: u32) void {
    if (!state.owns_render_target) {
        if (state.render_target) |texture|
            vk_resources.mark_texture_image_layout(self, texture.image, color_layout);
    }
    if (!state.owns_depth_stencil_target) {
        if (state.depth_stencil_target) |texture|
            vk_resources.mark_texture_image_layout(self, texture.image, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL);
    }
}

fn begin_primary_recording(self: anytype) !void {
    try c.check_vk(c.vkResetCommandPool(self.device, self.command_pool, 0));
    var begin_info = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
}

fn record_and_submit_clear(
    self: anytype,
    state: *RenderState,
    cmd: model_render_types.RenderDrawCommand,
    target_width: u32,
    target_height: u32,
) !void {
    try begin_primary_recording(self);

    var clear_values = [_]c.VkClearValue{
        try draw_recording.color_clear_value(cmd.target_format, cmd.clear_color),
        .{ .depthStencil = .{ .depth = cmd.depth_clear_value, .stencil = cmd.stencil_clear_value } },
    };
    var render_pass_begin = c.VkRenderPassBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
        .pNext = null,
        .renderPass = state.render_pass,
        .framebuffer = state.framebuffer,
        .renderArea = .{
            .offset = .{ .x = 0, .y = 0 },
            .extent = .{ .width = target_width, .height = target_height },
        },
        .clearValueCount = if (state.depth_stencil_target != null) 2 else 1,
        .pClearValues = clear_values[0..if (state.depth_stencil_target != null) 2 else 1].ptr,
    };
    c.vkCmdBeginRenderPass(self.primary_command_buffer, &render_pass_begin, c.VK_SUBPASS_CONTENTS_INLINE);
    c.vkCmdEndRenderPass(self.primary_command_buffer);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    try submit_and_wait(self);
}

fn submit_render_with_fence(retirement: *vk_sync.Retirement, device: c.VkDevice, queue: c.VkQueue, info: *const c.VkSubmitInfo, fence: c.VkFence) BackendNativeError!void {
    const result = c.vkQueueSubmit(queue, 1, @ptrCast(info), fence);
    c.check_vk(result) catch |err| {
        if (!vk_sync.submissionRejected(result)) retire_failed_submission(retirement, device, err);
        return err;
    };
}

fn retire_failed_submission(retirement: *vk_sync.Retirement, device: c.VkDevice, err: BackendNativeError) void {
    // These commands own stack-scoped attachments and index storage. An error
    // cannot unwind that scope until native completion or device loss permits it.
    retirement.failed(err);
    retirement.waitForDestruction(device);
}

fn submit_and_wait(self: anytype) !void {
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
    if (self.has_timeline_semaphore) {
        var tsi = try vk_sync.TimelineSubmitHelper.prepare(&self.timeline_semaphore);
        tsi.patch();
        submit_info.pNext = @ptrCast(&tsi.timeline_info);
        submit_info.signalSemaphoreCount = 1;
        submit_info.pSignalSemaphores = @ptrCast(&tsi.semaphore);
        tsi.submit(&self.timeline_semaphore, self.queue, &submit_info) catch |err| {
            // Timeline submission publishes its reserved value only when work
            // may have reached the queue; allocation rejection permits retry.
            if (self.timeline_semaphore.current_value == tsi.signal_value)
                retire_failed_submission(&self.retirement, self.device, err);
            return err;
        };
        errdefer |err| retire_failed_submission(&self.retirement, self.device, err);
        try self.timeline_semaphore.wait(self.device, tsi.signal_value);
    } else {
        try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try submit_render_with_fence(&self.retirement, self.device, self.queue, &submit_info, self.fence);
        errdefer |err| retire_failed_submission(&self.retirement, self.device, err);
        try c.check_vk(c.vkWaitForFences(self.device, 1, @ptrCast(&self.fence), c.VK_TRUE, vk_upload.WAIT_TIMEOUT_NS));
    }
}

fn prepare_index_binding(self: anytype, state: *RenderState, cmd: model_render_types.RenderDrawCommand) !?draw_recording.IndexBinding {
    if (cmd.index_data == null and cmd.index_binding == null and cmd.index_count == null) return null;
    if (cmd.index_binding) |binding| {
        return .{
            .buffer = resolve_vk_buffer_handle(self, binding.handle) orelse return error.InvalidArgument,
            .offset = binding.offset,
            .format = if (binding.format == WGPU_INDEX_FORMAT_UINT16) c.VK_INDEX_TYPE_UINT16 else c.VK_INDEX_TYPE_UINT32,
            .count = cmd.index_count orelse if (cmd.indirect_buffer_handle != 0) 0 else return error.InvalidArgument,
        };
    }
    if (cmd.index_buffer_handle != 0) {
        const buffer = self.compute_buffers.get(cmd.index_buffer_handle) orelse return error.InvalidArgument;
        return .{
            .buffer = buffer.buffer,
            .offset = cmd.index_buffer_offset,
            .format = if (cmd.index_format == WGPU_INDEX_FORMAT_UINT16) c.VK_INDEX_TYPE_UINT16 else c.VK_INDEX_TYPE_UINT32,
            .count = cmd.index_count orelse if (cmd.indirect_buffer_handle != 0) 0 else return error.InvalidArgument,
        };
    }
    const data = cmd.index_data orelse return error.InvalidArgument;
    const bytes = switch (data) {
        .uint16 => |values| std.mem.sliceAsBytes(values),
        .uint32 => |values| std.mem.sliceAsBytes(values),
    };
    const buffer = try vk_resources.create_host_visible_buffer(self, bytes.len, c.VK_BUFFER_USAGE_INDEX_BUFFER_BIT);
    state.index_buffer = buffer;
    if (buffer.mapped) |raw| @memcpy(@as([*]u8, @ptrCast(raw))[0..bytes.len], bytes);
    return .{
        .buffer = buffer.buffer,
        .offset = 0,
        .format = if (data == .uint16) c.VK_INDEX_TYPE_UINT16 else c.VK_INDEX_TYPE_UINT32,
        .count = cmd.index_count orelse switch (data) {
            .uint16 => |values| @intCast(values.len),
            .uint32 => |values| @intCast(values.len),
        },
    };
}

// Replay render bundles into a standalone render pass. Creates render target,
// render pass + framebuffer, then replays each bundle's command list.
pub fn execute_render_bundles(
    self: anytype,
    bundles: []const *const render_bundle.DoeRenderBundle,
    target_width: u32,
    target_height: u32,
    color_format: u32,
    sample_count: u32,
) !DispatchMetrics {
    try self.retirement.requireActive();
    if (bundles.len == 0) return .{};
    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0)
        _ = try vk_upload.flush_queue(self);
    try vk_device.ensure_submission_state(self);
    const width = if (target_width > 0) target_width else model_render_types.DEFAULT_RENDER_TARGET_WIDTH;
    const height = if (target_height > 0) target_height else model_render_types.DEFAULT_RENDER_TARGET_HEIGHT;
    const vk_format = try vk_resources.texture_format_to_vk(color_format);
    const pass_sample_count = if (sample_count == 0) @as(u32, 1) else sample_count;
    var state = RenderState{};
    defer release_render_state(self.device, &state);
    const encode_start = common_timing.now_ns();
    const bundle_cmd = model_render_types.RenderDrawCommand{
        .draw_count = 1,
        .target_width = width,
        .target_height = height,
        .target_format = @intCast(color_format),
    };
    try ensure_render_target(self, &state, bundle_cmd, width, height, @intCast(color_format), model_gpu_types.WGPUTextureFormat_Undefined);
    try create_render_pass(
        self,
        &state,
        vk_format,
        false,
        0,
        c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
        bundle_cmd,
    );
    try create_framebuffer(self, &state, width, height);
    const encode_end = common_timing.now_ns();
    const draw_start = common_timing.now_ns();
    try begin_primary_recording(self);

    var clear_value = try draw_recording.color_clear_value(bundle_cmd.target_format, .{ 0, 0, 0, 1 });
    var render_pass_begin = c.VkRenderPassBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
        .pNext = null,
        .renderPass = state.render_pass,
        .framebuffer = state.framebuffer,
        .renderArea = .{
            .offset = .{ .x = 0, .y = 0 },
            .extent = .{ .width = width, .height = height },
        },
        .clearValueCount = 1,
        .pClearValues = @ptrCast(&clear_value),
    };
    c.vkCmdBeginRenderPass(self.primary_command_buffer, &render_pass_begin, c.VK_SUBPASS_CONTENTS_INLINE);
    var viewport = c.VkViewport{ .x = 0, .y = 0, .width = @floatFromInt(width), .height = @floatFromInt(height), .minDepth = 0, .maxDepth = 1 };
    c.vkCmdSetViewport(self.primary_command_buffer, 0, 1, @ptrCast(&viewport));
    var scissor = c.VkRect2D{ .offset = .{ .x = 0, .y = 0 }, .extent = .{ .width = width, .height = height } };
    c.vkCmdSetScissor(self.primary_command_buffer, 0, 1, @ptrCast(&scissor));
    for (bundles) |b| {
        // Unsubmitted recording may be abandoned: state cleanup invalidates its
        // references, and begin_primary_recording resets the pool before reuse.
        try render_bundle.replay_bundle_vk(b, @ptrCast(self.primary_command_buffer), color_format, pass_sample_count);
    }
    c.vkCmdEndRenderPass(self.primary_command_buffer);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    try submit_and_wait(self);
    const draw_end = common_timing.now_ns();
    return .{ .encode_ns = common_timing.ns_delta(encode_end, encode_start), .submit_wait_ns = common_timing.ns_delta(draw_end, draw_start) };
}
