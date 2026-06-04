// doe_render_native.zig — Render Pass C ABI exports for the Doe native backend.
// Texture/Sampler ops sharded to doe_texture_sampler_native.zig.
// Render Pipeline ops sharded to doe_render_pipeline_native.zig.

const std = @import("std");
const abi_texture = @import("core/abi/wgpu_texture_base_types.zig");
const abi_pipeline = @import("core/abi/wgpu_pipeline_descriptor_types.zig");
const native_types = @import("doe_native_object_types.zig");
const native_shared = @import("doe_native_shared_types.zig");
const native_cmds = @import("doe_native_command_types.zig");
const native_helpers = @import("doe_native_object_helpers.zig");

const alloc = native_helpers.alloc;
const make = native_helpers.make;
const cast = native_helpers.cast;
const toOpaque = native_helpers.toOpaque;
const label_store = native_helpers.label_store;

// D3D12 texture view swizzle classification for descriptor binding.
pub const D3D12TextureViewSwizzleMode = enum { identity, swizzled_sampled, unsupported_storage };

pub fn d3d12TextureViewSwizzleMode(
    usage: u64,
    swizzle_r: u32,
    swizzle_g: u32,
    swizzle_b: u32,
    swizzle_a: u32,
) D3D12TextureViewSwizzleMode {
    const is_identity = (swizzle_r == abi_texture.WGPUTextureComponentSwizzle_Red or swizzle_r == 0) and
        (swizzle_g == abi_texture.WGPUTextureComponentSwizzle_Green or swizzle_g == 0) and
        (swizzle_b == abi_texture.WGPUTextureComponentSwizzle_Blue or swizzle_b == 0) and
        (swizzle_a == abi_texture.WGPUTextureComponentSwizzle_Alpha or swizzle_a == 0);
    const wants_storage = (usage & abi_texture.WGPUTextureUsage_StorageBinding) != 0 and
        (usage & abi_texture.WGPUTextureUsage_TextureBinding) == 0;
    if (wants_storage and !is_identity) return .unsupported_storage;
    if (is_identity) return .identity;
    return .swizzled_sampled;
}

const DoeDevice = native_types.DoeDevice;
const DoeBuffer = native_types.DoeBuffer;
const DoeTexture = native_types.DoeTexture;
const DoeTextureView = native_types.DoeTextureView;
const DoeBindGroup = native_types.DoeBindGroup;
const DoeRenderPipeline = native_types.DoeRenderPipeline;
const DoeRenderPass = native_types.DoeRenderPass;
const DoeCommandEncoder = native_types.DoeCommandEncoder;

const texture_sampler = @import("doe_texture_sampler_native.zig");
const render_pipeline = @import("doe_render_pipeline_native.zig");

// Re-export texture/sampler symbols for callers that import doe_render_native.
pub const doeNativeDeviceCreateTexture = texture_sampler.doeNativeDeviceCreateTexture;
pub const doeNativeTextureCreateView = texture_sampler.doeNativeTextureCreateView;
pub const doeNativeTextureDestroy = texture_sampler.doeNativeTextureDestroy;
pub const doeNativeTextureRelease = texture_sampler.doeNativeTextureRelease;
pub const doeNativeTextureViewRelease = texture_sampler.doeNativeTextureViewRelease;
pub const doeNativeDeviceCreateSampler = texture_sampler.doeNativeDeviceCreateSampler;
pub const doeNativeSamplerRelease = texture_sampler.doeNativeSamplerRelease;

// Re-export render pipeline symbols.
pub const doeNativeDeviceCreateRenderPipeline = render_pipeline.doeNativeDeviceCreateRenderPipeline;
pub const doeNativeRenderPipelineRelease = render_pipeline.doeNativeRenderPipelineRelease;

const DEFAULT_MAX_DRAW_COUNT: u64 = 50_000_000;

