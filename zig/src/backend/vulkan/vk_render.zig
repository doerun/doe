// Render pass, graphics pipeline, and draw call execution for the Vulkan backend.
//
// Handles:
//   - VkRenderPass creation for offscreen color attachments
//   - VkGraphicsPipeline creation (vertex + fragment stages, dynamic viewport/scissor)
//   - VkFramebuffer creation bound to a render target image view
//   - Vertex buffer upload and binding
//   - Draw call recording (non-indexed and indexed)
//   - Render state cleanup

const std = @import("std");
const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const vk_upload = @import("vk_upload.zig");
const vk_resources = @import("vk_resources.zig");
const vk_pipeline = @import("vk_pipeline.zig");
const model = @import("../../model.zig");
const doe_wgsl = @import("../../doe_wgsl/mod.zig");
const common_timing = @import("../common/timing.zig");

const VK_NULL_U64 = c.VK_NULL_U64;
const native_runtime = @import("native_runtime.zig");
const Runtime = native_runtime.NativeVulkanRuntime;
const DispatchMetrics = native_runtime.DispatchMetrics;

// Passthrough vertex+fragment WGSL: vertex_index generates a fullscreen triangle,
// fragment outputs a UV-gradient color. Single combined source for both entry points.
const RENDER_SHADER_WGSL =
    \\struct VertexOutput {
    \\    @builtin(position) position: vec4f,
    \\    @location(0) uv: vec2f,
    \\};
    \\
    \\@vertex fn vs_main(@builtin(vertex_index) vi: u32) -> VertexOutput {
    \\    var out: VertexOutput;
    \\    let x = f32(i32(vi & 1u) * 4 - 1);
    \\    let y = f32(i32(vi >> 1u & 1u) * 4 - 1);
    \\    out.position = vec4f(x, y, 0.0, 1.0);
    \\    out.uv = vec2f(x * 0.5 + 0.5, y * 0.5 + 0.5);
    \\    return out;
    \\}
    \\
    \\@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
    \\    return vec4f(uv.x, uv.y, 0.5, 1.0);
    \\}
;

const VERTEX_ENTRY_POINT: [*:0]const u8 = "vs_main";
const FRAGMENT_ENTRY_POINT: [*:0]const u8 = "fs_main";

pub const RenderState = struct {
    render_pass: c.VkRenderPass = VK_NULL_U64,
    framebuffer: c.VkFramebuffer = VK_NULL_U64,
    graphics_pipeline: c.VkPipeline = VK_NULL_U64,
    graphics_pipeline_layout: c.VkPipelineLayout = VK_NULL_U64,
    vertex_shader: c.VkShaderModule = VK_NULL_U64,
    fragment_shader: c.VkShaderModule = VK_NULL_U64,
    render_target: ?vk_resources.TextureResource = null,
    render_target_handle: u64 = 0,
    target_width: u32 = 0,
    target_height: u32 = 0,
    target_format: u32 = 0,
};

pub fn release_render_state(device: c.VkDevice, state: *RenderState) void {
    if (state.graphics_pipeline != VK_NULL_U64) {
        c.vkDestroyPipeline(device, state.graphics_pipeline, null);
        state.graphics_pipeline = VK_NULL_U64;
    }
    if (state.graphics_pipeline_layout != VK_NULL_U64) {
        c.vkDestroyPipelineLayout(device, state.graphics_pipeline_layout, null);
        state.graphics_pipeline_layout = VK_NULL_U64;
    }
    if (state.fragment_shader != VK_NULL_U64) {
        c.vkDestroyShaderModule(device, state.fragment_shader, null);
        state.fragment_shader = VK_NULL_U64;
    }
    if (state.vertex_shader != VK_NULL_U64) {
        c.vkDestroyShaderModule(device, state.vertex_shader, null);
        state.vertex_shader = VK_NULL_U64;
    }
    if (state.framebuffer != VK_NULL_U64) {
        c.vkDestroyFramebuffer(device, state.framebuffer, null);
        state.framebuffer = VK_NULL_U64;
    }
    if (state.render_pass != VK_NULL_U64) {
        c.vkDestroyRenderPass(device, state.render_pass, null);
        state.render_pass = VK_NULL_U64;
    }
    if (state.render_target) |target| {
        vk_resources.release_texture_resource_with_device(device, target);
        state.render_target = null;
    }
}

