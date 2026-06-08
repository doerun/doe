const builtin = @import("builtin");

const vk_pipeline_cache_persistent = if (builtin.os.tag == .linux) @import("vulkan/vk_pipeline_cache_persistent.zig") else struct {
    pub const WarmupTelemetry = struct {
        count: u64 = 0,
        ns: u64 = 0,
    };
};

pub const WarmupTelemetry = vk_pipeline_cache_persistent.WarmupTelemetry;

pub fn vulkanPipelineCacheActive(runtime: anytype) bool {
    _ = runtime;
    if (comptime builtin.os.tag != .linux) return false;
    return vk_pipeline_cache_persistent.process_active_cache_present();
}

pub fn vulkanPipelineCacheDisabled(runtime: anytype) bool {
    _ = runtime;
    if (comptime builtin.os.tag != .linux) return false;
    return vk_pipeline_cache_persistent.is_process_pipeline_cache_disabled();
}

pub fn vulkanPipelineCacheWarmupTelemetry(runtime: anytype) WarmupTelemetry {
    _ = runtime;
    if (comptime builtin.os.tag != .linux) return .{};
    return vk_pipeline_cache_persistent.process_active_cache_warmup_telemetry();
}

pub fn flushVulkanPipelineCache(runtime: anytype) void {
    if (comptime builtin.os.tag != .linux) return;
    if (runtime.device == null) return;
    vk_pipeline_cache_persistent.flush_process_pipeline_cache(runtime.device);
}
