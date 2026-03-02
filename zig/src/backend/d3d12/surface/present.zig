const d3d12_errors = @import("../d3d12_errors.zig");
const d3d12_runtime_state = @import("../d3d12_runtime_state.zig");

pub fn acquire_surface() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.acquire_surface();
}

pub fn present_surface() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.present_surface();
}

pub fn release_surface() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.release_surface();
}
