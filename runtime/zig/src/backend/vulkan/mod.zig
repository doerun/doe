const std = @import("std");
const builtin = @import("builtin");
const model_commands = @import("../../contracts/command.zig");
const model_profile = @import("../../contracts/model/model_profile.zig");
const model_resource_types = @import("../../contracts/model/model_resource_types.zig");
const model_compute_types = @import("../../contracts/model/model_compute_types.zig");
const compute_contract = @import("../../contracts/compute.zig");
const prepared = @import("../../contracts/prepared_operation.zig");
const model_render_types = @import("../../contracts/model/model_render_types.zig");
const model_async_types = @import("../../contracts/model/model_async_types.zig");
const webgpu = @import("../../contracts/runtime_types.zig");
const runtime_configuration = @import("../../contracts/runtime_configuration.zig");
const runtime_telemetry = @import("../../contracts/runtime_telemetry.zig");
const backend_telemetry = @import("../backend_telemetry.zig");
const port_factory = @import("../ports/factory.zig");
const provider_adapter = @import("../ports/provider_adapter.zig");
const backend_policy = @import("../backend_policy.zig");
const common_errors = @import("../../contracts/execution.zig");
const command_info = @import("../../contracts/command.zig");
const capabilities = @import("../../contracts/capability.zig");
const HASH_HEX_SIZE = @import("../../contracts/artifact.zig").SHA256_HEX_SIZE;
const MAX_SHADER_SOURCE_BYTES: usize = 16 * 1024 * 1024;
const hash_utils = @import("../../contracts/artifact.zig");
const artifact_meta = @import("../../contracts/artifact.zig");
const artifact_policy = @import("../common/artifact_policy.zig");
const artifact_state = @import("../common/artifact_state.zig");
const artifact_emit = @import("artifact_emit.zig");
const backend_execute = @import("backend_execute.zig");
const native_runtime = @import("native_runtime.zig");
const vk_pipeline = @import("vk_pipeline.zig");
const shared_pipeline = @import("vk_shared_pipeline.zig");
const vk_pipeline_cache_persistent = @import("vk_pipeline_cache_persistent.zig");

const STATUS_MESSAGE_BYTES: usize = 256;

const model = struct {
    pub const AsyncDiagnosticsCommand = model_async_types.AsyncDiagnosticsCommand;
    pub const BufferWriteCommand = model_resource_types.BufferWriteCommand;
    pub const Command = model_commands.Command;
    pub const DeviceProfile = model_profile.DeviceProfile;
    pub const KernelBinding = model_compute_types.KernelBinding;
    pub const KernelDispatchCommand = model_compute_types.KernelDispatchCommand;
    pub const RenderDrawCommand = model_render_types.RenderDrawCommand;
    pub const UploadCommand = model_resource_types.UploadCommand;
};

// Uploads accumulate and flush lazily: flush_pending_uploads_if_required fires
// once before the first non-upload command that needs to see the written data.
// This matches Dawn's batched-upload behavior and eliminates per-upload fence overhead.
const UPLOAD_BATCH_LAZY: u32 = std.math.maxInt(u32);

