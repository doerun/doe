const std = @import("std");

pub const BackendId = enum {
    dawn_delegate,
    doe_metal,
    doe_vulkan,
    doe_d3d12,
};

pub fn backend_id_name(id: BackendId) []const u8 {
    return switch (id) {
        .dawn_delegate => "dawn_delegate",
        .doe_metal => "doe_metal",
        .doe_vulkan => "doe_vulkan",
        .doe_d3d12 => "doe_d3d12",
    };
}

pub fn backendIdName(id: BackendId) []const u8 {
    return backend_id_name(id);
}

pub fn parse_backend_id(raw: []const u8) ?BackendId {
    if (std.ascii.eqlIgnoreCase(raw, "dawn_delegate")) return .dawn_delegate;
    if (std.ascii.eqlIgnoreCase(raw, "doe_metal")) return .doe_metal;
    if (std.ascii.eqlIgnoreCase(raw, "doe_vulkan")) return .doe_vulkan;
    if (std.ascii.eqlIgnoreCase(raw, "doe_d3d12")) return .doe_d3d12;
    return null;
}

pub fn parseBackendId(raw: []const u8) ?BackendId {
    return parse_backend_id(raw);
}
