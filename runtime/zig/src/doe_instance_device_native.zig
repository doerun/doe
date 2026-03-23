// doe_instance_device_native.zig — Instance, adapter, and device lifecycle exports.
// Sharded from doe_wgpu_native.zig to stay under the 777-line limit.
//
// Backend selection: DOE_BACKEND explicitly selects the runtime backend. When
// DOE_BACKEND is absent, FAWN_BACKEND_LANE provides the Chromium/browser lane
// contract that Doe should honor.

const std = @import("std");
const builtin = @import("builtin");
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
const NativeVulkanRuntime = native.NativeVulkanRuntime;
const NativeD3D12Runtime = native.NativeD3D12Runtime;
const d3d12_device_caps = @import("backend/d3d12/d3d12_device_caps.zig");
const vk_feature_caps = @import("backend/vulkan/vk_feature_caps.zig");
const vk_device_caps = @import("backend/vulkan/vk_device_caps.zig");
const vulkan_feature_cache = @import("doe_vulkan_feature_cache.zig");
const vk_device = @import("backend/vulkan/vk_device.zig");
const backend_policy = @import("backend/backend_policy.zig");

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
const MSG_D3D12_RUNTIME_INIT_FAILED = "d3d12 runtime init failed";

const RequestedBackend = enum {
    metal,
    vulkan,
    d3d12,
};

fn instance_add_ref(inst: *DoeInstance) void {
    inst.ref_count +|= 1;
}

fn adapter_add_ref(adapter: *DoeAdapter) void {
    adapter.ref_count +|= 1;
}

fn device_add_ref(device: *DoeDevice) void {
    device.ref_count +|= 1;
}

fn parse_requested_backend(raw: []const u8) ?RequestedBackend {
    if (std.ascii.eqlIgnoreCase(raw, "metal")) return .metal;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan")) return .vulkan;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12")) return .d3d12;
    return null;
}

fn requested_backend_from_lane(raw: []const u8) ?RequestedBackend {
    const lane = backend_policy.parse_lane(raw) orelse return null;
    return switch (lane) {
        .metal_doe_app, .metal_doe_directional, .metal_doe_comparable, .metal_doe_release, .metal_dawn_release => .metal,
        .vulkan_doe_app, .vulkan_doe_comparable, .vulkan_doe_release, .vulkan_dawn_release => .vulkan,
        .d3d12_doe_app, .d3d12_doe_directional, .d3d12_doe_comparable, .d3d12_doe_release, .d3d12_dawn_release => .d3d12,
    };
}

fn selected_backend() RequestedBackend {
    const explicit_backend = std.process.getEnvVarOwned(alloc, "DOE_BACKEND") catch null;
    if (explicit_backend) |raw_backend| {
        defer alloc.free(raw_backend);
        if (parse_requested_backend(raw_backend)) |backend| return backend;
    }

    const lane_value = std.process.getEnvVarOwned(alloc, "FAWN_BACKEND_LANE") catch null;
    if (lane_value) |raw_lane| {
        defer alloc.free(raw_lane);
        if (requested_backend_from_lane(raw_lane)) |backend| return backend;
    }

    return switch (builtin.os.tag) {
        .macos => .metal,
        .windows => .d3d12,
        else => .vulkan,
    };
}

fn probe_d3d12_adapter_caps() d3d12_device_caps.D3D12DeviceCaps {
    var rt = NativeD3D12Runtime.init(alloc, null) catch return .{};
    defer rt.deinit();
    return rt.device_caps;
}

// Conservative static fallback when Vulkan probe fails (no GPU, driver error).
fn probe_vulkan_device_caps_fallback() vk_device_caps.VulkanDeviceCaps {
    return .{
        .limits = vulkan_limits_static_fallback(),
        .has_depth_clip_control = false,
        .has_texture_compression_bc = false,
        .has_texture_compression_etc2 = false,
        .has_texture_compression_astc = false,
        .has_draw_indirect_first_instance = false,
        .has_float32_filterable = false,
        .has_timestamp_query = false,
    };
}

fn vulkan_limits_static_fallback() types.WGPULimits {
    const doe_device_caps = @import("doe_device_caps.zig");
    return doe_device_caps.VULKAN_LIMITS_STATIC;
}

fn stringView(comptime message: []const u8) types.WGPUStringView {
    return .{ .data = message.ptr, .length = message.len };
}

fn call_request_adapter_callback(
    info: types.WGPURequestAdapterCallbackInfo,
    status: types.WGPURequestAdapterStatus,
    adapter: ?*anyopaque,
    message: types.WGPUStringView,
) void {
    const callback = info.callback orelse return;
    callback(status, adapter, message, info.userdata1, info.userdata2);
}

