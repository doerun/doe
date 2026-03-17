// metal_pipeline_cache.zig — MTLBinaryArchive integration for Metal pipeline caching.
//
// MTLBinaryArchive (macOS 11+) persists compiled GPU binaries across process launches.
// This module wraps the ObjC bridge calls and integrates with pipeline_cache.zig for
// the in-process LRU layer.
//
// Fallback: if MTLBinaryArchive is unavailable (< macOS 11), we fall through to the
// MSL-text caching path in pipeline_cache.zig without binary archiving.

const builtin = @import("builtin");
const std = @import("std");

// ============================================================
// Constants

const MAGIC_METAL_CACHE: u32 = 0xD0EB_10AC;
const BRIDGE_ERROR_CAP: usize = 512;
const ARCHIVE_FILENAME = "doe_pipeline_archive.metallib";

// ============================================================
// Bridge declarations (implemented in metal_bridge.m)

extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;

// Create a MTLBinaryArchive backed by a file at `path` (NUL-terminated).
// Returns the archive handle (+1 retained), or null if the API is unavailable or
// the file cannot be opened/created.
extern fn metal_bridge_binary_archive_create(
    device: ?*anyopaque,
    path: [*:0]const u8,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

// Add a compute pipeline to the archive.  Returns 1 on success, 0 on failure.
extern fn metal_bridge_binary_archive_add_compute(
    archive: ?*anyopaque,
    device: ?*anyopaque,
    pipeline: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) u32;

// Add a render pipeline to the archive.  Returns 1 on success, 0 on failure.
extern fn metal_bridge_binary_archive_add_render(
    archive: ?*anyopaque,
    device: ?*anyopaque,
    pipeline: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) u32;

// Flush archive to the file URL provided at creation.  Returns 1 on success.
extern fn metal_bridge_binary_archive_serialize(
    archive: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) u32;

// Create a compute pipeline using a pre-existing archive as the binary source.
// Returns null if the archive does not contain a matching entry (caller then
// falls back to fresh compilation and calls metal_bridge_binary_archive_add_compute).
extern fn metal_bridge_device_new_compute_pipeline_with_archive(
    device: ?*anyopaque,
    function: ?*anyopaque,
    archive: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

// Create a render pipeline using a pre-existing archive.
extern fn metal_bridge_device_new_render_pipeline_with_archive(
    device: ?*anyopaque,
    pixel_format: u32,
    support_icb: c_int,
    archive: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

// ============================================================
// MetalPipelineCache

pub const MetalPipelineCache = struct {
    magic: u32 = MAGIC_METAL_CACHE,
    allocator: std.mem.Allocator,
    device: ?*anyopaque,
    // MTLBinaryArchive handle, or null if unavailable.
    archive: ?*anyopaque,
    // Full path to the .metallib archive file (owned).
    archive_path: ?[]u8,
    // Tracks whether the archive has unserialized changes.
    dirty: bool = false,

    pub fn init(
        allocator: std.mem.Allocator,
        device: ?*anyopaque,
        cache_dir: []const u8,
    ) !*MetalPipelineCache {
        const self = try allocator.create(MetalPipelineCache);
        errdefer allocator.destroy(self);

        self.* = .{
            .allocator = allocator,
            .device = device,
            .archive = null,
            .archive_path = null,
        };

        if (builtin.os.tag != .macos) return self;

        // Build archive path: <cache_dir>/doe_pipeline_archive.metallib\0
        const path = try std.fmt.allocPrint(allocator, "{s}/{s}\x00", .{ cache_dir, ARCHIVE_FILENAME });
        self.archive_path = path[0 .. path.len]; // keep as []u8 (not sentinel)

        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        self.archive = metal_bridge_binary_archive_create(
            device,
            @ptrCast(path.ptr),
            &err_buf,
            BRIDGE_ERROR_CAP,
        );
        // archive == null means MTLBinaryArchive is unavailable (< macOS 11) or the
        // path could not be opened; we continue without it — MSL text cache still works.

        return self;
    }

    pub fn deinit(self: *MetalPipelineCache) void {
        const allocator = self.allocator;
        if (self.dirty) self.flush_archive();
        if (self.archive) |a| metal_bridge_release(a);
        if (self.archive_path) |p| allocator.free(p);
        allocator.destroy(self);
    }

    // Try to create a compute PSO via the archive.  On miss, returns null so the
    // caller creates it fresh and then calls cache_compute_pipeline.
    pub fn lookup_compute_pipeline(
        self: *MetalPipelineCache,
        function: ?*anyopaque,
    ) ?*anyopaque {
        const archive = self.archive orelse return null;
        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        return metal_bridge_device_new_compute_pipeline_with_archive(
            self.device,
            function,
            archive,
            &err_buf,
            BRIDGE_ERROR_CAP,
        );
    }

    // Try to create a render PSO via the archive.  Returns null on miss.
    pub fn lookup_render_pipeline(
        self: *MetalPipelineCache,
        pixel_format: u32,
        support_icb: c_int,
    ) ?*anyopaque {
        const archive = self.archive orelse return null;
        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        return metal_bridge_device_new_render_pipeline_with_archive(
            self.device,
            pixel_format,
            support_icb,
            archive,
            &err_buf,
            BRIDGE_ERROR_CAP,
        );
    }

    // Record a freshly compiled compute PSO into the archive.
    pub fn cache_compute_pipeline(self: *MetalPipelineCache, pipeline: ?*anyopaque) void {
        const archive = self.archive orelse return;
        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        const ok = metal_bridge_binary_archive_add_compute(
            archive,
            self.device,
            pipeline,
            &err_buf,
            BRIDGE_ERROR_CAP,
        );
        if (ok != 0) self.dirty = true;
    }

    // Record a freshly compiled render PSO into the archive.
    pub fn cache_render_pipeline(self: *MetalPipelineCache, pipeline: ?*anyopaque) void {
        const archive = self.archive orelse return;
        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        const ok = metal_bridge_binary_archive_add_render(
            archive,
            self.device,
            pipeline,
            &err_buf,
            BRIDGE_ERROR_CAP,
        );
        if (ok != 0) self.dirty = true;
    }

    // Write archive to disk.  Called at deinit and by the native ABI flush.
    pub fn flush_archive(self: *MetalPipelineCache) void {
        const archive = self.archive orelse return;
        if (!self.dirty) return;
        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        _ = metal_bridge_binary_archive_serialize(archive, &err_buf, BRIDGE_ERROR_CAP);
        self.dirty = false;
    }
};

// ============================================================
// C ABI exports

const MAGIC_METAL_CACHE_OPAQUE: u32 = MAGIC_METAL_CACHE;

pub export fn doeNativeMetalPipelineCacheCreate(
    device: ?*anyopaque,
    cache_dir: ?[*:0]const u8,
) callconv(.c) ?*anyopaque {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    const allocator = gpa.allocator();

    const dir: []const u8 = if (cache_dir) |d| std.mem.span(d) else "cache/fawn/pipeline_cache";
    const cache = MetalPipelineCache.init(allocator, device, dir) catch return null;
    return @ptrCast(cache);
}

pub export fn doeNativeMetalPipelineCacheFlush(raw: ?*anyopaque) callconv(.c) void {
    if (cache_from_opaque(raw)) |c| c.flush_archive();
}

pub export fn doeNativeMetalPipelineCacheRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cache_from_opaque(raw)) |c| c.deinit();
}

// Look up and return a compute PSO (+1 retained by the archive lookup path).
// Returns null on miss — caller must compile and call doeNativeMetalPipelineCacheAddCompute.
pub export fn doeNativeMetalPipelineCacheLookupCompute(
    cache_raw: ?*anyopaque,
    function: ?*anyopaque,
) callconv(.c) ?*anyopaque {
    const cache = cache_from_opaque(cache_raw) orelse return null;
    return cache.lookup_compute_pipeline(function);
}

pub export fn doeNativeMetalPipelineCacheAddCompute(
    cache_raw: ?*anyopaque,
    pipeline: ?*anyopaque,
) callconv(.c) void {
    if (cache_from_opaque(cache_raw)) |c| c.cache_compute_pipeline(pipeline);
}

pub export fn doeNativeMetalPipelineCacheLookupRender(
    cache_raw: ?*anyopaque,
    pixel_format: u32,
    support_icb: c_int,
) callconv(.c) ?*anyopaque {
    const cache = cache_from_opaque(cache_raw) orelse return null;
    return cache.lookup_render_pipeline(pixel_format, support_icb);
}

pub export fn doeNativeMetalPipelineCacheAddRender(
    cache_raw: ?*anyopaque,
    pipeline: ?*anyopaque,
) callconv(.c) void {
    if (cache_from_opaque(cache_raw)) |c| c.cache_render_pipeline(pipeline);
}

// ============================================================
// Internal

fn cache_from_opaque(raw: ?*anyopaque) ?*MetalPipelineCache {
    const p = raw orelse return null;
    const c: *MetalPipelineCache = @ptrCast(@alignCast(p));
    if (c.magic != MAGIC_METAL_CACHE) return null;
    return c;
}
