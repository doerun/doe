const builtin = @import("builtin");
const std = @import("std");
const abi_copy = @import("core/abi/wgpu_copy_descriptor_types.zig");
const abi_texture = @import("core/abi/wgpu_texture_base_types.zig");
const queue_submit_ops = @import("backend/dropin_queue_submit.zig");
const native_types = @import("doe_native_object_types.zig");
const native_helpers = @import("doe_native_object_helpers.zig");
const native_rt_helpers = @import("doe_native_runtime_helpers.zig");
const native_exports = @import("doe_native_exports.zig");
const error_scope = @import("error_scope.zig");
const shared = @import("doe_queue_submit_shared.zig");

const has_vulkan = (builtin.os.tag == .linux);
const cast = native_helpers.cast;
const toOpaque = native_helpers.toOpaque;
const DoeBuffer = native_types.DoeBuffer;
const DoeQueue = native_types.DoeQueue;
const DoeTexture = native_types.DoeTexture;
const bridge = queue_submit_ops.metal_bridge;

extern fn doeNativeQueueSubmit(q_raw: ?*anyopaque, count: usize, cmd_bufs: [*]const ?*anyopaque) callconv(.c) void;

pub fn doeNativeQueueWriteBuffer(q_raw: ?*anyopaque, buf_raw: ?*anyopaque, offset: u64, data: [*]const u8, size: usize) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    const buf = cast(DoeBuffer, buf_raw) orelse return;
    const size_u64: u64 = @intCast(size);
    const write_end = std.math.add(u64, offset, size_u64) catch {
        q.dev.error_scopes.deliver(error_scope.ERROR_TYPE_VALIDATION, "wgpuQueueWriteBuffer range exceeds buffer size");
        return;
    };
    if (write_end > buf.size) {
        q.dev.error_scopes.deliver(error_scope.ERROR_TYPE_VALIDATION, "wgpuQueueWriteBuffer range exceeds buffer size");
        return;
    }
    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            if (buf.vk_mapped_ptr) |base| {
                const o: usize = @intCast(offset);
                @memcpy(base[o .. o + size], data[0..size]);
                return;
            }
            if (buf.vk_id != 0) {
                const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return;
                if (rt.compute_buffers.get(buf.vk_id)) |cb| {
                    if (cb.mapped) |ptr| {
                        const o: usize = @intCast(offset);
                        const d: [*]u8 = @ptrCast(ptr);
                        @memcpy(d[o .. o + size], data[0..size]);
                    }
                }
            }
        }
        return;
    }
    const contents = bridge.metal_bridge_buffer_contents(buf.mtl) orelse return;
    const dst = (contents + @as(usize, @intCast(offset)))[0..size];
    @memcpy(dst, data[0..size]);
}

fn copy_texture_for_browser_passthrough(
    q: *DoeQueue,
    source: *const abi_copy.WGPUTexelCopyTextureInfo,
    destination: *const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size: *const abi_copy.WGPUExtent3D,
) void {
    const src_texture = cast(DoeTexture, source.texture) orelse return;
    const dst_texture = cast(DoeTexture, destination.texture) orelse return;

    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return;
            if (src_texture.vk_id == 0 or dst_texture.vk_id == 0) return;
            rt.texture_copy(.{
                .src_handle = src_texture.vk_id,
                .src_mip = source.mipLevel,
                .src_x = source.origin.x,
                .src_y = source.origin.y,
                .src_z = source.origin.z,
                .dst_handle = dst_texture.vk_id,
                .dst_mip = destination.mipLevel,
                .dst_x = destination.origin.x,
                .dst_y = destination.origin.y,
                .dst_z = destination.origin.z,
                .width = copy_size.width,
                .height = copy_size.height,
                .depth_or_layers = copy_size.depthOrArrayLayers,
            }) catch |err| {
                shared.deliverInternalError(q.dev, "doe_queue_submit: texture copy: {s}", .{@errorName(err)});
            };
        }
        return;
    }

    const encoder = native_exports.doeNativeDeviceCreateCommandEncoder(toOpaque(q.dev), null) orelse return;
    defer native_exports.doeNativeCommandEncoderRelease(encoder);

    @import("doe_command_texture_native.zig").doeNativeCommandEncoderCopyTextureToTexture(
        encoder,
        source.texture,
        source.mipLevel,
        source.origin.z,
        source.origin.x,
        source.origin.y,
        source.origin.z,
        destination.texture,
        destination.mipLevel,
        destination.origin.z,
        destination.origin.x,
        destination.origin.y,
        destination.origin.z,
        copy_size.width,
        copy_size.height,
        copy_size.depthOrArrayLayers,
    );

    const command_buffer = native_exports.doeNativeCommandEncoderFinish(encoder, null) orelse return;
    defer native_exports.doeNativeCommandBufferRelease(command_buffer);
    var command_buffers = [1]?*anyopaque{command_buffer};
    doeNativeQueueSubmit(toOpaque(q), command_buffers.len, &command_buffers);
}

