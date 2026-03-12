// doe_render_native.zig — Texture, Sampler, Render Pipeline, and Render Pass
// C ABI exports for the Doe native Metal backend. Sharded from doe_wgpu_native.zig.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");
const metal_bridge_device_new_render_pipeline = bridge.metal_bridge_device_new_render_pipeline;
const metal_bridge_device_new_sampler = bridge.metal_bridge_device_new_sampler;
const metal_bridge_device_new_texture = bridge.metal_bridge_device_new_texture;
const metal_bridge_release = bridge.metal_bridge_release;

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const ERR_CAP = native.ERR_CAP;

const DoeDevice = native.DoeDevice;
const DoeTexture = native.DoeTexture;
const DoeTextureView = native.DoeTextureView;
const DoeSampler = native.DoeSampler;
const DoeRenderPipeline = native.DoeRenderPipeline;
const DoeRenderPass = native.DoeRenderPass;
const DoeCommandEncoder = native.DoeCommandEncoder;

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
//
// Render pipeline descriptor parsing is not yet implemented.
// The WGSL compiler currently covers compute shaders only; vertex/fragment
// shader translation is planned. Until then, createRenderPipeline creates
// a basic noop Metal render pipeline (RGBA8Unorm, no vertex/fragment shaders)
// suitable for benchmark render passes. Callers passing a real descriptor
// get a diagnostic so the limitation is visible.

pub export fn doeNativeDeviceCreateRenderPipeline(dev_raw: ?*anyopaque, desc: ?*anyopaque) callconv(.c) ?*anyopaque {
    if (desc != null) {
        std.debug.print("doe: createRenderPipeline: descriptor parsing not yet implemented; creating basic noop pipeline\n", .{});
    }
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    var err_buf: [ERR_CAP]u8 = undefined;
    const PIXEL_FORMAT_RGBA8_UNORM: u32 = 0x00000016;
    const pso = metal_bridge_device_new_render_pipeline(dev.mtl_device, PIXEL_FORMAT_RGBA8_UNORM, 0, &err_buf, ERR_CAP) orelse return null;
    const rp = make(DoeRenderPipeline) orelse {
        metal_bridge_release(pso);
        return null;
    };
    rp.* = .{ .mtl_pso = pso };
    return toOpaque(rp);
}

pub export fn doeNativeRenderPipelineRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeRenderPipeline, raw)) |p| {
        if (p.mtl_pso) |pso| metal_bridge_release(pso);
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
    }
    return toOpaque(pass);
}

pub export fn doeNativeRenderPassSetPipeline(pass_raw: ?*anyopaque, pip_raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    pass.pipeline = cast(DoeRenderPipeline, pip_raw);
}

pub export fn doeNativeRenderPassDraw(pass_raw: ?*anyopaque, vertex_count: u32, instance_count: u32, first_vertex: u32, first_instance: u32) callconv(.c) void {
    _ = first_vertex;
    _ = first_instance;
    const pass = cast(DoeRenderPass, pass_raw) orelse return;
    const pip = pass.pipeline orelse return;
    pass.enc.cmds.append(alloc, .{ .render_pass = .{
        .pso = pip.mtl_pso,
        .target = pass.target,
        .draw_count = 1,
        .vertex_count = vertex_count,
        .instance_count = instance_count,
    } }) catch std.debug.panic("doe_render_native: OOM recording render command", .{});
}

pub export fn doeNativeRenderPassEnd(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}

pub export fn doeNativeRenderPassRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeRenderPass, raw)) |p| alloc.destroy(p);
}
