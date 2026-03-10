const std = @import("std");
const model = @import("../../model.zig");
const types = @import("../abi/wgpu_types.zig");
const loader = @import("../abi/wgpu_loader.zig");
const p0_procs_mod = @import("../../wgpu_p0_procs.zig");
const texture_procs_mod = @import("../../wgpu_texture_procs.zig");
const ffi = @import("../../webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;
const BUFFER_ZERO_INIT_CHUNK_BYTES: usize = 64 * 1024;
const BUFFER_MIN_ALIGNMENT: u64 = 4;

pub fn getOrCreateBuffer(
    self: *Backend,
    handle: u64,
    requested_size: u64,
    required_usage: types.WGPUBufferUsage,
) !types.WGPUBuffer {
    return getOrCreateBufferWithOptions(self, handle, requested_size, required_usage, false);
}

pub fn getOrCreateBufferInitialized(
    self: *Backend,
    handle: u64,
    requested_size: u64,
    required_usage: types.WGPUBufferUsage,
) !types.WGPUBuffer {
    return getOrCreateBufferWithOptions(self, handle, requested_size, required_usage, true);
}

fn getOrCreateBufferWithOptions(
    self: *Backend,
    handle: u64,
    requested_size: u64,
    required_usage: types.WGPUBufferUsage,
    initialize_on_create: bool,
) !types.WGPUBuffer {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const p0_procs = p0_procs_mod.loadP0Procs(self.core.dyn_lib);

    if (self.core.buffers.get(handle)) |existing| {
        const can_reuse = existing.size >= requested_size and (existing.usage & required_usage) == required_usage;
        if (can_reuse) return existing.buffer;
        p0_procs_mod.destroyBuffer(p0_procs, existing.buffer);
        procs.wgpuBufferRelease(existing.buffer);
        _ = self.core.buffers.remove(handle);
    }

    const size = loader.alignTo(requested_size, BUFFER_MIN_ALIGNMENT);

    const desc = types.WGPUBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .usage = required_usage,
        .size = size,
        .mappedAtCreation = types.WGPU_FALSE,
    };
    const buffer = procs.wgpuDeviceCreateBuffer(self.core.device.?, &desc);
    if (buffer == null) {
        return error.BufferAllocationFailed;
    }
    errdefer procs.wgpuBufferRelease(buffer);
    if (initialize_on_create) {
        try zeroInitializeBuffer(self, buffer, size);
    }
    try self.core.buffers.put(handle, .{
        .buffer = buffer,
        .size = size,
        .usage = required_usage,
    });
    return buffer;
}

fn zeroInitializeBuffer(self: *Backend, buffer: types.WGPUBuffer, size: u64) !void {
    if (size == 0) return;
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const queue = self.core.queue orelse return error.ProceduralNotReady;
    const zero_chunk = try ensureZeroScratchBytes(self, BUFFER_ZERO_INIT_CHUNK_BYTES);

    var offset: u64 = 0;
    while (offset < size) {
        const remaining = size - offset;
        const write_len_u64 = @min(remaining, @as(u64, zero_chunk.len));
        const write_len = @as(usize, @intCast(write_len_u64));
        procs.wgpuQueueWriteBuffer(
            queue,
            buffer,
            offset,
            @ptrCast(zero_chunk.ptr),
            write_len,
        );
        offset += write_len_u64;
    }
}

fn ensureZeroScratchBytes(self: *Backend, required_len: usize) ![]u8 {
    if (self.core.upload_scratch.len < required_len) {
        if (self.core.upload_scratch.len > 0) {
            self.core.allocator.free(self.core.upload_scratch);
        }
        self.core.upload_scratch = try self.core.allocator.alloc(u8, required_len);
    }
    const chunk = self.core.upload_scratch[0..required_len];
    @memset(chunk, 0);
    return chunk;
}

pub fn requiredBytes(bytes: u64, offset: u64) !u64 {
    const checked = try std.math.add(u64, bytes, offset);
    return loader.alignTo(checked, 4);
}

pub fn getOrCreateTexture(self: *Backend, resource: model.CopyTextureResource, required_usage: types.WGPUTextureUsage) !types.WGPUTexture {
    return getOrCreateTextureWithOptions(self, resource, required_usage, false);
}