pub const ZigVulkanBackend = struct {
    allocator: std.mem.Allocator,
    kernel_root_owned: ?[]u8 = null,
    pipeline_cache_dir_owned: ?[]u8 = null,
    pipeline_cache_enabled: bool = true,
    runtime: ?native_runtime.NativeVulkanRuntime = null,

    upload_path_policy: backend_policy.UploadPathPolicy = .allow_mapped_shortcuts,
    upload_buffer_usage_mode: webgpu.UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = UPLOAD_BATCH_LAZY,
    queue_family_policy: webgpu.QueueFamilyPolicy = .prefer_graphics_compute,
    deferred_submission_sync_policy: webgpu.DeferredSubmissionSyncPolicy = .prefer_timeline_semaphore,
    vulkan_subgroup_size_policy: backend_policy.VulkanSubgroupSizePolicy = .fixed_32_when_supported,
    queue_wait_mode: webgpu.QueueWaitMode = .process_events,
    queue_sync_mode: webgpu.QueueSyncMode = .per_command,
    gpu_timestamp_mode: webgpu.GpuTimestampMode = .auto,
    pending_upload_commands: u32 = 0,
    telemetry: runtime_telemetry.RuntimeTelemetry = backend_telemetry.default_telemetry(),

    capability_set: capabilities.CapabilitySet,

    status_message_storage: [STATUS_MESSAGE_BYTES]u8 = [_]u8{0} ** STATUS_MESSAGE_BYTES,

    artifacts: artifact_state.State,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*ZigVulkanBackend {
        return init_with_upload_path_policy(allocator, profile, kernel_root, .allow_mapped_shortcuts);
    }

    pub fn init_with_selection_policy(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        selection_policy: backend_policy.SelectionPolicy,
    ) !*ZigVulkanBackend {
        return init_with_selection_policy_and_cache_configuration(
            allocator,
            profile,
            kernel_root,
            .{},
            selection_policy,
        );
    }

    pub fn init_with_selection_policy_and_cache_configuration(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        pipeline_cache: runtime_configuration.PipelineCacheConfiguration,
        selection_policy: backend_policy.SelectionPolicy,
    ) !*ZigVulkanBackend {
        return init_with_backend_policy(
            allocator,
            profile,
            kernel_root,
            pipeline_cache,
            selection_policy.upload_path_policy,
            selection_policy.queue_family_policy,
            selection_policy.deferred_submission_sync_policy,
            selection_policy.vulkan_subgroup_size_policy,
        );
    }

    fn init_with_upload_path_policy(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !*ZigVulkanBackend {
        return init_with_backend_policy(allocator, profile, kernel_root, .{}, upload_path_policy, .prefer_graphics_compute, .prefer_timeline_semaphore, .fixed_32_when_supported);
    }

    fn init_with_backend_policy(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        pipeline_cache: runtime_configuration.PipelineCacheConfiguration,
        upload_path_policy: backend_policy.UploadPathPolicy,
        queue_family_policy: webgpu.QueueFamilyPolicy,
        deferred_submission_sync_policy: webgpu.DeferredSubmissionSyncPolicy,
        vulkan_subgroup_size_policy: backend_policy.VulkanSubgroupSizePolicy,
    ) !*ZigVulkanBackend {
        if (profile.api != .vulkan) return error.UnsupportedFeature;

        const owned_kernel_root = if (kernel_root) |root| try allocator.dupe(u8, root) else null;
        errdefer if (owned_kernel_root) |root| allocator.free(root);
        const owned_pipeline_cache_dir = if (pipeline_cache.directory.len > 0)
            try allocator.dupe(u8, pipeline_cache.directory)
        else
            null;
        errdefer if (owned_pipeline_cache_dir) |directory| allocator.free(directory);

        const ptr = try allocator.create(ZigVulkanBackend);
        errdefer allocator.destroy(ptr);

        ptr.* = .{
            .allocator = allocator,
            .kernel_root_owned = owned_kernel_root,
            .pipeline_cache_dir_owned = owned_pipeline_cache_dir,
            .pipeline_cache_enabled = pipeline_cache.enabled,
            .runtime = null,
            .upload_path_policy = upload_path_policy,
            .upload_buffer_usage_mode = .copy_dst_copy_src,
            .upload_submit_every = UPLOAD_BATCH_LAZY,
            .queue_family_policy = queue_family_policy,
            .deferred_submission_sync_policy = deferred_submission_sync_policy,
            .vulkan_subgroup_size_policy = vulkan_subgroup_size_policy,
            .queue_wait_mode = .process_events,
            .queue_sync_mode = .per_command,
            .gpu_timestamp_mode = .auto,
            .pending_upload_commands = 0,
            .telemetry = backend_telemetry.default_telemetry(),
            .capability_set = native_capability_set(),
            .status_message_storage = [_]u8{0} ** STATUS_MESSAGE_BYTES,
            .artifacts = .{ .allocator = allocator },
        };

        return ptr;
    }

    pub fn asPorts(self: *ZigVulkanBackend, reason: []const u8, policy_hash: []const u8, fallback_used: bool) port_factory.PortBundle {
        self.telemetry = backend_telemetry.forSelection(.doe_vulkan, reason, fallback_used, policy_hash);
        return provider_adapter.fromDriver(PortDriver, self, .doe_vulkan);
    }

    pub fn write_status(self: *ZigVulkanBackend, comptime fmt: []const u8, args: anytype) []const u8 {
        return artifact_policy.formatStatus(&self.status_message_storage, fmt, args);
    }

    pub fn ensure_runtime_bootstrapped(self: *ZigVulkanBackend) !*native_runtime.NativeVulkanRuntime {
        if (self.runtime == null) {
            self.runtime = try native_runtime.NativeVulkanRuntime.init_with_backend_policy_and_cache(
                self.allocator,
                self.kernel_root_owned,
                .{
                    .enabled = self.pipeline_cache_enabled,
                    .directory = self.pipeline_cache_dir_owned orelse "",
                },
                self.queue_family_policy,
                self.deferred_submission_sync_policy,
                self.vulkan_subgroup_size_policy,
            );
        }
        return &self.runtime.?;
    }

    fn beginCommand(self: *ZigVulkanBackend) void {
        if (self.runtime) |*runtime| {
            vk_pipeline.discardPendingSpirv(runtime);
            runtime.last_submit_count = null;
        }
    }

    pub fn takePendingSpirv(self: *ZigVulkanBackend) ?*shared_pipeline.Pipeline {
        if (self.runtime) |*runtime| {
            const owner = runtime.pending_spirv_pipeline;
            runtime.pending_spirv_pipeline = null;
            return owner;
        }
        return null;
    }

    pub fn shader_source_hash_for_module(self: *ZigVulkanBackend, module: []const u8) ?[HASH_HEX_SIZE]u8 {
        if (self.hash_shader_source_file(module)) |hash| return hash;
        const root = self.kernel_root_owned orelse "bench/kernels";
        const path = std.fs.path.join(self.allocator, &.{ root, module }) catch return null;
        defer self.allocator.free(path);
        if (self.hash_shader_source_file(path)) |hash| return hash;
        if (std.mem.endsWith(u8, module, ".wgsl")) return null;
        const wgsl_module = std.fmt.allocPrint(self.allocator, "{s}.wgsl", .{module}) catch return null;
        defer self.allocator.free(wgsl_module);
        const wgsl_path = std.fs.path.join(self.allocator, &.{ root, wgsl_module }) catch return null;
        defer self.allocator.free(wgsl_path);
        return self.hash_shader_source_file(wgsl_path);
    }

    fn hash_shader_source_file(self: *ZigVulkanBackend, path: []const u8) ?[HASH_HEX_SIZE]u8 {
        const bytes = std.fs.cwd().readFileAlloc(self.allocator, path, MAX_SHADER_SOURCE_BYTES) catch return null;
        defer self.allocator.free(bytes);
        return hash_utils.sha256_hex(bytes);
    }

    pub fn annotate_result(self: *ZigVulkanBackend, command: model.Command, result: webgpu.NativeExecutionResult) webgpu.NativeExecutionResult {
        var out = result;
        const meta = artifact_meta.classify(
            .native_vulkan,
            out.gpu_timestamp_valid,
            out.gpu_timestamp_attempted,
        );
        if (out.status == .ok or out.status_message.len == 0) {
            out.status_message = self.write_status(
                "{s} timing={s} comparability={s}",
                .{ command_info.manifest_module(command), meta.timing_source.name(), meta.comparability.name() },
            );
        }

        if (out.status == .ok and artifact_policy.should_emit_shader_artifact(command)) {
            const status_code = artifact_policy.artifact_status_code(out);
            const owner = self.takePendingSpirv();
            defer if (owner) |pipeline| {
                const runtime = &self.runtime.?;
                runtime.shared_pipelines.release(runtime.allocator, runtime.device, pipeline);
            };
            const spirv = if (owner) |pipeline| std.mem.sliceAsBytes(pipeline.words) else null;
            self.artifacts.capture(command_info.shader_artifact_module(command), meta, status_code, spirv, self.shader_source_hash_for_module(command_info.shader_artifact_module(command))) catch |err| {
                out.status = .@"error";
                out.status_message = @errorName(err);
            };
        }

        return out;
    }
};

fn native_capability_set() capabilities.CapabilitySet {
    var set = capabilities.CapabilitySet{};
    set.declare_all(&.{
        .kernel_dispatch,
        .compute_dispatch,
        .compute_dispatch_indirect,
        .buffer_upload,
        .buffer_write,
        .buffer_copy,
        .barrier_sync,
        .sampler_lifecycle,
        .render_draw,
        .render_pass,
        .texture_write,
        .texture_query,
        .texture_destroy,
        .surface_lifecycle,
        .surface_present,
        .async_pipeline_diagnostics,
        .async_capability_introspection,
        .async_resource_table_immediates,
        .async_lifecycle_refcount,
        .async_pixel_local_storage,
        .gpu_timestamps,
        .render_bundle,
        .indirect_draw,
        .indexed_indirect_draw,
        .depth_stencil,
        .descriptor_binding,
    });
    return set;
}

fn cast(ctx: *anyopaque) *ZigVulkanBackend {
    return @as(*ZigVulkanBackend, @ptrCast(@alignCast(ctx)));
}

pub fn manifest_path_from_context(ctx: *anyopaque) ?[]const u8 {
    const self = cast(ctx);
    return self.artifacts.path();
}

pub fn manifest_hash_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).artifacts.hash();
}

