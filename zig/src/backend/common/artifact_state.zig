const std = @import("std");
const artifact_meta = @import("artifact_meta.zig");

pub fn persist_value(storage: []u8, len: *usize, value: []const u8) void {
    if (value.len > storage.len) {
        len.* = 0;
        return;
    }
    std.mem.copyForwards(u8, storage[0..value.len], value);
    len.* = value.len;
}

pub fn manifest_signature_matches(
    last_meta: ?artifact_meta.ArtifactMeta,
    last_module: []const u8,
    last_status_code: []const u8,
    module: []const u8,
    meta: artifact_meta.ArtifactMeta,
    status_code: []const u8,
) bool {
    const persisted_meta = last_meta orelse return false;
    if (persisted_meta.backend_kind != meta.backend_kind or
        persisted_meta.timing_source != meta.timing_source or
        persisted_meta.comparability != meta.comparability)
    {
        return false;
    }
    if (!std.mem.eql(u8, last_module, module)) return false;
    if (!std.mem.eql(u8, last_status_code, status_code)) return false;
    return true;
}

pub fn persist_manifest_signature(
    last_meta: *?artifact_meta.ArtifactMeta,
    module_storage: []u8,
    module_len: *usize,
    status_storage: []u8,
    status_len: *usize,
    module: []const u8,
    meta: artifact_meta.ArtifactMeta,
    status_code: []const u8,
) void {
    last_meta.* = meta;
    persist_value(module_storage, module_len, module);
    persist_value(status_storage, status_len, status_code);
}
