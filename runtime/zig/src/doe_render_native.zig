// doe_render_native.zig — Texture, Sampler, Render Pipeline, and Render Pass
// C ABI exports for the Doe native Metal backend. Sharded from doe_wgpu_native.zig.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const ERR_CAP = native.ERR_CAP;
const label_store = native.label_store;

const DoeDevice = native.DoeDevice;
const DoeTexture = native.DoeTexture;
const DoeTextureView = native.DoeTextureView;
const DoeSampler = native.DoeSampler;
const DoeShaderModule = native.DoeShaderModule;
const DoePipelineLayout = native.DoePipelineLayout;
const DoeRenderPipeline = native.DoeRenderPipeline;
const DoeRenderPass = native.DoeRenderPass;
const DoeCommandEncoder = native.DoeCommandEncoder;

// Metal bridge externs (resolved at link time from metal_bridge.m).
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_device_new_texture(device: ?*anyopaque, width: u32, height: u32, depth_or_array_layers: u32, mip_levels: u32, sample_count: u32, pixel_format: u32, usage: u32, dimension: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_texture_new_view(texture: ?*anyopaque, pixel_format: u32, dimension: u32, base_mip_level: u32, mip_level_count: u32, base_array_layer: u32, array_layer_count: u32, swizzle_r: u32, swizzle_g: u32, swizzle_b: u32, swizzle_a: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_sampler(device: ?*anyopaque, min_f: u32, mag_f: u32, mip_f: u32, addr_u: u32, addr_v: u32, addr_w: u32, lod_min: f32, lod_max: f32, max_aniso: u16) callconv(.c) ?*anyopaque;
extern fn metal_bridge_library_new_function(library: ?*anyopaque, name: [*:0]const u8) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_render_pipeline_full(device: ?*anyopaque, vertex_function: ?*anyopaque, fragment_function: ?*anyopaque, pixel_format: u32, depth_format: u32, sample_count: u32, blend_enabled: c_int, color_operation: u32, color_src_factor: u32, color_dst_factor: u32, alpha_operation: u32, alpha_src_factor: u32, alpha_dst_factor: u32, color_write_mask: u32, vertex_layouts: ?[*]const MtlVertexBufferLayout, vertex_layout_count: u32, vertex_attributes: ?[*]const MtlVertexAttributeDesc, vertex_attribute_count: u32, error_buf: ?[*]u8, error_cap: usize) callconv(.c) ?*anyopaque;

// Metal vertex descriptor types (mirrors metal_bridge_decls.zig MetalVertexBufferLayout/MetalVertexAttributeDesc).
const MtlVertexBufferLayout = extern struct {
    array_stride: u64,
    step_mode: u32,
    buffer_index: u32,
};
const MtlVertexAttributeDesc = extern struct {
    format: u32,
    offset: u64,
    shader_location: u32,
    buffer_index: u32,
};

// Mirror of the C structs passed by doe_napi.c for WGPURenderPipelineDescriptor.
// Must match the C layout exactly (extern struct, same field order and types).
const RenderStringView = extern struct { data: ?[*]const u8, length: usize };
const RenderColorTargetState = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
    blend: ?*anyopaque,
    writeMask: u64,
};
const RenderVertexState = extern struct {
    nextInChain: ?*anyopaque,
    module: ?*anyopaque,
    entryPoint: RenderStringView,
    constantCount: usize,
    constants: ?*anyopaque,
    bufferCount: usize,
    buffers: ?*anyopaque,
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
const RenderMultisampleState = extern struct {
    nextInChain: ?*anyopaque,
    count: u32,
    mask: u32,
    alphaToCoverageEnabled: u32,
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
const RenderDepthStencilDesc = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
};
const RenderPipelineDesc = extern struct {
    nextInChain: ?*anyopaque,
    label: RenderStringView,
    layout: ?*anyopaque,
    vertex: RenderVertexState,
    primitive: RenderPrimitiveState,
    depthStencil: ?*anyopaque,
    multisample: RenderMultisampleState,
    fragment: ?*const RenderFragmentState,
};

const DEFAULT_MAX_DRAW_COUNT: u64 = 50_000_000;

fn reserve_render_draw(pass: *DoeRenderPass) bool {
    if (pass.recorded_draw_count >= pass.max_draw_count) {
        std.log.err("doe: render pass draw rejected: maxDrawCount={} exhausted", .{pass.max_draw_count});
        return false;
    }
    pass.recorded_draw_count += 1;
    return true;
}

// ============================================================
// Texture
// ============================================================

pub export fn doeNativeDeviceCreateTexture(dev_raw: ?*anyopaque, desc: ?*const types.WGPUTextureDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const tex = make(DoeTexture) orelse return null;
    tex.* = .{
        .format = d.format,
        .width = d.size.width,
        .height = d.size.height,
        .depth_or_array_layers = d.size.depthOrArrayLayers,
        .dimension = d.dimension,
        .mip_level_count = d.mipLevelCount,
        .sample_count = d.sampleCount,
        .usage = d.usage,
        .texture_binding_view_dimension = d.textureBindingViewDimension,
        .view_format_count = d.viewFormatCount,
    };
    if (dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        if (!vk_render.vulkan_create_texture(dev, tex, d)) {
            alloc.destroy(tex);
            return null;
        }
        const result = toOpaque(tex);
        label_store.set(result, d.label.data, d.label.length);
        return result;
    }
    // Metal path.
    const mtl = metal_bridge_device_new_texture(dev.mtl_device, d.size.width, d.size.height, d.size.depthOrArrayLayers, d.mipLevelCount, d.sampleCount, d.format, @intCast(d.usage), d.dimension) orelse {
        alloc.destroy(tex);
        return null;
    };
    tex.mtl = mtl;
    const result = toOpaque(tex);
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeTextureCreateView(tex_raw: ?*anyopaque, desc: ?*const types.WGPUTextureViewDescriptor) callconv(.c) ?*anyopaque {
    const tex = cast(DoeTexture, tex_raw) orelse return null;
    const tv = make(DoeTextureView) orelse return null;
    const d = desc orelse &types.WGPUTextureViewDescriptor{
        .nextInChain = null,
        .label = .{ .data = null, .length = 0 },
        .format = tex.format,
        .dimension = if (tex.texture_binding_view_dimension != 0) tex.texture_binding_view_dimension else tex.dimension,
        .baseMipLevel = 0,
        .mipLevelCount = tex.mip_level_count,
        .baseArrayLayer = 0,
        .arrayLayerCount = tex.depth_or_array_layers,
        .aspect = types.WGPUTextureAspect_All,
        .usage = tex.usage,
        .swizzleR = types.WGPUTextureComponentSwizzle_Red,
        .swizzleG = types.WGPUTextureComponentSwizzle_Green,
        .swizzleB = types.WGPUTextureComponentSwizzle_Blue,
        .swizzleA = types.WGPUTextureComponentSwizzle_Alpha,
    };
    const resolved_format = if (d.format != 0) d.format else tex.format;
    const resolved_dimension = if (d.dimension != 0) d.dimension else if (tex.texture_binding_view_dimension != 0) tex.texture_binding_view_dimension else tex.dimension;
    const resolved_mip_level_count = if (d.mipLevelCount != 0) d.mipLevelCount else tex.mip_level_count - d.baseMipLevel;
    const resolved_array_layer_count = if (d.arrayLayerCount != 0) d.arrayLayerCount else if (tex.dimension == types.WGPUTextureDimension_3D) 1 else tex.depth_or_array_layers - d.baseArrayLayer;
    const resolved_usage = if (d.usage != 0) d.usage else tex.usage;
    const resolved_swizzle_r = if (d.swizzleR != 0) d.swizzleR else types.WGPUTextureComponentSwizzle_Red;
    const resolved_swizzle_g = if (d.swizzleG != 0) d.swizzleG else types.WGPUTextureComponentSwizzle_Green;
    const resolved_swizzle_b = if (d.swizzleB != 0) d.swizzleB else types.WGPUTextureComponentSwizzle_Blue;
    const resolved_swizzle_a = if (d.swizzleA != 0) d.swizzleA else types.WGPUTextureComponentSwizzle_Alpha;
    if (tex.mtl == null and tex.vk_id != 0) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        if (!vk_render.vulkan_create_texture_view(tex, tv, d)) {
            alloc.destroy(tv);
            return null;
        }
    }
    const view_handle = if (tex.mtl != null)
        metal_bridge_texture_new_view(
            tex.mtl,
            resolved_format,
            resolved_dimension,
            d.baseMipLevel,
            resolved_mip_level_count,
            d.baseArrayLayer,
            resolved_array_layer_count,
            resolved_swizzle_r,
            resolved_swizzle_g,
            resolved_swizzle_b,
            resolved_swizzle_a,
        )
    else
        tv.handle;
    tv.* = .{
        .tex = tex,
        .handle = if (view_handle) |handle| handle else tex.mtl,
        .format = resolved_format,
        .dimension = resolved_dimension,
        .base_mip_level = d.baseMipLevel,
        .mip_level_count = resolved_mip_level_count,
        .base_array_layer = d.baseArrayLayer,
        .array_layer_count = resolved_array_layer_count,
        .aspect = if (d.aspect != 0) d.aspect else types.WGPUTextureAspect_All,
        .usage = resolved_usage,
    };
    const result = toOpaque(tv);
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeTextureRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeTexture, raw)) |t| {
        label_store.remove(raw);
        if (t.vk_id != 0) {
            const vk_render = @import("doe_vulkan_render_native.zig");
            vk_render.vulkan_destroy_texture(t);
            alloc.destroy(t);
            return;
        }
        if (t.mtl) |m| metal_bridge_release(m);
        alloc.destroy(t);
    }
}

