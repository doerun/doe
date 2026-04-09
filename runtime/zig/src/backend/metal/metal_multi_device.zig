// metal_multi_device.zig — Metal multi-device bridge: adapter enumeration and
// device-lost notification forwarding.
//
// The ObjC-side implementation is in metal_bridge.m (the new multi-device section).
// This file provides typed Zig wrappers and the eGPU-removal notification hook.

const std = @import("std");
const builtin = @import("builtin");

// ============================================================
// Constants

const MAX_ADAPTERS: usize = 16;

// ============================================================
// Bridge declarations (symbols implemented in metal_bridge.m)

extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_retain_device(device: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_enumerate_devices(
    out_devices: ?[*]?*anyopaque,
    max_count: u32,
    out_count: *u32,
) callconv(.c) void;
extern fn metal_bridge_device_registry_id(device: ?*anyopaque) callconv(.c) u64;
extern fn metal_bridge_device_is_low_power(device: ?*anyopaque) callconv(.c) u32;
extern fn metal_bridge_device_is_removable(device: ?*anyopaque) callconv(.c) u32;
extern fn metal_bridge_device_name(device: ?*anyopaque, buf: [*]u8, cap: usize) callconv(.c) void;

// ============================================================
// MTLBinaryArchive bridge (macOS 11+)

extern fn metal_bridge_binary_archive_create(
    device: ?*anyopaque,
    path: [*:0]const u8,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

extern fn metal_bridge_binary_archive_add_compute(
    archive: ?*anyopaque,
    device: ?*anyopaque,
    pipeline: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) u32;

extern fn metal_bridge_binary_archive_add_render(
    archive: ?*anyopaque,
    device: ?*anyopaque,
    pipeline: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) u32;

extern fn metal_bridge_binary_archive_serialize(
    archive: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) u32;

extern fn metal_bridge_device_new_compute_pipeline_with_archive(
    device: ?*anyopaque,
    function: ?*anyopaque,
    archive: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

extern fn metal_bridge_device_new_render_pipeline_with_archive(
    device: ?*anyopaque,
    pixel_format: u32,
    support_icb: c_int,
    archive: ?*anyopaque,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

// ============================================================
// Typed enumeration helper — used by multi_adapter.zig

pub const DeviceList = struct {
    handles: [MAX_ADAPTERS]?*anyopaque = [_]?*anyopaque{null} ** MAX_ADAPTERS,
    count: usize = 0,

    // Enumerate all Metal devices.  Each returned handle is +1 retained.
    pub fn enumerate() DeviceList {
        var list = DeviceList{};
        if (builtin.os.tag != .macos) return list;
        var found: u32 = 0;
        metal_bridge_enumerate_devices(@ptrCast(&list.handles), MAX_ADAPTERS, &found);
        list.count = @min(@as(usize, found), MAX_ADAPTERS);
        return list;
    }

    // Release all retained handles.
    pub fn release_all(self: *DeviceList) void {
        for (self.handles[0..self.count]) |dev| metal_bridge_release(dev);
        self.count = 0;
    }
};

// ============================================================
// Device property accessors (thin typed wrappers)

pub fn device_registry_id(dev: ?*anyopaque) u64 {
    return metal_bridge_device_registry_id(dev);
}

pub fn device_is_low_power(dev: ?*anyopaque) bool {
    return metal_bridge_device_is_low_power(dev) != 0;
}

pub fn device_is_removable(dev: ?*anyopaque) bool {
    return metal_bridge_device_is_removable(dev) != 0;
}

pub fn device_name(dev: ?*anyopaque, buf: []u8) usize {
    if (buf.len == 0) return 0;
    metal_bridge_device_name(dev, buf.ptr, buf.len);
    return std.mem.len(@as([*:0]const u8, @ptrCast(buf.ptr)));
}

// ============================================================
// Binary archive helpers

pub const BinaryArchive = struct {
    handle: ?*anyopaque,

    pub fn open(device: ?*anyopaque, path: [*:0]const u8) BinaryArchive {
        var err_buf: [512]u8 = undefined;
        const h = metal_bridge_binary_archive_create(device, path, &err_buf, 512);
        return .{ .handle = h };
    }

    pub fn deinit(self: *BinaryArchive) void {
        if (self.handle) |h| {
            metal_bridge_release(h);
            self.handle = null;
        }
    }

    pub fn available(self: *const BinaryArchive) bool {
        return self.handle != null;
    }

    pub fn add_compute_pipeline(self: *BinaryArchive, device: ?*anyopaque, pipeline: ?*anyopaque) bool {
        const h = self.handle orelse return false;
        var err_buf: [512]u8 = undefined;
        return metal_bridge_binary_archive_add_compute(h, device, pipeline, &err_buf, 512) != 0;
    }

    pub fn add_render_pipeline(self: *BinaryArchive, device: ?*anyopaque, pipeline: ?*anyopaque) bool {
        const h = self.handle orelse return false;
        var err_buf: [512]u8 = undefined;
        return metal_bridge_binary_archive_add_render(h, device, pipeline, &err_buf, 512) != 0;
    }

    pub fn serialize(self: *BinaryArchive) bool {
        const h = self.handle orelse return false;
        var err_buf: [512]u8 = undefined;
        return metal_bridge_binary_archive_serialize(h, &err_buf, 512) != 0;
    }

    pub fn create_compute_pipeline(
        self: *BinaryArchive,
        device: ?*anyopaque,
        function: ?*anyopaque,
    ) ?*anyopaque {
        const h = self.handle orelse return null;
        var err_buf: [512]u8 = undefined;
        return metal_bridge_device_new_compute_pipeline_with_archive(device, function, h, &err_buf, 512);
    }

    pub fn create_render_pipeline(
        self: *BinaryArchive,
        device: ?*anyopaque,
        pixel_format: u32,
        support_icb: c_int,
    ) ?*anyopaque {
        const h = self.handle orelse return null;
        var err_buf: [512]u8 = undefined;
        return metal_bridge_device_new_render_pipeline_with_archive(device, pixel_format, support_icb, h, &err_buf, 512);
    }
};

// ============================================================
// Device retain (needed by multi_adapter.zig when returning handles)

pub fn retain_device(dev: ?*anyopaque) void {
    metal_bridge_retain_device(dev);
}