pub fn adapter_ordinal_from_context(ctx: *anyopaque) ?u32 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.adapter_ordinal_value;
    }
    return null;
}

pub fn queue_family_index_from_context(ctx: *anyopaque) ?u32 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.queue_family_index_value_cache;
    }
    return null;
}

pub fn present_capable_from_context(ctx: *anyopaque) ?bool {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.present_capable_value;
    }
    return null;
}

pub fn queue_family_policy_from_context(ctx: *anyopaque) ?[]const u8 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.queue_family_policy.name();
    }
    return self.queue_family_policy.name();
}

pub fn queue_family_kind_from_context(ctx: *anyopaque) ?[]const u8 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        const kind = runtime.queue_family_kind_value_cache orelse return null;
        return kind.name();
    }
    return null;
}

pub fn queue_family_queue_count_from_context(ctx: *anyopaque) ?u32 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.queue_family_queue_count_value_cache;
    }
    return null;
}

pub fn queue_family_timestamp_valid_bits_from_context(ctx: *anyopaque) ?u32 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.queue_family_timestamp_valid_bits_value_cache;
    }
    return null;
}

pub fn queue_family_supports_graphics_from_context(ctx: *anyopaque) ?bool {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.queue_family_supports_graphics_value_cache;
    }
    return null;
}

