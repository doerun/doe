const std = @import("std");
const model = @import("../model.zig");
const backend_ids = @import("backend_ids.zig");
const backend_iface = @import("backend_iface.zig");
const dawn_delegate_backend = @import("dawn_delegate_backend.zig");

fn init_doe_delegate_backend(
    allocator: std.mem.Allocator,
    backend_id: backend_ids.BackendId,
    profile: model.DeviceProfile,
    kernel_root: ?[]const u8,
    reason: []const u8,
    policy_hash: []const u8,
) !backend_iface.BackendIface {
    const backend = try dawn_delegate_backend.DawnDelegateBackend.init(allocator, profile, kernel_root);
    var iface = try backend.as_iface(allocator, reason, policy_hash);
    iface.id = backend_id;
    iface.telemetry.backend_id = backend_id;
    return iface;
}

pub fn init_backend(
    allocator: std.mem.Allocator,
    backend_id: backend_ids.BackendId,
    profile: model.DeviceProfile,
    kernel_root: ?[]const u8,
    reason: []const u8,
    policy_hash: []const u8,
) !backend_iface.BackendIface {
    return switch (backend_id) {
        .dawn_delegate => blk: {
            const backend = try dawn_delegate_backend.DawnDelegateBackend.init(allocator, profile, kernel_root);
            break :blk try backend.as_iface(allocator, reason, policy_hash);
        },
        .doe_metal => try init_doe_delegate_backend(allocator, .doe_metal, profile, kernel_root, reason, policy_hash),
        .doe_vulkan => try init_doe_delegate_backend(allocator, .doe_vulkan, profile, kernel_root, reason, policy_hash),
        .doe_d3d12 => try init_doe_delegate_backend(allocator, .doe_d3d12, profile, kernel_root, reason, policy_hash),
    };
}
