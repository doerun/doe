const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn run_msl_compile() metal_errors.MetalError!void {
    return try metal_runtime_state.run_msl_compile();
}
