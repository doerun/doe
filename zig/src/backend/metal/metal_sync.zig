const metal_errors = @import("metal_errors.zig");

pub fn wait_for_completion() metal_errors.MetalError!void {
    return metal_errors.MetalError.Unsupported;
}