fn call_request_device_callback(
    info: types.WGPURequestDeviceCallbackInfo,
    status: types.WGPURequestDeviceStatus,
    device: ?*anyopaque,
    message: types.WGPUStringView,
) void {
    const callback = info.callback orelse return;
    callback(status, device, message, info.userdata1, info.userdata2);
}

const CreateDeviceError = error{
    QueueUnavailable,
    DeviceAllocationFailed,
    VkRuntimeInitFailed,
    D3D12RuntimeInitFailed,
};

fn create_device_error_message(err: CreateDeviceError) types.WGPUStringView {
    return switch (err) {
        error.QueueUnavailable => stringView(MSG_QUEUE_UNAVAILABLE),
        error.DeviceAllocationFailed => stringView(MSG_DEVICE_ALLOCATION_FAILED),
        error.VkRuntimeInitFailed => stringView(MSG_VK_RUNTIME_INIT_FAILED),
        error.D3D12RuntimeInitFailed => stringView(MSG_D3D12_RUNTIME_INIT_FAILED),
    };
}

fn create_device_for_adapter(adapter: *DoeAdapter, adapter_raw: ?*anyopaque) CreateDeviceError!*DoeDevice {
    if (adapter.backend == .vulkan) {
        const feature_caps: vk_feature_caps.VulkanFeatureCaps =
            vulkan_feature_cache.get_adapter(adapter_raw) orelse .{};
        const dev = make(DoeDevice) orelse return error.DeviceAllocationFailed;
        const rt = alloc.create(NativeVulkanRuntime) catch {
            alloc.destroy(dev);
            return error.DeviceAllocationFailed;
        };
        rt.* = NativeVulkanRuntime.init(alloc, null) catch {
            alloc.destroy(rt);
            alloc.destroy(dev);
            return error.VkRuntimeInitFailed;
        };
        adapter_add_ref(adapter);
        dev.* = .{ .backend = .vulkan, .adapter = adapter, .vk_runtime = @ptrCast(rt) };
        vulkan_feature_cache.set_device(toOpaque(dev), feature_caps);
        // Propagate hardware-queried device caps from adapter, or re-query from runtime.
        if (vulkan_feature_cache.get_adapter_device_caps(adapter_raw)) |adapter_hw_caps| {
            vulkan_feature_cache.set_device_device_caps(toOpaque(dev), adapter_hw_caps);
        } else {
            const runtime_caps = vk_device_caps.query_device_caps(
                rt.physical_device,
                if (rt.timestamp_query_supported_value) 36 else 0,
            );
            vulkan_feature_cache.set_device_device_caps(toOpaque(dev), runtime_caps);
        }
        return dev;
    }

    if (adapter.backend == .d3d12) {
        const dev = make(DoeDevice) orelse return error.DeviceAllocationFailed;
        const rt = alloc.create(NativeD3D12Runtime) catch {
            alloc.destroy(dev);
            return error.DeviceAllocationFailed;
        };
        rt.* = NativeD3D12Runtime.init(alloc, null) catch {
            alloc.destroy(rt);
            alloc.destroy(dev);
            return error.D3D12RuntimeInitFailed;
        };
        adapter_add_ref(adapter);
        dev.* = .{
            .backend = .d3d12,
            .adapter = adapter,
            .mtl_device = rt.device,
            .mtl_queue = rt.queue,
            .d3d12_runtime = @ptrCast(rt),
        };
        return dev;
    }

    const queue = metal_bridge_device_new_command_queue(adapter.mtl_device);
    if (queue == null) return error.QueueUnavailable;
    const dev = make(DoeDevice) orelse {
        metal_bridge_release(queue);
        return error.DeviceAllocationFailed;
    };
    adapter_add_ref(adapter);
    dev.* = .{ .adapter = adapter, .mtl_device = adapter.mtl_device, .mtl_queue = queue };
    return dev;
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

pub export fn doeNativeInstanceAddRef(raw: ?*anyopaque) callconv(.c) void {
    const inst = cast(DoeInstance, raw) orelse return;
    instance_add_ref(inst);
}

pub export fn doeNativeInstanceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeInstance, raw)) |inst| {
        // Guard: prevent destruction while external textures still reference this
        // Instance. The Chromium wire client may release its Instance handle before
        // external textures are freed; the external-texture backref path will call
        // InstanceRelease again when the last external texture is destroyed.
        const ext_tex = @import("doe_external_texture_native.zig");
        if (ext_tex.instance_external_texture_count(raw) > 0) {
            if (inst.ref_count > 1) inst.ref_count -= 1;
            return;
        }
        if (!native.object_should_destroy(inst)) return;
        native.label_store.remove(raw);
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
    const retained_instance = cast(DoeInstance, inst);

    switch (selected_backend()) {
        .d3d12 => {
            const adapter = make(DoeAdapter) orelse {
                if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_ADAPTER_ALLOCATION_FAILED), userdata1, userdata2);
                return .{ .id = 1 };
            };
            if (retained_instance) |instance_ref| instance_add_ref(instance_ref);
            adapter.* = .{ .backend = .d3d12, .instance = retained_instance };
            d3d12_device_caps.set_adapter_caps(toOpaque(adapter), probe_d3d12_adapter_caps());
            if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(adapter), stringView(""), userdata1, userdata2);
            return .{ .id = 1 };
        },
        .vulkan => {
            const feature_caps: vk_feature_caps.VulkanFeatureCaps =
                vk_device.probe_default_feature_caps(alloc) catch .{};
            const hw_caps: vk_device_caps.VulkanDeviceCaps =
                vk_device_caps.probe_device_caps(alloc) catch probe_vulkan_device_caps_fallback();
            const adapter = make(DoeAdapter) orelse {
                if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, stringView(MSG_ADAPTER_ALLOCATION_FAILED), userdata1, userdata2);
                return .{ .id = 1 };
            };
            if (retained_instance) |instance_ref| instance_add_ref(instance_ref);
            adapter.* = .{ .backend = .vulkan, .instance = retained_instance };
            vulkan_feature_cache.set_adapter(toOpaque(adapter), feature_caps);
            vulkan_feature_cache.set_adapter_device_caps(toOpaque(adapter), hw_caps);
            if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(adapter), stringView(""), userdata1, userdata2);
            return .{ .id = 1 };
        },
        .metal => {},
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
    if (retained_instance) |instance_ref| instance_add_ref(instance_ref);
    adapter.* = .{ .instance = retained_instance, .mtl_device = device };
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
    const retained_instance = cast(DoeInstance, inst);

    switch (selected_backend()) {
        .d3d12 => {
            const adapter = make(DoeAdapter) orelse {
                call_request_adapter_callback(info, .@"error", null, stringView(MSG_ADAPTER_ALLOCATION_FAILED));
                return .{ .id = 1 };
            };
            if (retained_instance) |instance_ref| instance_add_ref(instance_ref);
            adapter.* = .{ .backend = .d3d12, .instance = retained_instance };
            d3d12_device_caps.set_adapter_caps(toOpaque(adapter), probe_d3d12_adapter_caps());
            call_request_adapter_callback(info, .success, toOpaque(adapter), stringView(""));
            return .{ .id = 1 };
        },
        .vulkan => {
            const feature_caps: vk_feature_caps.VulkanFeatureCaps =
                vk_device.probe_default_feature_caps(alloc) catch .{};
            const hw_caps: vk_device_caps.VulkanDeviceCaps =
                vk_device_caps.probe_device_caps(alloc) catch probe_vulkan_device_caps_fallback();
            const adapter = make(DoeAdapter) orelse {
                call_request_adapter_callback(info, .@"error", null, stringView(MSG_ADAPTER_ALLOCATION_FAILED));
                return .{ .id = 1 };
            };
            if (retained_instance) |instance_ref| instance_add_ref(instance_ref);
            adapter.* = .{ .backend = .vulkan, .instance = retained_instance };
            vulkan_feature_cache.set_adapter(toOpaque(adapter), feature_caps);
            vulkan_feature_cache.set_adapter_device_caps(toOpaque(adapter), hw_caps);
            call_request_adapter_callback(info, .success, toOpaque(adapter), stringView(""));
            return .{ .id = 1 };
        },
        .metal => {},
    }

    const device = metal_bridge_create_default_device();
    if (device == null) {
        call_request_adapter_callback(info, .unavailable, null, stringView(MSG_ADAPTER_UNAVAILABLE));
        return .{ .id = 1 };
    }
    const adapter = make(DoeAdapter) orelse {
        metal_bridge_release(device);
        call_request_adapter_callback(info, .@"error", null, stringView(MSG_ADAPTER_ALLOCATION_FAILED));
        return .{ .id = 1 };
    };
    if (retained_instance) |instance_ref| instance_add_ref(instance_ref);
    adapter.* = .{ .instance = retained_instance, .mtl_device = device };
    call_request_adapter_callback(info, .success, toOpaque(adapter), stringView(""));
    return .{ .id = 1 };
}

