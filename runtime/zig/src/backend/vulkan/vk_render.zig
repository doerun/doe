// Render pass, graphics pipeline, draw call execution, and render bundle
// replay for the Vulkan backend.
//
// Handles:
//   - VkRenderPass creation for offscreen color attachments
//   - VkGraphicsPipeline creation (vertex + fragment stages, dynamic viewport/scissor)
//   - VkFramebuffer creation bound to a render target image view
//   - Vertex buffer upload and binding
//   - Draw call recording (non-indexed and indexed)
//   - Render bundle replay into active render passes
//   - Render state cleanup

const std = @import("std");
const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const vk_sync = @import("vk_sync.zig");
const vk_formats = @import("vk_formats.zig");

const VK_QUERY_CONTROL_NONE: u32 = 0;
const vk_upload = @import("vk_upload.zig");
const vk_resources = @import("vk_resources.zig");
const vk_pipeline = @import("vk_pipeline.zig");
const model = @import("../../model.zig");
const doe_wgsl = @import("../../doe_wgsl/mod.zig");
const common_timing = @import("../common/timing.zig");
const render_bundle = @import("../../render_bundle.zig");

const VK_NULL_U64 = c.VK_NULL_U64;
const native_runtime = @import("native_runtime.zig");
const Runtime = native_runtime.NativeVulkanRuntime;
const DispatchMetrics = native_runtime.DispatchMetrics;
const VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT: u32 = 0x00000020;
const VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL: u32 = 3;
const VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT: u32 = 0x00000100;
const VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT: u32 = 0x00000200;
const VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT: u32 = 0x00000200;
const VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT: u32 = 0x00000400;
const VK_PRIMITIVE_TOPOLOGY_POINT_LIST: u32 = 0;
const VK_PRIMITIVE_TOPOLOGY_LINE_LIST: u32 = 1;
const VK_PRIMITIVE_TOPOLOGY_LINE_STRIP: u32 = 2;
const VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP: u32 = 4;
const VK_CULL_MODE_FRONT_BIT: u32 = 0x00000001;
const VK_CULL_MODE_BACK_BIT: u32 = 0x00000002;
const VK_FRONT_FACE_CLOCKWISE: u32 = 1;
const VK_COMPARE_OP_LESS: u32 = 1;
const VK_COMPARE_OP_EQUAL: u32 = 2;
const VK_COMPARE_OP_LESS_OR_EQUAL: u32 = 3;
const VK_COMPARE_OP_GREATER: u32 = 4;
const VK_COMPARE_OP_NOT_EQUAL: u32 = 5;
const VK_COMPARE_OP_GREATER_OR_EQUAL: u32 = 6;
const VK_COMPARE_OP_ALWAYS: u32 = 7;
const VK_STENCIL_OP_KEEP: u32 = 0;
const VK_STENCIL_OP_ZERO: u32 = 1;
const VK_STENCIL_OP_REPLACE: u32 = 2;
const VK_STENCIL_OP_INCREMENT_AND_CLAMP: u32 = 3;
const VK_STENCIL_OP_DECREMENT_AND_CLAMP: u32 = 4;
const VK_STENCIL_OP_INVERT: u32 = 5;
const VK_STENCIL_OP_INCREMENT_AND_WRAP: u32 = 6;
const VK_STENCIL_OP_DECREMENT_AND_WRAP: u32 = 7;
const VK_VERTEX_INPUT_RATE_VERTEX: u32 = 0;
const VK_VERTEX_INPUT_RATE_INSTANCE: u32 = 1;
const VK_INDEX_TYPE_UINT16: u32 = 0;
const VK_INDEX_TYPE_UINT32: u32 = 1;
const WGPU_VERTEX_STEP_MODE_INSTANCE: u32 = 0x00000002;
const WGPU_INDEX_FORMAT_UINT16: u32 = 0x00000001;
const WGPU_INDEX_FORMAT_UINT32: u32 = 0x00000002;

const VkStencilOpState = extern struct {
    failOp: u32,
    passOp: u32,
    depthFailOp: u32,
    compareOp: u32,
    compareMask: u32,
    writeMask: u32,
    reference: u32,
};

