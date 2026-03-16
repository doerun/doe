const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn create_texture() metal_errors.MetalError!void {
    return try metal_runtime_state.create_texture();
}

pub fn write_texture() metal_errors.MetalError!void {
    return try metal_runtime_state.write_texture();
}

pub fn query_texture() metal_errors.MetalError!void {
    return try metal_runtime_state.query_texture();
}

pub fn destroy_texture() metal_errors.MetalError!void {
    return try metal_runtime_state.destroy_texture();
}
