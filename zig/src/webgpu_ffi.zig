const std = @import("std");
const model = @import("model.zig");
const types = @import("core/abi/wgpu_types.zig");
const loader = @import("core/abi/wgpu_loader.zig");
const resources = @import("core/resource/wgpu_resources.zig");
const capability_runtime_mod = @import("wgpu_capability_runtime.zig");
const p0_procs_mod = @import("wgpu_p0_procs.zig");
const p1_capability_procs_mod = @import("wgpu_p1_capability_procs.zig");
const p1_resource_table_procs_mod = @import("wgpu_p1_resource_table_procs.zig");
const p2_lifecycle_procs_mod = @import("wgpu_p2_lifecycle_procs.zig");
const surface_procs_mod = @import("full/surface/wgpu_surface_procs.zig");
const texture_procs_mod = @import("wgpu_texture_procs.zig");
const commands = @import("wgpu_commands.zig");
const compute_commands = @import("core/compute/wgpu_commands_compute.zig");
const env_flags = @import("env_flags.zig");

pub const NativeExecutionStatus = types.NativeExecutionStatus;
pub const NativeExecutionResult = types.NativeExecutionResult;
const QUEUE_SYNC_RETRY_LIMIT: u32 = 3;
const QUEUE_SYNC_RETRY_BACKOFF_NS: u64 = 1_000_000;
const TIMESTAMP_MAP_RETRY_LIMIT: u32 = 3;
const TIMESTAMP_MAP_RETRY_BACKOFF_NS: u64 = 1_000_000;
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

pub const GpuTimestampMode = enum {
    auto,
    off,
    require,
};

pub const ManagedSurface = struct {
    surface: surface_procs_mod.Surface,
    configured: bool = false,
    acquired_texture: types.WGPUTexture = null,
    last_texture_status: u32 = 0,
};

pub const CoreWebGPUBackend = struct {
    allocator: std.mem.Allocator,
    dyn_lib: ?std.DynLib = null,
    procs: ?types.Procs = null,
    capability_procs: ?p1_capability_procs_mod.CapabilityProcs = null,
    resource_table_procs: ?p1_resource_table_procs_mod.ResourceTableProcs = null,
    lifecycle_procs: ?p2_lifecycle_procs_mod.LifecycleProcs = null,
    instance: types.WGPUInstance = null,
    adapter: types.WGPUAdapter = null,
    device: types.WGPUDevice = null,
    queue: types.WGPUQueue = null,
    buffers: std.AutoHashMap(u64, types.BufferRecord),
    textures: std.AutoHashMap(u64, types.TextureRecord),
    pipeline_cache: std.AutoHashMap(u64, types.PipelineCacheEntry),
    upload_scratch: []u8 = &[_]u8{},
    upload_buffer_usage_mode: UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = 1,
    upload_submit_pending: u32 = 0,
    queue_wait_mode: QueueWaitMode = .process_events,
    queue_sync_mode: QueueSyncMode = .per_command,
    gpu_timestamp_mode: GpuTimestampMode = .auto,
    kernel_root: ?[]const u8 = null,
    library_error: []const u8 = "",
    requested_backend_type: types.WGPUBackendType = .undefined,
    adapter_has_timestamp_query: bool = false,
    adapter_has_multi_draw_indirect: bool = false,
    adapter_has_pixel_local_storage_coherent: bool = false,
    adapter_has_pixel_local_storage_non_coherent: bool = false,
    has_timestamp_query: bool = false,
    has_timestamp_inside_passes: bool = false,
    has_multi_draw_indirect: bool = false,
    has_pixel_local_storage_coherent: bool = false,
    has_pixel_local_storage_non_coherent: bool = false,
    has_adapter_limits: bool = false,
    has_device_limits: bool = false,
    adapter_limits: types.WGPULimits = std.mem.zeroes(types.WGPULimits),
    device_limits: types.WGPULimits = std.mem.zeroes(types.WGPULimits),
    uncaptured_error_state: types.UncapturedErrorState = .{},
    timestamp_debug: bool = false,
};

pub const FullWebGPUBackendState = struct {
    render_pipeline_cache: std.AutoHashMap(u32, types.RenderPipelineCacheEntry),
    render_target_view_cache: std.AutoHashMap(u64, types.RenderTextureViewCacheEntry),
    render_depth_view_cache: std.AutoHashMap(u64, types.RenderTextureViewCacheEntry),
    samplers: std.AutoHashMap(u64, types.WGPUSampler),
    surfaces: std.AutoHashMap(u64, ManagedSurface),
    render_uniform_bind_group_layout: types.WGPUBindGroupLayout = null,
    render_uniform_bind_group: types.WGPUBindGroup = null,
    render_sampler: types.WGPUSampler = null,
    render_occlusion_query_set: types.WGPUQuerySet = null,
    render_timestamp_query_set: types.WGPUQuerySet = null,
};

