// doe_bind_group_native.zig — Bind group, bind group layout, and pipeline layout
// C ABI exports for the Doe native Metal backend. Sharded from doe_wgpu_native.zig.

const native = @import("doe_wgpu_native.zig");
const types = @import("core/abi/wgpu_types.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const MAX_BIND = native.MAX_BIND;

const DoeBuffer = native.DoeBuffer;
const DoeSampler = native.DoeSampler;
const DoeBindGroupLayout = native.DoeBindGroupLayout;
const DoeBindGroup = native.DoeBindGroup;
const DoePipelineLayout = native.DoePipelineLayout;
const DoeTextureView = native.DoeTextureView;

// ============================================================
// Bind Group Layout / Bind Group / Pipeline Layout
// ============================================================

pub export fn doeNativeDeviceCreateBindGroupLayout(dev_raw: ?*anyopaque, desc: ?*const types.WGPUBindGroupLayoutDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    const d = desc orelse return null;
    const bgl = make(DoeBindGroupLayout) orelse return null;
    bgl.* = .{ .entry_count = @intCast(d.entryCount) };
    return toOpaque(bgl);
}

pub export fn doeNativeBindGroupLayoutRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBindGroupLayout, raw)) |l| alloc.destroy(l);
}

pub export fn doeNativeDeviceCreateBindGroup(dev_raw: ?*anyopaque, desc: ?*const types.WGPUBindGroupDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    const d = desc orelse return null;
    const bg = make(DoeBindGroup) orelse return null;
    bg.* = .{};
    for (d.entries[0..d.entryCount]) |e| {
        if (e.binding < MAX_BIND) {
            if (cast(DoeBuffer, e.buffer)) |doe_buf| {
                bg.buffers[e.binding] = doe_buf.mtl;
                bg.offsets[e.binding] = e.offset;
            } else if (cast(DoeTextureView, e.textureView)) |view| {
                bg.textures[e.binding] = view.tex.mtl;
            } else if (cast(DoeSampler, e.sampler)) |sampler| {
                bg.samplers[e.binding] = sampler.mtl;
            } else continue;
            if (e.binding + 1 > bg.count) bg.count = e.binding + 1;
        }
    }
    return toOpaque(bg);
}

pub export fn doeNativeBindGroupRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBindGroup, raw)) |g| alloc.destroy(g);
}

pub export fn doeNativeDeviceCreatePipelineLayout(dev_raw: ?*anyopaque, desc: ?*const types.WGPUPipelineLayoutDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    _ = desc;
    const pl = make(DoePipelineLayout) orelse return null;
    pl.* = .{};
    return toOpaque(pl);
}

pub export fn doeNativePipelineLayoutRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoePipelineLayout, raw)) |l| alloc.destroy(l);
}
