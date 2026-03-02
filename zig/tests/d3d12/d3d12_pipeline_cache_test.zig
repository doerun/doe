const d3d12_pipeline_cache = @import("../../src/backend/d3d12/pipeline/pipeline_cache.zig");
const d3d12_wgsl_ingest = @import("../../src/backend/d3d12/pipeline/wgsl_ingest.zig");
const d3d12_wgsl_to_spirv_runner = @import("../../src/backend/d3d12/pipeline/wgsl_to_spirv_runner.zig");
const d3d12_spirv_opt_runner = @import("../../src/backend/d3d12/pipeline/spirv_opt_runner.zig");

test "d3d12 pipeline conversion chain succeeds" {
    try d3d12_wgsl_ingest.ingest();
    try d3d12_wgsl_to_spirv_runner.run();
    try d3d12_spirv_opt_runner.run();
    try d3d12_pipeline_cache.pipeline_cache_lookup();
}
