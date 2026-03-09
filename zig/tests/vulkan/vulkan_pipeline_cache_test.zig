const std = @import("std");
const vulkan_pipeline_cache = @import("../../src/backend/vulkan/pipeline/pipeline_cache.zig");
const vulkan_wgsl_ingest = @import("../../src/backend/vulkan/pipeline/wgsl_ingest.zig");
const vulkan_wgsl_to_spirv_runner = @import("../../src/backend/vulkan/pipeline/wgsl_to_spirv_runner.zig");

test "vulkan wgsl-to-spirv runner accepts the sample shader" {
    try vulkan_wgsl_ingest.ingest();
    try vulkan_wgsl_to_spirv_runner.run();
}

test "vulkan pipeline cache lookup succeeds" {
    try vulkan_pipeline_cache.pipeline_cache_lookup();
}
