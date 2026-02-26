const std = @import("std");
const pipeline_cache = @import("../../src/backend/metal/pipeline/pipeline_cache.zig");

test "metal pipeline cache reports unsupported" {
    try std.testing.expectError(error.Unsupported, pipeline_cache.pipeline_cache_lookup());
}
