// doe_bind_group_native.zig — Bind group, bind group layout, and pipeline layout
// C ABI exports for the Doe native Metal/Vulkan backend. Sharded from doe_wgpu_native.zig.

const native = @import("doe_wgpu_native.zig");
const types = @import("core/abi/wgpu_types.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const MAX_BIND = native.MAX_BIND;
const label_store = native.label_store;

const DoeDevice = native.DoeDevice;
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
    const result = toOpaque(bgl);
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeBindGroupLayoutRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBindGroupLayout, raw)) |l| {
        label_store.remove(raw);
        alloc.destroy(l);
    }
}

pub export fn doeNativeDeviceCreateBindGroup(dev_raw: ?*anyopaque, desc: ?*const types.WGPUBindGroupDescriptor) callconv(.c) ?*anyopaque {
    const d = desc orelse return null;
    const bg = make(DoeBindGroup) orelse return null;
    bg.* = .{};

    // For Vulkan devices, store the DoeBuffer* opaque pointer in buffers[] instead
    // of the MTL handle, so the compute dispatch can look up the vk_id at submit time.
    const is_vulkan = if (cast(DoeDevice, dev_raw)) |dev| dev.backend == .vulkan else false;

    for (d.entries[0..d.entryCount]) |e| {
        if (e.binding < MAX_BIND) {
            if (cast(DoeBuffer, e.buffer)) |doe_buf| {
                if (is_vulkan) {
                    // Store the DoeBuffer handle — dispatch reads vk_id from it.
                    bg.buffers[e.binding] = toOpaque(doe_buf);
                } else {
                    bg.buffers[e.binding] = doe_buf.mtl;
                }
                bg.offsets[e.binding] = e.offset;
                bg.buffer_sizes[e.binding] = doe_buf.size;
            } else if (cast(DoeTextureView, e.textureView)) |view| {
                bg.textures[e.binding] = view.tex.mtl;
            } else if (cast(DoeSampler, e.sampler)) |sampler| {
                bg.samplers[e.binding] = sampler.mtl;
            } else continue;
            if (e.binding + 1 > bg.count) bg.count = e.binding + 1;
        }
    }
    const bg_result = toOpaque(bg);
    label_store.set(bg_result, d.label.data, d.label.length);
    return bg_result;
}

pub export fn doeNativeBindGroupRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBindGroup, raw)) |g| {
        label_store.remove(raw);
        alloc.destroy(g);
    }
}

pub export fn doeNativeDeviceCreatePipelineLayout(dev_raw: ?*anyopaque, desc: ?*const types.WGPUPipelineLayoutDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    const pl = make(DoePipelineLayout) orelse return null;
    pl.* = .{};
    const pl_result = toOpaque(pl);
    if (desc) |pd| {
        pl.immediate_size = pd.immediateSize;
        label_store.set(pl_result, pd.label.data, pd.label.length);
    }
    return pl_result;
}

pub export fn doeNativePipelineLayoutRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoePipelineLayout, raw)) |l| {
        label_store.remove(raw);
        alloc.destroy(l);
    }
}
