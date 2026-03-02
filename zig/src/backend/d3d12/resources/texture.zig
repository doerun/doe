const d3d12_errors = @import("../d3d12_errors.zig");
const d3d12_runtime_state = @import("../d3d12_runtime_state.zig");

pub fn create_texture() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.create_texture();
}

pub fn write_texture() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.write_texture();
}

pub fn query_texture() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.query_texture();
}

pub fn destroy_texture() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.destroy_texture();
}
