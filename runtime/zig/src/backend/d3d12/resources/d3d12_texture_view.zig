const std = @import("std");
const model = @import("../../../model.zig");
const common_timing = @import("../../common/timing.zig");

// --- Bridge externs ---

extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_device_create_srv_texture_2d(device: ?*anyopaque, resource: ?*anyopaque, heap: ?*anyopaque, index: u32, format: u32, aspect: u32, base_mip: u32, mip_count: u32, base_array_layer: u32, array_layer_count: u32) callconv(.c) void;
extern fn d3d12_bridge_device_create_srv_texture_cube(device: ?*anyopaque, resource: ?*anyopaque, heap: ?*anyopaque, index: u32, format: u32, aspect: u32, base_mip: u32, mip_count: u32, base_array_layer: u32, array_layer_count: u32) callconv(.c) void;
extern fn d3d12_bridge_device_create_srv_texture_3d(device: ?*anyopaque, resource: ?*anyopaque, heap: ?*anyopaque, index: u32, format: u32, aspect: u32, base_mip: u32, mip_count: u32) callconv(.c) void;
extern fn d3d12_bridge_device_create_uav_texture_2d(device: ?*anyopaque, resource: ?*anyopaque, heap: ?*anyopaque, index: u32, format: u32, mip_slice: u32) callconv(.c) void;

// --- View dimension constants (WebGPU GPUTextureViewDimension) ---

const VIEW_DIMENSION_1D: u32 = 1;
const VIEW_DIMENSION_2D: u32 = 2;
const VIEW_DIMENSION_2D_ARRAY: u32 = 3;
const VIEW_DIMENSION_CUBE: u32 = 4;
const VIEW_DIMENSION_CUBE_ARRAY: u32 = 5;
const VIEW_DIMENSION_3D: u32 = 6;

// --- Texture aspect constants (WebGPU GPUTextureAspect) ---

const TEXTURE_ASPECT_ALL: u32 = 0;
const TEXTURE_ASPECT_STENCIL_ONLY: u32 = 1;
const TEXTURE_ASPECT_DEPTH_ONLY: u32 = 2;

fn normalize_aspect(aspect: u32) ?u32 {
    return switch (aspect) {
        TEXTURE_ASPECT_ALL, model.WGPUTextureAspect_All => TEXTURE_ASPECT_ALL,
        TEXTURE_ASPECT_STENCIL_ONLY, model.WGPUTextureAspect_StencilOnly => TEXTURE_ASPECT_STENCIL_ONLY,
        TEXTURE_ASPECT_DEPTH_ONLY, model.WGPUTextureAspect_DepthOnly => TEXTURE_ASPECT_DEPTH_ONLY,
        else => null,
    };
}

fn texture_aspect_supported(format: u32, aspect: u32) bool {
    const normalized = normalize_aspect(aspect) orelse return false;
    return switch (normalized) {
        TEXTURE_ASPECT_ALL => true,
        TEXTURE_ASPECT_DEPTH_ONLY => switch (format) {
            model.WGPUTextureFormat_Stencil8 => false,
            model.WGPUTextureFormat_Depth16Unorm, model.WGPUTextureFormat_Depth24Plus, model.WGPUTextureFormat_Depth24PlusStencil8, model.WGPUTextureFormat_Depth32Float, model.WGPUTextureFormat_Depth32FloatStencil8 => true,
            else => false,
        },
        TEXTURE_ASPECT_STENCIL_ONLY => switch (format) {
            model.WGPUTextureFormat_Stencil8, model.WGPUTextureFormat_Depth24PlusStencil8, model.WGPUTextureFormat_Depth32FloatStencil8 => true,
            else => false,
        },
        else => false,
    };
}

