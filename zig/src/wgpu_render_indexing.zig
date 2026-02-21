const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const resources = @import("wgpu_resources.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

pub const DEFAULT_INDEX_BUFFER_HANDLE: u64 = 0x8C9F_2700_0000_0000;
pub const INDEX_FORMAT_UINT16: u32 = 0x00000001;
pub const INDEX_FORMAT_UINT32: u32 = 0x00000002;

pub const PreparedIndexBuffer = struct {
    buffer: types.WGPUBuffer,
    format: u32,
};

pub fn prepareIndexBuffer(self: *Backend, render: model.RenderDrawCommand) !?PreparedIndexBuffer {
    const requested_count = render.index_count orelse return null;
    if (requested_count == 0) return error.InvalidIndexedDrawData;

    const index_data = render.index_data orelse return error.InvalidIndexedDrawData;
    const index_usage = types.WGPUBufferUsage_Index | types.WGPUBufferUsage_CopyDst;
    const Selected = struct {
        format: u32,
        bytes: []const u8,
    };
    const selected: Selected = switch (index_data) {
        .uint16 => |values| blk: {
            const total_count = std.math.cast(u32, values.len) orelse return error.InvalidIndexedDrawData;
            const end = std.math.add(u32, render.first_index, requested_count) catch return error.InvalidIndexedDrawData;
            if (end > total_count) return error.InvalidIndexedDrawData;
            break :blk .{
                .format = INDEX_FORMAT_UINT16,
                .bytes = std.mem.sliceAsBytes(values),
            };
        },
        .uint32 => |values| blk: {
            const total_count = std.math.cast(u32, values.len) orelse return error.InvalidIndexedDrawData;
            const end = std.math.add(u32, render.first_index, requested_count) catch return error.InvalidIndexedDrawData;
            if (end > total_count) return error.InvalidIndexedDrawData;
            break :blk .{
                .format = INDEX_FORMAT_UINT32,
                .bytes = std.mem.sliceAsBytes(values),
            };
        },
    };

    const procs = self.procs orelse return error.ProceduralNotReady;
    const requested_size = std.math.cast(u64, selected.bytes.len) orelse return error.InvalidIndexedDrawData;
    const index_buffer = try resources.getOrCreateBuffer(
        self,
        DEFAULT_INDEX_BUFFER_HANDLE,
        requested_size,
        index_usage,
    );
    procs.wgpuQueueWriteBuffer(
        self.queue.?,
        index_buffer,
        0,
        selected.bytes.ptr,
        selected.bytes.len,
    );
    return .{
        .buffer = index_buffer,
        .format = selected.format,
    };
}
