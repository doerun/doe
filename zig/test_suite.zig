const vulkan_compute_encode_test = @import("tests/vulkan/vulkan_compute_encode_test.zig");
const vulkan_copy_encode_test = @import("tests/vulkan/vulkan_copy_encode_test.zig");
const vulkan_device_queue_test = @import("tests/vulkan/vulkan_device_queue_test.zig");
const vulkan_instance_test = @import("tests/vulkan/vulkan_instance_test.zig");
const vulkan_mod_integration_test = @import("tests/vulkan/vulkan_mod_integration_test.zig");
const vulkan_pipeline_cache_test = @import("tests/vulkan/vulkan_pipeline_cache_test.zig");
const vulkan_render_encode_test = @import("tests/vulkan/vulkan_render_encode_test.zig");
const vulkan_shader_artifact_manifest_test = @import("tests/vulkan/vulkan_shader_artifact_manifest_test.zig");
const vulkan_surface_present_test = @import("tests/vulkan/vulkan_surface_present_test.zig");
const vulkan_sync_semantics_test = @import("tests/vulkan/vulkan_sync_semantics_test.zig");
const vulkan_timing_semantics_test = @import("tests/vulkan/vulkan_timing_semantics_test.zig");
const vulkan_upload_path_test = @import("tests/vulkan/vulkan_upload_path_test.zig");

comptime {
    _ = vulkan_compute_encode_test;
    _ = vulkan_copy_encode_test;
    _ = vulkan_device_queue_test;
    _ = vulkan_instance_test;
    _ = vulkan_mod_integration_test;
    _ = vulkan_pipeline_cache_test;
    _ = vulkan_render_encode_test;
    _ = vulkan_shader_artifact_manifest_test;
    _ = vulkan_surface_present_test;
    _ = vulkan_sync_semantics_test;
    _ = vulkan_timing_semantics_test;
    _ = vulkan_upload_path_test;
}