pub fn getOrCreateTextureInitialized(self: *Backend, resource: model.CopyTextureResource, required_usage: types.WGPUTextureUsage) !types.WGPUTexture {
    return getOrCreateTextureWithOptions(self, resource, required_usage, true);
}

fn getOrCreateTextureWithOptions(
    self: *Backend,
    resource: model.CopyTextureResource,
    required_usage: types.WGPUTextureUsage,
    initialize_on_create: bool,
) !types.WGPUTexture {
    if (resource.kind != .texture) return error.InvalidTextureResourceKind;
    const procs = self.core.procs orelse return error.ProceduralNotReady;

    const handle = resource.handle;
    const width = if (resource.width == 0) 1 else resource.width;
    const height = if (resource.height == 0) 1 else resource.height;
    const depth = if (resource.depth_or_array_layers == 0) 1 else resource.depth_or_array_layers;
    const sample_count = if (resource.sample_count == 0) 1 else resource.sample_count;
    const dimension = if (resource.dimension == model.WGPUTextureDimension_Undefined or resource.dimension == 0)
        types.WGPUTextureDimension_2D
    else
        resource.dimension;
    const raw_format = normalizeTextureFormat(resource.format);
    const format = if (raw_format == types.WGPUTextureFormat_Undefined) types.WGPUTextureFormat_R8Unorm else raw_format;
    const usage = required_usage | resource.usage;

    if (self.core.textures.get(handle)) |existing| {
        if (existing.width == width and
            existing.height == height and
            existing.depth_or_array_layers == depth and
            existing.format == format and
            existing.dimension == dimension and
            existing.sample_count == sample_count and
            (existing.usage & required_usage) == required_usage)
        {
            return existing.texture;
        }
        const texture_procs = texture_procs_mod.loadTextureProcs(self.core.dyn_lib) orelse return error.TextureProcUnavailable;
        texture_procs.texture_destroy(existing.texture);
        procs.wgpuTextureRelease(existing.texture);
        _ = self.core.textures.remove(handle);
    }

    const descriptor = types.WGPUTextureDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .usage = usage,
        .dimension = dimension,
        .size = .{
            .width = width,
            .height = height,
            .depthOrArrayLayers = depth,
        },
        .format = format,
        .mipLevelCount = 1,
        .sampleCount = if (sample_count == 0) 1 else sample_count,
        .viewFormatCount = 0,
        .viewFormats = null,
    };
    const texture = procs.wgpuDeviceCreateTexture(self.core.device.?, &descriptor);
    if (texture == null) return error.TextureAllocationFailed;
    errdefer procs.wgpuTextureRelease(texture);

    if (initialize_on_create) {
        try zeroInitializeTexture(self, texture, .{
            .handle = resource.handle,
            .kind = .texture,
            .width = width,
            .height = height,
            .depth_or_array_layers = depth,
            .format = format,
            .usage = usage,
            .dimension = dimension,
            .view_dimension = resource.view_dimension,
            .mip_level = resource.mip_level,
            .sample_count = sample_count,
            .aspect = resource.aspect,
            .bytes_per_row = resource.bytes_per_row,
            .rows_per_image = resource.rows_per_image,
            .offset = resource.offset,
        });
    }

    try self.core.textures.put(handle, .{
        .texture = texture,
        .width = width,
        .height = height,
        .depth_or_array_layers = depth,
        .format = format,
        .usage = usage,
        .dimension = dimension,
        .sample_count = if (sample_count == 0) 1 else sample_count,
    });

    return texture;
}

