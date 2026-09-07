const std = @import("std");
const vk_feature_caps = @import("vk_feature_caps.zig");
const vk_device = @import("vk_device.zig");
const NativeVulkanRuntime = @import("native_runtime.zig").NativeVulkanRuntime;

pub fn probe_default_feature_caps(allocator: std.mem.Allocator) !vk_feature_caps.VulkanFeatureCaps {
    var probe = NativeVulkanRuntime{ .allocator = allocator, .kernel_root = null };
    try vk_device.create_instance(&probe);
    defer if (probe.has_instance) {
        vk_device.destroy_instance_only(&probe);
    };
    try vk_device.select_physical_device(&probe);
    return vk_feature_caps.query(probe.physical_device).caps;
}
