const std = @import("std");
const vulkan_pipeline_cache = @import("../../src/backend/vulkan/pipeline/pipeline_cache.zig");
const vulkan_wgsl_ingest = @import("../../src/backend/vulkan/pipeline/wgsl_ingest.zig");
const vulkan_wgsl_to_spirv_runner = @import("../../src/backend/vulkan/pipeline/wgsl_to_spirv_runner.zig");

test "vulkan wgsl-to-spirv reports unsupported until IR layer is built" {
    try vulkan_wgsl_ingest.ingest();
    const result = vulkan_wgsl_to_spirv_runner.run();
    try std.testing.expectError(error.UnsupportedFeature, result);
}

test "vulkan pipeline cache lookup succeeds" {
    try vulkan_pipeline_cache.pipeline_cache_lookup();
}
