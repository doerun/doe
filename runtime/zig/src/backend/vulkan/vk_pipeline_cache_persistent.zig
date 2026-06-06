// Process-level persistent VkPipelineCache for the Doe Vulkan backend.
//
// Parallels runtime/zig/src/backend/metal/metal_pipeline_cache.zig in shape.
// Creates a real VkPipelineCache via vkCreatePipelineCache at device bring-up
// and passes its handle to vkCreateComputePipelines / vkCreateGraphicsPipelines
// instead of VK_NULL_U64. When a cache directory is configured, the module
// also reads any existing blob at process start and writes the current cache
// out at shutdown via vkGetPipelineCacheData (atomic .tmp + rename).
//
// Vulkan-spec behavior: if the blob header does not match the current device's
// pipelineCacheUUID/vendorID/deviceID, the driver silently initializes an
// empty cache from the bytes and continues. We do not need to pre-validate
// the header on our side; the driver handles incompatibility cleanly.

const std = @import("std");
const c = @import("vk_constants.zig");

const CACHE_BLOB_BASENAME = "doe-vulkan-pipeline-cache.blob";
const CACHE_BLOB_MAX_BYTES: usize = 64 * 1024 * 1024;
const CACHE_BLOB_MIN_BYTES: usize = 32;

pub const VulkanPipelineCacheState = enum { disabled, enabled, enabled_reloaded };

pub const WarmupTelemetry = struct {
    count: u64 = 0,
    ns: u64 = 0,
};

// Process-level handle mirroring the Metal backend's process_active_cache
// pattern. Only one Vulkan device is active per process in current benchmark
// usage; the module deliberately stays single-handle until a multi-device
// consumer needs it.
var process_cache_handle: c.VkPipelineCache = c.VK_NULL_U64;
var process_cache_state: VulkanPipelineCacheState = .disabled;
var process_cache_disabled: bool = false;
var process_cache_device: c.VkDevice = null;
var process_warmup: WarmupTelemetry = .{};

// Optional cache directory for disk-backed persistence. When set (via
// set_process_pipeline_cache_dir), create_process_pipeline_cache reads the
// blob at <dir>/doe-vulkan-pipeline-cache.blob if present and writes it back
// on destroy. When null, the cache is in-memory only for the process
// lifetime.
var process_cache_dir_buf: [512]u8 = undefined;
var process_cache_dir_len: usize = 0;
// Persistent blob path derived from dir at configure time.
var process_cache_path_buf: [512]u8 = undefined;
var process_cache_path_len: usize = 0;

pub fn set_process_pipeline_cache_disabled(disabled: bool) void {
    process_cache_disabled = disabled;
}

pub fn is_process_pipeline_cache_disabled() bool {
    return process_cache_disabled;
}

/// Configure the on-disk cache directory. Empty slice clears the setting so
/// the next create runs in-memory-only. Path must be shorter than 448 bytes
/// (cache-dir buffer minus file-basename budget).
pub fn set_process_pipeline_cache_dir(dir: []const u8) void {
    if (dir.len == 0) {
        process_cache_dir_len = 0;
        process_cache_path_len = 0;
        return;
    }
    const trimmed = trimTrailingSeparator(dir);
    if (trimmed.len == 0 or trimmed.len + 1 + CACHE_BLOB_BASENAME.len >= process_cache_path_buf.len) {
        // Path too long or empty after trim; reject quietly (in-memory only).
        process_cache_dir_len = 0;
        process_cache_path_len = 0;
        return;
    }
    @memcpy(process_cache_dir_buf[0..trimmed.len], trimmed);
    process_cache_dir_len = trimmed.len;
    @memcpy(process_cache_path_buf[0..trimmed.len], trimmed);
    process_cache_path_buf[trimmed.len] = '/';
    @memcpy(
        process_cache_path_buf[trimmed.len + 1 .. trimmed.len + 1 + CACHE_BLOB_BASENAME.len],
        CACHE_BLOB_BASENAME,
    );
    process_cache_path_len = trimmed.len + 1 + CACHE_BLOB_BASENAME.len;
}

