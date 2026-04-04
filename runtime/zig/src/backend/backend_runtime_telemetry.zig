const builtin = @import("builtin");
const backend_iface = @import("backend_iface.zig");
const vulkan_backend = if (builtin.os.tag == .linux) @import("vulkan/mod.zig") else struct {};
const metal_backend = if (builtin.os.tag == .macos) @import("metal/mod.zig") else struct {};
const d3d12_backend = if (builtin.os.tag == .windows) @import("d3d12/mod.zig") else struct {};

pub fn refresh(backend: *backend_iface.BackendIface) void {
    switch (backend.id) {
        .doe_vulkan => {
            if (comptime builtin.os.tag == .linux) {
                backend.telemetry.shader_artifact_manifest_path = vulkan_backend.manifest_path_from_context(backend.context);
                backend.telemetry.shader_artifact_manifest_hash = vulkan_backend.manifest_hash_from_context(backend.context);
                backend.telemetry.adapter_ordinal = vulkan_backend.adapter_ordinal_from_context(backend.context);
                backend.telemetry.queue_family_index = vulkan_backend.queue_family_index_from_context(backend.context);
                backend.telemetry.present_capable = vulkan_backend.present_capable_from_context(backend.context);
            }
        },
        .doe_metal => {
            if (comptime builtin.os.tag == .macos) {
                backend.telemetry.shader_artifact_manifest_path = metal_backend.manifest_path_from_context(backend.context);
                backend.telemetry.shader_artifact_manifest_hash = metal_backend.manifest_hash_from_context(backend.context);
                backend.telemetry.host_plan_artifact_path = metal_backend.host_plan_path_from_context(backend.context);
                backend.telemetry.host_plan_artifact_hash = metal_backend.host_plan_hash_from_context(backend.context);
            }
        },
        .doe_d3d12 => {
            if (comptime builtin.os.tag == .windows) {
                backend.telemetry.shader_artifact_manifest_path = d3d12_backend.manifest_path_from_context(backend.context);
                backend.telemetry.shader_artifact_manifest_hash = d3d12_backend.manifest_hash_from_context(backend.context);
            }
        },
        else => {},
    }
}
