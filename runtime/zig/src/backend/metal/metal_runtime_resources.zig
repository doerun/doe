const builtin = @import("builtin");
const std = @import("std");
const bridge = @import("metal_bridge_decls.zig");
const metal_buffer_pool = @import("metal_buffer_pool.zig");
const metal_pipeline_cache = @import("metal_pipeline_cache.zig");
const wgsl_compiler = @import("../../doe_wgsl/mod.zig");
const wgsl_runtime_compile = @import("../../doe_wgsl/runtime_compile.zig");
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
const KERNEL_ENTRY_Z: [*:0]const u8 = "main_kernel";
const BRIDGE_ERROR_CAP: usize = 512;
const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;

pub fn ensure_kernel_pipeline(self: anytype, kernel: []const u8) !?*anyopaque {
    const base = metal_buffer_pool.strip_extension(kernel);
    if (self.kernel_pipelines.get(base)) |kp| return kp.pipeline;

    const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
    var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
    const lib = try compile_kernel_library(self, root, base, &err_buf);
    errdefer metal_bridge_release(lib);

    const func = metal_bridge_library_new_function(lib, KERNEL_ENTRY_Z) orelse return error.ShaderCompileFailed;
    errdefer metal_bridge_release(func);

    const pso = try resolve_compute_pso_for(self, func, &err_buf);
    metal_bridge_release(func);

    const key = try self.allocator.dupe(u8, base);
    errdefer self.allocator.free(key);
    try self.kernel_pipelines.put(self.allocator, key, .{ .library = lib, .pipeline = pso });

    // Register kernel name in the pipeline cache warmup manifest so
    // future sessions can pre-compile it on startup.
    if (builtin.os.tag == .macos) {
        if (HAS_PIPELINE_CACHE) {
            if (@hasField(@TypeOf(self.*), "pipeline_binary_cache")) {
                if (self.pipeline_binary_cache) |c| {
                    const t: *metal_pipeline_cache.MetalPipelineCache = @ptrCast(@alignCast(c));
                    t.register_compute_key(base);
                }
            }
        }
    }
    return pso;
}

fn compile_kernel_library(
    self: anytype,
    root: []const u8,
    base: []const u8,
    err_buf: *[BRIDGE_ERROR_CAP]u8,
) !?*anyopaque {
    const metal_path = try std.fmt.allocPrint(self.allocator, "{s}/{s}.metal", .{ root, base });
    defer self.allocator.free(metal_path);

    const metal_source = std.fs.cwd().readFileAlloc(self.allocator, metal_path, MAX_KERNEL_SOURCE_BYTES) catch |err| switch (err) {
        error.FileNotFound => null,
        else => return error.ShaderCompileFailed,
    };
    if (metal_source) |source| {
        defer self.allocator.free(source);
        return metal_bridge_device_new_library_msl(
            self.device,
            source.ptr,
            source.len,
            err_buf,
            BRIDGE_ERROR_CAP,
        ) orelse error.ShaderCompileFailed;
    }

    const wgsl_path = try std.fmt.allocPrint(self.allocator, "{s}/{s}.wgsl", .{ root, base });
    defer self.allocator.free(wgsl_path);

    const wgsl_source = std.fs.cwd().readFileAlloc(self.allocator, wgsl_path, MAX_KERNEL_SOURCE_BYTES) catch {
        return error.ShaderCompileFailed;
    };
    defer self.allocator.free(wgsl_source);

    const msl_buf = try self.allocator.alloc(u8, wgsl_compiler.MAX_OUTPUT);
    defer self.allocator.free(msl_buf);

    const translated_len = blk: {
        var translation = wgsl_runtime_compile.translateToMslForComputeRuntime(
            self.allocator,
            wgsl_source,
            msl_buf,
            null,
            0,
        ) catch {
            break :blk wgsl_compiler.translateToMsl(self.allocator, wgsl_source, msl_buf) catch {
                return error.ShaderCompileFailed;
            };
        };
        defer translation.info.deinit(self.allocator);
        break :blk translation.len;
    };

    return metal_bridge_device_new_library_msl(
        self.device,
        msl_buf.ptr,
        translated_len,
        err_buf,
        BRIDGE_ERROR_CAP,
    ) orelse error.ShaderCompileFailed;
}

fn zeroBufferBytes(bytes: []u8) void {
    @memset(bytes, 0);
}

fn zeroComputeBufferContents(buffer: ?*anyopaque, size: u64) !void {
    if (size == 0) return;
    const mapped = metal_bridge_buffer_contents(buffer) orelse return error.InvalidState;
    zeroBufferBytes(@as([*]u8, @ptrCast(mapped))[0..@intCast(size)]);
}

