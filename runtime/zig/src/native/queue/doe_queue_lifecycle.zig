const builtin = @import("builtin");
const std = @import("std");
const abi_core = @import("../../core/abi/wgpu_core_base_types.zig");
const abi_callback = @import("../../core/abi/wgpu_callback_descriptor_types.zig");
const pipeline_cache_ops = @import("../../backend/dropin_pipeline_cache.zig");
const queue_submit_ops = @import("../../backend/dropin_queue_submit.zig");
const native_types = @import("../support/doe_native_object_types.zig");
const shared_types = @import("../support/doe_native_shared_types.zig");
const native_helpers = @import("../support/doe_native_object_helpers.zig");
const native_rt_helpers = @import("../support/doe_native_runtime_helpers.zig");
const native_exports = @import("../support/doe_native_exports.zig");
const queue_flush_breakdown = @import("doe_queue_flush_breakdown.zig");
const shared = @import("doe_queue_submit_shared.zig");
const callback_dispatch = @import("../../runtime/callback_dispatch.zig");

const has_vulkan = (builtin.os.tag == .linux);
const alloc = native_helpers.alloc;
const cast = native_helpers.cast;
const toOpaque = native_helpers.toOpaque;
const DoeQueue = native_types.DoeQueue;
const metal_bridge = queue_submit_ops.metal_bridge;

const QUEUE_SYNC_INFO_BACKEND_VULKAN: u32 = 1 << 0;
const QUEUE_SYNC_INFO_TIMELINE_SEMAPHORE: u32 = 1 << 1;
const QUEUE_SYNC_INFO_FENCE_POOL: u32 = 1 << 2;
const QUEUE_SYNC_INFO_DEFERRED_SUBMISSIONS: u32 = 1 << 3;
const QUEUE_PIPELINE_CACHE_INFO_BACKEND_VULKAN: u32 = 1 << 0;
const QUEUE_PIPELINE_CACHE_INFO_ACTIVE: u32 = 1 << 1;
const QUEUE_PIPELINE_CACHE_INFO_DISABLED: u32 = 1 << 2;
const QUEUE_PIPELINE_CACHE_INFO_SUPPORTED: u32 = 1 << 3;
const QUEUE_FAMILY_UNAVAILABLE: u32 = 0xffff_ffff;
const QUEUE_FAMILY_POLICY_PREFER_GRAPHICS_COMPUTE: u32 = 0;
const QUEUE_FAMILY_POLICY_PREFER_COMPUTE_ONLY: u32 = 1;
const QUEUE_FAMILY_POLICY_REQUIRE_COMPUTE_ONLY: u32 = 2;
const QUEUE_FAMILY_KIND_GRAPHICS_COMPUTE: u32 = 0;
const QUEUE_FAMILY_KIND_COMPUTE_ONLY: u32 = 1;
const DEFERRED_SYNC_POLICY_PREFER_TIMELINE_SEMAPHORE: u32 = 0;
const DEFERRED_SYNC_POLICY_REQUIRE_FENCE_POOL: u32 = 1;

pub fn doeNativeQueueFlush(q_raw: ?*anyopaque) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return;
            _ = rt.flush_queue() catch |err| {
                shared.deliverInternalError(q.dev, "doe_queue_submit: queue flush: {s}", .{@errorName(err)});
            };
        }
        return;
    }
    if (q.dev.backend == .d3d12) {
        if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
            _ = rt.flush_queue() catch |err| {
                shared.deliverInternalError(q.dev, "doe_queue_submit: d3d12 queue flush: {s}", .{@errorName(err)});
            };
        }
        return;
    }
    shared.flush_pending_work(q);
}

