const model = @import("../../model.zig");
const types = @import("../../core/abi/wgpu_types.zig");
const loader = @import("../../core/abi/wgpu_loader.zig");
const texture_procs_mod = @import("../../wgpu_texture_procs.zig");
const ffi = @import("../../webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

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
    const texture_procs = texture_procs_mod.loadTextureProcs(self.core.dyn_lib) orelse return error.TextureProcUnavailable;
    if (self.full.samplers.get(sampler_cmd.handle)) |existing| {
        texture_procs.sampler_release(existing);
        _ = self.full.samplers.remove(sampler_cmd.handle);
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
    const sampler = texture_procs.device_create_sampler(self.core.device.?, @ptrCast(&descriptor));
    if (sampler == null) {
        return .{ .status = .@"error", .status_message = "sampler_create failed" };
    }
    try self.full.samplers.put(sampler_cmd.handle, sampler);
    return .{ .status = .ok, .status_message = "sampler created" };
}

pub fn executeSamplerDestroy(self: *Backend, sampler_cmd: model.SamplerDestroyCommand) !types.NativeExecutionResult {
    const texture_procs = texture_procs_mod.loadTextureProcs(self.core.dyn_lib) orelse return error.TextureProcUnavailable;
    const removed = self.full.samplers.fetchRemove(sampler_cmd.handle) orelse {
        return .{ .status = .unsupported, .status_message = "sampler handle not found" };
    };
    texture_procs.sampler_release(removed.value);
    return .{ .status = .ok, .status_message = "sampler destroyed" };
}