fn reserve_render_draw(pass: *DoeRenderPass) bool {
    if (pass.recorded_draw_count >= pass.max_draw_count) {
        std.log.err("doe: render pass draw rejected: maxDrawCount={} exhausted", .{pass.max_draw_count});
        return false;
    }
    pass.recorded_draw_count += 1;
    return true;
}

// ============================================================
// Render Pass
// ============================================================

pub export fn doeNativeCommandEncoderBeginRenderPass(enc_raw: ?*anyopaque, desc: ?*const abi_pipeline.WGPURenderPassDescriptor) callconv(.c) ?*anyopaque {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const pass = make(DoeRenderPass) orelse return null;
    pass.* = .{ .enc = enc };
    if (desc) |d| {
        pass.max_draw_count = if (d.maxDrawCount == 0) DEFAULT_MAX_DRAW_COUNT else d.maxDrawCount;
        pass.occlusion_query_set = d.occlusionQuerySet;
        if (d.colorAttachmentCount > 0) {
            if (d.colorAttachments) |attachments| {
                const att = attachments[0];
                const tv = cast(DoeTextureView, att.view);
                if (tv) |v| {
                    pass.target = if (texture_sampler.d3d12_texture_view_registry.contains(att.view))
                        v.tex.mtl
                    else if (v.handle) |handle|
                        handle
                    else
                        v.tex.mtl;
                    pass.target_view_handle = @intFromPtr(v);
                    pass.target_format = if (v.format != 0) v.format else v.tex.format;
                    pass.sample_count = if (v.tex.sample_count != 0) v.tex.sample_count else 1;
                }
                if (cast(DoeTextureView, att.resolveTarget)) |resolve_view| {
                    pass.resolve_target = resolve_view.tex.mtl;
                    pass.resolve_target_view_handle = @intFromPtr(resolve_view);
                }
                pass.depth_slice = att.depthSlice;
                pass.clear_r = att.clearValue.r;
                pass.clear_g = att.clearValue.g;
                pass.clear_b = att.clearValue.b;
                pass.clear_a = att.clearValue.a;
            }
        }
        if (d.depthStencilAttachment) |depth_att| {
            if (cast(DoeTextureView, depth_att.view)) |v| {
                pass.depth_target = if (texture_sampler.d3d12_texture_view_registry.contains(depth_att.view))
                    v.tex.mtl
                else if (v.handle) |handle|
                    handle
                else
                    v.tex.mtl;
                pass.depth_target_view_handle = @intFromPtr(v);
                pass.depth_stencil_format = if (v.format != 0) v.format else v.tex.format;
            }
            pass.depth_read_only = depth_att.depthReadOnly != 0;
            pass.stencil_read_only = depth_att.stencilReadOnly != 0;
        }
    }
    return toOpaque(pass);
}

pub export fn doeNativeRenderPassSetPipeline(pass_raw: ?*anyopaque, pip_raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.pipeline = cast(DoeRenderPipeline, pip_raw);
    if (pass.pipeline) |pipeline| {
        pass.depth_compare = pipeline.depth_compare;
        pass.depth_write_enabled = pipeline.depth_write_enabled;
    }
}

pub export fn doeNativeRenderPassRecordViewportState(
    pass_raw: ?*anyopaque,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    min_depth: f64,
    max_depth: f64,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.viewport_x = @floatCast(x);
    pass.viewport_y = @floatCast(y);
    pass.viewport_width = @floatCast(width);
    pass.viewport_height = @floatCast(height);
    pass.viewport_min_depth = @floatCast(min_depth);
    pass.viewport_max_depth = @floatCast(max_depth);
}

pub export fn doeNativeRenderPassRecordScissorState(
    pass_raw: ?*anyopaque,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.scissor_x = x;
    pass.scissor_y = y;
    pass.scissor_width = width;
    pass.scissor_height = height;
}

pub export fn doeNativeRenderPassRecordBlendConstantState(
    pass_raw: ?*anyopaque,
    r: f64,
    g: f64,
    b: f64,
    a: f64,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.blend_constant = .{
        @floatCast(r),
        @floatCast(g),
        @floatCast(b),
        @floatCast(a),
    };
}

