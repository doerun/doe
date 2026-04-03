// doe_texture_sampler_native.zig — Texture and Sampler C ABI exports.
// Sharded from doe_render_native.zig for file-size compliance.

const std = @import("std");
const model = @import("model_webgpu_types.zig");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");
const d3d12_formats = @import("backend/d3d12/d3d12_formats.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const label_store = native.label_store;

const DoeDevice = native.DoeDevice;
const DoeBuffer = native.DoeBuffer;
const DoeTexture = native.DoeTexture;
const DoeTextureView = native.DoeTextureView;
const DoeSampler = native.DoeSampler;

// Metal bridge externs (resolved at link time from metal_bridge.m).
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;
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

const OpaqueRegistry = struct {
    map: std.AutoHashMapUnmanaged(usize, void) = .{},
    mutex: std.Thread.Mutex = .{},

    pub fn insert(self: *OpaqueRegistry, raw: ?*anyopaque) !void {
        const key = @intFromPtr(raw orelse return error.InvalidState);
        self.mutex.lock();
        defer self.mutex.unlock();
        try self.map.put(alloc, key, {});
    }

    pub fn contains(self: *OpaqueRegistry, raw: ?*anyopaque) bool {
        const key = @intFromPtr(raw orelse return false);
        self.mutex.lock();
        defer self.mutex.unlock();
        return self.map.contains(key);
    }

    pub fn remove(self: *OpaqueRegistry, raw: ?*anyopaque) void {
        const key = @intFromPtr(raw orelse return);
        self.mutex.lock();
        defer self.mutex.unlock();
        _ = self.map.remove(key);
    }
};

pub var d3d12_texture_registry: OpaqueRegistry = .{};
pub var d3d12_texture_view_registry: OpaqueRegistry = .{};
pub var d3d12_sampler_registry: OpaqueRegistry = .{};

pub fn default_texture_view_dimension(tex: *const DoeTexture) u32 {
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
    native.object_add_ref(DoeTexture, tex_raw);
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
            native.doeNativeTextureRelease(tex_raw);
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
            native.doeNativeTextureRelease(tex_raw);
            alloc.destroy(tv);
            return null;
        }
        if ((resolved_dimension == types.WGPUTextureViewDimension_Cube or
            resolved_dimension == types.WGPUTextureViewDimension_CubeArray) and
            ((d.baseArrayLayer % 6) != 0 or (resolved_array_layer_count % 6) != 0))
        {
            native.doeNativeTextureRelease(tex_raw);
            alloc.destroy(tv);
            return null;
        }
        if ((resolved_usage & types.WGPUTextureUsage_StorageBinding) != 0 and
            (resolved_usage & types.WGPUTextureUsage_TextureBinding) != 0)
        {
            native.doeNativeTextureRelease(tex_raw);
            alloc.destroy(tv);
            return null;
        }
        if (wants_storage_only) {
            if (tex.sample_count > 1 or is_depth_format(tex.format) or resolved_mip_level_count != 1) {
                native.doeNativeTextureRelease(tex_raw);
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
                native.doeNativeTextureRelease(tex_raw);
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
        native.doeNativeTextureRelease(tex_raw);
        alloc.destroy(tv);
        return null;
    }
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeTextureDestroy(raw: ?*anyopaque) callconv(.c) void {
    _ = cast(DoeTexture, raw) orelse return;
}

pub export fn doeNativeTextureRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeTexture, raw)) |t| {
        if (!native.object_should_destroy(t)) return;
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
        if (!native.object_should_destroy(tv)) return;
        const texture = tv.tex;
        label_store.remove(raw);
        if (d3d12_texture_view_registry.contains(raw)) {
            d3d12_texture_view_registry.remove(raw);
            if (tv.handle) |handle| d3d12_bridge_release(handle);
            alloc.destroy(tv);
            native.doeNativeTextureRelease(toOpaque(texture));
            return;
        }
        if (tv.tex.vk_id != 0) {
            const vk_render = @import("doe_vulkan_render_native.zig");
            vk_render.vulkan_destroy_texture_view(tv);
            alloc.destroy(tv);
            native.doeNativeTextureRelease(toOpaque(texture));
            return;
        }
        if (tv.handle) |handle| {
            if (tv.tex.mtl == null or handle != tv.tex.mtl) metal_bridge_release(handle);
        }
        alloc.destroy(tv);
        native.doeNativeTextureRelease(toOpaque(texture));
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
        if (!native.object_should_destroy(s)) return;
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
