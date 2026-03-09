const model = @import("../../model.zig");
const types = @import("../../core/abi/wgpu_types.zig");
const loader = @import("../../core/abi/wgpu_loader.zig");
const resources = @import("../../core/resource/wgpu_resources.zig");
const surface_procs_mod = @import("wgpu_surface_procs.zig");
const ffi = @import("../../webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

const SURFACE_TEXTURE_STATUS_SUCCESS: u32 = 0x00000001;
const SURFACE_ALPHA_MODE_AUTO: u32 = 0x00000001;
const SURFACE_PRESENT_MODE_FIFO: u32 = 0x00000002;

pub fn executeSurfaceCreate(self: *Backend, surface_cmd: model.SurfaceCreateCommand) !types.NativeExecutionResult {
    if (self.full.surfaces.contains(surface_cmd.handle)) {
        return .{ .status = .unsupported, .status_message = "surface handle already exists" };
    }
    const surface = self.createSurface(.{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    }) catch {
        return .{ .status = .@"error", .status_message = "surface creation failed" };
    };
    try self.full.surfaces.put(surface_cmd.handle, .{ .surface = surface });
    return .{ .status = .ok, .status_message = "surface created" };
}

pub fn executeSurfaceCapabilities(self: *Backend, surface_cmd: model.SurfaceCapabilitiesCommand) !types.NativeExecutionResult {
    const managed = self.full.surfaces.get(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    const capabilities = self.getSurfaceCapabilities(managed.surface) catch {
        return .{ .status = .@"error", .status_message = "surface capabilities query failed" };
    };
    defer self.freeSurfaceCapabilities(capabilities);
    if (capabilities.formatCount == 0 or capabilities.presentModeCount == 0) {
        return .{ .status = .@"error", .status_message = "surface capabilities are empty" };
    }
    return .{ .status = .ok, .status_message = "surface capabilities queried" };
}

pub fn executeSurfaceConfigure(self: *Backend, surface_cmd: model.SurfaceConfigureCommand) !types.NativeExecutionResult {
    const managed = self.full.surfaces.getPtr(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (managed.acquired_texture != null) {
        self.core.procs.?.wgpuTextureRelease(managed.acquired_texture);
        managed.acquired_texture = null;
    }
    const config = surface_procs_mod.SurfaceConfiguration{
        .nextInChain = null,
        .device = self.core.device.?,
        .format = resources.normalizeTextureFormat(surface_cmd.format),
        .usage = if (surface_cmd.usage == 0) types.WGPUTextureUsage_RenderAttachment else surface_cmd.usage,
        .width = surface_cmd.width,
        .height = surface_cmd.height,
        .viewFormatCount = 0,
        .viewFormats = null,
        .alphaMode = if (surface_cmd.alpha_mode == 0) SURFACE_ALPHA_MODE_AUTO else surface_cmd.alpha_mode,
        .presentMode = if (surface_cmd.present_mode == 0) SURFACE_PRESENT_MODE_FIFO else surface_cmd.present_mode,
        .desiredMaximumFrameLatency = surface_cmd.desired_maximum_frame_latency,
    };
    self.configureSurface(managed.surface, config) catch {
        return .{ .status = .@"error", .status_message = "surface configure failed" };
    };
    managed.configured = true;
    return .{ .status = .ok, .status_message = "surface configured" };
}

pub fn executeSurfaceAcquire(self: *Backend, surface_cmd: model.SurfaceAcquireCommand) !types.NativeExecutionResult {
    const managed = self.full.surfaces.getPtr(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (!managed.configured) return .{ .status = .unsupported, .status_message = "surface must be configured before acquire" };
    if (managed.acquired_texture != null) return .{ .status = .unsupported, .status_message = "surface already has an acquired texture" };

    const surface_texture = self.getCurrentSurfaceTexture(managed.surface) catch {
        return .{ .status = .@"error", .status_message = "surface acquire failed" };
    };
    if (surface_texture.status != SURFACE_TEXTURE_STATUS_SUCCESS or surface_texture.texture == null) {
        return .{ .status = .@"error", .status_message = "surface acquire returned non-success status" };
    }
    managed.acquired_texture = surface_texture.texture;
    managed.last_texture_status = surface_texture.status;
    return .{ .status = .ok, .status_message = "surface texture acquired" };
}

pub fn executeSurfacePresent(self: *Backend, surface_cmd: model.SurfacePresentCommand) !types.NativeExecutionResult {
    const managed = self.full.surfaces.getPtr(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (!managed.configured) return .{ .status = .unsupported, .status_message = "surface must be configured before present" };
    if (managed.acquired_texture == null) return .{ .status = .unsupported, .status_message = "surface present requires an acquired texture" };

    self.presentSurface(managed.surface) catch {
        return .{ .status = .@"error", .status_message = "surface present failed" };
    };
    self.core.procs.?.wgpuTextureRelease(managed.acquired_texture);
    managed.acquired_texture = null;
    return .{ .status = .ok, .status_message = "surface presented" };
}

pub fn executeSurfaceUnconfigure(self: *Backend, surface_cmd: model.SurfaceUnconfigureCommand) !types.NativeExecutionResult {
    const managed = self.full.surfaces.getPtr(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (managed.acquired_texture != null) {
        self.core.procs.?.wgpuTextureRelease(managed.acquired_texture);
        managed.acquired_texture = null;
    }
    self.unconfigureSurface(managed.surface) catch {
        return .{ .status = .@"error", .status_message = "surface unconfigure failed" };
    };
    managed.configured = false;
    return .{ .status = .ok, .status_message = "surface unconfigured" };
}

pub fn executeSurfaceRelease(self: *Backend, surface_cmd: model.SurfaceReleaseCommand) !types.NativeExecutionResult {
    const removed = self.full.surfaces.fetchRemove(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (removed.value.acquired_texture != null) {
        self.core.procs.?.wgpuTextureRelease(removed.value.acquired_texture);
    }
    if (removed.value.configured) {
        _ = self.unconfigureSurface(removed.value.surface) catch {};
    }
    self.releaseSurface(removed.value.surface);
    return .{ .status = .ok, .status_message = "surface released" };
}
