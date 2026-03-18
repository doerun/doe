// doe_immediates_external_native.zig — immediate-data forwarding and external-texture stubs.
// Sharded from doe_wgpu_native.zig; groups newer WebGPU APIs that are not part of
// the core command/resource path modules.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const resource_table_procs = @import("wgpu_p1_resource_table_procs.zig");

extern fn wgpuComputePassEncoderSetImmediates(
    encoder: types.WGPUComputePassEncoder,
    index: u32,
    data: ?*const anyopaque,
    data_len: usize,
) callconv(.c) void;
extern fn wgpuRenderPassEncoderSetImmediates(
    encoder: types.WGPURenderPassEncoder,
    index: u32,
    data: ?*const anyopaque,
    data_len: usize,
) callconv(.c) void;
extern fn wgpuRenderBundleEncoderSetImmediates(
    encoder: resource_table_procs.WGPURenderBundleEncoder,
    index: u32,
    data: ?*const anyopaque,
    data_len: usize,
) callconv(.c) void;

fn as_anyopaque_const(data_ptr: ?[*]const u8) ?*const anyopaque {
    return if (data_ptr) |ptr| @ptrCast(ptr) else null;
}

// ============================================================
// setImmediates — push constants / immediate data upload
// ============================================================

// setImmediates is the WebGPU immediate-data surface. There is no generic
// proc for the abstract binding-commands mixin, so the concrete compute/render
// pass entry points are forwarded directly to the provider WebGPU symbols below.
// The mixin export remains an explicit unsupported entry because it has no
// standalone runtime object or generic proc target.

pub export fn doeNativeBindingCommandsSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    _ = encoder_raw;
    _ = index;
    _ = data_ptr;
    _ = data_len;
    std.log.err("doe: doeNativeBindingCommandsSetImmediates: unsupported — " ++
        "abstract mixin entry has no standalone encoder type; use the concrete " ++
        "compute/render pass setImmediates entry points", .{});
}

pub export fn doeNativeComputePassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    const encoder = encoder_raw orelse return;
    wgpuComputePassEncoderSetImmediates(@ptrCast(encoder), index, as_anyopaque_const(data_ptr), data_len);
}

pub export fn doeNativeRenderPassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    const encoder = encoder_raw orelse return;
    wgpuRenderPassEncoderSetImmediates(@ptrCast(encoder), index, as_anyopaque_const(data_ptr), data_len);
}

pub export fn doeNativeRenderBundleEncoderSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    const encoder = encoder_raw orelse return;
    wgpuRenderBundleEncoderSetImmediates(@ptrCast(encoder), index, as_anyopaque_const(data_ptr), data_len);
}

// ============================================================
// importExternalTexture — OS-level video frame / shared texture import
// ============================================================

// importExternalTexture requires OS-level video frame integration:
//   - Metal: CVPixelBuffer / IOSurface shared-texture import via MTLTexture descriptors
//   - Vulkan: DMABUF external memory import (VK_EXT_external_memory_dmabuf)
//   - D3D12: shared handle import (DXGI shared resource)
// None of these import paths are bootstrapped in any Doe backend.
// Returns null to signal failure — the caller must check for null and handle it.
pub export fn doeNativeDeviceImportExternalTexture(
    dev_raw: ?*anyopaque,
    descriptor: ?*const anyopaque,
) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    _ = descriptor;
    // importExternalTexture is not implemented in any Doe backend.
    // Requires OS-level video frame / shared texture import:
    //   Metal: CVPixelBuffer / IOSurface via MTLTexture
    //   Vulkan: DMABUF external memory (VK_EXT_external_memory_dmabuf)
    //   D3D12: DXGI shared resource handle
    std.log.err("doe: doeNativeDeviceImportExternalTexture: unsupported — " ++
        "video frame / shared texture import path not bootstrapped in any backend", .{});
    return null;
}