pub fn pipeline_cache_active_from_context(ctx: *anyopaque) bool {
    const self = cast(ctx);
    if (self.runtime) |*runtime| return runtime.pipeline_cache.active();
    return false;
}

pub fn pipeline_cache_warmup_telemetry_from_context(ctx: *anyopaque) vk_pipeline_cache_persistent.WarmupTelemetry {
    const self = cast(ctx);
    if (self.runtime) |*runtime| return runtime.pipeline_cache.warmupTelemetry();
    return .{};
}

pub fn last_submit_count_from_context(ctx: *anyopaque) ?u32 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.last_submit_count;
    }
    return null;
}

fn deinit(ctx: *anyopaque) void {
    const self = cast(ctx);
    self.artifacts.deinit();
    const allocator = self.allocator;
    if (self.runtime) |*runtime| {
        runtime.deinit();
        self.runtime = null;
    }

    if (self.kernel_root_owned) |kernel_root| {
        allocator.free(kernel_root);
        self.kernel_root_owned = null;
    }
    if (self.pipeline_cache_dir_owned) |directory| {
        allocator.free(directory);
        self.pipeline_cache_dir_owned = null;
    }

    allocator.destroy(self);
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    self.beginCommand();
    return backend_execute.execute_command(self, command);
}

fn execute_prepared_compute(ctx: *anyopaque, operation: prepared.PreparedComputeOperation) anyerror!webgpu.NativeExecutionResult {
    return execute_command(ctx, operation.toCommand());
}

