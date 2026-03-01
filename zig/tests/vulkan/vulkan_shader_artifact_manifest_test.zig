const std = @import("std");
const vulkan_shader_artifact_manifest = @import("../../src/backend/vulkan/pipeline/shader_artifact_manifest.zig");
const vulkan_runtime_state = @import("../../src/backend/vulkan/vulkan_runtime_state.zig");

fn manifest_field_value(document: []const u8, comptime field_name: []const u8) ?[]const u8 {
    const prefix = "\"" ++ field_name ++ "\":\"";
    const start_index = std.mem.indexOf(u8, document, prefix) orelse return null;
    const value_start = start_index + prefix.len;
    const value_end_rel = std.mem.indexOfScalar(u8, document[value_start..], '"') orelse return null;
    return document[value_start .. value_start + value_end_rel];
}

test "vulkan shader artifact manifest emits deterministic hash-linked payload" {
    vulkan_runtime_state.reset_state();
    vulkan_runtime_state.set_manifest_module("texture_write");
    try vulkan_shader_artifact_manifest.emit();
    const first_path = vulkan_runtime_state.current_manifest_path() orelse return error.MissingManifestPath;
    const first_manifest = try std.fs.cwd().readFileAlloc(std.testing.allocator, first_path, 4096);
    defer std.testing.allocator.free(first_manifest);

    try std.testing.expect(vulkan_runtime_state.current_manifest_hash() != null);
    try std.testing.expectEqual(@as(u64, 1), vulkan_runtime_state.manifest_emit_count());
    try std.testing.expect(vulkan_runtime_state.current_manifest_module() != null);
    if (vulkan_runtime_state.current_manifest_module()) |module| {
        try std.testing.expectEqualStrings("texture_write", module);
    }
    try std.testing.expect(std.mem.indexOf(u8, first_manifest, "\"backendId\":\"zig_vulkan\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, first_manifest, "\"module\":\"texture_write\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, first_manifest, "\"wgslSha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"") == null);

    const first_hash = manifest_field_value(first_manifest, "hash") orelse return error.MissingHashField;
    try std.testing.expectEqual(@as(usize, 64), first_hash.len);

    try vulkan_shader_artifact_manifest.emit();
    const second_path = vulkan_runtime_state.current_manifest_path() orelse return error.MissingManifestPath;
    const second_manifest = try std.fs.cwd().readFileAlloc(std.testing.allocator, second_path, 4096);
    defer std.testing.allocator.free(second_manifest);

    try std.testing.expectEqual(@as(u64, 2), vulkan_runtime_state.manifest_emit_count());
    const second_previous = manifest_field_value(second_manifest, "previousHash") orelse return error.MissingPreviousHashField;
    try std.testing.expectEqualStrings(first_hash, second_previous);
}
