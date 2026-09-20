const std = @import("std");
const builtin = @import("builtin");
const bridge = @import("metal_bridge_decls.zig");
const metal_buffer_pool = @import("metal_buffer_pool.zig");
const metal_pipeline_cache = @import("metal_pipeline_cache.zig");
const msl_translation = @import("../../compiler/wgsl/pipeline/translate_msl.zig");
const emit_msl_maps = @import("../../compiler/wgsl/emit/msl/emit_msl_maps.zig");
const wgsl_runtime_compile = @import("../../compiler/wgsl/runtime/runtime_compute_translation.zig");
const HAS_PIPELINE_CACHE = builtin.os.tag == .macos;

const metal_bridge_cmd_buf_render_encoder = bridge.metal_bridge_cmd_buf_render_encoder;
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_device_new_compute_pipeline = bridge.metal_bridge_device_new_compute_pipeline;
const metal_bridge_device_new_icb = bridge.metal_bridge_device_new_icb;
const metal_bridge_device_new_library_msl = bridge.metal_bridge_device_new_library_msl;
const metal_bridge_device_new_render_pipeline = bridge.metal_bridge_device_new_render_pipeline;
const metal_bridge_device_new_render_target = bridge.metal_bridge_device_new_render_target;
const metal_bridge_end_blit_encoding = bridge.metal_bridge_end_blit_encoding;
const metal_bridge_icb_encode_draws = bridge.metal_bridge_icb_encode_draws;
const metal_bridge_library_new_function = bridge.metal_bridge_library_new_function;
const metal_bridge_release = bridge.metal_bridge_release;

const DEFAULT_KERNEL_ROOT: []const u8 = "bench/kernels";
const DEFAULT_COMPUTE_ENTRY_POINT: []const u8 = "main";
const PIPELINE_KEY_SEPARATOR: []const u8 = "#";
const BRIDGE_ERROR_CAP: usize = 512;
const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;
const MAX_PIPELINE_KEY_BYTES: usize = 512;
const SINGLE_THREADGROUP_ANNOTATION = "[[max_total_threads_per_threadgroup(1)]]";

const PipelineRequest = struct {
    base: []const u8,
    requested_entry_point: []const u8,
    cache_key: []const u8,
};

fn normalizeComputeEntryPoint(entry_point: ?[]const u8) []const u8 {
    if (entry_point) |value| {
        if (value.len != 0) return value;
    }
    return DEFAULT_COMPUTE_ENTRY_POINT;
}

fn appendPipelineCacheKey(
    base: []const u8,
    requested_entry_point: []const u8,
    key_buf: []u8,
) ![]const u8 {
    if (std.mem.eql(u8, requested_entry_point, DEFAULT_COMPUTE_ENTRY_POINT)) return base;
    return std.fmt.bufPrint(key_buf, "{s}{s}{s}", .{ base, PIPELINE_KEY_SEPARATOR, requested_entry_point });
}

fn parsePipelineRequest(
    kernel: []const u8,
    entry_point: ?[]const u8,
    key_buf: []u8,
) !PipelineRequest {
    if (entry_point) |requested| {
        const base = metal_buffer_pool.strip_extension(kernel);
        const normalized = normalizeComputeEntryPoint(requested);
        return .{
            .base = base,
            .requested_entry_point = normalized,
            .cache_key = try appendPipelineCacheKey(base, normalized, key_buf),
        };
    }

    if (std.mem.indexOf(u8, kernel, PIPELINE_KEY_SEPARATOR)) |separator_index| {
        const requested = normalizeComputeEntryPoint(kernel[separator_index + PIPELINE_KEY_SEPARATOR.len ..]);
        return .{
            .base = kernel[0..separator_index],
            .requested_entry_point = requested,
            .cache_key = kernel,
        };
    }

    const base = metal_buffer_pool.strip_extension(kernel);
    return .{
        .base = base,
        .requested_entry_point = DEFAULT_COMPUTE_ENTRY_POINT,
        .cache_key = base,
    };
}

fn resolveMslComputeFunctionName(requested_entry_point: []const u8) []const u8 {
    return emit_msl_maps.msl_function_name(requested_entry_point, .compute);
}

fn workgroupSizeForRawMetalSource(source: []const u8) [3]u32 {
    if (std.mem.indexOf(u8, source, SINGLE_THREADGROUP_ANNOTATION) != null) {
        return .{ 1, 1, 1 };
    }
    return .{ 0, 0, 0 };
}

const CompiledKernelLibrary = struct {
    library: ?*anyopaque,
    workgroup_size: [3]u32 = .{ 0, 0, 0 },
};