fn execute_prepared_transfer(ctx: *anyopaque, operation: prepared.PreparedTransferOperation) anyerror!webgpu.NativeExecutionResult {
    return execute_command(ctx, operation.operation.toCommand().?);
}

fn execute_prepared_render(ctx: *anyopaque, operation: prepared.PreparedRenderOperation) anyerror!webgpu.NativeExecutionResult {
    return execute_command(ctx, operation.operation.toCommand());
}

fn execute_prepared_resource(ctx: *anyopaque, operation: prepared.PreparedResourceOperation) anyerror!webgpu.NativeExecutionResult {
    return execute_command(ctx, operation.operation.toCommand());
}

fn execute_prepared_surface(ctx: *anyopaque, operation: prepared.PreparedSurfaceOperation) anyerror!webgpu.NativeExecutionResult {
    return execute_command(ctx, operation.operation.toCommand());
}

fn execute_prepared_lifecycle(ctx: *anyopaque, operation: prepared.PreparedLifecycleOperation) anyerror!webgpu.NativeExecutionResult {
    return execute_command(ctx, operation.toCommand());
}

fn execute_dispatch(context: compute_contract.ComputeContext, request: compute_contract.DispatchRequest) anyerror!compute_contract.DispatchReport {
    const self = cast(context.state);
    self.beginCommand();
    const result = try backend_execute.execute_dispatch(ZigVulkanBackend, self, request);
    return .{ .execution = result };
}

fn execute_buffer_write_bytes_iface(ctx: *anyopaque, handle: u64, offset: u64, buffer_size: u64, data: []const u8) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    self.beginCommand();
    return backend_execute.execute_buffer_write_bytes_iface(self, handle, offset, buffer_size, data);
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    backend_execute.set_upload_behavior(cast(ctx), mode, submit_every);
}

fn set_queue_wait_mode(ctx: *anyopaque, mode: webgpu.QueueWaitMode) void {
    backend_execute.set_queue_wait_mode(cast(ctx), mode);
}

fn set_webgpu_ffi_queue_wait_timeout_ns(ctx: *anyopaque, timeout_ns: u64) void {
    _ = ctx;
    _ = timeout_ns;
}

fn set_queue_sync_mode(ctx: *anyopaque, mode: webgpu.QueueSyncMode) void {
    backend_execute.set_queue_sync_mode(cast(ctx), mode);
}

