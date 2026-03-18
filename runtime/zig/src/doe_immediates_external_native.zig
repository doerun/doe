// doe_immediates_external_native.zig — Unsupported stubs for setImmediates and importExternalTexture.
// Sharded from doe_wgpu_native.zig; groups newer WebGPU APIs not yet implemented in any backend.
//
// All exports here represent explicitly tracked gaps, not silent omissions.
// Each function logs an actionable error so callers can diagnose missing support.

const std = @import("std");

// ============================================================
// setImmediates — push constants / immediate data upload
// ============================================================

// setImmediates is a newer WebGPU extension (analogous to push constants in Vulkan /
// root constants in D3D12 / setBytes in Metal).  No Doe backend implements the
// immediate-data upload path yet — Metal requires `setBytes:length:atIndex:` at
// the encode site, which needs encoder-type dispatch (compute vs render) and a
// slot-allocation contract that has not been specified in the Doe backend vTable.
// Until the contract is established and implemented in all backends, these functions
// fail explicitly rather than silently skipping the upload (which would produce
// wrong results for any shader that reads immediates data).

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
    // setImmediates (push constants) is not yet implemented in any Doe backend.
    // Shader reads of immediates data will produce undefined values if this is called.
    std.log.err("doe: doeNativeBindingCommandsSetImmediates: unsupported — " ++
        "setImmediates (push constants) has no backend implementation; " ++
        "expected: encoder handle, slot index, data pointer and byte length", .{});
}

pub export fn doeNativeComputePassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    _ = encoder_raw;
    _ = index;
    _ = data_ptr;
    _ = data_len;
    // setImmediates on compute pass encoders is not yet implemented.
    // Metal equivalent is setBytes:length:atIndex: on MTLComputeCommandEncoder.
    std.log.err("doe: doeNativeComputePassSetImmediates: unsupported — " ++
        "setImmediates (push constants) has no compute backend implementation; " ++
        "expected: compute pass encoder handle, slot index, data pointer and byte length", .{});
}

pub export fn doeNativeRenderPassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    _ = encoder_raw;
    _ = index;
    _ = data_ptr;
    _ = data_len;
    // setImmediates on render pass encoders is not yet implemented.
    // Metal equivalent is setVertexBytes:length:atIndex: / setFragmentBytes:length:atIndex:.
    std.log.err("doe: doeNativeRenderPassSetImmediates: unsupported — " ++
        "setImmediates (push constants) has no render backend implementation; " ++
        "expected: render pass encoder handle, slot index, data pointer and byte length", .{});
}

pub export fn doeNativeRenderBundleEncoderSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    _ = encoder_raw;
    _ = index;
    _ = data_ptr;
    _ = data_len;
    // setImmediates on render bundle encoders is not yet implemented.
    // Render bundles are pre-recorded; immediate data upload requires per-encode
    // setBytes calls that are incompatible with the current bundle execution model.
    std.log.err("doe: doeNativeRenderBundleEncoderSetImmediates: unsupported — " ++
        "setImmediates (push constants) has no render bundle implementation; " ++
        "expected: render bundle encoder handle, slot index, data pointer and byte length", .{});
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