pub const KernelPipelineInfo = struct {
    pipeline: ?*anyopaque,
    workgroup_size: [3]u32,
};

pub fn ensure_kernel_pipeline_info(
    self: anytype,
    pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache,
    kernel: []const u8,
    entry_point: ?[]const u8,
) !KernelPipelineInfo {
    var key_buf: [MAX_PIPELINE_KEY_BYTES]u8 = undefined;
    const request = try parsePipelineRequest(kernel, entry_point, &key_buf);
    if (self.kernel_pipelines.get(request.cache_key)) |kp| {
        return .{
            .pipeline = kp.pipeline,
            .workgroup_size = kp.workgroup_size,
        };
    }

    const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
    var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
    const compiled = try compile_kernel_library(self, root, request.base, &err_buf);
    errdefer metal_bridge_release(compiled.library);

    const function_name = resolveMslComputeFunctionName(request.requested_entry_point);
    const function_name_z = try self.allocator.dupeZ(u8, function_name);
    defer self.allocator.free(function_name_z);

    const func = metal_bridge_library_new_function(compiled.library, function_name_z.ptr) orelse return error.ShaderCompileFailed;
    defer metal_bridge_release(func);

    const pso = try resolve_compute_pso_for(self.device, pipeline_cache, func, &err_buf);
    errdefer metal_bridge_release(pso);

    const key = try self.allocator.dupe(u8, request.cache_key);
    errdefer self.allocator.free(key);
    try self.kernel_pipelines.put(self.allocator, key, .{
        .library = compiled.library,
        .pipeline = pso,
        .workgroup_size = compiled.workgroup_size,
    });

    if (builtin.os.tag == .macos and HAS_PIPELINE_CACHE) {
        if (pipeline_cache) |cache| {
            cache.register_compute_key(request.cache_key);
        }
    }

    return .{
        .pipeline = pso,
        .workgroup_size = compiled.workgroup_size,
    };
}

pub fn ensure_kernel_pipeline(
    self: anytype,
    pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache,
    kernel: []const u8,
    entry_point: ?[]const u8,
) !?*anyopaque {
    const info = try ensure_kernel_pipeline_info(self, pipeline_cache, kernel, entry_point);
    return info.pipeline;
}

pub fn get_kernel_workgroup_size(self: anytype, kernel: []const u8, entry_point: ?[]const u8) ![3]u32 {
    var key_buf: [MAX_PIPELINE_KEY_BYTES]u8 = undefined;
    const request = try parsePipelineRequest(kernel, entry_point, &key_buf);
    if (self.kernel_pipelines.get(request.cache_key)) |kp| return kp.workgroup_size;
    return .{ 0, 0, 0 };
}

fn compile_kernel_library(
    self: anytype,
    root: []const u8,
    base: []const u8,
    err_buf: *[BRIDGE_ERROR_CAP]u8,
) !CompiledKernelLibrary {
    const metal_path = try std.fmt.allocPrint(self.allocator, "{s}/{s}.metal", .{ root, base });
    defer self.allocator.free(metal_path);

    const metal_source = std.fs.cwd().readFileAlloc(self.allocator, metal_path, MAX_KERNEL_SOURCE_BYTES) catch |err| switch (err) {
        error.FileNotFound => null,
        else => return error.ShaderCompileFailed,
    };
    if (metal_source) |source| {
        defer self.allocator.free(source);
        const library = metal_bridge_device_new_library_msl(
            self.device,
            source.ptr,
            source.len,
            err_buf,
            BRIDGE_ERROR_CAP,
        ) orelse return error.ShaderCompileFailed;
        return .{
            .library = library,
            .workgroup_size = workgroupSizeForRawMetalSource(source),
        };
    }

    const wgsl_path = try std.fmt.allocPrint(self.allocator, "{s}/{s}.wgsl", .{ root, base });
    defer self.allocator.free(wgsl_path);

    const wgsl_source = std.fs.cwd().readFileAlloc(self.allocator, wgsl_path, MAX_KERNEL_SOURCE_BYTES) catch {
        return error.ShaderCompileFailed;
    };
    defer self.allocator.free(wgsl_source);

    const msl_buf = try self.allocator.alloc(u8, msl_translation.MAX_OUTPUT);
    defer self.allocator.free(msl_buf);

    const translated_len = blk: {
        var translation = wgsl_runtime_compile.translateToMslForComputeRuntime(
            self.allocator,
            wgsl_source,
            msl_buf,
            null,
            0,
        ) catch {
            break :blk msl_translation.translateToMsl(self.allocator, wgsl_source, msl_buf) catch {
                return error.ShaderCompileFailed;
            };
        };
        const workgroup_size = translation.info.workgroup_size;
        defer translation.info.deinit(self.allocator);
        const library = metal_bridge_device_new_library_msl(
            self.device,
            msl_buf.ptr,
            translation.len,
            err_buf,
            BRIDGE_ERROR_CAP,
        ) orelse return error.ShaderCompileFailed;
        return .{
            .library = library,
            .workgroup_size = workgroup_size,
        };
    };

    const library = metal_bridge_device_new_library_msl(
        self.device,
        msl_buf.ptr,
        translated_len,
        err_buf,
        BRIDGE_ERROR_CAP,
    ) orelse return error.ShaderCompileFailed;
    return .{
        .library = library,
        .workgroup_size = .{ 0, 0, 0 },
    };
}

