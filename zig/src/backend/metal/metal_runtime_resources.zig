const std = @import("std");
const bridge = @import("metal_bridge_decls.zig");

const metal_bridge_cmd_buf_render_encoder = bridge.metal_bridge_cmd_buf_render_encoder;
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
    const base = strip_extension(kernel);
    if (self.kernel_pipelines.get(base)) |kp| return kp.pipeline;

    const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
    const path = try std.fmt.allocPrint(self.allocator, "{s}/{s}.metal", .{ root, base });
    defer self.allocator.free(path);

    const source = std.fs.cwd().readFileAlloc(self.allocator, path, MAX_KERNEL_SOURCE_BYTES) catch {
        return error.ShaderToolchainUnavailable;
    };
    defer self.allocator.free(source);

    var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
    const lib = metal_bridge_device_new_library_msl(
        self.device,
        source.ptr,
        source.len,
        &err_buf,
        BRIDGE_ERROR_CAP,
    ) orelse return error.ShaderCompileFailed;
    errdefer metal_bridge_release(lib);

    const func = metal_bridge_library_new_function(lib, KERNEL_ENTRY_Z) orelse return error.ShaderCompileFailed;
    errdefer metal_bridge_release(func);

    const pso = metal_bridge_device_new_compute_pipeline(
        self.device,
        func,
        &err_buf,
        BRIDGE_ERROR_CAP,
    ) orelse return error.ShaderCompileFailed;
    metal_bridge_release(func);

    const key = try self.allocator.dupe(u8, base);
    errdefer self.allocator.free(key);
    try self.kernel_pipelines.put(self.allocator, key, .{ .library = lib, .pipeline = pso });
    return pso;
}

pub fn ensure_compute_buffer(self: anytype, handle: u64, size: u64) !?*anyopaque {
    if (self.compute_buffers.get(handle)) |b| return b;
    const buf = metal_bridge_device_new_buffer_shared(self.device, @intCast(size)) orelse return error.InvalidState;
    try self.compute_buffers.put(self.allocator, handle, buf);
    return buf;
}

pub fn ensure_render_pipeline(self: anytype, fmt: u32) !void {
    if (self.render_pipeline != null and self.render_pipeline_format == fmt) return;
    if (self.render_pipeline) |pipeline| metal_bridge_release(pipeline);
    if (self.cached_icb) |icb| {
        metal_bridge_release(icb);
        self.cached_icb = null;
    }
    var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
    self.render_pipeline = metal_bridge_device_new_render_pipeline(
        self.device,
        fmt,
        1,
        &err_buf,
        BRIDGE_ERROR_CAP,
    ) orelse return error.ShaderCompileFailed;
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

fn strip_extension(name: []const u8) []const u8 {
    const suffixes = [_][]const u8{ ".wgsl", ".spv", ".metal" };
    for (suffixes) |suffix| {
        if (std.mem.endsWith(u8, name, suffix)) return name[0 .. name.len - suffix.len];
    }
    return name;
}