pub export fn doeNativeAdapterAddRef(raw: ?*anyopaque) callconv(.c) void {
    const adapter = cast(DoeAdapter, raw) orelse return;
    adapter_add_ref(adapter);
}

pub export fn doeNativeAdapterGetInstance(raw: ?*anyopaque) callconv(.c) ?*anyopaque {
    const adapter = cast(DoeAdapter, raw) orelse return null;
    const instance = adapter.instance orelse return null;
    instance_add_ref(instance);
    return toOpaque(instance);
}

pub export fn doeNativeAdapterRelease(raw: ?*anyopaque) callconv(.c) void {
    // Adapter does NOT own the MTLDevice — device ownership transfers to DoeDevice.
    if (cast(DoeAdapter, raw)) |a| {
        if (a.ref_count > 1) {
            a.ref_count -= 1;
            return;
        }
        label_store.remove(raw);
        if (a.backend == .vulkan) vulkan_feature_cache.remove_adapter(raw);
        if (a.backend == .d3d12) d3d12_device_caps.remove_adapter_caps(raw);
        if (a.instance) |instance_ref| doeNativeInstanceRelease(toOpaque(instance_ref));
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
        call_request_device_callback(info, .@"error", null, stringView(MSG_INVALID_ADAPTER));
        return .{ .id = 2 };
    };
    const dev = create_device_for_adapter(adapter, adapter_raw) catch |err| {
        call_request_device_callback(info, .@"error", null, create_device_error_message(err));
        return .{ .id = 2 };
    };
    call_request_device_callback(info, .success, toOpaque(dev), stringView(""));
    return .{ .id = 2 };
}

