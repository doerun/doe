// doe_render_native.zig — Texture, Sampler, Render Pipeline, and Render Pass
// C ABI exports for the Doe native Metal backend. Sharded from doe_wgpu_native.zig.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const render_types = @import("full/render/wgpu_render_types.zig");
const native = @import("doe_wgpu_native.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");
const MetalVertexAttributeDesc = bridge.MetalVertexAttributeDesc;
const MetalVertexBufferLayout = bridge.MetalVertexBufferLayout;
const metal_bridge_device_new_depth_stencil_state = bridge.metal_bridge_device_new_depth_stencil_state;
const metal_bridge_device_new_render_pipeline_full = bridge.metal_bridge_device_new_render_pipeline_full;
const metal_bridge_device_new_sampler = bridge.metal_bridge_device_new_sampler;
const metal_bridge_device_new_texture = bridge.metal_bridge_device_new_texture;
const metal_bridge_library_new_function = bridge.metal_bridge_library_new_function;
const metal_bridge_release = bridge.metal_bridge_release;

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const ERR_CAP = native.ERR_CAP;

const DoeDevice = native.DoeDevice;
const DoeBindGroup = native.DoeBindGroup;
const DoeBuffer = native.DoeBuffer;
const DoeShaderModule = native.DoeShaderModule;
const DoeTexture = native.DoeTexture;
const DoeTextureView = native.DoeTextureView;
const DoeSampler = native.DoeSampler;
const DoeRenderPipeline = native.DoeRenderPipeline;
const DoeRenderPass = native.DoeRenderPass;
const DoeCommandEncoder = native.DoeCommandEncoder;
const RenderPassCmd = std.meta.TagPayloadByName(native.RecordedCmd, "render_pass");

// ============================================================
// Texture
// ============================================================

pub export fn doeNativeDeviceCreateTexture(dev_raw: ?*anyopaque, desc: ?*const types.WGPUTextureDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const mtl = metal_bridge_device_new_texture(dev.mtl_device, d.size.width, d.size.height, d.mipLevelCount, d.format, @intCast(d.usage)) orelse return null;
    const tex = make(DoeTexture) orelse {
        metal_bridge_release(mtl);
        return null;
    };
    tex.* = .{ .mtl = mtl, .format = d.format, .width = d.size.width, .height = d.size.height };
    return toOpaque(tex);
}

pub export fn doeNativeTextureCreateView(tex_raw: ?*anyopaque, desc: ?*const types.WGPUTextureViewDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const tex = cast(DoeTexture, tex_raw) orelse return null;
    const tv = make(DoeTextureView) orelse return null;
    tv.* = .{ .tex = tex };
    return toOpaque(tv);
}

pub export fn doeNativeTextureRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeTexture, raw)) |t| {
        if (t.mtl) |m| metal_bridge_release(m);
        alloc.destroy(t);
    }
}

pub export fn doeNativeTextureViewRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeTextureView, raw)) |tv| alloc.destroy(tv);
}

// ============================================================
// Sampler
// ============================================================

pub export fn doeNativeDeviceCreateSampler(dev_raw: ?*anyopaque, desc: ?*const types.WGPUSamplerDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const mtl = metal_bridge_device_new_sampler(dev.mtl_device, d.minFilter, d.magFilter, d.mipmapFilter, d.addressModeU, d.addressModeV, d.addressModeW, d.lodMinClamp, d.lodMaxClamp, d.maxAnisotropy) orelse return null;
    const s = make(DoeSampler) orelse {
        metal_bridge_release(mtl);
        return null;
    };
    s.* = .{ .mtl = mtl };
    return toOpaque(s);
}

pub export fn doeNativeSamplerRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeSampler, raw)) |s| {
        if (s.mtl) |m| metal_bridge_release(m);
        alloc.destroy(s);
    }
}

// ============================================================
// Render Pipeline
// ============================================================
fn owned_c_string(allocator: std.mem.Allocator, view: types.WGPUStringView, fallback: []const u8) ![:0]u8 {
    if (view.data) |ptr| {
        const slice = ptr[0..view.length];
        return try allocator.dupeZ(u8, slice);
    }
    return try allocator.dupeZ(u8, fallback);
}

fn vertex_buffer_layouts_ptr(raw: ?*const anyopaque) ?[*]const render_types.RenderVertexBufferLayout {
    const ptr = raw orelse return null;
    return @as([*]const render_types.RenderVertexBufferLayout, @ptrCast(@alignCast(ptr)));
}

