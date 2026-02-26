const std = @import("std");
const pipeline_cache = @import("../../src/backend/metal/pipeline/pipeline_cache.zig");

test "metal pipeline cache lookup succeeds" {
    try pipeline_cache.pipeline_cache_lookup();
}
