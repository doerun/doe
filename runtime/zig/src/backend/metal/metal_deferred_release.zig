//! Batched release of retired native references and runtime-owned sampler reuse.
//! The caller must retire GPU uses before enqueue, release, eviction, or deinit.

const std = @import("std");
const bridge = @import("metal_bridge_decls.zig");
const model_render_types = @import("../../contracts/model/model_render_types.zig");
const metal_bridge_release = bridge.metal_bridge_release;

const model = struct {
    pub const SamplerCreateCommand = model_render_types.SamplerCreateCommand;
};

// ============================================================
// Constants
// ============================================================

/// Maximum pending releases before forced drain. Sized to cover the typical
/// texture_sampler_write_query_destroy command stream (2 destroys per iteration
/// x 10 repeats = 20) with headroom for surface/render target churn.
const DEFERRED_RING_CAPACITY: usize = 64;

/// Maximum unique sampler descriptor tuples cached. Metal sampler state objects
/// are immutable and lightweight; caching avoids alloc/dealloc churn. 16 covers
/// the practical range of filter/address/LOD combinations in Doppler workloads.
const SAMPLER_CACHE_CAPACITY: usize = 16;

// ============================================================
// Deferred release ring buffer
// ============================================================

pub const DeferredReleasePool = struct {
    ring: [DEFERRED_RING_CAPACITY]?*anyopaque = [_]?*anyopaque{null} ** DEFERRED_RING_CAPACITY,
    count: usize = 0,

    /// Enqueue a Metal object for deferred release. If the ring is full,
    /// drain all pending releases first to maintain the invariant.
    pub fn enqueue(self: *DeferredReleasePool, obj: ?*anyopaque) void {
        if (obj == null) return;
        if (self.count >= DEFERRED_RING_CAPACITY) {
            self.drain();
        }
        self.ring[self.count] = obj;
        self.count += 1;
    }

    /// Batch-release all pending objects. Called at command buffer boundaries
    /// (flush_queue_timed) and during runtime teardown (deinit).
    pub fn drain(self: *DeferredReleasePool) void {
        const n = self.count;
        if (n == 0) return;
        // Tight release loop — single call site, branch-free interior.
        for (self.ring[0..n]) |obj| {
            metal_bridge_release(obj);
        }
        // Zero the drained slots to avoid dangling pointers.
        @memset(self.ring[0..n], null);
        self.count = 0;
    }

    /// Number of objects waiting for release.
    pub fn pending(self: *const DeferredReleasePool) usize {
        return self.count;
    }
};

// ============================================================
// Sampler descriptor cache
// ============================================================

/// Compact representation of a sampler descriptor for cache keying.
/// Equality compares fields, independently of struct padding.
pub const SamplerDescKey = struct {
    min_filter: u32,
    mag_filter: u32,
    mipmap_filter: u32,
    address_mode_u: u32,
    address_mode_v: u32,
    address_mode_w: u32,
    lod_min_clamp_bits: u32,
    lod_max_clamp_bits: u32,
    compare: u32,
    max_anisotropy: u16,

    pub fn from_cmd(cmd: model.SamplerCreateCommand) SamplerDescKey {
        return .{
            .min_filter = cmd.min_filter,
            .mag_filter = cmd.mag_filter,
            .mipmap_filter = cmd.mipmap_filter,
            .address_mode_u = cmd.address_mode_u,
            .address_mode_v = cmd.address_mode_v,
            .address_mode_w = cmd.address_mode_w,
            .lod_min_clamp_bits = @bitCast(cmd.lod_min_clamp),
            .lod_max_clamp_bits = @bitCast(cmd.lod_max_clamp),
            .compare = cmd.compare,
            .max_anisotropy = cmd.max_anisotropy,
        };
    }
};

const SamplerCacheEntry = struct {
    key: SamplerDescKey,
    handle: ?*anyopaque,
    ref_count: u32,
};

