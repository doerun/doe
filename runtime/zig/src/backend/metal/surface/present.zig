const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn present_surface() metal_errors.MetalError!void {
    return try metal_runtime_state.present_surface();
}

pub fn acquire_surface() metal_errors.MetalError!void {
    return try metal_runtime_state.acquire_surface();
}

pub fn release_surface() metal_errors.MetalError!void {
    return try metal_runtime_state.release_surface();
}
