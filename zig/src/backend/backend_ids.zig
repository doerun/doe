const std = @import("std");

pub const BackendId = enum {
    dawn_oracle,
    zig_metal,
};

pub fn backend_id_name(id: BackendId) []const u8 {
    return switch (id) {
        .dawn_oracle => "dawn_oracle",
        .zig_metal => "zig_metal",
    };
}

pub fn backendIdName(id: BackendId) []const u8 {
    return backend_id_name(id);
}

pub fn parse_backend_id(raw: []const u8) ?BackendId {
    if (std.ascii.eqlIgnoreCase(raw, "dawn_oracle")) return .dawn_oracle;
    if (std.ascii.eqlIgnoreCase(raw, "zig_metal")) return .zig_metal;
    return null;
}

pub fn parseBackendId(raw: []const u8) ?BackendId {
    return parse_backend_id(raw);
}
