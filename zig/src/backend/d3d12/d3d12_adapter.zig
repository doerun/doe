const d3d12_errors = @import("d3d12_errors.zig");
const d3d12_runtime_state = @import("d3d12_runtime_state.zig");

pub fn select_adapter() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.select_adapter();
}
