const std = @import("std");

pub const BehaviorMode = enum {
    dawn_ownership,
    mixed_ownership,
    zig_metal_ownership,
};

pub fn parse_behavior_mode(raw: []const u8) ?BehaviorMode {
    if (std.ascii.eqlIgnoreCase(raw, "dawn_ownership")) return .dawn_ownership;
    if (std.ascii.eqlIgnoreCase(raw, "mixed_ownership")) return .mixed_ownership;
    if (std.ascii.eqlIgnoreCase(raw, "zig_metal_ownership")) return .zig_metal_ownership;
    return null;
}
