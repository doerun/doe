const d3d12_errors = @import("d3d12_errors.zig");
const d3d12_runtime_state = @import("d3d12_runtime_state.zig");

pub fn operation_timing_ns() d3d12_errors.D3D12Error!u64 {
    return try d3d12_runtime_state.operation_timing_ns();
}
