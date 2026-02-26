const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const texture_procs_mod = @import("wgpu_texture_procs.zig");
const surface_procs_mod = @import("wgpu_surface_procs.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;
const ManagedSurface = ffi.ManagedSurface;

const SURFACE_TEXTURE_STATUS_SUCCESS: u32 = 0x00000001;
const SURFACE_ALPHA_MODE_AUTO: u32 = 0x00000001;
const SURFACE_PRESENT_MODE_FIFO: u32 = 0x00000002;

const SamplerDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: types.WGPUStringView,
    addressModeU: u32,
    addressModeV: u32,
    addressModeW: u32,
    magFilter: u32,
    minFilter: u32,
    mipmapFilter: u32,
    lodMinClamp: f32,
    lodMaxClamp: f32,
    compare: u32,
    maxAnisotropy: u16,
};

pub fn executeSamplerCreate(self: *Backend, sampler_cmd: model.SamplerCreateCommand) !types.NativeExecutionResult {
    const texture_procs = texture_procs_mod.loadTextureProcs(self.dyn_lib) orelse return error.TextureProcUnavailable;
    if (self.samplers.get(sampler_cmd.handle)) |existing| {
        texture_procs.sampler_release(existing);
        _ = self.samplers.remove(sampler_cmd.handle);
    }

    const descriptor = SamplerDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .addressModeU = sampler_cmd.address_mode_u,
        .addressModeV = sampler_cmd.address_mode_v,
        .addressModeW = sampler_cmd.address_mode_w,
        .magFilter = sampler_cmd.mag_filter,
        .minFilter = sampler_cmd.min_filter,
        .mipmapFilter = sampler_cmd.mipmap_filter,
        .lodMinClamp = sampler_cmd.lod_min_clamp,
        .lodMaxClamp = sampler_cmd.lod_max_clamp,
        .compare = sampler_cmd.compare,
        .maxAnisotropy = sampler_cmd.max_anisotropy,
    };
    const sampler = texture_procs.device_create_sampler(self.device.?, @ptrCast(&descriptor));
    if (sampler == null) {
        return .{ .status = .@"error", .status_message = "sampler_create failed" };
    }
    try self.samplers.put(sampler_cmd.handle, sampler);
    return .{ .status = .ok, .status_message = "sampler created" };
}

pub fn executeSamplerDestroy(self: *Backend, sampler_cmd: model.SamplerDestroyCommand) !types.NativeExecutionResult {
    const texture_procs = texture_procs_mod.loadTextureProcs(self.dyn_lib) orelse return error.TextureProcUnavailable;
    const removed = self.samplers.fetchRemove(sampler_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "sampler handle not found" };
    };
    texture_procs.sampler_release(removed.value);
    return .{ .status = .ok, .status_message = "sampler destroyed" };
}

pub fn executeTextureWrite(self: *Backend, texture_cmd: model.TextureWriteCommand) !types.NativeExecutionResult {
    const texture_procs = texture_procs_mod.loadTextureProcs(self.dyn_lib) orelse return error.TextureProcUnavailable;
    const required_usage = types.WGPUTextureUsage_CopyDst;
    const texture = try resources.getOrCreateTexture(self, texture_cmd.texture, required_usage);

    const bytes_per_texel = try textureBytesPerTexel(texture_cmd.texture.format);
    const width_u64 = @as(u64, texture_cmd.texture.width);
    const height_u64 = @as(u64, texture_cmd.texture.height);
    const depth_u64 = @as(u64, texture_cmd.texture.depth_or_array_layers);
    const min_bytes_per_row = std.math.mul(u64, width_u64, bytes_per_texel) catch return error.InvalidTextureWriteLayout;
    const bytes_per_row = if (texture_cmd.texture.bytes_per_row == 0)
        min_bytes_per_row
    else
        @as(u64, texture_cmd.texture.bytes_per_row);
    if (bytes_per_row < min_bytes_per_row) return error.InvalidTextureWriteLayout;
    const rows_per_image = if (texture_cmd.texture.rows_per_image == 0)
        height_u64
    else
        @as(u64, texture_cmd.texture.rows_per_image);
    if (rows_per_image < height_u64) return error.InvalidTextureWriteLayout;
    const copy_bytes = std.math.mul(u64, bytes_per_row, rows_per_image) catch return error.InvalidTextureWriteLayout;
    const total_bytes = std.math.mul(u64, copy_bytes, depth_u64) catch return error.InvalidTextureWriteLayout;
    const needed = std.math.add(u64, texture_cmd.texture.offset, total_bytes) catch return error.InvalidTextureWriteLayout;
    if (needed > texture_cmd.data.len) return error.InvalidTextureWriteLayout;

    texture_procs.queue_write_texture(
        self.queue.?,
        &types.WGPUTexelCopyTextureInfo{
            .texture = texture,
            .mipLevel = texture_cmd.texture.mip_level,
            .origin = .{ .x = 0, .y = 0, .z = 0 },
            .aspect = loader.normalizeTextureAspect(texture_cmd.texture.aspect),
        },
        texture_cmd.data.ptr,
        texture_cmd.data.len,
        &types.WGPUTexelCopyBufferLayout{
            .offset = texture_cmd.texture.offset,
            .bytesPerRow = @as(u32, @intCast(bytes_per_row)),
            .rowsPerImage = @as(u32, @intCast(rows_per_image)),
        },
        &types.WGPUExtent3D{
            .width = texture_cmd.texture.width,
            .height = texture_cmd.texture.height,
            .depthOrArrayLayers = texture_cmd.texture.depth_or_array_layers,
        },
    );
    return .{ .status = .ok, .status_message = "texture write submitted" };
}

