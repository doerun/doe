const builtin = @import("builtin");
const std = @import("std");
const pipeline_cache = @import("pipeline_cache.zig");
const wgsl_runtime_compile = @import("doe_wgsl/runtime_compile.zig");
const ir = @import("doe_wgsl/ir.zig");

const PipelineCache = pipeline_cache.PipelineCache;
const PipelineCacheKey = pipeline_cache.PipelineCacheKey;
const TranslationInfo = wgsl_runtime_compile.TranslationInfo;

const CACHE_MAGIC: u32 = 0xD0E5_CACE;
const CACHE_VERSION: u32 = 1;
const FLAG_NEEDS_SIZES_BUF: u32 = 1 << 0;
const FLAG_BOUNDS_ELISION: u32 = 1 << 1;
const FLAG_TEXTURE_BOUNDS_ELISION: u32 = 1 << 2;
const DEFAULT_CACHE_DIR_SUFFIX = "doe/shader_translation_cache";

const Header = extern struct {
    magic: u32,
    version: u32,
    flags: u32,
    workgroup_x: u32,
    workgroup_y: u32,
    workgroup_z: u32,
    dispatch_count: u32,
    texture_dispatch_count: u32,
    dispatch_stride: u32,
    texture_dispatch_stride: u32,
    msl_len: u32,
};

pub const CachedTranslation = struct {
    msl: []u8,
    info: TranslationInfo,

    pub fn deinit(self: *CachedTranslation, allocator: std.mem.Allocator) void {
        allocator.free(self.msl);
        self.info.deinit(allocator);
        self.* = undefined;
    }
};

var global_cache: ?*PipelineCache = null;
var init_attempted: bool = false;

pub fn lookupComputeTranslation(
    allocator: std.mem.Allocator,
    wgsl_source: []const u8,
) ?CachedTranslation {
    const cache = ensureGlobalCache() orelse return null;
    const payload = cache.lookup(&buildComputeKey(wgsl_source)) orelse return null;
    return decodePayload(allocator, payload);
}

pub fn storeComputeTranslation(
    allocator: std.mem.Allocator,
    wgsl_source: []const u8,
    msl_source: []const u8,
    info: *const TranslationInfo,
) void {
    const cache = ensureGlobalCache() orelse return;
    const payload = encodePayload(allocator, msl_source, info) catch return;
    defer allocator.free(payload);
    cache.store(&buildComputeKey(wgsl_source), payload);
}

fn ensureGlobalCache() ?*PipelineCache {
    if (global_cache) |cache| return cache;
    if (init_attempted) return null;
    init_attempted = true;
    const cache_dir = resolveDefaultCacheDir(std.heap.c_allocator) catch return null;
    defer std.heap.c_allocator.free(cache_dir);
    global_cache = PipelineCache.init(std.heap.c_allocator, cache_dir) catch null;
    return global_cache;
}

fn resolveDefaultCacheDir(allocator: std.mem.Allocator) ![]u8 {
    if (builtin.os.tag == .macos or builtin.os.tag == .linux) {
        if (std.posix.getenv("HOME")) |home| {
            return std.fmt.allocPrint(allocator, "{s}/.cache/{s}", .{ home, DEFAULT_CACHE_DIR_SUFFIX });
        }
    }
    return allocator.dupe(u8, "cache/" ++ DEFAULT_CACHE_DIR_SUFFIX);
}

fn buildComputeKey(wgsl_source: []const u8) PipelineCacheKey {
    return .{
        .wgsl_hash = pipeline_cache.hash_wgsl(wgsl_source),
        .kind = .compute,
        .pixel_format = 0,
        .vertex_entry_hash = 0,
        .fragment_entry_hash = 0,
        .sample_count = 1,
        .color_attachment_count = 0,
    };
}

fn currentFlags(info: ?*const TranslationInfo) u32 {
    var flags = compilerModeFlags();
    if (info != null and info.?.needs_sizes_buf) flags |= FLAG_NEEDS_SIZES_BUF;
    return flags;
}

fn compilerModeFlags() u32 {
    const config = wgsl_runtime_compile.compute_runtime_robustness_config();
    var flags: u32 = 0;
    if (config.elide_proven_bounds) flags |= FLAG_BOUNDS_ELISION;
    if (config.elide_proven_texture_bounds) flags |= FLAG_TEXTURE_BOUNDS_ELISION;
    return flags;
}

fn encodePayload(
    allocator: std.mem.Allocator,
    msl_source: []const u8,
    info: *const TranslationInfo,
) ![]u8 {
    const dispatch_bytes_len = info.dispatch_preconditions.len * @sizeOf(ir.DispatchPrecondition);
    const texture_bytes_len = info.texture_dispatch_preconditions.len * @sizeOf(ir.TextureDispatchPrecondition);
    const total_len =
        @sizeOf(Header) +
        msl_source.len +
        dispatch_bytes_len +
        texture_bytes_len;
    const payload = try allocator.alloc(u8, total_len);
    var offset: usize = 0;
    const header = Header{
        .magic = CACHE_MAGIC,
        .version = CACHE_VERSION,
        .flags = currentFlags(info),
        .workgroup_x = info.workgroup_size[0],
        .workgroup_y = info.workgroup_size[1],
        .workgroup_z = info.workgroup_size[2],
        .dispatch_count = @intCast(info.dispatch_preconditions.len),
        .texture_dispatch_count = @intCast(info.texture_dispatch_preconditions.len),
        .dispatch_stride = @sizeOf(ir.DispatchPrecondition),
        .texture_dispatch_stride = @sizeOf(ir.TextureDispatchPrecondition),
        .msl_len = @intCast(msl_source.len),
    };
    writeBytes(payload, &offset, std.mem.asBytes(&header));
    writeBytes(payload, &offset, msl_source);
    writeStructSlice(ir.DispatchPrecondition, payload, &offset, info.dispatch_preconditions);
    writeStructSlice(ir.TextureDispatchPrecondition, payload, &offset, info.texture_dispatch_preconditions);
    return payload;
}

