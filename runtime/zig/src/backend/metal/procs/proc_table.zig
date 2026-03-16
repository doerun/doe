const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn build_proc_table() metal_errors.MetalError!void {
    return try metal_runtime_state.build_proc_table();
}
