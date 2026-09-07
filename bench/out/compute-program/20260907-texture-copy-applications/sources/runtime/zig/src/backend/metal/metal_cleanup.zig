// metal_cleanup.zig — Resource release and cleanup helpers for NativeMetalRuntime.
// Sharded from metal_native_runtime.zig to stay under the line-limit policy.

const std = @import("std");
const bridge = @import("metal_bridge_decls.zig");
const metal_bridge_release = bridge.metal_bridge_release;

pub const BufferPoolMap = std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque));

pub inline fn release_ref(ref: *?*anyopaque) void {
    if (ref.*) |obj| {
        metal_bridge_release(obj);
        ref.* = null;
    }
}

pub fn release_deferred(deferred_releases: *std.ArrayListUnmanaged(?*anyopaque)) void {
    for (deferred_releases.items) |obj| metal_bridge_release(obj);
    deferred_releases.clearRetainingCapacity();
}

pub fn release_buffer_pool(allocator: std.mem.Allocator, pool: *BufferPoolMap) void {
    var it = pool.valueIterator();
    while (it.next()) |list| {
        for (list.items) |buf| metal_bridge_release(buf);
        var m = list.*;
        m.deinit(allocator);
    }
    pool.deinit(allocator);
}

pub fn release_kernel_pipelines(self: anytype) void {
    var it = self.kernel_pipelines.iterator();
    while (it.next()) |e| {
        self.allocator.free(e.key_ptr.*);
        metal_bridge_release(e.value_ptr.library);
        metal_bridge_release(e.value_ptr.pipeline);
    }
    self.kernel_pipelines.deinit(self.allocator);
}

pub fn release_compute_buffers(self: anytype) void {
    var it = self.compute_buffers.valueIterator();
    while (it.next()) |v| metal_bridge_release(v.*);
    self.compute_buffers.deinit(self.allocator);
}

pub fn release_textures(self: anytype) void {
    var it = self.textures.valueIterator();
    while (it.next()) |v| metal_bridge_release(v.*);
    self.textures.deinit(self.allocator);
}

/// Release all sampler handles in the map. Handles owned by the sampler cache
/// are skipped (the cache owns their Metal reference and releases them during
/// its own deinit). Non-cached handles are released directly.
pub fn release_samplers(self: anytype) void {
    var it = self.samplers.valueIterator();
    while (it.next()) |v| {
        if (!self.sampler_cache.release(v.*)) {
            metal_bridge_release(v.*);
        }
    }
    self.samplers.deinit(self.allocator);
}

pub fn release_surfaces(self: anytype) void {
    var it = self.surfaces.valueIterator();
    while (it.next()) |state| {
        if (state.texture) |texture| metal_bridge_release(texture);
    }
    self.surfaces.deinit(self.allocator);
}

pub fn release_render_resources(self: anytype) void {
    release_ref(&self.cached_icb);
    release_ref(&self.render_pipeline);
    release_ref(&self.render_target);
    self.render_pipeline_format = 0;
}
