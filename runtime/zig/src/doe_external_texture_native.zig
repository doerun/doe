// doe_external_texture_native.zig — ExternalTexture handle for the Doe WebGPU runtime.
//
// Wraps plane texture views and color conversion parameters from the
// WGPUExternalTextureDescriptor into an opaque handle that can be used
// in bind groups. The browser (Chromium) handles the actual video frame
// import (DMABUF, IOSurface, DXGI shared handle) and passes the resulting
// texture views through the descriptor; Doe just needs to hold them.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");

const MAGIC_EXTERNAL_TEXTURE: u32 = 0xD0E1_0013;

pub const DoeExternalTexture = struct {
    pub const TYPE_MAGIC = MAGIC_EXTERNAL_TEXTURE;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    expired: bool = false,
    plane0: ?*anyopaque = null,
    plane1: ?*anyopaque = null,
    is_single_plane: bool = true,
    width: u32 = 0,
    height: u32 = 0,
};

pub fn cast(raw: ?*anyopaque) ?*DoeExternalTexture {
    return native.cast(DoeExternalTexture, raw);
}

// -- Creation --

pub export fn doeNativeDeviceImportExternalTexture(
    dev_raw: ?*anyopaque,
    descriptor: ?*const anyopaque,
) callconv(.c) ?*anyopaque {
    return doeNativeDeviceCreateExternalTexture(dev_raw, descriptor);
}

/// WGPUExternalTextureDescriptor C ABI layout (Dawn, x86_64):
///   nextInChain: *WGPUChainedStruct  (offset 0, 8 bytes)
///   label: WGPUStringView            (offset 8, 16 bytes = ptr + size_t)
///   plane0: WGPUTextureView          (offset 24, 8 bytes)
///   plane1: WGPUTextureView          (offset 32, 8 bytes)
const PLANE0_OFFSET = 24;
const PLANE1_OFFSET = 32;
const MIN_DESCRIPTOR_SIZE = 40;

pub export fn doeNativeDeviceCreateExternalTexture(
    dev_raw: ?*anyopaque,
    descriptor: ?*const anyopaque,
) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    const desc = descriptor orelse return null;
    const desc_ptr: [*]const u8 = @ptrCast(desc);
    const plane0 = @as(*const ?*anyopaque, @ptrCast(@alignCast(desc_ptr + PLANE0_OFFSET))).*;
    const plane1 = @as(*const ?*anyopaque, @ptrCast(@alignCast(desc_ptr + PLANE1_OFFSET))).*;

    const ext = std.heap.c_allocator.create(DoeExternalTexture) catch return null;
    ext.* = .{
        .plane0 = plane0,
        .plane1 = plane1,
        .is_single_plane = plane1 == null,
    };
    return @ptrCast(ext);
}

// -- Lifecycle --

pub export fn doeNativeExternalTextureAddRef(raw: ?*anyopaque) callconv(.c) void {
    const ext = cast(raw) orelse return;
    ext.ref_count +|= 1;
}

pub export fn doeNativeExternalTextureRelease(raw: ?*anyopaque) callconv(.c) void {
    const ext = cast(raw) orelse return;
    if (ext.ref_count <= 1) {
        std.heap.c_allocator.destroy(ext);
        return;
    }
    ext.ref_count -= 1;
}

pub export fn doeNativeExternalTextureDestroy(raw: ?*anyopaque) callconv(.c) void {
    const ext = cast(raw) orelse return;
    ext.expired = true;
}

pub export fn doeNativeExternalTextureExpire(raw: ?*anyopaque) callconv(.c) void {
    const ext = cast(raw) orelse return;
    ext.expired = true;
}

pub export fn doeNativeExternalTextureRefresh(raw: ?*anyopaque) callconv(.c) void {
    const ext = cast(raw) orelse return;
    ext.expired = false;
}

pub export fn doeNativeExternalTextureSetLabel(
    raw: ?*anyopaque,
    _: [*]const u8,
    _: usize,
) callconv(.c) void {
    _ = cast(raw) orelse return;
}