pub export fn doeNativeTextureViewRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeTextureView, raw)) |tv| {
        label_store.remove(raw);
        if (tv.tex.vk_id != 0) {
            const vk_render = @import("doe_vulkan_render_native.zig");
            vk_render.vulkan_destroy_texture_view(tv);
            alloc.destroy(tv);
            return;
        }
        if (tv.handle) |handle| {
            if (tv.tex.mtl == null or handle != tv.tex.mtl) metal_bridge_release(handle);
        }
        alloc.destroy(tv);
    }
}

// ============================================================
// Sampler
// ============================================================

pub export fn doeNativeDeviceCreateSampler(dev_raw: ?*anyopaque, desc: ?*const types.WGPUSamplerDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const s = make(DoeSampler) orelse return null;
    s.* = .{};
    if (dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        if (!vk_render.vulkan_create_sampler(dev, s, d)) {
            alloc.destroy(s);
            return null;
        }
        const result = toOpaque(s);
        label_store.set(result, d.label.data, d.label.length);
        return result;
    }
    // Metal path.
    const mtl = metal_bridge_device_new_sampler(dev.mtl_device, d.minFilter, d.magFilter, d.mipmapFilter, d.addressModeU, d.addressModeV, d.addressModeW, d.lodMinClamp, d.lodMaxClamp, d.maxAnisotropy) orelse {
        alloc.destroy(s);
        return null;
    };
    s.* = .{ .mtl = mtl };
    const result = toOpaque(s);
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeSamplerRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeSampler, raw)) |s| {
        label_store.remove(raw);
        if (s.vk_runtime_ref) |rt_ptr| {
            const NativeVulkanRuntime = native.NativeVulkanRuntime;
            const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
            const vk_render = @import("doe_vulkan_render_native.zig");
            vk_render.vulkan_destroy_sampler(s, rt);
            alloc.destroy(s);
            return;
        }
        if (s.mtl) |m| metal_bridge_release(m);
        alloc.destroy(s);
    }
}

