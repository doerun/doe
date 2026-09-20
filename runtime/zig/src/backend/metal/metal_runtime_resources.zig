const std = @import("std");
const builtin = @import("builtin");
const bridge = @import("metal_bridge_decls.zig");
const metal_buffer_pool = @import("metal_buffer_pool.zig");
const metal_pipeline_cache = @import("metal_pipeline_cache.zig");
const msl_translation = @import("../../compiler/wgsl/pipeline/translate_msl.zig");
const analysis = @import("../../compiler/wgsl/pipeline/analysis.zig");
const reflection = @import("../../compiler/wgsl/pipeline/binding_reflection.zig");
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
const BRIDGE_ERROR_CAP: usize = 512;
const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;

pub const KernelInterface = struct {
    bindings: [reflection.MAX_BINDINGS]reflection.BindingMeta = undefined,
    binding_count: usize = 0,
    needs_sizes_buf: bool = false,
};

pub const KernelPipelineInfo = struct {
    pipeline: ?*anyopaque,
    workgroup_size: [3]u32,
    interface: KernelInterface = .{},
};

pub const KernelPipeline = struct {
    library: ?*anyopaque,
    pipeline: ?*anyopaque,
    workgroup_size: [3]u32,
    interface: KernelInterface,
    source: []const u8,
    compiler_identity: []const u8,
};

const PipelineRequest = struct {
    path: []const u8,
    entry_point: []const u8,
    key: []const u8,

    fn deinit(self: PipelineRequest, allocator: std.mem.Allocator) void {
        allocator.free(self.path);
        allocator.free(self.key);
    }
};

fn parsePipelineRequest(allocator: std.mem.Allocator, root: []const u8, kernel: []const u8, entry_point: ?[]const u8) !PipelineRequest {
    const separator = std.mem.indexOfScalar(u8, kernel, '#');
    const name = kernel[0 .. separator orelse kernel.len];
    const requested = entry_point orelse if (separator) |i| kernel[i + 1 ..] else DEFAULT_COMPUTE_ENTRY_POINT;
    const entry = if (requested.len == 0) DEFAULT_COMPUTE_ENTRY_POINT else requested;
    if (name.len == 0 or std.mem.indexOfScalar(u8, entry, 0) != null or std.mem.indexOfScalar(u8, entry, '#') != null) return error.InvalidArgument;
    const extension = std.fs.path.extension(name);
    // Command WGSL must never be replaced by a sibling native shader. Raw MSL
    // needs a separate reflected layout contract before this path can execute it.
    if (extension.len != 0 and !std.mem.eql(u8, extension, ".wgsl")) return error.UnsupportedKernelLanguage;
    const suffix = if (extension.len == 0) ".wgsl" else "";
    const requested_path = if (std.fs.path.isAbsolute(name)) try std.fmt.allocPrint(allocator, "{s}{s}", .{ name, suffix }) else try std.fmt.allocPrint(allocator, "{s}/{s}{s}", .{ root, name, suffix });
    defer allocator.free(requested_path);
    const path = try std.fs.cwd().realpathAlloc(allocator, requested_path);
    errdefer allocator.free(path);
    const key = try std.fmt.allocPrint(allocator, "{s}#{s}", .{ path, entry });
    return .{ .path = path, .entry_point = entry, .key = key };
}

fn pipelineInfo(pipeline: KernelPipeline) KernelPipelineInfo {
    return .{ .pipeline = pipeline.pipeline, .workgroup_size = pipeline.workgroup_size, .interface = pipeline.interface };
}

pub fn ensure_kernel_pipeline_info(self: anytype, pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache, kernel: []const u8, entry_point: ?[]const u8) !KernelPipelineInfo {
    return ensureKernelPipelineWithBridge(self, pipeline_cache, kernel, entry_point, bridge);
}