fn trimTrailingSeparator(dir: []const u8) []const u8 {
    var end = dir.len;
    while (end > 0 and dir[end - 1] == '/') : (end -= 1) {}
    return dir[0..end];
}

fn cache_path_slice() ?[]const u8 {
    if (process_cache_path_len == 0) return null;
    return process_cache_path_buf[0..process_cache_path_len];
}

/// Create the process-level VkPipelineCache after vkCreateDevice. When a
/// cache directory has been configured (set_process_pipeline_cache_dir) and
/// the blob file exists, its contents seed the cache; the Vulkan driver
/// silently discards the blob if it is header-incompatible with the current
/// device, so no pre-validation is required here. Safe to call multiple
/// times: if the cache is already live, the call is a no-op.
pub fn create_process_pipeline_cache(device: c.VkDevice) !void {
    if (process_cache_disabled) {
        process_cache_state = .disabled;
        return;
    }
    if (process_cache_handle != c.VK_NULL_U64) {
        // Already live; treat as idempotent.
        return;
    }
    if (device == null) return error.InvalidArgument;

    const start_ns = std.time.nanoTimestamp();

    var blob_bytes: ?[]u8 = null;
    defer if (blob_bytes) |b| std.heap.page_allocator.free(b);
    var reloaded = false;
    if (cache_path_slice()) |path| {
        blob_bytes = try_read_cache_blob(path);
        if (blob_bytes != null) reloaded = true;
    }

    const initial_size: usize = if (blob_bytes) |b| b.len else 0;
    const initial_ptr: ?*const anyopaque = if (blob_bytes) |b| @ptrCast(b.ptr) else null;
    var create_info = c.VkPipelineCacheCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .initialDataSize = initial_size,
        .pInitialData = initial_ptr,
    };
    var handle: c.VkPipelineCache = c.VK_NULL_U64;
    const result = c.vkCreatePipelineCache(device, &create_info, null, &handle);
    if (result != c.VK_SUCCESS) {
        process_cache_state = .disabled;
        return error.PipelineCacheCreateFailed;
    }
    process_cache_handle = handle;
    process_cache_device = device;
    process_cache_state = if (reloaded) .enabled_reloaded else .enabled;
    const end_ns = std.time.nanoTimestamp();
    process_warmup.count = 1;
    process_warmup.ns = @intCast(end_ns - start_ns);
}

fn try_read_cache_blob(path: []const u8) ?[]u8 {
    const file = if (std.fs.path.isAbsolute(path))
        std.fs.openFileAbsolute(path, .{ .mode = .read_only }) catch return null
    else
        std.fs.cwd().openFile(path, .{ .mode = .read_only }) catch return null;
    defer file.close();
    const stat = file.stat() catch return null;
    if (stat.size < CACHE_BLOB_MIN_BYTES or stat.size > CACHE_BLOB_MAX_BYTES) return null;
    const size: usize = @intCast(stat.size);
    const buf = std.heap.page_allocator.alloc(u8, size) catch return null;
    errdefer std.heap.page_allocator.free(buf);
    const read = file.readAll(buf) catch {
        std.heap.page_allocator.free(buf);
        return null;
    };
    if (read != size) {
        std.heap.page_allocator.free(buf);
        return null;
    }
    return buf;
}

/// Destroy the process-level cache. Safe to call multiple times. Must be
/// called before vkDestroyDevice on the same device the cache was created on.
/// When a cache directory is configured, serializes the current cache out to
/// the blob path via vkGetPipelineCacheData with atomic .tmp + rename. Write
/// failures are non-fatal: the cache is still destroyed cleanly.
pub fn destroy_process_pipeline_cache(device: c.VkDevice) void {
    if (process_cache_handle == c.VK_NULL_U64) return;
    if (device == null) return;
    if (process_cache_device != device) {
        // Device mismatch; refuse to destroy against a foreign device rather
        // than crash inside the driver. This should be impossible in current
        // single-device usage, but keeps the invariant explicit.
        return;
    }

    if (cache_path_slice()) |path| {
        try_write_cache_blob(device, process_cache_handle, path) catch {};
    }

    c.vkDestroyPipelineCache(device, process_cache_handle, null);
    process_cache_handle = c.VK_NULL_U64;
    process_cache_device = null;
    process_cache_state = .disabled;
    process_warmup = .{};
}

