const builtin = @import("builtin");
const native_shared = @import("../support/doe_native_shared_types.zig");

const has_vulkan = (builtin.os.tag == .linux);

pub fn flushBeforeDestroy(rt_raw: ?*anyopaque) void {
    if (comptime !has_vulkan) return;
    const raw = rt_raw orelse return;
    const rt: *native_shared.NativeVulkanRuntime = @ptrCast(@alignCast(raw));
    rt.waitForDestruction();
}
