const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const p0_procs_mod = @import("wgpu_p0_procs.zig");
const resources = @import("wgpu_resources.zig");
const render_commands = @import("wgpu_render_commands.zig");
const extended_commands = @import("wgpu_extended_commands.zig");
const async_diagnostics_command = @import("wgpu_async_diagnostics_command.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;
const BARRIER_SCRATCH_BUFFER_HANDLE: u64 = 0xFFFF_FFFF_FFFF_FFFB;
const DISPATCH_INDIRECT_ARGS_HANDLE: u64 = 0xFFFF_FFFF_FFFF_FFFA;
const BUFFER_USAGE_INDIRECT: types.WGPUBufferUsage = 0x0000000000000100;
const MAX_KERNEL_SOURCE_BYTES: usize = 4 * 1024 * 1024;

pub fn executeCommand(self: *Backend, command: model.Command) !types.NativeExecutionResult {
    if (!self.backendAvailable()) {
        return .{
            .status = .@"error",
            .status_message = "backend-not-initialized",
        };
    }

    return switch (command) {
        .upload => |upload| executeUpload(self, upload),
        .copy_buffer_to_texture => |copy| blk: {
            try flushPendingUploads(self);
            break :blk executeCopy(self, copy);
        },
        .barrier => |barrier| blk: {
            try flushPendingUploads(self);
            break :blk executeBarrier(self, barrier);
        },
        .dispatch => |dispatch| blk: {
            try flushPendingUploads(self);
            break :blk executeDispatch(self, dispatch);
        },
        .kernel_dispatch => |kernel| blk: {
            try flushPendingUploads(self);
            break :blk executeKernelDispatch(self, kernel);
        },
        .render_draw => |render| blk: {
            try flushPendingUploads(self);
            break :blk render_commands.executeRenderDraw(self, render);
        },
        .sampler_create => |sampler_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSamplerCreate(self, sampler_cmd);
        },
        .sampler_destroy => |sampler_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSamplerDestroy(self, sampler_cmd);
        },
        .texture_write => |texture_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeTextureWrite(self, texture_cmd);
        },
        .texture_query => |texture_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeTextureQuery(self, texture_cmd);
        },
        .texture_destroy => |texture_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeTextureDestroy(self, texture_cmd);
        },
        .surface_create => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceCreate(self, surface_cmd);
        },
        .surface_capabilities => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceCapabilities(self, surface_cmd);
        },
        .surface_configure => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceConfigure(self, surface_cmd);
        },
        .surface_acquire => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceAcquire(self, surface_cmd);
        },
        .surface_present => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfacePresent(self, surface_cmd);
        },
        .surface_unconfigure => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceUnconfigure(self, surface_cmd);
        },
        .surface_release => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceRelease(self, surface_cmd);
        },
        .async_diagnostics => |diagnostics| blk: {
            try flushPendingUploads(self);
            break :blk async_diagnostics_command.executeAsyncDiagnostics(self, diagnostics);
        },
    };
}

fn flushPendingUploads(self: *Backend) !void {
    if (self.upload_submit_pending == 0) return;
    _ = try self.submitEmpty();
    self.upload_submit_pending = 0;
}

fn executeUpload(self: *Backend, upload: model.UploadCommand) !types.NativeExecutionResult {
    const setup_start_ns = std.time.nanoTimestamp();
    const bytes = @as(u64, upload.bytes);
    if (bytes == 0) {
        return .{ .status = .unsupported, .status_message = "upload command has zero bytes" };
    }

    const usage = switch (self.upload_buffer_usage_mode) {
        .copy_dst_copy_src => types.WGPUBufferUsage_CopyDst | types.WGPUBufferUsage_CopySrc,
        .copy_dst => types.WGPUBufferUsage_CopyDst,
    };
    const upload_buffer = try resources.getOrCreateBuffer(self, loader.BUFFER_UPLOAD_KEY, bytes, usage);
    const bytes_usize = std.math.cast(usize, bytes) orelse {
        return .{
            .status = .@"error",
            .status_message = "upload bytes exceed address space",
        };
    };

    if (bytes_usize > self.upload_scratch.len) {
        if (self.upload_scratch.len > 0) {
            self.allocator.free(self.upload_scratch);
        }
        self.upload_scratch = try self.allocator.alloc(u8, bytes_usize);
        @memset(self.upload_scratch, 0);
    }
    const staging = self.upload_scratch[0..bytes_usize];
    self.procs.?.wgpuQueueWriteBuffer(self.queue.?, upload_buffer, 0, @ptrCast(staging.ptr), bytes_usize);
    const setup_end_ns = std.time.nanoTimestamp();

    self.upload_submit_pending += 1;
    var submit_wait_ns: u64 = 0;
    if (self.upload_submit_pending >= self.upload_submit_every) {
        submit_wait_ns = try self.submitEmpty();
        self.upload_submit_pending = 0;
    }

    const setup_ns = if (setup_end_ns > setup_start_ns)
        @as(u64, @intCast(setup_end_ns - setup_start_ns))
    else
        0;

    return .{
        .status = .ok,
        .status_message = "upload staged via queueWriteBuffer",
        .setup_ns = setup_ns,
        .submit_wait_ns = submit_wait_ns,
    };
}

