const std = @import("std");
const spirv_translation = @import("../../compiler/wgsl/pipeline/translate_spirv.zig");
const path_utils = @import("../common/path_utils.zig");

const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;
const SPIRV_MAGIC: u32 = 0x07230203;
const DEFAULT_KERNEL_ROOT = "bench/kernels";

pub fn load_kernel_source(self: anytype, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
    if (kernel_name.len == 0) return error.InvalidArgument;
    const path = try resolve_kernel_path(self, allocator, kernel_name);
    defer allocator.free(path);
    return std.fs.cwd().readFileAlloc(allocator, path, MAX_KERNEL_SOURCE_BYTES);
}

pub fn load_kernel_spirv(self: anytype, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
    return try load_kernel_spirv_uncached(self, allocator, kernel_name);
}

pub fn ensure_kernel_spirv_cached(self: anytype, kernel_name: []const u8) ![]const u32 {
    if (kernel_name.len == 0) return error.InvalidArgument;
    if (self.kernel_spirv_cache.get(kernel_name)) |cached| return cached;
    const words = try load_kernel_spirv_uncached(self, self.allocator, kernel_name);
    errdefer self.allocator.free(words);
    const owned_kernel_name = try self.allocator.dupe(u8, kernel_name);
    errdefer self.allocator.free(owned_kernel_name);
    try self.kernel_spirv_cache.put(self.allocator, owned_kernel_name, words);
    return words;
}

pub fn release_kernel_spirv_cache(self: anytype) void {
    var it = self.kernel_spirv_cache.iterator();
    while (it.next()) |entry| {
        self.allocator.free(entry.key_ptr.*);
        self.allocator.free(entry.value_ptr.*);
    }
    self.kernel_spirv_cache.deinit(self.allocator);
}

fn load_kernel_spirv_uncached(self: anytype, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
    if (kernel_name.len == 0) return error.InvalidArgument;
    const path = resolve_kernel_spirv_path(self, allocator, kernel_name) catch |err| switch (err) {
        error.UnsupportedFeature => return try compile_kernel_wgsl_to_spirv(self, allocator, kernel_name),
        else => return err,
    };
    defer allocator.free(path);

    const bytes = try std.fs.cwd().readFileAlloc(allocator, path, MAX_KERNEL_SOURCE_BYTES);
    defer allocator.free(bytes);
    return try words_from_spirv_bytes(allocator, bytes);
}

pub fn load_kernel_spirv_cached(self: anytype, kernel_name: []const u8) ![]const u32 {
    return ensure_kernel_spirv_cached(self, kernel_name);
}

fn compile_kernel_wgsl_to_spirv(self: anytype, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
    const source_path = try resolve_kernel_path(self, allocator, kernel_name);
    defer allocator.free(source_path);
    if (!std.mem.endsWith(u8, source_path, ".wgsl")) return error.UnsupportedFeature;

    const wgsl = try std.fs.cwd().readFileAlloc(allocator, source_path, MAX_KERNEL_SOURCE_BYTES);
    defer allocator.free(wgsl);

    var spirv_buf = try allocator.alloc(u8, spirv_translation.MAX_OUTPUT);
    defer allocator.free(spirv_buf);
    const spirv_len = spirv_translation.translateToSpirv(allocator, wgsl, spirv_buf) catch |err| switch (err) {
        error.OutOfMemory => return err,
        else => return error.ShaderCompileFailed,
    };
    return try words_from_spirv_bytes(allocator, spirv_buf[0..spirv_len]);
}

