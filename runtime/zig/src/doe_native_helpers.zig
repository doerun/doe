const std = @import("std");
const builtin = @import("builtin");
const types = @import("doe_native_types.zig");

var gpa = std.heap.GeneralPurposeAllocator(.{}){};

pub const alloc = gpa.allocator();
pub const label_store = @import("doe_label_store.zig");

pub fn make(comptime T: type) ?*T {
    return alloc.create(T) catch null;
}

pub fn cast(comptime T: type, p: ?*anyopaque) ?*T {
    const ptr = p orelse return null;
    const result: *T = @ptrCast(@alignCast(ptr));
    if (result.magic != T.TYPE_MAGIC) return null;
    return result;
}

pub fn object_add_ref(comptime T: type, raw: ?*anyopaque) void {
    const obj = cast(T, raw) orelse return;
    obj.ref_count +|= 1;
}

pub fn object_should_destroy(obj: anytype) bool {
    if (obj.ref_count > 1) {
        obj.ref_count -= 1;
        return false;
    }
    return true;
}

pub fn toOpaque(p: anytype) ?*anyopaque {
    return @ptrCast(p);
}

pub fn device_vk_runtime(dev: *types.DoeDevice) if (builtin.os.tag == .linux) ?*types.NativeVulkanRuntime else ?*void {
    if (comptime builtin.os.tag != .linux) return null;
    const ptr = dev.vk_runtime orelse return null;
    return @as(*types.NativeVulkanRuntime, @ptrCast(@alignCast(ptr)));
}

pub fn device_d3d12_runtime(dev: *types.DoeDevice) ?*types.NativeD3D12Runtime {
    const ptr = dev.d3d12_runtime orelse return null;
    return @as(*types.NativeD3D12Runtime, @ptrCast(@alignCast(ptr)));
}
