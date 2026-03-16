const std = @import("std");

pub fn definitions(comptime types: type) type {
    return struct {
        pub const BufferRecord = struct {
            buffer: types.WGPUBuffer,
            size: u64,
            usage: types.WGPUBufferUsage,
        };

        pub const TextureRecord = struct {
            texture: types.WGPUTexture,
            width: u32,
            height: u32,
            depth_or_array_layers: u32,
            format: types.WGPUTextureFormat,
            usage: types.WGPUTextureUsage,
            dimension: types.WGPUTextureDimension,
            sample_count: u32,
        };

        pub const DispatchPassArtifacts = struct {
            pass_bind_groups: []?types.WGPUBindGroup,
            group_layouts: []types.WGPUBindGroupLayout,
            texture_views: []types.WGPUTextureView,
        };

        pub const RenderPipelineCacheEntry = struct {
            shader_module: types.WGPUShaderModule,
            pipeline: types.WGPURenderPipeline,
        };

        pub const RenderTextureViewCacheEntry = struct {
            texture: types.WGPUTexture,
            view: types.WGPUTextureView,
            width: u32,
            height: u32,
            format: types.WGPUTextureFormat,
        };

        pub const DispatchPassGroup = struct {
            layout_entries: std.ArrayList(types.WGPUBindGroupLayoutEntry),
            bind_entries: std.ArrayList(types.WGPUBindGroupEntry),
        };

        pub const RequestState = struct {
            done: bool = false,
            status: types.WGPURequestAdapterStatus = .@"error",
            adapter: types.WGPUAdapter = null,
            status_message: []const u8 = "",
        };

        pub const DeviceRequestState = struct {
            done: bool = false,
            status: types.WGPURequestDeviceStatus = .@"error",
            device: types.WGPUDevice = null,
            status_message: []const u8 = "",
        };
    };
}