fn zeroBufferBytes(bytes: []u8) void {
    @memset(bytes, 0);
}

pub fn ensure_compute_buffer(self: anytype, handle: u64, size: u64, initialize_buffers_on_create: bool) !?*anyopaque {
    return ensureComputeBufferWithBridge(self, handle, size, initialize_buffers_on_create, bridge);
}

fn ensureComputeBufferWithBridge(self: anytype, handle: u64, size: u64, initialize: bool, comptime native: type) !?*anyopaque {
    if (size == 0) return error.InvalidArgument;
    const length = std.math.cast(usize, size) orelse return error.InvalidArgument;
    if (self.compute_buffers.get(handle)) |buffer| {
        if (native.metal_bridge_buffer_length(buffer) < length) return error.InvalidArgument;
        return buffer;
    }
    const buffer = native.metal_bridge_device_new_buffer_shared(self.device, length) orelse return error.InvalidState;
    errdefer native.metal_bridge_release(buffer);
    if (initialize) {
        const mapped = native.metal_bridge_buffer_contents(buffer) orelse return error.InvalidState;
        zeroBufferBytes(mapped[0..length]);
    }
    try self.compute_buffers.put(self.allocator, handle, buffer);
    return buffer;
}

pub fn requiredWriteSize(offset: u64, size: u64, length: usize) !u64 {
    const end = std.math.add(u64, offset, length) catch return error.InvalidArgument;
    return @max(size, end);
}

pub fn write_compute_buffer_words(self: anytype, handle: u64, offset: u64, buffer_size: u64, data: []const u32) !void {
    if (data.len == 0) return error.InvalidArgument;
    const data_bytes = std.mem.sliceAsBytes(data);
    return write_compute_buffer_bytes(self, handle, offset, buffer_size, data_bytes);
}

pub fn write_compute_buffer_bytes(self: anytype, handle: u64, offset: u64, buffer_size: u64, data_bytes: []const u8) !void {
    if (data_bytes.len == 0) return error.InvalidArgument;
    const required_size = try requiredWriteSize(offset, buffer_size, data_bytes.len);
    const buffer = try ensure_compute_buffer(self, handle, required_size, false);
    _ = try self.flush_queue();
    const mapped = metal_bridge_buffer_contents(buffer) orelse return error.InvalidState;
    const dst = @as([*]u8, @ptrCast(mapped));
    @memcpy(dst[@intCast(offset)..][0..data_bytes.len], data_bytes);
}

test "zeroBufferBytes clears mapped storage" {
    var bytes = [_]u8{ 1, 2, 3, 4, 5, 6, 7, 8 };
    zeroBufferBytes(bytes[0..]);
    for (bytes) |value| {
        try std.testing.expectEqual(@as(u8, 0), value);
    }
}

test "parsePipelineRequest keeps default entrypoint on base key" {
    var key_buf: [MAX_PIPELINE_KEY_BYTES]u8 = undefined;
    const request = try parsePipelineRequest("rmsnorm.wgsl", null, &key_buf);
    try std.testing.expectEqualStrings("rmsnorm", request.base);
    try std.testing.expectEqualStrings("main", request.requested_entry_point);
    try std.testing.expectEqualStrings("rmsnorm", request.cache_key);
}

test "parsePipelineRequest keys non-default compute entrypoints separately" {
    var key_buf: [MAX_PIPELINE_KEY_BYTES]u8 = undefined;
    const request = try parsePipelineRequest("matmul_gemv_subgroup.wgsl", "main_vec4", &key_buf);
    try std.testing.expectEqualStrings("matmul_gemv_subgroup", request.base);
    try std.testing.expectEqualStrings("main_vec4", request.requested_entry_point);
    try std.testing.expectEqualStrings("matmul_gemv_subgroup#main_vec4", request.cache_key);
}

