const std = @import("std");

pub fn definitions(comptime types: type) type {
    return struct {
        pub const QueueSubmitState = struct {
            done: bool = false,
            status: types.WGPUQueueWorkDoneStatus = .@"error",
            status_message: []const u8 = "",
        };

        pub const BufferMapState = struct {
            done: bool = false,
            status: types.WGPUMapAsyncStatus = 0,
        };

        pub const UncapturedErrorState = struct {
            pending: std.atomic.Value(u32) = std.atomic.Value(u32).init(0),
            error_type: std.atomic.Value(u32) = std.atomic.Value(u32).init(@intFromEnum(types.WGPUErrorType.noError)),
        };

        pub const KernelSource = struct {
            source: []const u8,
            owned: bool,
            mode: KernelLookupResult,
        };

        pub const KernelLookupResult = enum {
            fallback,
            builtin,
            file,
        };

        pub const PipelineCacheEntry = struct {
            shader_module: types.WGPUShaderModule,
            pipeline: types.WGPUComputePipeline,
        };
    };
}
