const std = @import("std");
const abi_core = @import("../../core/abi/wgpu_core_base_types.zig");
const abi_texture = @import("../../core/abi/wgpu_texture_base_types.zig");
const surface_procs_mod = @import("wgpu_surface_procs.zig");

pub fn createSurface(
    self: anytype,
    descriptor: surface_procs_mod.SurfaceDescriptor,
) !surface_procs_mod.Surface {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    const surface = surface_procs.instance_create_surface(self.core.instance.?, &descriptor);
    if (surface == null) return error.SurfaceCreationFailed;
    return surface;
}

pub fn getSurfaceCapabilities(
    self: anytype,
    surface: surface_procs_mod.Surface,
) !surface_procs_mod.SurfaceCapabilities {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    var capabilities = surface_procs_mod.SurfaceCapabilities{
        .nextInChain = null,
        .usages = abi_texture.WGPUTextureUsage_None,
        .formatCount = 0,
        .formats = null,
        .presentModeCount = 0,
        .presentModes = null,
        .alphaModeCount = 0,
        .alphaModes = null,
    };
    const status = surface_procs.surface_get_capabilities(surface, self.core.adapter.?, &capabilities);
    if (status != abi_core.WGPUStatus_Success) return error.SurfaceCapabilitiesFailed;
    return capabilities;
}

pub fn freeSurfaceCapabilities(
    self: anytype,
    capabilities: surface_procs_mod.SurfaceCapabilities,
) void {
    if (surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib)) |surface_procs| {
        surface_procs.surface_capabilities_free_members(capabilities);
    }
}

pub fn configureSurface(
    self: anytype,
    surface: surface_procs_mod.Surface,
    config: surface_procs_mod.SurfaceConfiguration,
) !void {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    surface_procs.surface_configure(surface, &config);
}

pub fn getCurrentSurfaceTexture(
    self: anytype,
    surface: surface_procs_mod.Surface,
) !surface_procs_mod.SurfaceTexture {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    var surface_texture = surface_procs_mod.SurfaceTexture{
        .nextInChain = null,
        .texture = null,
        .status = 0,
    };
    surface_procs.surface_get_current_texture(surface, &surface_texture);
    return surface_texture;
}

pub fn presentSurface(self: anytype, surface: surface_procs_mod.Surface) !void {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    const status = surface_procs.surface_present(surface);
    if (status != abi_core.WGPUStatus_Success) return error.SurfacePresentFailed;
}

pub fn unconfigureSurface(self: anytype, surface: surface_procs_mod.Surface) !void {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    surface_procs.surface_unconfigure(surface);
}

pub fn releaseSurface(self: anytype, surface: surface_procs_mod.Surface) void {
    if (surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib)) |surface_procs| {
        surface_procs.surface_release(surface);
    }
}