pub fn doeNativeQueueFlushBreakdown(
    q_raw: ?*anyopaque,
    wait_completed_ns_out: *u64,
    deferred_copy_ns_out: *u64,
    deferred_resolve_ns_out: *u64,
) void {
    const q = cast(DoeQueue, q_raw) orelse {
        wait_completed_ns_out.* = 0;
        deferred_copy_ns_out.* = 0;
        deferred_resolve_ns_out.* = 0;
        return;
    };
    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
                wait_completed_ns_out.* = rt.flush_queue() catch |err| blk: {
                    shared.deliverInternalError(q.dev, "doe_queue_submit: vulkan flush breakdown: {s}", .{@errorName(err)});
                    break :blk 0;
                };
            } else {
                wait_completed_ns_out.* = 0;
            }
        } else {
            wait_completed_ns_out.* = 0;
        }
        deferred_copy_ns_out.* = 0;
        deferred_resolve_ns_out.* = 0;
        return;
    }
    if (q.dev.backend == .d3d12) {
        if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
            wait_completed_ns_out.* = rt.flush_queue() catch |err| blk: {
                shared.deliverInternalError(q.dev, "doe_queue_submit: d3d12 flush breakdown: {s}", .{@errorName(err)});
                break :blk 0;
            };
        } else {
            wait_completed_ns_out.* = 0;
        }
        deferred_copy_ns_out.* = 0;
        deferred_resolve_ns_out.* = 0;
        return;
    }
    const breakdown = queue_flush_breakdown.flushPendingWorkTimed(q);
    wait_completed_ns_out.* = breakdown.waitCompletedNs;
    deferred_copy_ns_out.* = breakdown.deferredCopyNs;
    deferred_resolve_ns_out.* = breakdown.deferredResolveNs;
}

pub fn doeNativeQueueSyncInfo(q_raw: ?*anyopaque) u32 {
    const q = cast(DoeQueue, q_raw) orelse return 0;
    if (q.dev.backend != .vulkan) return 0;
    var bits: u32 = QUEUE_SYNC_INFO_BACKEND_VULKAN;
    if (comptime has_vulkan) {
        if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
            if (rt.timeline_semaphore_available()) bits |= QUEUE_SYNC_INFO_TIMELINE_SEMAPHORE;
            if (rt.has_fence_pool) bits |= QUEUE_SYNC_INFO_FENCE_POOL;
            if (rt.has_deferred_submissions) bits |= QUEUE_SYNC_INFO_DEFERRED_SUBMISSIONS;
        }
    }
    return bits;
}

pub fn doeNativeQueuePipelineCacheInfo(q_raw: ?*anyopaque) u32 {
    const q = cast(DoeQueue, q_raw) orelse return 0;
    if (q.dev.backend != .vulkan) return 0;
    var bits: u32 = QUEUE_PIPELINE_CACHE_INFO_BACKEND_VULKAN | QUEUE_PIPELINE_CACHE_INFO_SUPPORTED;
    if (comptime has_vulkan) {
        if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
            if (pipeline_cache_ops.vulkanPipelineCacheActive(rt)) bits |= QUEUE_PIPELINE_CACHE_INFO_ACTIVE;
            if (pipeline_cache_ops.vulkanPipelineCacheDisabled(rt)) bits |= QUEUE_PIPELINE_CACHE_INFO_DISABLED;
        }
    }
    return bits;
}

pub fn doeNativeQueuePipelineCacheWarmupCount(q_raw: ?*anyopaque) u64 {
    const q = cast(DoeQueue, q_raw) orelse return 0;
    if (q.dev.backend != .vulkan) return 0;
    if (comptime has_vulkan) {
        if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
            return pipeline_cache_ops.vulkanPipelineCacheWarmupTelemetry(rt).count;
        }
    }
    return 0;
}

pub fn doeNativeQueuePipelineCacheWarmupNs(q_raw: ?*anyopaque) u64 {
    const q = cast(DoeQueue, q_raw) orelse return 0;
    if (q.dev.backend != .vulkan) return 0;
    if (comptime has_vulkan) {
        if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
            return pipeline_cache_ops.vulkanPipelineCacheWarmupTelemetry(rt).ns;
        }
    }
    return 0;
}

