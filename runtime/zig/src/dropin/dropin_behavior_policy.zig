const std = @import("std");

pub const BehaviorMode = enum {
    dawn_ownership,
    mixed_ownership,
    doe_metal_ownership,
    doe_vulkan_ownership,
    doe_d3d12_ownership,
};

pub fn parse_behavior_mode(raw: []const u8) ?BehaviorMode {
    inline for (@typeInfo(BehaviorMode).@"enum".fields) |field| {
        if (std.ascii.eqlIgnoreCase(raw, field.name)) return @enumFromInt(field.value);
    }
    return null;
}
