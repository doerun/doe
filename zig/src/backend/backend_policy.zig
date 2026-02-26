const backend_ids = @import("backend_ids.zig");

pub const BackendLane = enum {
    amd_vulkan_release,
    local_metal_directional,
    local_metal_comparable,
    local_metal_release,
    macos_app,
};

pub const SelectionPolicy = struct {
    lane: BackendLane,
    default_backend: backend_ids.BackendId,
    allow_fallback: bool,
    strict_no_fallback: bool,
    policy_hash: []const u8,
};

pub fn default_policy_for_lane(lane: BackendLane) SelectionPolicy {
    return switch (lane) {
        .amd_vulkan_release => .{
            .lane = lane,
            .default_backend = .dawn_oracle,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .local_metal_directional => .{
            .lane = lane,
            .default_backend = .dawn_oracle,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .local_metal_comparable, .local_metal_release, .macos_app => .{
            .lane = lane,
            .default_backend = .zig_metal,
            .allow_fallback = false,
            .strict_no_fallback = true,
            .policy_hash = "backend-runtime-policy-v1",
        },
    };
}
