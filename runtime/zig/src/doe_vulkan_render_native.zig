// doe_vulkan_render_native.zig — Vulkan-specific texture, sampler, render pipeline,
// and render pass operations for the Doe WebGPU C ABI.
//
// Commands execute immediately (no deferred queue). Render pass draws dispatch
// synchronously via NativeVulkanRuntime.run_render_draw.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");
const types = @import("core/abi/wgpu_types.zig");
const model = @import("model.zig");
const query_native = @import("doe_query_native.zig");
const c = @import("backend/vulkan/vk_constants.zig");
const vk_resources = @import("backend/vulkan/vk_resources.zig");
const NativeVulkanRuntime = native.NativeVulkanRuntime;

const DoeDevice = native.DoeDevice;
const DoeTexture = native.DoeTexture;
const DoeTextureView = native.DoeTextureView;
const DoeSampler = native.DoeSampler;
const DoeRenderPipeline = native.DoeRenderPipeline;
const DoeRenderPass = native.DoeRenderPass;
const DoeBuffer = native.DoeBuffer;

// WebGPU filter values (from the WebGPU spec enum order used by doe_napi.c).
const WGPU_FILTER_NEAREST: u32 = 1;
const WGPU_FILTER_LINEAR: u32 = 2;

// WebGPU address mode values.
const WGPU_ADDRESS_MODE_CLAMP_TO_EDGE: u32 = 1;
const WGPU_ADDRESS_MODE_REPEAT: u32 = 2;
const WGPU_ADDRESS_MODE_MIRROR_REPEAT: u32 = 3;
const WGPU_COMPARE_UNDEFINED: u32 = 0;

// Vulkan address mode constants not already in vk_constants.
const VK_SAMPLER_ADDRESS_MODE_REPEAT: u32 = 0;
const VK_SAMPLER_ADDRESS_MODE_MIRRORED_REPEAT: u32 = 1;
// VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE = 2 (already in vk_constants)
const VK_FILTER_LINEAR: u32 = 1;
const VK_SAMPLER_MIPMAP_MODE_LINEAR: u32 = 1;
const VK_COMPARE_OP_LESS: u32 = 1;
const VK_COMPARE_OP_EQUAL: u32 = 2;
const VK_COMPARE_OP_LESS_OR_EQUAL: u32 = 3;
const VK_COMPARE_OP_GREATER: u32 = 4;
const VK_COMPARE_OP_NOT_EQUAL: u32 = 5;
const VK_COMPARE_OP_GREATER_OR_EQUAL: u32 = 6;
const VK_COMPARE_OP_ALWAYS: u32 = 7;

// ============================================================
// Internal helpers
// ============================================================

fn get_runtime(dev: *DoeDevice) ?*NativeVulkanRuntime {
    return native.device_vk_runtime(dev);
}

fn wgpu_filter_to_vk(filter: u32) u32 {
    return if (filter == WGPU_FILTER_LINEAR) VK_FILTER_LINEAR else c.VK_FILTER_NEAREST;
}

fn wgpu_mipmap_to_vk(filter: u32) u32 {
    return if (filter == WGPU_FILTER_LINEAR) VK_SAMPLER_MIPMAP_MODE_LINEAR else c.VK_SAMPLER_MIPMAP_MODE_NEAREST;
}

