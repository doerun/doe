const vulkan_shader_artifact_manifest = @import("../../src/backend/vulkan/pipeline/shader_artifact_manifest.zig");

test "vulkan shader artifact manifest emits successfully" {
    try vulkan_shader_artifact_manifest.emit();
}