fn decodePayload(
    allocator: std.mem.Allocator,
    payload: []const u8,
) ?CachedTranslation {
    if (payload.len < @sizeOf(Header)) return null;
    var offset: usize = 0;
    const header = readHeader(payload, &offset) orelse return null;
    if (header.magic != CACHE_MAGIC or header.version != CACHE_VERSION) return null;
    if (header.flags & ~FLAG_NEEDS_SIZES_BUF != compilerModeFlags()) return null;

    const msl_len: usize = @intCast(header.msl_len);
    const dispatch_count: usize = @intCast(header.dispatch_count);
    const texture_dispatch_count: usize = @intCast(header.texture_dispatch_count);
    if (header.dispatch_stride != @sizeOf(ir.DispatchPrecondition)) return null;
    if (header.texture_dispatch_stride != @sizeOf(ir.TextureDispatchPrecondition)) return null;
    const dispatch_bytes_len = dispatch_count * @sizeOf(ir.DispatchPrecondition);
    const texture_bytes_len = texture_dispatch_count * @sizeOf(ir.TextureDispatchPrecondition);
    if (offset + msl_len + dispatch_bytes_len + texture_bytes_len != payload.len) return null;

    const msl_source = allocator.dupe(u8, payload[offset .. offset + msl_len]) catch return null;
    offset += msl_len;
    errdefer allocator.free(msl_source);

    const dispatch_preconditions = duplicateStructSlice(
        allocator,
        ir.DispatchPrecondition,
        payload[offset .. offset + dispatch_bytes_len],
        dispatch_count,
    ) orelse return null;
    offset += dispatch_bytes_len;
    errdefer if (dispatch_preconditions.len > 0) allocator.free(dispatch_preconditions);

    const texture_dispatch_preconditions = duplicateStructSlice(
        allocator,
        ir.TextureDispatchPrecondition,
        payload[offset .. offset + texture_bytes_len],
        texture_dispatch_count,
    ) orelse return null;

    return .{
        .msl = msl_source,
        .info = .{
            .workgroup_size = .{ header.workgroup_x, header.workgroup_y, header.workgroup_z },
            .needs_sizes_buf = (header.flags & FLAG_NEEDS_SIZES_BUF) != 0,
            .dispatch_preconditions = dispatch_preconditions,
            .texture_dispatch_preconditions = texture_dispatch_preconditions,
        },
    };
}

fn readHeader(payload: []const u8, offset: *usize) ?Header {
    if (payload.len < @sizeOf(Header)) return null;
    const bytes = payload[offset.* .. offset.* + @sizeOf(Header)];
    offset.* += @sizeOf(Header);
    return std.mem.bytesToValue(Header, bytes[0..@sizeOf(Header)]);
}

fn writeBytes(payload: []u8, offset: *usize, bytes: []const u8) void {
    @memcpy(payload[offset.* .. offset.* + bytes.len], bytes);
    offset.* += bytes.len;
}

fn writeStructSlice(
    comptime T: type,
    payload: []u8,
    offset: *usize,
    items: []const T,
) void {
    if (items.len == 0) return;
    const bytes = std.mem.sliceAsBytes(items);
    writeBytes(payload, offset, bytes);
}

fn duplicateStructSlice(
    allocator: std.mem.Allocator,
    comptime T: type,
    bytes: []const u8,
    count: usize,
) ?[]const T {
    if (count == 0) return &.{};
    const items = allocator.alloc(T, count) catch return null;
    @memcpy(std.mem.sliceAsBytes(items), bytes);
    return items;
}

test "shader translation cache payload roundtrips" {
    var dispatch = [_]ir.DispatchPrecondition{.{
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 1 },
        .element_stride_bytes = 4,
    }};
    var texture = [_]ir.TextureDispatchPrecondition{.{
        .kind = .gid_coords_2d,
        .texture_binding = .{ .group = 0, .binding = 2 },
        .mip_level = 0,
    }};
    const info = TranslationInfo{
        .workgroup_size = .{ 8, 4, 1 },
        .needs_sizes_buf = true,
        .dispatch_preconditions = dispatch[0..],
        .texture_dispatch_preconditions = texture[0..],
    };
    const payload = try encodePayload(std.testing.allocator, "kernel msl", &info);
    defer std.testing.allocator.free(payload);

    var decoded = decodePayload(std.testing.allocator, payload) orelse return error.TestExpectedEqual;
    defer decoded.deinit(std.testing.allocator);

    try std.testing.expectEqualStrings("kernel msl", decoded.msl);
    try std.testing.expect(decoded.info.needs_sizes_buf);
    try std.testing.expectEqual(@as(u32, 8), decoded.info.workgroup_size[0]);
    try std.testing.expectEqual(@as(usize, 1), decoded.info.dispatch_preconditions.len);
    try std.testing.expectEqual(@as(usize, 1), decoded.info.texture_dispatch_preconditions.len);
}
