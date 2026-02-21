const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const render_assets = @import("wgpu_render_assets.zig");
const texture_procs_mod = @import("wgpu_texture_procs.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

pub const RENDER_UNIFORM_BINDING_INDEX: u32 = 0;
pub const RENDER_TEXTURE_BINDING_INDEX: u32 = 1;
pub const RENDER_SAMPLER_BINDING_INDEX: u32 = 2;

const RENDER_UNIFORM_BUFFER_HANDLE: u64 = 0x8C9F_2600_0000_0000;
pub const RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES: u64 = 3 * @sizeOf(f32);
pub const RENDER_UNIFORM_DYNAMIC_STRIDE_BYTES: u64 = 256;
pub const RENDER_UNIFORM_DYNAMIC_SLOT_COUNT: u64 = 64;
pub const RENDER_UNIFORM_TOTAL_BYTES: u64 = RENDER_UNIFORM_DYNAMIC_STRIDE_BYTES * RENDER_UNIFORM_DYNAMIC_SLOT_COUNT;
const RENDER_SAMPLED_TEXTURE_HANDLE: u64 = 0x8C9F_2800_0000_0000;

pub const RenderUniformBindingResources = struct {
    bind_group_layout: types.WGPUBindGroupLayout,
    bind_group: types.WGPUBindGroup,
};

pub fn getOrCreateRenderUniformBindingResources(self: *Backend) !RenderUniformBindingResources {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const texture_procs = texture_procs_mod.loadTextureProcs(self.dyn_lib) orelse return error.TextureProcUnavailable;

    if (self.render_uniform_bind_group_layout != null and self.render_uniform_bind_group != null) {
        return .{
            .bind_group_layout = self.render_uniform_bind_group_layout,
            .bind_group = self.render_uniform_bind_group,
        };
    }

    if (self.render_uniform_bind_group) |stale_group| {
        procs.wgpuBindGroupRelease(stale_group);
        self.render_uniform_bind_group = null;
    }
    if (self.render_uniform_bind_group_layout) |stale_layout| {
        procs.wgpuBindGroupLayoutRelease(stale_layout);
        self.render_uniform_bind_group_layout = null;
    }

    const uniform_bytes = std.mem.sliceAsBytes(render_assets.RENDER_DRAW_UNIFORM_COLOR[0..]);
    const uniform_usage = types.WGPUBufferUsage_Uniform | types.WGPUBufferUsage_CopyDst;
    const should_upload_uniform_data = blk: {
        if (self.buffers.get(RENDER_UNIFORM_BUFFER_HANDLE)) |existing| {
            if (existing.size >= RENDER_UNIFORM_TOTAL_BYTES and
                (existing.usage & uniform_usage) == uniform_usage)
            {
                break :blk false;
            }
        }
        break :blk true;
    };
    const uniform_buffer = try resources.getOrCreateBuffer(
        self,
        RENDER_UNIFORM_BUFFER_HANDLE,
        RENDER_UNIFORM_TOTAL_BYTES,
        uniform_usage,
    );
    if (should_upload_uniform_data) {
        var payload: [@intCast(RENDER_UNIFORM_TOTAL_BYTES)]u8 = undefined;
        @memset(payload[0..], 0);
        var offset: usize = 0;
        while (offset + uniform_bytes.len <= payload.len) : (offset += @as(usize, @intCast(RENDER_UNIFORM_DYNAMIC_STRIDE_BYTES))) {
            @memcpy(payload[offset .. offset + uniform_bytes.len], uniform_bytes);
        }
        procs.wgpuQueueWriteBuffer(
            self.queue.?,
            uniform_buffer,
            0,
            payload[0..].ptr,
            payload.len,
        );
    }

    const sampled_usage = types.WGPUTextureUsage_TextureBinding | types.WGPUTextureUsage_CopyDst;
    const sampled_resource = model.CopyTextureResource{
        .handle = RENDER_SAMPLED_TEXTURE_HANDLE,
        .kind = .texture,
        .width = render_assets.RENDER_DRAW_TEXTURE_WIDTH,
        .height = render_assets.RENDER_DRAW_TEXTURE_HEIGHT,
        .depth_or_array_layers = 1,
        .format = model.WGPUTextureFormat_RGBA8Unorm,
        .usage = sampled_usage,
        .dimension = model.WGPUTextureDimension_2D,
        .view_dimension = model.WGPUTextureViewDimension_2D,
        .mip_level = 0,
        .sample_count = 1,
        .aspect = model.WGPUTextureAspect_All,
        .bytes_per_row = 0,
        .rows_per_image = 0,
        .offset = 0,
    };
    const should_upload_texture_data = blk: {
        if (self.textures.get(RENDER_SAMPLED_TEXTURE_HANDLE)) |existing| {
            if (existing.width == render_assets.RENDER_DRAW_TEXTURE_WIDTH and
                existing.height == render_assets.RENDER_DRAW_TEXTURE_HEIGHT and
                existing.depth_or_array_layers == 1 and
                existing.format == model.WGPUTextureFormat_RGBA8Unorm and
                existing.dimension == model.WGPUTextureDimension_2D and
                existing.sample_count == 1 and
                (existing.usage & sampled_usage) == sampled_usage)
            {
                break :blk false;
            }
        }
        break :blk true;
    };
    const sampled_texture = try resources.getOrCreateTexture(self, sampled_resource, sampled_usage);
    if (should_upload_texture_data) {
        texture_procs.queue_write_texture(
            self.queue.?,
            &types.WGPUTexelCopyTextureInfo{
                .texture = sampled_texture,
                .mipLevel = 0,
                .origin = .{ .x = 0, .y = 0, .z = 0 },
                .aspect = types.WGPUTextureAspect_All,
            },
            render_assets.RENDER_DRAW_TEXTURE_DATA[0..].ptr,
            render_assets.RENDER_DRAW_TEXTURE_DATA.len,
            &types.WGPUTexelCopyBufferLayout{
                .offset = 0,
                .bytesPerRow = render_assets.RENDER_DRAW_TEXTURE_BYTES_PER_ROW,
                .rowsPerImage = render_assets.RENDER_DRAW_TEXTURE_HEIGHT,
            },
            &types.WGPUExtent3D{
                .width = render_assets.RENDER_DRAW_TEXTURE_WIDTH,
                .height = render_assets.RENDER_DRAW_TEXTURE_HEIGHT,
                .depthOrArrayLayers = 1,
            },
        );
    }

    const sampled_texture_view = try getOrCreateCachedRenderTextureView(
        self,
        &self.render_target_view_cache,
        RENDER_SAMPLED_TEXTURE_HANDLE,
        sampled_texture,
        render_assets.RENDER_DRAW_TEXTURE_WIDTH,
        render_assets.RENDER_DRAW_TEXTURE_HEIGHT,
        model.WGPUTextureFormat_RGBA8Unorm,
        types.WGPUTextureUsage_TextureBinding,
    );

    if (self.render_sampler == null) {
        const sampler = texture_procs.device_create_sampler(self.device.?, null);
        if (sampler == null) return error.SamplerCreationFailed;
        self.render_sampler = sampler;
    }

    const layout_entries = [_]types.WGPUBindGroupLayoutEntry{
        .{
            .nextInChain = null,
            .binding = RENDER_UNIFORM_BINDING_INDEX,
            .visibility = types.WGPUShaderStage_Fragment,
            .bindingArraySize = 0,
            .buffer = .{
                .nextInChain = null,
                .type = types.WGPUBufferBindingType_Uniform,
                .hasDynamicOffset = types.WGPU_TRUE,
                .minBindingSize = RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES,
            },
            .sampler = .{
                .nextInChain = null,
                .type = types.WGPUSamplerBindingType_BindingNotUsed,
            },
            .texture = .{
                .nextInChain = null,
                .sampleType = types.WGPUTextureSampleType_BindingNotUsed,
                .viewDimension = types.WGPUTextureViewDimension_Undefined,
                .multisampled = types.WGPU_FALSE,
            },
            .storageTexture = .{
                .nextInChain = null,
                .access = types.WGPUStorageTextureAccess_BindingNotUsed,
                .format = types.WGPUTextureFormat_Undefined,
                .viewDimension = types.WGPUTextureViewDimension_Undefined,
            },
        },
        .{
            .nextInChain = null,
            .binding = RENDER_TEXTURE_BINDING_INDEX,
            .visibility = types.WGPUShaderStage_Fragment,
            .bindingArraySize = 0,
            .buffer = .{
                .nextInChain = null,
                .type = types.WGPUBufferBindingType_BindingNotUsed,
                .hasDynamicOffset = types.WGPU_FALSE,
                .minBindingSize = 0,
            },
            .sampler = .{
                .nextInChain = null,
                .type = types.WGPUSamplerBindingType_BindingNotUsed,
            },
            .texture = .{
                .nextInChain = null,
                .sampleType = types.WGPUTextureSampleType_Float,
                .viewDimension = types.WGPUTextureViewDimension_2D,
                .multisampled = types.WGPU_FALSE,
            },
            .storageTexture = .{
                .nextInChain = null,
                .access = types.WGPUStorageTextureAccess_BindingNotUsed,
                .format = types.WGPUTextureFormat_Undefined,
                .viewDimension = types.WGPUTextureViewDimension_Undefined,
            },
        },
        .{
            .nextInChain = null,
            .binding = RENDER_SAMPLER_BINDING_INDEX,
            .visibility = types.WGPUShaderStage_Fragment,
            .bindingArraySize = 0,
            .buffer = .{
                .nextInChain = null,
                .type = types.WGPUBufferBindingType_BindingNotUsed,
                .hasDynamicOffset = types.WGPU_FALSE,
                .minBindingSize = 0,
            },
            .sampler = .{
                .nextInChain = null,
                .type = types.WGPUSamplerBindingType_Filtering,
            },
            .texture = .{
                .nextInChain = null,
                .sampleType = types.WGPUTextureSampleType_BindingNotUsed,
                .viewDimension = types.WGPUTextureViewDimension_Undefined,
                .multisampled = types.WGPU_FALSE,
            },
            .storageTexture = .{
                .nextInChain = null,
                .access = types.WGPUStorageTextureAccess_BindingNotUsed,
                .format = types.WGPUTextureFormat_Undefined,
                .viewDimension = types.WGPUTextureViewDimension_Undefined,
            },
        },
    };

    const bind_group_layout = try resources.createBindGroupLayout(self, layout_entries[0..]);
    errdefer procs.wgpuBindGroupLayoutRelease(bind_group_layout);

    const bind_entries = [_]types.WGPUBindGroupEntry{
        .{
            .nextInChain = null,
            .binding = RENDER_UNIFORM_BINDING_INDEX,
            .buffer = uniform_buffer,
            .offset = 0,
            .size = RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES,
            .sampler = null,
            .textureView = null,
        },
        .{
            .nextInChain = null,
            .binding = RENDER_TEXTURE_BINDING_INDEX,
            .buffer = null,
            .offset = 0,
            .size = 0,
            .sampler = null,
            .textureView = sampled_texture_view,
        },
        .{
            .nextInChain = null,
            .binding = RENDER_SAMPLER_BINDING_INDEX,
            .buffer = null,
            .offset = 0,
            .size = 0,
            .sampler = self.render_sampler,
            .textureView = null,
        },
    };
    const bind_group = try resources.createBindGroup(self, bind_group_layout, bind_entries[0..]);

    self.render_uniform_bind_group_layout = bind_group_layout;
    self.render_uniform_bind_group = bind_group;
    return .{
        .bind_group_layout = bind_group_layout,
        .bind_group = bind_group,
    };
}

pub fn getOrCreateCachedRenderTextureView(
    self: *Backend,
    cache: *std.AutoHashMap(u64, types.RenderTextureViewCacheEntry),
    key: u64,
    texture: types.WGPUTexture,
    width: u32,
    height: u32,
    format: types.WGPUTextureFormat,
    usage: types.WGPUTextureUsage,
) !types.WGPUTextureView {
    const procs = self.procs orelse return error.ProceduralNotReady;
    if (cache.get(key)) |existing| {
        if (existing.texture == texture and
            existing.width == width and
            existing.height == height and
            existing.format == format)
        {
            return existing.view;
        }
        procs.wgpuTextureViewRelease(existing.view);
        _ = cache.remove(key);
    }

    const view = procs.wgpuTextureCreateView(texture, &types.WGPUTextureViewDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .format = format,
        .dimension = types.WGPUTextureViewDimension_2D,
        .baseMipLevel = 0,
        .mipLevelCount = 1,
        .baseArrayLayer = 0,
        .arrayLayerCount = 1,
        .aspect = types.WGPUTextureAspect_All,
        .usage = usage,
    });
    if (view == null) return error.TextureViewCreationFailed;
    cache.put(key, .{
        .texture = texture,
        .view = view,
        .width = width,
        .height = height,
        .format = format,
    }) catch {
        procs.wgpuTextureViewRelease(view);
        return error.TextureViewCacheInsertFailed;
    };
    return view;
}