pub fn doeNativeQueuePipelineCacheFlush(q_raw: ?*anyopaque) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    if (q.dev.backend != .vulkan) return;
    if (comptime has_vulkan) {
        if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
            pipeline_cache_ops.flushVulkanPipelineCache(rt);
        }
    }
}

fn queueVulkanRuntime(q_raw: ?*anyopaque) ?*shared_types.NativeVulkanRuntime {
    const q = cast(DoeQueue, q_raw) orelse return null;
    if (q.dev.backend != .vulkan) return null;
    if (comptime has_vulkan) {
        return native_rt_helpers.device_vk_runtime(q.dev);
    }
    return null;
}

pub fn doeNativeQueueFamilyPolicyCode(q_raw: ?*anyopaque) u32 {
    if (comptime !has_vulkan) return QUEUE_FAMILY_UNAVAILABLE;
    const rt = queueVulkanRuntime(q_raw) orelse return QUEUE_FAMILY_UNAVAILABLE;
    return switch (rt.queue_family_policy) {
        .prefer_graphics_compute => QUEUE_FAMILY_POLICY_PREFER_GRAPHICS_COMPUTE,
        .prefer_compute_only => QUEUE_FAMILY_POLICY_PREFER_COMPUTE_ONLY,
        .require_compute_only => QUEUE_FAMILY_POLICY_REQUIRE_COMPUTE_ONLY,
    };
}

pub fn doeNativeQueueDeferredSubmissionSyncPolicyCode(q_raw: ?*anyopaque) u32 {
    if (comptime !has_vulkan) return QUEUE_FAMILY_UNAVAILABLE;
    const rt = queueVulkanRuntime(q_raw) orelse return QUEUE_FAMILY_UNAVAILABLE;
    return switch (rt.deferred_submission_sync_policy) {
        .prefer_timeline_semaphore => DEFERRED_SYNC_POLICY_PREFER_TIMELINE_SEMAPHORE,
        .require_fence_pool => DEFERRED_SYNC_POLICY_REQUIRE_FENCE_POOL,
    };
}

pub fn doeNativeQueueFamilyKindCode(q_raw: ?*anyopaque) u32 {
    if (comptime !has_vulkan) return QUEUE_FAMILY_UNAVAILABLE;
    const rt = queueVulkanRuntime(q_raw) orelse return QUEUE_FAMILY_UNAVAILABLE;
    const kind = rt.queue_family_kind_value_cache orelse return QUEUE_FAMILY_UNAVAILABLE;
    return switch (kind) {
        .graphics_compute => QUEUE_FAMILY_KIND_GRAPHICS_COMPUTE,
        .compute_only => QUEUE_FAMILY_KIND_COMPUTE_ONLY,
    };
}

pub fn doeNativeQueueFamilyIndex(q_raw: ?*anyopaque) u32 {
    if (comptime !has_vulkan) return QUEUE_FAMILY_UNAVAILABLE;
    const rt = queueVulkanRuntime(q_raw) orelse return QUEUE_FAMILY_UNAVAILABLE;
    return rt.queue_family_index_value_cache orelse QUEUE_FAMILY_UNAVAILABLE;
}

pub fn doeNativeQueueFamilyQueueCount(q_raw: ?*anyopaque) u32 {
    if (comptime !has_vulkan) return QUEUE_FAMILY_UNAVAILABLE;
    const rt = queueVulkanRuntime(q_raw) orelse return QUEUE_FAMILY_UNAVAILABLE;
    return rt.queue_family_queue_count_value_cache orelse QUEUE_FAMILY_UNAVAILABLE;
}

pub fn doeNativeQueueFamilyTimestampValidBits(q_raw: ?*anyopaque) u32 {
    if (comptime !has_vulkan) return QUEUE_FAMILY_UNAVAILABLE;
    const rt = queueVulkanRuntime(q_raw) orelse return QUEUE_FAMILY_UNAVAILABLE;
    return rt.queue_family_timestamp_valid_bits_value_cache orelse QUEUE_FAMILY_UNAVAILABLE;
}