pub const SamplerCache = struct {
    device_identity: ?*anyopaque = null,
    entries: [SAMPLER_CACHE_CAPACITY]SamplerCacheEntry = undefined,
    len: usize = 0,

    pub fn init() SamplerCache {
        var cache = SamplerCache{};
        for (&cache.entries) |*e| {
            e.* = .{ .key = std.mem.zeroes(SamplerDescKey), .handle = null, .ref_count = 0 };
        }
        return cache;
    }

    /// Look up or create a Metal sampler matching the given descriptor.
    /// Returns the cached handle (shared, NOT +1 retained for the caller —
    /// the cache owns the single Metal reference). The caller must call
    /// release() with the returned handle when done. Uncached handles transfer
    /// a native reference: release() returns false and the caller releases it.
    pub fn acquire(self: *SamplerCache, device: ?*anyopaque, cmd: model.SamplerCreateCommand) !?*anyopaque {
        return self.acquireWithBridge(device, cmd, bridge);
    }

    fn acquireWithBridge(self: *SamplerCache, device: ?*anyopaque, cmd: model.SamplerCreateCommand, comptime native: type) !?*anyopaque {
        if (self.len != 0 and self.device_identity != device) return error.InvalidArgument;
        const key = SamplerDescKey.from_cmd(cmd);

        // Scan for existing entry with matching key.
        for (self.entries[0..self.len]) |*entry| {
            if (std.meta.eql(entry.key, key)) {
                entry.ref_count = std.math.add(u32, entry.ref_count, 1) catch return error.InvalidState;
                return entry.handle;
            }
        }

        // Cache miss: create new Metal sampler.
        const handle = native.metal_bridge_device_new_sampler_with_compare(
            device,
            cmd.min_filter,
            cmd.mag_filter,
            cmd.mipmap_filter,
            cmd.address_mode_u,
            cmd.address_mode_v,
            cmd.address_mode_w,
            cmd.lod_min_clamp,
            cmd.lod_max_clamp,
            cmd.compare,
            cmd.max_anisotropy,
        ) orelse return error.InvalidState;

        // If cache is full, evict the entry with ref_count == 0 (LRU-ish).
        if (self.len >= SAMPLER_CACHE_CAPACITY) {
            var evict_idx: ?usize = null;
            for (self.entries[0..self.len], 0..) |*entry, i| {
                if (entry.ref_count == 0) {
                    evict_idx = i;
                    break;
                }
            }
            if (evict_idx) |idx| {
                native.metal_bridge_release(self.entries[idx].handle);
                self.entries[idx] = .{ .key = key, .handle = handle, .ref_count = 1 };
                return handle;
            }
            // All entries in use — cannot cache, return uncached handle.
            // Caller manages this handle directly.
            return handle;
        }

        self.device_identity = device;
        self.entries[self.len] = .{ .key = key, .handle = handle, .ref_count = 1 };
        self.len += 1;
        return handle;
    }

    /// Release a reference to a cached sampler. If the ref count drops to
    /// zero, the entry remains in cache for future reuse (lazy eviction).
    /// Returns true if the handle is cache-managed (caller should NOT release
    /// it via metal_bridge_release). Returns false if the handle was not found
    /// in cache (caller must release it directly).
    pub fn release(self: *SamplerCache, handle: ?*anyopaque) bool {
        if (handle == null) return false;
        for (self.entries[0..self.len]) |*entry| {
            if (entry.handle == handle) {
                entry.ref_count -|= 1;
                return true;
            }
        }
        return false;
    }

    /// Release all cached Metal sampler objects. Called during runtime teardown.
    pub fn deinit(self: *SamplerCache) void {
        self.deinitWithBridge(bridge);
    }

    fn deinitWithBridge(self: *SamplerCache, comptime native: type) void {
        for (self.entries[0..self.len]) |*entry| {
            if (entry.handle != null) {
                native.metal_bridge_release(entry.handle);
                entry.handle = null;
            }
        }
        self.len = 0;
        self.device_identity = null;
    }
};