pub fn execute_render_draw(
    self: *Runtime,
    cmd: model.RenderDrawCommand,
) !DispatchMetrics {
    const draw_count = if (cmd.draw_count > 0) cmd.draw_count else 1;
    const target_width = if (cmd.target_width > 0) cmd.target_width else model.DEFAULT_RENDER_TARGET_WIDTH;
    const target_height = if (cmd.target_height > 0) cmd.target_height else model.DEFAULT_RENDER_TARGET_HEIGHT;
    const vk_format = try vk_resources.texture_format_to_vk(cmd.target_format);

    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
        _ = try vk_upload.flush_queue(self);
    }

    var render_state = RenderState{};
    defer release_render_state(self.device, &render_state);

    // Phase 1: create render target texture
    const encode_start = common_timing.now_ns();

    try ensure_render_target(self, &render_state, target_width, target_height, cmd.target_format);

    // Phase 2: create render pass
    try create_render_pass(self, &render_state, vk_format);

    // Phase 3: create framebuffer
    try create_framebuffer(self, &render_state, target_width, target_height);

    // Phase 4: compile shaders and create graphics pipeline
    try create_graphics_pipeline(self, &render_state, vk_format);

    const encode_end = common_timing.now_ns();
    const setup_ns = common_timing.ns_delta(encode_end, encode_start);

    // Phase 5: record and submit draw commands
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

fn ensure_render_target(
    self: *Runtime,
    state: *RenderState,
    width: u32,
    height: u32,
    format: model.WGPUTextureFormat,
) !void {
    const usage = model.WGPUTextureUsage_RenderAttachment | model.WGPUTextureUsage_CopyDst;
    const texture_spec = model.CopyTextureResource{
        .handle = 0,
        .width = width,
        .height = height,
        .format = format,
        .usage = usage,
        .mip_level = 0,
        .bytes_per_row = 0,
        .rows_per_image = 0,
    };
    state.render_target = try create_render_target_texture(self, texture_spec);
    state.target_width = width;
    state.target_height = height;
}

fn create_render_target_texture(
    self: *Runtime,
    spec: model.CopyTextureResource,
) !vk_resources.TextureResource {
    var image: c.VkImage = VK_NULL_U64;
    var memory: c.VkDeviceMemory = VK_NULL_U64;
    var view: c.VkImageView = VK_NULL_U64;
    const vk_format = try vk_resources.texture_format_to_vk(spec.format);

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
        .usage = c.VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | c.VK_IMAGE_USAGE_TRANSFER_DST_BIT,
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
            .aspectMask = c.VK_IMAGE_ASPECT_COLOR_BIT,
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
        .mip_levels = 1,
        .format = spec.format,
        .usage = spec.usage,
        .layout = c.VK_IMAGE_LAYOUT_UNDEFINED,
    };
}

fn create_render_pass(
    self: *Runtime,
    state: *RenderState,
    vk_format: u32,
) !void {
    var attachment = c.VkAttachmentDescription{
        .flags = 0,
        .format = vk_format,
        .samples = c.VK_SAMPLE_COUNT_1_BIT,
        .loadOp = c.VK_ATTACHMENT_LOAD_OP_CLEAR,
        .storeOp = c.VK_ATTACHMENT_STORE_OP_STORE,
        .stencilLoadOp = c.VK_ATTACHMENT_LOAD_OP_DONT_CARE,
        .stencilStoreOp = c.VK_ATTACHMENT_STORE_OP_DONT_CARE,
        .initialLayout = c.VK_IMAGE_LAYOUT_UNDEFINED,
        .finalLayout = c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
    };

    var color_ref = c.VkAttachmentReference{
        .attachment = 0,
        .layout = c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
    };

    var subpass = c.VkSubpassDescription{
        .flags = 0,
        .pipelineBindPoint = c.VK_PIPELINE_BIND_POINT_GRAPHICS,
        .inputAttachmentCount = 0,
        .pInputAttachments = null,
        .colorAttachmentCount = 1,
        .pColorAttachments = @ptrCast(&color_ref),
        .pResolveAttachments = null,
        .pDepthStencilAttachment = null,
        .preserveAttachmentCount = 0,
        .pPreserveAttachments = null,
    };

    var dependency = c.VkSubpassDependency{
        .srcSubpass = c.VK_SUBPASS_EXTERNAL,
        .dstSubpass = 0,
        .srcStageMask = c.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
        .dstStageMask = c.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
        .srcAccessMask = 0,
        .dstAccessMask = c.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
        .dependencyFlags = 0,
    };

    var render_pass_info = c.VkRenderPassCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .attachmentCount = 1,
        .pAttachments = @ptrCast(&attachment),
        .subpassCount = 1,
        .pSubpasses = @ptrCast(&subpass),
        .dependencyCount = 1,
        .pDependencies = @ptrCast(&dependency),
    };
    try c.check_vk(c.vkCreateRenderPass(self.device, &render_pass_info, null, &state.render_pass));
}