pub export fn doeNativeRenderPassRecordStencilReferenceState(
    pass_raw: ?*anyopaque,
    reference: u32,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.stencil_reference = reference;
}

pub export fn doeNativeRenderPassDraw(pass_raw: ?*anyopaque, vertex_count: u32, instance_count: u32, first_vertex: u32, first_instance: u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (!reserve_render_draw(pass)) return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_draw(pass, vertex_count, instance_count, first_vertex, first_instance);
        return;
    }
    const pip = pass.pipeline orelse return;
    pass.enc.cmds.append(alloc, .{ .render_pass = .{
        .pso = pip.mtl_pso,
        .root_signature = pip.backend_root_signature,
        .depth_state = pip.depth_state,
        .target = pass.target,
        .resolve_target = pass.resolve_target,
        .depth_target = pass.depth_target,
        .target_view_handle = pass.target_view_handle,
        .resolve_target_view_handle = pass.resolve_target_view_handle,
        .depth_target_view_handle = pass.depth_target_view_handle,
        .target_format = pass.target_format,
        .depth_stencil_format = pass.depth_stencil_format,
        .sample_count = if (pass.sample_count != 0) pass.sample_count else pip.sample_count,
        .depth_slice = pass.depth_slice,
        .depth_read_only = pass.depth_read_only,
        .stencil_read_only = pass.stencil_read_only,
        .topology = pip.topology,
        .front_face = pip.front_face,
        .cull_mode = pip.cull_mode,
        .draw_count = 1,
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .first_vertex = first_vertex,
        .first_instance = first_instance,
        .vertex_buffers = blk: {
            var buffers: [native_shared.MAX_VERTEX_BUFFERS]?*anyopaque = [_]?*anyopaque{null} ** native_shared.MAX_VERTEX_BUFFERS;
            var i: usize = 0;
            while (i < native_shared.MAX_VERTEX_BUFFERS) : (i += 1) {
                buffers[i] = if (pass.vertex_buffers[i]) |buffer| buffer.mtl else null;
            }
            break :blk buffers;
        },
        .vertex_buffer_offsets = pass.vertex_buffer_offsets,
        .vertex_buffer_sizes = pass.vertex_buffer_sizes,
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .depth_compare = pass.depth_compare,
        .depth_write_enabled = pass.depth_write_enabled,
        .unclipped_depth = pip.unclipped_depth,
        .clear_r = pass.clear_r,
        .clear_g = pass.clear_g,
        .clear_b = pass.clear_b,
        .clear_a = pass.clear_a,
    } }) catch std.debug.panic("doe_render_native: OOM recording render command", .{});
}

pub export fn doeNativeRenderPassSetVertexBuffer(pass_raw: ?*anyopaque, slot: u32, buffer_raw: ?*anyopaque, offset: u64, size: u64) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (slot >= native_shared.MAX_VERTEX_BUFFERS) return;
    const buffer = cast(DoeBuffer, buffer_raw);
    if (buffer != null and buffer.?.error_object) return;
    pass.vertex_buffers[slot] = buffer;
    pass.vertex_buffer_offsets[slot] = offset;
    pass.vertex_buffer_sizes[slot] = size;
}

pub export fn doeNativeRenderPassSetIndexBuffer(pass_raw: ?*anyopaque, buffer_raw: ?*anyopaque, format: u32, offset: u64, size: u64) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    const buffer = cast(DoeBuffer, buffer_raw);
    if (buffer != null and buffer.?.error_object) return;
    pass.index_buffer = buffer;
    pass.index_format = format;
    pass.index_offset = offset;
    pass.index_buffer_size = size;
}

pub export fn doeNativeRenderPassSetBindGroup(pass_raw: ?*anyopaque, group_index: u32, group_raw: ?*anyopaque, dynamic_offset_count: usize, dynamic_offsets: ?[*]const u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (group_index >= native_shared.MAX_RENDER_BIND_GROUPS) return;
    pass.bind_groups[group_index] = cast(DoeBindGroup, group_raw);
    _ = dynamic_offset_count;
    _ = dynamic_offsets;
}

