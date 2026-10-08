const std = @import("std");
const abi = @import("../../core/abi/wgpu_callback_descriptor_types.zig");
const base = @import("../../core/abi/wgpu_core_base_types.zig");
const future_ids = @import("doe_future_ids.zig");
const objects = @import("doe_native_object_types.zig");
const helpers = @import("doe_native_object_helpers.zig");
const exports = @import("doe_native_exports.zig");

pub fn instanceForDevice(device: *const objects.DoeDevice) ?*objects.DoeInstance {
    const adapter = device.adapter orelse return null;
    return adapter.instance;
}

/// On success the event owns context until delivery; failure leaves it with the caller.
/// Deliverers release their resource leases after foreign callbacks return.
pub fn ready(
    comptime Context: type,
    allocator: std.mem.Allocator,
    instance: ?*objects.DoeInstance,
    mode: u32,
    context: Context,
    comptime deliver: fn (*Context) void,
) !base.WGPUFuture {
    return publish(Context, allocator, instance, mode, context, deliver, markReady);
}

fn markReady(completion: *future_ids.Completion) void {
    completion.markReady();
}

/// Publisher takes the prepared completion and must publish readiness exactly once.
/// It may hand publication to a worker; the event retains context and instance.
pub fn publish(
    comptime Context: type,
    allocator: std.mem.Allocator,
    instance: ?*objects.DoeInstance,
    mode: u32,
    context: Context,
    comptime deliver: fn (*Context) void,
    comptime publisher: fn (*future_ids.Completion) void,
) !base.WGPUFuture {
    if (mode != 0 and mode != abi.WGPUCallbackMode_WaitAnyOnly and mode != abi.WGPUCallbackMode_AllowProcessEvents and mode != abi.WGPUCallbackMode_AllowSpontaneous) return error.UnsupportedCallbackMode;
    const owner = instance orelse {
        if (mode != 0 and mode != abi.WGPUCallbackMode_AllowSpontaneous) return error.CallbackInstanceUnavailable;
        var immediate = context;
        deliver(&immediate);
        return .{ .id = future_ids.legacyFuture() };
    };
    const Node = struct {
        allocator: std.mem.Allocator,
        instance: *objects.DoeInstance,
        completion: future_ids.Completion = .{},
        context: Context,
        fn dispatch(completion: *future_ids.Completion) void {
            const self: *@This() = @fieldParentPtr("completion", completion);
            const node_allocator = self.allocator;
            const instance_ref = self.instance;
            deliver(&self.context);
            completion.finish();
            node_allocator.destroy(self);
            exports.doeNativeInstanceRelease(helpers.toOpaque(instance_ref));
        }
    };
    const node = try allocator.create(Node);
    const id = owner.pending_completions.newFuture();
    node.* = .{ .allocator = allocator, .instance = owner, .context = context, .completion = .{ .mode = mode, .dispatch = Node.dispatch } };
    helpers.object_add_ref(objects.DoeInstance, helpers.toOpaque(owner));
    owner.pending_completions.register(&node.completion, id);
    publisher(&node.completion);
    return .{ .id = id };
}

test "callback allocation failure leaves context and instance with caller" {
    const Reply = struct {
        delivered: *bool,
        fn deliver(self: *@This()) void {
            self.delivered.* = true;
        }
    };
    var instance = objects.DoeInstance{};
    var delivered = false;
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    try std.testing.expectError(error.OutOfMemory, ready(Reply, failing.allocator(), &instance, abi.WGPUCallbackMode_WaitAnyOnly, .{ .delivered = &delivered }, Reply.deliver));
    try std.testing.expect(!delivered);
    try std.testing.expectEqual(@as(u32, 1), instance.ref_count);
    try std.testing.expect(instance.pending_completions.head == null);
}

test "deferred callback lease survives reentrant caller instance release" {
    const Reply = struct {
        instance: *objects.DoeInstance,
        count: *u32,
        fn deliver(self: *@This()) void {
            self.count.* += 1;
            exports.doeNativeInstanceRelease(helpers.toOpaque(self.instance));
        }
    };
    // One independent observer lease and one caller lease; event adds its own.
    var instance = objects.DoeInstance{ .ref_count = 2 };
    var count: u32 = 0;
    const future = try ready(Reply, std.testing.allocator, &instance, abi.WGPUCallbackMode_WaitAnyOnly, .{ .instance = &instance, .count = &count }, Reply.deliver);
    try std.testing.expectEqual(@as(u32, 3), instance.ref_count);
    instance.pending_completions.processEvents();
    try std.testing.expectEqual(@as(u32, 0), count);
    var infos = [_]abi.WGPUFutureWaitInfo{.{ .future = future, .completed = 0 }};
    try std.testing.expect(try instance.pending_completions.waitAny(&infos, 0));
    try std.testing.expect(try instance.pending_completions.waitAny(&infos, 0));
    try std.testing.expectEqual(@as(u32, 1), count);
    try std.testing.expectEqual(@as(u32, 1), instance.ref_count);
}
