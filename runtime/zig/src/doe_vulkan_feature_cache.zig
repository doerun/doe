const std = @import("std");
const vk_feature_caps = @import("backend/vulkan/vk_feature_caps.zig");

var gpa = std.heap.GeneralPurposeAllocator(.{}){};
const alloc = gpa.allocator();

var adapter_caps: std.AutoHashMapUnmanaged(usize, vk_feature_caps.VulkanFeatureCaps) = .{};
var device_caps: std.AutoHashMapUnmanaged(usize, vk_feature_caps.VulkanFeatureCaps) = .{};

fn cache_key(handle: ?*anyopaque) ?usize {
    return if (handle) |ptr| @intFromPtr(ptr) else null;
}

pub fn set_adapter(handle: ?*anyopaque, caps: vk_feature_caps.VulkanFeatureCaps) void {
    const key = cache_key(handle) orelse return;
    adapter_caps.put(alloc, key, caps) catch {};
}

pub fn get_adapter(handle: ?*anyopaque) ?vk_feature_caps.VulkanFeatureCaps {
    const key = cache_key(handle) orelse return null;
    return adapter_caps.get(key);
}

pub fn remove_adapter(handle: ?*anyopaque) void {
    const key = cache_key(handle) orelse return;
    _ = adapter_caps.remove(key);
}

pub fn set_device(handle: ?*anyopaque, caps: vk_feature_caps.VulkanFeatureCaps) void {
    const key = cache_key(handle) orelse return;
    device_caps.put(alloc, key, caps) catch {};
}

pub fn get_device(handle: ?*anyopaque) ?vk_feature_caps.VulkanFeatureCaps {
    const key = cache_key(handle) orelse return null;
    return device_caps.get(key);
}

pub fn remove_device(handle: ?*anyopaque) void {
    const key = cache_key(handle) orelse return;
    _ = device_caps.remove(key);
}
