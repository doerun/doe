const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

const MapAsyncContext = struct {
    resolved: bool = false,
    status: types.WGPUBufferMapAsyncStatus = undefined,
};

fn onMapBufferCallback(
    status: types.WGPUMapAsyncStatus,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    if (userdata1) |ptr| {
        var context = @as(*MapAsyncContext, @ptrCast(@alignCast(ptr)));
        context.status = status;
        context.resolved = true;
    }
}

pub fn executeMapAsync(self: *Backend, command: model.MapAsyncCommand) !types.NativeExecutionResult {
    const setup_start_ns = std.time.nanoTimestamp();
    const bytes = @as(u64, command.bytes);

    const usage: types.WGPUBufferUsage = if (command.mode == .read)
        types.WGPUBufferUsage_MapRead | types.WGPUBufferUsage_CopyDst
    else
        types.WGPUBufferUsage_MapWrite | types.WGPUBufferUsage_CopySrc;

    const buffer = try resources.getOrCreateBuffer(self, loader.BUFFER_MAP_ASYNC_KEY, bytes, usage);

    // Unmap first in case it was mapped from a previous iteration
    self.procs.?.wgpuBufferUnmap(buffer);

    var map_context = MapAsyncContext{};
    const mode_flag: types.WGPUMapMode = if (command.mode == .read) types.WGPUMapMode_Read else types.WGPUMapMode_Write;

    // Map the buffer
    _ = self.procs.?.wgpuBufferMapAsync(
        buffer,
        mode_flag,
        0,
        bytes,
        .{
            .nextInChain = null,
            .mode = types.WGPUCallbackMode_WaitAnyOnly,
            .callback = onMapBufferCallback,
            .userdata1 = &map_context,
            .userdata2 = null,
        },
    );

    const setup_end_ns = std.time.nanoTimestamp();

    // Spin block wait for map_async completion
    const submit_wait_start_ns = std.time.nanoTimestamp();
    while (!map_context.resolved) {
        // Yield to browser/Dawn queue to resolve futures
        _ = try self.waitForQueueProcessEvents();
    }
    const submit_wait_end_ns = std.time.nanoTimestamp();

    if (map_context.status != types.WGPUBufferMapAsyncStatus_Success) {
        return .{
            .status = .@"error",
            .status_message = "buffer map async failed",
        };
    }

    if (command.mode == .write) {
        const mapped_ptr = self.procs.?.wgpuBufferGetMappedRange(buffer, 0, bytes);
        if (mapped_ptr != null) {
            // Write some dummy data zero payload to force page fault materialization
            @memset(@as([*]u8, @ptrCast(mapped_ptr))[0..bytes], 0);
        }
    }

    // Clean up map for next iteration (benchmarks map/unmap synchronously inside operations)
    self.procs.?.wgpuBufferUnmap(buffer);

    const setup_ns = if (setup_end_ns > setup_start_ns) @as(u64, @intCast(setup_end_ns - setup_start_ns)) else 0;
    const submit_wait_ns = if (submit_wait_end_ns > submit_wait_start_ns) @as(u64, @intCast(submit_wait_end_ns - submit_wait_start_ns)) else 0;

    return .{
        .status = .ok,
        .status_message = "buffer map resolved synchronously",
        .setup_ns = setup_ns,
        .submit_wait_ns = submit_wait_ns,
    };
}

pub fn executeUpload(self: *Backend, upload: model.UploadCommand) !types.NativeExecutionResult {
    const setup_start_ns = std.time.nanoTimestamp();
    const bytes = @as(u64, upload.bytes);

    const usage = switch (self.upload_buffer_usage_mode) {
        .copy_dst_copy_src => types.WGPUBufferUsage_CopyDst | types.WGPUBufferUsage_CopySrc,
        .copy_dst => types.WGPUBufferUsage_CopyDst,
    };
    const upload_buffer = try resources.getOrCreateBuffer(self, loader.BUFFER_UPLOAD_KEY, bytes, usage);
    const bytes_usize = std.math.cast(usize, bytes) orelse unreachable;

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

pub fn executeCopy(self: *Backend, copy: model.CopyCommand) !types.NativeExecutionResult {
    const bytes = @as(u64, copy.bytes);

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
            const dst = try resources.getOrCreateTexture(self, copy.dst, types.WGPUTextureUsage_CopyDst);

            if (copy.uses_temporary_buffer) {
                const alignment: u64 = @max(copy.temporary_buffer_alignment, 1);
                const aligned_size = ((bytes + alignment - 1) / alignment) * alignment;
                const src = try resources.getOrCreateBuffer(self, copy.src.handle, src_size, types.WGPUBufferUsage_CopySrc | types.WGPUBufferUsage_CopyDst);
                const temp_key = copy.src.handle +% 0xFFFF_0000_0000_0001;
                const temp = try resources.getOrCreateBuffer(self, temp_key, aligned_size, types.WGPUBufferUsage_CopySrc | types.WGPUBufferUsage_CopyDst);
                procs.wgpuCommandEncoderCopyBufferToBuffer(encoder, src, copy.src.offset, temp, 0, bytes);
                procs.wgpuCommandEncoderCopyBufferToTexture(
                    encoder,
                    &types.WGPUTexelCopyBufferInfo{
                        .layout = .{
                            .offset = 0,
                            .bytesPerRow = loader.normalizeCopyLayoutValue(copy.src.bytes_per_row),
                            .rowsPerImage = loader.normalizeCopyLayoutValue(copy.src.rows_per_image),
                        },
                        .buffer = temp,
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
            } else {
                const src = try resources.getOrCreateBuffer(self, copy.src.handle, src_size, types.WGPUBufferUsage_CopySrc);
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
            }
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
            if (copy.uses_temporary_buffer) {
                // Workaround path: tex → temp buffer → tex (avoids direct tex-to-tex copy bugs)
                const alignment: u64 = @max(copy.temporary_buffer_alignment, 1);
                const aligned_size = ((bytes + alignment - 1) / alignment) * alignment;
                const temp_key = copy.src.handle +% 0xFFFF_0000_0000_0002;
                const temp = try resources.getOrCreateBuffer(self, temp_key, aligned_size, types.WGPUBufferUsage_CopySrc | types.WGPUBufferUsage_CopyDst);
                const src = try resources.getOrCreateTexture(self, copy.src, types.WGPUTextureUsage_CopySrc);
                const dst = try resources.getOrCreateTexture(self, copy.dst, types.WGPUTextureUsage_CopyDst);

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
                            .offset = 0,
                            .bytesPerRow = loader.normalizeCopyLayoutValue(copy.src.bytes_per_row),
                            .rowsPerImage = loader.normalizeCopyLayoutValue(copy.src.rows_per_image),
                        },
                        .buffer = temp,
                    },
                    .{
                        .width = copy.src.width,
                        .height = copy.src.height,
                        .depthOrArrayLayers = copy.src.depth_or_array_layers,
                    },
                );

                procs.wgpuCommandEncoderCopyBufferToTexture(
                    encoder,
                    &types.WGPUTexelCopyBufferInfo{
                        .layout = .{
                            .offset = 0,
                            .bytesPerRow = loader.normalizeCopyLayoutValue(copy.dst.bytes_per_row),
                            .rowsPerImage = loader.normalizeCopyLayoutValue(copy.dst.rows_per_image),
                        },
                        .buffer = temp,
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
            } else {
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
            }
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