pub fn ensure_compute_buffer(self: anytype, handle: u64, size: u64, initialize_buffers_on_create: bool) !?*anyopaque {
    if (self.compute_buffers.get(handle)) |b| return b;
    const buf = metal_bridge_device_new_buffer_shared(self.device, @intCast(size)) orelse return error.InvalidState;
    if (initialize_buffers_on_create) try zeroComputeBufferContents(buf, size);
    try self.compute_buffers.put(self.allocator, handle, buf);
    return buf;
}

pub fn write_compute_buffer_words(self: anytype, handle: u64, offset: u64, buffer_size: u64, data: []const u32) !void {
    if (data.len == 0) return error.InvalidArgument;
    const data_bytes = std.mem.sliceAsBytes(data);
    const required_size = if (buffer_size > 0)
        @max(buffer_size, offset + data_bytes.len)
    else
        offset + data_bytes.len;
    const buffer = try ensure_compute_buffer(self, handle, required_size, false);
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

pub fn ensure_render_pipeline(self: anytype, fmt: u32) !void {
    if (self.render_pipeline != null and self.render_pipeline_format == fmt) return;
    if (self.render_pipeline) |pipeline| metal_bridge_release(pipeline);
    if (self.cached_icb) |icb| {
        metal_bridge_release(icb);
        self.cached_icb = null;
    }
    var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
    self.render_pipeline = try resolve_render_pso_for(self, fmt, &err_buf);
    self.render_pipeline_format = fmt;
}

pub fn ensure_render_target(self: anytype, width: u32, height: u32, fmt: u32) !void {
    if (self.render_target != null and
        self.render_target_width == width and
        self.render_target_height == height and
        self.render_target_format == fmt) return;
    if (self.render_target) |target| metal_bridge_release(target);
    self.render_target = metal_bridge_device_new_render_target(self.device, width, height, fmt) orelse return error.InvalidState;
    self.render_target_width = width;
    self.render_target_height = height;
    self.render_target_format = fmt;
}

pub fn ensure_streaming_render_encoder(self: anytype) !void {
    if (self.streaming_render_encoder != null) return;

    if (self.streaming_blit_encoder) |encoder| {
        metal_bridge_end_blit_encoding(encoder);
        self.streaming_blit_encoder = null;
    }

    if (self.streaming_cmd_buf == null) {
        self.streaming_cmd_buf = bridge.metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
    }

    self.streaming_render_encoder = metal_bridge_cmd_buf_render_encoder(
        self.streaming_cmd_buf,
        self.render_pipeline,
        self.render_target,
        null,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
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
    if (self.cached_icb) |icb| metal_bridge_release(icb);
    const icb = metal_bridge_device_new_icb(self.device, self.render_pipeline, draw_count, redundant_pl) orelse return error.InvalidState;
    metal_bridge_icb_encode_draws(icb, self.render_pipeline, draw_count, vertex_count, instance_count, redundant_pl);
    self.cached_icb = icb;
    self.cached_icb_key = key;
    return icb;
}

// Resolve compute PSO: try archive (compile-or-serve), fall back to plain compile.
// Phase 2: on archive hit, the ObjC bridge returns a pre-compiled binary without
// calling newLibraryWithSource.  On miss, it compiles and primes the archive.
fn resolve_compute_pso_for(self: anytype, func: ?*anyopaque, err_buf: *[BRIDGE_ERROR_CAP]u8) !?*anyopaque {
    if (builtin.os.tag == .macos) {
        if (HAS_PIPELINE_CACHE) {
            if (@hasField(@TypeOf(self.*), "pipeline_binary_cache")) {
                if (self.pipeline_binary_cache) |c| {
                    const t: *metal_pipeline_cache.MetalPipelineCache = @ptrCast(@alignCast(c));
                    if (t.compile_or_serve_compute(func)) |pso| return pso;
                }
            }
        }
    }
    return metal_bridge_device_new_compute_pipeline(self.device, func, err_buf, BRIDGE_ERROR_CAP) orelse error.ShaderCompileFailed;
}

// Resolve render PSO: try archive (compile-or-serve), fall back to plain compile.
fn resolve_render_pso_for(self: anytype, fmt: u32, err_buf: *[BRIDGE_ERROR_CAP]u8) !?*anyopaque {
    if (builtin.os.tag == .macos) {
        if (HAS_PIPELINE_CACHE) {
            if (@hasField(@TypeOf(self.*), "pipeline_binary_cache")) {
                if (self.pipeline_binary_cache) |c| {
                    const t: *metal_pipeline_cache.MetalPipelineCache = @ptrCast(@alignCast(c));
                    if (t.compile_or_serve_render(fmt, 1)) |pso| return pso;
                }
            }
        }
    }
    return metal_bridge_device_new_render_pipeline(self.device, fmt, 1, err_buf, BRIDGE_ERROR_CAP) orelse error.ShaderCompileFailed;
}
