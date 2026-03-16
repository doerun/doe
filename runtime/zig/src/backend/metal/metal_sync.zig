const metal_errors = @import("metal_errors.zig");
const metal_runtime_state = @import("metal_runtime_state.zig");

pub fn wait_for_completion() metal_errors.MetalError!void {
    return try metal_runtime_state.wait_for_completion();
}