fn executeCopy(self: *Backend, copy: model.CopyCommand) !types.NativeExecutionResult {
    const bytes = @as(u64, copy.bytes);
    if (bytes == 0) {
        return .{
            .status = .unsupported,
            .status_message = "copy bytes must be > 0",
        };
    }

    switch (copy.direction) {
        .buffer_to_buffer => {
            if (copy.src.kind != .buffer or copy.dst.kind != .buffer) {
                return .{ .status = .unsupported, .status_message = "copy_buffer_to_buffer requires src and dst resources to be buffers" };
            }
        },
        .buffer_to_texture => {
            if (copy.src.kind != .buffer or copy.dst.kind != .texture) {
                return .{ .status = .unsupported, .status_message = "buffer_to_texture requires a buffer source and texture destination" };
            }
        },
        .texture_to_buffer => {
            if (copy.src.kind != .texture or copy.dst.kind != .buffer) {
                return .{ .status = .unsupported, .status_message = "texture_to_buffer requires a texture source and buffer destination" };
            }
        },
        .texture_to_texture => {
            if (copy.src.kind != .texture or copy.dst.kind != .texture) {
                return .{ .status = .unsupported, .status_message = "texture_to_texture requires both source and destination textures" };
            }
        },
    }
    switch (copy.direction) {
        .buffer_to_texture => {
            if (!hasValidTextureExtent(copy.dst)) {
                return .{ .status = .unsupported, .status_message = "buffer_to_texture requires non-zero texture extent" };
            }
        },
        .texture_to_buffer => {
            if (!hasValidTextureExtent(copy.src)) {
                return .{ .status = .unsupported, .status_message = "texture_to_buffer requires non-zero texture extent" };
            }
        },
        .texture_to_texture => {
            if (!hasValidTextureExtent(copy.src) or !hasValidTextureExtent(copy.dst)) {
                return .{ .status = .unsupported, .status_message = "texture_to_texture requires non-zero texture extents" };
            }
            if (!hasMatchingTextureExtent(copy.src, copy.dst)) {
                return .{ .status = .unsupported, .status_message = "texture_to_texture requires matching source/destination extents" };
            }
        },
        .buffer_to_buffer => {},
    }

    const procs = self.procs orelse return error.ProceduralNotReady;

    const encoder = procs.wgpuDeviceCreateCommandEncoder(self.device.?, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) {
        return .{ .status = .@"error", .status_message = "deviceCreateCommandEncoder returned null" };
    }
    defer procs.wgpuCommandEncoderRelease(encoder);

    switch (copy.direction) {
        .buffer_to_buffer => {
            const src_size = try resources.requiredBytes(bytes, copy.src.offset);
            const dst_size = try resources.requiredBytes(bytes, copy.dst.offset);
            const src = try resources.getOrCreateBuffer(self, copy.src.handle, src_size, types.WGPUBufferUsage_CopySrc);
            const dst = try resources.getOrCreateBuffer(self, copy.dst.handle, dst_size, types.WGPUBufferUsage_CopyDst);
            procs.wgpuCommandEncoderCopyBufferToBuffer(encoder, src, copy.src.offset, dst, copy.dst.offset, bytes);
        },
        .buffer_to_texture => {
            const src_size = try resources.requiredBytes(bytes, copy.src.offset);
            const src = try resources.getOrCreateBuffer(self, copy.src.handle, src_size, types.WGPUBufferUsage_CopySrc);
            const dst = try resources.getOrCreateTexture(self, copy.dst, types.WGPUTextureUsage_CopyDst);
            procs.wgpuCommandEncoderCopyBufferToTexture(
                encoder,
                &types.WGPUTexelCopyBufferInfo{
                    .layout = .{
                        .offset = copy.src.offset,
                        .bytesPerRow = loader.normalizeCopyLayoutValue(copy.src.bytes_per_row),
                        .rowsPerImage = loader.normalizeCopyLayoutValue(copy.src.rows_per_image),
                    },
                    .buffer = src,
                },
                &types.WGPUTexelCopyTextureInfo{
                    .texture = dst,
                    .mipLevel = copy.dst.mip_level,
                    .origin = .{ .x = 0, .y = 0, .z = 0 },
                    .aspect = loader.normalizeTextureAspect(copy.dst.aspect),
                },
                .{
                    .width = copy.dst.width,
                    .height = copy.dst.height,
                    .depthOrArrayLayers = copy.dst.depth_or_array_layers,
                },
            );
        },
        .texture_to_buffer => {
            const dst_size = try resources.requiredBytes(bytes, copy.dst.offset);
            const src = try resources.getOrCreateTexture(self, copy.src, types.WGPUTextureUsage_CopySrc);
            const dst = try resources.getOrCreateBuffer(self, copy.dst.handle, dst_size, types.WGPUBufferUsage_CopyDst);
            procs.wgpuCommandEncoderCopyTextureToBuffer(
                encoder,
                &types.WGPUTexelCopyTextureInfo{
                    .texture = src,
                    .mipLevel = copy.src.mip_level,
                    .origin = .{ .x = 0, .y = 0, .z = 0 },
                    .aspect = loader.normalizeTextureAspect(copy.src.aspect),
                },
                &types.WGPUTexelCopyBufferInfo{
                    .layout = .{
                        .offset = copy.dst.offset,
                        .bytesPerRow = loader.normalizeCopyLayoutValue(copy.dst.bytes_per_row),
                        .rowsPerImage = loader.normalizeCopyLayoutValue(copy.dst.rows_per_image),
                    },
                    .buffer = dst,
                },
                .{
                    .width = copy.src.width,
                    .height = copy.src.height,
                    .depthOrArrayLayers = copy.src.depth_or_array_layers,
                },
            );
        },
        .texture_to_texture => {
            const src = try resources.getOrCreateTexture(self, copy.src, types.WGPUTextureUsage_CopySrc);
            const dst = try resources.getOrCreateTexture(self, copy.dst, types.WGPUTextureUsage_CopyDst);
            procs.wgpuCommandEncoderCopyTextureToTexture(
                encoder,
                &types.WGPUTexelCopyTextureInfo{
                    .texture = src,
                    .mipLevel = copy.src.mip_level,
                    .origin = .{ .x = 0, .y = 0, .z = 0 },
                    .aspect = loader.normalizeTextureAspect(copy.src.aspect),
                },
                &types.WGPUTexelCopyTextureInfo{
                    .texture = dst,
                    .mipLevel = copy.dst.mip_level,
                    .origin = .{ .x = 0, .y = 0, .z = 0 },
                    .aspect = loader.normalizeTextureAspect(copy.dst.aspect),
                },
                .{
                    .width = copy.src.width,
                    .height = copy.src.height,
                    .depthOrArrayLayers = copy.src.depth_or_array_layers,
                },
            );
        },
    }

    const command_buffer = procs.wgpuCommandEncoderFinish(encoder, &types.WGPUCommandBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (command_buffer == null) {
        return .{ .status = .@"error", .status_message = "commandEncoderFinish returned null" };
    }
    defer procs.wgpuCommandBufferRelease(command_buffer);

    var commands = [_]types.WGPUCommandBuffer{command_buffer};
    const submit_wait_ns = try self.submitCommandBuffers(commands[0..]);

    return .{
        .status = .ok,
        .status_message = switch (copy.direction) {
            .buffer_to_buffer => "copy-buffer-to-buffer command submitted",
            .buffer_to_texture => "copy-buffer-to-texture command submitted",
            .texture_to_buffer => "copy-texture-to-buffer command submitted",
            .texture_to_texture => "copy-texture-to-texture command submitted",
        },
        .submit_wait_ns = submit_wait_ns,
    };
}

fn executeBarrier(self: *Backend, barrier: model.BarrierCommand) !types.NativeExecutionResult {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const p0_procs = p0_procs_mod.loadP0Procs(self.dyn_lib);
    const clear_buffer = if (p0_procs) |loaded| loaded.command_encoder_clear_buffer else null;
    if (clear_buffer == null) {
        return executeNoopCommand(self, "barrier command translated into empty command buffer");
    }
    const clear_size = loader.alignTo(@max(@as(u64, 16), @as(u64, barrier.dependency_count) * 16), 4);
    const scratch_buffer = try resources.getOrCreateBuffer(
        self,
        BARRIER_SCRATCH_BUFFER_HANDLE,
        clear_size,
        types.WGPUBufferUsage_CopyDst,
    );
    const encoder = procs.wgpuDeviceCreateCommandEncoder(self.device.?, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) {
        return .{ .status = .@"error", .status_message = "deviceCreateCommandEncoder returned null" };
    }
    defer procs.wgpuCommandEncoderRelease(encoder);
    clear_buffer.?(encoder, scratch_buffer, 0, clear_size);
    const command_buffer = procs.wgpuCommandEncoderFinish(encoder, &types.WGPUCommandBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (command_buffer == null) {
        return .{ .status = .@"error", .status_message = "commandEncoderFinish returned null" };
    }
    defer procs.wgpuCommandBufferRelease(command_buffer);
    var commands = [_]types.WGPUCommandBuffer{command_buffer};
    const submit_wait_ns = try self.submitCommandBuffers(commands[0..]);
    return .{
        .status = .ok,
        .status_message = "barrier command lowered via commandEncoderClearBuffer",
        .submit_wait_ns = submit_wait_ns,
    };
}

fn executeDispatch(self: *Backend, dispatch: model.DispatchCommand) !types.NativeExecutionResult {
    if (dispatch.x == 0 and dispatch.y == 0 and dispatch.z == 0) {
        return .{
            .status = .unsupported,
            .status_message = "dispatch dimensions must be non-zero",
        };
    }
    return executeKernelDispatchKernel(self, "builtin:noop", "main", dispatch.x, dispatch.y, dispatch.z, 1, .{
        .source = loader.BUILTIN_KERNEL_DEFAULT_SOURCE,
        .owned = false,
        .mode = .fallback,
    }, null);
}

fn executeKernelDispatch(self: *Backend, kernel: model.KernelDispatchCommand) !types.NativeExecutionResult {
    if (kernel.x == 0 and kernel.y == 0 and kernel.z == 0) {
        return .{ .status = .unsupported, .status_message = "kernel_dispatch dimensions must be non-zero" };
    }
    if (kernel.kernel.len == 0) {
        return .{ .status = .unsupported, .status_message = "kernel_dispatch requires a non-empty kernel marker" };
    }
    if (kernel.repeat == 0) {
        return .{ .status = .unsupported, .status_message = "kernel_dispatch repeat must be > 0" };
    }
    const source = resolveKernelSource(self, kernel.kernel) catch |err| {
        const message = switch (err) {
            error.MissingKernelSource => "kernel_dispatch has no resolvable WGSL source",
        };
        return .{ .status = .unsupported, .status_message = message };
    };
    const entry_point = kernel.entry_point orelse "main";
    return executeKernelDispatchKernel(self, kernel.kernel, entry_point, kernel.x, kernel.y, kernel.z, kernel.repeat, source, kernel.bindings);
}

fn pipelineCacheKey(source_bytes: []const u8, entry_point: []const u8) u64 {
    var h: u64 = 0x9e3779b97f4a7c15;
    for (source_bytes) |b| {
        h = (h ^ b) *% 0x517cc1b727220a95;
    }
    h ^= 0xff;
    for (entry_point) |b| {
        h = (h ^ b) *% 0x517cc1b727220a95;
    }
    return h;
}

fn executeKernelDispatchKernel(
    self: *Backend,
    kernel_name: []const u8,
    entry_point: []const u8,
    x: u32,
    y: u32,
    z: u32,
    repeat_count: u32,
    source: types.KernelSource,
    bindings: ?[]const model.KernelBinding,
) !types.NativeExecutionResult {
    const setup_start_ns = std.time.nanoTimestamp();
    defer if (source.owned) self.allocator.free(source.source);
    if (!sourceContainsComputeStage(source.source)) {
        return .{
            .status = .unsupported,
            .status_message = "kernel source missing @compute stage",
        };
    }

    const procs = self.procs orelse return error.ProceduralNotReady;
    const p0_procs = p0_procs_mod.loadP0Procs(self.dyn_lib);

    const cache_key = pipelineCacheKey(source.source, entry_point);
    const cached = self.pipeline_cache.get(cache_key);

    var artifacts: ?types.DispatchPassArtifacts = null;
    if (bindings) |bound| {
        if (bound.len > 0) {
            artifacts = try resources.buildDispatchPassGroups(self, bound);
        }
    }
    defer {
        if (artifacts) |dispatch_artifacts| {
            for (dispatch_artifacts.texture_views) |texture_view| {
                procs.wgpuTextureViewRelease(texture_view);
            }
            self.allocator.free(dispatch_artifacts.texture_views);

            for (dispatch_artifacts.pass_bind_groups) |bind_group| {
                if (bind_group) |bound_group| {
                    procs.wgpuBindGroupRelease(bound_group);
                }
            }
            self.allocator.free(dispatch_artifacts.pass_bind_groups);

            for (dispatch_artifacts.group_layouts) |group_layout| {
                procs.wgpuBindGroupLayoutRelease(group_layout);
            }
            self.allocator.free(dispatch_artifacts.group_layouts);
        }
    }

    var pipeline_layout: types.WGPUPipelineLayout = null;
    var owns_pipeline_layout = false;
    if (cached == null) {
        if (artifacts) |dispatch_artifacts| {
            if (dispatch_artifacts.group_layouts.len > 0) {
                pipeline_layout = try resources.createPipelineLayout(self, dispatch_artifacts.group_layouts);
                owns_pipeline_layout = true;
            }
        }
    }
    defer if (owns_pipeline_layout) if (pipeline_layout) |layout| procs.wgpuPipelineLayoutRelease(layout);

    const shader_module = if (cached) |hit| hit.shader_module else resources.createShaderModule(self, source.source) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.KernelModuleCreationFailed => "shader module creation returned null",
                error.ProceduralNotReady => "backend not ready",
            },
        };
    };

    const pipeline = if (cached) |hit| hit.pipeline else resources.createComputePipeline(self, kernel_name, shader_module, entry_point, pipeline_layout) catch {
        procs.wgpuShaderModuleRelease(shader_module);
        return .{ .status = .@"error", .status_message = "compute pipeline creation failed" };
    };

    if (cached == null) {
        self.pipeline_cache.put(cache_key, .{
            .shader_module = shader_module,
            .pipeline = pipeline,
        }) catch {};
    }

    const use_timestamps = self.has_timestamp_query;
    self.timestampLog(
        "dispatch kernel={s} repeat={} adapter_timestamp_query={} device_timestamp_query={}\n",
        .{ kernel_name, repeat_count, self.adapter_has_timestamp_query, self.has_timestamp_query },
    );
    var query_set: types.WGPUQuerySet = null;
    var resolve_buffer: types.WGPUBuffer = null;
    var readback_buffer: types.WGPUBuffer = null;
    const dispatch_indirect_proc = if (p0_procs) |loaded| loaded.compute_pass_encoder_dispatch_workgroups_indirect else null;
    const command_encoder_write_buffer = if (p0_procs) |loaded| loaded.command_encoder_write_buffer else null;
    const compute_pass_write_timestamp = if (p0_procs) |loaded| loaded.compute_pass_encoder_write_timestamp else null;
    var dispatch_indirect_buffer: types.WGPUBuffer = null;

    if (use_timestamps) {
        query_set = procs.wgpuDeviceCreateQuerySet(self.device.?, &types.WGPUQuerySetDescriptor{
            .nextInChain = null,
            .label = loader.emptyStringView(),
            .@"type" = types.WGPUQueryType_Timestamp,
            .count = 2,
        });
        if (query_set != null) {
            if (!p0_procs_mod.querySetMatches(p0_procs, query_set, 2, types.WGPUQueryType_Timestamp)) {
                p0_procs_mod.destroyQuerySet(p0_procs, query_set);
                procs.wgpuQuerySetRelease(query_set);
                query_set = null;
            }
        }
        if (query_set != null) {
            resolve_buffer = procs.wgpuDeviceCreateBuffer(self.device.?, &types.WGPUBufferDescriptor{
                .nextInChain = null,
                .label = loader.emptyStringView(),
                .usage = types.WGPUBufferUsage_QueryResolve | types.WGPUBufferUsage_CopySrc,
                .size = types.TIMESTAMP_BUFFER_SIZE,
                .mappedAtCreation = types.WGPU_FALSE,
            });
            readback_buffer = procs.wgpuDeviceCreateBuffer(self.device.?, &types.WGPUBufferDescriptor{
                .nextInChain = null,
                .label = loader.emptyStringView(),
                .usage = types.WGPUBufferUsage_MapRead | types.WGPUBufferUsage_CopyDst,
                .size = types.TIMESTAMP_BUFFER_SIZE,
                .mappedAtCreation = types.WGPU_FALSE,
            });
        }
    }
    if (dispatch_indirect_proc != null and command_encoder_write_buffer != null) {
        dispatch_indirect_buffer = resources.getOrCreateBuffer(
            self,
            DISPATCH_INDIRECT_ARGS_HANDLE,
            @sizeOf([3]u32),
            BUFFER_USAGE_INDIRECT | types.WGPUBufferUsage_CopyDst,
        ) catch null;
    }
    const timestamps_active = query_set != null and resolve_buffer != null and readback_buffer != null;
    self.timestampLog(
        "timestamp_artifacts qs={} resolve={} readback={} active={}\n",
        .{ query_set != null, resolve_buffer != null, readback_buffer != null, timestamps_active },
    );
    if (!use_timestamps) {
        self.timestampLog("timestamp_path_disabled feature_unavailable\n", .{});
    } else if (!timestamps_active) {
        self.timestampLog(
            "timestamp_artifacts query_set={} resolve_buffer={} readback_buffer={}\n",
            .{ query_set != null, resolve_buffer != null, readback_buffer != null },
        );
    }
    defer {
        if (query_set) |qs| {
            p0_procs_mod.destroyQuerySet(p0_procs, qs);
            procs.wgpuQuerySetRelease(qs);
        }
        if (resolve_buffer) |buf| procs.wgpuBufferRelease(buf);
        if (readback_buffer) |buf| procs.wgpuBufferRelease(buf);
    }

    const setup_end_ns = std.time.nanoTimestamp();

    const encode_start_ns = std.time.nanoTimestamp();
    const encoder = procs.wgpuDeviceCreateCommandEncoder(self.device.?, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) {
        return .{ .status = .@"error", .status_message = "deviceCreateCommandEncoder returned null" };
    }
    defer procs.wgpuCommandEncoderRelease(encoder);

    const command_encoder_write_timestamp = procs.wgpuCommandEncoderWriteTimestamp;
    const use_compute_pass_timestamps = timestamps_active and compute_pass_write_timestamp != null and self.has_timestamp_inside_passes;
    const use_command_encoder_timestamps = timestamps_active and !use_compute_pass_timestamps and command_encoder_write_timestamp != null and self.has_timestamp_inside_passes;
    if (timestamps_active) {
        const mode = if (use_compute_pass_timestamps) "compute_pass" else if (use_command_encoder_timestamps) "command_encoder" else "pass_timestamp_writes";
        self.timestampLog(
            "timestamp_write_mode={s}\n",
            .{mode},
        );
    }
    var timestamp_writes = types.WGPUPassTimestampWrites{
        .nextInChain = null,
        .querySet = query_set,
        .beginningOfPassWriteIndex = 0,
        .endOfPassWriteIndex = 1,
    };

    if (use_command_encoder_timestamps) {
        command_encoder_write_timestamp.?(encoder, query_set, 0);
    }
    if (dispatch_indirect_proc != null and command_encoder_write_buffer != null and dispatch_indirect_buffer != null) {
        const dispatch_args = [3]u32{ x, y, z };
        const dispatch_args_bytes = std.mem.asBytes(&dispatch_args);
        command_encoder_write_buffer.?(encoder, dispatch_indirect_buffer, 0, dispatch_args_bytes.ptr, @as(u64, dispatch_args_bytes.len));
    }

    const pass = procs.wgpuCommandEncoderBeginComputePass(
        encoder,
        &types.WGPUComputePassDescriptor{
            .nextInChain = null,
            .label = loader.emptyStringView(),
            .timestampWrites = if (timestamps_active and !use_command_encoder_timestamps and !use_compute_pass_timestamps) &timestamp_writes else null,
        },
    );
    if (pass == null) {
        return .{ .status = .@"error", .status_message = "commandEncoderBeginComputePass returned null" };
    }
    defer procs.wgpuComputePassEncoderRelease(pass);

    procs.wgpuComputePassEncoderSetPipeline(pass, pipeline);
    if (artifacts) |dispatch_artifacts| {
        for (dispatch_artifacts.pass_bind_groups, 0..) |bind_group, group| {
            if (bind_group) |actual_bind_group| {
                procs.wgpuComputePassEncoderSetBindGroup(
                    pass,
                    @as(u32, @intCast(group)),
                    actual_bind_group,
                    0,
                    null,
                );
            }
        }
    }
    if (use_compute_pass_timestamps) {
        compute_pass_write_timestamp.?(pass, query_set, 0);
    }
    var dispatch_index: u32 = 0;
    while (dispatch_index < repeat_count) : (dispatch_index += 1) {
        if (dispatch_indirect_proc != null and dispatch_indirect_buffer != null) {
            dispatch_indirect_proc.?(pass, dispatch_indirect_buffer, 0);
        } else {
            procs.wgpuComputePassEncoderDispatchWorkgroups(pass, x, y, z);
        }
    }
    if (use_compute_pass_timestamps) {
        compute_pass_write_timestamp.?(pass, query_set, 1);
    }
    procs.wgpuComputePassEncoderEnd(pass);
    if (use_command_encoder_timestamps) {
        command_encoder_write_timestamp.?(encoder, query_set, 1);
    }

    if (timestamps_active) {
        procs.wgpuCommandEncoderResolveQuerySet(encoder, query_set, 0, 2, resolve_buffer, 0);
        procs.wgpuCommandEncoderCopyBufferToBuffer(encoder, resolve_buffer, 0, readback_buffer, 0, types.TIMESTAMP_BUFFER_SIZE);
    }

    const command_buffer = procs.wgpuCommandEncoderFinish(encoder, &types.WGPUCommandBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (command_buffer == null) {
        return .{ .status = .@"error", .status_message = "commandEncoderFinish returned null" };
    }
    defer procs.wgpuCommandBufferRelease(command_buffer);
    const encode_end_ns = std.time.nanoTimestamp();

    var commands = [_]types.WGPUCommandBuffer{command_buffer};
    const submit_wait_ns = try self.submitCommandBuffers(commands[0..]);

    const setup_ns = if (setup_end_ns > setup_start_ns)
        @as(u64, @intCast(setup_end_ns - setup_start_ns))
    else
        0;
    const encode_ns = if (encode_end_ns > encode_start_ns)
        @as(u64, @intCast(encode_end_ns - encode_start_ns))
    else
        0;
    var gpu_timestamp_ns: u64 = 0;
    var gpu_timestamp_valid = false;
    if (timestamps_active) {
        gpu_timestamp_ns = self.readTimestampBuffer(readback_buffer) catch |err| {
            self.timestampLog("timestamp_readback_error={s}\n", .{@errorName(err)});
            return .{
                .status = .@"error",
                .status_message = timestampReadbackStatus(err),
                .setup_ns = setup_ns,
                .encode_ns = encode_ns,
                .submit_wait_ns = submit_wait_ns,
                .dispatch_count = repeat_count,
                .gpu_timestamp_attempted = true,
                .gpu_timestamp_valid = false,
            };
        };
        gpu_timestamp_valid = gpu_timestamp_ns > 0;
        self.timestampLog("timestamp_ns={}\n", .{gpu_timestamp_ns});
    }

    return .{
        .status = .ok,
        .status_message = switch (source.mode) {
            .fallback => "dispatch command executed through fallback compute kernel",
            .builtin => "kernel source resolved via built-in kernel map",
            .file => "kernel source loaded and executed",
        },
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = repeat_count,
        .gpu_timestamp_ns = gpu_timestamp_ns,
        .gpu_timestamp_attempted = timestamps_active,
        .gpu_timestamp_valid = gpu_timestamp_valid,
    };
}

