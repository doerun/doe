// doe_instance_device_native.zig — Instance, adapter, and device lifecycle exports.
// Sharded from doe_wgpu_native.zig to stay under the 777-line limit.
//
// Backend selection: set DOE_BACKEND=vulkan in the environment to use the
// Vulkan runtime instead of Metal. Metal is the default on macOS.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const label_store = native.label_store;

const DoeInstance = native.DoeInstance;
const DoeAdapter = native.DoeAdapter;
const DoeDevice = native.DoeDevice;
const DoeQueue = native.DoeQueue;
const BackendKind = native.BackendKind;
const NativeVulkanRuntime = native.NativeVulkanRuntime;

const bridge = @import("backend/metal/metal_bridge_decls.zig");
const metal_bridge_create_default_device = bridge.metal_bridge_create_default_device;
const metal_bridge_device_new_command_queue = bridge.metal_bridge_device_new_command_queue;
const metal_bridge_device_new_shared_event = bridge.metal_bridge_device_new_shared_event;
const metal_bridge_release = bridge.metal_bridge_release;

const WGPU_WAIT_STATUS_SUCCESS: u32 = 1;
const WGPU_REQUEST_STATUS_SUCCESS: u32 = 1;
const WGPU_REQUEST_STATUS_UNAVAILABLE: u32 = 3;
const WGPU_REQUEST_STATUS_ERROR: u32 = 4;
const MSG_ADAPTER_UNAVAILABLE = "metal default device unavailable";
const MSG_ADAPTER_ALLOCATION_FAILED = "adapter allocation failed";
const MSG_INVALID_ADAPTER = "invalid adapter handle";
const MSG_QUEUE_UNAVAILABLE = "metal command queue unavailable";
const MSG_DEVICE_ALLOCATION_FAILED = "device allocation failed";
const MSG_VK_RUNTIME_INIT_FAILED = "vulkan runtime init failed";

// Check the DOE_BACKEND environment variable. Returns true when "vulkan" is set.
// Uses the GPA allocator for the temporary env string.
fn env_requests_vulkan() bool {
    const env = std.process.getEnvVarOwned(alloc, "DOE_BACKEND") catch return false;
    defer alloc.free(env);
    return std.mem.eql(u8, env, "vulkan");
}

fn stringView(comptime message: []const u8) types.WGPUStringView {
    return .{ .data = message.ptr, .length = message.len };
}

// ============================================================
// Instance
// ============================================================

pub export fn doeNativeCreateInstance(desc: ?*anyopaque) callconv(.c) ?*anyopaque {
    _ = desc;
    const inst = make(DoeInstance) orelse return null;
    inst.* = .{};
    return toOpaque(inst);
}

pub export fn doeNativeInstanceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeInstance, raw)) |inst| {
        label_store.remove(raw);
        alloc.destroy(inst);
    }
}

pub export fn doeNativeInstanceWaitAny(inst: ?*anyopaque, count: usize, infos: [*]types.WGPUFutureWaitInfo, timeout_ns: u64) callconv(.c) u32 {
    _ = inst;
    _ = timeout_ns;
    for (infos[0..count]) |*info| info.completed = 1;
    return WGPU_WAIT_STATUS_SUCCESS;
}

// ============================================================
// Adapter
// ============================================================

// Flat adapter request: callback(status, adapter, message, userdata1, userdata2)
pub export fn doeNativeRequestAdapterFlat(
    inst: ?*anyopaque,
    _: ?*anyopaque, // options
    _: u32, // callback mode
    callback: ?*const fn (u32, ?*anyopaque, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    _ = inst;

    if (env_requests_vulkan()) {
        const adapter = make(DoeAdapter) orelse {
            if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_ADAPTER_ALLOCATION_FAILED), userdata1, userdata2);
            return .{ .id = 1 };
        };
        adapter.* = .{ .backend = .vulkan };
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(adapter), stringView(""), userdata1, userdata2);
        return .{ .id = 1 };
    }

    const device = metal_bridge_create_default_device();
    if (device == null) {
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_UNAVAILABLE, null, stringView(MSG_ADAPTER_UNAVAILABLE), userdata1, userdata2);
        return .{ .id = 1 };
    }
    const adapter = make(DoeAdapter) orelse {
        metal_bridge_release(device);
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_ADAPTER_ALLOCATION_FAILED), userdata1, userdata2);
        return .{ .id = 1 };
    };
    adapter.* = .{ .mtl_device = device };
    if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(adapter), stringView(""), userdata1, userdata2);
    return .{ .id = 1 };
}

