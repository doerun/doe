//! Descriptor loss obligation, independent of device/backend object storage.
const std = @import("std");
const abi = @import("../../core/abi/wgpu_callback_descriptor_types.zig");
const base = @import("../../core/abi/wgpu_core_base_types.zig");
const leases = @import("../../contracts/resource_lease.zig");
const futures = @import("doe_future_ids.zig");

pub const References = struct {
    retain_device: *const fn (?*anyopaque) callconv(.c) void,
    release_device: *const fn (?*anyopaque) callconv(.c) void,
    retain_instance: *const fn (?*anyopaque) callconv(.c) void,
    release_instance: *const fn (?*anyopaque) callconv(.c) void,
};

pub const Event = struct {
    allocator: std.mem.Allocator,
    ref_count: u32 = 1,
    mutex: std.Thread.Mutex = .{},
    completion: futures.Completion,
    future: base.WGPUFuture,
    instance: ?*anyopaque,
    references: References,
    info: abi.WGPUDeviceLostCallbackInfo,
    device: ?*anyopaque = null,
    reason: ?abi.WGPUDeviceLostReason = null,
    message: []const u8 = "",

    pub fn create(allocator: std.mem.Allocator, owner: ?*futures.PendingCompletions, instance: ?*anyopaque, info: abi.WGPUDeviceLostCallbackInfo, references: References) !*Event {
        if (info.mode != 0 and info.mode != abi.WGPUCallbackMode_WaitAnyOnly and info.mode != abi.WGPUCallbackMode_AllowProcessEvents and info.mode != abi.WGPUCallbackMode_AllowSpontaneous) return error.UnsupportedCallbackMode;
        if (owner == null and info.mode != 0 and info.mode != abi.WGPUCallbackMode_AllowSpontaneous) return error.CallbackInstanceUnavailable;
        const self = try allocator.create(Event);
        const id = if (owner) |pending| pending.newFuture() else futures.legacyFuture();
        self.* = .{ .allocator = allocator, .completion = .{ .mode = info.mode, .dispatch = dispatch }, .future = .{ .id = id }, .instance = instance, .references = references, .info = info };
        // The pending obligation and device each own one reference, without a device cycle.
        leases.retainCount(&self.ref_count);
        if (owner) |pending| {
            references.retain_instance(instance);
            pending.register(&self.completion, id);
        }
        return self;
    }

    pub fn release(self: *Event) void {
        if (leases.releaseCount(&self.ref_count)) self.allocator.destroy(self);
    }

    pub fn setDevice(self: *Event, device: ?*anyopaque) void {
        self.mutex.lock();
        defer self.mutex.unlock();
        self.device = device;
    }

    pub fn setCallback(self: *Event, callback: ?abi.WGPUDeviceLostCallback, userdata1: ?*anyopaque, userdata2: ?*anyopaque) void {
        self.mutex.lock();
        defer self.mutex.unlock();
        if (self.reason != null) return;
        self.info.callback = callback;
        self.info.userdata1 = userdata1;
        self.info.userdata2 = userdata2;
    }

    /// Messages are immutable runtime diagnostics, never borrowed descriptor bytes.
    pub fn lose(self: *Event, reason: abi.WGPUDeviceLostReason, message: []const u8) void {
        self.mutex.lock();
        if (self.reason != null) {
            self.mutex.unlock();
            return;
        }
        self.reason = reason;
        self.message = message;
        self.mutex.unlock();
        self.completion.markReady();
    }

    fn dispatch(completion: *futures.Completion) void {
        const self: *Event = @fieldParentPtr("completion", completion);
        self.mutex.lock();
        const info = self.info;
        const reason = self.reason.?;
        const message = self.message;
        const device = self.device;
        if (device != null) self.references.retain_device(device);
        self.mutex.unlock();
        if (info.callback) |callback| callback(@ptrCast(&device), reason, .{ .data = message.ptr, .length = message.len }, info.userdata1, info.userdata2);
        if (device != null) self.references.release_device(device);
        completion.finish();
        const references = self.references;
        const instance = self.instance;
        self.release();
        if (instance != null) references.release_instance(instance);
    }
};

const TestReferences = struct {
    fn ignore(_: ?*anyopaque) callconv(.c) void {}
    const ops = References{ .retain_device = ignore, .release_device = ignore, .retain_instance = ignore, .release_instance = ignore };
};

test "loss allocation rollback leaves no pending obligation" {
    var pending: futures.PendingCompletions = .{};
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    const info = std.mem.zeroes(abi.WGPUDeviceLostCallbackInfo);
    try std.testing.expectError(error.OutOfMemory, Event.create(failing.allocator(), &pending, null, info, TestReferences.ops));
    try std.testing.expect(pending.head == null);
}

test "device loss clears borrowed handle before deferred delivery exactly once" {
    const Capture = struct {
        count: u32 = 0,
        reason: abi.WGPUDeviceLostReason = .unknown,
        handle: ?*anyopaque = null,
        fn callback(raw: ?*const anyopaque, reason: abi.WGPUDeviceLostReason, _: base.WGPUStringView, userdata: ?*anyopaque, _: ?*anyopaque) callconv(.c) void {
            const self: *@This() = @ptrCast(@alignCast(userdata.?));
            const device: *const ?*anyopaque = @ptrCast(@alignCast(raw.?));
            self.count += 1;
            self.reason = reason;
            self.handle = device.*;
        }
    };
    for ([_]u32{ abi.WGPUCallbackMode_WaitAnyOnly, abi.WGPUCallbackMode_AllowProcessEvents, abi.WGPUCallbackMode_AllowSpontaneous }) |mode| {
        var pending: futures.PendingCompletions = .{};
        var capture = Capture{};
        var info = std.mem.zeroes(abi.WGPUDeviceLostCallbackInfo);
        info.mode = mode;
        info.callback = Capture.callback;
        info.userdata1 = &capture;
        const event = try Event.create(std.testing.allocator, &pending, null, info, TestReferences.ops);
        defer event.release();
        event.setDevice(&capture);
        const future = event.future;
        var infos = [_]abi.WGPUFutureWaitInfo{.{ .future = future, .completed = 0 }};
        try std.testing.expect(!try pending.waitAny(&infos, 0));
        event.setDevice(null);
        event.lose(.destroyed, "destroyed");
        event.lose(.failedCreation, "ignored duplicate");
        pending.processEvents();
        if (mode == abi.WGPUCallbackMode_WaitAnyOnly) try std.testing.expectEqual(@as(u32, 0), capture.count);
        try std.testing.expect(try pending.waitAny(&infos, 0));
        try std.testing.expect(try pending.waitAny(&infos, 0));
        try std.testing.expectEqual(@as(u32, 1), capture.count);
        try std.testing.expectEqual(abi.WGPUDeviceLostReason.destroyed, capture.reason);
        try std.testing.expect(capture.handle == null);
        try std.testing.expect(pending.head == null);
    }
}