fn texture_supports_storage_binding(format: u32) bool {
    return switch (format) {
        model.WGPUTextureFormat_Stencil8, model.WGPUTextureFormat_Depth16Unorm, model.WGPUTextureFormat_Depth24Plus, model.WGPUTextureFormat_Depth24PlusStencil8, model.WGPUTextureFormat_Depth32Float, model.WGPUTextureFormat_Depth32FloatStencil8, model.WGPUTextureFormat_BGRA8Unorm, model.WGPUTextureFormat_BGRA8UnormSrgb, model.WGPUTextureFormat_RGB10A2Uint, model.WGPUTextureFormat_RGB10A2Unorm, model.WGPUTextureFormat_RG11B10Ufloat, model.WGPUTextureFormat_RGB9E5Ufloat, model.WGPUTextureFormat_BC1RGBAUnorm, model.WGPUTextureFormat_BC1RGBAUnormSrgb, model.WGPUTextureFormat_BC2RGBAUnorm, model.WGPUTextureFormat_BC2RGBAUnormSrgb, model.WGPUTextureFormat_BC3RGBAUnorm, model.WGPUTextureFormat_BC3RGBAUnormSrgb, model.WGPUTextureFormat_BC4RUnorm, model.WGPUTextureFormat_BC4RSnorm, model.WGPUTextureFormat_BC5RGUnorm, model.WGPUTextureFormat_BC5RGSnorm, model.WGPUTextureFormat_BC6HRGBUfloat, model.WGPUTextureFormat_BC6HRGBFloat, model.WGPUTextureFormat_BC7RGBAUnorm, model.WGPUTextureFormat_BC7RGBAUnormSrgb, model.WGPUTextureFormat_ETC2RGB8Unorm, model.WGPUTextureFormat_ETC2RGB8UnormSrgb, model.WGPUTextureFormat_ETC2RGB8A1Unorm, model.WGPUTextureFormat_ETC2RGB8A1UnormSrgb, model.WGPUTextureFormat_ETC2RGBA8Unorm, model.WGPUTextureFormat_ETC2RGBA8UnormSrgb, model.WGPUTextureFormat_EACR11Unorm, model.WGPUTextureFormat_EACR11Snorm, model.WGPUTextureFormat_EACRG11Unorm, model.WGPUTextureFormat_EACRG11Snorm, model.WGPUTextureFormat_ASTC4x4Unorm, model.WGPUTextureFormat_ASTC4x4UnormSrgb, model.WGPUTextureFormat_ASTC5x4Unorm, model.WGPUTextureFormat_ASTC5x4UnormSrgb, model.WGPUTextureFormat_ASTC5x5Unorm, model.WGPUTextureFormat_ASTC5x5UnormSrgb, model.WGPUTextureFormat_ASTC6x5Unorm, model.WGPUTextureFormat_ASTC6x5UnormSrgb => false,
        model.WGPUTextureFormat_ASTC6x6Unorm, model.WGPUTextureFormat_ASTC6x6UnormSrgb, model.WGPUTextureFormat_ASTC8x5Unorm, model.WGPUTextureFormat_ASTC8x5UnormSrgb, model.WGPUTextureFormat_ASTC8x6Unorm, model.WGPUTextureFormat_ASTC8x6UnormSrgb, model.WGPUTextureFormat_ASTC8x8Unorm, model.WGPUTextureFormat_ASTC8x8UnormSrgb, model.WGPUTextureFormat_ASTC10x5Unorm, model.WGPUTextureFormat_ASTC10x5UnormSrgb, model.WGPUTextureFormat_ASTC10x6Unorm, model.WGPUTextureFormat_ASTC10x6UnormSrgb, model.WGPUTextureFormat_ASTC10x8Unorm, model.WGPUTextureFormat_ASTC10x8UnormSrgb, model.WGPUTextureFormat_ASTC10x10Unorm, model.WGPUTextureFormat_ASTC10x10UnormSrgb, model.WGPUTextureFormat_ASTC12x10Unorm, model.WGPUTextureFormat_ASTC12x10UnormSrgb, model.WGPUTextureFormat_ASTC12x12Unorm, model.WGPUTextureFormat_ASTC12x12UnormSrgb => false,
        else => true,
    };
}

// --- D3D12 SRV dimension values (D3D12_SRV_DIMENSION) ---
// These map WebGPU view dimensions to the D3D12 enum for CreateShaderResourceView.

const SRV_DIMENSION_TEXTURE1D: u32 = 3;
const SRV_DIMENSION_TEXTURE2D: u32 = 4;
const SRV_DIMENSION_TEXTURE2DARRAY: u32 = 5;
const SRV_DIMENSION_TEXTURECUBE: u32 = 8;
const SRV_DIMENSION_TEXTURECUBEARRAY: u32 = 9;
const SRV_DIMENSION_TEXTURE3D: u32 = 7;

pub const TextureViewEntry = struct {
    handle: u64,
    texture_handle: u64,
    format: u32,
    dimension: u32,
    base_mip_level: u32,
    mip_level_count: u32,
    base_array_layer: u32,
    array_layer_count: u32,
    aspect: u32,
    descriptor_index: u32, // index into CBV/SRV/UAV heap
};