fn create_framebuffer(
    self: *Runtime,
    state: *RenderState,
    width: u32,
    height: u32,
) !void {
    const target = state.render_target orelse return error.InvalidState;

    var fb_info = c.VkFramebufferCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .renderPass = state.render_pass,
        .attachmentCount = 1,
        .pAttachments = @ptrCast(&target.view),
        .width = width,
        .height = height,
        .layers = 1,
    };
    try c.check_vk(c.vkCreateFramebuffer(self.device, &fb_info, null, &state.framebuffer));
}

fn create_graphics_pipeline(
    self: *Runtime,
    state: *RenderState,
    vk_format: u32,
) !void {
    _ = vk_format;

    // Compile WGSL to SPIR-V
    var spirv_buf = try self.allocator.alloc(u8, doe_wgsl.MAX_SPIRV_OUTPUT);
    defer self.allocator.free(spirv_buf);
    const spirv_len = doe_wgsl.translateToSpirv(self.allocator, RENDER_SHADER_WGSL, spirv_buf) catch
        return error.ShaderCompileFailed;
    const spirv_words = try vk_pipeline.words_from_spirv_bytes(self.allocator, spirv_buf[0..spirv_len]);
    defer self.allocator.free(spirv_words);

    // Create shader modules (single module with both entry points)
    var shader_info = c.VkShaderModuleCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .codeSize = spirv_words.len * @sizeOf(u32),
        .pCode = spirv_words.ptr,
    };
    try c.check_vk(c.vkCreateShaderModule(self.device, &shader_info, null, &state.vertex_shader));
    try c.check_vk(c.vkCreateShaderModule(self.device, &shader_info, null, &state.fragment_shader));

    // Pipeline layout (no descriptors needed for passthrough)
    var layout_info = c.VkPipelineLayoutCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .setLayoutCount = 0,
        .pSetLayouts = null,
        .pushConstantRangeCount = 0,
        .pPushConstantRanges = null,
    };
    try c.check_vk(c.vkCreatePipelineLayout(self.device, &layout_info, null, &state.graphics_pipeline_layout));

    // Shader stages
    const stages = [2]c.VkPipelineShaderStageCreateInfo{
        .{
            .sType = c.VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .stage = c.VK_SHADER_STAGE_VERTEX_BIT,
            .module = state.vertex_shader,
            .pName = VERTEX_ENTRY_POINT,
            .pSpecializationInfo = null,
        },
        .{
            .sType = c.VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .stage = c.VK_SHADER_STAGE_FRAGMENT_BIT,
            .module = state.fragment_shader,
            .pName = FRAGMENT_ENTRY_POINT,
            .pSpecializationInfo = null,
        },
    };

    // No vertex input (vertex_index built-in generates geometry)
    var vertex_input = c.VkPipelineVertexInputStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .vertexBindingDescriptionCount = 0,
        .pVertexBindingDescriptions = null,
        .vertexAttributeDescriptionCount = 0,
        .pVertexAttributeDescriptions = null,
    };

    var input_assembly = c.VkPipelineInputAssemblyStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .topology = c.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
        .primitiveRestartEnable = c.VK_FALSE,
    };

    // Dynamic viewport and scissor
    var viewport_state = c.VkPipelineViewportStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .viewportCount = 1,
        .pViewports = null,
        .scissorCount = 1,
        .pScissors = null,
    };

    var rasterization = c.VkPipelineRasterizationStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .depthClampEnable = c.VK_FALSE,
        .rasterizerDiscardEnable = c.VK_FALSE,
        .polygonMode = c.VK_POLYGON_MODE_FILL,
        .cullMode = c.VK_CULL_MODE_NONE,
        .frontFace = c.VK_FRONT_FACE_COUNTER_CLOCKWISE,
        .depthBiasEnable = c.VK_FALSE,
        .depthBiasConstantFactor = 0.0,
        .depthBiasClamp = 0.0,
        .depthBiasSlopeFactor = 0.0,
        .lineWidth = 1.0,
    };

    var multisample = c.VkPipelineMultisampleStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .rasterizationSamples = c.VK_SAMPLE_COUNT_1_BIT,
        .sampleShadingEnable = c.VK_FALSE,
        .minSampleShading = 1.0,
        .pSampleMask = null,
        .alphaToCoverageEnable = c.VK_FALSE,
        .alphaToOneEnable = c.VK_FALSE,
    };

    const COLOR_WRITE_ALL = c.VK_COLOR_COMPONENT_R_BIT |
        c.VK_COLOR_COMPONENT_G_BIT |
        c.VK_COLOR_COMPONENT_B_BIT |
        c.VK_COLOR_COMPONENT_A_BIT;

    var blend_attachment = c.VkPipelineColorBlendAttachmentState{
        .blendEnable = c.VK_FALSE,
        .srcColorBlendFactor = c.VK_BLEND_FACTOR_ONE,
        .dstColorBlendFactor = c.VK_BLEND_FACTOR_ZERO,
        .colorBlendOp = c.VK_BLEND_OP_ADD,
        .srcAlphaBlendFactor = c.VK_BLEND_FACTOR_ONE,
        .dstAlphaBlendFactor = c.VK_BLEND_FACTOR_ZERO,
        .alphaBlendOp = c.VK_BLEND_OP_ADD,
        .colorWriteMask = COLOR_WRITE_ALL,
    };

    var color_blend = c.VkPipelineColorBlendStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .logicOpEnable = c.VK_FALSE,
        .logicOp = c.VK_LOGIC_OP_CLEAR,
        .attachmentCount = 1,
        .pAttachments = @ptrCast(&blend_attachment),
        .blendConstants = .{ 0.0, 0.0, 0.0, 0.0 },
    };

    const dynamic_states = [_]u32{
        c.VK_DYNAMIC_STATE_VIEWPORT,
        c.VK_DYNAMIC_STATE_SCISSOR,
    };
    var dynamic_state = c.VkPipelineDynamicStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .dynamicStateCount = dynamic_states.len,
        .pDynamicStates = &dynamic_states,
    };

    var pipeline_info = c.VkGraphicsPipelineCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .stageCount = 2,
        .pStages = &stages,
        .pVertexInputState = &vertex_input,
        .pInputAssemblyState = &input_assembly,
        .pTessellationState = null,
        .pViewportState = &viewport_state,
        .pRasterizationState = &rasterization,
        .pMultisampleState = &multisample,
        .pDepthStencilState = null,
        .pColorBlendState = &color_blend,
        .pDynamicState = &dynamic_state,
        .layout = state.graphics_pipeline_layout,
        .renderPass = state.render_pass,
        .subpass = 0,
        .basePipelineHandle = VK_NULL_U64,
        .basePipelineIndex = -1,
    };
    try c.check_vk(c.vkCreateGraphicsPipelines(
        self.device,
        VK_NULL_U64,
        1,
        @ptrCast(&pipeline_info),
        null,
        @ptrCast(&state.graphics_pipeline),
    ));
}

