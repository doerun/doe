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

// WebGPU filter values (from the WebGPU spec enum order used by doe_napi.c).
const WGPU_FILTER_NEAREST: u32 = 1;
const WGPU_FILTER_LINEAR: u32 = 2;

// WebGPU address mode values.
const WGPU_ADDRESS_MODE_CLAMP_TO_EDGE: u32 = 1;
const WGPU_ADDRESS_MODE_REPEAT: u32 = 2;
const WGPU_ADDRESS_MODE_MIRROR_REPEAT: u32 = 3;

// Vulkan address mode constants not already in vk_constants.
const VK_SAMPLER_ADDRESS_MODE_REPEAT: u32 = 0;
const VK_SAMPLER_ADDRESS_MODE_MIRRORED_REPEAT: u32 = 1;
// VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE = 2 (already in vk_constants)
const VK_FILTER_LINEAR: u32 = 1;
const VK_SAMPLER_MIPMAP_MODE_LINEAR: u32 = 1;

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
        .compareEnable = c.VK_FALSE,
        .compareOp = c.VK_COMPARE_OP_NEVER,
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
    const RenderPrimitiveState = extern struct {
        nextInChain: ?*anyopaque,
        topology: u32,
        stripIndexFormat: u32,
        frontFace: u32,
        cullMode: u32,
        unclippedDepth: u32,
    };
    const RenderDepthStencilDesc = extern struct {
        nextInChain: ?*anyopaque,
        format: u32,
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
        fragment: ?*anyopaque,
    };
    const d = @as(*const LocalDesc, @ptrCast(@alignCast(desc)));
    pip.topology = d.primitive.topology;
    pip.front_face = d.primitive.frontFace;
    pip.cull_mode = d.primitive.cullMode;
    pip.unclipped_depth = (d.primitive.unclippedDepth != 0);

    if (d.depthStencil) |ds_raw| {
        const ds = @as(*const RenderDepthStencilDesc, @ptrCast(@alignCast(ds_raw)));
        _ = ds; // depth_compare stays 0 for Vulkan v0; run_render_draw owns pipeline
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

    const cmd = model.RenderDrawCommand{
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
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .occlusion_query_pool = if (occlusion_qs) |qs| qs.vk_query_pool else 0,
        .occlusion_query_index = if (occlusion_qs != null) pass.occlusion_query_index else null,
        .unclipped_depth = pip_unclipped,
    };

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

    const cmd = model.RenderDrawCommand{
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
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .occlusion_query_pool = if (occlusion_qs) |qs| qs.vk_query_pool else 0,
        .occlusion_query_index = if (occlusion_qs != null) pass.occlusion_query_index else null,
        .unclipped_depth = pip_unclipped,
    };

    _ = rt.run_render_draw(cmd) catch |err| {
        std.debug.print("doe_vulkan_render_native: run_render_draw (indexed) failed: {}\n", .{err});
    };
}

// Render pass end is a no-op for the Vulkan path: each draw executes
// immediately and there is no deferred command buffer to flush here.
pub fn vulkan_render_pass_end(pass: *DoeRenderPass) void {
    _ = pass;
}