pub export fn doeNativeRenderPassDrawIndexed(pass_raw: ?*anyopaque, index_count: u32, instance_count: u32, first_index: u32, base_vertex: i32, first_instance: u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (!reserve_render_draw(pass)) return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_draw_indexed(pass, index_count, instance_count, first_index, base_vertex, first_instance);
        return;
    }
    const pip = pass.pipeline orelse return;
    pass.enc.cmds.append(alloc, .{ .render_pass = .{
        .pso = pip.mtl_pso,
        .root_signature = pip.backend_root_signature,
        .depth_state = pip.depth_state,
        .target = pass.target,
        .resolve_target = pass.resolve_target,
        .depth_target = pass.depth_target,
        .target_view_handle = pass.target_view_handle,
        .resolve_target_view_handle = pass.resolve_target_view_handle,
        .depth_target_view_handle = pass.depth_target_view_handle,
        .target_format = pass.target_format,
        .depth_stencil_format = pass.depth_stencil_format,
        .sample_count = if (pass.sample_count != 0) pass.sample_count else pip.sample_count,
        .depth_slice = pass.depth_slice,
        .depth_read_only = pass.depth_read_only,
        .stencil_read_only = pass.stencil_read_only,
        .topology = pip.topology,
        .front_face = pip.front_face,
        .cull_mode = pip.cull_mode,
        .draw_count = 1,
        .vertex_count = 0,
        .instance_count = instance_count,
        .first_vertex = 0,
        .first_instance = first_instance,
        .indexed = true,
        .index_buffer = if (pass.index_buffer) |buffer| buffer.mtl else null,
        .index_offset = pass.index_offset,
        .index_format = pass.index_format,
        .index_buffer_size = pass.index_buffer_size,
        .index_count = index_count,
        .first_index = first_index,
        .base_vertex = base_vertex,
        .vertex_buffers = blk: {
            var buffers: [native_shared.MAX_VERTEX_BUFFERS]?*anyopaque = [_]?*anyopaque{null} ** native_shared.MAX_VERTEX_BUFFERS;
            var i: usize = 0;
            while (i < native_shared.MAX_VERTEX_BUFFERS) : (i += 1) {
                buffers[i] = if (pass.vertex_buffers[i]) |buffer| buffer.mtl else null;
            }
            break :blk buffers;
        },
        .vertex_buffer_offsets = pass.vertex_buffer_offsets,
        .vertex_buffer_sizes = pass.vertex_buffer_sizes,
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .depth_compare = pass.depth_compare,
        .depth_write_enabled = pass.depth_write_enabled,
        .unclipped_depth = pip.unclipped_depth,
        .clear_r = pass.clear_r,
        .clear_g = pass.clear_g,
        .clear_b = pass.clear_b,
        .clear_a = pass.clear_a,
    } }) catch std.debug.panic("doe_render_native: OOM recording indexed render command", .{});
}