fn record_and_submit_draws(
    self: *Runtime,
    state: *RenderState,
    cmd: model.RenderDrawCommand,
    draw_count: u32,
    target_width: u32,
    target_height: u32,
) !void {
    try c.check_vk(c.vkResetCommandPool(self.device, self.command_pool, 0));

    var begin_info = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));

    // Begin render pass
    var clear_value = c.VkClearValue{
        .color = .{ .float32 = .{ 0.0, 0.0, 0.0, 1.0 } },
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
        .clearValueCount = 1,
        .pClearValues = @ptrCast(&clear_value),
    };
    c.vkCmdBeginRenderPass(self.primary_command_buffer, &render_pass_begin, c.VK_SUBPASS_CONTENTS_INLINE);

    // Set dynamic viewport
    const vp_width = cmd.viewport_width orelse @as(f32, @floatFromInt(target_width));
    const vp_height = cmd.viewport_height orelse @as(f32, @floatFromInt(target_height));
    var viewport = c.VkViewport{
        .x = cmd.viewport_x,
        .y = cmd.viewport_y,
        .width = vp_width,
        .height = vp_height,
        .minDepth = cmd.viewport_min_depth,
        .maxDepth = cmd.viewport_max_depth,
    };
    c.vkCmdSetViewport(self.primary_command_buffer, 0, 1, @ptrCast(&viewport));

    // Set dynamic scissor
    const sc_width = cmd.scissor_width orelse target_width;
    const sc_height = cmd.scissor_height orelse target_height;
    var scissor = c.VkRect2D{
        .offset = .{
            .x = @intCast(cmd.scissor_x),
            .y = @intCast(cmd.scissor_y),
        },
        .extent = .{ .width = sc_width, .height = sc_height },
    };
    c.vkCmdSetScissor(self.primary_command_buffer, 0, 1, @ptrCast(&scissor));

    // Bind graphics pipeline
    c.vkCmdBindPipeline(self.primary_command_buffer, c.VK_PIPELINE_BIND_POINT_GRAPHICS, state.graphics_pipeline);

    // Issue draw calls
    const vertex_count = cmd.vertex_count;
    const instance_count = cmd.instance_count;
    const first_vertex = cmd.first_vertex;
    const first_instance = cmd.first_instance;

    if (cmd.index_data != null) {
        try record_indexed_draws(self, cmd, draw_count);
    } else {
        var draw_index: u32 = 0;
        while (draw_index < draw_count) : (draw_index += 1) {
            c.vkCmdDraw(
                self.primary_command_buffer,
                vertex_count,
                instance_count,
                first_vertex,
                first_instance,
            );
        }
    }

    c.vkCmdEndRenderPass(self.primary_command_buffer);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));

    // Submit
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
}