pub export fn doeNativeAdapterCreateDevice(
    adapter_raw: ?*anyopaque,
    desc: ?*const types.WGPUDeviceDescriptor,
) callconv(.c) ?*anyopaque {
    _ = desc;
    const adapter = cast(DoeAdapter, adapter_raw) orelse return null;
    const dev = create_device_for_adapter(adapter, adapter_raw) catch return null;
    return toOpaque(dev);
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
    const dev = create_device_for_adapter(adapter, adapter_raw) catch |err| {
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, create_device_error_message(err), userdata1, userdata2);
        return .{ .id = 2 };
    };
    if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(dev), stringView(""), userdata1, userdata2);
    return .{ .id = 2 };
}

pub export fn doeNativeDeviceAddRef(raw: ?*anyopaque) callconv(.c) void {
    const device = cast(DoeDevice, raw) orelse return;
    device_add_ref(device);
}

pub export fn doeNativeDeviceGetAdapter(raw: ?*anyopaque) callconv(.c) ?*anyopaque {
    const device = cast(DoeDevice, raw) orelse return null;
    const adapter = device.adapter orelse return null;
    adapter_add_ref(adapter);
    return toOpaque(adapter);
}

pub export fn doeNativeDeviceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeDevice, raw)) |d| {
        if (d.ref_count > 1) {
            d.ref_count -= 1;
            return;
        }
        label_store.remove(raw);
        // Fire the device-lost callback with reason "destroyed" before teardown.
        const multi_adapter = @import("multi_adapter.zig");
        multi_adapter.notify_device_released(raw);
        if (d.backend == .vulkan) {
            vulkan_feature_cache.remove_device(raw);
            // Deinit and free the Vulkan runtime (releases all VkBuffer/VkDevice etc.).
            if (d.vk_runtime) |ptr| {
                const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(ptr));
                rt.deinit();
                alloc.destroy(rt);
            }
        } else if (d.backend == .d3d12) {
            if (d.d3d12_runtime) |ptr| {
                const rt: *NativeD3D12Runtime = @ptrCast(@alignCast(ptr));
                rt.deinit();
                alloc.destroy(rt);
            }
        } else {
            if (d.mtl_queue) |q| metal_bridge_release(q);
            if (d.mtl_device) |dev| metal_bridge_release(dev);
        }
        const adapter = d.adapter;
        alloc.destroy(d);
        if (adapter) |adapter_ref| doeNativeAdapterRelease(toOpaque(adapter_ref));
    }
}

pub export fn doeNativeDeviceGetQueue(raw: ?*anyopaque) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, raw) orelse return null;
    if (dev.queue) |q| {
        q.ref_count +|= 1;
        return toOpaque(q);
    }
    const q = make(DoeQueue) orelse return null;
    device_add_ref(dev);
    q.* = .{ .dev = dev };
    // MTLSharedEvent is only used for Metal GPU-CPU synchronization.
    if (dev.backend == .metal) {
        q.mtl_event = metal_bridge_device_new_shared_event(dev.mtl_device);
    }
    dev.queue = q;
    return toOpaque(q);
}
