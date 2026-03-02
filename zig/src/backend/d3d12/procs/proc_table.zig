const d3d12_errors = @import("../d3d12_errors.zig");
const d3d12_runtime_state = @import("../d3d12_runtime_state.zig");

pub fn build_proc_table() d3d12_errors.D3D12Error!void {
    return try d3d12_runtime_state.build_proc_table();
}