// Null-terminate a WGPUStringView into caller-supplied buffer.
// Returns null if the string is empty or buf is too small.
fn nullTermView(sv: RenderStringView, buf: []u8) ?[*:0]const u8 {
    const len = sv.length;
    if (len == 0) return null;
    if (len >= buf.len) return null;
    const data = sv.data orelse return null;
    @memcpy(buf[0..len], data[0..len]);
    buf[len] = 0;
    return buf[0..len :0];
}

const StageKind = enum { vertex, fragment };

// Map a WGSL entry point name to its MSL function name, applying the same
// renaming the WGSL→MSL emitter uses: "main" → "main_vertex"/"main_fragment".
fn mslStageName(sv: RenderStringView, stage: StageKind, buf: []u8) [*:0]const u8 {
    const data = sv.data orelse return switch (stage) {
        .vertex => "main_vertex",
        .fragment => "main_fragment",
    };
    const len = if (sv.length > 0) sv.length else std.mem.indexOfScalar(u8, data[0..256], 0) orelse 0;
    const name = data[0..len];
    if (std.mem.eql(u8, name, "main")) {
        return switch (stage) {
            .vertex => "main_vertex",
            .fragment => "main_fragment",
        };
    }
    if (len >= buf.len) return switch (stage) {
        .vertex => "main_vertex",
        .fragment => "main_fragment",
    };
    @memcpy(buf[0..len], name);
    buf[len] = 0;
    return buf[0..len :0];
}

