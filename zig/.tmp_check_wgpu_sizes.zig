const std = @import("std");
const t = @import("src/wgpu_types.zig");
pub fn main() !void {
    std.debug.print("Zig sizeof WGPUBufferMapCallbackInfo={}\\n", .{@sizeOf(t.WGPUBufferMapCallbackInfo)});
    std.debug.print("Zig offsetof mode={} callback={} userdata1={} userdata2={}\\n", .{@offsetOf(t.WGPUBufferMapCallbackInfo, "mode"), @offsetOf(t.WGPUBufferMapCallbackInfo, "callback"), @offsetOf(t.WGPUBufferMapCallbackInfo, "userdata1"), @offsetOf(t.WGPUBufferMapCallbackInfo, "userdata2")});
    std.debug.print("Zig sizeof WGPUQueueWorkDoneCallbackInfo={}\\n", .{@sizeOf(t.WGPUQueueWorkDoneCallbackInfo)});
    std.debug.print("Zig offsetof q mode={} callback={} userdata1={} userdata2={}\\n", .{@offsetOf(t.WGPUQueueWorkDoneCallbackInfo, "mode"), @offsetOf(t.WGPUQueueWorkDoneCallbackInfo, "callback"), @offsetOf(t.WGPUQueueWorkDoneCallbackInfo, "userdata1"), @offsetOf(t.WGPUQueueWorkDoneCallbackInfo, "userdata2")});
}