pub const WebGPUBackend = struct {
    const Self = @This();

    core: CoreWebGPUBackend,
    full: FullWebGPUBackendState,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !Self {
        var self = Self{
            .core = .{
                .allocator = allocator,
                .buffers = std.AutoHashMap(u64, types.BufferRecord).init(allocator),
                .textures = std.AutoHashMap(u64, types.TextureRecord).init(allocator),
                .pipeline_cache = std.AutoHashMap(u64, types.PipelineCacheEntry).init(allocator),
                .kernel_root = kernel_root,
                .library_error = "",
                .requested_backend_type = preferredBackendType(profile),
            },
            .full = .{
                .render_pipeline_cache = std.AutoHashMap(u32, types.RenderPipelineCacheEntry).init(allocator),
                .render_target_view_cache = std.AutoHashMap(u64, types.RenderTextureViewCacheEntry).init(allocator),
                .render_depth_view_cache = std.AutoHashMap(u64, types.RenderTextureViewCacheEntry).init(allocator),
                .samplers = std.AutoHashMap(u64, types.WGPUSampler).init(allocator),
                .surfaces = std.AutoHashMap(u64, ManagedSurface).init(allocator),
            },
        };
        errdefer self.deinit();
        self.core.timestamp_debug = env_flags.enabled(allocator, "DOE_WGPU_TIMESTAMP_DEBUG");
        self.core.dyn_lib = try loader.openLibrary();
        self.core.procs = try loader.loadProcs(self.core.dyn_lib.?);
        self.core.capability_procs = p1_capability_procs_mod.loadCapabilityProcs(self.core.dyn_lib);
        self.core.resource_table_procs = p1_resource_table_procs_mod.loadResourceTableProcs(self.core.dyn_lib);
        self.core.lifecycle_procs = p2_lifecycle_procs_mod.loadLifecycleProcs(self.core.dyn_lib);
        if (self.core.procs) |procs| {
            self.core.instance = procs.wgpuCreateInstance(null);
            if (self.core.instance == null) return error.NativeInstanceUnavailable;
            try capability_runtime_mod.probeInstanceCapabilities(self.core.capability_procs, self.core.instance);
            self.core.adapter = try self.requestAdapter();
            self.core.adapter_has_timestamp_query = procs.wgpuAdapterHasFeature(self.core.adapter.?, types.WGPUFeatureName_TimestampQuery) != types.WGPU_FALSE;
            self.core.adapter_has_multi_draw_indirect = procs.wgpuAdapterHasFeature(self.core.adapter.?, types.WGPUFeatureName_MultiDrawIndirect) != types.WGPU_FALSE;
            self.core.adapter_has_pixel_local_storage_coherent = procs.wgpuAdapterHasFeature(self.core.adapter.?, types.WGPUFeatureName_PixelLocalStorageCoherent) != types.WGPU_FALSE;
            self.core.adapter_has_pixel_local_storage_non_coherent = procs.wgpuAdapterHasFeature(self.core.adapter.?, types.WGPUFeatureName_PixelLocalStorageNonCoherent) != types.WGPU_FALSE;
            self.core.has_timestamp_query = self.core.adapter_has_timestamp_query;
            self.core.has_multi_draw_indirect = self.core.adapter_has_multi_draw_indirect;
            self.core.has_pixel_local_storage_coherent = self.core.adapter_has_pixel_local_storage_coherent;
            self.core.has_pixel_local_storage_non_coherent = self.core.adapter_has_pixel_local_storage_non_coherent;
            self.core.has_timestamp_inside_passes = procs.wgpuAdapterHasFeature(self.core.adapter.?, types.WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses) != types.WGPU_FALSE;
            const adapter_probe = try capability_runtime_mod.probeAdapterCapabilities(
                self.core.capability_procs,
                self.core.adapter,
                self.core.instance,
                .{
                    .adapter_has_timestamp_query = self.core.adapter_has_timestamp_query,
                    .has_timestamp_inside_passes = self.core.has_timestamp_inside_passes,
                    .adapter_has_multi_draw_indirect = self.core.adapter_has_multi_draw_indirect,
                    .adapter_has_pixel_local_storage_coherent = self.core.adapter_has_pixel_local_storage_coherent,
                    .adapter_has_pixel_local_storage_non_coherent = self.core.adapter_has_pixel_local_storage_non_coherent,
                },
            );
            self.core.adapter_has_timestamp_query = adapter_probe.adapter_has_timestamp_query;
            self.core.has_timestamp_inside_passes = adapter_probe.has_timestamp_inside_passes;
            self.core.adapter_has_multi_draw_indirect = adapter_probe.adapter_has_multi_draw_indirect;
            self.core.adapter_has_pixel_local_storage_coherent = adapter_probe.adapter_has_pixel_local_storage_coherent;
            self.core.adapter_has_pixel_local_storage_non_coherent = adapter_probe.adapter_has_pixel_local_storage_non_coherent;
            try self.captureAdapterLimits();
            self.core.device = try self.requestDevice();
            if (procs.wgpuDeviceHasFeature) |device_has_feature| {
                self.core.has_timestamp_query = device_has_feature(self.core.device.?, types.WGPUFeatureName_TimestampQuery) != types.WGPU_FALSE;
                self.core.has_multi_draw_indirect = device_has_feature(self.core.device.?, types.WGPUFeatureName_MultiDrawIndirect) != types.WGPU_FALSE;
                self.core.has_pixel_local_storage_coherent = device_has_feature(self.core.device.?, types.WGPUFeatureName_PixelLocalStorageCoherent) != types.WGPU_FALSE;
                self.core.has_pixel_local_storage_non_coherent = device_has_feature(self.core.device.?, types.WGPUFeatureName_PixelLocalStorageNonCoherent) != types.WGPU_FALSE;
            }
            const device_probe = try capability_runtime_mod.probeDeviceCapabilities(
                self.core.capability_procs,
                self.core.device,
                self.core.adapter,
                .{
                    .has_timestamp_query = self.core.has_timestamp_query,
                    .has_multi_draw_indirect = self.core.has_multi_draw_indirect,
                    .has_pixel_local_storage_coherent = self.core.has_pixel_local_storage_coherent,
                    .has_pixel_local_storage_non_coherent = self.core.has_pixel_local_storage_non_coherent,
                },
            );
            self.core.has_timestamp_query = device_probe.has_timestamp_query;
            self.core.has_multi_draw_indirect = device_probe.has_multi_draw_indirect;
            self.core.has_pixel_local_storage_coherent = device_probe.has_pixel_local_storage_coherent;
            self.core.has_pixel_local_storage_non_coherent = device_probe.has_pixel_local_storage_non_coherent;
            try self.captureDeviceLimits();
            self.core.queue = procs.wgpuDeviceGetQueue(self.core.device.?);
            if (self.core.queue == null) return error.NativeQueueUnavailable;
            capability_runtime_mod.touchPrimaryObjectRefs(
                self.core.lifecycle_procs,
                procs,
                self.core.instance,
                self.core.adapter,
                self.core.device,
                self.core.queue,
            );
            self.timestampLog(
                "init_features adapter_ts={} device_ts={} inside_passes={} adapter_multi_draw={} device_multi_draw={} adapter_pls_coherent={} adapter_pls_noncoherent={} device_pls_coherent={} device_pls_noncoherent={}\n",
                .{
                    self.core.adapter_has_timestamp_query,
                    self.core.has_timestamp_query,
                    self.core.has_timestamp_inside_passes,
                    self.core.adapter_has_multi_draw_indirect,
                    self.core.has_multi_draw_indirect,
                    self.core.adapter_has_pixel_local_storage_coherent,
                    self.core.adapter_has_pixel_local_storage_non_coherent,
                    self.core.has_pixel_local_storage_coherent,
                    self.core.has_pixel_local_storage_non_coherent,
                },
            );
        }
        return self;
    }
    fn preferredBackendType(profile: model.DeviceProfile) types.WGPUBackendType {
        return switch (profile.api) {
            .vulkan => .vulkan,
            .metal => .metal,
            .d3d12 => .d3d12,
            .webgpu => .webgpu,
        };
    }

    fn backendTypeName(backend_type: types.WGPUBackendType) []const u8 {
        return switch (backend_type) {
            .vulkan => "vulkan",
            .metal => "metal",
            .d3d12 => "d3d12",
            .webgpu => "webgpu",
            else => "undefined",
        };
    }

    pub fn deinit(self: *Self) void {
        const procs = self.core.procs orelse return;
        const p0_procs = p0_procs_mod.loadP0Procs(self.core.dyn_lib);

        if (self.full.render_uniform_bind_group) |bind_group| {
            procs.wgpuBindGroupRelease(bind_group);
            self.full.render_uniform_bind_group = null;
        }
        if (self.full.render_uniform_bind_group_layout) |bind_group_layout| {
            procs.wgpuBindGroupLayoutRelease(bind_group_layout);
            self.full.render_uniform_bind_group_layout = null;
        }
        if (self.full.render_sampler) |sampler| {
            if (texture_procs_mod.loadTextureProcs(self.core.dyn_lib)) |texture_procs| {
                texture_procs.sampler_release(sampler);
            }
            self.full.render_sampler = null;
        }

        if (texture_procs_mod.loadTextureProcs(self.core.dyn_lib)) |texture_procs| {
            var sampler_it = self.full.samplers.valueIterator();
            while (sampler_it.next()) |sampler| {
                if (sampler.* != null) texture_procs.sampler_release(sampler.*);
            }
        }
        self.full.samplers.clearAndFree();

        var it = self.core.buffers.valueIterator();
        while (it.next()) |record| {
            p0_procs_mod.destroyBuffer(p0_procs, record.buffer);
            procs.wgpuBufferRelease(record.buffer);
        }
        self.core.buffers.clearAndFree();

        var target_view_it = self.full.render_target_view_cache.valueIterator();
        while (target_view_it.next()) |entry| {
            procs.wgpuTextureViewRelease(entry.view);
        }
        self.full.render_target_view_cache.clearAndFree();

        var depth_view_it = self.full.render_depth_view_cache.valueIterator();
        while (depth_view_it.next()) |entry| {
            procs.wgpuTextureViewRelease(entry.view);
        }
        self.full.render_depth_view_cache.clearAndFree();

        const texture_procs = texture_procs_mod.loadTextureProcs(self.core.dyn_lib);
        var texture_it = self.core.textures.valueIterator();
        while (texture_it.next()) |record| {
            if (texture_procs) |tp| {
                tp.texture_destroy(record.texture);
            }
            procs.wgpuTextureRelease(record.texture);
        }
        self.core.textures.clearAndFree();

        if (surface_procs_mod.loadSurfaceProcs(self.core.dyn_lib)) |surface_procs| {
            var surface_it = self.full.surfaces.valueIterator();
            while (surface_it.next()) |managed_surface| {
                if (managed_surface.*.acquired_texture != null) {
                    procs.wgpuTextureRelease(managed_surface.*.acquired_texture);
                }
                if (managed_surface.*.configured) {
                    surface_procs.surface_unconfigure(managed_surface.*.surface);
                }
                surface_procs.surface_release(managed_surface.*.surface);
            }
        }
        self.full.surfaces.clearAndFree();

        var pipe_it = self.core.pipeline_cache.valueIterator();
        while (pipe_it.next()) |entry| {
            procs.wgpuComputePipelineRelease(entry.pipeline);
            procs.wgpuShaderModuleRelease(entry.shader_module);
        }
        self.core.pipeline_cache.clearAndFree();

        var render_pipe_it = self.full.render_pipeline_cache.valueIterator();
        while (render_pipe_it.next()) |entry| {
            if (procs.wgpuRenderPipelineRelease) |release_render_pipeline| {
                release_render_pipeline(entry.pipeline);
            }
            procs.wgpuShaderModuleRelease(entry.shader_module);
        }
        self.full.render_pipeline_cache.clearAndFree();
        if (self.full.render_occlusion_query_set) |query_set| {
            p0_procs_mod.destroyQuerySet(p0_procs, query_set);
            procs.wgpuQuerySetRelease(query_set);
            self.full.render_occlusion_query_set = null;
        }
        if (self.full.render_timestamp_query_set) |query_set| {
            p0_procs_mod.destroyQuerySet(p0_procs, query_set);
            procs.wgpuQuerySetRelease(query_set);
            self.full.render_timestamp_query_set = null;
        }

        if (self.core.upload_scratch.len > 0) {
            self.core.allocator.free(self.core.upload_scratch);
            self.core.upload_scratch = &[_]u8{};
        }

        if (self.core.queue) |queue| {
            procs.wgpuQueueRelease(queue);
            self.core.queue = null;
        }
        if (self.core.device) |device| {
            if (p0_procs) |loaded| {
                if (loaded.device_destroy) |destroy_device| {
                    destroy_device(device);
                }
            }
            procs.wgpuDeviceRelease(device);
            self.core.device = null;
        }
        if (self.core.adapter) |adapter| {
            procs.wgpuAdapterRelease(adapter);
            self.core.adapter = null;
        }
        if (self.core.instance) |instance| {
            procs.wgpuInstanceRelease(instance);
            self.core.instance = null;
        }

        if (self.core.dyn_lib) |*lib| {
            lib.close();
            self.core.dyn_lib = null;
        }

        self.core.procs = null;
        self.core.capability_procs = null;
        self.core.resource_table_procs = null;
        self.core.lifecycle_procs = null;
    }

    pub fn backendAvailable(self: Self) bool {
        return self.core.procs != null and self.core.instance != null and self.core.adapter != null and self.core.device != null and self.core.queue != null;
    }

    pub fn executeCommand(self: *Self, command: model.Command) !NativeExecutionResult {
        return commands.executeCommand(self, command);
    }

    pub fn runCapabilityIntrospection(self: *Self) !void {
        try capability_runtime_mod.probeInstanceCapabilities(self.core.capability_procs, self.core.instance);
        const adapter_probe = try capability_runtime_mod.probeAdapterCapabilities(
            self.core.capability_procs,
            self.core.adapter,
            self.core.instance,
            .{
                .adapter_has_timestamp_query = self.core.adapter_has_timestamp_query,
                .has_timestamp_inside_passes = self.core.has_timestamp_inside_passes,
                .adapter_has_multi_draw_indirect = self.core.adapter_has_multi_draw_indirect,
                .adapter_has_pixel_local_storage_coherent = self.core.adapter_has_pixel_local_storage_coherent,
                .adapter_has_pixel_local_storage_non_coherent = self.core.adapter_has_pixel_local_storage_non_coherent,
            },
        );
        self.core.adapter_has_timestamp_query = adapter_probe.adapter_has_timestamp_query;
        self.core.has_timestamp_inside_passes = adapter_probe.has_timestamp_inside_passes;
        self.core.adapter_has_multi_draw_indirect = adapter_probe.adapter_has_multi_draw_indirect;
        self.core.adapter_has_pixel_local_storage_coherent = adapter_probe.adapter_has_pixel_local_storage_coherent;
        self.core.adapter_has_pixel_local_storage_non_coherent = adapter_probe.adapter_has_pixel_local_storage_non_coherent;
        const device_probe = try capability_runtime_mod.probeDeviceCapabilities(
            self.core.capability_procs,
            self.core.device,
            self.core.adapter,
            .{
                .has_timestamp_query = self.core.has_timestamp_query,
                .has_multi_draw_indirect = self.core.has_multi_draw_indirect,
                .has_pixel_local_storage_coherent = self.core.has_pixel_local_storage_coherent,
                .has_pixel_local_storage_non_coherent = self.core.has_pixel_local_storage_non_coherent,
            },
        );
        self.core.has_timestamp_query = device_probe.has_timestamp_query;
        self.core.has_multi_draw_indirect = device_probe.has_multi_draw_indirect;
        self.core.has_pixel_local_storage_coherent = device_probe.has_pixel_local_storage_coherent;
        self.core.has_pixel_local_storage_non_coherent = device_probe.has_pixel_local_storage_non_coherent;
        try self.captureAdapterLimits();
        try self.captureDeviceLimits();
    }

    pub fn getResourceTableProcs(self: Self) ?p1_resource_table_procs_mod.ResourceTableProcs {
        return self.core.resource_table_procs;
    }

    pub fn getLifecycleProcs(self: Self) ?p2_lifecycle_procs_mod.LifecycleProcs {
        return self.core.lifecycle_procs;
    }

    pub fn setUploadBehavior(
        self: *Self,
        usage_mode: UploadBufferUsageMode,
        submit_every: u32,
    ) void {
        self.core.upload_buffer_usage_mode = usage_mode;
        self.core.upload_submit_every = if (submit_every == 0) 1 else submit_every;
        self.core.upload_submit_pending = 0;
    }

    pub fn setQueueWaitMode(self: *Self, wait_mode: QueueWaitMode) void {
        self.core.queue_wait_mode = wait_mode;
    }

    pub fn setQueueSyncMode(self: *Self, sync_mode: QueueSyncMode) void {
        self.core.queue_sync_mode = sync_mode;
    }

    pub fn setGpuTimestampMode(self: *Self, timestamp_mode: GpuTimestampMode) void {
        self.core.gpu_timestamp_mode = timestamp_mode;
    }

    pub fn gpuTimestampsEnabled(self: *const Self) bool {
        return self.core.has_timestamp_query and self.core.gpu_timestamp_mode != .off;
    }

    pub fn gpuTimestampsRequired(self: *const Self) bool {
        return self.core.gpu_timestamp_mode == .require;
    }

    pub fn clearUncapturedError(self: *Self) void {
        self.core.uncaptured_error_state.error_type.store(@intFromEnum(types.WGPUErrorType.noError), .release);
        self.core.uncaptured_error_state.pending.store(0, .release);
    }

    pub fn takeUncapturedError(self: *Self) ?types.WGPUErrorType {
        if (self.core.uncaptured_error_state.pending.swap(0, .acq_rel) == 0) return null;
        const raw = self.core.uncaptured_error_state.error_type.load(.acquire);
        return @enumFromInt(raw);
    }

    pub fn uncapturedErrorStatusMessage(error_type: types.WGPUErrorType) []const u8 {
        return switch (error_type) {
            .validation => "uncaptured WebGPU validation error",
            .outOfMemory => "uncaptured WebGPU out-of-memory error",
            .internal => "uncaptured WebGPU internal error",
            .unknown => "uncaptured WebGPU unknown error",
            else => "uncaptured WebGPU error",
        };
    }

    pub fn effectiveLimits(self: *const Self) ?*const types.WGPULimits {
        if (self.core.has_device_limits) return &self.core.device_limits;
        if (self.core.has_adapter_limits) return &self.core.adapter_limits;
        return null;
    }

    pub fn releaseFullTextureViewsForTexture(self: *Self, texture: types.WGPUTexture) void {
        const procs = self.core.procs orelse return;

        var target_keys = std.ArrayList(u64).empty;
        defer target_keys.deinit(self.core.allocator);
        var target_it = self.full.render_target_view_cache.iterator();
        while (target_it.next()) |entry| {
            if (entry.value_ptr.texture == texture) target_keys.append(self.core.allocator, entry.key_ptr.*) catch return;
        }
        for (target_keys.items) |key| {
            if (self.full.render_target_view_cache.fetchRemove(key)) |removed| {
                procs.wgpuTextureViewRelease(removed.value.view);
            }
        }

        var depth_keys = std.ArrayList(u64).empty;
        defer depth_keys.deinit(self.core.allocator);
        var depth_it = self.full.render_depth_view_cache.iterator();
        while (depth_it.next()) |entry| {
            if (entry.value_ptr.texture == texture) depth_keys.append(self.core.allocator, entry.key_ptr.*) catch return;
        }
        for (depth_keys.items) |key| {
            if (self.full.render_depth_view_cache.fetchRemove(key)) |removed| {
                procs.wgpuTextureViewRelease(removed.value.view);
            }
        }
    }

    pub const syncAfterSubmit = @import("core/queue/wgpu_ffi_sync.zig").syncAfterSubmit;
    pub const submitEmpty = @import("core/queue/wgpu_ffi_sync.zig").submitEmpty;
    pub const submitCommandBuffers = @import("core/queue/wgpu_ffi_sync.zig").submitCommandBuffers;
    pub const submitInternal = @import("core/queue/wgpu_ffi_sync.zig").submitInternal;
    pub const flushQueue = @import("core/queue/wgpu_ffi_sync.zig").flushQueue;
    pub const waitForQueue = @import("core/queue/wgpu_ffi_sync.zig").waitForQueue;
    pub const waitForQueueOnce = @import("core/queue/wgpu_ffi_sync.zig").waitForQueueOnce;
    pub const shouldRetryQueueWait = @import("core/queue/wgpu_ffi_sync.zig").shouldRetryQueueWait;
    pub const waitForQueueProcessEvents = @import("core/queue/wgpu_ffi_sync.zig").waitForQueueProcessEvents;
    pub const waitForQueueWaitAny = @import("core/queue/wgpu_ffi_sync.zig").waitForQueueWaitAny;
    pub const readTimestampBuffer = @import("core/queue/wgpu_ffi_sync.zig").readTimestampBuffer;
    pub const readTimestampBufferOnce = @import("core/queue/wgpu_ffi_sync.zig").readTimestampBufferOnce;
    pub const shouldRetryTimestampMap = @import("core/queue/wgpu_ffi_sync.zig").shouldRetryTimestampMap;
    pub const processEventsUntil = @import("core/queue/wgpu_ffi_sync.zig").processEventsUntil;
    pub const createSurface = @import("full/surface/wgpu_ffi_surface.zig").createSurface;
    pub const getSurfaceCapabilities = @import("full/surface/wgpu_ffi_surface.zig").getSurfaceCapabilities;
    pub const freeSurfaceCapabilities = @import("full/surface/wgpu_ffi_surface.zig").freeSurfaceCapabilities;
    pub const configureSurface = @import("full/surface/wgpu_ffi_surface.zig").configureSurface;
    pub const getCurrentSurfaceTexture = @import("full/surface/wgpu_ffi_surface.zig").getCurrentSurfaceTexture;
    pub const presentSurface = @import("full/surface/wgpu_ffi_surface.zig").presentSurface;
    pub const unconfigureSurface = @import("full/surface/wgpu_ffi_surface.zig").unconfigureSurface;
    pub const releaseSurface = @import("full/surface/wgpu_ffi_surface.zig").releaseSurface;
    pub fn prewarmUploadPath(self: *Self, max_upload_bytes: u64) !void {
        if (max_upload_bytes == 0) return;
        if (!self.backendAvailable()) return error.NativeQueueUnavailable;

        const usage = switch (self.core.upload_buffer_usage_mode) {
            .copy_dst_copy_src => types.WGPUBufferUsage_CopyDst | types.WGPUBufferUsage_CopySrc,
            .copy_dst => types.WGPUBufferUsage_CopyDst,
        };
        _ = try resources.getOrCreateBuffer(self, loader.BUFFER_UPLOAD_KEY, max_upload_bytes, usage);

        const bytes_usize = std.math.cast(usize, max_upload_bytes) orelse {
            return error.BufferAllocationFailed;
        };
        if (bytes_usize <= self.core.upload_scratch.len) return;

        if (self.core.upload_scratch.len > 0) {
            self.core.allocator.free(self.core.upload_scratch);
        }
        self.core.upload_scratch = try self.core.allocator.alloc(u8, bytes_usize);
        @memset(self.core.upload_scratch, 0);
    }

    pub fn prewarmKernelPipeline(self: *Self, kernel: []const u8, bindings: ?[]const model.KernelBinding) !void {
        if (!self.backendAvailable()) return;
        const source = compute_commands.resolveKernelSource(self, kernel) catch return;
        defer if (source.owned) self.core.allocator.free(source.source);
        const entry_point = "main";
        const cache_key = compute_commands.pipelineCacheKey(source.source, entry_point);
        if (self.core.pipeline_cache.get(cache_key) != null) return;
        const procs = self.core.procs orelse return;
        const shader_module = resources.createShaderModule(self, source.source) catch return;
        const pipeline = resources.createComputePipeline(self, kernel, shader_module, entry_point, null) catch {
            procs.wgpuShaderModuleRelease(shader_module);
            return;
        };
        self.core.pipeline_cache.put(cache_key, .{ .shader_module = shader_module, .pipeline = pipeline }) catch {};
        if (bindings) |bs| {
            for (bs) |b| {
                if (b.resource_kind != .buffer) continue;
                const usage = types.WGPUBufferUsage_Storage | types.WGPUBufferUsage_CopyDst | types.WGPUBufferUsage_CopySrc;
                _ = resources.getOrCreateBuffer(self, b.resource_handle, b.buffer_size, usage) catch {};
            }
        }
    }

    fn captureAdapterLimits(self: *Self) !void {
        self.core.has_adapter_limits = false;
        self.core.adapter_limits = types.initLimits();
        const cap = self.core.capability_procs orelse return;
        const get_limits = cap.adapter_get_limits orelse return;
        if (self.core.adapter == null) return;
        if (get_limits(self.core.adapter.?, &self.core.adapter_limits) != types.WGPUStatus_Success) {
            return error.AdapterLimitsQueryFailed;
        }
        self.core.has_adapter_limits = true;
    }

    fn captureDeviceLimits(self: *Self) !void {
        self.core.has_device_limits = false;
        self.core.device_limits = types.initLimits();
        const cap = self.core.capability_procs orelse return;
        const get_limits = cap.device_get_limits orelse return;
        if (self.core.device == null) return;
        if (get_limits(self.core.device.?, &self.core.device_limits) != types.WGPUStatus_Success) {
            return error.DeviceLimitsQueryFailed;
        }
        self.core.has_device_limits = true;
    }

    fn requestAdapter(self: *Self) !types.WGPUAdapter {
        var state = types.RequestState{};
        const request_info = types.WGPURequestAdapterCallbackInfo{
            .nextInChain = null,
            .mode = types.WGPUCallbackMode_AllowProcessEvents,
            .callback = loader.adapterCallback,
            .userdata1 = &state,
            .userdata2 = null,
        };
        const options = types.WGPURequestAdapterOptions{
            .nextInChain = null,
            .featureLevel = .undefined,
            .powerPreference = .undefined,
            .forceFallbackAdapter = types.WGPU_FALSE,
            .backendType = self.core.requested_backend_type,
            .compatibleSurface = null,
        };
        self.timestampLog(
            "request_adapter backend_type={s}\n",
            .{backendTypeName(self.core.requested_backend_type)},
        );

        const adapter_request_info = request_info;
        const future = self.core.procs.?.wgpuInstanceRequestAdapter(
            self.core.instance.?,
            &options,
            adapter_request_info,
        );
        if (future.id == 0) return error.AdapterRequestFailed;

        try self.processEventsUntil(&state.done, loader.DEFAULT_TIMEOUT_NS);
        if (!state.done) return error.AdapterRequestNoCallback;
        self.timestampLog("request_adapter_status={}\n", .{@intFromEnum(state.status)});

        return switch (state.status) {
            .success => state.adapter orelse error.AdapterRequestFailed,
            .callbackCancelled, .unavailable => error.AdapterUnavailable,
            .@"error" => error.AdapterRequestFailed,
            else => error.AdapterRequestFailed,
        };
    }

    fn requestDevice(self: *Self) !types.WGPUDevice {
        self.clearUncapturedError();
        var state = types.DeviceRequestState{};
        const request_info = types.WGPURequestDeviceCallbackInfo{
            .nextInChain = null,
            .mode = types.WGPUCallbackMode_AllowProcessEvents,
            .callback = loader.deviceRequestCallback,
            .userdata1 = &state,
            .userdata2 = null,
        };
        var required_features = [_]types.WGPUFeatureName{undefined} ** 6;
        var feature_count: usize = 0;
        const has_resource_table_feature = self.core.procs.?.wgpuAdapterHasFeature(self.core.adapter.?, types.WGPUFeatureName_ChromiumExperimentalSamplingResourceTable) != types.WGPU_FALSE;
        if (self.core.has_timestamp_query) {
            required_features[feature_count] = types.WGPUFeatureName_TimestampQuery;
            feature_count += 1;
        }
        if (self.core.has_timestamp_inside_passes) {
            required_features[feature_count] = types.WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses;
            feature_count += 1;
        }
        if (self.core.has_multi_draw_indirect) {
            required_features[feature_count] = types.WGPUFeatureName_MultiDrawIndirect;
            feature_count += 1;
        }
        if (self.core.has_pixel_local_storage_coherent) {
            required_features[feature_count] = types.WGPUFeatureName_PixelLocalStorageCoherent;
            feature_count += 1;
        }
        if (self.core.has_pixel_local_storage_non_coherent) {
            required_features[feature_count] = types.WGPUFeatureName_PixelLocalStorageNonCoherent;
            feature_count += 1;
        }
        if (has_resource_table_feature) {
            required_features[feature_count] = types.WGPUFeatureName_ChromiumExperimentalSamplingResourceTable;
            feature_count += 1;
        }
        self.timestampLog("request_device required_features timestamp={} inside_passes={} multi_draw={} pls_coherent={} pls_noncoherent={} resource_table={} count={} adapter_limits={} max_storage_binding={} max_uniform_binding={} max_buffer={}\n", .{
            self.core.has_timestamp_query,
            self.core.has_timestamp_inside_passes,
            self.core.has_multi_draw_indirect,
            self.core.has_pixel_local_storage_coherent,
            self.core.has_pixel_local_storage_non_coherent,
            has_resource_table_feature,
            feature_count,
            self.core.has_adapter_limits,
            self.core.adapter_limits.maxStorageBufferBindingSize,
            self.core.adapter_limits.maxUniformBufferBindingSize,
            self.core.adapter_limits.maxBufferSize,
        });
        const device_desc = types.WGPUDeviceDescriptor{
            .nextInChain = null,
            .label = loader.emptyStringView(),
            .requiredFeatureCount = feature_count,
            .requiredFeatures = if (feature_count > 0) required_features[0..].ptr else null,
            .requiredLimits = if (self.core.has_adapter_limits) &self.core.adapter_limits else null,
            .defaultQueue = .{ .nextInChain = null, .label = loader.emptyStringView() },
            .deviceLostCallbackInfo = .{
                .nextInChain = null,
                .mode = types.WGPUCallbackMode_AllowProcessEvents,
                .callback = null,
                .userdata1 = null,
                .userdata2 = null,
            },
            .uncapturedErrorCallbackInfo = .{
                .nextInChain = null,
                .callback = loader.uncapturedErrorCallback,
                .userdata1 = &self.core.uncaptured_error_state,
                .userdata2 = null,
            },
        };
        const device_request_info = request_info;
        const future = self.core.procs.?.wgpuAdapterRequestDevice(self.core.adapter.?, &device_desc, device_request_info);
        if (future.id == 0) return error.DeviceRequestFailed;

        try self.processEventsUntil(&state.done, loader.DEFAULT_TIMEOUT_NS);
        if (!state.done) return error.DeviceRequestNoCallback;
        self.timestampLog("request_device_status={}\n", .{@intFromEnum(state.status)});

        return switch (state.status) {
            .success => state.device orelse error.DeviceRequestFailed,
            .callbackCancelled => error.DeviceRequestCancelled,
            .@"error" => error.DeviceRequestFailed,
            else => error.DeviceRequestFailed,
        };
    }

    pub fn timestampLog(self: *Self, comptime fmt: []const u8, args: anytype) void {
        if (!self.core.timestamp_debug) return;
        std.debug.print("[doe-timestamp] " ++ fmt, args);
    }
};