// ============================================================
// Render Pipeline
// ============================================================

pub export fn doeNativeDeviceCreateRenderPipeline(dev_raw: ?*anyopaque, desc_raw: ?*anyopaque) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = @as(*const RenderPipelineDesc, @ptrCast(@alignCast(desc_raw orelse return null)));
    const pip = make(DoeRenderPipeline) orelse return null;
    pip.* = .{};
    pip.layout = cast(DoePipelineLayout, d.layout);
    if (dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        if (!vk_render.vulkan_create_render_pipeline(dev, pip, @ptrCast(d))) {
            alloc.destroy(pip);
            return null;
        }
        return toOpaque(pip);
    }
    var err_buf: [ERR_CAP]u8 = undefined;
    const frag = d.fragment orelse { alloc.destroy(pip); return null; };
    const vert_mod = cast(DoeShaderModule, d.vertex.module) orelse { alloc.destroy(pip); return null; };
    const frag_mod = cast(DoeShaderModule, frag.module) orelse { alloc.destroy(pip); return null; };

    // Pixel format from the first fragment target (default rgba8unorm).
    const pixel_format: u32 = if (frag.targetCount > 0)
        if (frag.targets) |ts| ts[0].format else 0x00000016
    else
        0x00000016;

    // Depth format (0 = no depth attachment).
    const depth_format: u32 = if (d.depthStencil) |ds_raw|
        (@as(*const RenderDepthStencilDesc, @ptrCast(@alignCast(ds_raw)))).format
    else
        0;

    // MSL function lookup, applying the "main" → "main_vertex"/"main_fragment" rename.
    var vert_entry_buf: [256]u8 = undefined;
    var frag_entry_buf: [256]u8 = undefined;
    const vert_entry = mslStageName(d.vertex.entryPoint, .vertex, &vert_entry_buf);
    const frag_entry = mslStageName(frag.entryPoint, .fragment, &frag_entry_buf);
    const vfn = metal_bridge_library_new_function(vert_mod.mtl_library, vert_entry);
    const ffn = metal_bridge_library_new_function(frag_mod.mtl_library, frag_entry);

    if (vfn == null or ffn == null) {
        if (vfn) |f| metal_bridge_release(f);
        if (ffn) |f| metal_bridge_release(f);
        alloc.destroy(pip);
        return null;
    }

    // Build flat Metal vertex layout + attribute arrays from the WGPU descriptor.
    // Metal buffer slot = the index of the vertex buffer layout in the descriptor.
    var mtl_layouts: [8]MtlVertexBufferLayout = undefined;
    var mtl_attrs: [16]MtlVertexAttributeDesc = undefined;
    var layout_count: u32 = 0;
    var attr_count: u32 = 0;

    const buf_count = @min(d.vertex.bufferCount, 8);
    if (buf_count > 0) {
        const bufs = @as(?[*]const RenderVertexBufferLayout, @ptrCast(@alignCast(d.vertex.buffers)));
        if (bufs) |layouts| {
            var i: usize = 0;
            while (i < buf_count) : (i += 1) {
                const layout = layouts[i];
                mtl_layouts[layout_count] = .{
                    .array_stride = layout.arrayStride,
                    .step_mode = layout.stepMode,
                    .buffer_index = @intCast(i),
                };
                layout_count += 1;
                const ac = @min(layout.attributeCount, 16 - @as(usize, attr_count));
                if (layout.attributes) |attrs| {
                    var j: usize = 0;
                    while (j < ac) : (j += 1) {
                        const attr = attrs[j];
                        mtl_attrs[attr_count] = .{
                            .format = attr.format,
                            .offset = attr.offset,
                            .shader_location = attr.shaderLocation,
                            .buffer_index = @intCast(i),
                        };
                        attr_count += 1;
                    }
                }
            }
        }
    }

    const target0 = if (frag.targetCount > 0 and frag.targets != null) frag.targets.?[0] else RenderColorTargetState{
        .nextInChain = null,
        .format = pixel_format,
        .blend = null,
        .writeMask = 0xF,
    };
    const blend_enabled: c_int = if (target0.blend != null) 1 else 0;
    const color_operation: u32 = if (target0.blend) |blend| blend.color.operation else 1;
    const color_src_factor: u32 = if (target0.blend) |blend| blend.color.srcFactor else 2;
    const color_dst_factor: u32 = if (target0.blend) |blend| blend.color.dstFactor else 1;
    const alpha_operation: u32 = if (target0.blend) |blend| blend.alpha.operation else 1;
    const alpha_src_factor: u32 = if (target0.blend) |blend| blend.alpha.srcFactor else 2;
    const alpha_dst_factor: u32 = if (target0.blend) |blend| blend.alpha.dstFactor else 1;
    const sample_count: u32 = if (d.multisample_count > 0) d.multisample_count else 1;

    const pso = metal_bridge_device_new_render_pipeline_full(
        dev.mtl_device, vfn, ffn,
        pixel_format, depth_format, sample_count,
        blend_enabled,
        color_operation, color_src_factor, color_dst_factor,
        alpha_operation, alpha_src_factor, alpha_dst_factor,
        @intCast(target0.writeMask),
        if (layout_count > 0) &mtl_layouts else null, layout_count,
        if (attr_count > 0) &mtl_attrs else null, attr_count,
        &err_buf, ERR_CAP,
    ) orelse {
        if (vfn) |f| metal_bridge_release(f);
        if (ffn) |f| metal_bridge_release(f);
        alloc.destroy(pip);
        return null;
    };
    // Release function handles — PSO holds its own retain.
    if (vfn) |f| metal_bridge_release(f);
    if (ffn) |f| metal_bridge_release(f);
    pip.* = .{
        .mtl_pso = pso,
        .topology = d.primitive.topology,
        .front_face = d.primitive.frontFace,
        .cull_mode = d.primitive.cullMode,
        .blend_enabled = blend_enabled != 0,
        .color_operation = color_operation,
        .color_src_factor = color_src_factor,
        .color_dst_factor = color_dst_factor,
        .alpha_operation = alpha_operation,
        .alpha_src_factor = alpha_src_factor,
        .alpha_dst_factor = alpha_dst_factor,
        .color_write_mask = @intCast(target0.writeMask),
        .sample_count = sample_count,
    };
    return toOpaque(pip);
}

pub export fn doeNativeRenderPipelineRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeRenderPipeline, raw)) |p| {
        label_store.remove(raw);
        if (p.mtl_pso) |pso| metal_bridge_release(pso);
        alloc.destroy(p);
    }
}

// ============================================================
// Render Pass
// ============================================================

pub export fn doeNativeCommandEncoderBeginRenderPass(enc_raw: ?*anyopaque, desc: ?*const types.WGPURenderPassDescriptor) callconv(.c) ?*anyopaque {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const pass = make(DoeRenderPass) orelse return null;
    pass.* = .{ .enc = enc };
    if (desc) |d| {
        pass.max_draw_count = if (d.maxDrawCount == 0) DEFAULT_MAX_DRAW_COUNT else d.maxDrawCount;
        pass.occlusion_query_set = d.occlusionQuerySet;
        if (d.colorAttachmentCount > 0) {
            if (d.colorAttachments) |attachments| {
                const att = attachments[0];
                const tv = cast(DoeTextureView, att.view);
                if (tv) |v| pass.target = if (v.handle) |handle| handle else v.tex.mtl;
                pass.clear_r = att.clearValue.r;
                pass.clear_g = att.clearValue.g;
                pass.clear_b = att.clearValue.b;
                pass.clear_a = att.clearValue.a;
            }
        }
    }
    return toOpaque(pass);
}

pub export fn doeNativeRenderPassSetPipeline(pass_raw: ?*anyopaque, pip_raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.pipeline = cast(DoeRenderPipeline, pip_raw);
}