test "sampler cache preserves comparison identity and device ownership" {
    const Probe = struct {
        const Sampler = struct { device: ?*anyopaque, compare: u32 };
        var samplers: [SAMPLER_CACHE_CAPACITY + 6]Sampler = undefined;
        var count: usize = 0;
        var releases: usize = 0;
        var fail_create = false;
        fn metal_bridge_device_new_sampler_with_compare(device: ?*anyopaque, _: u32, _: u32, _: u32, _: u32, _: u32, _: u32, _: f32, _: f32, compare: u32, _: u16) ?*anyopaque {
            if (fail_create) return null;
            samplers[count] = .{ .device = device, .compare = compare };
            defer count += 1;
            return &samplers[count];
        }
        fn metal_bridge_release(_: ?*anyopaque) void {
            releases += 1;
        }
    };
    Probe.count = 0;
    Probe.releases = 0;
    var first_device: u8 = 0;
    var second_device: u8 = 0;
    var first = SamplerCache.init();
    var second = SamplerCache.init();
    const descriptor: model.SamplerCreateCommand = .{ .handle = 1, .compare = 2 };
    const less = try first.acquireWithBridge(&first_device, descriptor, Probe);
    var changed = descriptor;
    changed.compare = 5;
    const greater = try first.acquireWithBridge(&first_device, changed, Probe);
    try std.testing.expect(less != greater);
    try std.testing.expectEqual(@as(u32, 2), Probe.samplers[0].compare);
    try std.testing.expectEqual(@as(u32, 5), Probe.samplers[1].compare);
    try std.testing.expectEqual(less, try first.acquireWithBridge(&first_device, descriptor, Probe));
    try std.testing.expectEqual(@as(usize, 2), Probe.count);
    try std.testing.expectError(error.InvalidArgument, first.acquireWithBridge(&second_device, descriptor, Probe));
    const other = try second.acquireWithBridge(&second_device, descriptor, Probe);
    try std.testing.expect(other != less);
    try std.testing.expectEqual(@as(?*anyopaque, &second_device), Probe.samplers[2].device);
    Probe.fail_create = true;
    changed.lod_max_clamp += 1;
    try std.testing.expectError(error.InvalidState, first.acquireWithBridge(&first_device, changed, Probe));
    Probe.fail_create = false;
    try std.testing.expectEqual(@as(usize, 2), first.len);
    first.entries[0].ref_count = std.math.maxInt(u32);
    try std.testing.expectError(error.InvalidState, first.acquireWithBridge(&first_device, descriptor, Probe));
    first.entries[0].ref_count = 2;
    try std.testing.expect(first.release(less));
    try std.testing.expect(first.release(less));
    try std.testing.expect(first.release(greater));
    try std.testing.expect(second.release(other));
    first.deinitWithBridge(Probe);
    second.deinitWithBridge(Probe);
    try std.testing.expectEqual(@as(usize, 3), Probe.releases);
    try std.testing.expectEqual(@as(?*anyopaque, null), first.device_identity);
    for (0..SAMPLER_CACHE_CAPACITY) |i| {
        changed.lod_max_clamp = @floatFromInt(i + 1);
        _ = try first.acquireWithBridge(&first_device, changed, Probe);
    }
    changed.lod_max_clamp = 100;
    const uncached = try first.acquireWithBridge(&first_device, changed, Probe);
    try std.testing.expect(!first.release(uncached));
    Probe.metal_bridge_release(uncached);
    try std.testing.expectEqual(@as(usize, 4), Probe.releases);
    try std.testing.expect(first.release(first.entries[0].handle));
    _ = try first.acquireWithBridge(&first_device, changed, Probe);
    try std.testing.expectEqual(@as(usize, 5), Probe.releases);
    try std.testing.expectEqual(@as(usize, SAMPLER_CACHE_CAPACITY), first.len);
    first.deinitWithBridge(Probe);
    try std.testing.expectEqual(Probe.count, Probe.releases);
}