pub fn executeTextureQuery(self: *Backend, texture_cmd: model.TextureQueryCommand) !types.NativeExecutionResult {
    const texture_procs = texture_procs_mod.loadTextureProcs(self.dyn_lib) orelse return error.TextureProcUnavailable;
    if (self.textures.getPtr(texture_cmd.handle)) |record| {
        const info = texture_procs_mod.queryTextureInfo(texture_procs, record.texture);
        if (info.width == 0 or info.height == 0 or info.depth_or_array_layers == 0) {
            return .{ .status = .@"error", .status_message = "texture query returned invalid dimensions" };
        }
        if (texture_cmd.expected_width) |expected| {
            if (info.width != expected) return .{ .status = .unsupported, .status_message = "texture query width mismatch" };
        }
        if (texture_cmd.expected_height) |expected| {
            if (info.height != expected) return .{ .status = .unsupported, .status_message = "texture query height mismatch" };
        }
        if (texture_cmd.expected_depth_or_array_layers) |expected| {
            if (info.depth_or_array_layers != expected) return .{ .status = .unsupported, .status_message = "texture query depth mismatch" };
        }
        if (texture_cmd.expected_format) |expected| {
            if (info.format != expected) return .{ .status = .unsupported, .status_message = "texture query format mismatch" };
        }
        if (texture_cmd.expected_dimension) |expected| {
            if (info.dimension != expected) return .{ .status = .unsupported, .status_message = "texture query dimension mismatch" };
        }
        if (texture_cmd.expected_view_dimension) |expected| {
            if (info.view_dimension != expected) return .{ .status = .unsupported, .status_message = "texture query view-dimension mismatch" };
        }
        if (texture_cmd.expected_sample_count) |expected| {
            if (info.sample_count != expected) return .{ .status = .unsupported, .status_message = "texture query sample-count mismatch" };
        }
        if (texture_cmd.expected_usage) |expected| {
            if ((info.usage & expected) != expected) return .{ .status = .unsupported, .status_message = "texture query usage mismatch" };
        }
        record.width = info.width;
        record.height = info.height;
        record.depth_or_array_layers = info.depth_or_array_layers;
        record.format = info.format;
        record.dimension = info.dimension;
        record.sample_count = info.sample_count;
        record.usage = info.usage;
        return .{ .status = .ok, .status_message = "texture query completed" };
    }
    return .{ .status = .unsupported, .status_message = "texture handle not found" };
}

pub fn executeTextureDestroy(self: *Backend, texture_cmd: model.TextureDestroyCommand) !types.NativeExecutionResult {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const texture_procs = texture_procs_mod.loadTextureProcs(self.dyn_lib) orelse return error.TextureProcUnavailable;
    const removed = self.textures.fetchRemove(texture_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "texture handle not found" };
    };
    removeTextureViewsForTexture(self, removed.value.texture);
    texture_procs.texture_destroy(removed.value.texture);
    procs.wgpuTextureRelease(removed.value.texture);
    return .{ .status = .ok, .status_message = "texture destroyed" };
}

pub fn executeSurfaceCreate(self: *Backend, surface_cmd: model.SurfaceCreateCommand) !types.NativeExecutionResult {
    if (self.surfaces.contains(surface_cmd.handle)) {
        return .{ .status = .unsupported, .status_message = "surface handle already exists" };
    }
    const surface = self.createSurface(.{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    }) catch {
        return .{ .status = .@"error", .status_message = "surface creation failed" };
    };
    try self.surfaces.put(surface_cmd.handle, .{ .surface = surface });
    return .{ .status = .ok, .status_message = "surface created" };
}