pub fn doeNativeQueueFamilySupportsGraphics(q_raw: ?*anyopaque) u32 {
    if (comptime !has_vulkan) return QUEUE_FAMILY_UNAVAILABLE;
    const rt = queueVulkanRuntime(q_raw) orelse return QUEUE_FAMILY_UNAVAILABLE;
    const supports_graphics = rt.queue_family_supports_graphics_value_cache orelse return QUEUE_FAMILY_UNAVAILABLE;
    return if (supports_graphics) 1 else 0;
}

pub fn doeNativeQueueRelease(raw: ?*anyopaque) void {
    const q = cast(DoeQueue, raw) orelse return;
    if (!native_helpers.object_should_destroy(q)) return;
    native_helpers.label_store.remove(raw);
    if (q.dev.queue == q) {
        q.dev.queue = null;
    }
    // Backend-specific drain of any in-flight GPU work before we release the
    // device reference. The common teardown at the bottom runs for every path.
    switch (q.dev.backend) {
        .vulkan => {
            if (comptime has_vulkan) {
                if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
                    _ = rt.flush_queue() catch |err| {
                        shared.deliverInternalError(q.dev, "doe_queue_submit: flush on queue release: {s}", .{@errorName(err)});
                    };
                }
            }
        },
        .d3d12 => {
            if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
                _ = rt.flush_queue() catch |err| {
                    shared.deliverInternalError(q.dev, "doe_queue_submit: d3d12 flush on queue release: {s}", .{@errorName(err)});
                };
            }
        },
        else => {
            shared.flush_pending_work_dropin_sync(q);
            if (q.mtl_event) |ev| metal_bridge.metal_bridge_release(ev);
        },
    }
    const dev = q.dev;
    alloc.destroy(q);
    native_exports.doeNativeDeviceRelease(toOpaque(dev));
}

pub fn doeNativeQueueAddRef(raw: ?*anyopaque) void {
    native_helpers.object_add_ref(DoeQueue, raw);
}

const MAX_GLOBAL_WORK_DONE: usize = 128;
const WORK_DONE_FUTURE_ID_BASE: u64 = 4;
const WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS: u32 = 0x00000002;
const WGPU_CALLBACK_MODE_ALLOW_SPONTANEOUS: u32 = 0x00000003;

