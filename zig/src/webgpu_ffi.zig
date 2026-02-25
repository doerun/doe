const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const capability_runtime_mod = @import("wgpu_capability_runtime.zig");
const p0_procs_mod = @import("wgpu_p0_procs.zig");
const p1_capability_procs_mod = @import("wgpu_p1_capability_procs.zig");
const p1_resource_table_procs_mod = @import("wgpu_p1_resource_table_procs.zig");
const p2_lifecycle_procs_mod = @import("wgpu_p2_lifecycle_procs.zig");
const surface_procs_mod = @import("wgpu_surface_procs.zig");
const texture_procs_mod = @import("wgpu_texture_procs.zig");
const commands = @import("wgpu_commands.zig");
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

pub const ManagedSurface = struct {
    surface: surface_procs_mod.Surface,
    configured: bool = false,
    acquired_texture: types.WGPUTexture = null,
    last_texture_status: u32 = 0,
};

pub const WebGPUBackend = struct {
    const Self = @This();

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
    upload_scratch: []u8 = &[_]u8{},
    upload_buffer_usage_mode: UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = 1,
    upload_submit_pending: u32 = 0,
    queue_wait_mode: QueueWaitMode = .process_events,
    queue_sync_mode: QueueSyncMode = .per_command,
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

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !Self {
        var self = Self{
            .allocator = allocator,
            .buffers = std.AutoHashMap(u64, types.BufferRecord).init(allocator),
            .textures = std.AutoHashMap(u64, types.TextureRecord).init(allocator),
            .pipeline_cache = std.AutoHashMap(u64, types.PipelineCacheEntry).init(allocator),
            .render_pipeline_cache = std.AutoHashMap(u32, types.RenderPipelineCacheEntry).init(allocator),
            .render_target_view_cache = std.AutoHashMap(u64, types.RenderTextureViewCacheEntry).init(allocator),
            .render_depth_view_cache = std.AutoHashMap(u64, types.RenderTextureViewCacheEntry).init(allocator),
            .samplers = std.AutoHashMap(u64, types.WGPUSampler).init(allocator),
            .surfaces = std.AutoHashMap(u64, ManagedSurface).init(allocator),
            .kernel_root = kernel_root,
            .library_error = "",
            .requested_backend_type = preferredBackendType(profile),
        };
        errdefer self.deinit();
        self.timestamp_debug = env_flags.enabled(allocator, "FAWN_WGPU_TIMESTAMP_DEBUG");
        self.dyn_lib = try loader.openLibrary();
        self.procs = try loader.loadProcs(self.dyn_lib.?);
        self.capability_procs = p1_capability_procs_mod.loadCapabilityProcs(self.dyn_lib);
        self.resource_table_procs = p1_resource_table_procs_mod.loadResourceTableProcs(self.dyn_lib);
        self.lifecycle_procs = p2_lifecycle_procs_mod.loadLifecycleProcs(self.dyn_lib);
        if (self.procs) |procs| {
            self.instance = procs.wgpuCreateInstance(null);
            if (self.instance == null) return error.NativeInstanceUnavailable;
            try capability_runtime_mod.probeInstanceCapabilities(self.capability_procs, self.instance);
            self.adapter = try self.requestAdapter();
            self.adapter_has_timestamp_query = procs.wgpuAdapterHasFeature(self.adapter.?, types.WGPUFeatureName_TimestampQuery) != types.WGPU_FALSE;
            self.adapter_has_multi_draw_indirect = procs.wgpuAdapterHasFeature(self.adapter.?, types.WGPUFeatureName_MultiDrawIndirect) != types.WGPU_FALSE;
            self.adapter_has_pixel_local_storage_coherent = procs.wgpuAdapterHasFeature(self.adapter.?, types.WGPUFeatureName_PixelLocalStorageCoherent) != types.WGPU_FALSE;
            self.adapter_has_pixel_local_storage_non_coherent = procs.wgpuAdapterHasFeature(self.adapter.?, types.WGPUFeatureName_PixelLocalStorageNonCoherent) != types.WGPU_FALSE;
            self.has_timestamp_query = self.adapter_has_timestamp_query;
            self.has_multi_draw_indirect = self.adapter_has_multi_draw_indirect;
            self.has_pixel_local_storage_coherent = self.adapter_has_pixel_local_storage_coherent;
            self.has_pixel_local_storage_non_coherent = self.adapter_has_pixel_local_storage_non_coherent;
            self.has_timestamp_inside_passes = procs.wgpuAdapterHasFeature(self.adapter.?, types.WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses) != types.WGPU_FALSE;
            const adapter_probe = try capability_runtime_mod.probeAdapterCapabilities(
                self.capability_procs,
                self.adapter,
                self.instance,
                .{
                    .adapter_has_timestamp_query = self.adapter_has_timestamp_query,
                    .has_timestamp_inside_passes = self.has_timestamp_inside_passes,
                    .adapter_has_multi_draw_indirect = self.adapter_has_multi_draw_indirect,
                    .adapter_has_pixel_local_storage_coherent = self.adapter_has_pixel_local_storage_coherent,
                    .adapter_has_pixel_local_storage_non_coherent = self.adapter_has_pixel_local_storage_non_coherent,
                },
            );
            self.adapter_has_timestamp_query = adapter_probe.adapter_has_timestamp_query;
            self.has_timestamp_inside_passes = adapter_probe.has_timestamp_inside_passes;
            self.adapter_has_multi_draw_indirect = adapter_probe.adapter_has_multi_draw_indirect;
            self.adapter_has_pixel_local_storage_coherent = adapter_probe.adapter_has_pixel_local_storage_coherent;
            self.adapter_has_pixel_local_storage_non_coherent = adapter_probe.adapter_has_pixel_local_storage_non_coherent;
            try self.captureAdapterLimits();
            self.device = try self.requestDevice();
            if (procs.wgpuDeviceHasFeature) |device_has_feature| {
                self.has_timestamp_query = device_has_feature(self.device.?, types.WGPUFeatureName_TimestampQuery) != types.WGPU_FALSE;
                self.has_multi_draw_indirect = device_has_feature(self.device.?, types.WGPUFeatureName_MultiDrawIndirect) != types.WGPU_FALSE;
                self.has_pixel_local_storage_coherent = device_has_feature(self.device.?, types.WGPUFeatureName_PixelLocalStorageCoherent) != types.WGPU_FALSE;
                self.has_pixel_local_storage_non_coherent = device_has_feature(self.device.?, types.WGPUFeatureName_PixelLocalStorageNonCoherent) != types.WGPU_FALSE;
            }
            const device_probe = try capability_runtime_mod.probeDeviceCapabilities(
                self.capability_procs,
                self.device,
                self.adapter,
                .{
                    .has_timestamp_query = self.has_timestamp_query,
                    .has_multi_draw_indirect = self.has_multi_draw_indirect,
                    .has_pixel_local_storage_coherent = self.has_pixel_local_storage_coherent,
                    .has_pixel_local_storage_non_coherent = self.has_pixel_local_storage_non_coherent,
                },
            );
            self.has_timestamp_query = device_probe.has_timestamp_query;
            self.has_multi_draw_indirect = device_probe.has_multi_draw_indirect;
            self.has_pixel_local_storage_coherent = device_probe.has_pixel_local_storage_coherent;
            self.has_pixel_local_storage_non_coherent = device_probe.has_pixel_local_storage_non_coherent;
            try self.captureDeviceLimits();
            self.queue = procs.wgpuDeviceGetQueue(self.device.?);
            if (self.queue == null) return error.NativeQueueUnavailable;
            capability_runtime_mod.touchPrimaryObjectRefs(
                self.lifecycle_procs,
                procs,
                self.instance,
                self.adapter,
                self.device,
                self.queue,
            );
            self.timestampLog(
                "init_features adapter_ts={} device_ts={} inside_passes={} adapter_multi_draw={} device_multi_draw={} adapter_pls_coherent={} adapter_pls_noncoherent={} device_pls_coherent={} device_pls_noncoherent={}\n",
                .{
                    self.adapter_has_timestamp_query,
                    self.has_timestamp_query,
                    self.has_timestamp_inside_passes,
                    self.adapter_has_multi_draw_indirect,
                    self.has_multi_draw_indirect,
                    self.adapter_has_pixel_local_storage_coherent,
                    self.adapter_has_pixel_local_storage_non_coherent,
                    self.has_pixel_local_storage_coherent,
                    self.has_pixel_local_storage_non_coherent,
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

    pub fn deinit(self: *Self) void {
        const procs = self.procs orelse return;
        const p0_procs = p0_procs_mod.loadP0Procs(self.dyn_lib);

        if (self.render_uniform_bind_group) |bind_group| {
            procs.wgpuBindGroupRelease(bind_group);
            self.render_uniform_bind_group = null;
        }
        if (self.render_uniform_bind_group_layout) |bind_group_layout| {
            procs.wgpuBindGroupLayoutRelease(bind_group_layout);
            self.render_uniform_bind_group_layout = null;
        }
        if (self.render_sampler) |sampler| {
            if (texture_procs_mod.loadTextureProcs(self.dyn_lib)) |texture_procs| {
                texture_procs.sampler_release(sampler);
            }
            self.render_sampler = null;
        }

        if (texture_procs_mod.loadTextureProcs(self.dyn_lib)) |texture_procs| {
            var sampler_it = self.samplers.valueIterator();
            while (sampler_it.next()) |sampler| {
                if (sampler.* != null) texture_procs.sampler_release(sampler.*);
            }
        }
        self.samplers.clearAndFree();

        var it = self.buffers.valueIterator();
        while (it.next()) |record| {
            p0_procs_mod.destroyBuffer(p0_procs, record.buffer);
            procs.wgpuBufferRelease(record.buffer);
        }
        self.buffers.clearAndFree();

        var target_view_it = self.render_target_view_cache.valueIterator();
        while (target_view_it.next()) |entry| {
            procs.wgpuTextureViewRelease(entry.view);
        }
        self.render_target_view_cache.clearAndFree();

        var depth_view_it = self.render_depth_view_cache.valueIterator();
        while (depth_view_it.next()) |entry| {
            procs.wgpuTextureViewRelease(entry.view);
        }
        self.render_depth_view_cache.clearAndFree();

        const texture_procs = texture_procs_mod.loadTextureProcs(self.dyn_lib);
        var texture_it = self.textures.valueIterator();
        while (texture_it.next()) |record| {
            if (texture_procs) |tp| {
                tp.texture_destroy(record.texture);
            }
            procs.wgpuTextureRelease(record.texture);
        }
        self.textures.clearAndFree();

        if (surface_procs_mod.loadSurfaceProcs(self.dyn_lib)) |surface_procs| {
            var surface_it = self.surfaces.valueIterator();
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
        self.surfaces.clearAndFree();

        var pipe_it = self.pipeline_cache.valueIterator();
        while (pipe_it.next()) |entry| {
            procs.wgpuComputePipelineRelease(entry.pipeline);
            procs.wgpuShaderModuleRelease(entry.shader_module);
        }
        self.pipeline_cache.clearAndFree();

        var render_pipe_it = self.render_pipeline_cache.valueIterator();
        while (render_pipe_it.next()) |entry| {
            if (procs.wgpuRenderPipelineRelease) |release_render_pipeline| {
                release_render_pipeline(entry.pipeline);
            }
            procs.wgpuShaderModuleRelease(entry.shader_module);
        }
        self.render_pipeline_cache.clearAndFree();
        if (self.render_occlusion_query_set) |query_set| {
            p0_procs_mod.destroyQuerySet(p0_procs, query_set);
            procs.wgpuQuerySetRelease(query_set);
            self.render_occlusion_query_set = null;
        }
        if (self.render_timestamp_query_set) |query_set| {
            p0_procs_mod.destroyQuerySet(p0_procs, query_set);
            procs.wgpuQuerySetRelease(query_set);
            self.render_timestamp_query_set = null;
        }

        if (self.upload_scratch.len > 0) {
            self.allocator.free(self.upload_scratch);
            self.upload_scratch = &[_]u8{};
        }

        if (self.queue) |queue| {
            procs.wgpuQueueRelease(queue);
            self.queue = null;
        }
        if (self.device) |device| {
            if (p0_procs) |loaded| {
                if (loaded.device_destroy) |destroy_device| {
                    destroy_device(device);
                }
            }
            procs.wgpuDeviceRelease(device);
            self.device = null;
        }
        if (self.adapter) |adapter| {
            procs.wgpuAdapterRelease(adapter);
            self.adapter = null;
        }
        if (self.instance) |instance| {
            procs.wgpuInstanceRelease(instance);
            self.instance = null;
        }

        if (self.dyn_lib) |*lib| {
            lib.close();
            self.dyn_lib = null;
        }

        self.procs = null;
        self.capability_procs = null;
        self.resource_table_procs = null;
        self.lifecycle_procs = null;
    }

    pub fn backendAvailable(self: Self) bool {
        return self.procs != null and self.instance != null and self.adapter != null and self.device != null and self.queue != null;
    }

    pub fn executeCommand(self: *Self, command: model.Command) !NativeExecutionResult {
        return commands.executeCommand(self, command);
    }

    pub fn runCapabilityIntrospection(self: *Self) !void {
        try capability_runtime_mod.probeInstanceCapabilities(self.capability_procs, self.instance);
        const adapter_probe = try capability_runtime_mod.probeAdapterCapabilities(
            self.capability_procs,
            self.adapter,
            self.instance,
            .{
                .adapter_has_timestamp_query = self.adapter_has_timestamp_query,
                .has_timestamp_inside_passes = self.has_timestamp_inside_passes,
                .adapter_has_multi_draw_indirect = self.adapter_has_multi_draw_indirect,
                .adapter_has_pixel_local_storage_coherent = self.adapter_has_pixel_local_storage_coherent,
                .adapter_has_pixel_local_storage_non_coherent = self.adapter_has_pixel_local_storage_non_coherent,
            },
        );
        self.adapter_has_timestamp_query = adapter_probe.adapter_has_timestamp_query;
        self.has_timestamp_inside_passes = adapter_probe.has_timestamp_inside_passes;
        self.adapter_has_multi_draw_indirect = adapter_probe.adapter_has_multi_draw_indirect;
        self.adapter_has_pixel_local_storage_coherent = adapter_probe.adapter_has_pixel_local_storage_coherent;
        self.adapter_has_pixel_local_storage_non_coherent = adapter_probe.adapter_has_pixel_local_storage_non_coherent;
        const device_probe = try capability_runtime_mod.probeDeviceCapabilities(
            self.capability_procs,
            self.device,
            self.adapter,
            .{
                .has_timestamp_query = self.has_timestamp_query,
                .has_multi_draw_indirect = self.has_multi_draw_indirect,
                .has_pixel_local_storage_coherent = self.has_pixel_local_storage_coherent,
                .has_pixel_local_storage_non_coherent = self.has_pixel_local_storage_non_coherent,
            },
        );
        self.has_timestamp_query = device_probe.has_timestamp_query;
        self.has_multi_draw_indirect = device_probe.has_multi_draw_indirect;
        self.has_pixel_local_storage_coherent = device_probe.has_pixel_local_storage_coherent;
        self.has_pixel_local_storage_non_coherent = device_probe.has_pixel_local_storage_non_coherent;
        try self.captureAdapterLimits();
        try self.captureDeviceLimits();
    }

    pub fn getResourceTableProcs(self: Self) ?p1_resource_table_procs_mod.ResourceTableProcs {
        return self.resource_table_procs;
    }

    pub fn getLifecycleProcs(self: Self) ?p2_lifecycle_procs_mod.LifecycleProcs {
        return self.lifecycle_procs;
    }

    pub fn setUploadBehavior(
        self: *Self,
        usage_mode: UploadBufferUsageMode,
        submit_every: u32,
    ) void {
        self.upload_buffer_usage_mode = usage_mode;
        self.upload_submit_every = if (submit_every == 0) 1 else submit_every;
        self.upload_submit_pending = 0;
    }

    pub fn setQueueWaitMode(self: *Self, wait_mode: QueueWaitMode) void {
        self.queue_wait_mode = wait_mode;
    }

    pub fn setQueueSyncMode(self: *Self, sync_mode: QueueSyncMode) void {
        self.queue_sync_mode = sync_mode;
    }

    pub fn clearUncapturedError(self: *Self) void {
        self.uncaptured_error_state.error_type.store(@intFromEnum(types.WGPUErrorType.noError), .release);
        self.uncaptured_error_state.pending.store(0, .release);
    }

    pub fn takeUncapturedError(self: *Self) ?types.WGPUErrorType {
        if (self.uncaptured_error_state.pending.swap(0, .acq_rel) == 0) return null;
        const raw = self.uncaptured_error_state.error_type.load(.acquire);
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
        if (self.has_device_limits) return &self.device_limits;
        if (self.has_adapter_limits) return &self.adapter_limits;
        return null;
    }

    pub fn syncAfterSubmit(self: *Self) !void {
        if (self.queue_sync_mode == .per_command) {
            try self.waitForQueue();
        }
    }

    pub fn submitEmpty(self: *Self) !u64 {
        return try self.submitInternal(0, null);
    }

    pub fn submitCommandBuffers(self: *Self, command_buffers: []types.WGPUCommandBuffer) !u64 {
        return try self.submitInternal(command_buffers.len, command_buffers.ptr);
    }

    fn submitInternal(
        self: *Self,
        command_count: usize,
        command_ptr: ?[*]types.WGPUCommandBuffer,
    ) !u64 {
        const procs = self.procs orelse return error.ProceduralNotReady;
        const submit_start_ns = std.time.nanoTimestamp();
        procs.wgpuQueueSubmit(self.queue.?, command_count, if (command_count == 0) null else command_ptr.?);
        try self.syncAfterSubmit();
        const submit_end_ns = std.time.nanoTimestamp();
        return if (submit_end_ns > submit_start_ns)
            @as(u64, @intCast(submit_end_ns - submit_start_ns))
        else
            0;
    }

    pub fn flushQueue(self: *Self) !u64 {
        const start = std.time.nanoTimestamp();
        try self.waitForQueue();
        const end = std.time.nanoTimestamp();
        return if (end > start) @as(u64, @intCast(end - start)) else 0;
    }

    pub fn createSurface(
        self: *Self,
        descriptor: surface_procs_mod.SurfaceDescriptor,
    ) !surface_procs_mod.Surface {
        const surface_procs = surface_procs_mod.loadSurfaceProcs(self.dyn_lib) orelse return error.SurfaceProcUnavailable;
        const surface = surface_procs.instance_create_surface(self.instance.?, &descriptor);
        if (surface == null) return error.SurfaceCreationFailed;
        return surface;
    }

    pub fn getSurfaceCapabilities(
        self: *Self,
        surface: surface_procs_mod.Surface,
    ) !surface_procs_mod.SurfaceCapabilities {
        const surface_procs = surface_procs_mod.loadSurfaceProcs(self.dyn_lib) orelse return error.SurfaceProcUnavailable;
        var capabilities = surface_procs_mod.SurfaceCapabilities{
            .nextInChain = null,
            .usages = types.WGPUTextureUsage_None,
            .formatCount = 0,
            .formats = null,
            .presentModeCount = 0,
            .presentModes = null,
            .alphaModeCount = 0,
            .alphaModes = null,
        };
        const status = surface_procs.surface_get_capabilities(surface, self.adapter.?, &capabilities);
        if (status != types.WGPUStatus_Success) return error.SurfaceCapabilitiesFailed;
        return capabilities;
    }

    pub fn freeSurfaceCapabilities(
        self: *Self,
        capabilities: surface_procs_mod.SurfaceCapabilities,
    ) void {
        if (surface_procs_mod.loadSurfaceProcs(self.dyn_lib)) |surface_procs| {
            surface_procs.surface_capabilities_free_members(capabilities);
        }
    }

    pub fn configureSurface(
        self: *Self,
        surface: surface_procs_mod.Surface,
        config: surface_procs_mod.SurfaceConfiguration,
    ) !void {
        const surface_procs = surface_procs_mod.loadSurfaceProcs(self.dyn_lib) orelse return error.SurfaceProcUnavailable;
        surface_procs.surface_configure(surface, &config);
    }

    pub fn getCurrentSurfaceTexture(
        self: *Self,
        surface: surface_procs_mod.Surface,
    ) !surface_procs_mod.SurfaceTexture {
        const surface_procs = surface_procs_mod.loadSurfaceProcs(self.dyn_lib) orelse return error.SurfaceProcUnavailable;
        var surface_texture = surface_procs_mod.SurfaceTexture{
            .nextInChain = null,
            .texture = null,
            .status = 0,
        };
        surface_procs.surface_get_current_texture(surface, &surface_texture);
        return surface_texture;
    }

    pub fn presentSurface(self: *Self, surface: surface_procs_mod.Surface) !void {
        const surface_procs = surface_procs_mod.loadSurfaceProcs(self.dyn_lib) orelse return error.SurfaceProcUnavailable;
        const status = surface_procs.surface_present(surface);
        if (status != types.WGPUStatus_Success) return error.SurfacePresentFailed;
    }

    pub fn unconfigureSurface(self: *Self, surface: surface_procs_mod.Surface) !void {
        const surface_procs = surface_procs_mod.loadSurfaceProcs(self.dyn_lib) orelse return error.SurfaceProcUnavailable;
        surface_procs.surface_unconfigure(surface);
    }

    pub fn releaseSurface(self: *Self, surface: surface_procs_mod.Surface) void {
        if (surface_procs_mod.loadSurfaceProcs(self.dyn_lib)) |surface_procs| {
            surface_procs.surface_release(surface);
        }
    }

    pub fn prewarmUploadPath(self: *Self, max_upload_bytes: u64) !void {
        if (max_upload_bytes == 0) return;
        if (!self.backendAvailable()) return error.NativeQueueUnavailable;

        const usage = switch (self.upload_buffer_usage_mode) {
            .copy_dst_copy_src => types.WGPUBufferUsage_CopyDst | types.WGPUBufferUsage_CopySrc,
            .copy_dst => types.WGPUBufferUsage_CopyDst,
        };
        _ = try resources.getOrCreateBuffer(self, loader.BUFFER_UPLOAD_KEY, max_upload_bytes, usage);

        const bytes_usize = std.math.cast(usize, max_upload_bytes) orelse {
            return error.BufferAllocationFailed;
        };
        if (bytes_usize <= self.upload_scratch.len) return;

        if (self.upload_scratch.len > 0) {
            self.allocator.free(self.upload_scratch);
        }
        self.upload_scratch = try self.allocator.alloc(u8, bytes_usize);
        @memset(self.upload_scratch, 0);
    }

    pub fn waitForQueue(self: *Self) !void {
        var attempt: u32 = 0;
        while (attempt < QUEUE_SYNC_RETRY_LIMIT) : (attempt += 1) {
            if (self.waitForQueueOnce()) |_| {
                return;
            } else |err| {
                if (attempt + 1 < QUEUE_SYNC_RETRY_LIMIT and shouldRetryQueueWait(err)) {
                    std.Thread.sleep(QUEUE_SYNC_RETRY_BACKOFF_NS);
                    continue;
                }
                return err;
            }
        }
        return error.QueueSubmitTimeout;
    }

    fn waitForQueueOnce(self: *Self) !void {
        switch (self.queue_wait_mode) {
            .process_events => try self.waitForQueueProcessEvents(),
            .wait_any => try self.waitForQueueWaitAny(),
        }
    }

    fn shouldRetryQueueWait(err: anyerror) bool {
        return switch (err) {
            error.WaitTimedOut,
            error.QueueSubmitTimeout,
            error.WaitAnyIncomplete,
            => true,
            else => false,
        };
    }

    fn waitForQueueProcessEvents(self: *Self) !void {
        if (self.procs == null) return error.ProceduralNotReady;

        var done_state = types.QueueSubmitState{};

        const queue_done_callback_info = types.WGPUQueueWorkDoneCallbackInfo{
            .nextInChain = null,
            .mode = types.WGPUCallbackMode_AllowProcessEvents,
            .callback = loader.queueWorkDoneCallback,
            .userdata1 = &done_state,
            .userdata2 = null,
        };
        const queue_done_future = self.procs.?.wgpuQueueOnSubmittedWorkDone(
            self.queue.?,
            queue_done_callback_info,
        );
        if (queue_done_future.id == 0) return error.QueueFutureUnavailable;
        try self.processEventsUntil(&done_state.done, loader.QUEUE_WAIT_TIMEOUT_NS);
        if (!done_state.done) return error.QueueSubmitTimeout;
        if (done_state.status == .@"error") {
            return error.QueueSubmissionError;
        }
    }

    fn waitForQueueWaitAny(self: *Self) !void {
        const procs = self.procs orelse return error.ProceduralNotReady;

        var done_state = types.QueueSubmitState{};
        const queue_done_callback_info = types.WGPUQueueWorkDoneCallbackInfo{
            .nextInChain = null,
            .mode = types.WGPUCallbackMode_WaitAnyOnly,
            .callback = loader.queueWorkDoneCallback,
            .userdata1 = &done_state,
            .userdata2 = null,
        };
        const queue_done_future = procs.wgpuQueueOnSubmittedWorkDone(
            self.queue.?,
            queue_done_callback_info,
        );
        if (queue_done_future.id == 0) return error.QueueFutureUnavailable;

        var wait_infos = [_]types.WGPUFutureWaitInfo{
            .{
                .future = queue_done_future,
                .completed = types.WGPU_FALSE,
            },
        };
        const wait_status = procs.wgpuInstanceWaitAny(
            self.instance.?,
            wait_infos.len,
            wait_infos[0..].ptr,
            loader.QUEUE_WAIT_TIMEOUT_NS,
        );
        switch (wait_status) {
            .success => {},
            .timedOut => return error.WaitTimedOut,
            .@"error" => return error.WaitAnyFailed,
            else => return error.WaitAnyUnsupported,
        }

        if (!done_state.done) {
            try self.processEventsUntil(&done_state.done, loader.DEFAULT_WAIT_SLICE_NS);
        }
        if (!done_state.done) return error.WaitAnyIncomplete;
        if (done_state.status == .@"error") {
            return error.QueueSubmissionError;
        }
    }

    pub fn readTimestampBuffer(self: *Self, readback_buffer: types.WGPUBuffer) !u64 {
        const procs = self.procs orelse return error.ProceduralNotReady;
        var attempt: u32 = 0;
        while (attempt < TIMESTAMP_MAP_RETRY_LIMIT) : (attempt += 1) {
            if (self.readTimestampBufferOnce(procs, readback_buffer)) |delta| {
                return delta;
            } else |err| {
                if (attempt + 1 < TIMESTAMP_MAP_RETRY_LIMIT and shouldRetryTimestampMap(err)) {
                    self.timestampLog(
                        "timestamp_readback_retry attempt={} error={s}\n",
                        .{ attempt + 1, @errorName(err) },
                    );
                    std.Thread.sleep(TIMESTAMP_MAP_RETRY_BACKOFF_NS);
                    continue;
                }
                return err;
            }
        }
        return error.BufferMapFailed;
    }

    fn readTimestampBufferOnce(
        self: *Self,
        procs: types.Procs,
        readback_buffer: types.WGPUBuffer,
    ) !u64 {
        var map_state = types.BufferMapState{};
        const map_callback_info = types.WGPUBufferMapCallbackInfo{
            .nextInChain = null,
            .mode = types.WGPUCallbackMode_AllowProcessEvents,
            .callback = loader.bufferMapCallback,
            .userdata1 = &map_state,
            .userdata2 = null,
        };
        const map_future = procs.wgpuBufferMapAsync(
            readback_buffer,
            types.WGPUMapMode_Read,
            0,
            types.TIMESTAMP_BUFFER_SIZE,
            map_callback_info,
        );
        if (map_future.id == 0) {
            self.timestampLog("map_async_future_id=0\n", .{});
            return error.BufferMapFailed;
        }
        try self.processEventsUntil(&map_state.done, loader.DEFAULT_TIMEOUT_NS);
        if (!map_state.done) {
            self.timestampLog("map_async_timeout\n", .{});
            return error.BufferMapTimeout;
        }
        if (map_state.status != types.WGPUMapAsyncStatus_Success) {
            self.timestampLog("map_async_status={}\n", .{map_state.status});
            return error.BufferMapFailed;
        }

        const mapped_ptr = procs.wgpuBufferGetConstMappedRange(readback_buffer, 0, types.TIMESTAMP_BUFFER_SIZE);
        if (mapped_ptr == null) {
            self.timestampLog("mapped_range=null\n", .{});
            return error.BufferMapFailed;
        }
        const timestamps = @as(*const [2]u64, @ptrCast(@alignCast(mapped_ptr)));
        const begin_ts = timestamps[0];
        const end_ts = timestamps[1];
        procs.wgpuBufferUnmap(readback_buffer);
        if (end_ts < begin_ts) {
            self.timestampLog("mapped_invalid_range begin={} end={}\n", .{ begin_ts, end_ts });
            return error.TimestampRangeInvalid;
        }
        const delta = end_ts - begin_ts;
        self.timestampLog("mapped_begin={} mapped_end={} mapped_delta={}\n", .{ begin_ts, end_ts, delta });
        return delta;
    }

    fn shouldRetryTimestampMap(err: anyerror) bool {
        return switch (err) {
            error.BufferMapTimeout,
            error.BufferMapFailed,
            => true,
            else => false,
        };
    }

    fn processEventsUntil(self: *Self, done: *const bool, timeout_ns: u64) !void {
        const start = std.time.nanoTimestamp();
        var spins: u32 = 0;
        while (!done.*) {
            self.procs.?.wgpuInstanceProcessEvents(self.instance.?);
            const elapsed = std.time.nanoTimestamp() - start;
            if (elapsed >= timeout_ns) return error.WaitTimedOut;
            spins += 1;
            if (spins > 1000) {
                std.Thread.sleep(1_000);
            }
        }
    }

    fn captureAdapterLimits(self: *Self) !void {
        self.has_adapter_limits = false;
        self.adapter_limits = types.initLimits();
        const cap = self.capability_procs orelse return;
        const get_limits = cap.adapter_get_limits orelse return;
        if (self.adapter == null) return;
        if (get_limits(self.adapter.?, &self.adapter_limits) != types.WGPUStatus_Success) {
            return error.AdapterLimitsQueryFailed;
        }
        self.has_adapter_limits = true;
    }

    fn captureDeviceLimits(self: *Self) !void {
        self.has_device_limits = false;
        self.device_limits = types.initLimits();
        const cap = self.capability_procs orelse return;
        const get_limits = cap.device_get_limits orelse return;
        if (self.device == null) return;
        if (get_limits(self.device.?, &self.device_limits) != types.WGPUStatus_Success) {
            return error.DeviceLimitsQueryFailed;
        }
        self.has_device_limits = true;
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
            .backendType = self.requested_backend_type,
            .compatibleSurface = null,
        };
        self.timestampLog("request_adapter backend_type={}\n", .{@intFromEnum(self.requested_backend_type)});

        const adapter_request_info = request_info;
        const future = self.procs.?.wgpuInstanceRequestAdapter(
            self.instance.?,
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
        const has_resource_table_feature = self.procs.?.wgpuAdapterHasFeature(self.adapter.?, types.WGPUFeatureName_ChromiumExperimentalSamplingResourceTable) != types.WGPU_FALSE;
        if (self.has_timestamp_query) {
            required_features[feature_count] = types.WGPUFeatureName_TimestampQuery;
            feature_count += 1;
        }
        if (self.has_timestamp_inside_passes) {
            required_features[feature_count] = types.WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses;
            feature_count += 1;
        }
        if (self.has_multi_draw_indirect) {
            required_features[feature_count] = types.WGPUFeatureName_MultiDrawIndirect;
            feature_count += 1;
        }
        if (self.has_pixel_local_storage_coherent) { required_features[feature_count] = types.WGPUFeatureName_PixelLocalStorageCoherent; feature_count += 1; }
        if (self.has_pixel_local_storage_non_coherent) { required_features[feature_count] = types.WGPUFeatureName_PixelLocalStorageNonCoherent; feature_count += 1; }
        if (has_resource_table_feature) { required_features[feature_count] = types.WGPUFeatureName_ChromiumExperimentalSamplingResourceTable; feature_count += 1; }
        self.timestampLog("request_device required_features timestamp={} inside_passes={} multi_draw={} pls_coherent={} pls_noncoherent={} resource_table={} count={} adapter_limits={} max_storage_binding={} max_uniform_binding={} max_buffer={}\n", .{
            self.has_timestamp_query,
            self.has_timestamp_inside_passes,
            self.has_multi_draw_indirect,
            self.has_pixel_local_storage_coherent,
            self.has_pixel_local_storage_non_coherent,
            has_resource_table_feature,
            feature_count,
            self.has_adapter_limits,
            self.adapter_limits.maxStorageBufferBindingSize,
            self.adapter_limits.maxUniformBufferBindingSize,
            self.adapter_limits.maxBufferSize,
        });
        const device_desc = types.WGPUDeviceDescriptor{
            .nextInChain = null,
            .label = loader.emptyStringView(),
            .requiredFeatureCount = feature_count,
            .requiredFeatures = if (feature_count > 0) required_features[0..].ptr else null,
            .requiredLimits = if (self.has_adapter_limits) &self.adapter_limits else null,
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
                .userdata1 = &self.uncaptured_error_state,
                .userdata2 = null,
            },
        };
        const device_request_info = request_info;
        const future = self.procs.?.wgpuAdapterRequestDevice(self.adapter.?, &device_desc, device_request_info);
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
        if (!self.timestamp_debug) return;
        std.debug.print("[fawn-timestamp] " ++ fmt, args);
    }
};