pub export fn doeNativeRenderPassRecordViewportState(
    pass_raw: ?*anyopaque,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    min_depth: f64,
    max_depth: f64,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.viewport_x = @floatCast(x);
    pass.viewport_y = @floatCast(y);
    pass.viewport_width = @floatCast(width);
    pass.viewport_height = @floatCast(height);
    pass.viewport_min_depth = @floatCast(min_depth);
    pass.viewport_max_depth = @floatCast(max_depth);
}

pub export fn doeNativeRenderPassRecordScissorState(
    pass_raw: ?*anyopaque,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.scissor_x = x;
    pass.scissor_y = y;
    pass.scissor_width = width;
    pass.scissor_height = height;
}

pub export fn doeNativeRenderPassRecordBlendConstantState(
    pass_raw: ?*anyopaque,
    r: f64,
    g: f64,
    b: f64,
    a: f64,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.blend_constant = .{
        @floatCast(r),
        @floatCast(g),
        @floatCast(b),
        @floatCast(a),
    };
}

pub export fn doeNativeRenderPassRecordStencilReferenceState(
    pass_raw: ?*anyopaque,
    reference: u32,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.stencil_reference = reference;
}

pub export fn doeNativeRenderPassDraw(pass_raw: ?*anyopaque, vertex_count: u32, instance_count: u32, first_vertex: u32, first_instance: u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (!reserve_render_draw(pass)) return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_draw(pass, vertex_count, instance_count, first_vertex, first_instance);
        return;
    }
    const pip = pass.pipeline orelse return;
    pass.enc.cmds.append(alloc, .{ .render_pass = .{
        .pso = pip.mtl_pso,
        .depth_state = null,
        .target = pass.target,
        .depth_target = null,
        .topology = 0,
        .front_face = 0,
        .cull_mode = 0,
        .draw_count = 1,
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .first_vertex = first_vertex,
        .first_instance = first_instance,
        .clear_r = pass.clear_r,
        .clear_g = pass.clear_g,
        .clear_b = pass.clear_b,
        .clear_a = pass.clear_a,
    } }) catch std.debug.panic("doe_render_native: OOM recording render command", .{});
}

pub export fn doeNativeRenderPassSetVertexBuffer(pass_raw: ?*anyopaque, slot: u32, buffer_raw: ?*anyopaque, offset: u64, size: u64) callconv(.c) void {
    _ = cast(DoeRenderPass, pass_raw) orelse return;
    _ = slot;
    _ = buffer_raw;
    _ = offset;
    _ = size;
    // TODO: implement vertex buffer assignment
}

pub export fn doeNativeRenderPassSetIndexBuffer(pass_raw: ?*anyopaque, buffer_raw: ?*anyopaque, format: u32, offset: u64, size: u64) callconv(.c) void {
    _ = cast(DoeRenderPass, pass_raw) orelse return;
    _ = buffer_raw;
    _ = format;
    _ = offset;
    _ = size;
    // TODO: implement index buffer assignment
}

pub export fn doeNativeRenderPassSetBindGroup(pass_raw: ?*anyopaque, group_index: u32, group_raw: ?*anyopaque, dynamic_offset_count: usize, dynamic_offsets: ?[*]const u32) callconv(.c) void {
    _ = cast(DoeRenderPass, pass_raw) orelse return;
    _ = group_index;
    _ = group_raw;
    _ = dynamic_offset_count;
    _ = dynamic_offsets;
    // TODO: implement render pass bind group assignment
}

pub export fn doeNativeRenderPassDrawIndexed(pass_raw: ?*anyopaque, index_count: u32, instance_count: u32, first_index: u32, base_vertex: i32, first_instance: u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (!reserve_render_draw(pass)) return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_draw_indexed(pass, index_count, instance_count, first_index, base_vertex, first_instance);
        return;
    }
    // TODO: implement indexed draw for Metal
}

pub export fn doeNativeRenderPassEnd(raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeRenderPass, raw) orelse return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_end(pass);
        return;
    }
    // Metal: render pass commands were recorded and will be submitted on queue submit.
}

pub export fn doeNativeRenderPassRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeRenderPass, raw)) |p| {
        label_store.remove(raw);
        alloc.destroy(p);
    }
}

// Full render state: viewport, scissor, blend, MSAA, stencil, depth/stencil pipeline.
// Forced into this compilation unit so the C ABI exports reach the final shared library.
const render_state = @import("doe_render_state_native.zig");
comptime {
    _ = render_state;
}
