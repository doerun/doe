const metal_errors = @import("metal_errors.zig");
const metal_runtime_state = @import("metal_runtime_state.zig");

pub fn operation_timing_ns() metal_errors.MetalError!u64 {
    return try metal_runtime_state.operation_timing_ns();
}
