const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn create_sampler() metal_errors.MetalError!void {
    return try metal_runtime_state.create_sampler();
}

pub fn destroy_sampler() metal_errors.MetalError!void {
    return try metal_runtime_state.destroy_sampler();
}