pub fn executeSurfaceCapabilities(self: *Backend, surface_cmd: model.SurfaceCapabilitiesCommand) !types.NativeExecutionResult {
    const managed = self.surfaces.get(surface_cmd.handle) orelse {
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
    const managed = self.surfaces.getPtr(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (managed.acquired_texture != null) {
        self.procs.?.wgpuTextureRelease(managed.acquired_texture);
        managed.acquired_texture = null;
    }
    const config = surface_procs_mod.SurfaceConfiguration{
        .nextInChain = null,
        .device = self.device.?,
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
    const managed = self.surfaces.getPtr(surface_cmd.handle) orelse {
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
    const managed = self.surfaces.getPtr(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (!managed.configured) return .{ .status = .unsupported, .status_message = "surface must be configured before present" };
    if (managed.acquired_texture == null) return .{ .status = .unsupported, .status_message = "surface present requires an acquired texture" };

    self.presentSurface(managed.surface) catch {
        return .{ .status = .@"error", .status_message = "surface present failed" };
    };
    self.procs.?.wgpuTextureRelease(managed.acquired_texture);
    managed.acquired_texture = null;
    return .{ .status = .ok, .status_message = "surface presented" };
}

pub fn executeSurfaceUnconfigure(self: *Backend, surface_cmd: model.SurfaceUnconfigureCommand) !types.NativeExecutionResult {
    const managed = self.surfaces.getPtr(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (managed.acquired_texture != null) {
        self.procs.?.wgpuTextureRelease(managed.acquired_texture);
        managed.acquired_texture = null;
    }
    self.unconfigureSurface(managed.surface) catch {
        return .{ .status = .@"error", .status_message = "surface unconfigure failed" };
    };
    managed.configured = false;
    return .{ .status = .ok, .status_message = "surface unconfigured" };
}

pub fn executeSurfaceRelease(self: *Backend, surface_cmd: model.SurfaceReleaseCommand) !types.NativeExecutionResult {
    const removed = self.surfaces.fetchRemove(surface_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "surface handle not found" };
    };
    if (removed.value.acquired_texture != null) {
        self.procs.?.wgpuTextureRelease(removed.value.acquired_texture);
    }
    if (removed.value.configured) {
        _ = self.unconfigureSurface(removed.value.surface) catch {};
    }
    self.releaseSurface(removed.value.surface);
    return .{ .status = .ok, .status_message = "surface released" };
}

fn textureBytesPerTexel(format: types.WGPUTextureFormat) !u64 {
    return switch (format) {
        model.WGPUTextureFormat_R8Unorm,
        model.WGPUTextureFormat_R8Snorm,
        model.WGPUTextureFormat_R8Uint,
        model.WGPUTextureFormat_R8Sint,
        => 1,
        model.WGPUTextureFormat_R16Unorm,
        model.WGPUTextureFormat_R16Snorm,
        model.WGPUTextureFormat_R16Uint,
        model.WGPUTextureFormat_R16Sint,
        model.WGPUTextureFormat_R16Float,
        model.WGPUTextureFormat_RG8Unorm,
        model.WGPUTextureFormat_RG8Snorm,
        model.WGPUTextureFormat_RG8Uint,
        model.WGPUTextureFormat_RG8Sint,
        => 2,
        model.WGPUTextureFormat_R32Float,
        model.WGPUTextureFormat_R32Uint,
        model.WGPUTextureFormat_R32Sint,
        model.WGPUTextureFormat_RG16Unorm,
        model.WGPUTextureFormat_RG16Snorm,
        model.WGPUTextureFormat_RG16Uint,
        model.WGPUTextureFormat_RG16Sint,
        model.WGPUTextureFormat_RG16Float,
        model.WGPUTextureFormat_RGBA8Unorm,
        model.WGPUTextureFormat_RGBA8UnormSrgb,
        model.WGPUTextureFormat_RGBA8Snorm,
        model.WGPUTextureFormat_RGBA8Uint,
        model.WGPUTextureFormat_RGBA8Sint,
        model.WGPUTextureFormat_BGRA8Unorm,
        model.WGPUTextureFormat_BGRA8UnormSrgb,
        model.WGPUTextureFormat_Depth24Plus,
        model.WGPUTextureFormat_Depth24PlusStencil8,
        model.WGPUTextureFormat_Depth32Float,
        model.WGPUTextureFormat_Depth32FloatStencil8,
        => 4,
        else => error.UnsupportedTextureFormat,
    };
}

fn removeTextureViewsForTexture(self: *Backend, texture: types.WGPUTexture) void {
    const procs = self.procs orelse return;

    var target_keys = std.ArrayList(u64).empty;
    defer target_keys.deinit(self.allocator);
    var target_it = self.render_target_view_cache.iterator();
    while (target_it.next()) |entry| {
        if (entry.value_ptr.texture == texture) target_keys.append(self.allocator, entry.key_ptr.*) catch return;
    }
    for (target_keys.items) |key| {
        if (self.render_target_view_cache.fetchRemove(key)) |removed| {
            procs.wgpuTextureViewRelease(removed.value.view);
        }
    }

    var depth_keys = std.ArrayList(u64).empty;
    defer depth_keys.deinit(self.allocator);
    var depth_it = self.render_depth_view_cache.iterator();
    while (depth_it.next()) |entry| {
        if (entry.value_ptr.texture == texture) depth_keys.append(self.allocator, entry.key_ptr.*) catch return;
    }
    for (depth_keys.items) |key| {
        if (self.render_depth_view_cache.fetchRemove(key)) |removed| {
            procs.wgpuTextureViewRelease(removed.value.view);
        }
    }
}
