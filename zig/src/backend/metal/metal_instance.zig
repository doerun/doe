const metal_errors = @import("metal_errors.zig");

pub fn create_instance() metal_errors.MetalError!void {
    return metal_errors.MetalError.Unsupported;
}
