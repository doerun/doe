const std = @import("std");
const contract = @import("../../contracts/command_recording.zig");
const abi = @import("../../core/abi/wgpu_core_base_types.zig");
const objects = @import("../support/doe_native_object_types.zig");

const COPY_ALIGNMENT: u64 = 4;

pub const Copy = struct {
    source: ?*objects.DoeBuffer,
    source_offset: u64,
    destination: ?*objects.DoeBuffer,
    destination_offset: u64,
    size: u64,
};

pub const AliasPolicy = enum { distinct_buffers, disjoint_ranges };
pub const ValidationError = contract.BufferCopyError;

pub fn validate(device: *objects.DoeDevice, copy: Copy, alias: AliasPolicy) ValidationError!u64 {
    const source = copy.source orelse return error.InvalidArgument;
    const destination = copy.destination orelse return error.InvalidArgument;
    if (source.error_object or source.destroyed or destination.error_object or destination.destroyed)
        return error.InvalidArgument;
    if (source.dev != device or destination.dev != device) return error.BufferCopyDeviceMismatch;
    if (source.usage & abi.WGPUBufferUsage_CopySrc == 0 or destination.usage & abi.WGPUBufferUsage_CopyDst == 0)
        return error.BufferCopyUsageMissing;
    if (copy.source_offset > source.size or copy.destination_offset > destination.size)
        return error.BufferCopyOutOfBounds;
    const size = if (copy.size == std.math.maxInt(u64)) source.size - copy.source_offset else copy.size;
    if (copy.source_offset % COPY_ALIGNMENT != 0 or copy.destination_offset % COPY_ALIGNMENT != 0 or size % COPY_ALIGNMENT != 0)
        return error.BufferCopyUnaligned;
    if (size > source.size - copy.source_offset or size > destination.size - copy.destination_offset)
        return error.BufferCopyOutOfBounds;
    if (source == destination and (alias == .distinct_buffers or
        (size != 0 and copy.source_offset < copy.destination_offset + size and copy.destination_offset < copy.source_offset + size)))
        return error.BufferCopyAliasing;
    return size;
}

test "buffer copy validation resolves whole size and keeps alias contracts explicit" {
    var device = objects.DoeDevice{};
    var source = objects.DoeBuffer{ .dev = &device, .size = 32, .usage = abi.WGPUBufferUsage_CopySrc | abi.WGPUBufferUsage_CopyDst };
    var destination = objects.DoeBuffer{ .dev = &device, .size = 16, .usage = abi.WGPUBufferUsage_CopyDst };
    var copy = Copy{ .source = &source, .source_offset = 16, .destination = &destination, .destination_offset = 0, .size = std.math.maxInt(u64) };
    try std.testing.expectEqual(@as(u64, 16), try validate(&device, copy, .distinct_buffers));
    copy.source_offset = 32;
    copy.destination_offset = 16;
    try std.testing.expectEqual(@as(u64, 0), try validate(&device, copy, .distinct_buffers));
    copy = .{ .source = &source, .source_offset = 0, .destination = &source, .destination_offset = 16, .size = 16 };
    try std.testing.expectEqual(@as(u64, 16), try validate(&device, copy, .disjoint_ranges));
    try std.testing.expectError(error.BufferCopyAliasing, validate(&device, copy, .distinct_buffers));
    copy.destination_offset = 12;
    try std.testing.expectError(error.BufferCopyAliasing, validate(&device, copy, .disjoint_ranges));
    copy.size = 0;
    try std.testing.expectError(error.BufferCopyAliasing, validate(&device, copy, .distinct_buffers));
}

test "buffer copy admission rejects device usage alignment range and object failures" {
    var device = objects.DoeDevice{};
    var other = objects.DoeDevice{};
    var source = objects.DoeBuffer{ .dev = &device, .size = 16, .usage = abi.WGPUBufferUsage_CopySrc };
    var destination = objects.DoeBuffer{ .dev = &device, .size = 16, .usage = abi.WGPUBufferUsage_CopyDst };
    var copy = Copy{ .source = &source, .source_offset = 0, .destination = &destination, .destination_offset = 0, .size = 4 };
    try std.testing.expectError(error.BufferCopyDeviceMismatch, validate(&other, copy, .distinct_buffers));
    destination.dev = null;
    try std.testing.expectError(error.BufferCopyDeviceMismatch, validate(&device, copy, .distinct_buffers));
    destination.dev = &device;
    for ([_]u64{ 0, 4 }) |size| {
        copy.size = size;
        source.usage = 0;
        try std.testing.expectError(error.BufferCopyUsageMissing, validate(&device, copy, .distinct_buffers));
        source.usage = abi.WGPUBufferUsage_CopySrc;
        destination.usage = 0;
        try std.testing.expectError(error.BufferCopyUsageMissing, validate(&device, copy, .distinct_buffers));
        destination.usage = abi.WGPUBufferUsage_CopyDst;
    }
    copy.source_offset = 1;
    try std.testing.expectError(error.BufferCopyUnaligned, validate(&device, copy, .distinct_buffers));
    copy.source_offset = 0;
    copy.destination_offset = 1;
    try std.testing.expectError(error.BufferCopyUnaligned, validate(&device, copy, .distinct_buffers));
    copy.destination_offset = 0;
    copy.size = 1;
    try std.testing.expectError(error.BufferCopyUnaligned, validate(&device, copy, .distinct_buffers));
    copy.size = 20;
    try std.testing.expectError(error.BufferCopyOutOfBounds, validate(&device, copy, .distinct_buffers));
    copy.source_offset = std.math.maxInt(u64) - 3;
    try std.testing.expectError(error.BufferCopyOutOfBounds, validate(&device, copy, .distinct_buffers));
    copy.source_offset = 0;
    copy.size = 4;
    source.destroyed = true;
    try std.testing.expectError(error.InvalidArgument, validate(&device, copy, .distinct_buffers));
    source.destroyed = false;
    destination.error_object = true;
    try std.testing.expectError(error.InvalidArgument, validate(&device, copy, .distinct_buffers));
}
