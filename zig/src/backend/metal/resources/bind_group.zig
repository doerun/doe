const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn create_bind_group() metal_errors.MetalError!void {
    return try metal_runtime_state.create_bind_group();
}
