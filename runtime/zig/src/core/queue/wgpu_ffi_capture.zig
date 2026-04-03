const std = @import("std");
const types = @import("../abi/wgpu_types.zig");
const loader = @import("../abi/wgpu_loader.zig");
const WebGPUBackend = @import("../../webgpu_backend.zig").WebGPUBackend;

const CAPTURE_ALIGNMENT_BYTES: u64 = 4;

pub fn captureBuffer(
    self: *WebGPUBackend,
    allocator: std.mem.Allocator,
    handle: u64,
    offset: u64,
    size: u64,
) ![]u8 {
    if (size == 0) return error.InvalidArgument;
    if ((offset % CAPTURE_ALIGNMENT_BYTES) != 0 or (size % CAPTURE_ALIGNMENT_BYTES) != 0) {
        return error.InvalidArgument;
    }

    const procs = self.core.procs orelse return error.ProceduralNotReady;
    const queue = self.core.queue orelse return error.ProceduralNotReady;
    const device = self.core.device orelse return error.ProceduralNotReady;
    const source_record = self.core.buffers.get(handle) orelse return error.InvalidArgument;
    const end = std.math.add(u64, offset, size) catch return error.InvalidArgument;
    if (end > source_record.size) return error.InvalidArgument;
    if ((source_record.usage & types.WGPUBufferUsage_CopySrc) == 0) return error.UnsupportedFeature;

    const readback_buffer = procs.wgpuDeviceCreateBuffer(device, &types.WGPUBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .usage = types.WGPUBufferUsage_MapRead | types.WGPUBufferUsage_CopyDst,
        .size = size,
        .mappedAtCreation = types.WGPU_FALSE,
    });
    if (readback_buffer == null) return error.BufferAllocationFailed;
    defer procs.wgpuBufferRelease(readback_buffer);

    const encoder = procs.wgpuDeviceCreateCommandEncoder(device, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) return error.CommandEncoderUnavailable;
    defer procs.wgpuCommandEncoderRelease(encoder);

    procs.wgpuCommandEncoderCopyBufferToBuffer(
        encoder,
        source_record.buffer,
        offset,
        readback_buffer,
        0,
        size,
    );

    const command_buffer = procs.wgpuCommandEncoderFinish(encoder, &types.WGPUCommandBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (command_buffer == null) return error.CommandEncoderFinishFailed;
    defer procs.wgpuCommandBufferRelease(command_buffer);

    var command_buffers = [_]types.WGPUCommandBuffer{command_buffer};
    procs.wgpuQueueSubmit(queue, command_buffers.len, &command_buffers);
    try self.waitForQueue();

    return try mapReadbackBytes(self, allocator, procs, readback_buffer, size);
}

fn mapReadbackBytes(
    self: *WebGPUBackend,
    allocator: std.mem.Allocator,
    procs: types.Procs,
    readback_buffer: types.WGPUBuffer,
    size: u64,
) ![]u8 {
    const size_usize = std.math.cast(usize, size) orelse return error.InvalidArgument;
    var map_state = types.BufferMapState{};
    const map_callback_info = types.WGPUBufferMapCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_AllowProcessEvents,
        .callback = loader.bufferMapCallback,
        .userdata1 = &map_state,
        .userdata2 = null,
    };
    const map_future = procs.wgpuBufferMapAsync(
        readback_buffer,
        types.WGPUMapMode_Read,
        0,
        size_usize,
        map_callback_info,
    );
    if (map_future.id == 0) return error.BufferMapFailed;

    try self.processEventsUntil(&map_state.done, loader.DEFAULT_TIMEOUT_NS);
    if (!map_state.done) return error.BufferMapTimeout;
    if (map_state.status != types.WGPUMapAsyncStatus_Success) return error.BufferMapFailed;

    const mapped_ptr = procs.wgpuBufferGetConstMappedRange(readback_buffer, 0, size_usize) orelse {
        return error.BufferMapFailed;
    };
    defer procs.wgpuBufferUnmap(readback_buffer);

    const bytes = @as([*]const u8, @ptrCast(mapped_ptr))[0..size_usize];
    return try allocator.dupe(u8, bytes);
}
