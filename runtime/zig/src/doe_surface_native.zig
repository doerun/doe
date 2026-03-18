// doe_surface_native.zig — WebGPU Surface C ABI for the Doe Vulkan backend.
//
// Metal surfaces are not exposed through this ABI (Metal uses CAMetalLayer natively).
// Vulkan path routes lifecycle calls to NativeVulkanRuntime surface methods.
//
// Platform VkSurface handles (XCB/Wayland) must be attached via
// doeNativeSurfaceSetXcbHandle / doeNativeSurfaceSetWaylandHandle before
// doeNativeSurfaceConfigure is called to enable a real VkSwapchainKHR.
// Without a platform handle the surface operates in headless mode:
// configure succeeds, acquire returns a placeholder texture, no actual
// GPU image is presented.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");
const vk_surf = @import("backend/vulkan/vulkan_surface.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;

const DoeDevice = native.DoeDevice;
const DoeTexture = native.DoeTexture;
const NativeVulkanRuntime = native.NativeVulkanRuntime;

const MAGIC_SURFACE: u32 = 0xD0E1_0013;

const WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_SUCCESS: u32 = 0x00000001;
const WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_TIMEOUT: u32 = 0x00000002;

pub const DoeSurface = struct {
    pub const TYPE_MAGIC = MAGIC_SURFACE;
    magic: u32 = TYPE_MAGIC,
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
) callconv(.c) void {
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    const model = @import("model.zig");
    rt.configure_surface(model.SurfaceConfigureCommand{
        .handle = surf.handle,
        .width = width,
        .height = height,
        .format = format,
        .usage = usage,
        .alpha_mode = alpha_mode,
        .present_mode = present_mode,
    }) catch |err| {
        std.log.err("doe_surface_native: configure_surface failed: {s}", .{@errorName(err)});
    };
}

/// Acquire the next swapchain image and expose it as a WGPUTexture handle.
/// For headless surfaces the returned texture is a placeholder with no GPU backing.
pub export fn doeNativeSurfaceGetCurrentTexture(
    surf_raw: ?*anyopaque,
    out_texture: ?*?*anyopaque,
    out_suboptimal: ?*u32,
    out_status: ?*u32,
) callconv(.c) void {
    if (out_status) |s| s.* = WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_TIMEOUT;
    if (out_suboptimal) |s| s.* = 0;
    if (out_texture) |t| t.* = null;

    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));

    rt.acquire_surface(surf.handle) catch |err| {
        std.log.err("doe_surface_native: acquire_surface failed: {s}", .{@errorName(err)});
        return;
    };

    if (surf.current_tex) |old| alloc.destroy(old);
    const tex = make(DoeTexture) orelse return;
    tex.* = .{ .vk_runtime_ref = surf.vk_runtime_ref };
    surf.current_tex = tex;
    if (out_texture) |t| t.* = toOpaque(tex);
    if (out_status) |s| s.* = WGPU_SURFACE_GET_CURRENT_TEXTURE_STATUS_SUCCESS;
}

pub export fn doeNativeSurfacePresent(surf_raw: ?*anyopaque) callconv(.c) void {
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    rt.present_surface(surf.handle) catch |err| {
        std.log.err("doe_surface_native: present_surface failed: {s}", .{@errorName(err)});
    };
}

pub export fn doeNativeSurfaceUnconfigure(surf_raw: ?*anyopaque) callconv(.c) void {
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend != .vulkan) return;
    const rt_ptr = surf.vk_runtime_ref orelse return;
    const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
    rt.unconfigure_surface(surf.handle) catch |err| {
        std.log.err("doe_surface_native: unconfigure_surface failed: {s}", .{@errorName(err)});
    };
}

pub export fn doeNativeSurfaceRelease(surf_raw: ?*anyopaque) callconv(.c) void {
    const surf = cast(DoeSurface, surf_raw) orelse return;
    if (surf.backend == .vulkan) {
        if (surf.vk_runtime_ref) |rt_ptr| {
            const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
            rt.release_surface(surf.handle) catch {};
        }
    }
    if (surf.current_tex) |tex| alloc.destroy(tex);
    alloc.destroy(surf);
}
