// doe_wgpu_native.zig — Native wgpu* C ABI implementations backed by Metal, Vulkan, or D3D12.
// Thin export facade over grouped native contracts and shard implementations.
usingnamespace @import("doe_native_api_core_exports.zig");
usingnamespace @import("doe_native_api_render_exports.zig");
usingnamespace @import("doe_native_api_misc_exports.zig");

comptime {
    _ = @import("doe_cache_adapter_native.zig");
    _ = @import("doe_compute_fast.zig");
}

// Instance process events — drain deferred work-done callbacks.
// Chromium expects onSubmittedWorkDone callbacks to fire here, not inline
// during the queueOnSubmittedWorkDone C proc call.
pub export fn doeNativeInstanceProcessEvents(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
    @import("doe_native_api_core_exports.zig").drain_global_work_done();
}