pub export fn doeNativeDeviceCreateRenderPipeline(dev_raw: ?*anyopaque, desc: ?*anyopaque) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const raw_desc = desc orelse return null;
    const pipeline_desc = @as(*const render_types.RenderPipelineDescriptor, @ptrCast(@alignCast(raw_desc)));
    const vertex_shader = cast(DoeShaderModule, pipeline_desc.vertex.module) orelse return null;
    const fragment_state = pipeline_desc.fragment orelse return null;
    const fragment_shader = cast(DoeShaderModule, fragment_state.module) orelse return null;
    if (fragment_state.targetCount == 0) return null;

    const vertex_entry = owned_c_string(alloc, pipeline_desc.vertex.entryPoint, "main") catch return null;
    defer alloc.free(vertex_entry);
    const fragment_entry = owned_c_string(alloc, fragment_state.entryPoint, "main") catch return null;
    defer alloc.free(fragment_entry);

    const vertex_func = metal_bridge_library_new_function(vertex_shader.mtl_library, vertex_entry.ptr) orelse return null;
    defer metal_bridge_release(vertex_func);
    const fragment_func = metal_bridge_library_new_function(fragment_shader.mtl_library, fragment_entry.ptr) orelse return null;
    defer metal_bridge_release(fragment_func);

    var layout_buf: [native.MAX_VERTEX_BUFFERS]MetalVertexBufferLayout = undefined;
    var attr_buf: [32]MetalVertexAttributeDesc = undefined;
    var layout_count: u32 = 0;
    var attr_count: u32 = 0;
    if (pipeline_desc.vertex.bufferCount > layout_buf.len) return null;
    if (vertex_buffer_layouts_ptr(pipeline_desc.vertex.buffers)) |layouts| {
        for (layouts[0..pipeline_desc.vertex.bufferCount], 0..) |layout, layout_index| {
            layout_buf[layout_index] = .{
                .array_stride = layout.arrayStride,
                .step_mode = layout.stepMode,
                .buffer_index = native.VERTEX_BUFFER_SLOT_BASE + @as(u32, @intCast(layout_index)),
            };
            layout_count += 1;
            if (layout.attributeCount > 0) {
                const attrs = layout.attributes orelse return null;
                if (attr_count + layout.attributeCount > attr_buf.len) return null;
                for (attrs[0..layout.attributeCount]) |attr| {
                    attr_buf[attr_count] = .{
                        .format = attr.format,
                        .offset = attr.offset,
                        .shader_location = attr.shaderLocation,
                        .buffer_index = layout_buf[layout_index].buffer_index,
                    };
                    attr_count += 1;
                }
            }
        }
    }

    var err_buf: [ERR_CAP]u8 = undefined;
    const target_format = fragment_state.targets[0].format;
    const depth_state = if (pipeline_desc.depthStencil) |depth_stencil|
        metal_bridge_device_new_depth_stencil_state(
            dev.mtl_device,
            depth_stencil.depthCompare,
            if (depth_stencil.depthWriteEnabled != 0) 1 else 0,
            &err_buf,
            ERR_CAP,
        )
    else
        null;
    const pso = metal_bridge_device_new_render_pipeline_full(
        dev.mtl_device,
        vertex_func,
        fragment_func,
        target_format,
        if (pipeline_desc.depthStencil) |depth_stencil| depth_stencil.format else 0,
        if (layout_count > 0) &layout_buf else null,
        layout_count,
        if (attr_count > 0) &attr_buf else null,
        attr_count,
        &err_buf,
        ERR_CAP,
    ) orelse return null;
    const rp = make(DoeRenderPipeline) orelse {
        metal_bridge_release(pso);
        if (depth_state) |state| metal_bridge_release(state);
        return null;
    };
    rp.* = .{
        .mtl_pso = pso,
        .depth_state = depth_state,
        .topology = pipeline_desc.primitive.topology,
        .front_face = pipeline_desc.primitive.frontFace,
        .cull_mode = pipeline_desc.primitive.cullMode,
        .depth_compare = if (pipeline_desc.depthStencil) |depth_stencil| depth_stencil.depthCompare else 0,
        .depth_write_enabled = if (pipeline_desc.depthStencil) |depth_stencil| depth_stencil.depthWriteEnabled != 0 else false,
    };
    return toOpaque(rp);
}

pub export fn doeNativeRenderPipelineRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeRenderPipeline, raw)) |p| {
        if (p.mtl_pso) |pso| metal_bridge_release(pso);
        if (p.depth_state) |state| metal_bridge_release(state);
        alloc.destroy(p);
    }
}

// ============================================================
// Render Pass
// ============================================================