fn executeNoopCommand(self: *Backend, reason: []const u8) !types.NativeExecutionResult {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const encoder = procs.wgpuDeviceCreateCommandEncoder(self.device.?, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) {
        return .{ .status = .@"error", .status_message = "deviceCreateCommandEncoder returned null" };
    }
    defer procs.wgpuCommandEncoderRelease(encoder);

    const command_buffer = procs.wgpuCommandEncoderFinish(encoder, &types.WGPUCommandBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (command_buffer == null) {
        return .{ .status = .@"error", .status_message = "commandEncoderFinish returned null" };
    }
    defer procs.wgpuCommandBufferRelease(command_buffer);

    var commands = [_]types.WGPUCommandBuffer{command_buffer};
    const submit_wait_ns = try self.submitCommandBuffers(commands[0..]);

    return .{
        .status = .ok,
        .status_message = reason,
        .submit_wait_ns = submit_wait_ns,
    };
}

fn timestampReadbackStatus(err: anyerror) []const u8 {
    return switch (err) {
        error.BufferMapTimeout => "gpu timestamp map timeout",
        error.BufferMapFailed => "gpu timestamp map failed",
        error.TimestampRangeInvalid => "gpu timestamp range invalid",
        error.WaitTimedOut => "gpu timestamp wait timed out",
        else => "gpu timestamp readback failed",
    };
}

fn resolveKernelSource(self: *Backend, kernel_name: []const u8) !types.KernelSource {
    if (kernel_name.len == 0) return error.MissingKernelSource;
    if (kernelForName(kernel_name)) |builtin_source| {
        return .{ .source = builtin_source, .owned = false, .mode = .builtin };
    }
    if (openKernelFile(self, kernel_name)) |source| return source;
    if (self.kernel_root) |root| {
        if (openKernelFromRoot(self, kernel_name, root)) |source| return source;
    }
    return error.MissingKernelSource;
}

fn kernelForName(kernel_name: []const u8) ?[]const u8 {
    if (std.mem.eql(u8, kernel_name, "builtin:noop")) return loader.BUILTIN_KERNEL_DEFAULT_SOURCE;
    if (std.mem.eql(u8, kernel_name, "fawn.noop")) return loader.BUILTIN_KERNEL_DEFAULT_SOURCE;
    if (std.mem.eql(u8, kernel_name, "copy_textures_x32")) return loader.BUILTIN_KERNEL_DEFAULT_SOURCE;
    return null;
}

fn openKernelFile(self: *Backend, path: []const u8) ?types.KernelSource {
    const maybe_file = std.fs.cwd().openFile(path, .{}) catch |err| {
        if (err == error.FileNotFound or err == error.NoSuchFileOrDirectory) {
            return null;
        }
        return null;
    };
    defer maybe_file.close();
    const text = maybe_file.readToEndAlloc(self.allocator, MAX_KERNEL_SOURCE_BYTES) catch return null;
    if (text.len == 0) {
        self.allocator.free(text);
        return null;
    }
    return .{ .source = text, .owned = true, .mode = .file };
}

fn openKernelFromRoot(self: *Backend, kernel_name: []const u8, root: []const u8) ?types.KernelSource {
    if (kernel_name.len == 0) return null;
    const direct = std.fs.path.join(self.allocator, &[_][]const u8{ root, kernel_name }) catch return null;
    defer self.allocator.free(direct);
    if (openKernelFile(self, direct)) |source| return source;

    if (!std.mem.endsWith(u8, kernel_name, ".wgsl")) {
        const named = std.fmt.allocPrint(self.allocator, "{s}.wgsl", .{kernel_name}) catch return null;
        defer self.allocator.free(named);
        const candidate = std.fs.path.join(self.allocator, &[_][]const u8{ root, named }) catch return null;
        defer self.allocator.free(candidate);
        if (openKernelFile(self, candidate)) |source| return source;
    }
    return null;
}

fn hasValidTextureExtent(resource: model.CopyTextureResource) bool {
    return resource.width > 0 and resource.height > 0 and resource.depth_or_array_layers > 0;
}

fn hasMatchingTextureExtent(src: model.CopyTextureResource, dst: model.CopyTextureResource) bool {
    return src.width == dst.width and
        src.height == dst.height and
        src.depth_or_array_layers == dst.depth_or_array_layers;
}

fn sourceContainsComputeStage(source: []const u8) bool {
    return std.mem.indexOf(u8, source, "@compute") != null;
}
