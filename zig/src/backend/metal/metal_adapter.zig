const metal_errors = @import("metal_errors.zig");

pub fn select_adapter() metal_errors.MetalError!void {
    return metal_errors.MetalError.Unsupported;
}