fn zeroInitializeTexture(
    self: *Backend,
    texture: types.WGPUTexture,
    resource: model.CopyTextureResource,
) !void {
    const texture_procs = texture_procs_mod.loadTextureProcs(self.core.dyn_lib) orelse return error.TextureProcUnavailable;
    const queue = self.core.queue orelse return error.ProceduralNotReady;

    const width = if (resource.width == 0) 1 else resource.width;
    const height = if (resource.height == 0) 1 else resource.height;
    const depth = if (resource.depth_or_array_layers == 0) 1 else resource.depth_or_array_layers;
    const format = normalizeTextureFormat(resource.format);
    const bytes_per_pixel = textureFormatBytesPerPixel(format) orelse return;
    const bytes_per_row = if (resource.bytes_per_row != 0)
        resource.bytes_per_row
    else
        width * bytes_per_pixel;
    const rows_per_image = if (resource.rows_per_image != 0) resource.rows_per_image else height;
    const data_size_u64 = @as(u64, bytes_per_row) * rows_per_image * depth;
    const data_size = std.math.cast(usize, data_size_u64) orelse return error.TextureAllocationFailed;
    const zero_bytes = try ensureZeroScratchBytes(self, data_size);

    texture_procs.queue_write_texture(
        queue,
        &types.WGPUTexelCopyTextureInfo{
            .texture = texture,
            .mipLevel = resource.mip_level,
            .origin = .{ .x = 0, .y = 0, .z = 0 },
            .aspect = loader.normalizeTextureAspect(resource.aspect),
        },
        @ptrCast(zero_bytes.ptr),
        zero_bytes.len,
        &types.WGPUTexelCopyBufferLayout{
            .offset = 0,
            .bytesPerRow = bytes_per_row,
            .rowsPerImage = rows_per_image,
        },
        &types.WGPUExtent3D{
            .width = width,
            .height = height,
            .depthOrArrayLayers = depth,
        },
    );
}

pub fn getOrCreateTextureFromBinding(self: *Backend, binding: model.KernelBinding, required_usage: types.WGPUTextureUsage) !types.WGPUTexture {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const handle = binding.resource_handle;
    const requested_format = normalizeTextureFormat(binding.texture_format);
    const requested_dimension = inferTextureDimensionFromViewDimension(binding.texture_view_dimension);
    var fallback_format = requested_format;
    var fallback_dimension = requested_dimension;
    var fallback_width: u32 = 1;
    var fallback_height: u32 = 1;
    var fallback_depth: u32 = 1;
    var fallback_sample_count: u32 = 1;
    var fallback_usage: types.WGPUTextureUsage = types.WGPUTextureUsage_None;

    if (self.core.textures.get(handle)) |existing| {
        fallback_format = if (requested_format == types.WGPUTextureFormat_Undefined) existing.format else requested_format;
        fallback_dimension = existing.dimension;
        fallback_width = existing.width;
        fallback_height = existing.height;
        fallback_depth = existing.depth_or_array_layers;
        fallback_sample_count = existing.sample_count;
        fallback_usage = existing.usage;

        if ((existing.usage & required_usage) == required_usage) {
            if ((requested_format == types.WGPUTextureFormat_Undefined or requested_format == existing.format) and
                (requested_dimension == types.WGPUTextureDimension_Undefined or requested_dimension == existing.dimension))
            {
                return existing.texture;
            }
        }
        const texture_procs = texture_procs_mod.loadTextureProcs(self.core.dyn_lib) orelse return error.TextureProcUnavailable;
        texture_procs.texture_destroy(existing.texture);
        procs.wgpuTextureRelease(existing.texture);
        _ = self.core.textures.remove(handle);
    }

    const dimension = if (requested_dimension == types.WGPUTextureDimension_Undefined) fallback_dimension else requested_dimension;
    const format = if (fallback_format == types.WGPUTextureFormat_Undefined) types.WGPUTextureFormat_R8Unorm else fallback_format;
    const usage = fallback_usage | required_usage;
    const resource = model.CopyTextureResource{
        .handle = handle,
        .kind = .texture,
        .width = fallback_width,
        .height = fallback_height,
        .depth_or_array_layers = fallback_depth,
        .format = format,
        .usage = fallback_usage,
        .dimension = dimension,
        .view_dimension = binding.texture_view_dimension,
        .mip_level = 0,
        .sample_count = fallback_sample_count,
        .aspect = normalizeTextureViewAspect(binding.texture_aspect),
        .bytes_per_row = 0,
        .rows_per_image = 0,
        .offset = 0,
    };
    return try getOrCreateTexture(self, resource, usage);
}

