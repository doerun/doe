const d3d12_errors = @import("../d3d12_errors.zig");
const d3d12_runtime_state = @import("../d3d12_runtime_state.zig");

pub fn configure_surface() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.configure_surface();
}

pub fn unconfigure_surface() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.unconfigure_surface();
}

pub fn get_surface_capabilities() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.get_surface_capabilities();
}