fn ensureKernelPipelineWithBridge(self: anytype, pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache, kernel: []const u8, entry_point: ?[]const u8, comptime native: type) !KernelPipelineInfo {
    const request = try parsePipelineRequest(self.allocator, self.kernel_root orelse DEFAULT_KERNEL_ROOT, kernel, entry_point);
    defer request.deinit(self.allocator);
    const source = try std.fs.cwd().readFileAlloc(self.allocator, request.path, MAX_KERNEL_SOURCE_BYTES);
    errdefer self.allocator.free(source);
    const compiler_identity = @import("build_options").wgsl_compiler_source_sha256;
    if (self.kernel_pipelines.get(request.key)) |cached| {
        if (std.mem.eql(u8, source, cached.source) and std.mem.eql(u8, compiler_identity, cached.compiler_identity)) {
            self.allocator.free(source);
            return pipelineInfo(cached);
        }
    }
    const output = try self.allocator.alloc(u8, msl_translation.MAX_OUTPUT);
    defer self.allocator.free(output);
    var diagnostic = analysis.Diagnostic{};
    var translation = try wgsl_runtime_compile.translateMslEntryPoint(self.allocator, source, request.entry_point, output, &diagnostic);
    defer translation.info.deinit(self.allocator);
    var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
    const library = native.metal_bridge_device_new_library_msl(self.device, output.ptr, translation.len, &err_buf, BRIDGE_ERROR_CAP) orelse return error.ShaderCompileFailed;
    errdefer native.metal_bridge_release(library);
    const function_name = try self.allocator.dupeZ(u8, emit_msl_maps.msl_function_name(request.entry_point, .compute));
    defer self.allocator.free(function_name);
    const function = native.metal_bridge_library_new_function(library, function_name.ptr) orelse return error.ShaderCompileFailed;
    defer native.metal_bridge_release(function);
    const pipeline = if (native == bridge) try resolve_compute_pso_for(self.device, pipeline_cache, function, &err_buf) else native.metal_bridge_device_new_compute_pipeline(self.device, function, &err_buf, BRIDGE_ERROR_CAP) orelse return error.ShaderCompileFailed;
    errdefer native.metal_bridge_release(pipeline);
    const replacement = KernelPipeline{
        .library = library,
        .pipeline = pipeline,
        .source = source,
        .compiler_identity = compiler_identity,
        .workgroup_size = translation.info.workgroup_size,
        .interface = .{ .bindings = translation.bindings, .binding_count = translation.binding_count, .needs_sizes_buf = translation.info.needs_sizes_buf },
    };
    if (self.kernel_pipelines.getPtr(request.key)) |existing| {
        // Queued work may still reference the previous native program. Failed
        // compilation or retirement leaves that owner unchanged.
        _ = try self.flush_queue();
        native.metal_bridge_release(existing.library);
        native.metal_bridge_release(existing.pipeline);
        self.allocator.free(existing.source);
        existing.* = replacement;
    } else {
        const key = try self.allocator.dupe(u8, request.key);
        errdefer self.allocator.free(key);
        try self.kernel_pipelines.put(self.allocator, key, replacement);
    }
    if (builtin.os.tag == .macos and HAS_PIPELINE_CACHE) {
        if (pipeline_cache) |cache| cache.register_compute_key(request.key);
    }
    return pipelineInfo(replacement);
}

pub fn ensure_kernel_pipeline(self: anytype, pipeline_cache: ?*metal_pipeline_cache.MetalPipelineCache, kernel: []const u8, entry_point: ?[]const u8) !?*anyopaque {
    return (try ensure_kernel_pipeline_info(self, pipeline_cache, kernel, entry_point)).pipeline;
}

pub fn get_kernel_workgroup_size(self: anytype, kernel: []const u8, entry_point: ?[]const u8) ![3]u32 {
    return (try self.ensure_kernel_pipeline_info(kernel, entry_point)).workgroup_size;
}

fn zeroBufferBytes(bytes: []u8) void {
    @memset(bytes, 0);
}