pub fn createTextureViewForBinding(self: *Backend, texture: types.WGPUTexture, binding: model.KernelBinding) !types.WGPUTextureView {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const format = blk: {
        if (self.core.textures.get(binding.resource_handle)) |record| {
            const normalized = normalizeTextureFormat(binding.texture_format);
            break :blk if (normalized == types.WGPUTextureFormat_Undefined) record.format else normalized;
        }
        const normalized = normalizeTextureFormat(binding.texture_format);
        break :blk if (normalized == types.WGPUTextureFormat_Undefined) types.WGPUTextureFormat_R8Unorm else normalized;
    };
    const dimension = normalizeTextureViewDimension(binding.texture_view_dimension);
    const descriptor = types.WGPUTextureViewDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .format = format,
        .dimension = if (dimension == types.WGPUTextureViewDimension_Undefined) types.WGPUTextureViewDimension_2D else dimension,
        .baseMipLevel = 0,
        .mipLevelCount = types.WGPU_MIP_LEVEL_COUNT_UNDEFINED,
        .baseArrayLayer = 0,
        .arrayLayerCount = types.WGPU_ARRAY_LAYER_COUNT_UNDEFINED,
        .aspect = loader.normalizeTextureAspect(binding.texture_aspect),
        .usage = 0,
    };

    const view = procs.wgpuTextureCreateView(texture, &descriptor);
    if (view == null) return error.TextureViewCreationFailed;
    return view;
}

pub fn buildDispatchPassGroups(
    self: *Backend,
    bindings: []const model.KernelBinding,
    initialize_buffers_on_create: bool,
) !types.DispatchPassArtifacts {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    var max_group: u32 = 0;
    for (bindings) |binding| {
        if (binding.group > max_group) max_group = binding.group;
    }

    const group_count_u32 = max_group + 1;
    const group_count = @as(usize, group_count_u32);

    var groups = try self.core.allocator.alloc(types.DispatchPassGroup, group_count);
    for (groups) |*group| {
        group.layout_entries = std.ArrayList(types.WGPUBindGroupLayoutEntry).empty;
        group.bind_entries = std.ArrayList(types.WGPUBindGroupEntry).empty;
    }

    var pending_group_layouts = try self.core.allocator.alloc(?types.WGPUBindGroupLayout, group_count);
    var pass_bind_groups = try self.core.allocator.alloc(?types.WGPUBindGroup, group_count);
    for (pending_group_layouts) |*pending| pending.* = null;
    for (pass_bind_groups) |*pending| pending.* = null;

    var texture_views = std.ArrayList(types.WGPUTextureView).empty;
    var clean_after = true;
    defer {
        if (clean_after) {
            for (pass_bind_groups) |bind_group| {
                if (bind_group) |actual_bind_group| {
                    procs.wgpuBindGroupRelease(actual_bind_group);
                }
            }
            self.core.allocator.free(pass_bind_groups);

            for (pending_group_layouts) |maybe_layout| {
                if (maybe_layout) |layout| {
                    procs.wgpuBindGroupLayoutRelease(layout);
                }
            }
            self.core.allocator.free(pending_group_layouts);

            for (texture_views.items) |texture_view| {
                procs.wgpuTextureViewRelease(texture_view);
            }
            texture_views.deinit(self.core.allocator);

            for (groups) |*group| {
                group.layout_entries.deinit(self.core.allocator);
                group.bind_entries.deinit(self.core.allocator);
            }
            self.core.allocator.free(groups);
        }
    }

    for (bindings) |binding| {
        if (binding.group >= group_count_u32) return error.InvalidKernelDispatchBinding;
        var group = &groups[@as(usize, binding.group)];
        try group.layout_entries.append(self.core.allocator, dispatchPassLayoutEntry(binding));
        try group.bind_entries.append(self.core.allocator, try dispatchPassBindEntry(self, binding, &texture_views, initialize_buffers_on_create));
    }

    for (groups, 0..) |*group, index| {
        const layout = try createBindGroupLayout(self, group.layout_entries.items);
        pending_group_layouts[index] = layout;
        if (group.bind_entries.items.len > 0) {
            const bind_group = try createBindGroup(self, layout, group.bind_entries.items);
            pass_bind_groups[index] = bind_group;
        }
    }

    var group_layouts = try self.core.allocator.alloc(types.WGPUBindGroupLayout, group_count);
    for (pending_group_layouts, 0..) |maybe_layout, index| {
        group_layouts[index] = maybe_layout orelse return error.InvalidKernelDispatchBinding;
    }

    const views = try texture_views.toOwnedSlice(self.core.allocator);
    for (groups) |*group| {
        group.layout_entries.deinit(self.core.allocator);
        group.bind_entries.deinit(self.core.allocator);
    }
    self.core.allocator.free(groups);
    self.core.allocator.free(pending_group_layouts);
    clean_after = false;

    return .{
        .pass_bind_groups = pass_bind_groups,
        .group_layouts = group_layouts,
        .texture_views = views,
    };
}