fn base_render_cmd(pass: *DoeRenderPass, pip: *DoeRenderPipeline) std.meta.TagPayloadByName(native_cmds.RecordedCmd, "render_pass") {
    return .{
        .pso = pip.mtl_pso,
        .root_signature = pip.backend_root_signature,
        .depth_state = pip.depth_state,
        .target = pass.target,
        .resolve_target = pass.resolve_target,
        .depth_target = pass.depth_target,
        .target_view_handle = pass.target_view_handle,
        .resolve_target_view_handle = pass.resolve_target_view_handle,
        .depth_target_view_handle = pass.depth_target_view_handle,
        .target_format = pass.target_format,
        .depth_stencil_format = pass.depth_stencil_format,
        .sample_count = if (pass.sample_count != 0) pass.sample_count else pip.sample_count,
        .depth_slice = pass.depth_slice,
        .depth_read_only = pass.depth_read_only,
        .stencil_read_only = pass.stencil_read_only,
        .topology = pip.topology,
        .front_face = pip.front_face,
        .cull_mode = pip.cull_mode,
        .draw_count = 1,
        .vertex_count = 0,
        .instance_count = 0,
        .first_vertex = 0,
        .first_instance = 0,
        .vertex_buffers = blk: {
            var buffers: [native_shared.MAX_VERTEX_BUFFERS]?*anyopaque = [_]?*anyopaque{null} ** native_shared.MAX_VERTEX_BUFFERS;
            var i: usize = 0;
            while (i < native_shared.MAX_VERTEX_BUFFERS) : (i += 1) {
                buffers[i] = if (pass.vertex_buffers[i]) |buffer| buffer.mtl else null;
            }
            break :blk buffers;
        },
        .vertex_buffer_offsets = pass.vertex_buffer_offsets,
        .vertex_buffer_sizes = pass.vertex_buffer_sizes,
        .blend_constant = pass.blend_constant,
        .stencil_reference = pass.stencil_reference,
        .depth_compare = pass.depth_compare,
        .depth_write_enabled = pass.depth_write_enabled,
        .unclipped_depth = pip.unclipped_depth,
        .clear_r = pass.clear_r,
        .clear_g = pass.clear_g,
        .clear_b = pass.clear_b,
        .clear_a = pass.clear_a,
    };
}

pub export fn doeNativeRenderPassDrawIndirect(pass_raw: ?*anyopaque, indirect_buffer_raw: ?*anyopaque, indirect_offset: u64) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (!reserve_render_draw(pass)) return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_draw_indirect(pass, indirect_buffer_raw, indirect_offset);
        return;
    }
    const pip = pass.pipeline orelse return;
    const indirect_buffer = cast(DoeBuffer, indirect_buffer_raw) orelse return;
    if (indirect_buffer.error_object) return;
    var cmd = base_render_cmd(pass, pip);
    cmd.indirect = true;
    cmd.indirect_buffer = indirect_buffer.mtl;
    cmd.indirect_offset = indirect_offset;
    pass.enc.cmds.append(alloc, .{ .render_pass = cmd }) catch
        std.debug.panic("doe_render_native: OOM recording indirect draw command", .{});
}

pub export fn doeNativeRenderPassDrawIndexedIndirect(pass_raw: ?*anyopaque, indirect_buffer_raw: ?*anyopaque, indirect_offset: u64) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (!reserve_render_draw(pass)) return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_draw_indexed_indirect(pass, indirect_buffer_raw, indirect_offset);
        return;
    }
    const pip = pass.pipeline orelse return;
    const indirect_buffer = cast(DoeBuffer, indirect_buffer_raw) orelse return;
    if (indirect_buffer.error_object) return;
    var cmd = base_render_cmd(pass, pip);
    cmd.indirect = true;
    cmd.indexed = true;
    cmd.indirect_buffer = indirect_buffer.mtl;
    cmd.indirect_offset = indirect_offset;
    cmd.index_buffer = if (pass.index_buffer) |buffer| buffer.mtl else null;
    cmd.index_offset = pass.index_offset;
    cmd.index_format = pass.index_format;
    cmd.index_buffer_size = pass.index_buffer_size;
    pass.enc.cmds.append(alloc, .{ .render_pass = cmd }) catch
        std.debug.panic("doe_render_native: OOM recording indexed indirect draw command", .{});
}

pub export fn doeNativeRenderPassEnd(raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeRenderPass, raw) orelse return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_render = @import("doe_vulkan_render_native.zig");
        vk_render.vulkan_render_pass_end(pass);
        return;
    }
}

pub export fn doeNativeRenderPassRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeRenderPass, raw)) |p| {
        label_store.remove(raw);
        alloc.destroy(p);
    }
}

// Ensure sharded modules' C ABI exports reach the final shared library.
comptime {
    _ = texture_sampler;
    _ = render_pipeline;
}

// Full render state: viewport, scissor, blend, MSAA, stencil, depth/stencil pipeline.
const render_state = @import("doe_render_state_native.zig");
comptime {
    _ = render_state;
}
