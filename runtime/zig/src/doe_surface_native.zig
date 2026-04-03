// doe_surface_native.zig — WebGPU Surface C ABI for the Doe Vulkan backend.
//
// Metal surfaces are not exposed through this ABI (Metal uses CAMetalLayer natively).
// Vulkan path routes lifecycle calls to NativeVulkanRuntime surface methods.
//
// Platform VkSurface handles (XCB/Wayland) must be attached via
// doeNativeSurfaceSetXcbHandle / doeNativeSurfaceSetWaylandHandle before
// doeNativeSurfaceConfigure is called to enable a real VkSwapchainKHR.
// Headless placeholder presentation is not allowed on this path; configure
// and acquire fail explicitly until a real platform surface is attached.

const std = @import("std");
const builtin = @import("builtin");
const has_vulkan = (builtin.os.tag == .linux);
const native = @import("doe_wgpu_native.zig");
const vk_surf = if (has_vulkan) @import("backend/vulkan/vulkan_surface.zig") else struct {};

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const model = @import("model_webgpu_types.zig");

const DoeDevice = native.DoeDevice;
const DoeTexture = native.DoeTexture;
const NativeVulkanRuntime = native.NativeVulkanRuntime;

const MAGIC_SURFACE: u32 = 0xD0E1_0013;

const WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_SUCCESS: u32 = 0x00000001;
const WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_TIMEOUT: u32 = 0x00000002;

pub const DoeSurface = struct {
    pub const TYPE_MAGIC = MAGIC_SURFACE;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    backend: native.BackendKind = .metal,
    handle: u64 = 0,
    vk_runtime_ref: ?*anyopaque = null,
    current_tex: ?*DoeTexture = null,
};

// ============================================================
// Instance: createSurface
// ============================================================

/// Create a surface associated with the given device.
/// For Vulkan, registers the surface in the runtime's surface map (headless by default).
/// Attach a platform window handle before configure to enable real swapchain presentation.
/// `dev_raw` is required for the Vulkan path; pass null for Metal (returns null).
pub export fn doeNativeInstanceCreateSurface(
    inst_raw: ?*anyopaque,
    desc_raw: ?*anyopaque,
    dev_raw: ?*anyopaque,
) callconv(.c) ?*anyopaque {
    if (comptime !has_vulkan) return null;
    _ = inst_raw;
    _ = desc_raw;
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    if (dev.backend != .vulkan) return null;

    const surf = make(DoeSurface) orelse return null;
    const handle: u64 = @intFromPtr(surf);
    surf.* = .{
        .backend = .vulkan,
        .handle = handle,
    };

    const rt = native.device_vk_runtime(dev) orelse {
        alloc.destroy(surf);
        return null;
    };
    surf.vk_runtime_ref = @ptrCast(rt);

    rt.create_surface(handle) catch |err| {
        std.log.err("doe_surface_native: create_surface failed: {s}", .{@errorName(err)});
        alloc.destroy(surf);
        return null;
    };
    return toOpaque(surf);
}

// ============================================================
// Platform VkSurface handle setters
// Must be called before doeNativeSurfaceConfigure for windowed rendering.
// ============================================================

/// Attach an XCB window to the surface. Enables real swapchain on Linux.
pub export fn doeNativeSurfaceSetXcbHandle(
    surf_raw: ?*anyopaque,
    xcb_connection: ?*anyopaque,
    xcb_window: u32,
) callconv(.c) void {
    if (comptime !has_vulkan) return;
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    const vk_handle = vk_surf.create_xcb_surface(rt.instance, xcb_connection, xcb_window) catch |err| {
        std.log.err("doe_surface_native: create_xcb_surface failed: {s}", .{@errorName(err)});
        return;
    };
    if (rt.surfaces.getPtr(surf.handle)) |s| {
        s.vk_surface = vk_handle;
        s.platform = .xcb;
    }
}

/// Attach a Wayland surface to the surface. Enables real swapchain on Linux.
pub export fn doeNativeSurfaceSetWaylandHandle(
    surf_raw: ?*anyopaque,
    wl_display: ?*anyopaque,
    wl_surface: ?*anyopaque,
) callconv(.c) void {
    if (comptime !has_vulkan) return;
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    const vk_handle = vk_surf.create_wayland_surface(rt.instance, wl_display, wl_surface) catch |err| {
        std.log.err("doe_surface_native: create_wayland_surface failed: {s}", .{@errorName(err)});
        return;
    };
    if (rt.surfaces.getPtr(surf.handle)) |s| {
        s.vk_surface = vk_handle;
        s.platform = .wayland;
    }
}