test "resolveMslComputeFunctionName maps main to main_kernel" {
    try std.testing.expectEqualStrings("main_kernel", resolveMslComputeFunctionName("main"));
    try std.testing.expectEqualStrings("main_vec4", resolveMslComputeFunctionName("main_vec4"));
}

test "workgroupSizeForRawMetalSource preserves explicit single-threadgroup kernels" {
    try std.testing.expectEqualDeep(
        @as([3]u32, .{ 1, 1, 1 }),
        workgroupSizeForRawMetalSource(
            \\[[max_total_threads_per_threadgroup(1)]]
            \\kernel void main_kernel(device uint* data [[buffer(0)]]) {}
        ),
    );
    try std.testing.expectEqualDeep(
        @as([3]u32, .{ 0, 0, 0 }),
        workgroupSizeForRawMetalSource(
            \\[[max_total_threads_per_threadgroup(64)]]
            \\kernel void main_kernel(uint gid [[thread_position_in_grid]]) {}
        ),
    );
}

test "get_kernel_workgroup_size returns cached metadata for normalized default entrypoint" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    const FakePipeline = struct {
        library: ?*anyopaque,
        pipeline: ?*anyopaque,
        workgroup_size: [3]u32,
    };
    const FakeRuntime = struct {
        kernel_pipelines: std.StringHashMapUnmanaged(FakePipeline) = .{},
    };

    var fake = FakeRuntime{};
    const key = try alloc.dupe(u8, "matmul_f16w_f32a_tiled");
    try fake.kernel_pipelines.put(alloc, key, .{
        .library = null,
        .pipeline = null,
        .workgroup_size = .{ 16, 16, 1 },
    });

    const wg = try get_kernel_workgroup_size(&fake, "matmul_f16w_f32a_tiled.wgsl", "main");
    try std.testing.expectEqual(@as(u32, 16), wg[0]);
    try std.testing.expectEqual(@as(u32, 16), wg[1]);
    try std.testing.expectEqual(@as(u32, 1), wg[2]);
}

pub fn ensure_render_pipeline(
    self: anytype,
    pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache,
    fmt: u32,
) !void {
    if (self.render_pipeline != null and self.render_pipeline_format == fmt) return;
    _ = try self.flush_queue();
    var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
    const replacement = try resolve_render_pso_for(self.device, pipeline_cache, fmt, &err_buf);
    if (self.render_pipeline) |pipeline| metal_bridge_release(pipeline);
    if (self.cached_icb) |icb| {
        metal_bridge_release(icb);
        self.cached_icb = null;
    }
    self.render_pipeline = replacement;
    self.render_pipeline_format = fmt;
}

pub fn ensure_render_target(self: anytype, width: u32, height: u32, fmt: u32) !void {
    if (self.render_target != null and
        self.render_target_width == width and
        self.render_target_height == height and
        self.render_target_format == fmt) return;
    _ = try self.flush_queue();
    const replacement = metal_bridge_device_new_render_target(self.device, width, height, fmt) orelse return error.InvalidState;
    if (self.render_target) |target| metal_bridge_release(target);
    self.render_target = replacement;
    self.render_target_width = width;
    self.render_target_height = height;
    self.render_target_format = fmt;
}

pub fn ensure_streaming_render_encoder(self: anytype) !void {
    if (self.streaming_render_encoder != null) return;

    if (self.streaming_compute_encoder) |encoder| {
        bridge.metal_bridge_end_compute_encoding(encoder);
        self.streaming_compute_encoder = null;
    }
    if (self.streaming_blit_encoder) |encoder| {
        metal_bridge_end_blit_encoding(encoder);
        self.streaming_blit_encoder = null;
    }

    if (self.streaming_cmd_buf == null) {
        self.streaming_cmd_buf = bridge.metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
    }

    const render_pass_ops = bridge.MetalRenderPassOps{
        .color_load_op = 0x00000002,
        .color_store_op = 0x00000001,
        .depth_load_op = 0,
        .depth_store_op = 0,
        .stencil_load_op = 0,
        .stencil_store_op = 0,
        .depth_read_only = 0,
        .stencil_read_only = 0,
        .clear_r = 0,
        .clear_g = 0,
        .clear_b = 0,
        .clear_a = 0,
        .depth_clear_value = 1,
        .stencil_clear_value = 0,
    };
    self.streaming_render_encoder = metal_bridge_cmd_buf_render_encoder(
        self.streaming_cmd_buf,
        self.render_pipeline,
        self.render_target,
        null,
        null,
        &render_pass_ops,
    ) orelse return error.InvalidState;
    self.streaming_has_render = true;
}