const VkPipelineDepthStencilStateCreateInfo = extern struct {
    sType: i32,
    pNext: ?*const anyopaque,
    flags: u32,
    depthTestEnable: u32,
    depthWriteEnable: u32,
    depthCompareOp: u32,
    depthBoundsTestEnable: u32,
    stencilTestEnable: u32,
    front: VkStencilOpState,
    back: VkStencilOpState,
    minDepthBounds: f32,
    maxDepthBounds: f32,
};

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
const VK_VERTEX_INPUT_RATE_VERTEX: u32 = 0;
const VK_VERTEX_INPUT_RATE_INSTANCE: u32 = 1;

pub const RenderState = struct {
    render_pass: c.VkRenderPass = VK_NULL_U64,
    framebuffer: c.VkFramebuffer = VK_NULL_U64,
    graphics_pipeline: c.VkPipeline = VK_NULL_U64,
    graphics_pipeline_layout: c.VkPipelineLayout = VK_NULL_U64,
    vertex_shader: c.VkShaderModule = VK_NULL_U64,
    fragment_shader: c.VkShaderModule = VK_NULL_U64,
    render_target: ?vk_resources.TextureResource = null,
    depth_stencil_target: ?vk_resources.TextureResource = null,
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
    if (state.depth_stencil_target) |target| {
        vk_resources.release_texture_resource_with_device(device, target);
        state.depth_stencil_target = null;
    }
}

fn wgpu_primitive_topology_to_vk(topology: u32) u32 {
    return switch (topology) {
        0x00000001 => VK_PRIMITIVE_TOPOLOGY_POINT_LIST,
        0x00000002 => VK_PRIMITIVE_TOPOLOGY_LINE_LIST,
        0x00000003 => VK_PRIMITIVE_TOPOLOGY_LINE_STRIP,
        0x00000005 => VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP,
        else => c.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
    };
}

fn wgpu_front_face_to_vk(front_face: u32) u32 {
    return if (front_face == 0x00000002) VK_FRONT_FACE_CLOCKWISE else c.VK_FRONT_FACE_COUNTER_CLOCKWISE;
}

fn wgpu_cull_mode_to_vk(cull_mode: u32) u32 {
    return switch (cull_mode) {
        0x00000002 => VK_CULL_MODE_FRONT_BIT,
        0x00000003 => VK_CULL_MODE_BACK_BIT,
        else => c.VK_CULL_MODE_NONE,
    };
}

fn wgpu_compare_to_vk(compare: u32) u32 {
    return switch (compare) {
        0x00000002 => VK_COMPARE_OP_LESS,
        0x00000003 => VK_COMPARE_OP_EQUAL,
        0x00000004 => VK_COMPARE_OP_LESS_OR_EQUAL,
        0x00000005 => VK_COMPARE_OP_GREATER,
        0x00000006 => VK_COMPARE_OP_NOT_EQUAL,
        0x00000007 => VK_COMPARE_OP_GREATER_OR_EQUAL,
        0x00000008 => VK_COMPARE_OP_ALWAYS,
        else => c.VK_COMPARE_OP_NEVER,
    };
}

fn wgpu_stencil_op_to_vk(op: u32) u32 {
    return switch (op) {
        0x00000001 => VK_STENCIL_OP_ZERO,
        0x00000002 => VK_STENCIL_OP_REPLACE,
        0x00000003 => VK_STENCIL_OP_INVERT,
        0x00000004 => VK_STENCIL_OP_INCREMENT_AND_CLAMP,
        0x00000005 => VK_STENCIL_OP_DECREMENT_AND_CLAMP,
        0x00000006 => VK_STENCIL_OP_INCREMENT_AND_WRAP,
        0x00000007 => VK_STENCIL_OP_DECREMENT_AND_WRAP,
        else => VK_STENCIL_OP_KEEP,
    };
}

