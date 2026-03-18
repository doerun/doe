// doe_canvas_event_native.zig — Canvas format query and DOM event stub exports.
// Sharded from doe_wgpu_native.zig to keep related surface concerns together.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");

// BGRA8Unorm is the Metal-native swapchain format on Apple Silicon.
// All modern macOS display hardware uses BGRA byte order for CAMetalLayer.
// The WebGPU spec allows the adapter to pick; Metal's preferred format is bgra8unorm.
const PREFERRED_CANVAS_FORMAT: u32 = types.WGPUTextureFormat_BGRA8Unorm;

// ============================================================
// Adapter: getPreferredCanvasFormat
// ============================================================

// Returns the preferred canvas texture format for the adapter.
// Metal always prefers bgra8unorm — the format is hardware-fixed, not adapter-instance-specific.
// The raw adapter pointer is accepted for ABI compatibility but not interrogated.
pub export fn doeNativeAdapterGetPreferredCanvasFormat(raw: ?*anyopaque) callconv(.c) u32 {
    _ = raw;
    return PREFERRED_CANVAS_FORMAT;
}

// ============================================================
// Device: DOM EventTarget stubs (addEventListener / removeEventListener)
// ============================================================

// addEventListener and removeEventListener are DOM EventTarget APIs.
// In a native non-browser runtime there is no event loop, no DOM, and no
// observer infrastructure — these calls are structurally no-ops.  They are
// exported to satisfy JS bindings that call them unconditionally on device
// creation; silently accepting them is the correct native-context behavior.
// No allocation, no crash, no side effects.

pub export fn doeNativeDeviceAddEventListener(
    dev_raw: ?*anyopaque,
    event_type_ptr: ?[*]const u8,
    event_type_len: usize,
    callback: ?*anyopaque,
    userdata: ?*anyopaque,
) callconv(.c) void {
    _ = dev_raw;
    _ = event_type_ptr;
    _ = event_type_len;
    _ = callback;
    _ = userdata;
    // DOM EventTarget API — no-op in native context; no event loop exists.
}

pub export fn doeNativeDeviceRemoveEventListener(
    dev_raw: ?*anyopaque,
    event_type_ptr: ?[*]const u8,
    event_type_len: usize,
    callback: ?*anyopaque,
    userdata: ?*anyopaque,
) callconv(.c) void {
    _ = dev_raw;
    _ = event_type_ptr;
    _ = event_type_len;
    _ = callback;
    _ = userdata;
    // DOM EventTarget API — no-op in native context; no event loop exists.
}
