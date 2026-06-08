const execution_types = @import("../core/abi/wgpu_execution_types.zig");

pub const NativeExecutionStatus = execution_types.NativeExecutionStatus;
pub const NativeExecutionResult = execution_types.NativeExecutionResult;

pub const UploadBufferUsageMode = enum {
    copy_dst_copy_src,
    copy_dst,
};

pub const QueueWaitMode = enum {
    process_events,
    wait_any,
};

pub const QueueSyncMode = enum {
    per_command,
    deferred,
};

pub const QueueFamilyPolicy = enum {
    prefer_graphics_compute,
    prefer_compute_only,
    require_compute_only,

    pub fn name(self: QueueFamilyPolicy) []const u8 {
        return switch (self) {
            .prefer_graphics_compute => "prefer_graphics_compute",
            .prefer_compute_only => "prefer_compute_only",
            .require_compute_only => "require_compute_only",
        };
    }
};

pub const QueueFamilyKind = enum {
    graphics_compute,
    compute_only,

    pub fn name(self: QueueFamilyKind) []const u8 {
        return switch (self) {
            .graphics_compute => "graphics_compute",
            .compute_only => "compute_only",
        };
    }
};

pub const DeferredSubmissionSyncPolicy = enum {
    prefer_timeline_semaphore,
    require_fence_pool,

    pub fn name(self: DeferredSubmissionSyncPolicy) []const u8 {
        return switch (self) {
            .prefer_timeline_semaphore => "prefer_timeline_semaphore",
            .require_fence_pool => "require_fence_pool",
        };
    }
};

pub const GpuTimestampMode = enum {
    auto,
    off,
    require,
};
