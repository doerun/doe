const std = @import("std");
const testing = std.testing;
const gpu_types = @import("model_gpu_types.zig");

test "texture usage flags are distinct powers of two" {
    const flags = [_]gpu_types.WGPUFlags{
        gpu_types.WGPUTextureUsage_CopySrc,
        gpu_types.WGPUTextureUsage_CopyDst,
        gpu_types.WGPUTextureUsage_TextureBinding,
        gpu_types.WGPUTextureUsage_StorageBinding,
        gpu_types.WGPUTextureUsage_RenderAttachment,
    };
    for (flags, 0..) |a, i| {
        try testing.expect(a != 0);
        try testing.expect(a & (a - 1) == 0);
        for (flags[i + 1 ..]) |b| {
            try testing.expect(a != b);
            try testing.expect(a & b == 0);
        }
    }
}