fn set_gpu_timestamp_mode(ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void {
    backend_execute.set_gpu_timestamp_mode(cast(ctx), mode);
}

fn flush_queue(ctx: *anyopaque) anyerror!u64 {
    return backend_execute.flush_queue(cast(ctx));
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    return backend_execute.prewarm_upload_path(cast(ctx), max_upload_bytes);
}

fn prewarm_kernel_dispatch(
    ctx: *anyopaque,
    kernel: []const u8,
    entry_point: ?[]const u8,
    bindings: ?[]const model.KernelBinding,
    initialize_buffers_on_create: bool,
) anyerror!void {
    return backend_execute.prewarm_kernel_dispatch(
        cast(ctx),
        kernel,
        entry_point,
        bindings,
        initialize_buffers_on_create,
    );
}

fn capture_buffer(ctx: *anyopaque, allocator: std.mem.Allocator, handle: u64, offset: u64, size: u64) anyerror![]u8 {
    return backend_execute.capture_buffer(cast(ctx), allocator, handle, offset, size);
}

fn telemetry_snapshot(ctx: *anyopaque) runtime_telemetry.RuntimeTelemetry {
    const self = cast(ctx);
    self.telemetry.shader_artifact_manifest_path = manifest_path_from_context(ctx);
    self.telemetry.shader_artifact_manifest_hash = manifest_hash_from_context(ctx);
    self.telemetry.adapter_ordinal = adapter_ordinal_from_context(ctx);
    self.telemetry.queue_family_index = queue_family_index_from_context(ctx);
    self.telemetry.present_capable = present_capable_from_context(ctx);
    self.telemetry.queue_family_policy = queue_family_policy_from_context(ctx);
    self.telemetry.queue_family_kind = queue_family_kind_from_context(ctx);
    self.telemetry.queue_family_queue_count = queue_family_queue_count_from_context(ctx);
    self.telemetry.queue_family_timestamp_valid_bits = queue_family_timestamp_valid_bits_from_context(ctx);
    self.telemetry.queue_family_supports_graphics = queue_family_supports_graphics_from_context(ctx);
    const cache = pipeline_cache_warmup_telemetry_from_context(ctx);
    self.telemetry.pipeline_cache_warmup_count = cache.count;
    self.telemetry.pipeline_cache_warmup_ns = cache.ns;
    self.telemetry.pipeline_cache_active = pipeline_cache_active_from_context(ctx);
    self.telemetry.last_submit_count = last_submit_count_from_context(ctx);
    return self.telemetry;
}

fn backend_id(ctx: *anyopaque) @import("../../contracts/backend.zig").BackendId {
    _ = ctx;
    return .doe_vulkan;
}

pub fn destroyContext(ctx: *anyopaque) void {
    deinit(ctx);
}

fn collect_artifacts(ctx: *anyopaque) !void {
    try artifact_emit.flushPending(&cast(ctx).artifacts);
}

const PortDriver = struct {
    pub const collectArtifacts = collect_artifacts;
    pub const backendId = backend_id;
    pub const executePreparedCompute = execute_prepared_compute;
    pub const executePreparedTransfer = execute_prepared_transfer;
    pub const executePreparedRender = execute_prepared_render;
    pub const executePreparedResource = execute_prepared_resource;
    pub const executePreparedSurface = execute_prepared_surface;
    pub const executePreparedLifecycle = execute_prepared_lifecycle;
    pub const executeDispatch = execute_dispatch;
    pub const executeBufferWrite = execute_buffer_write_bytes_iface;
    pub const setUploadBehavior = set_upload_behavior;
    pub const setQueueWaitMode = set_queue_wait_mode;
    pub const setQueueWaitTimeoutNs = set_webgpu_ffi_queue_wait_timeout_ns;
    pub const setQueueSyncMode = set_queue_sync_mode;
    pub const setGpuTimestampMode = set_gpu_timestamp_mode;
    pub const flush = flush_queue;
    pub const prewarmUpload = prewarm_upload_path;
    pub const prewarmKernel = prewarm_kernel_dispatch;
    pub const capture = capture_buffer;
    pub const telemetrySnapshot = telemetry_snapshot;
};

test "extensionless artifact module resolves the executed WGSL source" {
    var backend: ZigVulkanBackend = undefined;
    backend.allocator = std.testing.allocator;
    backend.kernel_root_owned = try std.testing.allocator.dupe(u8, "../../bench/kernels");
    defer std.testing.allocator.free(backend.kernel_root_owned.?);

    const extensionless_hash = backend.shader_source_hash_for_module("concurrent_execution_runsingle_u32");
    const explicit_hash = backend.shader_source_hash_for_module("concurrent_execution_runsingle_u32.wgsl");
    try std.testing.expect(extensionless_hash != null);
    try std.testing.expectEqual(explicit_hash, extensionless_hash);
}

test "Vulkan telemetry snapshots never collect pending artifacts" {
    const backend = try ZigVulkanBackend.init(std.testing.allocator, .{
        .vendor = "amd",
        .api = .vulkan,
        .driver_version = .{ .major = 0, .minor = 0, .patch = 0 },
    }, null);
    defer destroyContext(backend);
    var temp = std.testing.tmpDir(.{});
    defer temp.cleanup();
    const root = try temp.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    const missing = try std.fs.path.join(std.testing.allocator, &.{ root, "missing-toolchain.json" });
    defer std.testing.allocator.free(missing);
    backend.artifacts.output = .{ .directory = root, .toolchain_path = missing };
    try backend.artifacts.capture("module", artifact_meta.classify(.native_vulkan, false, false), "ok", null, null);
    const ports = backend.asPorts("test", "test", false);
    try std.testing.expect(ports.telemetry.snapshot().shader_artifact_manifest_path == null);
    try std.testing.expect(ports.telemetry.snapshot().shader_artifact_manifest_hash == null);
    try std.testing.expectEqual(@as(u64, 0), backend.artifacts.manifest_emit_count);
    try std.testing.expectError(error.FileNotFound, ports.telemetry.collectArtifacts());
    try std.testing.expect(backend.artifacts.pending != null);
}

test "new command discards prewarm or failed-command artifact staging" {
    const backend = try ZigVulkanBackend.init(std.testing.allocator, .{
        .vendor = "amd",
        .api = .vulkan,
        .driver_version = .{ .major = 0, .minor = 0, .patch = 0 },
    }, null);
    defer destroyContext(backend);
    backend.capability_set = .{};
    // Capability rejection must not access native device fields.
    backend.runtime = @as(native_runtime.NativeVulkanRuntime, undefined);
    backend.runtime.?.last_submit_count = 1;
    var pipeline = shared_pipeline.Pipeline{
        .handle = 0,
        .creation_layout = 0,
        .words = &.{0x07230203},
        .entry_point = @constCast("main"),
        .layout = &.{},
        .required_subgroup_size = null,
        .references = 2,
    };
    backend.runtime.?.allocator = std.testing.allocator;
    backend.runtime.?.device = null;
    backend.runtime.?.shared_pipelines = .{};
    backend.runtime.?.pending_spirv_pipeline = &pipeline;
    defer {
        vk_pipeline.discardPendingSpirv(&backend.runtime.?);
        backend.runtime = null;
    }
    const result = try execute_command(backend, .{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } });
    try std.testing.expectEqual(@TypeOf(result.status).unsupported, result.status);
    try std.testing.expect(backend.runtime.?.pending_spirv_pipeline == null);
    try std.testing.expectEqual(@as(usize, 1), pipeline.references);
    try std.testing.expect(backend.runtime.?.last_submit_count == null);
}