pub fn doeNativeQueueCopyTextureForBrowser(
    queue_raw: ?*anyopaque,
    source_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    destination_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size_raw: ?*const abi_copy.WGPUExtent3D,
    options_raw: ?*const abi_copy.WGPUCopyTextureForBrowserOptions,
) void {
    _ = options_raw;
    const queue = cast(DoeQueue, queue_raw) orelse return;
    const source = source_raw orelse return;
    const destination = destination_raw orelse return;
    const copy_size = copy_size_raw orelse return;
    copy_texture_for_browser_passthrough(queue, source, destination, copy_size);
}

const ext_texture_mod = @import("doe_external_texture_native.zig");
const DoeExternalTexture = ext_texture_mod.DoeExternalTexture;

fn copy_external_texture_to_dst(
    queue: *DoeQueue,
    ext: *const DoeExternalTexture,
    origin: abi_copy.WGPUOrigin3D,
    destination: *const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size: *const abi_copy.WGPUExtent3D,
) void {
    if (ext_texture_mod.resolvePlane0DoeTexture(ext)) |src_tex| {
        const source_copy = abi_copy.WGPUTexelCopyTextureInfo{
            .texture = native_helpers.toOpaque(src_tex),
            .mipLevel = 0,
            .origin = origin,
            .aspect = abi_texture.WGPUTextureAspect_All,
        };
        copy_texture_for_browser_passthrough(queue, &source_copy, destination, copy_size);
        return;
    }
    const src_mtl = ext_texture_mod.resolvePlane0MtlHandle(ext) orelse return;
    const dst_texture = cast(DoeTexture, destination.texture) orelse return;
    const dst_mtl = dst_texture.mtl orelse return;
    if (queue.dev.backend != .metal) return;
    const cmd_buf = bridge.metal_bridge_create_command_buffer(queue.dev.mtl_queue);
    if (cmd_buf == null) return;
    const blit = bridge.metal_bridge_cmd_buf_blit_encoder(cmd_buf);
    if (blit == null) {
        bridge.metal_bridge_release(cmd_buf);
        return;
    }
    bridge.metal_bridge_blit_encoder_copy_texture_to_texture(
        blit,
        src_mtl,
        0,
        dst_mtl,
        destination.mipLevel,
        copy_size.width,
        copy_size.height,
        copy_size.depthOrArrayLayers,
    );
    bridge.metal_bridge_end_blit_encoding(blit);
    bridge.metal_bridge_command_buffer_commit(cmd_buf);
    bridge.metal_bridge_command_buffer_wait_completed(cmd_buf);
    bridge.metal_bridge_release(cmd_buf);
}

pub fn doeNativeQueueCopyExternalImageToTexture(
    queue_raw: ?*anyopaque,
    source_raw: ?*const abi_copy.WGPUImageCopyExternalTexture,
    destination_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size_raw: ?*const abi_copy.WGPUExtent3D,
) void {
    const source = source_raw orelse return;
    const destination = destination_raw orelse return;
    const copy_size = copy_size_raw orelse return;
    const ext = ext_texture_mod.cast(source.externalTexture) orelse return;
    if (ext.expired) return;
    const queue = cast(DoeQueue, queue_raw) orelse return;
    copy_external_texture_to_dst(queue, ext, source.origin, destination, copy_size);
}

pub fn doeNativeQueueCopyExternalTextureForBrowser(
    queue_raw: ?*anyopaque,
    source_raw: ?*const abi_copy.WGPUImageCopyExternalTexture,
    destination_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size_raw: ?*const abi_copy.WGPUExtent3D,
    options_raw: ?*const abi_copy.WGPUCopyTextureForBrowserOptions,
) void {
    _ = options_raw;
    const source = source_raw orelse return;
    const destination = destination_raw orelse return;
    const copy_size = copy_size_raw orelse return;
    const ext = ext_texture_mod.cast(source.externalTexture) orelse return;
    if (ext.expired) return;
    const queue = cast(DoeQueue, queue_raw) orelse return;
    copy_external_texture_to_dst(queue, ext, source.origin, destination, copy_size);
}