fn wgpu_address_to_vk(mode: u32) u32 {
    return switch (mode) {
        WGPU_ADDRESS_MODE_REPEAT => VK_SAMPLER_ADDRESS_MODE_REPEAT,
        WGPU_ADDRESS_MODE_MIRROR_REPEAT => VK_SAMPLER_ADDRESS_MODE_MIRRORED_REPEAT,
        else => c.VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
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

// ============================================================
// Texture
// ============================================================

pub fn vulkan_create_texture(dev: *DoeDevice, tex: *DoeTexture, desc: *const types.WGPUTextureDescriptor) bool {
    const rt = get_runtime(dev) orelse {
        std.debug.print("doe_vulkan_render_native: device has no Vulkan runtime\n", .{});
        return false;
    };

    const handle: u64 = @intFromPtr(tex);
    const tex_resource = vk_resources.create_texture_resource_full(
        rt,
        desc.size.width,
        desc.size.height,
        desc.size.depthOrArrayLayers,
        desc.mipLevelCount,
        desc.sampleCount,
        desc.dimension,
        desc.format,
        @intCast(desc.usage),
    ) catch |err| {
        std.debug.print("doe_vulkan_render_native: create_texture_resource_full failed: {}\n", .{err});
        return false;
    };
    const result = rt.textures.getOrPut(rt.allocator, handle) catch {
        vk_resources.release_texture_resource(rt, tex_resource);
        return false;
    };
    if (result.found_existing) {
        vk_resources.release_texture_resource(rt, result.value_ptr.*);
    }
    result.value_ptr.* = tex_resource;

    tex.vk_id = handle;
    tex.vk_runtime_ref = @ptrCast(rt);
    tex.width = desc.size.width;
    tex.height = desc.size.height;
    tex.format = desc.format;
    tex.dimension = desc.dimension;
    return true;
}

pub fn vulkan_destroy_texture(tex: *DoeTexture) void {
    if (tex.vk_id == 0) return;
    const rt_ptr = tex.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    if (rt.textures.fetchRemove(tex.vk_id)) |entry| {
        vk_resources.release_texture_resource(rt, entry.value);
    }
    tex.vk_id = 0;
    tex.vk_runtime_ref = null;
}

pub fn vulkan_create_texture_view(tex: *DoeTexture, tv: *DoeTextureView, desc: *const types.WGPUTextureViewDescriptor) bool {
    if (tex.vk_id == 0) return false;
    const rt_ptr = tex.vk_runtime_ref orelse return false;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    const texture = rt.textures.get(tex.vk_id) orelse return false;
    const resolved_format: model.WGPUTextureFormat = @intCast(if (desc.format != 0) desc.format else tex.format);
    const resolved_dimension = if (desc.dimension != 0) desc.dimension else if (tex.texture_binding_view_dimension != 0) tex.texture_binding_view_dimension else tex.dimension;
    const resolved_mip_level_count = if (desc.mipLevelCount != 0) desc.mipLevelCount else tex.mip_level_count - desc.baseMipLevel;
    const resolved_array_layer_count = if (desc.arrayLayerCount != 0) desc.arrayLayerCount else if (tex.dimension == model.WGPUTextureDimension_3D) 1 else tex.depth_or_array_layers - desc.baseArrayLayer;
    const vk_view = vk_resources.create_texture_view(
        rt,
        texture,
        resolved_format,
        resolved_dimension,
        desc.baseMipLevel,
        resolved_mip_level_count,
        desc.baseArrayLayer,
        resolved_array_layer_count,
        desc.aspect,
        desc.swizzleR,
        desc.swizzleG,
        desc.swizzleB,
        desc.swizzleA,
    ) catch |err| {
        std.debug.print("doe_vulkan_render_native: create_texture_view failed: {}\n", .{err});
        return false;
    };
    const key: u64 = vk_view;
    const result = rt.textures.getOrPut(rt.allocator, key) catch {
        vk_resources.release_texture_view_with_device(rt.device, vk_view);
        return false;
    };
    result.value_ptr.* = .{
        .image = texture.image,
        .memory = c.VK_NULL_U64,
        .view = vk_view,
        .width = texture.width,
        .height = texture.height,
        .mip_levels = resolved_mip_level_count,
        .format = resolved_format,
        .usage = if (desc.usage != 0) @intCast(desc.usage) else texture.usage,
        .layout = texture.layout,
    };
    tv.handle = @ptrFromInt(vk_view);
    return true;
}

pub fn vulkan_destroy_texture_view(tv: *DoeTextureView) void {
    const handle_ptr = tv.handle orelse return;
    const rt_ptr = tv.tex.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    const key: u64 = @intFromPtr(handle_ptr);
    if (rt.textures.fetchRemove(key)) |entry| {
        vk_resources.release_texture_view_with_device(rt.device, entry.value.view);
    }
    tv.handle = null;
}

// ============================================================
// Sampler
// ============================================================

pub fn vulkan_create_sampler(dev: *DoeDevice, sampler: *DoeSampler, desc: *const types.WGPUSamplerDescriptor) bool {
    const rt = get_runtime(dev) orelse {
        std.debug.print("doe_vulkan_render_native: device has no Vulkan runtime for sampler\n", .{});
        return false;
    };

    var create_info = c.VkSamplerCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .magFilter = wgpu_filter_to_vk(desc.magFilter),
        .minFilter = wgpu_filter_to_vk(desc.minFilter),
        .mipmapMode = wgpu_mipmap_to_vk(desc.mipmapFilter),
        .addressModeU = wgpu_address_to_vk(desc.addressModeU),
        .addressModeV = wgpu_address_to_vk(desc.addressModeV),
        .addressModeW = wgpu_address_to_vk(desc.addressModeW),
        .mipLodBias = 0.0,
        .anisotropyEnable = c.VK_FALSE,
        .maxAnisotropy = 1.0,
        .compareEnable = if (desc.compare != WGPU_COMPARE_UNDEFINED) c.VK_TRUE else c.VK_FALSE,
        .compareOp = if (desc.compare != WGPU_COMPARE_UNDEFINED) wgpu_compare_to_vk(desc.compare) else c.VK_COMPARE_OP_NEVER,
        .minLod = desc.lodMinClamp,
        .maxLod = desc.lodMaxClamp,
        .borderColor = c.VK_BORDER_COLOR_FLOAT_TRANSPARENT_BLACK,
        .unnormalizedCoordinates = c.VK_FALSE,
    };

    var vk_sampler: c.VkSampler = c.VK_NULL_U64;
    c.check_vk(c.vkCreateSampler(rt.device, &create_info, null, &vk_sampler)) catch |err| {
        std.debug.print("doe_vulkan_render_native: vkCreateSampler failed: {}\n", .{err});
        return false;
    };

    // Store as opaque pointer: VkSampler is u64, cast via integer.
    sampler.mtl = @ptrFromInt(vk_sampler);
    sampler.vk_runtime_ref = @ptrCast(rt);

    // Register in runtime's sampler map so compute pipeline descriptor
    // binding can look up the VkSampler by handle.
    const handle: u64 = @intFromPtr(sampler);
    const gop = rt.samplers.getOrPut(rt.allocator, handle) catch {
        std.debug.print("doe_vulkan_render_native: sampler map put failed\n", .{});
        return true;
    };
    if (gop.found_existing and gop.value_ptr.* != c.VK_NULL_U64) {
        // Previous sampler at this handle replaced; Vulkan object already
        // created above, so just overwrite the map entry.
    }
    gop.value_ptr.* = vk_sampler;
    return true;
}

pub fn vulkan_destroy_sampler(sampler: *DoeSampler, rt: *NativeVulkanRuntime) void {
    const handle: u64 = @intFromPtr(sampler);
    // Remove from runtime map (does NOT destroy the VkSampler — we do that below).
    _ = rt.samplers.remove(handle);

    if (sampler.mtl) |ptr| {
        const vk_sampler: c.VkSampler = @intFromPtr(ptr);
        if (vk_sampler != c.VK_NULL_U64) {
            c.vkDestroySampler(rt.device, vk_sampler, null);
        }
        sampler.mtl = null;
    }
    sampler.vk_runtime_ref = null;
}

// ============================================================
// Render pipeline
// ============================================================

// Stores pipeline metadata. The VkPipeline itself is created by run_render_draw
// on first use; mtl_pso remains null for Vulkan.
pub fn vulkan_create_render_pipeline(
    dev: *DoeDevice,
    pip: *DoeRenderPipeline,
    desc: *const anyopaque,
) bool {
    _ = dev;
    // The RenderPipelineDesc type is defined in doe_render_native.zig; we only
    // need the primitive state fields, which share a common layout offset. Cast
    // through the opaque pointer to reach them via a minimal local mirror.
    const RenderStringView = extern struct {
        data: ?[*]const u8,
        length: usize,
    };
    const RenderBlendComponent = extern struct {
        operation: u32,
        srcFactor: u32,
        dstFactor: u32,
    };
    const RenderBlendState = extern struct {
        color: RenderBlendComponent,
        alpha: RenderBlendComponent,
    };
    const RenderColorTargetState = extern struct {
        nextInChain: ?*anyopaque,
        format: u32,
        blend: ?*const RenderBlendState,
        writeMask: u64,
    };
    const RenderFragmentState = extern struct {
        nextInChain: ?*anyopaque,
        module: ?*anyopaque,
        entryPoint: RenderStringView,
        constantCount: usize,
        constants: ?*anyopaque,
        targetCount: usize,
        targets: ?[*]const RenderColorTargetState,
    };
    const RenderPrimitiveState = extern struct {
        nextInChain: ?*anyopaque,
        topology: u32,
        stripIndexFormat: u32,
        frontFace: u32,
        cullMode: u32,
        unclippedDepth: u32,
    };
    const RenderVertexAttribute = extern struct {
        nextInChain: ?*anyopaque,
        format: u32,
        offset: u64,
        shaderLocation: u32,
    };
    const RenderVertexBufferLayout = extern struct {
        nextInChain: ?*anyopaque,
        stepMode: u32,
        arrayStride: u64,
        attributeCount: usize,
        attributes: ?[*]const RenderVertexAttribute,
    };
    const RenderStencilFaceState = extern struct {
        compare: u32,
        failOp: u32,
        depthFailOp: u32,
        passOp: u32,
    };
    const RenderDepthStencilDesc = extern struct {
        nextInChain: ?*anyopaque,
        format: u32,
        depthWriteEnabled: u32,
        depthCompare: u32,
        stencilFront: RenderStencilFaceState,
        stencilBack: RenderStencilFaceState,
        stencilReadMask: u32,
        stencilWriteMask: u32,
        depthBias: i32,
        depthBiasSlopeScale: f32,
        depthBiasClamp: f32,
    };
    const LocalDesc = extern struct {
        nextInChain: ?*anyopaque,
        label_data: ?[*]const u8,
        label_length: usize,
        layout: ?*anyopaque,
        // vertex state (5 pointer-sized fields, skip)
        vertex_nextInChain: ?*anyopaque,
        vertex_module: ?*anyopaque,
        vertex_ep_data: ?[*]const u8,
        vertex_ep_length: usize,
        vertex_constantCount: usize,
        vertex_constants: ?*anyopaque,
        vertex_bufferCount: usize,
        vertex_buffers: ?*anyopaque,
        primitive: RenderPrimitiveState,
        depthStencil: ?*anyopaque,
        // multisample (skip)
        multisample_nextInChain: ?*anyopaque,
        multisample_count: u32,
        multisample_mask: u32,
        multisample_alphaToCoverageEnabled: u32,
        fragment: ?*const RenderFragmentState,
    };
    const d = @as(*const LocalDesc, @ptrCast(@alignCast(desc)));
    pip.topology = d.primitive.topology;
    pip.front_face = d.primitive.frontFace;
    pip.cull_mode = d.primitive.cullMode;
    pip.unclipped_depth = (d.primitive.unclippedDepth != 0);
    pip.sample_count = if (d.multisample_count == 0) 1 else d.multisample_count;
    pip.vertex_buffer_count = 0;
    pip.vertex_attribute_count = 0;
    if (d.vertex_bufferCount > 0 and d.vertex_buffers != null) {
        const buffer_count = @min(d.vertex_bufferCount, native.MAX_VERTEX_BUFFERS);
        const buffers = @as([*]const RenderVertexBufferLayout, @ptrCast(@alignCast(d.vertex_buffers)));
        var buffer_index: usize = 0;
        while (buffer_index < buffer_count) : (buffer_index += 1) {
            const layout = buffers[buffer_index];
            pip.vertex_buffer_strides[buffer_index] = layout.arrayStride;
            pip.vertex_step_modes[buffer_index] = layout.stepMode;
            pip.vertex_buffer_count += 1;
            if (layout.attributes) |attrs| {
                const available = native.MAX_VERTEX_ATTRIBUTES - pip.vertex_attribute_count;
                const attr_count = @min(layout.attributeCount, available);
                var attr_index: usize = 0;
                while (attr_index < attr_count) : (attr_index += 1) {
                    const dst = pip.vertex_attribute_count;
                    const attr = attrs[attr_index];
                    pip.vertex_attribute_formats[dst] = attr.format;
                    pip.vertex_attribute_offsets[dst] = attr.offset;
                    pip.vertex_attribute_locations[dst] = attr.shaderLocation;
                    pip.vertex_attribute_buffer_slots[dst] = @intCast(buffer_index);
                    pip.vertex_attribute_count += 1;
                }
            }
        }
    }

    if (d.depthStencil) |ds_raw| {
        const ds = @as(*const RenderDepthStencilDesc, @ptrCast(@alignCast(ds_raw)));
        pip.depth_stencil_format = ds.format;
        pip.depth_compare = ds.depthCompare;
        pip.depth_write_enabled = ds.depthWriteEnabled != 0;
        pip.stencil_front_compare = ds.stencilFront.compare;
        pip.stencil_front_fail_op = ds.stencilFront.failOp;
        pip.stencil_front_depth_fail_op = ds.stencilFront.depthFailOp;
        pip.stencil_front_pass_op = ds.stencilFront.passOp;
        pip.stencil_back_compare = ds.stencilBack.compare;
        pip.stencil_back_fail_op = ds.stencilBack.failOp;
        pip.stencil_back_depth_fail_op = ds.stencilBack.depthFailOp;
        pip.stencil_back_pass_op = ds.stencilBack.passOp;
        pip.stencil_read_mask = ds.stencilReadMask;
        pip.stencil_write_mask = ds.stencilWriteMask;
    }

    if (d.fragment) |frag| {
        if (frag.targetCount > 0 and frag.targets != null) {
            const target0 = frag.targets.?[0];
            pip.color_write_mask = @intCast(target0.writeMask);
            if (target0.blend) |blend| {
                pip.blend_enabled = true;
                pip.color_operation = blend.color.operation;
                pip.color_src_factor = blend.color.srcFactor;
                pip.color_dst_factor = blend.color.dstFactor;
                pip.alpha_operation = blend.alpha.operation;
                pip.alpha_src_factor = blend.alpha.srcFactor;
                pip.alpha_dst_factor = blend.alpha.dstFactor;
            }
        }
    }

    // mtl_pso intentionally left null: Vulkan draw is routed through run_render_draw.
    pip.mtl_pso = null;
    return true;
}

// ============================================================
// Render pass draw operations
// ============================================================

pub fn vulkan_render_pass_draw(
    pass: *DoeRenderPass,
    vertex_count: u32,
    instance_count: u32,
    first_vertex: u32,
    first_instance: u32,
) void {
    const rt = get_runtime(pass.enc.dev) orelse {
        std.debug.print("doe_vulkan_render_native: render pass draw: no Vulkan runtime\n", .{});
        return;
    };
    const occlusion_qs = if (pass.occlusion_query_active and pass.occlusion_query_set != null)
        native.cast(query_native.DoeQuerySet, pass.occlusion_query_set)
    else
        null;

    const pip_unclipped = if (pass.pipeline) |pip| pip.unclipped_depth else false;
    var vertex_bindings: [model.MAX_VERTEX_BUFFERS]model.RenderVertexBinding = undefined;
    var vertex_binding_count: usize = 0;
    var slot: usize = 0;
    while (slot < pass.vertex_buffers.len) : (slot += 1) {
        if (pass.vertex_buffers[slot]) |buf| {
            if (buf.vk_id != 0) {
                vertex_bindings[vertex_binding_count] = .{
                    .slot = @intCast(slot),
                    .handle = @ptrCast(buf),
                    .offset = pass.vertex_buffer_offsets[slot],
                };
                vertex_binding_count += 1;
            }
        }
    }

    var cmd = model.RenderDrawCommand{
        .draw_count = 1,
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .first_vertex = first_vertex,
        .first_instance = first_instance,
        .viewport_x = pass.viewport_x,
        .viewport_y = pass.viewport_y,
        .viewport_width = pass.viewport_width,
        .viewport_height = pass.viewport_height,
        .viewport_min_depth = pass.viewport_min_depth,
        .viewport_max_depth = pass.viewport_max_depth,
        .scissor_x = pass.scissor_x,
        .scissor_y = pass.scissor_y,
        .scissor_width = pass.scissor_width,
        .scissor_height = pass.scissor_height,
        .vertex_layout_count = if (pass.pipeline) |pip| pip.vertex_layout_count else 0,
        .vertex_layouts = if (pass.pipeline) |pip| if (pip.vertex_layout_count > 0) pip.vertex_layouts[0..@intCast(pip.vertex_layout_count)] else null else null,
        .vertex_binding_count = @intCast(vertex_binding_count),
        .vertex_bindings = if (vertex_binding_count > 0) vertex_bindings[0..vertex_binding_count] else null,
        .index_binding = null,
        .topology = if (pass.pipeline) |pip| pip.topology else 0x00000004,
        .front_face = if (pass.pipeline) |pip| pip.front_face else 0x00000001,
        .cull_mode = if (pass.pipeline) |pip| pip.cull_mode else 0x00000001,
        .blend_enabled = if (pass.pipeline) |pip| pip.blend_enabled else false,
        .color_operation = if (pass.pipeline) |pip| pip.color_operation else 1,
        .color_src_factor = if (pass.pipeline) |pip| pip.color_src_factor else 2,
        .color_dst_factor = if (pass.pipeline) |pip| pip.color_dst_factor else 1,
        .alpha_operation = if (pass.pipeline) |pip| pip.alpha_operation else 1,
        .alpha_src_factor = if (pass.pipeline) |pip| pip.alpha_src_factor else 2,
        .alpha_dst_factor = if (pass.pipeline) |pip| pip.alpha_dst_factor else 1,
        .color_write_mask = if (pass.pipeline) |pip| pip.color_write_mask else 0xF,
        .sample_count = if (pass.pipeline) |pip| pip.sample_count else 1,
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .occlusion_query_pool = if (occlusion_qs) |qs| qs.vk_query_pool else 0,
        .occlusion_query_index = if (occlusion_qs != null) pass.occlusion_query_index else null,
        .topology = if (pass.pipeline) |pip| pip.topology else 0x00000004,
        .front_face = if (pass.pipeline) |pip| pip.front_face else 0x00000001,
        .cull_mode = if (pass.pipeline) |pip| pip.cull_mode else 0x00000001,
        .depth_stencil_format = if (pass.pipeline) |pip| pip.depth_stencil_format else 0,
        .depth_compare = if (pass.pipeline) |pip| pip.depth_compare else pass.depth_compare,
        .depth_write_enabled = if (pass.pipeline) |pip| pip.depth_write_enabled else pass.depth_write_enabled,
        .stencil_front_compare = if (pass.pipeline) |pip| pip.stencil_front_compare else 0x00000008,
        .stencil_front_fail_op = if (pass.pipeline) |pip| pip.stencil_front_fail_op else 0,
        .stencil_front_depth_fail_op = if (pass.pipeline) |pip| pip.stencil_front_depth_fail_op else 0,
        .stencil_front_pass_op = if (pass.pipeline) |pip| pip.stencil_front_pass_op else 0,
        .stencil_back_compare = if (pass.pipeline) |pip| pip.stencil_back_compare else 0x00000008,
        .stencil_back_fail_op = if (pass.pipeline) |pip| pip.stencil_back_fail_op else 0,
        .stencil_back_depth_fail_op = if (pass.pipeline) |pip| pip.stencil_back_depth_fail_op else 0,
        .stencil_back_pass_op = if (pass.pipeline) |pip| pip.stencil_back_pass_op else 0,
        .stencil_read_mask = if (pass.pipeline) |pip| pip.stencil_read_mask else 0xFFFF_FFFF,
        .stencil_write_mask = if (pass.pipeline) |pip| pip.stencil_write_mask else 0xFFFF_FFFF,
        .unclipped_depth = pip_unclipped,
    };
    if (pass.pipeline) |pip| {
        cmd.vertex_layout_count = pip.vertex_buffer_count;
        cmd.vertex_buffer_strides = pip.vertex_buffer_strides;
        cmd.vertex_step_modes = pip.vertex_step_modes;
        cmd.vertex_attribute_count = pip.vertex_attribute_count;
        cmd.vertex_attribute_formats = pip.vertex_attribute_formats;
        cmd.vertex_attribute_offsets = pip.vertex_attribute_offsets;
        cmd.vertex_attribute_locations = pip.vertex_attribute_locations;
        cmd.vertex_attribute_buffer_slots = pip.vertex_attribute_buffer_slots;
    }
    var bound_vertex_count: u32 = 0;
    var slot: usize = 0;
    while (slot < native.MAX_VERTEX_BUFFERS) : (slot += 1) {
        if (pass.vertex_buffers[slot]) |buffer| {
            cmd.vertex_buffer_handles[slot] = buffer.vk_id;
            cmd.vertex_buffer_offsets[slot] = pass.vertex_buffer_offsets[slot];
            bound_vertex_count = @intCast(slot + 1);
        }
    }
    cmd.vertex_buffer_count = bound_vertex_count;
    if (pass.index_buffer) |buffer| {
        cmd.index_buffer_handle = buffer.vk_id;
        cmd.index_buffer_offset = pass.index_offset;
        cmd.index_format = pass.index_format;
    }

    _ = rt.run_render_draw(cmd) catch |err| {
        std.debug.print("doe_vulkan_render_native: run_render_draw failed: {}\n", .{err});
    };
}

pub fn vulkan_render_pass_draw_indexed(
    pass: *DoeRenderPass,
    index_count: u32,
    instance_count: u32,
    first_index: u32,
    base_vertex: i32,
    first_instance: u32,
) void {
    const rt = get_runtime(pass.enc.dev) orelse {
        std.debug.print("doe_vulkan_render_native: render pass draw_indexed: no Vulkan runtime\n", .{});
        return;
    };
    const occlusion_qs = if (pass.occlusion_query_active and pass.occlusion_query_set != null)
        native.cast(query_native.DoeQuerySet, pass.occlusion_query_set)
    else
        null;

    const pip_unclipped = if (pass.pipeline) |pip| pip.unclipped_depth else false;
    var vertex_bindings: [model.MAX_VERTEX_BUFFERS]model.RenderVertexBinding = undefined;
    var vertex_binding_count: usize = 0;
    var slot: usize = 0;
    while (slot < pass.vertex_buffers.len) : (slot += 1) {
        if (pass.vertex_buffers[slot]) |buf| {
            if (buf.vk_id != 0) {
                vertex_bindings[vertex_binding_count] = .{
                    .slot = @intCast(slot),
                    .handle = @ptrCast(buf),
                    .offset = pass.vertex_buffer_offsets[slot],
                };
                vertex_binding_count += 1;
            }
        }
    }

    var cmd = model.RenderDrawCommand{
        .draw_count = 1,
        .vertex_count = 0,
        .instance_count = instance_count,
        .first_vertex = 0,
        .first_instance = first_instance,
        .index_count = index_count,
        .first_index = first_index,
        .base_vertex = base_vertex,
        .viewport_x = pass.viewport_x,
        .viewport_y = pass.viewport_y,
        .viewport_width = pass.viewport_width,
        .viewport_height = pass.viewport_height,
        .viewport_min_depth = pass.viewport_min_depth,
        .viewport_max_depth = pass.viewport_max_depth,
        .scissor_x = pass.scissor_x,
        .scissor_y = pass.scissor_y,
        .scissor_width = pass.scissor_width,
        .scissor_height = pass.scissor_height,
        .vertex_layout_count = if (pass.pipeline) |pip| pip.vertex_layout_count else 0,
        .vertex_layouts = if (pass.pipeline) |pip| if (pip.vertex_layout_count > 0) pip.vertex_layouts[0..@intCast(pip.vertex_layout_count)] else null else null,
        .vertex_binding_count = @intCast(vertex_binding_count),
        .vertex_bindings = if (vertex_binding_count > 0) vertex_bindings[0..vertex_binding_count] else null,
        .index_binding = if (pass.index_buffer) |idx_buf| .{
            .handle = @ptrCast(idx_buf),
            .offset = pass.index_offset,
            .size = pass.index_buffer_size,
            .format = pass.index_format,
        } else null,
        .topology = if (pass.pipeline) |pip| pip.topology else 0x00000004,
        .front_face = if (pass.pipeline) |pip| pip.front_face else 0x00000001,
        .cull_mode = if (pass.pipeline) |pip| pip.cull_mode else 0x00000001,
        .blend_enabled = if (pass.pipeline) |pip| pip.blend_enabled else false,
        .color_operation = if (pass.pipeline) |pip| pip.color_operation else 1,
        .color_src_factor = if (pass.pipeline) |pip| pip.color_src_factor else 2,
        .color_dst_factor = if (pass.pipeline) |pip| pip.color_dst_factor else 1,
        .alpha_operation = if (pass.pipeline) |pip| pip.alpha_operation else 1,
        .alpha_src_factor = if (pass.pipeline) |pip| pip.alpha_src_factor else 2,
        .alpha_dst_factor = if (pass.pipeline) |pip| pip.alpha_dst_factor else 1,
        .color_write_mask = if (pass.pipeline) |pip| pip.color_write_mask else 0xF,
        .sample_count = if (pass.pipeline) |pip| pip.sample_count else 1,
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .occlusion_query_pool = if (occlusion_qs) |qs| qs.vk_query_pool else 0,
        .occlusion_query_index = if (occlusion_qs != null) pass.occlusion_query_index else null,
        .topology = if (pass.pipeline) |pip| pip.topology else 0x00000004,
        .front_face = if (pass.pipeline) |pip| pip.front_face else 0x00000001,
        .cull_mode = if (pass.pipeline) |pip| pip.cull_mode else 0x00000001,
        .depth_stencil_format = if (pass.pipeline) |pip| pip.depth_stencil_format else 0,
        .depth_compare = if (pass.pipeline) |pip| pip.depth_compare else pass.depth_compare,
        .depth_write_enabled = if (pass.pipeline) |pip| pip.depth_write_enabled else pass.depth_write_enabled,
        .stencil_front_compare = if (pass.pipeline) |pip| pip.stencil_front_compare else 0x00000008,
        .stencil_front_fail_op = if (pass.pipeline) |pip| pip.stencil_front_fail_op else 0,
        .stencil_front_depth_fail_op = if (pass.pipeline) |pip| pip.stencil_front_depth_fail_op else 0,
        .stencil_front_pass_op = if (pass.pipeline) |pip| pip.stencil_front_pass_op else 0,
        .stencil_back_compare = if (pass.pipeline) |pip| pip.stencil_back_compare else 0x00000008,
        .stencil_back_fail_op = if (pass.pipeline) |pip| pip.stencil_back_fail_op else 0,
        .stencil_back_depth_fail_op = if (pass.pipeline) |pip| pip.stencil_back_depth_fail_op else 0,
        .stencil_back_pass_op = if (pass.pipeline) |pip| pip.stencil_back_pass_op else 0,
        .stencil_read_mask = if (pass.pipeline) |pip| pip.stencil_read_mask else 0xFFFF_FFFF,
        .stencil_write_mask = if (pass.pipeline) |pip| pip.stencil_write_mask else 0xFFFF_FFFF,
        .unclipped_depth = pip_unclipped,
    };
    if (pass.pipeline) |pip| {
        cmd.vertex_layout_count = pip.vertex_buffer_count;
        cmd.vertex_buffer_strides = pip.vertex_buffer_strides;
        cmd.vertex_step_modes = pip.vertex_step_modes;
        cmd.vertex_attribute_count = pip.vertex_attribute_count;
        cmd.vertex_attribute_formats = pip.vertex_attribute_formats;
        cmd.vertex_attribute_offsets = pip.vertex_attribute_offsets;
        cmd.vertex_attribute_locations = pip.vertex_attribute_locations;
        cmd.vertex_attribute_buffer_slots = pip.vertex_attribute_buffer_slots;
    }
    var bound_vertex_count: u32 = 0;
    var slot: usize = 0;
    while (slot < native.MAX_VERTEX_BUFFERS) : (slot += 1) {
        if (pass.vertex_buffers[slot]) |buffer| {
            cmd.vertex_buffer_handles[slot] = buffer.vk_id;
            cmd.vertex_buffer_offsets[slot] = pass.vertex_buffer_offsets[slot];
            bound_vertex_count = @intCast(slot + 1);
        }
    }
    cmd.vertex_buffer_count = bound_vertex_count;
    if (pass.index_buffer) |buffer| {
        cmd.index_buffer_handle = buffer.vk_id;
        cmd.index_buffer_offset = pass.index_offset;
        cmd.index_format = pass.index_format;
    }

    _ = rt.run_render_draw(cmd) catch |err| {
        std.debug.print("doe_vulkan_render_native: run_render_draw (indexed) failed: {}\n", .{err});
    };
}

// Render pass end is a no-op for the Vulkan path: each draw executes
// immediately and there is no deferred command buffer to flush here.
pub fn vulkan_render_pass_end(pass: *DoeRenderPass) void {
    _ = pass;
}