// Standard-signature wrapper for routing layer compatibility.
pub export fn doeNativeInstanceRequestAdapter(
    inst: ?*anyopaque,
    options: ?*const types.WGPURequestAdapterOptions,
    info: types.WGPURequestAdapterCallbackInfo,
) callconv(.c) types.WGPUFuture {
    _ = options;
    _ = inst;

    if (env_requests_vulkan()) {
        const adapter = make(DoeAdapter) orelse {
            info.callback(.@"error", null, stringView(MSG_ADAPTER_ALLOCATION_FAILED), info.userdata1, info.userdata2);
            return .{ .id = 1 };
        };
        adapter.* = .{ .backend = .vulkan };
        info.callback(.success, toOpaque(adapter), stringView(""), info.userdata1, info.userdata2);
        return .{ .id = 1 };
    }

    const device = metal_bridge_create_default_device();
    if (device == null) {
        info.callback(.unavailable, null, stringView(MSG_ADAPTER_UNAVAILABLE), info.userdata1, info.userdata2);
        return .{ .id = 1 };
    }
    const adapter = make(DoeAdapter) orelse {
        metal_bridge_release(device);
        info.callback(.@"error", null, stringView(MSG_ADAPTER_ALLOCATION_FAILED), info.userdata1, info.userdata2);
        return .{ .id = 1 };
    };
    adapter.* = .{ .mtl_device = device };
    info.callback(.success, toOpaque(adapter), stringView(""), info.userdata1, info.userdata2);
    return .{ .id = 1 };
}

pub export fn doeNativeAdapterRelease(raw: ?*anyopaque) callconv(.c) void {
    // Adapter does NOT own the MTLDevice — device ownership transfers to DoeDevice.
    if (cast(DoeAdapter, raw)) |a| {
        label_store.remove(raw);
        alloc.destroy(a);
    }
}

// ============================================================
// Device
// ============================================================

pub export fn doeNativeAdapterRequestDevice(
    adapter_raw: ?*anyopaque,
    desc: ?*const types.WGPUDeviceDescriptor,
    info: types.WGPURequestDeviceCallbackInfo,
) callconv(.c) types.WGPUFuture {
    _ = desc;
    const adapter = cast(DoeAdapter, adapter_raw) orelse {
        info.callback(.@"error", null, stringView(MSG_INVALID_ADAPTER), info.userdata1, info.userdata2);
        return .{ .id = 2 };
    };

    if (adapter.backend == .vulkan) {
        const dev = make(DoeDevice) orelse {
            info.callback(.@"error", null, stringView(MSG_DEVICE_ALLOCATION_FAILED), info.userdata1, info.userdata2);
            return .{ .id = 2 };
        };
        const rt = alloc.create(NativeVulkanRuntime) catch {
            alloc.destroy(dev);
            info.callback(.@"error", null, stringView(MSG_DEVICE_ALLOCATION_FAILED), info.userdata1, info.userdata2);
            return .{ .id = 2 };
        };
        rt.* = NativeVulkanRuntime.init(alloc, null) catch {
            alloc.destroy(rt);
            alloc.destroy(dev);
            info.callback(.@"error", null, stringView(MSG_VK_RUNTIME_INIT_FAILED), info.userdata1, info.userdata2);
            return .{ .id = 2 };
        };
        dev.* = .{ .backend = .vulkan, .vk_runtime = @ptrCast(rt) };
        info.callback(.success, toOpaque(dev), stringView(""), info.userdata1, info.userdata2);
        return .{ .id = 2 };
    }

    const queue = metal_bridge_device_new_command_queue(adapter.mtl_device);
    if (queue == null) {
        info.callback(.@"error", null, stringView(MSG_QUEUE_UNAVAILABLE), info.userdata1, info.userdata2);
        return .{ .id = 2 };
    }
    const dev = make(DoeDevice) orelse {
        metal_bridge_release(queue);
        info.callback(.@"error", null, stringView(MSG_DEVICE_ALLOCATION_FAILED), info.userdata1, info.userdata2);
        return .{ .id = 2 };
    };
    dev.* = .{ .mtl_device = adapter.mtl_device, .mtl_queue = queue };
    info.callback(.success, toOpaque(dev), stringView(""), info.userdata1, info.userdata2);
    return .{ .id = 2 };
}