fn dispatchPassLayoutEntry(binding: model.KernelBinding) types.WGPUBindGroupLayoutEntry {
    const visibility = if (binding.visibility != 0) binding.visibility else types.WGPUShaderStage_Compute;
    var layout_entry = types.WGPUBindGroupLayoutEntry{
        .nextInChain = null,
        .binding = binding.binding,
        .visibility = visibility,
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
    };

    switch (binding.resource_kind) {
        .buffer => {
            layout_entry.buffer.type = normalizeBufferBindingType(binding.buffer_type);
            layout_entry.buffer.minBindingSize = if (binding.buffer_size == types.WGPU_WHOLE_SIZE or binding.buffer_size == 0)
                0
            else
                binding.buffer_size;
        },
        .texture => {
            layout_entry.texture.sampleType = normalizeTextureSampleType(binding.texture_sample_type);
            layout_entry.texture.viewDimension = normalizeTextureViewDimension(binding.texture_view_dimension);
            layout_entry.texture.multisampled = if (binding.texture_multisampled) types.WGPU_TRUE else types.WGPU_FALSE;
        },
        .storage_texture => {
            layout_entry.storageTexture.access = normalizeStorageTextureAccess(binding.storage_texture_access);
            layout_entry.storageTexture.format = normalizeTextureFormat(binding.texture_format);
            if (layout_entry.storageTexture.format == types.WGPUTextureFormat_Undefined) {
                layout_entry.storageTexture.format = types.WGPUTextureFormat_R8Unorm;
            }
            layout_entry.storageTexture.viewDimension = normalizeTextureViewDimension(binding.texture_view_dimension);
        },
    }

    return layout_entry;
}

fn dispatchPassBindEntry(
    self: *Backend,
    binding: model.KernelBinding,
    texture_views: *std.ArrayList(types.WGPUTextureView),
    initialize_buffers_on_create: bool,
) !types.WGPUBindGroupEntry {
    var bind_entry = types.WGPUBindGroupEntry{
        .nextInChain = null,
        .binding = binding.binding,
        .buffer = null,
        .offset = binding.buffer_offset,
        .size = if (binding.buffer_size == 0) types.WGPU_WHOLE_SIZE else binding.buffer_size,
        .sampler = null,
        .textureView = null,
    };

    switch (binding.resource_kind) {
        .buffer => {
            const usage = bindingUsageForBufferKind(binding);
            const requested_size = if (binding.buffer_size == types.WGPU_WHOLE_SIZE)
                try requiredBytes(4, binding.buffer_offset)
            else
                try requiredBytes(binding.buffer_size, binding.buffer_offset);
            const buffer = if (initialize_buffers_on_create)
                try getOrCreateBufferInitialized(self, binding.resource_handle, requested_size, usage)
            else
                try getOrCreateBuffer(self, binding.resource_handle, requested_size, usage);
            bind_entry.buffer = buffer;
            bind_entry.size = binding.buffer_size;
        },
        .texture, .storage_texture => {
            const required_usage = if (binding.resource_kind == .storage_texture)
                (types.WGPUTextureUsage_StorageBinding | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_CopyDst)
            else
                (types.WGPUTextureUsage_TextureBinding | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_CopyDst);
            const texture = try getOrCreateTextureFromBinding(self, binding, required_usage);
            const view = try createTextureViewForBinding(self, texture, binding);
            try texture_views.append(self.core.allocator, view);
            bind_entry.textureView = view;
        },
    }
    return bind_entry;
}

