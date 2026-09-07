const std = @import("std");
const abi_core = @import("../../core/abi/wgpu_core_base_types.zig");
const abi_texture = @import("../../core/abi/wgpu_texture_base_types.zig");

pub const Surface = ?*anyopaque;
pub const SurfaceSourceMetalLayerSType: u32 = 0x00000004;
pub const SurfaceSourceWindowsHWNDSType: u32 = 0x00000005;
pub const SurfaceSourceXlibWindowSType: u32 = 0x00000006;
pub const SurfaceSourceWaylandSurfaceSType: u32 = 0x00000007;
pub const SurfaceSourceAndroidNativeWindowSType: u32 = 0x00000008;
pub const SurfaceSourceXCBWindowSType: u32 = 0x00000009;

pub const ChainedStruct = extern struct {
    next: ?*const ChainedStruct,
    sType: u32,
};

pub const SurfaceDescriptor = extern struct {
    nextInChain: ?*const ChainedStruct,
    label: abi_core.WGPUStringView,
};

pub const SurfaceSourceMetalLayer = extern struct {
    chain: ChainedStruct,
    layer: ?*anyopaque,
};

pub const SurfaceSourceWaylandSurface = extern struct {
    chain: ChainedStruct,
    display: ?*anyopaque,
    surface: ?*anyopaque,
};

pub const SurfaceSourceXCBWindow = extern struct {
    chain: ChainedStruct,
    connection: ?*anyopaque,
    window: u32,
};

pub const SurfaceSourceXlibWindow = extern struct {
    chain: ChainedStruct,
    display: ?*anyopaque,
    window: u64,
};

pub const SurfaceCapabilities = extern struct {
    nextInChain: ?*anyopaque,
    usages: abi_texture.WGPUTextureUsage,
    formatCount: usize,
    formats: ?[*]const abi_texture.WGPUTextureFormat,
    presentModeCount: usize,
    presentModes: ?[*]const u32,
    alphaModeCount: usize,
    alphaModes: ?[*]const u32,
};

pub const SurfaceConfiguration = extern struct {
    nextInChain: ?*anyopaque,
    device: abi_core.WGPUDevice,
    format: abi_texture.WGPUTextureFormat,
    usage: abi_texture.WGPUTextureUsage,
    width: u32,
    height: u32,
    viewFormatCount: usize,
    viewFormats: ?[*]const abi_texture.WGPUTextureFormat,
    alphaMode: u32,
    presentMode: u32,
};

pub const SurfaceTexture = extern struct {
    nextInChain: ?*anyopaque,
    texture: abi_core.WGPUTexture,
    status: u32,
};

const FnInstanceCreateSurface = *const fn (abi_core.WGPUInstance, *const SurfaceDescriptor) callconv(.c) Surface;
const FnSurfaceGetCapabilities = *const fn (Surface, abi_core.WGPUAdapter, *SurfaceCapabilities) callconv(.c) u32;
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

const LoadState = enum {
    uninitialized,
    unavailable,
    ready,
};

var load_state: LoadState = .uninitialized;
var cached_procs: SurfaceProcs = undefined;

fn loadProc(comptime T: type, lib: std.DynLib, comptime name: [:0]const u8) ?T {
    var mutable = lib;
    return mutable.lookup(T, name);
}

pub fn loadSurfaceProcs(dyn_lib: ?std.DynLib) ?SurfaceProcs {
    switch (load_state) {
        .ready => return cached_procs,
        .unavailable => return null,
        .uninitialized => {},
    }
    const lib = dyn_lib orelse return null;
    const loaded = SurfaceProcs{
        .instance_create_surface = loadProc(FnInstanceCreateSurface, lib, "wgpuInstanceCreateSurface") orelse return null,
        .surface_get_capabilities = loadProc(FnSurfaceGetCapabilities, lib, "wgpuSurfaceGetCapabilities") orelse return null,
        .surface_configure = loadProc(FnSurfaceConfigure, lib, "wgpuSurfaceConfigure") orelse return null,
        .surface_get_current_texture = loadProc(FnSurfaceGetCurrentTexture, lib, "wgpuSurfaceGetCurrentTexture") orelse return null,
        .surface_present = loadProc(FnSurfacePresent, lib, "wgpuSurfacePresent") orelse return null,
        .surface_unconfigure = loadProc(FnSurfaceUnconfigure, lib, "wgpuSurfaceUnconfigure") orelse return null,
        .surface_release = loadProc(FnSurfaceRelease, lib, "wgpuSurfaceRelease") orelse return null,
        .surface_capabilities_free_members = loadProc(FnSurfaceCapabilitiesFreeMembers, lib, "wgpuSurfaceCapabilitiesFreeMembers") orelse return null,
    };
    cached_procs = loaded;
    load_state = .ready;
    return loaded;
}
