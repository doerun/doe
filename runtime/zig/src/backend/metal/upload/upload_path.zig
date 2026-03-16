const metal_errors = @import("../metal_errors.zig");
const metal_runtime_state = @import("../metal_runtime_state.zig");

pub const UploadUsageMode = metal_runtime_state.UploadUsageMode;

pub fn upload_once(mode: UploadUsageMode, bytes: u64) metal_errors.MetalError!void {
    return try metal_runtime_state.upload_once(mode, bytes);
}