pub fn createBindGroupLayout(self: *Backend, entries: []const types.WGPUBindGroupLayoutEntry) !types.WGPUBindGroupLayout {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const descriptor = types.WGPUBindGroupLayoutDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .entryCount = entries.len,
        .entries = if (entries.len == 0) null else entries.ptr,
    };
    const layout = procs.wgpuDeviceCreateBindGroupLayout(self.core.device.?, &descriptor);
    if (layout == null) return error.BindGroupLayoutCreationFailed;
    return layout;
}

pub fn createBindGroup(self: *Backend, layout: types.WGPUBindGroupLayout, entries: []const types.WGPUBindGroupEntry) !types.WGPUBindGroup {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const descriptor = types.WGPUBindGroupDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .layout = layout,
        .entryCount = entries.len,
        .entries = entries.ptr,
    };
    const bind_group = procs.wgpuDeviceCreateBindGroup(self.core.device.?, &descriptor);
    if (bind_group == null) return error.BindGroupCreationFailed;
    return bind_group;
}

pub fn createShaderModule(self: *Backend, source: []const u8) !types.WGPUShaderModule {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    var chained_source = types.WGPUShaderSourceWGSL{
        .chain = .{
            .next = null,
            .sType = types.WGPUSType_ShaderSourceWGSL,
        },
        .code = loader.stringView(source),
    };
    const descriptor = types.WGPUShaderModuleDescriptor{
        .nextInChain = &chained_source.chain,
        .label = loader.emptyStringView(),
    };
    const shader_module = procs.wgpuDeviceCreateShaderModule(self.core.device.?, &descriptor);
    if (shader_module == null) return error.KernelModuleCreationFailed;
    return shader_module;
}

pub fn createComputePipeline(
    self: *Backend,
    kernel_name: []const u8,
    module: types.WGPUShaderModule,
    entry_point: []const u8,
    pipeline_layout: types.WGPUPipelineLayout,
) !types.WGPUComputePipeline {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const p0_procs = p0_procs_mod.loadP0Procs(self.core.dyn_lib);
    const compute_state = types.WGPUComputeState{
        .nextInChain = null,
        .module = module,
        .entryPoint = loader.stringView(entry_point),
        .constantCount = 0,
        .constants = null,
    };
    const descriptor = types.WGPUComputePipelineDescriptor{
        .nextInChain = null,
        .label = loader.stringView(kernel_name),
        .layout = pipeline_layout,
        .compute = compute_state,
    };
    if (p0_procs) |loaded| {
        if (loaded.device_create_compute_pipeline_async != null) {
            return p0_procs_mod.createComputePipelineAsyncAndWait(
                loaded,
                self.core.instance.?,
                procs,
                self.core.device.?,
                &descriptor,
            ) catch error.ComputePipelineCreationFailed;
        }
    }
    const pipeline = procs.wgpuDeviceCreateComputePipeline(self.core.device.?, &descriptor);
    if (pipeline == null) return error.ComputePipelineCreationFailed;
    return pipeline;
}

pub fn createPipelineLayout(self: *Backend, bind_group_layouts: []const types.WGPUBindGroupLayout) !types.WGPUPipelineLayout {
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const descriptor = types.WGPUPipelineLayoutDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .bindGroupLayoutCount = bind_group_layouts.len,
        .bindGroupLayouts = bind_group_layouts.ptr,
        .immediateSize = 0,
    };
    const layout = procs.wgpuDeviceCreatePipelineLayout(self.core.device.?, &descriptor);
    if (layout == null) return error.PipelineLayoutCreationFailed;
    return layout;
}

