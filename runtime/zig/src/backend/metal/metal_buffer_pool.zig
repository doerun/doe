// metal_buffer_pool.zig — Buffer pool helpers for NativeMetalRuntime.
// Sharded from metal_native_runtime.zig to stay under the 777-line limit.

const std = @import("std");

extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;

pub const MAX_POOL_ENTRIES_PER_SIZE: usize = 8;
pub const BufferPool = std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque));

pub fn pool_pop(pool: *BufferPool, size: usize) ?*anyopaque {
    if (pool.getPtr(size)) |list| {
        if (list.items.len > 0) return list.pop() orelse null;
    }
    return null;
}

pub fn pool_push_or_release(pool: *BufferPool, allocator: std.mem.Allocator, size: usize, buf: ?*anyopaque) void {
    const entry = pool.getOrPut(allocator, size) catch {
        metal_bridge_release(buf);
        return;
    };
    if (!entry.found_existing) {
        entry.value_ptr.* = .{};
    }
    if (entry.value_ptr.items.len >= MAX_POOL_ENTRIES_PER_SIZE) {
        metal_bridge_release(buf);
        return;
    }
    entry.value_ptr.append(allocator, buf) catch {
        metal_bridge_release(buf);
    };
}

pub fn strip_extension(name: []const u8) []const u8 {
    const suffixes = [_][]const u8{ ".wgsl", ".spv", ".metal" };
    for (suffixes) |sfx| {
        if (std.mem.endsWith(u8, name, sfx)) return name[0 .. name.len - sfx.len];
    }
    return name;
}
