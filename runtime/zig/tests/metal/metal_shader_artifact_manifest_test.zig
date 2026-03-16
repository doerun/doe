const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_adapter = @import("../../src/backend/metal/metal_adapter.zig");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const manifest = @import("../../src/backend/metal/pipeline/shader_artifact_manifest.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "shader artifact manifest emission succeeds" {
    metal_runtime_state.reset_state();
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    try manifest.emit_shader_artifact_manifest();
    try std.testing.expect(metal_runtime_state.current_manifest_path() != null);
    try std.testing.expect(metal_runtime_state.current_manifest_hash() != null);
    if (metal_runtime_state.current_manifest_path()) |path| {
        try std.testing.expect(path.len > 0);
    }
    if (metal_runtime_state.current_manifest_hash()) |hash| {
        try std.testing.expect(hash.len == 64);
    }
}
