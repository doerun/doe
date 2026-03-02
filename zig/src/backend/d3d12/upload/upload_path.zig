const d3d12_errors = @import("../d3d12_errors.zig");
const d3d12_runtime_state = @import("../d3d12_runtime_state.zig");
const staging_ring = @import("staging_ring.zig");

pub const UploadUsageMode = d3d12_runtime_state.UploadUsageMode;

pub fn prewarm_upload_path(max_upload_bytes: u64) d3d12_errors.D3D12Error!void {
    if (max_upload_bytes == 0) return;
    try staging_ring.reserve(max_upload_bytes);
}

pub fn upload_once(mode: UploadUsageMode, bytes: u64) d3d12_errors.D3D12Error!void {
    if (bytes == 0) return d3d12_errors.D3D12Error.InvalidArgument;
    try staging_ring.reserve(bytes);
    return try d3d12_runtime_state.upload_once(mode, bytes);
}
