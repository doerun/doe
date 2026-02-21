const std = @import("std");
const types = @import("wgpu_types.zig");

pub const Surface = ?*anyopaque;

pub const SurfaceDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: types.WGPUStringView,
};

pub const SurfaceCapabilities = extern struct {
    nextInChain: ?*anyopaque,
    usages: types.WGPUTextureUsage,
    formatCount: usize,
    formats: ?[*]const types.WGPUTextureFormat,
    presentModeCount: usize,
    presentModes: ?[*]const u32,
    alphaModeCount: usize,
    alphaModes: ?[*]const u32,
};

pub const SurfaceConfiguration = extern struct {
    nextInChain: ?*anyopaque,
    device: types.WGPUDevice,
    format: types.WGPUTextureFormat,
    usage: types.WGPUTextureUsage,
    width: u32,
    height: u32,
    viewFormatCount: usize,
    viewFormats: ?[*]const types.WGPUTextureFormat,
    alphaMode: u32,
    presentMode: u32,
    desiredMaximumFrameLatency: u32,
};

pub const SurfaceTexture = extern struct {
    nextInChain: ?*anyopaque,
    texture: types.WGPUTexture,
    status: u32,
};

const FnInstanceCreateSurface = *const fn (types.WGPUInstance, *const SurfaceDescriptor) callconv(.c) Surface;
const FnSurfaceGetCapabilities = *const fn (Surface, types.WGPUAdapter, *SurfaceCapabilities) callconv(.c) u32;
const FnSurfaceConfigure = *const fn (Surface, *const SurfaceConfiguration) callconv(.c) void;
const FnSurfaceGetCurrentTexture = *const fn (Surface, *SurfaceTexture) callconv(.c) void;
const FnSurfacePresent = *const fn (Surface) callconv(.c) u32;
const FnSurfaceUnconfigure = *const fn (Surface) callconv(.c) void;
const FnSurfaceRelease = *const fn (Surface) callconv(.c) void;
const FnSurfaceCapabilitiesFreeMembers = *const fn (SurfaceCapabilities) callconv(.c) void;

pub const SurfaceProcs = struct {
    instance_create_surface: FnInstanceCreateSurface,
    surface_get_capabilities: FnSurfaceGetCapabilities,
    surface_configure: FnSurfaceConfigure,
    surface_get_current_texture: FnSurfaceGetCurrentTexture,
    surface_present: FnSurfacePresent,
    surface_unconfigure: FnSurfaceUnconfigure,
    surface_release: FnSurfaceRelease,
    surface_capabilities_free_members: FnSurfaceCapabilitiesFreeMembers,
};

fn loadProc(comptime T: type, lib: std.DynLib, comptime name: [:0]const u8) ?T {
    var mutable = lib;
    return mutable.lookup(T, name);
}

pub fn loadSurfaceProcs(dyn_lib: ?std.DynLib) ?SurfaceProcs {
    const lib = dyn_lib orelse return null;
    return .{
        .instance_create_surface = loadProc(FnInstanceCreateSurface, lib, "wgpuInstanceCreateSurface") orelse return null,
        .surface_get_capabilities = loadProc(FnSurfaceGetCapabilities, lib, "wgpuSurfaceGetCapabilities") orelse return null,
        .surface_configure = loadProc(FnSurfaceConfigure, lib, "wgpuSurfaceConfigure") orelse return null,
        .surface_get_current_texture = loadProc(FnSurfaceGetCurrentTexture, lib, "wgpuSurfaceGetCurrentTexture") orelse return null,
        .surface_present = loadProc(FnSurfacePresent, lib, "wgpuSurfacePresent") orelse return null,
        .surface_unconfigure = loadProc(FnSurfaceUnconfigure, lib, "wgpuSurfaceUnconfigure") orelse return null,
        .surface_release = loadProc(FnSurfaceRelease, lib, "wgpuSurfaceRelease") orelse return null,
        .surface_capabilities_free_members = loadProc(FnSurfaceCapabilitiesFreeMembers, lib, "wgpuSurfaceCapabilitiesFreeMembers") orelse return null,
    };
}