pub fn bindingUsageForBufferKind(binding: model.KernelBinding) types.WGPUBufferUsage {
    return switch (binding.buffer_type) {
        model.WGPUBufferBindingType_Uniform => types.WGPUBufferUsage_Uniform | types.WGPUBufferUsage_CopySrc | types.WGPUBufferUsage_CopyDst,
        model.WGPUBufferBindingType_ReadOnlyStorage => types.WGPUBufferUsage_Storage | types.WGPUBufferUsage_CopySrc | types.WGPUBufferUsage_CopyDst,
        model.WGPUBufferBindingType_Storage => types.WGPUBufferUsage_Storage | types.WGPUBufferUsage_CopySrc | types.WGPUBufferUsage_CopyDst,
        else => types.WGPUBufferUsage_Storage | types.WGPUBufferUsage_Uniform | types.WGPUBufferUsage_CopySrc | types.WGPUBufferUsage_CopyDst,
    };
}

pub fn normalizeBufferBindingType(value: u32) u32 {
    return switch (value) {
        model.WGPUBufferBindingType_Uniform => types.WGPUBufferBindingType_Uniform,
        model.WGPUBufferBindingType_Storage => types.WGPUBufferBindingType_Storage,
        model.WGPUBufferBindingType_ReadOnlyStorage => types.WGPUBufferBindingType_ReadOnlyStorage,
        else => types.WGPUBufferBindingType_Undefined,
    };
}

pub fn normalizeTextureSampleType(value: u32) u32 {
    return switch (value) {
        model.WGPUTextureSampleType_Float => types.WGPUTextureSampleType_Float,
        model.WGPUTextureSampleType_UnfilterableFloat => types.WGPUTextureSampleType_UnfilterableFloat,
        model.WGPUTextureSampleType_Depth => types.WGPUTextureSampleType_Depth,
        model.WGPUTextureSampleType_Sint => types.WGPUTextureSampleType_Sint,
        model.WGPUTextureSampleType_Uint => types.WGPUTextureSampleType_Uint,
        else => types.WGPUTextureSampleType_Float,
    };
}

pub fn normalizeTextureViewDimension(value: u32) types.WGPUTextureViewDimension {
    return switch (value) {
        model.WGPUTextureViewDimension_1D => types.WGPUTextureViewDimension_1D,
        model.WGPUTextureViewDimension_2D => types.WGPUTextureViewDimension_2D,
        model.WGPUTextureViewDimension_2DArray => types.WGPUTextureViewDimension_2DArray,
        model.WGPUTextureViewDimension_Cube => types.WGPUTextureViewDimension_Cube,
        model.WGPUTextureViewDimension_CubeArray => types.WGPUTextureViewDimension_CubeArray,
        model.WGPUTextureViewDimension_3D => types.WGPUTextureViewDimension_3D,
        else => types.WGPUTextureViewDimension_2D,
    };
}

pub fn normalizeStorageTextureAccess(value: u32) u32 {
    return switch (value) {
        model.WGPUStorageTextureAccess_WriteOnly => types.WGPUStorageTextureAccess_WriteOnly,
        model.WGPUStorageTextureAccess_ReadOnly => types.WGPUStorageTextureAccess_ReadOnly,
        model.WGPUStorageTextureAccess_ReadWrite => types.WGPUStorageTextureAccess_ReadWrite,
        else => types.WGPUStorageTextureAccess_WriteOnly,
    };
}

