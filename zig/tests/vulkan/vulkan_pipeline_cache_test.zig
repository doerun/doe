const vulkan_pipeline_cache = @import("../../src/backend/vulkan/pipeline/pipeline_cache.zig");
const vulkan_wgsl_ingest = @import("../../src/backend/vulkan/pipeline/wgsl_ingest.zig");
const vulkan_wgsl_to_spirv_runner = @import("../../src/backend/vulkan/pipeline/wgsl_to_spirv_runner.zig");
const vulkan_spirv_opt_runner = @import("../../src/backend/vulkan/pipeline/spirv_opt_runner.zig");

test "vulkan pipeline conversion chain succeeds" {
    try vulkan_wgsl_ingest.ingest();
    try vulkan_wgsl_to_spirv_runner.run();
    try vulkan_spirv_opt_runner.run();
    try vulkan_pipeline_cache.pipeline_cache_lookup();
}
