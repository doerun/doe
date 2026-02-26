const std = @import("std");
const manifest = @import("../../src/backend/metal/pipeline/shader_artifact_manifest.zig");

test "shader artifact manifest reports unsupported until implemented" {
    try std.testing.expectError(error.Unsupported, manifest.emit_shader_artifact_manifest());
}
