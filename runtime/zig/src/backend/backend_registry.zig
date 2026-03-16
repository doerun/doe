const std = @import("std");
const model = @import("../model.zig");
const backend_ids = @import("backend_ids.zig");
const backend_iface = @import("backend_iface.zig");
const backend_policy = @import("backend_policy.zig");
const dawn_delegate_backend = @import("dawn_delegate_backend.zig");
const metal_backend = @import("metal/mod.zig");
const vulkan_backend = @import("vulkan/mod.zig");
const d3d12_backend = @import("d3d12/mod.zig");

pub fn init_backend(
    allocator: std.mem.Allocator,
    policy: backend_policy.SelectionPolicy,
    backend_id: backend_ids.BackendId,
    profile: model.DeviceProfile,
    kernel_root: ?[]const u8,
    reason: []const u8,
) !backend_iface.BackendIface {
    return switch (backend_id) {
        .dawn_delegate => blk: {
            const backend = try dawn_delegate_backend.DawnDelegateBackend.init(allocator, profile, kernel_root);
            break :blk try backend.as_iface(allocator, reason, policy.policy_hash);
        },
        .doe_metal => blk: {
            const backend = try metal_backend.ZigMetalBackend.init(allocator, profile, kernel_root);
            break :blk try backend.as_iface(allocator, reason, policy.policy_hash);
        },
        .doe_vulkan => blk: {
            const backend = try vulkan_backend.ZigVulkanBackend.init_with_selection_policy(allocator, profile, kernel_root, policy);
            break :blk try backend.as_iface(allocator, reason, policy.policy_hash);
        },
        .doe_d3d12 => blk: {
            const backend = try d3d12_backend.ZigD3D12Backend.init(allocator, profile, kernel_root);
            break :blk try backend.as_iface(allocator, reason, policy.policy_hash);
        },
    };
}