// Flat device request.
pub export fn doeNativeRequestDeviceFlat(
    adapter_raw: ?*anyopaque,
    _: ?*anyopaque,
    _: u32,
    callback: ?*const fn (u32, ?*anyopaque, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    const adapter = cast(DoeAdapter, adapter_raw) orelse {
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_INVALID_ADAPTER), userdata1, userdata2);
        return .{ .id = 2 };
    };

    if (adapter.backend == .vulkan) {
        const dev = make(DoeDevice) orelse {
            if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_DEVICE_ALLOCATION_FAILED), userdata1, userdata2);
            return .{ .id = 2 };
        };
        const rt = alloc.create(NativeVulkanRuntime) catch {
            alloc.destroy(dev);
            if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_DEVICE_ALLOCATION_FAILED), userdata1, userdata2);
            return .{ .id = 2 };
        };
        rt.* = NativeVulkanRuntime.init(alloc, null) catch {
            alloc.destroy(rt);
            alloc.destroy(dev);
            if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_VK_RUNTIME_INIT_FAILED), userdata1, userdata2);
            return .{ .id = 2 };
        };
        dev.* = .{ .backend = .vulkan, .vk_runtime = @ptrCast(rt) };
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(dev), stringView(""), userdata1, userdata2);
        return .{ .id = 2 };
    }

    const queue = metal_bridge_device_new_command_queue(adapter.mtl_device);
    if (queue == null) {
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_QUEUE_UNAVAILABLE), userdata1, userdata2);
        return .{ .id = 2 };
    }
    const dev = make(DoeDevice) orelse {
        metal_bridge_release(queue);
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_DEVICE_ALLOCATION_FAILED), userdata1, userdata2);
        return .{ .id = 2 };
    };
    dev.* = .{ .mtl_device = adapter.mtl_device, .mtl_queue = queue };
    if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(dev), stringView(""), userdata1, userdata2);
    return .{ .id = 2 };
}

pub export fn doeNativeDeviceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeDevice, raw)) |d| {
        label_store.remove(raw);
        // Fire the device-lost callback with reason "destroyed" before teardown.
        const multi_adapter = @import("multi_adapter.zig");
        multi_adapter.notify_device_released(raw);
        if (d.backend == .vulkan) {
            // Queue is just a thin wrapper with no Metal resources — destroy it.
            if (d.queue) |q| alloc.destroy(q);
            // Deinit and free the Vulkan runtime (releases all VkBuffer/VkDevice etc.).
            if (d.vk_runtime) |ptr| {
                const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(ptr));
                rt.deinit();
                alloc.destroy(rt);
            }
        } else {
            if (d.queue) |q| alloc.destroy(q);
            if (d.mtl_queue) |q| metal_bridge_release(q);
            if (d.mtl_device) |dev| metal_bridge_release(dev);
        }
        alloc.destroy(d);
    }
}

pub export fn doeNativeDeviceGetQueue(raw: ?*anyopaque) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, raw) orelse return null;
    if (dev.queue) |q| return toOpaque(q);
    const q = make(DoeQueue) orelse return null;
    q.* = .{ .dev = dev };
    // MTLSharedEvent is only used for Metal GPU-CPU synchronization.
    if (dev.backend != .vulkan) {
        q.mtl_event = metal_bridge_device_new_shared_event(dev.mtl_device);
    }
    dev.queue = q;
    return toOpaque(q);
}
