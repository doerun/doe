const std = @import("std");
const types = @import("wgpu_types.zig");

const FnDeviceCreateSampler = *const fn (types.WGPUDevice, ?*const anyopaque) callconv(.c) types.WGPUSampler;
const FnSamplerRelease = *const fn (types.WGPUSampler) callconv(.c) void;
const FnQueueWriteTexture = *const fn (
    types.WGPUQueue,
    *const types.WGPUTexelCopyTextureInfo,
    ?*const anyopaque,
    usize,
    *const types.WGPUTexelCopyBufferLayout,
    *const types.WGPUExtent3D,
) callconv(.c) void;
const FnTextureDestroy = *const fn (types.WGPUTexture) callconv(.c) void;
const FnTextureGetWidth = *const fn (types.WGPUTexture) callconv(.c) u32;
const FnTextureGetHeight = *const fn (types.WGPUTexture) callconv(.c) u32;
const FnTextureGetDepthOrArrayLayers = *const fn (types.WGPUTexture) callconv(.c) u32;
const FnTextureGetDimension = *const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureDimension;
const FnTextureGetFormat = *const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureFormat;
const FnTextureGetMipLevelCount = *const fn (types.WGPUTexture) callconv(.c) u32;
const FnTextureGetSampleCount = *const fn (types.WGPUTexture) callconv(.c) u32;
const FnTextureGetTextureBindingViewDimension = *const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureViewDimension;
const FnTextureGetUsage = *const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureUsage;

pub const TextureInfo = struct {
    width: u32,
    height: u32,
    depth_or_array_layers: u32,
    dimension: types.WGPUTextureDimension,
    format: types.WGPUTextureFormat,
    mip_level_count: u32,
    sample_count: u32,
    view_dimension: types.WGPUTextureViewDimension,
    usage: types.WGPUTextureUsage,
};

pub const TextureProcs = struct {
    device_create_sampler: FnDeviceCreateSampler,
    sampler_release: FnSamplerRelease,
    queue_write_texture: FnQueueWriteTexture,
    texture_destroy: FnTextureDestroy,
    texture_get_width: FnTextureGetWidth,
    texture_get_height: FnTextureGetHeight,
    texture_get_depth_or_array_layers: FnTextureGetDepthOrArrayLayers,
    texture_get_dimension: FnTextureGetDimension,
    texture_get_format: FnTextureGetFormat,
    texture_get_mip_level_count: FnTextureGetMipLevelCount,
    texture_get_sample_count: FnTextureGetSampleCount,
    texture_get_texture_binding_view_dimension: FnTextureGetTextureBindingViewDimension,
    texture_get_usage: FnTextureGetUsage,
};

fn loadProc(comptime T: type, lib: std.DynLib, comptime name: [:0]const u8) ?T {
    var mutable = lib;
    return mutable.lookup(T, name);
}

pub fn loadTextureProcs(dyn_lib: ?std.DynLib) ?TextureProcs {
    const lib = dyn_lib orelse return null;
    return .{
        .device_create_sampler = loadProc(FnDeviceCreateSampler, lib, "wgpuDeviceCreateSampler") orelse return null,
        .sampler_release = loadProc(FnSamplerRelease, lib, "wgpuSamplerRelease") orelse return null,
        .queue_write_texture = loadProc(FnQueueWriteTexture, lib, "wgpuQueueWriteTexture") orelse return null,
        .texture_destroy = loadProc(FnTextureDestroy, lib, "wgpuTextureDestroy") orelse return null,
        .texture_get_width = loadProc(FnTextureGetWidth, lib, "wgpuTextureGetWidth") orelse return null,
        .texture_get_height = loadProc(FnTextureGetHeight, lib, "wgpuTextureGetHeight") orelse return null,
        .texture_get_depth_or_array_layers = loadProc(FnTextureGetDepthOrArrayLayers, lib, "wgpuTextureGetDepthOrArrayLayers") orelse return null,
        .texture_get_dimension = loadProc(FnTextureGetDimension, lib, "wgpuTextureGetDimension") orelse return null,
        .texture_get_format = loadProc(FnTextureGetFormat, lib, "wgpuTextureGetFormat") orelse return null,
        .texture_get_mip_level_count = loadProc(FnTextureGetMipLevelCount, lib, "wgpuTextureGetMipLevelCount") orelse return null,
        .texture_get_sample_count = loadProc(FnTextureGetSampleCount, lib, "wgpuTextureGetSampleCount") orelse return null,
        .texture_get_texture_binding_view_dimension = loadProc(FnTextureGetTextureBindingViewDimension, lib, "wgpuTextureGetTextureBindingViewDimension") orelse return null,
        .texture_get_usage = loadProc(FnTextureGetUsage, lib, "wgpuTextureGetUsage") orelse return null,
    };
}

pub fn queryTextureInfo(procs: TextureProcs, texture: types.WGPUTexture) TextureInfo {
    return .{
        .width = procs.texture_get_width(texture),
        .height = procs.texture_get_height(texture),
        .depth_or_array_layers = procs.texture_get_depth_or_array_layers(texture),
        .dimension = procs.texture_get_dimension(texture),
        .format = procs.texture_get_format(texture),
        .mip_level_count = procs.texture_get_mip_level_count(texture),
        .sample_count = procs.texture_get_sample_count(texture),
        .view_dimension = procs.texture_get_texture_binding_view_dimension(texture),
        .usage = procs.texture_get_usage(texture),
    };
}
