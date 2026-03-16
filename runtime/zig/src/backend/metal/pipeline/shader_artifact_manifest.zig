const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub fn emit_shader_artifact_manifest() metal_errors.MetalError!void {
    return try metal_runtime_state.emit_shader_artifact_manifest();
}