test "Vulkan artifact capture releases its shader owner on success and every allocation failure" {
    for (0..4) |fail_index| {
        const backend = try ZigVulkanBackend.init(std.testing.allocator, .{
            .vendor = "amd",
            .api = .vulkan,
            .driver_version = .{ .major = 0, .minor = 0, .patch = 0 },
        }, null);
        defer destroyContext(backend);
        var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = fail_index });
        backend.artifacts.allocator = failing.allocator();
        var words = [_]u32{ 0x07230203, 1, 2 };
        const expected = words;
        var pipeline = shared_pipeline.Pipeline{
            .handle = 0,
            .creation_layout = 0,
            .words = &words,
            .entry_point = @constCast("main"),
            .layout = &.{},
            .required_subgroup_size = null,
            .references = 2,
        };
        backend.runtime = .{ .allocator = std.testing.allocator, .kernel_root = null, .pending_spirv_pipeline = &pipeline };
        defer backend.runtime = null;
        const result = backend.annotate_result(.{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } }, .{ .status = .ok, .status_message = "ok" });
        try std.testing.expectEqual(@as(usize, 1), pipeline.references);
        try std.testing.expect(backend.runtime.?.pending_spirv_pipeline == null);
        if (fail_index < 3) {
            try std.testing.expectEqual(webgpu.NativeExecutionStatus.@"error", result.status);
            try std.testing.expectEqualStrings("OutOfMemory", result.status_message);
            try std.testing.expect(backend.artifacts.pending == null);
        } else {
            try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, result.status);
            @memset(&words, 0);
            try std.testing.expectEqualSlices(u8, std.mem.sliceAsBytes(&expected), backend.artifacts.pending.?.spirv.?);
        }
    }
}
