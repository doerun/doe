const std = @import("std");
const types = @import("../../core/abi/wgpu_types.zig");
const surface_procs_mod = @import("wgpu_surface_procs.zig");
const WebGPUBackend = @import("../../webgpu_ffi.zig").WebGPUBackend;

pub fn createSurface(
    self: *WebGPUBackend,
    descriptor: surface_procs_mod.SurfaceDescriptor,
) !surface_procs_mod.Surface {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    const surface = surface_procs.instance_create_surface(self.core.instance.?, &descriptor);
    if (surface == null) return error.SurfaceCreationFailed;
    return surface;
}

pub fn getSurfaceCapabilities(
    self: *WebGPUBackend,
    surface: surface_procs_mod.Surface,
) !surface_procs_mod.SurfaceCapabilities {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    var capabilities = surface_procs_mod.SurfaceCapabilities{
        .nextInChain = null,
        .usages = types.WGPUTextureUsage_None,
        .formatCount = 0,
        .formats = null,
        .presentModeCount = 0,
        .presentModes = null,
        .alphaModeCount = 0,
        .alphaModes = null,
    };
    const status = surface_procs.surface_get_capabilities(surface, self.core.adapter.?, &capabilities);
    if (status != types.WGPUStatus_Success) return error.SurfaceCapabilitiesFailed;
    return capabilities;
}

pub fn freeSurfaceCapabilities(
    self: *WebGPUBackend,
    capabilities: surface_procs_mod.SurfaceCapabilities,
) void {
    if (surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib)) |surface_procs| {
        surface_procs.surface_capabilities_free_members(capabilities);
    }
}

pub fn configureSurface(
    self: *WebGPUBackend,
    surface: surface_procs_mod.Surface,
    config: surface_procs_mod.SurfaceConfiguration,
) !void {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    surface_procs.surface_configure(surface, &config);
}

pub fn getCurrentSurfaceTexture(
    self: *WebGPUBackend,
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

pub fn presentSurface(self: *WebGPUBackend, surface: surface_procs_mod.Surface) !void {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    const status = surface_procs.surface_present(surface);
    if (status != types.WGPUStatus_Success) return error.SurfacePresentFailed;
}

pub fn unconfigureSurface(self: *WebGPUBackend, surface: surface_procs_mod.Surface) !void {
    const surface_procs = surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib) orelse return error.SurfaceProcUnavailable;
    surface_procs.surface_unconfigure(surface);
}

pub fn releaseSurface(self: *WebGPUBackend, surface: surface_procs_mod.Surface) void {
    if (surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib)) |surface_procs| {
        surface_procs.surface_release(surface);
    }
}
