const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn configure_surface() metal_errors.MetalError!void {
    return try metal_runtime_state.configure_surface();
}

pub fn unconfigure_surface() metal_errors.MetalError!void {
    return try metal_runtime_state.unconfigure_surface();
}

pub fn get_surface_capabilities() metal_errors.MetalError!void {
    return try metal_runtime_state.get_surface_capabilities();
}
