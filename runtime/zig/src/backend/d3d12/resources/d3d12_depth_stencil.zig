const std = @import("std");
const dc = @import("../d3d12_constants.zig");

// --- DXGI depth/stencil format values ---
// These map directly to DXGI_FORMAT enum values for depth/stencil surfaces.
const DXGI_FORMAT_D16_UNORM: u32 = 55;
const DXGI_FORMAT_D32_FLOAT: u32 = 40;
const DXGI_FORMAT_D24_UNORM_S8_UINT: u32 = 45;
const DXGI_FORMAT_D32_FLOAT_S8X24_UINT: u32 = 20;

// --- WebGPU depth texture format identifiers ---
// From the WebGPU spec GPUTextureFormat enum.
const WGPU_DEPTH16_UNORM: u32 = 0x0000002D;
const WGPU_DEPTH24_PLUS: u32 = 0x0000002E;
const WGPU_DEPTH24_PLUS_STENCIL8: u32 = 0x0000002F;
const WGPU_DEPTH32_FLOAT: u32 = 0x00000030;
const WGPU_DEPTH32_FLOAT_STENCIL8: u32 = 0x00000031;
const WGPU_STENCIL8: u32 = 0x0000002C;

// Single DSV descriptor per depth/stencil state; more can be added if MRT
// depth targets are needed in the future.
const DSV_HEAP_SIZE: u32 = 1;

// D3D12_RESOURCE_STATE_DEPTH_WRITE — required initial state for DSV-bound resources.
const RESOURCE_STATE_DEPTH_WRITE: c_int = 0x00000010;

// --- Bridge extern declarations ---

extern fn d3d12_bridge_device_create_texture_2d(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    mip_levels: u32,
    format: u32,
    usage_flags: u32,
) callconv(.c) ?*anyopaque;

extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

extern fn d3d12_bridge_device_create_dsv_heap(
    device: ?*anyopaque,
    num_descriptors: u32,
) callconv(.c) ?*anyopaque;

extern fn d3d12_bridge_device_create_dsv(
    device: ?*anyopaque,
    resource: ?*anyopaque,
    dsv_heap: ?*anyopaque,
    index: u32,
    format: u32,
) callconv(.c) void;

extern fn d3d12_bridge_device_create_depth_texture(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    format: u32,
) callconv(.c) ?*anyopaque;

// --- Format mapping ---

/// Translate a WebGPU depth/stencil format to the corresponding DXGI format.
/// Returns 0 for unrecognized formats so the caller can fail explicitly.
pub fn map_wgpu_depth_format(format: u32) u32 {
    return switch (format) {
        WGPU_DEPTH16_UNORM => DXGI_FORMAT_D16_UNORM,
        WGPU_STENCIL8 => DXGI_FORMAT_D24_UNORM_S8_UINT,
        WGPU_DEPTH24_PLUS => DXGI_FORMAT_D24_UNORM_S8_UINT,
        WGPU_DEPTH24_PLUS_STENCIL8 => DXGI_FORMAT_D24_UNORM_S8_UINT,
        WGPU_DEPTH32_FLOAT => DXGI_FORMAT_D32_FLOAT,
        WGPU_DEPTH32_FLOAT_STENCIL8 => DXGI_FORMAT_D32_FLOAT_S8X24_UINT,
        else => 0,
    };
}

/// True when `format` is any WebGPU depth or depth/stencil format.
pub fn is_depth_format(format: u32) bool {
    return switch (format) {
        WGPU_DEPTH16_UNORM,
        WGPU_STENCIL8,
        WGPU_DEPTH24_PLUS,
        WGPU_DEPTH24_PLUS_STENCIL8,
        WGPU_DEPTH32_FLOAT,
        WGPU_DEPTH32_FLOAT_STENCIL8,
        => true,
        else => false,
    };
}

/// True when the format carries a stencil channel in addition to depth.
pub fn has_stencil(format: u32) bool {
    return switch (format) {
        WGPU_DEPTH24_PLUS_STENCIL8,
        WGPU_STENCIL8,
        WGPU_DEPTH32_FLOAT_STENCIL8,
        => true,
        else => false,
    };
}

// --- Depth/stencil state ---