// ============================================================
// Surface configure / acquire / present / unconfigure / release
// ============================================================

pub export fn doeNativeSurfaceConfigure(
    surf_raw: ?*anyopaque,
    width: u32,
    height: u32,
    format: u32,
    usage: u32,
    alpha_mode: u32,
    present_mode: u32,
    tone_mapping_mode: u32,
) callconv(.c) void {
    if (comptime !has_vulkan) return;
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    rt.configure_surface(model.SurfaceConfigureCommand{
        .handle = surf.handle,
        .width = width,
        .height = height,
        .format = format,
        .usage = usage,
        .alpha_mode = alpha_mode,
        .present_mode = present_mode,
        .tone_mapping_mode = tone_mapping_mode,
    }) catch |err| {
        std.log.err("doe_surface_native: configure_surface failed: {s}", .{@errorName(err)});
    };
}

/// Acquire the next swapchain image and expose it as a WGPUTexture handle.
pub export fn doeNativeSurfaceGetCurrentTexture(
    surf_raw: ?*anyopaque,
    out_texture: ?*?*anyopaque,
    out_suboptimal: ?*u32,
    out_status: ?*u32,
) callconv(.c) void {
    if (out_status) |s| s.* = WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_TIMEOUT;
    if (out_suboptimal) |s| s.* = 0;
    if (out_texture) |t| t.* = null;
    if (comptime !has_vulkan) return;

    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));

    rt.acquire_surface(surf.handle) catch |err| {
        std.log.err("doe_surface_native: acquire_surface failed: {s}", .{@errorName(err)});
        return;
    };

    const surface_state = rt.surfaces.getPtr(surf.handle) orelse return;

    if (surf.current_tex) |old| alloc.destroy(old);
    const tex = make(DoeTexture) orelse return;
    tex.* = .{
        .format = surface_state.format,
        .width = surface_state.swapchain_extent.width,
        .height = surface_state.swapchain_extent.height,
        .depth_or_array_layers = 1,
        .dimension = model.WGPUTextureDimension_2D,
        .mip_level_count = 1,
        .sample_count = 1,
        .usage = surface_state.usage,
        .texture_binding_view_dimension = model.WGPUTextureViewDimension_2D,
        .vk_runtime_ref = surf.vk_runtime_ref,
    };
    surf.current_tex = tex;
    if (out_texture) |t| t.* = toOpaque(tex);
    if (out_suboptimal) |s| s.* = if (surface_state.last_acquire_suboptimal or surface_state.last_present_suboptimal) 1 else 0;
    if (out_status) |s| s.* = WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_SUCCESS;
}

pub export fn doeNativeSurfacePresent(surf_raw: ?*anyopaque) callconv(.c) void {
    if (comptime !has_vulkan) return;
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    rt.present_surface(surf.handle) catch |err| {
        std.log.err("doe_surface_native: present_surface failed: {s}", .{@errorName(err)});
    };
}

pub export fn doeNativeSurfaceUnconfigure(surf_raw: ?*anyopaque) callconv(.c) void {
    if (comptime !has_vulkan) return;
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    rt.unconfigure_surface(surf.handle) catch |err| {
        std.log.err("doe_surface_native: unconfigure_surface failed: {s}", .{@errorName(err)});
    };
    if (surf.current_tex) |tex| {
        alloc.destroy(tex);
        surf.current_tex = null;
    }
}

pub export fn doeNativeSurfaceRelease(surf_raw: ?*anyopaque) callconv(.c) void {
    if (comptime !has_vulkan) return;
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (!native.object_should_destroy(surf)) return;
    if (surf.backend == .vulkan) {
        if (surf.vk_runtime_ref) |rt_ptr| {
            const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
            rt.release_surface(surf.handle) catch |err| {
                std.debug.print("warn: doe_surface_native: surface release: {s}\n", .{@errorName(err)});
            };
        }
    }
    if (surf.current_tex) |tex| alloc.destroy(tex);
    alloc.destroy(surf);
}

// ============================================================
// Capabilities query
// ============================================================

const surface_procs = @import("full/surface/wgpu_surface_procs.zig");

// Default surface format for Doe Vulkan surfaces.
const DOE_SURFACE_DEFAULT_FORMAT: u32 = model.WGPUTextureFormat_BGRA8Unorm;