pub fn ensure_icb(self: anytype, draw_count: u32, vertex_count: u32, instance_count: u32, redundant_pl: c_int) !?*anyopaque {
    const key = @TypeOf(self.cached_icb_key){
        .draw_count = draw_count,
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .redundant = redundant_pl != 0,
    };
    if (self.cached_icb != null and std.meta.eql(self.cached_icb_key, key)) return self.cached_icb;
    _ = try self.flush_queue();
    const icb = metal_bridge_device_new_icb(self.device, self.render_pipeline, draw_count, redundant_pl) orelse return error.InvalidState;
    metal_bridge_icb_encode_draws(icb, self.render_pipeline, draw_count, vertex_count, instance_count, redundant_pl);
    if (self.cached_icb) |previous| metal_bridge_release(previous);
    self.cached_icb = icb;
    self.cached_icb_key = key;
    return icb;
}

// Resolve compute PSO: try archive (compile-or-serve), fall back to plain compile.
// Phase 2: on archive hit, the ObjC bridge returns a pre-compiled binary without
// calling newLibraryWithSource.  On miss, it compiles and primes the archive.
fn resolve_compute_pso_for(
    device: ?*anyopaque,
    pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache,
    func: ?*anyopaque,
    err_buf: *[BRIDGE_ERROR_CAP]u8,
) !?*anyopaque {
    if (builtin.os.tag == .macos and HAS_PIPELINE_CACHE) {
        if (pipeline_cache) |cache| {
            if (cache.compile_or_serve_compute(func)) |pso| return pso;
        }
    }
    return metal_bridge_device_new_compute_pipeline(device, func, err_buf, BRIDGE_ERROR_CAP) orelse error.ShaderCompileFailed;
}

// Resolve render PSO: try archive (compile-or-serve), fall back to plain compile.
fn resolve_render_pso_for(
    device: ?*anyopaque,
    pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache,
    fmt: u32,
    err_buf: *[BRIDGE_ERROR_CAP]u8,
) !?*anyopaque {
    if (builtin.os.tag == .macos and HAS_PIPELINE_CACHE) {
        if (pipeline_cache) |cache| {
            if (cache.compile_or_serve_render(fmt, 1)) |pso| return pso;
        }
    }
    return metal_bridge_device_new_render_pipeline(device, fmt, 1, err_buf, BRIDGE_ERROR_CAP) orelse error.ShaderCompileFailed;
}

test "compute buffer publication releases failed allocations and rejects growing an existing handle" {
    const Probe = struct {
        var bytes: [8]u8 = @splat(9);
        var releases: usize = 0;
        var fail_mapping = false;
        fn metal_bridge_buffer_length(_: ?*anyopaque) usize {
            return bytes.len;
        }
        fn metal_bridge_device_new_buffer_shared(_: ?*anyopaque, _: usize) ?*anyopaque {
            return &bytes;
        }
        fn metal_bridge_buffer_contents(_: ?*anyopaque) ?[*]u8 {
            return if (fail_mapping) null else &bytes;
        }
        fn metal_bridge_release(_: ?*anyopaque) void {
            releases += 1;
        }
    };
    const Owner = struct {
        allocator: std.mem.Allocator,
        device: ?*anyopaque = null,
        compute_buffers: std.AutoHashMapUnmanaged(u64, ?*anyopaque) = .{},
    };
    Probe.releases = 0;
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    var failed: Owner = .{ .allocator = failing.allocator() };
    try std.testing.expectError(error.OutOfMemory, ensureComputeBufferWithBridge(&failed, 1, 8, true, Probe));
    try std.testing.expectEqual(@as(usize, 1), Probe.releases);
    try std.testing.expectEqual(@as(u32, 0), failed.compute_buffers.count());
    var owner: Owner = .{ .allocator = std.testing.allocator };
    defer owner.compute_buffers.deinit(owner.allocator);
    Probe.fail_mapping = true;
    try std.testing.expectError(error.InvalidState, ensureComputeBufferWithBridge(&owner, 1, 8, true, Probe));
    Probe.fail_mapping = false;
    try std.testing.expectEqual(@as(usize, 2), Probe.releases);
    _ = try ensureComputeBufferWithBridge(&owner, 1, 8, true, Probe);
    try std.testing.expectEqualSlices(u8, &(@as([8]u8, @splat(0))), &Probe.bytes);
    try std.testing.expectError(error.InvalidArgument, ensureComputeBufferWithBridge(&owner, 1, 9, false, Probe));
    try std.testing.expectError(error.InvalidArgument, requiredWriteSize(std.math.maxInt(u64), 0, 1));
    try std.testing.expectEqual(@as(u64, 12), try requiredWriteSize(4, 12, 3));
}