pub fn words_from_spirv_bytes(allocator: std.mem.Allocator, bytes: []const u8) ![]u32 {
    if (bytes.len == 0 or (bytes.len % 4) != 0) return error.ShaderCompileFailed;

    const words = try allocator.alloc(u32, bytes.len / 4);
    errdefer allocator.free(words);
    for (words, 0..) |*word, i| {
        const start = i * 4;
        const chunk: *const [4]u8 = @ptrCast(bytes[start .. start + 4].ptr);
        word.* = std.mem.readInt(u32, chunk, .little);
    }
    if (words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
    return words;
}

fn resolve_kernel_path(self: anytype, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
    {
        const direct = try allocator.dupe(u8, kernel_name);
        errdefer allocator.free(direct);
        if (try path_utils.file_exists(direct)) return direct;
        allocator.free(direct);
    }

    const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
    {
        const rooted = try std.fmt.allocPrint(allocator, "{s}/{s}", .{ root, kernel_name });
        errdefer allocator.free(rooted);
        if (try path_utils.file_exists(rooted)) return rooted;
        allocator.free(rooted);
    }

    if (!std.mem.endsWith(u8, kernel_name, ".wgsl")) {
        {
            const with_suffix = try std.fmt.allocPrint(allocator, "{s}/{s}.wgsl", .{ root, kernel_name });
            errdefer allocator.free(with_suffix);
            if (try path_utils.file_exists(with_suffix)) return with_suffix;
            allocator.free(with_suffix);
        }
    }
    return error.ShaderToolchainUnavailable;
}

fn resolve_kernel_spirv_path(self: anytype, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
    const source_path = try resolve_kernel_path(self, allocator, kernel_name);
    defer allocator.free(source_path);

    if (std.mem.endsWith(u8, source_path, ".spv") or std.mem.endsWith(u8, source_path, ".spirv")) {
        return try allocator.dupe(u8, source_path);
    }

    {
        const sibling_spv = try std.fmt.allocPrint(allocator, "{s}.spv", .{source_path});
        errdefer allocator.free(sibling_spv);
        if (try path_utils.file_exists(sibling_spv)) return sibling_spv;
        allocator.free(sibling_spv);
    }

    const extension = std.fs.path.extension(source_path);
    if (extension.len != 0) {
        {
            const replaced = try std.fmt.allocPrint(allocator, "{s}.spv", .{source_path[0 .. source_path.len - extension.len]});
            errdefer allocator.free(replaced);
            if (try path_utils.file_exists(replaced)) return replaced;
            allocator.free(replaced);
        }
    }

    return error.UnsupportedFeature;
}

fn exerciseCacheAllocation(allocator: std.mem.Allocator) !void {
    var temporary = std.testing.tmpDir(.{});
    defer temporary.cleanup();
    const root = try temporary.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    try temporary.dir.writeFile(.{ .sub_path = "probe.spv", .data = &.{ 3, 2, 35, 7 } });
    const Fixture = struct {
        allocator: std.mem.Allocator,
        kernel_root: ?[]const u8,
        kernel_spirv_cache: std.StringHashMapUnmanaged([]u32) = .{},
    };
    var fixture = Fixture{ .allocator = allocator, .kernel_root = root };
    defer release_kernel_spirv_cache(&fixture);
    const first = try ensure_kernel_spirv_cached(&fixture, "probe.spv");
    const second = try ensure_kernel_spirv_cached(&fixture, "probe.spv");
    try std.testing.expectEqual(@as(u32, SPIRV_MAGIC), first[0]);
    try std.testing.expect(first.ptr == second.ptr);
}

test "SPIR-V cache admission releases loaded words on allocation failure" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseCacheAllocation, .{});
}

fn exerciseWgslAllocation(allocator: std.mem.Allocator) !void {
    const Fixture = struct { kernel_root: ?[]const u8 };
    var temporary = std.testing.tmpDir(.{});
    defer temporary.cleanup();
    const root = try temporary.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    const source = "@compute @workgroup_size(1) fn main() {}";
    try temporary.dir.writeFile(.{ .sub_path = "probe.wgsl", .data = source });
    const fixture = Fixture{ .kernel_root = root };
    const loaded = try load_kernel_source(&fixture, allocator, "probe.wgsl");
    defer allocator.free(loaded);
    try std.testing.expectEqualStrings(source, loaded);
    const words = try load_kernel_spirv(&fixture, allocator, "probe.wgsl");
    defer allocator.free(words);
    try std.testing.expectEqual(SPIRV_MAGIC, words[0]);
}

test "WGSL source loading and compilation preserve allocation failures" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseWgslAllocation, .{});
}

test "SPIR-V sibling resolution never treats a parent directory suffix as a file extension" {
    var temporary = std.testing.tmpDir(.{});
    defer temporary.cleanup();
    try temporary.dir.makeDir("kernels.version");
    try temporary.dir.writeFile(.{ .sub_path = "kernels.version/probe", .data = "source" });
    try temporary.dir.writeFile(.{ .sub_path = "kernels.spv", .data = "unrelated" });
    const root = try temporary.dir.realpathAlloc(std.testing.allocator, "kernels.version");
    defer std.testing.allocator.free(root);
    const fixture = .{ .kernel_root = @as(?[]const u8, root) };
    try std.testing.expectError(error.UnsupportedFeature, resolve_kernel_spirv_path(&fixture, std.testing.allocator, "probe"));
    try temporary.dir.writeFile(.{ .sub_path = "kernels.version/probe.spv", .data = "sibling" });
    const resolved = try resolve_kernel_spirv_path(&fixture, std.testing.allocator, "probe");
    defer std.testing.allocator.free(resolved);
    try std.testing.expect(std.mem.endsWith(u8, resolved, "/kernels.version/probe.spv"));
}
