const abi_base = @import("../core/abi/wgpu_handle_types.zig");
const abi_callback = @import("../core/abi/wgpu_callback_descriptor_types.zig");
const process_roots = @import("process_roots.zig");
const task_pool = @import("task_pool.zig");

const MapCallbackJob = struct {
    status: u32,
    cb: ?*const fn (u32, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

const WorkDoneCallbackJob = struct {
    cb: ?*const fn (abi_callback.WGPUQueueWorkDoneStatus, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

fn run_map_callback_job(ctx_raw: ?*anyopaque) void {
    const job: *MapCallbackJob = @ptrCast(@alignCast(ctx_raw orelse return));
    defer process_roots.callbackJobAllocator().destroy(job);
    if (job.cb) |f| f(job.status, .{ .data = null, .length = 0 }, job.userdata1, job.userdata2);
}

fn run_work_done_callback_job(ctx_raw: ?*anyopaque) void {
    const job: *WorkDoneCallbackJob = @ptrCast(@alignCast(ctx_raw orelse return));
    defer process_roots.callbackJobAllocator().destroy(job);
    if (job.cb) |f| f(.success, .{ .data = null, .length = 0 }, job.userdata1, job.userdata2);
}

pub fn fire_map_callback_inline(
    status: u32,
    cb: ?*const fn (u32, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) void {
    if (cb) |f| f(status, .{ .data = null, .length = 0 }, userdata1, userdata2);
}

pub fn fire_work_done_callback_inline(
    cb: ?*const fn (abi_callback.WGPUQueueWorkDoneStatus, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) void {
    if (cb) |f| f(.success, .{ .data = null, .length = 0 }, userdata1, userdata2);
}

pub fn dispatch_map_callback(
    status: u32,
    cb: ?*const fn (u32, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) void {
    const allocator = process_roots.callbackJobAllocator();
    const job = allocator.create(MapCallbackJob) catch {
        fire_map_callback_inline(status, cb, userdata1, userdata2);
        return;
    };
    job.* = .{ .status = status, .cb = cb, .userdata1 = userdata1, .userdata2 = userdata2 };
    task_pool.submitWithAllocator(allocator, .{ .run = run_map_callback_job, .ctx = job }) catch {
        allocator.destroy(job);
        fire_map_callback_inline(status, cb, userdata1, userdata2);
    };
}

pub fn dispatch_work_done_callback(
    cb: ?*const fn (abi_callback.WGPUQueueWorkDoneStatus, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) void {
    const allocator = process_roots.callbackJobAllocator();
    const job = allocator.create(WorkDoneCallbackJob) catch {
        fire_work_done_callback_inline(cb, userdata1, userdata2);
        return;
    };
    job.* = .{ .cb = cb, .userdata1 = userdata1, .userdata2 = userdata2 };
    task_pool.submitWithAllocator(allocator, .{ .run = run_work_done_callback_job, .ctx = job }) catch {
        allocator.destroy(job);
        fire_work_done_callback_inline(cb, userdata1, userdata2);
    };
}