fn format_has_stencil(format: model.WGPUTextureFormat) bool {
    return switch (format) {
        model.WGPUTextureFormat_Stencil8,
        model.WGPUTextureFormat_Depth24PlusStencil8,
        model.WGPUTextureFormat_Depth32FloatStencil8,
        => true,
        else => false,
    };
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

    try ensure_render_target(self, &render_state, target_width, target_height, cmd.target_format, cmd.depth_stencil_format);

    // Phase 2: create render pass
    const has_depth_stencil = cmd.depth_stencil_format != model.WGPUTextureFormat_Undefined;
    const depth_stencil_vk_format = if (has_depth_stencil) try vk_resources.texture_format_to_vk(cmd.depth_stencil_format) else 0;
    try create_render_pass(self, &render_state, vk_format, has_depth_stencil, depth_stencil_vk_format);

    // Phase 3: create framebuffer
    try create_framebuffer(self, &render_state, target_width, target_height);

    // Phase 4: compile shaders and create graphics pipeline
    try create_graphics_pipeline(self, &render_state, vk_format, cmd);

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
    depth_stencil_format: model.WGPUTextureFormat,
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
    if (depth_stencil_format != model.WGPUTextureFormat_Undefined) {
        const depth_texture_spec = model.CopyTextureResource{
            .handle = 0,
            .width = width,
            .height = height,
            .format = depth_stencil_format,
            .usage = model.WGPUTextureUsage_RenderAttachment,
            .mip_level = 0,
            .bytes_per_row = 0,
            .rows_per_image = 0,
        };
        state.depth_stencil_target = try create_render_target_texture(self, depth_texture_spec);
    }
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
    has_depth_stencil: bool,
    depth_stencil_vk_format: u32,
) !void {
    _ = state;
    var attachments = [_]c.VkAttachmentDescription{
        .{
            .flags = 0,
            .format = vk_format,
            .samples = c.VK_SAMPLE_COUNT_1_BIT,
            .loadOp = c.VK_ATTACHMENT_LOAD_OP_CLEAR,
            .storeOp = c.VK_ATTACHMENT_STORE_OP_STORE,
            .stencilLoadOp = c.VK_ATTACHMENT_LOAD_OP_DONT_CARE,
            .stencilStoreOp = c.VK_ATTACHMENT_STORE_OP_DONT_CARE,
            .initialLayout = c.VK_IMAGE_LAYOUT_UNDEFINED,
            .finalLayout = c.VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
        },
        .{
            .flags = 0,
            .format = depth_stencil_vk_format,
            .samples = c.VK_SAMPLE_COUNT_1_BIT,
            .loadOp = c.VK_ATTACHMENT_LOAD_OP_CLEAR,
            .storeOp = c.VK_ATTACHMENT_STORE_OP_DONT_CARE,
            .stencilLoadOp = c.VK_ATTACHMENT_LOAD_OP_CLEAR,
            .stencilStoreOp = c.VK_ATTACHMENT_STORE_OP_DONT_CARE,
            .initialLayout = c.VK_IMAGE_LAYOUT_UNDEFINED,
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

    var dependency = c.VkSubpassDependency{
        .srcSubpass = c.VK_SUBPASS_EXTERNAL,
        .dstSubpass = 0,
        .srcStageMask = c.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
        .dstStageMask = if (has_depth_stencil)
            c.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT |
                VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT |
                VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT
        else
            c.VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
        .srcAccessMask = 0,
        .dstAccessMask = if (has_depth_stencil)
            c.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT |
                VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT |
                VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT
        else
            c.VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
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
    self: *Runtime,
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
    self: *Runtime,
    state: *RenderState,
    vk_format: u32,
    cmd: model.RenderDrawCommand,
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

    var vertex_binding_descriptions: [model.MAX_VERTEX_BUFFERS]c.VkVertexInputBindingDescription = undefined;
    var vertex_attribute_descriptions: [model.MAX_VERTEX_BUFFERS * model.MAX_VERTEX_ATTRIBUTES]c.VkVertexInputAttributeDescription = undefined;
    var vertex_binding_count: usize = 0;
    var vertex_attribute_count: usize = 0;
    if (cmd.vertex_layouts) |layouts| {
        const layout_count = @min(layouts.len, model.MAX_VERTEX_BUFFERS);
        var layout_index: usize = 0;
        while (layout_index < layout_count) : (layout_index += 1) {
            const layout = layouts[layout_index];
            vertex_binding_descriptions[vertex_binding_count] = .{
                .binding = @intCast(layout_index),
                .stride = @intCast(@min(layout.array_stride, @as(u64, std.math.maxInt(u32)))),
                .inputRate = vertex_step_mode_to_vk(layout.step_mode),
            };
            vertex_binding_count += 1;

            const attr_count = @min(@as(usize, layout.attribute_count), model.MAX_VERTEX_ATTRIBUTES);
            var attr_index: usize = 0;
            while (attr_index < attr_count and vertex_attribute_count < vertex_attribute_descriptions.len) : (attr_index += 1) {
                const attr = layout.attributes[attr_index];
                vertex_attribute_descriptions[vertex_attribute_count] = .{
                    .location = attr.shader_location,
                    .binding = @intCast(layout_index),
                    .format = try vk_formats.wgpu_vertex_format_to_vk(attr.format),
                    .offset = @intCast(@min(attr.offset, @as(u64, std.math.maxInt(u32)))),
                };
                vertex_attribute_count += 1;
            }
        }
    }

    var vertex_input = c.VkPipelineVertexInputStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .vertexBindingDescriptionCount = @intCast(vertex_binding_count),
        .pVertexBindingDescriptions = if (vertex_binding_count > 0) vertex_binding_descriptions[0..vertex_binding_count].ptr else null,
        .vertexAttributeDescriptionCount = @intCast(vertex_attribute_count),
        .pVertexAttributeDescriptions = if (vertex_attribute_count > 0) vertex_attribute_descriptions[0..vertex_attribute_count].ptr else null,
    };

    var input_assembly = c.VkPipelineInputAssemblyStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .topology = topology_to_vk(cmd.topology),
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

    // When unclippedDepth is requested and VK_EXT_depth_clip_enable is available,
    // enable depth clamping and chain the depth clip disable struct. Without the
    // extension, fall back to standard depth clipping and log a warning.
    const use_unclipped = cmd.unclipped_depth and self.has_depth_clip_enable_ext;
    if (cmd.unclipped_depth and !self.has_depth_clip_enable_ext) {
        std.debug.print("vk_render: unclippedDepth requested but VK_EXT_depth_clip_enable unavailable; falling back to standard clipping\n", .{});
    }

    var depth_clip_state = c.VkPipelineRasterizationDepthClipStateCreateInfoEXT{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_DEPTH_CLIP_STATE_CREATE_INFO_EXT,
        .pNext = null,
        .flags = 0,
        .depthClipEnable = c.VK_FALSE,
    };
    var rasterization = c.VkPipelineRasterizationStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
        .pNext = if (use_unclipped) @ptrCast(&depth_clip_state) else null,
        .flags = 0,
        .depthClampEnable = if (use_unclipped) c.VK_TRUE else c.VK_FALSE,
        .rasterizerDiscardEnable = c.VK_FALSE,
        .polygonMode = c.VK_POLYGON_MODE_FILL,
        .cullMode = cull_mode_to_vk(cmd.cull_mode),
        .frontFace = front_face_to_vk(cmd.front_face),
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
        .rasterizationSamples = sample_count_to_vk(cmd.sample_count),
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
        .blendEnable = if (cmd.blend_enabled) c.VK_TRUE else c.VK_FALSE,
        .srcColorBlendFactor = blend_factor_to_vk(cmd.color_src_factor),
        .dstColorBlendFactor = blend_factor_to_vk(cmd.color_dst_factor),
        .colorBlendOp = blend_operation_to_vk(cmd.color_operation),
        .srcAlphaBlendFactor = blend_factor_to_vk(cmd.alpha_src_factor),
        .dstAlphaBlendFactor = blend_factor_to_vk(cmd.alpha_dst_factor),
        .alphaBlendOp = blend_operation_to_vk(cmd.alpha_operation),
        .colorWriteMask = color_write_mask_to_vk(cmd.color_write_mask, COLOR_WRITE_ALL),
    };

    var color_blend = c.VkPipelineColorBlendStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .logicOpEnable = c.VK_FALSE,
        .logicOp = c.VK_LOGIC_OP_CLEAR,
        .attachmentCount = 1,
        .pAttachments = @ptrCast(&blend_attachment),
        .blendConstants = cmd.blend_constant,
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
    const has_depth_stencil = cmd.depth_stencil_format != model.WGPUTextureFormat_Undefined;
    const has_stencil = has_depth_stencil and format_has_stencil(cmd.depth_stencil_format);
    var depth_stencil_state = VkPipelineDepthStencilStateCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .depthTestEnable = if (cmd.depth_compare != 0) c.VK_TRUE else c.VK_FALSE,
        .depthWriteEnable = if (cmd.depth_write_enabled) c.VK_TRUE else c.VK_FALSE,
        .depthCompareOp = wgpu_compare_to_vk(cmd.depth_compare),
        .depthBoundsTestEnable = c.VK_FALSE,
        .stencilTestEnable = if (has_stencil) c.VK_TRUE else c.VK_FALSE,
        .front = .{
            .failOp = wgpu_stencil_op_to_vk(cmd.stencil_front_fail_op),
            .passOp = wgpu_stencil_op_to_vk(cmd.stencil_front_pass_op),
            .depthFailOp = wgpu_stencil_op_to_vk(cmd.stencil_front_depth_fail_op),
            .compareOp = wgpu_compare_to_vk(cmd.stencil_front_compare),
            .compareMask = cmd.stencil_read_mask,
            .writeMask = cmd.stencil_write_mask,
            .reference = cmd.stencil_reference,
        },
        .back = .{
            .failOp = wgpu_stencil_op_to_vk(cmd.stencil_back_fail_op),
            .passOp = wgpu_stencil_op_to_vk(cmd.stencil_back_pass_op),
            .depthFailOp = wgpu_stencil_op_to_vk(cmd.stencil_back_depth_fail_op),
            .compareOp = wgpu_compare_to_vk(cmd.stencil_back_compare),
            .compareMask = cmd.stencil_read_mask,
            .writeMask = cmd.stencil_write_mask,
            .reference = cmd.stencil_reference,
        },
        .minDepthBounds = 0.0,
        .maxDepthBounds = 1.0,
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
        .pDepthStencilState = if (has_depth_stencil) @ptrCast(&depth_stencil_state) else null,
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

fn topology_to_vk(topology: u32) u32 {
    return switch (topology) {
        0x00000001 => c.VK_PRIMITIVE_TOPOLOGY_POINT_LIST,
        0x00000002 => c.VK_PRIMITIVE_TOPOLOGY_LINE_LIST,
        0x00000003 => c.VK_PRIMITIVE_TOPOLOGY_LINE_STRIP,
        0x00000005 => c.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP,
        else => c.VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
    };
}

fn vertex_step_mode_to_vk(step_mode: u32) u32 {
    return if (step_mode == model.WGPUVertexStepMode_Instance) VK_VERTEX_INPUT_RATE_INSTANCE else VK_VERTEX_INPUT_RATE_VERTEX;
}

fn front_face_to_vk(front_face: u32) u32 {
    return switch (front_face) {
        0x00000002 => c.VK_FRONT_FACE_CLOCKWISE,
        else => c.VK_FRONT_FACE_COUNTER_CLOCKWISE,
    };
}

fn resolve_vk_buffer_handle(self: *Runtime, handle: ?*anyopaque) ?c.VkBuffer {
    const ptr = handle orelse return null;
    const cb = self.compute_buffers.get(@intFromPtr(ptr)) orelse return null;
    return cb.buffer;
}

fn bind_vertex_buffers(self: *Runtime, bindings: ?[]const model.RenderVertexBinding) void {
    const bs = bindings orelse return;
    for (bs) |binding| {
        const vk_buffer = resolve_vk_buffer_handle(self, binding.handle) orelse continue;
        const buffers = [1]c.VkBuffer{vk_buffer};
        const offsets = [1]u64{binding.offset};
        c.vkCmdBindVertexBuffers(self.primary_command_buffer, binding.slot, 1, &buffers, &offsets);
    }
}

fn cull_mode_to_vk(cull_mode: u32) u32 {
    return switch (cull_mode) {
        0x00000002 => c.VK_CULL_MODE_FRONT_BIT,
        0x00000003 => c.VK_CULL_MODE_BACK_BIT,
        else => c.VK_CULL_MODE_NONE,
    };
}

fn sample_count_to_vk(sample_count: u32) u32 {
    return switch (sample_count) {
        2 => c.VK_SAMPLE_COUNT_2_BIT,
        4 => c.VK_SAMPLE_COUNT_4_BIT,
        8 => c.VK_SAMPLE_COUNT_8_BIT,
        16 => c.VK_SAMPLE_COUNT_16_BIT,
        32 => c.VK_SAMPLE_COUNT_32_BIT,
        64 => c.VK_SAMPLE_COUNT_64_BIT,
        else => c.VK_SAMPLE_COUNT_1_BIT,
    };
}

fn blend_factor_to_vk(factor: u32) u32 {
    return switch (factor) {
        1 => c.VK_BLEND_FACTOR_ZERO,
        2 => c.VK_BLEND_FACTOR_ONE,
        3 => c.VK_BLEND_FACTOR_SRC_COLOR,
        4 => c.VK_BLEND_FACTOR_ONE_MINUS_SRC_COLOR,
        5 => c.VK_BLEND_FACTOR_SRC_ALPHA,
        6 => c.VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA,
        7 => c.VK_BLEND_FACTOR_DST_COLOR,
        8 => c.VK_BLEND_FACTOR_ONE_MINUS_DST_COLOR,
        9 => c.VK_BLEND_FACTOR_DST_ALPHA,
        10 => c.VK_BLEND_FACTOR_ONE_MINUS_DST_ALPHA,
        11 => c.VK_BLEND_FACTOR_SRC_ALPHA_SATURATE,
        12 => c.VK_BLEND_FACTOR_CONSTANT_COLOR,
        13 => c.VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_COLOR,
        14 => c.VK_BLEND_FACTOR_SRC1_COLOR,
        15 => c.VK_BLEND_FACTOR_ONE_MINUS_SRC1_COLOR,
        16 => c.VK_BLEND_FACTOR_SRC1_ALPHA,
        17 => c.VK_BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA,
        else => c.VK_BLEND_FACTOR_ONE,
    };
}

fn blend_operation_to_vk(operation: u32) u32 {
    return switch (operation) {
        2 => c.VK_BLEND_OP_SUBTRACT,
        3 => c.VK_BLEND_OP_REVERSE_SUBTRACT,
        4 => c.VK_BLEND_OP_MIN,
        5 => c.VK_BLEND_OP_MAX,
        else => c.VK_BLEND_OP_ADD,
    };
}

fn color_write_mask_to_vk(write_mask: u32, fallback: u32) u32 {
    var mask: u32 = 0;
    if ((write_mask & 0x1) != 0) mask |= c.VK_COLOR_COMPONENT_R_BIT;
    if ((write_mask & 0x2) != 0) mask |= c.VK_COLOR_COMPONENT_G_BIT;
    if ((write_mask & 0x4) != 0) mask |= c.VK_COLOR_COMPONENT_B_BIT;
    if ((write_mask & 0x8) != 0) mask |= c.VK_COLOR_COMPONENT_A_BIT;
    return if (mask == 0) fallback else mask;
}

fn record_and_submit_draws(
    self: *Runtime,
    state: *RenderState,
    cmd: model.RenderDrawCommand,
    draw_count: u32,
    target_width: u32,
    target_height: u32,
) !void {
    try begin_primary_recording(self);

    var clear_values = [_]c.VkClearValue{
        .{
        .color = .{ .float32 = .{ 0.0, 0.0, 0.0, 1.0 } },
        },
        .{
            .depthStencil = .{ .depth = 1.0, .stencil = 0 },
        },
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
    if (cmd.occlusion_query_pool != 0) {
        if (cmd.occlusion_query_index) |query_index| {
            const query_pool: c.VkQueryPool = @intCast(cmd.occlusion_query_pool);
            c.vkCmdResetQueryPool(self.primary_command_buffer, query_pool, query_index, 1);
            c.vkCmdBeginQuery(self.primary_command_buffer, query_pool, query_index, VK_QUERY_CONTROL_NONE);
        }
    }

    bind_vertex_buffers(self, cmd.vertex_bindings);

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

    if (cmd.vertex_buffer_count > 0) {
        var vk_buffers: [8]c.VkBuffer = [_]c.VkBuffer{VK_NULL_U64} ** 8;
        var vk_offsets: [8]u64 = [_]u64{0} ** 8;
        var bound_count: u32 = 0;
        while (bound_count < cmd.vertex_buffer_count and bound_count < vk_buffers.len) : (bound_count += 1) {
            const handle = cmd.vertex_buffer_handles[bound_count];
            if (handle == 0) break;
            const compute_buffer = self.compute_buffers.get(handle) orelse return error.InvalidArgument;
            vk_buffers[bound_count] = compute_buffer.buffer;
            vk_offsets[bound_count] = cmd.vertex_buffer_offsets[bound_count];
        }
        if (bound_count > 0) {
            c.vkCmdBindVertexBuffers(
                self.primary_command_buffer,
                0,
                bound_count,
                vk_buffers[0..bound_count].ptr,
                vk_offsets[0..bound_count].ptr,
            );
        }
    }

    // Issue draw calls
    const vertex_count = cmd.vertex_count;
    const instance_count = cmd.instance_count;
    const first_vertex = cmd.first_vertex;
    const first_instance = cmd.first_instance;

    if (cmd.index_data != null or cmd.index_binding != null or cmd.index_count != null) {
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
    if (cmd.occlusion_query_pool != 0) {
        if (cmd.occlusion_query_index) |query_index| {
            const query_pool: c.VkQueryPool = @intCast(cmd.occlusion_query_pool);
            c.vkCmdEndQuery(self.primary_command_buffer, query_pool, query_index);
        }
    }

    c.vkCmdEndRenderPass(self.primary_command_buffer);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    try submit_and_wait(self);
}

// Reset the command pool and begin recording on the primary command buffer.
fn begin_primary_recording(self: *Runtime) !void {
    try c.check_vk(c.vkResetCommandPool(self.device, self.command_pool, 0));
    var begin_info = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
}

fn submit_and_wait(self: *Runtime) !void {
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
        var tsi = vk_sync.TimelineSubmitHelper.prepare(&self.timeline_semaphore);
        tsi.patch();
        submit_info.pNext = @ptrCast(&tsi.timeline_info);
        submit_info.signalSemaphoreCount = 1;
        submit_info.pSignalSemaphores = @ptrCast(&tsi.semaphore);
        try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), VK_NULL_U64));
        try self.timeline_semaphore.wait(self.device, tsi.signal_value);
    } else {
        try c.check_vk(c.vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try c.check_vk(c.vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
        try c.check_vk(c.vkWaitForFences(self.device, 1, @ptrCast(&self.fence), c.VK_TRUE, vk_upload.WAIT_TIMEOUT_NS));
    }
}

fn record_indexed_draws(
    self: *Runtime,
    cmd: model.RenderDrawCommand,
    draw_count: u32,
) !void {
    if (cmd.index_binding) |ib| {
        const vk_buf = resolve_vk_buffer_handle(self, ib.handle) orelse return error.InvalidArgument;
        c.vkCmdBindIndexBuffer(self.primary_command_buffer, vk_buf, ib.offset, wgpu_index_format_to_vk(ib.format));
        var draw_index: u32 = 0;
        while (draw_index < draw_count) : (draw_index += 1) {
            c.vkCmdDrawIndexed(
                self.primary_command_buffer,
                cmd.index_count orelse return error.InvalidArgument,
                cmd.instance_count,
                cmd.first_index,
                cmd.base_vertex,
                cmd.first_instance,
            );
        }
        return;
    }

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

// Replay render bundles into a standalone render pass. Creates render target,
// render pass + framebuffer, then replays each bundle's command list.
pub fn execute_render_bundles(
    self: *Runtime,
    bundles: []const *const render_bundle.DoeRenderBundle,
    target_width: u32,
    target_height: u32,
    color_format: u32,
    sample_count: u32,
) !DispatchMetrics {
    if (bundles.len == 0) return .{};
    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0)
        _ = try vk_upload.flush_queue(self);
    const width = if (target_width > 0) target_width else model.DEFAULT_RENDER_TARGET_WIDTH;
    const height = if (target_height > 0) target_height else model.DEFAULT_RENDER_TARGET_HEIGHT;
    const vk_format = try vk_resources.texture_format_to_vk(color_format);
    const pass_sample_count = if (sample_count == 0) @as(u32, 1) else sample_count;
    var state = RenderState{};
    defer release_render_state(self.device, &state);
    const encode_start = common_timing.now_ns();
    try ensure_render_target(self, &state, width, height, color_format);
    try create_render_pass(self, &state, vk_format);
    try create_framebuffer(self, &state, width, height);
    const encode_end = common_timing.now_ns();
    const draw_start = common_timing.now_ns();
    try begin_primary_recording(self);

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
        render_bundle.replay_bundle_vk(b, self.primary_command_buffer, color_format, pass_sample_count) catch |err| {
            std.debug.print("vk_render: bundle replay failed: {}\n", .{err});
            continue;
        };
    }
    c.vkCmdEndRenderPass(self.primary_command_buffer);
    try c.check_vk(c.vkEndCommandBuffer(self.primary_command_buffer));
    try submit_and_wait(self);
    const draw_end = common_timing.now_ns();
    return .{ .encode_ns = common_timing.ns_delta(encode_end, encode_start), .submit_wait_ns = common_timing.ns_delta(draw_end, draw_start) };
}