fn try_write_cache_blob(
    device: c.VkDevice,
    cache: c.VkPipelineCache,
    path: []const u8,
) !void {
    var size: usize = 0;
    const query_result = c.vkGetPipelineCacheData(device, cache, &size, null);
    if (query_result != c.VK_SUCCESS or size == 0 or size > CACHE_BLOB_MAX_BYTES) return;
    const buf = try std.heap.page_allocator.alloc(u8, size);
    defer std.heap.page_allocator.free(buf);
    var written: usize = size;
    const fetch_result = c.vkGetPipelineCacheData(device, cache, &written, @ptrCast(buf.ptr));
    if (fetch_result != c.VK_SUCCESS or written == 0) return;

    // Parent dir must exist; create it idempotently.
    if (std.fs.path.dirname(path)) |dir| {
        if (std.fs.path.isAbsolute(path)) {
            std.fs.makeDirAbsolute(dir) catch |err| switch (err) {
                error.PathAlreadyExists => {},
                else => return err,
            };
        } else {
            try std.fs.cwd().makePath(dir);
        }
    }

    var tmp_buf: [520]u8 = undefined;
    if (path.len + 4 >= tmp_buf.len) return;
    @memcpy(tmp_buf[0..path.len], path);
    @memcpy(tmp_buf[path.len..][0..4], ".tmp");
    const tmp_path = tmp_buf[0 .. path.len + 4];

    const tmp_file = if (std.fs.path.isAbsolute(path))
        std.fs.createFileAbsolute(tmp_path, .{ .truncate = true }) catch return
    else
        std.fs.cwd().createFile(tmp_path, .{ .truncate = true }) catch return;
    var keep_tmp = false;
    defer if (!keep_tmp) {
        if (std.fs.path.isAbsolute(path)) {
            std.fs.deleteFileAbsolute(tmp_path) catch {};
        } else {
            std.fs.cwd().deleteFile(tmp_path) catch {};
        }
    };
    defer tmp_file.close();
    tmp_file.writeAll(buf[0..written]) catch return;
    if (std.fs.path.isAbsolute(path)) {
        std.fs.renameAbsolute(tmp_path, path) catch return;
    } else {
        std.fs.cwd().rename(tmp_path, path) catch return;
    }
    keep_tmp = true;
}

/// Returns the handle to pass to vkCreateComputePipelines /
/// vkCreateGraphicsPipelines. Returns VK_NULL_U64 when the cache is disabled
/// (either by --no-pipeline-cache or by a failed create); that preserves
/// existing behavior as the fallback.
pub fn handle_for_pipeline_creation() c.VkPipelineCache {
    if (process_cache_disabled) return c.VK_NULL_U64;
    return process_cache_handle;
}

pub fn process_active_cache_present() bool {
    return process_cache_handle != c.VK_NULL_U64 and process_cache_state != .disabled;
}

pub fn process_active_cache_warmup_telemetry() WarmupTelemetry {
    return process_warmup;
}

/// Reset module-level state. Test-only entrypoint.
pub fn reset_for_testing() void {
    process_cache_handle = c.VK_NULL_U64;
    process_cache_state = .disabled;
    process_cache_disabled = false;
    process_cache_device = null;
    process_warmup = .{};
    process_cache_dir_len = 0;
    process_cache_path_len = 0;
}

test "disabled flag suppresses cache creation" {
    reset_for_testing();
    set_process_pipeline_cache_disabled(true);
    try std.testing.expect(is_process_pipeline_cache_disabled());
    try std.testing.expectEqual(@as(c.VkPipelineCache, c.VK_NULL_U64), handle_for_pipeline_creation());
    try std.testing.expect(!process_active_cache_present());
}

test "default state is disabled handle" {
    reset_for_testing();
    try std.testing.expect(!is_process_pipeline_cache_disabled());
    try std.testing.expectEqual(@as(c.VkPipelineCache, c.VK_NULL_U64), handle_for_pipeline_creation());
    try std.testing.expect(!process_active_cache_present());
}
