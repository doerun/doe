const std = @import("std");

pub const BehaviorMode = enum {
    dawn_ownership,
    mixed_ownership,
    doe_metal_ownership,
    doe_vulkan_ownership,
    doe_d3d12_ownership,
};

pub fn parse_behavior_mode(raw: []const u8) ?BehaviorMode {
    if (std.ascii.eqlIgnoreCase(raw, "dawn_ownership")) return .dawn_ownership;
    if (std.ascii.eqlIgnoreCase(raw, "mixed_ownership")) return .mixed_ownership;
    if (std.ascii.eqlIgnoreCase(raw, "doe_metal_ownership")) return .doe_metal_ownership;
    if (std.ascii.eqlIgnoreCase(raw, "doe_vulkan_ownership")) return .doe_vulkan_ownership;
    if (std.ascii.eqlIgnoreCase(raw, "doe_d3d12_ownership")) return .doe_d3d12_ownership;
    return null;
}
