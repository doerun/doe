const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn pipeline_cache_lookup() metal_errors.MetalError!void {
    return try metal_runtime_state.pipeline_cache_lookup();
}