pub const TextureViewState = struct {
    map: std.AutoHashMapUnmanaged(u64, TextureViewEntry) = .{},

    /// Creates a texture view and writes the corresponding SRV descriptor
    /// into the CBV/SRV/UAV heap at `descriptor_index`.
    ///
    /// The bridge call dispatches to the correct D3D12 SRV variant based
    /// on `dimension`. 1D and array variants fall through to the 2D path
    /// because D3D12 uses the same descriptor structure for 1D/2D when
    /// array size is 1; the bridge layer handles the SRV_DIMENSION enum.
    pub fn create_view(
        self: *TextureViewState,
        allocator: std.mem.Allocator,
        device: ?*anyopaque,
        handle: u64,
        texture_handle: u64,
        texture_resource: ?*anyopaque,
        format: u32,
        dimension: u32,
        base_mip: u32,
        mip_count: u32,
        base_layer: u32,
        layer_count: u32,
        aspect: u32,
        texture_usage: u64,
        descriptor_heap: ?*anyopaque,
        descriptor_index: u32,
    ) !u64 {
        const encode_start = common_timing.now_ns();

        if (!texture_aspect_supported(format, aspect)) return error.UnsupportedFeature;

        // Storage bindings use UAV descriptors; sampled bindings use SRVs.
        if ((texture_usage & model.WGPUTextureUsage_StorageBinding) != 0) {
            if (!texture_supports_storage_binding(format)) return error.UnsupportedFeature;
            const normalized_aspect = normalize_aspect(aspect) orelse return error.UnsupportedFeature;
            if (normalized_aspect != TEXTURE_ASPECT_ALL) return error.UnsupportedFeature;
            if (dimension != VIEW_DIMENSION_2D) return error.UnsupportedFeature;
            d3d12_bridge_device_create_uav_texture_2d(
                device,
                texture_resource,
                descriptor_heap,
                descriptor_index,
                format,
                base_mip,
            );
        } else switch (dimension) {
            VIEW_DIMENSION_1D, VIEW_DIMENSION_2D, VIEW_DIMENSION_2D_ARRAY => {
                d3d12_bridge_device_create_srv_texture_2d(
                    device,
                    texture_resource,
                    descriptor_heap,
                    descriptor_index,
                    format,
                    aspect,
                    base_mip,
                    mip_count,
                    base_layer,
                    layer_count,
                );
            },
            VIEW_DIMENSION_CUBE, VIEW_DIMENSION_CUBE_ARRAY => {
                if ((layer_count % 6) != 0) return error.UnsupportedFeature;
                d3d12_bridge_device_create_srv_texture_cube(
                    device,
                    texture_resource,
                    descriptor_heap,
                    descriptor_index,
                    format,
                    aspect,
                    base_mip,
                    mip_count,
                    base_layer,
                    layer_count,
                );
            },
            VIEW_DIMENSION_3D => {
                d3d12_bridge_device_create_srv_texture_3d(
                    device,
                    texture_resource,
                    descriptor_heap,
                    descriptor_index,
                    format,
                    aspect,
                    base_mip,
                    mip_count,
                );
            },
            else => return error.UnsupportedFeature,
        }

        const entry = TextureViewEntry{
            .handle = handle,
            .texture_handle = texture_handle,
            .format = format,
            .dimension = dimension,
            .base_mip_level = base_mip,
            .mip_level_count = mip_count,
            .base_array_layer = base_layer,
            .array_layer_count = layer_count,
            .aspect = aspect,
            .descriptor_index = descriptor_index,
        };

        self.map.put(allocator, handle, entry) catch return error.InvalidState;

        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn destroy_view(self: *TextureViewState, handle: u64) void {
        // Descriptor heap slots are not individually freed; they are
        // reclaimed when the heap is reset or the device is destroyed.
        _ = self.map.fetchRemove(handle);
    }

    pub fn get_view(self: *const TextureViewState, handle: u64) ?TextureViewEntry {
        return self.map.get(handle);
    }

    pub fn deinit(self: *TextureViewState, allocator: std.mem.Allocator) void {
        self.map.deinit(allocator);
    }
};

/// Maps a WebGPU texture view dimension to the corresponding
/// D3D12_SRV_DIMENSION enum value for CreateShaderResourceView.
pub fn map_view_dimension_to_srv(dimension: u32) u32 {
    return switch (dimension) {
        VIEW_DIMENSION_1D => SRV_DIMENSION_TEXTURE1D,
        VIEW_DIMENSION_2D => SRV_DIMENSION_TEXTURE2D,
        VIEW_DIMENSION_2D_ARRAY => SRV_DIMENSION_TEXTURE2DARRAY,
        VIEW_DIMENSION_CUBE => SRV_DIMENSION_TEXTURECUBE,
        VIEW_DIMENSION_CUBE_ARRAY => SRV_DIMENSION_TEXTURECUBEARRAY,
        VIEW_DIMENSION_3D => SRV_DIMENSION_TEXTURE3D,
        // Unknown dimensions fall back to 2D; callers should validate
        // dimension before reaching this point.
        else => SRV_DIMENSION_TEXTURE2D,
    };
}
