const std = @import("std");
const model = @import("../model.zig");
const backend_ids = @import("backend_ids.zig");
const backend_iface = @import("backend_iface.zig");
const dawn_oracle_backend = @import("dawn_oracle_backend.zig");
const metal_mod = @import("metal/mod.zig");
const vulkan_mod = @import("vulkan/mod.zig");

pub fn init_backend(
    allocator: std.mem.Allocator,
    backend_id: backend_ids.BackendId,
    profile: model.DeviceProfile,
    kernel_root: ?[]const u8,
    reason: []const u8,
    policy_hash: []const u8,
) !backend_iface.BackendIface {
    return switch (backend_id) {
        .dawn_oracle => blk: {
            const backend = try dawn_oracle_backend.DawnOracleBackend.init(allocator, profile, kernel_root);
            break :blk try backend.as_iface(allocator, reason, policy_hash);
        },
        .zig_metal => blk: {
            const backend = try metal_mod.ZigMetalBackend.init(allocator, profile, kernel_root);
            break :blk try backend.as_iface(allocator, reason, policy_hash);
        },
        .zig_vulkan => blk: {
            const backend = try vulkan_mod.ZigVulkanBackend.init(allocator, profile, kernel_root);
            break :blk try backend.as_iface(allocator, reason, policy_hash);
        },
    };
}
