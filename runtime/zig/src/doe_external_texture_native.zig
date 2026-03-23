// doe_external_texture_native.zig — ExternalTexture handle for the Doe WebGPU runtime.
//
// Wraps plane texture views and color conversion parameters from the
// WGPUExternalTextureDescriptor into an opaque handle that can be used
// in bind groups. The browser (Chromium) handles the actual video frame
// import (DMABUF, IOSurface, DXGI shared handle) and passes the resulting
// texture views through the descriptor; Doe just needs to hold them.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");

const DoeTextureView = native.DoeTextureView;

const MAGIC_EXTERNAL_TEXTURE: u32 = 0xD0E1_0013;

// ============================================================
// Instance-level external texture registry
// ============================================================
//
// Tracks the number of live (non-released) external textures per
// DoeInstance pointer. This allows the instance to know whether
// external resources still reference it, preventing premature
// teardown while video frame textures are in flight.

var instance_ext_counts: std.AutoHashMapUnmanaged(usize, u32) = .{};

fn registry_key(inst: *native.DoeInstance) usize {
    return @intFromPtr(inst);
}

/// Register an external texture with its owning instance.
fn instance_register(inst: *native.DoeInstance) void {
    const key = registry_key(inst);
    if (instance_ext_counts.getPtr(key)) |slot| {
        slot.* +|= 1;
    } else {
        instance_ext_counts.put(std.heap.c_allocator, key, 1) catch {};
    }
}

/// Deregister an external texture from its owning instance.
fn instance_deregister(inst: *native.DoeInstance) void {
    const key = registry_key(inst);
    if (instance_ext_counts.getPtr(key)) |slot| {
        if (slot.* <= 1) {
            _ = instance_ext_counts.remove(key);
        } else {
            slot.* -= 1;
        }
    }
}

/// Query how many external textures are alive for the given instance.
pub fn instance_external_texture_count(inst_raw: ?*anyopaque) u32 {
    const inst = native.cast(native.DoeInstance, inst_raw) orelse return 0;
    return instance_ext_counts.get(registry_key(inst)) orelse 0;
}

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
    // Backref to Instance — prevents Instance from being freed while external
    // textures referencing it are still alive.
    instance: ?*native.DoeInstance = null,
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

fn resolve_device_instance(dev_raw: ?*anyopaque) ?*native.DoeInstance {
    const dev = native.cast(native.DoeDevice, dev_raw) orelse return null;
    const adapter = dev.adapter orelse return null;
    return adapter.instance;
}

pub export fn doeNativeDeviceCreateExternalTexture(
    dev_raw: ?*anyopaque,
    descriptor: ?*const anyopaque,
) callconv(.c) ?*anyopaque {
    const desc = descriptor orelse return null;
    const desc_ptr: [*]const u8 = @ptrCast(desc);
    const plane0 = @as(*const ?*anyopaque, @ptrCast(@alignCast(desc_ptr + PLANE0_OFFSET))).*;
    const plane1 = @as(*const ?*anyopaque, @ptrCast(@alignCast(desc_ptr + PLANE1_OFFSET))).*;
    const plane0_view = native.cast(DoeTextureView, plane0) orelse return null;
    const plane1_view = native.cast(DoeTextureView, plane1);

    const instance_ref = resolve_device_instance(dev_raw);
    // Add-ref the Instance so it stays alive while the external texture exists.
    if (instance_ref) |inst| inst.ref_count +|= 1;
    native.object_add_ref(DoeTextureView, native.toOpaque(plane0_view));
    if (plane1_view) |view| native.object_add_ref(DoeTextureView, native.toOpaque(view));

    const ext = std.heap.c_allocator.create(DoeExternalTexture) catch {
        // Roll back the add-ref on allocation failure.
        if (instance_ref) |inst| {
            if (inst.ref_count > 1) inst.ref_count -= 1;
        }
        native.doeNativeTextureViewRelease(native.toOpaque(plane0_view));
        if (plane1_view) |view| native.doeNativeTextureViewRelease(native.toOpaque(view));
        return null;
    };
    ext.* = .{
        .plane0 = plane0,
        .plane1 = plane1,
        .is_single_plane = plane1 == null,
        .instance = instance_ref,
    };
    if (instance_ref) |inst| instance_register(inst);
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
        const instance_ref = ext.instance;
        const plane0 = ext.plane0;
        const plane1 = ext.plane1;
        // Deregister from the instance registry before releasing the backref.
        if (instance_ref) |inst| instance_deregister(inst);
        std.heap.c_allocator.destroy(ext);
        if (plane0 != null) native.doeNativeTextureViewRelease(plane0);
        if (plane1 != null) native.doeNativeTextureViewRelease(plane1);
        // Release the Instance backref after freeing the external texture.
        if (instance_ref) |inst| {
            @import("doe_instance_device_native.zig").doeNativeInstanceRelease(native.toOpaque(inst));
        }
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