pub export fn doeNativeCommandEncoderBeginRenderPass(enc_raw: ?*anyopaque, desc: ?*const types.WGPURenderPassDescriptor) callconv(.c) ?*anyopaque {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const pass = make(DoeRenderPass) orelse return null;
    pass.* = .{ .enc = enc };
    if (desc) |d| {
        if (d.colorAttachmentCount > 0) {
            if (d.colorAttachments) |attachments| {
                const tv = cast(DoeTextureView, attachments[0].view);
                if (tv) |v| pass.target = v.tex.mtl;
            }
        }
        if (d.depthStencilAttachment) |depth_attachment| {
            const depth_view = cast(DoeTextureView, depth_attachment.view);
            if (depth_view) |view| pass.depth_target = view.tex.mtl;
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

pub export fn doeNativeRenderPassDraw(pass_raw: ?*anyopaque, vertex_count: u32, instance_count: u32, first_vertex: u32, first_instance: u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    const pip = pass.pipeline orelse return;
    var cmd = native.RecordedCmd{ .render_pass = .{
        .pso = pip.mtl_pso,
        .depth_state = pip.depth_state,
        .target = pass.target,
        .depth_target = pass.depth_target,
        .topology = pip.topology,
        .front_face = pip.front_face,
        .cull_mode = pip.cull_mode,
        .draw_count = 1,
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .first_vertex = first_vertex,
        .first_instance = first_instance,
        .depth_compare = pass.depth_compare,
        .depth_write_enabled = pass.depth_write_enabled,
    } };
    flatten_render_pass_state(pass, &cmd.render_pass);
    pass.enc.cmds.append(alloc, cmd) catch std.debug.panic("doe_render_native: OOM recording render command", .{});
}

fn flatten_render_pass_state(pass: *DoeRenderPass, cmd: *RenderPassCmd) void {
    for (pass.bind_groups) |maybe_bg| {
        const bg = maybe_bg orelse continue;
        for (0..bg.count) |slot| {
            cmd.bind_buffers[slot] = bg.buffers[slot];
            cmd.bind_buffer_offsets[slot] = bg.offsets[slot];
            cmd.bind_textures[slot] = bg.textures[slot];
            cmd.bind_samplers[slot] = bg.samplers[slot];
        }
    }
    for (pass.vertex_buffers, pass.vertex_buffer_offsets, 0..) |maybe_buf, offset, slot| {
        if (maybe_buf) |buffer| {
            cmd.vertex_buffers[slot] = buffer.mtl;
            cmd.vertex_buffer_offsets[slot] = offset;
        }
    }
    if (pass.index_buffer) |buffer| {
        cmd.index_buffer = buffer.mtl;
        if (!cmd.indexed) cmd.index_offset = pass.index_offset;
        cmd.index_format = pass.index_format;
    }
}

fn index_stride(format: u32) u64 {
    return switch (format) {
        0x00000001 => 2,
        0x00000002 => 4,
        else => 0,
    };
}

pub export fn doeNativeRenderPassSetBindGroup(pass_raw: ?*anyopaque, index: u32, bg_raw: ?*anyopaque, dyn_count: usize, dyn_offsets: ?[*]const u32) callconv(.c) void {
    _ = dyn_count;
    _ = dyn_offsets;
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (index < pass.bind_groups.len) pass.bind_groups[index] = cast(DoeBindGroup, bg_raw);
}

pub export fn doeNativeRenderPassSetVertexBuffer(pass_raw: ?*anyopaque, slot: u32, buf_raw: ?*anyopaque, offset: u64, size: u64) callconv(.c) void {
    _ = size;
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    if (slot >= pass.vertex_buffers.len) return;
    pass.vertex_buffers[slot] = cast(DoeBuffer, buf_raw);
    pass.vertex_buffer_offsets[slot] = offset;
}

pub export fn doeNativeRenderPassSetIndexBuffer(pass_raw: ?*anyopaque, buf_raw: ?*anyopaque, format: u32, offset: u64, size: u64) callconv(.c) void {
    _ = size;
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.index_buffer = cast(DoeBuffer, buf_raw);
    pass.index_format = format;
    pass.index_offset = offset;
}

pub export fn doeNativeRenderPassDrawIndexed(pass_raw: ?*anyopaque, index_count: u32, instance_count: u32, first_index: u32, base_vertex: i32, first_instance: u32) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    const pip = pass.pipeline orelse return;
    const first_index_offset = index_stride(pass.index_format) * @as(u64, first_index);
    var cmd = native.RecordedCmd{ .render_pass = .{
        .pso = pip.mtl_pso,
        .depth_state = pip.depth_state,
        .target = pass.target,
        .depth_target = pass.depth_target,
        .topology = pip.topology,
        .front_face = pip.front_face,
        .cull_mode = pip.cull_mode,
        .draw_count = 1,
        .vertex_count = 0,
        .instance_count = instance_count,
        .first_vertex = 0,
        .first_instance = first_instance,
        .indexed = true,
        .index_count = index_count,
        .index_offset = pass.index_offset + first_index_offset,
        .base_vertex = base_vertex,
        .depth_compare = pass.depth_compare,
        .depth_write_enabled = pass.depth_write_enabled,
    } };
    flatten_render_pass_state(pass, &cmd.render_pass);
    pass.enc.cmds.append(alloc, cmd) catch std.debug.panic("doe_render_native: OOM recording indexed render command", .{});
}

pub export fn doeNativeRenderPassEnd(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}

pub export fn doeNativeRenderPassRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeRenderPass, raw)) |p| alloc.destroy(p);
}
