// doe_immediates_external_native.zig — immediate-data forwarding and external-texture stubs.
// Sharded from doe_wgpu_native.zig; groups newer WebGPU APIs that are not part of
// the core command/resource path modules.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const resource_table_procs = @import("wgpu_p1_resource_table_procs.zig");
const native = @import("doe_wgpu_native.zig");
const render_bundle = @import("render_bundle.zig");

const DoePipelineLayout = native.DoePipelineLayout;

fn validate_immediate_data(data_ptr: ?[*]const u8, data_len: usize) bool {
    if (data_len == 0) return true;
    return data_ptr != null;
}

fn immediate_budget(layout: ?*DoePipelineLayout) u32 {
    return if (layout) |l| l.immediate_size else 0;
}

fn within_immediate_budget(layout: ?*DoePipelineLayout, index: u32, data_len: usize) bool {
    const budget = immediate_budget(layout);
    if (budget == 0) return data_len == 0 and index == 0;
    return @as(u64, index) + @as(u64, @intCast(data_len)) <= @as(u64, budget);
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
    const encoder = native.cast(native.DoeComputePass, encoder_raw) orelse return;
    if (!validate_immediate_data(data_ptr, data_len)) {
        std.log.err("doe: compute setImmediates rejected null data pointer for non-zero size", .{});
        return;
    }
    const layout = if (encoder.pipeline) |pipeline| pipeline.layout else null;
    if (!within_immediate_budget(layout, index, data_len)) {
        std.log.err("doe: compute setImmediates exceeds pipeline layout immediateSize (index={} size={} budget={})", .{
            index,
            data_len,
            immediate_budget(layout),
        });
    }
}

pub export fn doeNativeRenderPassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    const encoder = native.cast(native.DoeRenderPass, encoder_raw) orelse return;
    if (!validate_immediate_data(data_ptr, data_len)) {
        std.log.err("doe: render pass setImmediates rejected null data pointer for non-zero size", .{});
        return;
    }
    const layout = if (encoder.pipeline) |pipeline| pipeline.layout else null;
    if (!within_immediate_budget(layout, index, data_len)) {
        std.log.err("doe: render pass setImmediates exceeds pipeline layout immediateSize (index={} size={} budget={})", .{
            index,
            data_len,
            immediate_budget(layout),
        });
    }
}

pub export fn doeNativeRenderBundleEncoderSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void {
    _ = index;
    const encoder = render_bundle.cast_bundle_encoder(encoder_raw) orelse return;
    _ = encoder;
    if (!validate_immediate_data(data_ptr, data_len)) {
        std.log.err("doe: render bundle setImmediates rejected null data pointer for non-zero size", .{});
    }
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