pub fn normalizeTextureFormat(value: u32) types.WGPUTextureFormat {
    return switch (value) {
        model.WGPUTextureFormat_Undefined => types.WGPUTextureFormat_Undefined,
        model.WGPUTextureFormat_R8Unorm => types.WGPUTextureFormat_R8Unorm,
        model.WGPUTextureFormat_R8Snorm => model.WGPUTextureFormat_R8Snorm,
        model.WGPUTextureFormat_R8Uint => model.WGPUTextureFormat_R8Uint,
        model.WGPUTextureFormat_R8Sint => model.WGPUTextureFormat_R8Sint,
        model.WGPUTextureFormat_R16Unorm => model.WGPUTextureFormat_R16Unorm,
        model.WGPUTextureFormat_R16Snorm => model.WGPUTextureFormat_R16Snorm,
        model.WGPUTextureFormat_R16Uint => model.WGPUTextureFormat_R16Uint,
        model.WGPUTextureFormat_R16Sint => model.WGPUTextureFormat_R16Sint,
        model.WGPUTextureFormat_R16Float => model.WGPUTextureFormat_R16Float,
        model.WGPUTextureFormat_RG8Unorm => model.WGPUTextureFormat_RG8Unorm,
        model.WGPUTextureFormat_RG8Snorm => model.WGPUTextureFormat_RG8Snorm,
        model.WGPUTextureFormat_RG8Uint => model.WGPUTextureFormat_RG8Uint,
        model.WGPUTextureFormat_RG8Sint => model.WGPUTextureFormat_RG8Sint,
        model.WGPUTextureFormat_R32Float => model.WGPUTextureFormat_R32Float,
        model.WGPUTextureFormat_R32Uint => model.WGPUTextureFormat_R32Uint,
        model.WGPUTextureFormat_R32Sint => model.WGPUTextureFormat_R32Sint,
        model.WGPUTextureFormat_RG16Unorm => model.WGPUTextureFormat_RG16Unorm,
        model.WGPUTextureFormat_RG16Snorm => model.WGPUTextureFormat_RG16Snorm,
        model.WGPUTextureFormat_RG16Uint => model.WGPUTextureFormat_RG16Uint,
        model.WGPUTextureFormat_RG16Sint => model.WGPUTextureFormat_RG16Sint,
        model.WGPUTextureFormat_RG16Float => model.WGPUTextureFormat_RG16Float,
        model.WGPUTextureFormat_RGBA8Unorm => model.WGPUTextureFormat_RGBA8Unorm,
        model.WGPUTextureFormat_RGBA8UnormSrgb => model.WGPUTextureFormat_RGBA8UnormSrgb,
        model.WGPUTextureFormat_RGBA8Snorm => model.WGPUTextureFormat_RGBA8Snorm,
        model.WGPUTextureFormat_RGBA8Uint => model.WGPUTextureFormat_RGBA8Uint,
        model.WGPUTextureFormat_RGBA8Sint => model.WGPUTextureFormat_RGBA8Sint,
        model.WGPUTextureFormat_BGRA8Unorm => model.WGPUTextureFormat_BGRA8Unorm,
        model.WGPUTextureFormat_BGRA8UnormSrgb => model.WGPUTextureFormat_BGRA8UnormSrgb,
        model.WGPUTextureFormat_Depth16Unorm => model.WGPUTextureFormat_Depth16Unorm,
        model.WGPUTextureFormat_Depth24Plus => model.WGPUTextureFormat_Depth24Plus,
        model.WGPUTextureFormat_Depth24PlusStencil8 => model.WGPUTextureFormat_Depth24PlusStencil8,
        model.WGPUTextureFormat_Depth32Float => model.WGPUTextureFormat_Depth32Float,
        model.WGPUTextureFormat_Depth32FloatStencil8 => model.WGPUTextureFormat_Depth32FloatStencil8,
        else => types.WGPUTextureFormat_Undefined,
    };
}

fn textureFormatBytesPerPixel(format: types.WGPUTextureFormat) ?u32 {
    return switch (format) {
        types.WGPUTextureFormat_R8Unorm,
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
        model.WGPUTextureFormat_Depth32Float,
        => 4,
        else => null,
    };
}

pub fn inferTextureDimensionFromViewDimension(value: u32) types.WGPUTextureDimension {
    const view_dim = normalizeTextureViewDimension(value);
    return switch (view_dim) {
        types.WGPUTextureViewDimension_Undefined => types.WGPUTextureDimension_Undefined,
        types.WGPUTextureViewDimension_1D => types.WGPUTextureDimension_1D,
        types.WGPUTextureViewDimension_3D => types.WGPUTextureDimension_3D,
        else => types.WGPUTextureDimension_2D,
    };
}

pub fn normalizeTextureViewAspect(value: u32) types.WGPUTextureAspect {
    return switch (value) {
        model.WGPUTextureAspect_DepthOnly => types.WGPUTextureAspect_DepthOnly,
        model.WGPUTextureAspect_StencilOnly => types.WGPUTextureAspect_StencilOnly,
        else => types.WGPUTextureAspect_All,
    };
}
