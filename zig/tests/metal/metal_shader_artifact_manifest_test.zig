const std = @import("std");
const manifest = @import("../../src/backend/metal/pipeline/shader_artifact_manifest.zig");

test "shader artifact manifest emission succeeds" {
    try manifest.emit_shader_artifact_manifest();
}
