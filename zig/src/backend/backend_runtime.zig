const std = @import("std");
const model = @import("../model.zig");
const webgpu = @import("../webgpu_ffi.zig");
const backend_iface = @import("backend_iface.zig");
const backend_policy = @import("backend_policy.zig");
const backend_registry = @import("backend_registry.zig");
const backend_selection = @import("backend_selection.zig");
const backend_telemetry = @import("backend_telemetry.zig");
const vulkan_backend = @import("vulkan/mod.zig");
const metal_backend = @import("metal/mod.zig");
const d3d12_backend = @import("d3d12/mod.zig");

pub const BackendRuntime = struct {
    allocator: std.mem.Allocator,
    backend: backend_iface.BackendIface,
    owned_policy_hash: ?[]u8 = null,

    pub fn init(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        lane: backend_policy.BackendLane,
    ) !BackendRuntime {
        return try init_with_policy_path(
            allocator,
            profile,
            kernel_root,
            lane,
            backend_policy.DEFAULT_RUNTIME_POLICY_PATH,
        );
    }

    pub fn init_with_policy_path(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        lane: backend_policy.BackendLane,
        policy_path: []const u8,
    ) !BackendRuntime {
        const loaded_policy = try backend_policy.load_policy_for_lane(
            allocator,
            policy_path,
            lane,
        );
        errdefer allocator.free(loaded_policy.owned_policy_hash);
        const policy = loaded_policy.policy;
        const selected = backend_selection.select_backend(profile, policy);
        var backend = try backend_registry.init_backend(
            allocator,
            selected.backend_id,
            profile,
            kernel_root,
            selected.reason,
            policy.policy_hash,
        );
        backend.telemetry.fallback_used = selected.fallback_used;
        return .{
            .allocator = allocator,
            .backend = backend,
            .owned_policy_hash = loaded_policy.owned_policy_hash,
        };
    }

    pub fn deinit(self: *BackendRuntime) void {
        self.backend.deinit();
        if (self.owned_policy_hash) |value| {
            self.allocator.free(value);
            self.owned_policy_hash = null;
        }
    }

    fn refreshBackendTelemetry(self: *BackendRuntime) void {
        switch (self.backend.id) {
            .doe_vulkan => {
                self.backend.telemetry.shader_artifact_manifest_path = vulkan_backend.manifest_path_from_context(self.backend.context);
                self.backend.telemetry.shader_artifact_manifest_hash = vulkan_backend.manifest_hash_from_context(self.backend.context);
                self.backend.telemetry.adapter_ordinal = vulkan_backend.adapter_ordinal_from_context(self.backend.context);
                self.backend.telemetry.queue_family_index = vulkan_backend.queue_family_index_from_context(self.backend.context);
                self.backend.telemetry.present_capable = vulkan_backend.present_capable_from_context(self.backend.context);
            },
            .doe_metal => {
                self.backend.telemetry.shader_artifact_manifest_path = metal_backend.manifest_path_from_context(self.backend.context);
                self.backend.telemetry.shader_artifact_manifest_hash = metal_backend.manifest_hash_from_context(self.backend.context);
            },
            .doe_d3d12 => {
                self.backend.telemetry.shader_artifact_manifest_path = d3d12_backend.manifest_path_from_context(self.backend.context);
                self.backend.telemetry.shader_artifact_manifest_hash = d3d12_backend.manifest_hash_from_context(self.backend.context);
            },
            else => {},
        }
    }

    pub fn execute_command(self: *BackendRuntime, command: model.Command) !webgpu.NativeExecutionResult {
        return try self.backend.execute_command(command);
    }

    pub fn set_upload_behavior(self: *BackendRuntime, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
        self.backend.set_upload_behavior(mode, submit_every);
    }

    pub fn set_queue_wait_mode(self: *BackendRuntime, mode: webgpu.QueueWaitMode) void {
        self.backend.set_queue_wait_mode(mode);
    }

    pub fn set_queue_sync_mode(self: *BackendRuntime, mode: webgpu.QueueSyncMode) void {
        self.backend.set_queue_sync_mode(mode);
    }

    pub fn set_gpu_timestamp_mode(self: *BackendRuntime, mode: webgpu.GpuTimestampMode) void {
        self.backend.set_gpu_timestamp_mode(mode);
    }

    pub fn flush_queue(self: *BackendRuntime) !u64 {
        return try self.backend.flush_queue();
    }

    pub fn prewarm_upload_path(self: *BackendRuntime, max_upload_bytes: u64) !void {
        try self.backend.prewarm_upload_path(max_upload_bytes);
    }

    pub fn prewarm_kernel_dispatch(self: *BackendRuntime, kernel: []const u8, bindings: ?[]const model.KernelBinding) !void {
        try self.backend.prewarm_kernel_dispatch(kernel, bindings);
    }

    pub fn telemetry(self: *BackendRuntime) backend_telemetry.BackendTelemetry {
        self.refreshBackendTelemetry();
        return self.backend.telemetry;
    }
};
