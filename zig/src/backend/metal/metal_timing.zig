const metal_errors = @import("metal_errors.zig");

pub fn operation_timing_ns() metal_errors.MetalError!u64 {
    return metal_errors.MetalError.Unsupported;
}