fn record_indexed_draws(
    self: *Runtime,
    cmd: model.RenderDrawCommand,
    draw_count: u32,
) !void {
    const index_data = cmd.index_data orelse return error.InvalidArgument;
    const index_count = cmd.index_count orelse switch (index_data) {
        .uint16 => |data| @as(u32, @intCast(data.len)),
        .uint32 => |data| @as(u32, @intCast(data.len)),
    };

    // Create index buffer with appropriate data
    const index_buffer_size: u64 = switch (index_data) {
        .uint16 => |data| @as(u64, data.len) * @sizeOf(u16),
        .uint32 => |data| @as(u64, data.len) * @sizeOf(u32),
    };
    const index_buffer = try vk_resources.create_host_visible_buffer(
        self,
        index_buffer_size,
        c.VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
    );
    defer vk_resources.destroy_host_visible_buffer(self, index_buffer);

    // Copy index data
    if (index_buffer.mapped) |raw| {
        const dst = @as([*]u8, @ptrCast(raw));
        switch (index_data) {
            .uint16 => |data| @memcpy(dst[0..@intCast(index_buffer_size)], std.mem.sliceAsBytes(data)),
            .uint32 => |data| @memcpy(dst[0..@intCast(index_buffer_size)], std.mem.sliceAsBytes(data)),
        }
    }

    const vk_index_type: u32 = switch (index_data) {
        .uint16 => c.VK_INDEX_TYPE_UINT16,
        .uint32 => c.VK_INDEX_TYPE_UINT32,
    };
    c.vkCmdBindIndexBuffer(self.primary_command_buffer, index_buffer.buffer, 0, vk_index_type);

    var draw_index: u32 = 0;
    while (draw_index < draw_count) : (draw_index += 1) {
        c.vkCmdDrawIndexed(
            self.primary_command_buffer,
            index_count,
            cmd.instance_count,
            cmd.first_index,
            cmd.base_vertex,
            cmd.first_instance,
        );
    }
}