// Present mode constants matching WGPUPresentMode values.
const DOE_PRESENT_MODE_FIFO: u32 = 0x00000003;

// Composite alpha mode constants matching WGPUCompositeAlphaMode values.
const DOE_COMPOSITE_ALPHA_MODE_OPAQUE: u32 = 0x00000002;

// Static capability arrays — returned by pointer, never freed.
const DEFAULT_FORMATS = [_]u32{DOE_SURFACE_DEFAULT_FORMAT};
const DEFAULT_PRESENT_MODES = [_]u32{DOE_PRESENT_MODE_FIFO};
const DEFAULT_ALPHA_MODES = [_]u32{DOE_COMPOSITE_ALPHA_MODE_OPAQUE};

/// Minimal capabilities query: reports BGRA8Unorm, Fifo, Opaque.
pub export fn doeNativeSurfaceGetCapabilities(
    surf_raw: ?*anyopaque,
    _: ?*anyopaque,
    out: ?*surface_procs.SurfaceCapabilities,
) callconv(.c) u32 {
    const surf = cast(DoeSurface, surf_raw) orelse return 0;
    _ = surf;
    const caps = out orelse return 0;
    caps.nextInChain = null;
    caps.usages = 0x00000010; // WGPUTextureUsage_RenderAttachment
    caps.formatCount = DEFAULT_FORMATS.len;
    caps.formats = &DEFAULT_FORMATS;
    caps.presentModeCount = DEFAULT_PRESENT_MODES.len;
    caps.presentModes = &DEFAULT_PRESENT_MODES;
    caps.alphaModeCount = DEFAULT_ALPHA_MODES.len;
    caps.alphaModes = &DEFAULT_ALPHA_MODES;
    return 1; // WGPUStatus_Success
}

/// Free members from a capabilities query. Static arrays need no deallocation.
pub export fn doeNativeSurfaceCapabilitiesFreeMembers(_: surface_procs.SurfaceCapabilities) callconv(.c) void {
    // Static arrays — nothing to free.
}

// ============================================================
// ABI bridges: translate WebGPU C ABI struct signatures to
// the flattened parameter signatures used by native functions.
// ============================================================

/// ABI bridge for wgpuInstanceCreateSurface.
/// The native implementation takes an extra dev_raw parameter; the C ABI does not.
/// We pass null for dev_raw (device association happens at configure time).
pub fn doeAbiBridgeInstanceCreateSurface(
    inst_raw: ?*anyopaque,
    desc_raw: *const surface_procs.SurfaceDescriptor,
) callconv(.c) ?*anyopaque {
    return doeNativeInstanceCreateSurface(inst_raw, @ptrCast(@constCast(desc_raw)), null);
}

/// ABI bridge for wgpuSurfaceConfigure.
/// Unpacks SurfaceConfiguration fields into the flattened native call.
pub fn doeAbiBridgeSurfaceConfigure(
    surf_raw: ?*anyopaque,
    config: *const surface_procs.SurfaceConfiguration,
) callconv(.c) void {
    doeNativeSurfaceConfigure(
        surf_raw,
        config.width,
        config.height,
        config.format,
        @truncate(config.usage), // WGPUTextureUsage is u64; native uses u32
        config.alphaMode,
        config.presentMode,
        0, // tone_mapping_mode — not in C ABI struct; default to standard
    );
}

/// ABI bridge for wgpuSurfaceGetCurrentTexture.
/// Unpacks the SurfaceTexture output struct from the flattened native outputs.
pub fn doeAbiBridgeSurfaceGetCurrentTexture(
    surf_raw: ?*anyopaque,
    out: *surface_procs.SurfaceTexture,
) callconv(.c) void {
    var tex_ptr: ?*anyopaque = null;
    var suboptimal: u32 = 0;
    var status: u32 = 0;
    doeNativeSurfaceGetCurrentTexture(surf_raw, &tex_ptr, &suboptimal, &status);
    out.texture = tex_ptr;
    out.status = status;
}

/// ABI bridge for wgpuSurfacePresent.
/// Native returns void; C ABI expects u32 (WGPUStatus).
pub fn doeAbiBridgeSurfacePresent(surf_raw: ?*anyopaque) callconv(.c) u32 {
    doeNativeSurfacePresent(surf_raw);
    return 1; // WGPUStatus_Success
}