const WorkDoneEntry = struct {
    cb: ?*const fn (abi_callback.WGPUQueueWorkDoneStatus, abi_core.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

// This compatibility registry owns pending callback records process-wide.
// Transfer a batch under the mutex; invoke foreign callbacks after unlocking.
var global_work_done_mutex: std.Thread.Mutex = .{};
var global_work_done_buf: [MAX_GLOBAL_WORK_DONE]WorkDoneEntry = undefined;
var global_work_done_count: usize = 0;
var global_work_done_future_id: u64 = WORK_DONE_FUTURE_ID_BASE;

fn shouldDispatchSpontaneousMetalWorkDone(
    q: *const DoeQueue,
    info: abi_callback.WGPUQueueWorkDoneCallbackInfo,
) bool {
    return q.dev.backend == .metal and
        info.mode == WGPU_CALLBACK_MODE_ALLOW_SPONTANEOUS and
        info.callback != null;
}

fn next_work_done_future() abi_core.WGPUFuture {
    global_work_done_mutex.lock();
    defer global_work_done_mutex.unlock();
    const id = global_work_done_future_id;
    global_work_done_future_id +%= 1;
    if (global_work_done_future_id == 0) global_work_done_future_id = WORK_DONE_FUTURE_ID_BASE;
    return .{ .id = id };
}

fn enqueue_global_work_done(info: abi_callback.WGPUQueueWorkDoneCallbackInfo) bool {
    if (info.callback == null) return true;
    global_work_done_mutex.lock();
    defer global_work_done_mutex.unlock();
    if (global_work_done_count >= MAX_GLOBAL_WORK_DONE) return false;
    global_work_done_buf[global_work_done_count] = .{
        .cb = info.callback,
        .userdata1 = info.userdata1,
        .userdata2 = info.userdata2,
    };
    global_work_done_count += 1;
    return true;
}

pub fn drain_global_work_done() void {
    var batch: [MAX_GLOBAL_WORK_DONE]WorkDoneEntry = undefined;
    global_work_done_mutex.lock();
    const n = global_work_done_count;
    @memcpy(batch[0..n], global_work_done_buf[0..n]);
    global_work_done_count = 0;
    global_work_done_mutex.unlock();
    for (batch[0..n]) |entry| {
        if (entry.cb) |f| {
            f(.success, .{ .data = null, .length = 0 }, entry.userdata1, entry.userdata2);
        }
    }
}

pub fn doeNativeQueueOnSubmittedWorkDone(q_raw: ?*anyopaque, info: abi_callback.WGPUQueueWorkDoneCallbackInfo) abi_core.WGPUFuture {
    const future = next_work_done_future();
    if (cast(DoeQueue, q_raw)) |q| {
        if (shouldDispatchSpontaneousMetalWorkDone(q, info)) {
            // Complete the queue state, including deferred copies, resolves,
            // releases, and the retained command buffer, before the callback
            // makes the queue reusable from JavaScript. The shared-event-only
            // path acknowledged the GPU signal without finalizing this state.
            shared.flush_pending_work_dropin_sync(q);
            callback_dispatch.dispatch_work_done_callback(
                info.callback,
                info.userdata1,
                info.userdata2,
            );
            return future;
        }
        shared.flush_pending_work_dropin_sync(q);
    }
    if (info.mode == WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS and enqueue_global_work_done(info)) {
        return future;
    }
    if (info.callback) |cb| {
        cb(.success, .{ .data = null, .length = 0 }, info.userdata1, info.userdata2);
    }
    return future;
}

fn testWorkDoneCallback(
    _: abi_callback.WGPUQueueWorkDoneStatus,
    _: abi_core.WGPUStringView,
    _: ?*anyopaque,
    _: ?*anyopaque,
) callconv(.c) void {}

test "spontaneous Metal completion uses finalized asynchronous dispatch" {
    const testing = @import("std").testing;
    var device = native_types.DoeDevice{ .backend = .metal };
    var queue = DoeQueue{
        .dev = &device,
    };
    const info = abi_callback.WGPUQueueWorkDoneCallbackInfo{
        .nextInChain = null,
        .mode = WGPU_CALLBACK_MODE_ALLOW_SPONTANEOUS,
        .callback = testWorkDoneCallback,
        .userdata1 = null,
        .userdata2 = null,
    };
    try testing.expect(shouldDispatchSpontaneousMetalWorkDone(&queue, info));
}

test "spontaneous completion stays on the synchronous path for non-Metal queues" {
    const testing = @import("std").testing;
    var device = native_types.DoeDevice{ .backend = .vulkan };
    var queue = DoeQueue{
        .dev = &device,
    };
    const info = abi_callback.WGPUQueueWorkDoneCallbackInfo{
        .nextInChain = null,
        .mode = WGPU_CALLBACK_MODE_ALLOW_SPONTANEOUS,
        .callback = testWorkDoneCallback,
        .userdata1 = null,
        .userdata2 = null,
    };
    try testing.expect(!shouldDispatchSpontaneousMetalWorkDone(&queue, info));
}

test "work done ownership preserves pending callbacks during reentrant enqueue" {
    const Fixture = struct {
        const Self = @This();
        observed: [4]u8 = undefined,
        count: usize = 0,
        rejected: usize = 0,

        const Event = struct {
            owner: *Self,
            id: u8,
            followups: []const Event = &.{},

            fn info(self: *const Event) abi_callback.WGPUQueueWorkDoneCallbackInfo {
                return .{
                    .nextInChain = null,
                    .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
                    .callback = callback,
                    .userdata1 = @ptrCast(@constCast(self)),
                    .userdata2 = null,
                };
            }

            fn callback(
                _: abi_callback.WGPUQueueWorkDoneStatus,
                _: abi_core.WGPUStringView,
                userdata: ?*anyopaque,
                _: ?*anyopaque,
            ) callconv(.c) void {
                const self: *const Event = @ptrCast(@alignCast(userdata.?));
                if (self.owner.count < self.owner.observed.len) self.owner.observed[self.owner.count] = self.id;
                self.owner.count += 1;
                for (self.followups) |*event| {
                    self.owner.rejected += @intFromBool(!enqueue_global_work_done(event.info()));
                }
            }
        };
    };
    var fixture: Fixture = .{};
    const followups = [_]Fixture.Event{
        .{ .owner = &fixture, .id = 3 },
        .{ .owner = &fixture, .id = 4 },
    };
    const initial = [_]Fixture.Event{
        .{ .owner = &fixture, .id = 1, .followups = &followups },
        .{ .owner = &fixture, .id = 2 },
    };
    defer drain_global_work_done();
    for (&initial) |*event| try std.testing.expect(enqueue_global_work_done(event.info()));
    drain_global_work_done();
    try std.testing.expectEqual(@as(usize, 0), fixture.rejected);
    try std.testing.expectEqual(@as(usize, 2), fixture.count);
    try std.testing.expectEqualSlices(u8, &.{ 1, 2 }, fixture.observed[0..fixture.count]);
    drain_global_work_done();
    try std.testing.expectEqual(@as(usize, 4), fixture.count);
    try std.testing.expectEqualSlices(u8, &.{ 1, 2, 3, 4 }, &fixture.observed);
}

test "work done ownership serializes concurrent registration and future identity" {
    const Fixture = struct {
        const THREADS = 4;
        const PER_THREAD = MAX_GLOBAL_WORK_DONE / THREADS;
        ready: std.Thread.ResetEvent = .{},
        delivered: std.atomic.Value(usize) = .init(0),
        rejected: std.atomic.Value(usize) = .init(0),
        ids: [THREADS][PER_THREAD]u64 = undefined,

        fn callback(
            _: abi_callback.WGPUQueueWorkDoneStatus,
            _: abi_core.WGPUStringView,
            userdata: ?*anyopaque,
            _: ?*anyopaque,
        ) callconv(.c) void {
            const self: *@This() = @ptrCast(@alignCast(userdata.?));
            _ = self.delivered.fetchAdd(1, .monotonic);
        }

        fn register(self: *@This(), index: usize) void {
            self.ready.wait();
            for (&self.ids[index]) |*id| {
                id.* = next_work_done_future().id;
                if (!enqueue_global_work_done(.{
                    .nextInChain = null,
                    .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
                    .callback = callback,
                    .userdata1 = @ptrCast(self),
                    .userdata2 = null,
                })) _ = self.rejected.fetchAdd(1, .monotonic);
            }
        }
    };
    var fixture: Fixture = .{};
    var workers: [Fixture.THREADS]std.Thread = undefined;
    var started: usize = 0;
    defer drain_global_work_done();
    {
        defer {
            fixture.ready.set();
            for (workers[0..started]) |worker| worker.join();
        }
        for (&workers, 0..) |*worker, index| {
            worker.* = try std.Thread.spawn(.{}, Fixture.register, .{ &fixture, index });
            started += 1;
        }
    }
    try std.testing.expectEqual(@as(usize, 0), fixture.rejected.load(.monotonic));
    const ids = std.mem.asBytes(&fixture.ids);
    const flat = std.mem.bytesAsSlice(u64, ids);
    for (flat, 0..) |id, index| {
        try std.testing.expect(id >= WORK_DONE_FUTURE_ID_BASE);
        for (flat[0..index]) |previous| try std.testing.expect(id != previous);
    }
    drain_global_work_done();
    try std.testing.expectEqual(@as(usize, MAX_GLOBAL_WORK_DONE), fixture.delivered.load(.monotonic));
}