pub const DepthStencilState = struct {
    dsv_heap: ?*anyopaque = null,
    depth_texture: ?*anyopaque = null,
    cached_width: u32 = 0,
    cached_height: u32 = 0,
    cached_format: u32 = 0,

    /// Ensure a depth/stencil texture and DSV exist that match the requested
    /// dimensions and format.  Re-creates both when any parameter changes so
    /// the caller can bind the DSV heap directly to the pipeline.
    pub fn ensure_depth_texture(
        self: *DepthStencilState,
        device: ?*anyopaque,
        width: u32,
        height: u32,
        format: u32,
    ) !void {
        if (width == 0 or height == 0) return error.InvalidArgument;

        const dxgi_format = map_wgpu_depth_format(format);
        if (dxgi_format == 0) return error.UnsupportedFeature;

        // Reuse the existing texture when nothing changed.
        if (self.depth_texture != null and
            self.cached_width == width and
            self.cached_height == height and
            self.cached_format == format)
        {
            return;
        }

        // Tear down previous resources before allocating new ones.
        self.release_resources();

        const texture = d3d12_bridge_device_create_depth_texture(
            device,
            width,
            height,
            dxgi_format,
        ) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(texture);

        const heap = d3d12_bridge_device_create_dsv_heap(
            device,
            DSV_HEAP_SIZE,
        ) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(heap);

        d3d12_bridge_device_create_dsv(device, texture, heap, 0, dxgi_format);

        self.depth_texture = texture;
        self.dsv_heap = heap;
        self.cached_width = width;
        self.cached_height = height;
        self.cached_format = format;
    }

    /// Return the DSV descriptor heap, or null if no depth texture has been
    /// created yet.
    pub fn get_dsv_heap(self: *DepthStencilState) ?*anyopaque {
        return self.dsv_heap;
    }

    /// Release all D3D12 resources held by this state.
    pub fn deinit(self: *DepthStencilState) void {
        self.release_resources();
    }

    // -- internal helpers --

    fn release_resources(self: *DepthStencilState) void {
        if (self.depth_texture) |tex| {
            d3d12_bridge_release(tex);
            self.depth_texture = null;
        }
        if (self.dsv_heap) |heap| {
            d3d12_bridge_release(heap);
            self.dsv_heap = null;
        }
        self.cached_width = 0;
        self.cached_height = 0;
        self.cached_format = 0;
    }
};

// --- Tests ---

test "map_wgpu_depth_format returns correct DXGI values" {
    try std.testing.expectEqual(DXGI_FORMAT_D16_UNORM, map_wgpu_depth_format(WGPU_DEPTH16_UNORM));
    try std.testing.expectEqual(DXGI_FORMAT_D24_UNORM_S8_UINT, map_wgpu_depth_format(WGPU_DEPTH24_PLUS));
    try std.testing.expectEqual(DXGI_FORMAT_D24_UNORM_S8_UINT, map_wgpu_depth_format(WGPU_DEPTH24_PLUS_STENCIL8));
    try std.testing.expectEqual(DXGI_FORMAT_D32_FLOAT, map_wgpu_depth_format(WGPU_DEPTH32_FLOAT));
    try std.testing.expectEqual(DXGI_FORMAT_D32_FLOAT_S8X24_UINT, map_wgpu_depth_format(WGPU_DEPTH32_FLOAT_STENCIL8));
}

test "map_wgpu_depth_format returns 0 for unknown format" {
    try std.testing.expectEqual(@as(u32, 0), map_wgpu_depth_format(0xFFFF));
}

test "is_depth_format identifies all depth formats" {
    try std.testing.expect(is_depth_format(WGPU_DEPTH16_UNORM));
    try std.testing.expect(is_depth_format(WGPU_DEPTH24_PLUS));
    try std.testing.expect(is_depth_format(WGPU_DEPTH24_PLUS_STENCIL8));
    try std.testing.expect(is_depth_format(WGPU_DEPTH32_FLOAT));
    try std.testing.expect(is_depth_format(WGPU_DEPTH32_FLOAT_STENCIL8));
    try std.testing.expect(!is_depth_format(0));
    try std.testing.expect(!is_depth_format(0x00000001));
}

test "has_stencil distinguishes stencil formats" {
    try std.testing.expect(!has_stencil(WGPU_DEPTH16_UNORM));
    try std.testing.expect(!has_stencil(WGPU_DEPTH24_PLUS));
    try std.testing.expect(has_stencil(WGPU_DEPTH24_PLUS_STENCIL8));
    try std.testing.expect(!has_stencil(WGPU_DEPTH32_FLOAT));
    try std.testing.expect(has_stencil(WGPU_DEPTH32_FLOAT_STENCIL8));
}
