const std = @import("std");
const testing = std.testing;
const webgpu_types = @import("model_webgpu_types.zig");

test "texture usage flags are distinct powers of two" {
    const flags = [_]webgpu_types.WGPUFlags{
        webgpu_types.WGPUTextureUsage_CopySrc,
        webgpu_types.WGPUTextureUsage_CopyDst,
        webgpu_types.WGPUTextureUsage_TextureBinding,
        webgpu_types.WGPUTextureUsage_StorageBinding,
        webgpu_types.WGPUTextureUsage_RenderAttachment,
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
