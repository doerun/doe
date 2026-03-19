// doe_render_native.zig — Texture, Sampler, Render Pipeline, and Render Pass
// C ABI exports for the Doe native Metal backend. Sharded from doe_wgpu_native.zig.

const std = @import("std");
const model = @import("model.zig");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");
const d3d12_formats = @import("backend/d3d12/d3d12_formats.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const ERR_CAP = native.ERR_CAP;
const label_store = native.label_store;

const DoeDevice = native.DoeDevice;
const DoeBuffer = native.DoeBuffer;
const DoeTexture = native.DoeTexture;
const DoeTextureView = native.DoeTextureView;
const DoeSampler = native.DoeSampler;
const DoeShaderModule = native.DoeShaderModule;
const DoePipelineLayout = native.DoePipelineLayout;
const DoeBindGroup = native.DoeBindGroup;
const DoeRenderPipeline = native.DoeRenderPipeline;
const DoeRenderPass = native.DoeRenderPass;
const DoeCommandEncoder = native.DoeCommandEncoder;

// Metal bridge externs (resolved at link time from metal_bridge.m).
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_device_create_root_signature_empty(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_texture_2d_layered(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    array_layers: u32,
    mip_levels: u32,
    sample_count: u32,
    format: u32,
    usage_flags: u32,
) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_texture_3d(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    depth: u32,
    mip_levels: u32,
    format: u32,
    usage_flags: u32,
) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_texture_create_view(
    texture: ?*anyopaque,
    format: u32,
    dimension: u32,
    aspect: u32,
    base_mip: u32,
    mip_count: u32,
    base_array_layer: u32,
    array_layer_count: u32,
    usage_flags: u64,
) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_sampler(
    device: ?*anyopaque,
    min_filter: u32,
    mag_filter: u32,
    mipmap_filter: u32,
    address_mode_u: u32,
    address_mode_v: u32,
    address_mode_w: u32,
    lod_min_clamp: f32,
    lod_max_clamp: f32,
    compare: u32,
    max_anisotropy: u16,
) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_texture(device: ?*anyopaque, width: u32, height: u32, depth_or_array_layers: u32, mip_levels: u32, sample_count: u32, pixel_format: u32, usage: u32, dimension: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_texture_new_view(texture: ?*anyopaque, pixel_format: u32, dimension: u32, base_mip_level: u32, mip_level_count: u32, base_array_layer: u32, array_layer_count: u32, swizzle_r: u32, swizzle_g: u32, swizzle_b: u32, swizzle_a: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_sampler(device: ?*anyopaque, min_f: u32, mag_f: u32, mip_f: u32, addr_u: u32, addr_v: u32, addr_w: u32, lod_min: f32, lod_max: f32, max_aniso: u16) callconv(.c) ?*anyopaque;
extern fn metal_bridge_library_new_function(library: ?*anyopaque, name: [*:0]const u8) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_render_pipeline_full(device: ?*anyopaque, vertex_function: ?*anyopaque, fragment_function: ?*anyopaque, pixel_format: u32, depth_format: u32, sample_count: u32, blend_enabled: c_int, color_operation: u32, color_src_factor: u32, color_dst_factor: u32, alpha_operation: u32, alpha_src_factor: u32, alpha_dst_factor: u32, color_write_mask: u32, vertex_layouts: ?[*]const MtlVertexBufferLayout, vertex_layout_count: u32, vertex_attributes: ?[*]const MtlVertexAttributeDesc, vertex_attribute_count: u32, error_buf: ?[*]u8, error_cap: usize) callconv(.c) ?*anyopaque;
const D3D12InputElementDesc = extern struct {
    format: u32,
    input_slot: u32,
    aligned_byte_offset: u32,
    semantic_index: u32,
    input_slot_class: u32,
    instance_data_step_rate: u32,
};
const D3D12GraphicsPipelineDesc = extern struct {
    target_format: u32,
    depth_stencil_format: u32,
    sample_count: u32,
    topology: u32,
    topology_type: u32,
    front_face: u32,
    cull_mode: u32,
    blend_enabled: u32,
    color_operation: u32,
    color_src_factor: u32,
    color_dst_factor: u32,
    alpha_operation: u32,
    alpha_src_factor: u32,
    alpha_dst_factor: u32,
    color_write_mask: u32,
    depth_compare: u32,
    depth_write_enabled: u32,
    stencil_front_compare: u32,
    stencil_front_fail_op: u32,
    stencil_front_depth_fail_op: u32,
    stencil_front_pass_op: u32,
    stencil_back_compare: u32,
    stencil_back_fail_op: u32,
    stencil_back_depth_fail_op: u32,
    stencil_back_pass_op: u32,
    stencil_read_mask: u32,
    stencil_write_mask: u32,
    depth_bias: i32,
    depth_bias_slope_scale: f32,
    depth_bias_clamp: f32,
    unclipped_depth: u32,
};
extern fn d3d12_bridge_device_create_graphics_pipeline_hlsl(
    device: ?*anyopaque,
    root_sig: ?*anyopaque,
    vs_source: [*:0]const u8,
    vs_source_len: usize,
    vs_entry: [*:0]const u8,
    ps_source: [*:0]const u8,
    ps_source_len: usize,
    ps_entry: [*:0]const u8,
    desc: *const D3D12GraphicsPipelineDesc,
    input_elements: ?[*]const D3D12InputElementDesc,
    input_element_count: u32,
) callconv(.c) ?*anyopaque;

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
    depthWriteEnabled: u32,
    depthCompare: u32,
    stencilFront: extern struct {
        compare: u32,
        failOp: u32,
        depthFailOp: u32,
        passOp: u32,
    },
    stencilBack: extern struct {
        compare: u32,
        failOp: u32,
        depthFailOp: u32,
        passOp: u32,
    },
    stencilReadMask: u32,
    stencilWriteMask: u32,
    depthBias: i32,
    depthBiasSlopeScale: f32,
    depthBiasClamp: f32,
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
const D3D12_INPUT_CLASSIFICATION_PER_VERTEX_DATA: u32 = 0;
const D3D12_INPUT_CLASSIFICATION_PER_INSTANCE_DATA: u32 = 1;

const OpaqueRegistry = struct {
    map: std.AutoHashMapUnmanaged(usize, void) = .{},
    mutex: std.Thread.Mutex = .{},

    fn insert(self: *OpaqueRegistry, raw: ?*anyopaque) !void {
        const key = @intFromPtr(raw orelse return error.InvalidState);
        self.mutex.lock();
        defer self.mutex.unlock();
        try self.map.put(alloc, key, {});
    }

    fn contains(self: *OpaqueRegistry, raw: ?*anyopaque) bool {
        const key = @intFromPtr(raw orelse return false);
        self.mutex.lock();
        defer self.mutex.unlock();
        return self.map.contains(key);
    }

    fn remove(self: *OpaqueRegistry, raw: ?*anyopaque) void {
        const key = @intFromPtr(raw orelse return);
        self.mutex.lock();
        defer self.mutex.unlock();
        _ = self.map.remove(key);
    }
};

var d3d12_texture_registry: OpaqueRegistry = .{};
var d3d12_texture_view_registry: OpaqueRegistry = .{};
var d3d12_sampler_registry: OpaqueRegistry = .{};

const d3d12_passthrough_vs_source =
    \\struct VSOutput {
    \\    float4 position : SV_Position;
    \\    float4 color : COLOR0;
    \\};
    \\VSOutput main_vertex(uint vertex_id : SV_VertexID, uint instance_id : SV_InstanceID) {
    \\    static const float2 positions[3] = {
    \\        float2(-0.5f, -0.5f),
    \\        float2( 0.5f, -0.5f),
    \\        float2( 0.0f,  0.5f)
    \\    };
    \\    VSOutput output;
    \\    float2 p = positions[vertex_id % 3];
    \\    output.position = float4(p, 0.0f, 1.0f);
    \\    output.color = float4((instance_id & 1u) ? 0.75f : 0.25f, 0.5f, 0.9f, 1.0f);
    \\    return output;
    \\}
;
const d3d12_passthrough_ps_source =
    \\float4 main_fragment(float4 position : SV_Position, float4 color : COLOR0) : SV_Target0 {
    \\    return color;
    \\}
;

fn default_texture_view_dimension(tex: *const DoeTexture) u32 {
    if (tex.texture_binding_view_dimension != 0) return tex.texture_binding_view_dimension;
    return switch (tex.dimension) {
        types.WGPUTextureDimension_1D => types.WGPUTextureViewDimension_1D,
        types.WGPUTextureDimension_3D => types.WGPUTextureViewDimension_3D,
        else => if (tex.depth_or_array_layers > 1)
            types.WGPUTextureViewDimension_2DArray
        else
            types.WGPUTextureViewDimension_2D,
    };
}

fn is_depth_format(format: u32) bool {
    return switch (format) {
        types.WGPUTextureFormat_Stencil8,
        types.WGPUTextureFormat_Depth16Unorm,
        types.WGPUTextureFormat_Depth24Plus,
        types.WGPUTextureFormat_Depth24PlusStencil8,
        types.WGPUTextureFormat_Depth32Float,
        types.WGPUTextureFormat_Depth32FloatStencil8,
        => true,
        else => false,
    };
}

fn is_combined_depth_stencil_format(format: u32) bool {
    return switch (format) {
        types.WGPUTextureFormat_Depth24PlusStencil8,
        types.WGPUTextureFormat_Depth32FloatStencil8,
        => true,
        else => false,
    };
}

fn view_aspect_supported(format: u32, aspect: u32) bool {
    const resolved_aspect = if (aspect == 0) types.WGPUTextureAspect_All else aspect;
    return switch (resolved_aspect) {
        types.WGPUTextureAspect_All => true,
        types.WGPUTextureAspect_DepthOnly => switch (format) {
            types.WGPUTextureFormat_Depth16Unorm, types.WGPUTextureFormat_Depth24Plus, types.WGPUTextureFormat_Depth24PlusStencil8, types.WGPUTextureFormat_Depth32Float, types.WGPUTextureFormat_Depth32FloatStencil8 => true,
            else => false,
        },
        types.WGPUTextureAspect_StencilOnly => switch (format) {
            types.WGPUTextureFormat_Stencil8, types.WGPUTextureFormat_Depth24PlusStencil8, types.WGPUTextureFormat_Depth32FloatStencil8 => true,
            else => false,
        },
        else => false,
    };
}

fn d3d12_sampled_aspect(format: u32, aspect: u32) u32 {
    const resolved_aspect = if (aspect == 0) types.WGPUTextureAspect_All else aspect;
    if (is_combined_depth_stencil_format(format)) {
        return if (resolved_aspect == types.WGPUTextureAspect_StencilOnly)
            types.WGPUTextureAspect_StencilOnly
        else
            types.WGPUTextureAspect_DepthOnly;
    }
    if (format == types.WGPUTextureFormat_Stencil8) return types.WGPUTextureAspect_StencilOnly;
    return resolved_aspect;
}

fn identity_swizzle(swizzle_r: u32, swizzle_g: u32, swizzle_b: u32, swizzle_a: u32) bool {
    return swizzle_r == types.WGPUTextureComponentSwizzle_Red and
        swizzle_g == types.WGPUTextureComponentSwizzle_Green and
        swizzle_b == types.WGPUTextureComponentSwizzle_Blue and
        swizzle_a == types.WGPUTextureComponentSwizzle_Alpha;
}

fn d3d12_texture_descriptor_supported(desc: *const types.WGPUTextureDescriptor) bool {
    if ((desc.usage & (types.WGPUTextureUsage_TransientAttachment | types.WGPUTextureUsage_StorageAttachment)) != 0) return false;
    if (desc.dimension == types.WGPUTextureDimension_1D) return false;
    if (desc.dimension == types.WGPUTextureDimension_3D and desc.sampleCount > 1) return false;
    if (desc.viewFormatCount > 0) {
        const view_formats = desc.viewFormats orelse return false;
        var i: usize = 0;
        while (i < desc.viewFormatCount) : (i += 1) {
            if (view_formats[i] != desc.format) return false;
        }
    }
    return true;
}

fn d3d12_view_dimension_supported(tex: *const DoeTexture, view_dimension: u32) bool {
    return switch (tex.dimension) {
        types.WGPUTextureDimension_3D => view_dimension == types.WGPUTextureViewDimension_3D,
        types.WGPUTextureDimension_2D => switch (view_dimension) {
            types.WGPUTextureViewDimension_2D,
            types.WGPUTextureViewDimension_2DArray,
            => true,
            types.WGPUTextureViewDimension_2DDepth,
            types.WGPUTextureViewDimension_2DArrayDepth,
            => is_depth_format(tex.format),
            types.WGPUTextureViewDimension_Cube,
            types.WGPUTextureViewDimension_CubeArray,
            => tex.depth_or_array_layers >= 6 and (tex.depth_or_array_layers % 6) == 0,
            else => false,
        },
        else => false,
    };
}

fn d3d12_register_texture(raw: ?*anyopaque) bool {
    d3d12_texture_registry.insert(raw) catch return false;
    return true;
}

fn d3d12_register_texture_view(raw: ?*anyopaque) bool {
    d3d12_texture_view_registry.insert(raw) catch return false;
    return true;
}

fn d3d12_register_sampler(raw: ?*anyopaque) bool {
    d3d12_sampler_registry.insert(raw) catch return false;
    return true;
}

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
        .texture_binding_view_dimension = 0,
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
    if (dev.backend == .d3d12) {
        if (!d3d12_texture_descriptor_supported(d)) {
            alloc.destroy(tex);
            return null;
        }
        const d3d12_texture = switch (d.dimension) {
            types.WGPUTextureDimension_2D => d3d12_bridge_device_create_texture_2d_layered(
                dev.mtl_device,
                d.size.width,
                d.size.height,
                d.size.depthOrArrayLayers,
                d.mipLevelCount,
                d.sampleCount,
                d.format,
                @intCast(d.usage),
            ),
            types.WGPUTextureDimension_3D => d3d12_bridge_device_create_texture_3d(
                dev.mtl_device,
                d.size.width,
                d.size.height,
                d.size.depthOrArrayLayers,
                d.mipLevelCount,
                d.format,
                @intCast(d.usage),
            ),
            else => null,
        } orelse {
            alloc.destroy(tex);
            return null;
        };
        tex.mtl = d3d12_texture;
        const result = toOpaque(tex);
        if (!d3d12_register_texture(result)) {
            d3d12_bridge_release(d3d12_texture);
            alloc.destroy(tex);
            return null;
        }
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
        .dimension = default_texture_view_dimension(tex),
        .baseMipLevel = 0,
        .mipLevelCount = tex.mip_level_count,
        .baseArrayLayer = 0,
        .arrayLayerCount = if (tex.dimension == types.WGPUTextureDimension_3D) 1 else tex.depth_or_array_layers,
        .aspect = types.WGPUTextureAspect_All,
        .usage = tex.usage,
        .swizzleR = types.WGPUTextureComponentSwizzle_Red,
        .swizzleG = types.WGPUTextureComponentSwizzle_Green,
        .swizzleB = types.WGPUTextureComponentSwizzle_Blue,
        .swizzleA = types.WGPUTextureComponentSwizzle_Alpha,
    };
    const resolved_format = if (d.format != 0) d.format else tex.format;
    const resolved_dimension = if (d.dimension != 0) d.dimension else default_texture_view_dimension(tex);
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
    const is_d3d12_texture = d3d12_texture_registry.contains(tex_raw);
    var view_handle: ?*anyopaque = tv.handle;
    if (is_d3d12_texture) {
        const resolved_aspect = if (d.aspect != 0) d.aspect else types.WGPUTextureAspect_All;
        const wants_storage_only =
            (resolved_usage & types.WGPUTextureUsage_StorageBinding) != 0 and
            (resolved_usage & types.WGPUTextureUsage_TextureBinding) == 0;

        if (resolved_format != tex.format or
            !identity_swizzle(resolved_swizzle_r, resolved_swizzle_g, resolved_swizzle_b, resolved_swizzle_a) or
            !d3d12_view_dimension_supported(tex, resolved_dimension) or
            !view_aspect_supported(tex.format, resolved_aspect))
        {
            alloc.destroy(tv);
            return null;
        }
        if ((resolved_dimension == types.WGPUTextureViewDimension_Cube or
            resolved_dimension == types.WGPUTextureViewDimension_CubeArray) and
            ((d.baseArrayLayer % 6) != 0 or (resolved_array_layer_count % 6) != 0))
        {
            alloc.destroy(tv);
            return null;
        }
        if ((resolved_usage & types.WGPUTextureUsage_StorageBinding) != 0 and
            (resolved_usage & types.WGPUTextureUsage_TextureBinding) != 0)
        {
            alloc.destroy(tv);
            return null;
        }
        if (wants_storage_only) {
            if (tex.sample_count > 1 or is_depth_format(tex.format) or resolved_mip_level_count != 1) {
                alloc.destroy(tv);
                return null;
            }
            view_handle = d3d12_bridge_texture_create_view(
                tex.mtl,
                resolved_format,
                resolved_dimension,
                resolved_aspect,
                d.baseMipLevel,
                resolved_mip_level_count,
                d.baseArrayLayer,
                resolved_array_layer_count,
                types.WGPUTextureUsage_StorageBinding,
            ) orelse {
                alloc.destroy(tv);
                return null;
            };
        } else if (tex.sample_count == 1) {
            view_handle = d3d12_bridge_texture_create_view(
                tex.mtl,
                resolved_format,
                resolved_dimension,
                d3d12_sampled_aspect(tex.format, resolved_aspect),
                d.baseMipLevel,
                resolved_mip_level_count,
                d.baseArrayLayer,
                resolved_array_layer_count,
                types.WGPUTextureUsage_TextureBinding,
            );
        } else {
            view_handle = null;
        }
    } else if (tex.mtl != null) {
        view_handle = metal_bridge_texture_new_view(
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
        );
    }
    tv.* = .{
        .tex = tex,
        .handle = view_handle,
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
    if (is_d3d12_texture and !d3d12_register_texture_view(result)) {
        if (view_handle) |handle| d3d12_bridge_release(handle);
        alloc.destroy(tv);
        return null;
    }
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeTextureRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeTexture, raw)) |t| {
        label_store.remove(raw);
        if (d3d12_texture_registry.contains(raw)) {
            d3d12_texture_registry.remove(raw);
            if (t.mtl) |m| d3d12_bridge_release(m);
            alloc.destroy(t);
            return;
        }
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
        if (d3d12_texture_view_registry.contains(raw)) {
            d3d12_texture_view_registry.remove(raw);
            if (tv.handle) |handle| d3d12_bridge_release(handle);
            alloc.destroy(tv);
            return;
        }
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
    if (dev.backend == .d3d12) {
        const sampler = d3d12_bridge_device_create_sampler(
            dev.mtl_device,
            d.minFilter,
            d.magFilter,
            d.mipmapFilter,
            d.addressModeU,
            d.addressModeV,
            d.addressModeW,
            d.lodMinClamp,
            d.lodMaxClamp,
            d.compare,
            d.maxAnisotropy,
        ) orelse {
            alloc.destroy(s);
            return null;
        };
        s.* = .{ .mtl = sampler };
        const result = toOpaque(s);
        if (!d3d12_register_sampler(result)) {
            d3d12_bridge_release(sampler);
            alloc.destroy(s);
            return null;
        }
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
        if (d3d12_sampler_registry.contains(raw)) {
            d3d12_sampler_registry.remove(raw);
            if (s.mtl) |m| d3d12_bridge_release(m);
            alloc.destroy(s);
            return;
        }
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

fn stageEntryName(sv: RenderStringView, fallback: [*:0]const u8) [*:0]const u8 {
    const data = sv.data orelse return fallback;
    return @ptrCast(data);
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

    const buf_count = @min(d.vertex.bufferCount, @as(usize, model.MAX_VERTEX_BUFFERS));
    if (buf_count > 0) {
        const bufs = @as(?[*]const RenderVertexBufferLayout, @ptrCast(@alignCast(d.vertex.buffers)));
        if (bufs) |layouts| {
            pip.vertex_layout_count = @intCast(buf_count);
            var i: usize = 0;
            while (i < buf_count) : (i += 1) {
                const layout = layouts[i];
                const dst = &pip.vertex_layouts[i];
                dst.* = .{
                    .array_stride = layout.arrayStride,
                    .step_mode = layout.stepMode,
                    .attribute_count = @intCast(@min(layout.attributeCount, @as(usize, model.MAX_VERTEX_ATTRIBUTES))),
                };
                if (layout.attributes) |attrs| {
                    const attr_count = @min(layout.attributeCount, @as(usize, model.MAX_VERTEX_ATTRIBUTES));
                    var j: usize = 0;
                    while (j < attr_count) : (j += 1) {
                        const attr = attrs[j];
                        dst.attributes[j] = .{
                            .format = attr.format,
                            .offset = attr.offset,
                            .shader_location = attr.shaderLocation,
                        };
                    }
                }
            }
        }
    }

    if (dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        if (!vk_render.vulkan_create_render_pipeline(dev, pip, @ptrCast(d))) {
            alloc.destroy(pip);
            return null;
        }
        return toOpaque(pip);
    }
    var err_buf: [ERR_CAP]u8 = undefined;
    const frag = d.fragment orelse {
        alloc.destroy(pip);
        return null;
    };
    const vert_mod = cast(DoeShaderModule, d.vertex.module) orelse {
        alloc.destroy(pip);
        return null;
    };
    const frag_mod = cast(DoeShaderModule, frag.module) orelse {
        alloc.destroy(pip);
        return null;
    };

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
    const sample_count: u32 = if (d.multisample.count > 0) d.multisample.count else 1;
    const depth_desc = if (d.depthStencil) |ds_raw|
        @as(*const RenderDepthStencilDesc, @ptrCast(@alignCast(ds_raw)))
    else
        null;

    if (dev.backend == .d3d12) {
        const vertex_hlsl = vert_mod.hlsl_source orelse {
            alloc.destroy(pip);
            return null;
        };
        const fragment_hlsl = frag_mod.hlsl_source orelse {
            alloc.destroy(pip);
            return null;
        };
        const root_sig = d3d12_bridge_device_create_root_signature_empty(dev.mtl_device) orelse {
            alloc.destroy(pip);
            return null;
        };
        errdefer d3d12_bridge_release(root_sig);

        var input_elements: [model.MAX_VERTEX_ATTRIBUTES]D3D12InputElementDesc =
            [_]D3D12InputElementDesc{std.mem.zeroes(D3D12InputElementDesc)} ** model.MAX_VERTEX_ATTRIBUTES;
        var input_count: u32 = 0;
        var vb_count: u32 = 0;
        var attr_count: u32 = 0;
        var i: usize = 0;
        while (i < @as(usize, pip.vertex_layout_count) and i < model.MAX_VERTEX_BUFFERS) : (i += 1) {
            const layout = pip.vertex_layouts[i];
            vb_count += 1;
            pip.vertex_buffer_strides[i] = layout.array_stride;
            pip.vertex_step_modes[i] = layout.step_mode;
            var j: usize = 0;
            while (j < @as(usize, layout.attribute_count) and attr_count < @as(u32, model.MAX_VERTEX_ATTRIBUTES)) : (j += 1) {
                const attr = layout.attributes[j];
                const input_slot_class = if (layout.step_mode == model.WGPUVertexStepMode_Instance)
                    D3D12_INPUT_CLASSIFICATION_PER_INSTANCE_DATA
                else
                    D3D12_INPUT_CLASSIFICATION_PER_VERTEX_DATA;
                input_elements[input_count] = .{
                    .format = d3d12_formats.wgpu_vertex_format_to_dxgi(attr.format) catch {
                        alloc.destroy(pip);
                        return null;
                    },
                    .input_slot = @intCast(i),
                    .aligned_byte_offset = @intCast(attr.offset),
                    .semantic_index = attr.shader_location,
                    .input_slot_class = input_slot_class,
                    .instance_data_step_rate = if (input_slot_class == D3D12_INPUT_CLASSIFICATION_PER_INSTANCE_DATA) 1 else 0,
                };
                pip.vertex_attribute_formats[attr_count] = attr.format;
                pip.vertex_attribute_offsets[attr_count] = attr.offset;
                pip.vertex_attribute_locations[attr_count] = attr.shader_location;
                pip.vertex_attribute_buffer_slots[attr_count] = @intCast(i);
                input_count += 1;
                attr_count += 1;
            }
        }

        const d3d_desc = D3D12GraphicsPipelineDesc{
            .target_format = pixel_format,
            .depth_stencil_format = depth_format,
            .sample_count = sample_count,
            .topology = d.primitive.topology,
            .topology_type = 0,
            .front_face = d.primitive.frontFace,
            .cull_mode = d.primitive.cullMode,
            .blend_enabled = if (blend_enabled != 0) 1 else 0,
            .color_operation = color_operation,
            .color_src_factor = color_src_factor,
            .color_dst_factor = color_dst_factor,
            .alpha_operation = alpha_operation,
            .alpha_src_factor = alpha_src_factor,
            .alpha_dst_factor = alpha_dst_factor,
            .color_write_mask = @intCast(target0.writeMask),
            .depth_compare = if (depth_desc) |ds| ds.depthCompare else 0x00000008,
            .depth_write_enabled = if (depth_desc) |ds| ds.depthWriteEnabled else 0,
            .stencil_front_compare = if (depth_desc) |ds| ds.stencilFront.compare else 0x00000008,
            .stencil_front_fail_op = if (depth_desc) |ds| ds.stencilFront.failOp else 0,
            .stencil_front_depth_fail_op = if (depth_desc) |ds| ds.stencilFront.depthFailOp else 0,
            .stencil_front_pass_op = if (depth_desc) |ds| ds.stencilFront.passOp else 0,
            .stencil_back_compare = if (depth_desc) |ds| ds.stencilBack.compare else 0x00000008,
            .stencil_back_fail_op = if (depth_desc) |ds| ds.stencilBack.failOp else 0,
            .stencil_back_depth_fail_op = if (depth_desc) |ds| ds.stencilBack.depthFailOp else 0,
            .stencil_back_pass_op = if (depth_desc) |ds| ds.stencilBack.passOp else 0,
            .stencil_read_mask = if (depth_desc) |ds| ds.stencilReadMask else 0xFFFF_FFFF,
            .stencil_write_mask = if (depth_desc) |ds| ds.stencilWriteMask else 0xFFFF_FFFF,
            .depth_bias = if (depth_desc) |ds| ds.depthBias else 0,
            .depth_bias_slope_scale = if (depth_desc) |ds| ds.depthBiasSlopeScale else 0,
            .depth_bias_clamp = if (depth_desc) |ds| ds.depthBiasClamp else 0,
            .unclipped_depth = d.primitive.unclippedDepth,
        };
        const d3d_pso = d3d12_bridge_device_create_graphics_pipeline_hlsl(
            dev.mtl_device,
            root_sig,
            @ptrCast(vertex_hlsl.ptr),
            vertex_hlsl.len,
            stageEntryName(d.vertex.entryPoint, "main"),
            @ptrCast(fragment_hlsl.ptr),
            fragment_hlsl.len,
            stageEntryName(frag.entryPoint, "main"),
            &d3d_desc,
            if (input_count > 0) &input_elements else null,
            input_count,
        ) orelse {
            alloc.destroy(pip);
            return null;
        };
        pip.* = .{
            .mtl_pso = d3d_pso,
            .backend_root_signature = root_sig,
            .topology = d.primitive.topology,
            .front_face = d.primitive.frontFace,
            .cull_mode = d.primitive.cullMode,
            .depth_stencil_format = depth_format,
            .depth_compare = if (depth_desc) |ds| ds.depthCompare else 0x00000008,
            .depth_write_enabled = if (depth_desc) |ds| ds.depthWriteEnabled != 0 else false,
            .unclipped_depth = d.primitive.unclippedDepth != 0,
            .stencil_front_compare = if (depth_desc) |ds| ds.stencilFront.compare else 0x00000008,
            .stencil_front_fail_op = if (depth_desc) |ds| ds.stencilFront.failOp else 0,
            .stencil_front_depth_fail_op = if (depth_desc) |ds| ds.stencilFront.depthFailOp else 0,
            .stencil_front_pass_op = if (depth_desc) |ds| ds.stencilFront.passOp else 0,
            .stencil_back_compare = if (depth_desc) |ds| ds.stencilBack.compare else 0x00000008,
            .stencil_back_fail_op = if (depth_desc) |ds| ds.stencilBack.failOp else 0,
            .stencil_back_depth_fail_op = if (depth_desc) |ds| ds.stencilBack.depthFailOp else 0,
            .stencil_back_pass_op = if (depth_desc) |ds| ds.stencilBack.passOp else 0,
            .stencil_read_mask = if (depth_desc) |ds| ds.stencilReadMask else 0xFFFF_FFFF,
            .stencil_write_mask = if (depth_desc) |ds| ds.stencilWriteMask else 0xFFFF_FFFF,
            .blend_enabled = blend_enabled != 0,
            .color_operation = color_operation,
            .color_src_factor = color_src_factor,
            .color_dst_factor = color_dst_factor,
            .alpha_operation = alpha_operation,
            .alpha_src_factor = alpha_src_factor,
            .alpha_dst_factor = alpha_dst_factor,
            .color_write_mask = @intCast(target0.writeMask),
            .sample_count = sample_count,
            .vertex_layout_count = pip.vertex_layout_count,
            .vertex_layouts = pip.vertex_layouts,
            .vertex_buffer_count = vb_count,
            .vertex_buffer_strides = pip.vertex_buffer_strides,
            .vertex_step_modes = pip.vertex_step_modes,
            .vertex_attribute_count = attr_count,
            .vertex_attribute_formats = pip.vertex_attribute_formats,
            .vertex_attribute_offsets = pip.vertex_attribute_offsets,
            .vertex_attribute_locations = pip.vertex_attribute_locations,
            .vertex_attribute_buffer_slots = pip.vertex_attribute_buffer_slots,
        };
        return toOpaque(pip);
    }

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

    const metal_buf_count = @min(d.vertex.bufferCount, 8);
    if (metal_buf_count > 0) {
        const bufs = @as(?[*]const RenderVertexBufferLayout, @ptrCast(@alignCast(d.vertex.buffers)));
        if (bufs) |layouts| {
            var i: usize = 0;
            while (i < metal_buf_count) : (i += 1) {
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

    const pso = metal_bridge_device_new_render_pipeline_full(
        dev.mtl_device,
        vfn,
        ffn,
        pixel_format,
        depth_format,
        sample_count,
        blend_enabled,
        color_operation,
        color_src_factor,
        color_dst_factor,
        alpha_operation,
        alpha_src_factor,
        alpha_dst_factor,
        @intCast(target0.writeMask),
        if (layout_count > 0) &mtl_layouts else null,
        layout_count,
        if (attr_count > 0) &mtl_attrs else null,
        attr_count,
        &err_buf,
        ERR_CAP,
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
        if (p.backend_root_signature != null) {
            if (p.mtl_pso) |pso| d3d12_bridge_release(pso);
            if (p.backend_root_signature) |root_sig| d3d12_bridge_release(root_sig);
        } else if (p.mtl_pso) |pso| {
            metal_bridge_release(pso);
        }
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
                if (tv) |v| {
                    pass.target = if (d3d12_texture_view_registry.contains(att.view))
                        v.tex.mtl
                    else if (v.handle) |handle|
                        handle
                    else
                        v.tex.mtl;
                }
                pass.clear_r = att.clearValue.r;
                pass.clear_g = att.clearValue.g;
                pass.clear_b = att.clearValue.b;
                pass.clear_a = att.clearValue.a;
            }
        }
        if (d.depthStencilAttachment) |depth_att| {
            if (cast(DoeTextureView, depth_att.view)) |v| {
                pass.depth_target = if (d3d12_texture_view_registry.contains(depth_att.view))
                    v.tex.mtl
                else if (v.handle) |handle|
                    handle
                else
                    v.tex.mtl;
            }
        }
    }
    return toOpaque(pass);
}

pub export fn doeNativeRenderPassSetPipeline(pass_raw: ?*anyopaque, pip_raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.pipeline = cast(DoeRenderPipeline, pip_raw);
    if (pass.pipeline) |pipeline| {
        pass.depth_compare = pipeline.depth_compare;
        pass.depth_write_enabled = pipeline.depth_write_enabled;
    }
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
        .root_signature = pip.backend_root_signature,
        .depth_state = pip.depth_state,
        .target = pass.target,
        .depth_target = pass.depth_target,
        .topology = pip.topology,
        .front_face = pip.front_face,
        .cull_mode = pip.cull_mode,
        .draw_count = 1,
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .first_vertex = first_vertex,
        .first_instance = first_instance,
        .vertex_buffers = blk: {
            var buffers: [native.MAX_VERTEX_BUFFERS]?*anyopaque = [_]?*anyopaque{null} ** native.MAX_VERTEX_BUFFERS;
            var i: usize = 0;
            while (i < native.MAX_VERTEX_BUFFERS) : (i += 1) {
                buffers[i] = if (pass.vertex_buffers[i]) |buffer| buffer.mtl else null;
            }
            break :blk buffers;
        },
        .vertex_buffer_offsets = pass.vertex_buffer_offsets,
        .vertex_buffer_sizes = pass.vertex_buffer_sizes,
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .depth_compare = pass.depth_compare,
        .depth_write_enabled = pass.depth_write_enabled,
        .unclipped_depth = pip.unclipped_depth,
        .clear_r = pass.clear_r,
        .clear_g = pass.clear_g,
        .clear_b = pass.clear_b,
        .clear_a = pass.clear_a,
    } }) catch std.debug.panic("doe_render_native: OOM recording render command", .{});
}

pub export fn doeNativeRenderPassSetVertexBuffer(pass_raw: ?*anyopaque, slot: u32, buffer_raw: ?*anyopaque, offset: u64, size: u64) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (slot >= native.MAX_VERTEX_BUFFERS) return;
    pass.vertex_buffers[slot] = cast(DoeBuffer, buffer_raw);
    pass.vertex_buffer_offsets[slot] = offset;
    pass.vertex_buffer_sizes[slot] = size;
}

pub export fn doeNativeRenderPassSetIndexBuffer(pass_raw: ?*anyopaque, buffer_raw: ?*anyopaque, format: u32, offset: u64, size: u64) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.index_buffer = cast(DoeBuffer, buffer_raw);
    pass.index_format = format;
    pass.index_offset = offset;
    pass.index_buffer_size = size;
}

pub export fn doeNativeRenderPassSetBindGroup(pass_raw: ?*anyopaque, group_index: u32, group_raw: ?*anyopaque, dynamic_offset_count: usize, dynamic_offsets: ?[*]const u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (group_index >= native.MAX_RENDER_BIND_GROUPS) return;
    pass.bind_groups[group_index] = cast(DoeBindGroup, group_raw);
    _ = dynamic_offset_count;
    _ = dynamic_offsets;
}

pub export fn doeNativeRenderPassDrawIndexed(pass_raw: ?*anyopaque, index_count: u32, instance_count: u32, first_index: u32, base_vertex: i32, first_instance: u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (!reserve_render_draw(pass)) return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_draw_indexed(pass, index_count, instance_count, first_index, base_vertex, first_instance);
        return;
    }
    const pip = pass.pipeline orelse return;
    pass.enc.cmds.append(alloc, .{ .render_pass = .{
        .pso = pip.mtl_pso,
        .root_signature = pip.backend_root_signature,
        .depth_state = pip.depth_state,
        .target = pass.target,
        .depth_target = pass.depth_target,
        .topology = pip.topology,
        .front_face = pip.front_face,
        .cull_mode = pip.cull_mode,
        .draw_count = 1,
        .vertex_count = 0,
        .instance_count = instance_count,
        .first_vertex = 0,
        .first_instance = first_instance,
        .indexed = true,
        .index_buffer = if (pass.index_buffer) |buffer| buffer.mtl else null,
        .index_offset = pass.index_offset,
        .index_format = pass.index_format,
        .index_buffer_size = pass.index_buffer_size,
        .index_count = index_count,
        .first_index = first_index,
        .base_vertex = base_vertex,
        .vertex_buffers = blk: {
            var buffers: [native.MAX_VERTEX_BUFFERS]?*anyopaque = [_]?*anyopaque{null} ** native.MAX_VERTEX_BUFFERS;
            var i: usize = 0;
            while (i < native.MAX_VERTEX_BUFFERS) : (i += 1) {
                buffers[i] = if (pass.vertex_buffers[i]) |buffer| buffer.mtl else null;
            }
            break :blk buffers;
        },
        .vertex_buffer_offsets = pass.vertex_buffer_offsets,
        .vertex_buffer_sizes = pass.vertex_buffer_sizes,
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .depth_compare = pass.depth_compare,
        .depth_write_enabled = pass.depth_write_enabled,
        .unclipped_depth = pip.unclipped_depth,
        .clear_r = pass.clear_r,
        .clear_g = pass.clear_g,
        .clear_b = pass.clear_b,
        .clear_a = pass.clear_a,
    } }) catch std.debug.panic("doe_render_native: OOM recording indexed render command", .{});
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
