const std = @import("std");
const model = @import("../model.zig");
const backend_ids = @import("backend_ids.zig");
const backend_policy = @import("backend_policy.zig");

pub const Selection = struct {
    backend_id: backend_ids.BackendId,
    reason: []const u8,
    fallback_used: bool,
};

fn is_apple_vendor(vendor: []const u8) bool {
    return std.ascii.eqlIgnoreCase(vendor, "apple");
}

pub fn select_backend(profile: model.DeviceProfile, policy: backend_policy.SelectionPolicy) Selection {
    if (policy.default_backend == .dawn_oracle) {
        return .{
            .backend_id = .dawn_oracle,
            .reason = "policy_lane_prefers_dawn_oracle",
            .fallback_used = false,
        };
    }

    if (policy.default_backend == .zig_metal and profile.api == .metal and is_apple_vendor(profile.vendor)) {
        return .{
            .backend_id = .zig_metal,
            .reason = "apple_chip_prefers_zig_metal",
            .fallback_used = false,
        };
    }

    if (policy.default_backend == .zig_vulkan) {
        return .{
            .backend_id = .zig_vulkan,
            .reason = "policy_lane_prefers_zig_vulkan",
            .fallback_used = false,
        };
    }

    if (profile.api == .metal and policy.default_backend == .zig_metal) {
        return .{
            .backend_id = .zig_metal,
            .reason = "policy_lane_prefers_zig_metal",
            .fallback_used = false,
        };
    }

    if (policy.default_backend == .zig_metal and !policy.allow_fallback) {
        return .{
            .backend_id = .zig_metal,
            .reason = "strict_lane_no_fallback",
            .fallback_used = false,
        };
    }

    return .{
        .backend_id = policy.default_backend,
        .reason = "policy_lane_default",
        .fallback_used = false,
    };
}