test "Metal program cache reads exact source and preserves the old owner after failed replacement" {
    const Probe = struct {
        var objects: [3]u8 = .{ 0, 0, 0 };
        var libraries: usize = 0;
        var releases: usize = 0;
        pub fn metal_bridge_device_new_library_msl(_: ?*anyopaque, _: [*]const u8, _: usize, _: ?[*]u8, _: usize) ?*anyopaque {
            libraries += 1;
            return &objects[0];
        }
        pub fn metal_bridge_library_new_function(_: ?*anyopaque, name: [*:0]const u8) ?*anyopaque {
            std.testing.expectEqualStrings("selected", std.mem.span(name)) catch @panic("wrong entrypoint");
            return &objects[1];
        }
        pub fn metal_bridge_device_new_compute_pipeline(_: ?*anyopaque, _: ?*anyopaque, _: ?[*]u8, _: usize) ?*anyopaque {
            return &objects[2];
        }
        pub fn metal_bridge_release(_: ?*anyopaque) void {
            releases += 1;
        }
    };
    const Runtime = struct {
        allocator: std.mem.Allocator,
        kernel_root: ?[]const u8,
        device: ?*anyopaque = null,
        kernel_pipelines: std.StringHashMapUnmanaged(KernelPipeline) = .{},
        flushes: usize = 0,
        pub fn flush_queue(self: *@This()) !u64 {
            self.flushes += 1;
            return 0;
        }
    };
    const source = "@compute @workgroup_size(1) fn main() {} @compute @workgroup_size(7) fn selected() {}";
    var directory = std.testing.tmpDir(.{});
    defer directory.cleanup();
    try directory.dir.writeFile(.{ .sub_path = "kernel.wgsl", .data = source });
    try directory.dir.writeFile(.{ .sub_path = "kernel.metal", .data = "must not select this sibling" });
    const root = try directory.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    var runtime = Runtime{ .allocator = std.testing.allocator, .kernel_root = root };
    defer {
        var it = runtime.kernel_pipelines.iterator();
        while (it.next()) |entry| {
            runtime.allocator.free(entry.key_ptr.*);
            runtime.allocator.free(entry.value_ptr.source);
            Probe.metal_bridge_release(entry.value_ptr.library);
            Probe.metal_bridge_release(entry.value_ptr.pipeline);
        }
        runtime.kernel_pipelines.deinit(runtime.allocator);
    }
    Probe.libraries = 0;
    Probe.releases = 0;
    const first = try ensureKernelPipelineWithBridge(&runtime, null, "kernel.wgsl", "selected", Probe);
    try std.testing.expectEqualDeep(@as([3]u32, .{ 7, 1, 1 }), first.workgroup_size);
    _ = try ensureKernelPipelineWithBridge(&runtime, null, "kernel", "selected", Probe);
    try std.testing.expectEqual(@as(usize, 1), Probe.libraries);
    try directory.dir.writeFile(.{ .sub_path = "kernel.wgsl", .data = source ++ "\n" });
    _ = try ensureKernelPipelineWithBridge(&runtime, null, "kernel.wgsl", "selected", Probe);
    try std.testing.expectEqual(@as(usize, 2), Probe.libraries);
    try std.testing.expectEqual(@as(usize, 1), runtime.flushes);
    try directory.dir.writeFile(.{ .sub_path = "kernel.wgsl", .data = "@compute @workgroup_size(1) fn missing() {}" });
    try std.testing.expectError(error.UnknownIdentifier, ensureKernelPipelineWithBridge(&runtime, null, "kernel.wgsl", "selected", Probe));
    try std.testing.expectEqual(@as(usize, 2), Probe.libraries);
    try std.testing.expectEqual(@as(usize, 1), runtime.kernel_pipelines.count());
    try directory.dir.deleteFile("kernel.wgsl");
    try std.testing.expectError(error.FileNotFound, ensureKernelPipelineWithBridge(&runtime, null, "kernel.wgsl", "selected", Probe));
    try std.testing.expectError(error.UnsupportedKernelLanguage, ensureKernelPipelineWithBridge(&runtime, null, "kernel.metal", "selected", Probe));
}

test "Metal compiler metadata binds the selected entrypoint and minimum buffer extent" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> unused: array<u32, 2>;
        \\@group(1) @binding(2) var<storage, read_write> selected_data: array<u32, 7>;
        \\@compute @workgroup_size(1) fn main() { unused[0] = 1u; }
        \\@compute @workgroup_size(7) fn selected() { selected_data[0] = 2u; }
        \\fn helper() {}
    ;
    const output = try std.testing.allocator.alloc(u8, msl_translation.MAX_OUTPUT);
    defer std.testing.allocator.free(output);
    var diagnostic = analysis.Diagnostic{};
    var translated = try wgsl_runtime_compile.translateMslEntryPoint(std.testing.allocator, source, "selected", output, &diagnostic);
    defer translated.info.deinit(std.testing.allocator);
    try std.testing.expectEqualDeep(@as([3]u32, .{ 7, 1, 1 }), translated.info.workgroup_size);
    try std.testing.expectEqual(@as(usize, 1), translated.binding_count);
    const binding = translated.bindings[0];
    try std.testing.expectEqual(@as(u32, 1), binding.group);
    try std.testing.expectEqual(@as(u32, 2), binding.binding);
    try std.testing.expectEqual(@as(u32, 28), binding.min_binding_size);
    try std.testing.expectError(error.UnknownIdentifier, wgsl_runtime_compile.translateMslEntryPoint(std.testing.allocator, source, "helper", output, &diagnostic));
    try std.testing.expectEqual(@as(?analysis.TranslateError, error.UnknownIdentifier), diagnostic.last_error_kind);
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
