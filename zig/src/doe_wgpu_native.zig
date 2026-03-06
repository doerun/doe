// doe_wgpu_native.zig — Native wgpu* C ABI implementations backed by Metal.
// Implements the ~30 functions needed by doe_napi.c without Dawn.

const std = @import("std");
const types = @import("wgpu_types.zig");
const wgsl_msl = @import("doe_wgsl_msl.zig");

const alloc = std.heap.page_allocator;

// Metal bridge C functions (provided by metal_bridge.m).
extern fn metal_bridge_create_default_device() callconv(.c) ?*anyopaque;
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_device_new_command_queue(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_buffer_shared(device: ?*anyopaque, length: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_buffer_contents(buffer: ?*anyopaque) callconv(.c) ?[*]u8;
extern fn metal_bridge_device_new_library_msl(device: ?*anyopaque, src: [*]const u8, src_len: usize, err: ?[*]u8, err_cap: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_library_new_function(library: ?*anyopaque, name: [*:0]const u8) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_compute_pipeline(device: ?*anyopaque, function: ?*anyopaque, err: ?[*]u8, err_cap: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_encode_compute_dispatch(queue: ?*anyopaque, pipeline: ?*anyopaque, bufs: ?[*]?*anyopaque, buf_count: u32, x: u32, y: u32, z: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_encode_blit_copy(queue: ?*anyopaque, src: ?*anyopaque, dst: ?*anyopaque, length: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_command_buffer_commit(cmd: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_command_buffer_wait_completed(cmd: ?*anyopaque) callconv(.c) void;

// ============================================================
// Handle types — heap-allocated structs cast to opaque pointers
// ============================================================
const HANDLE_MAGIC: u32 = 0xD0E0_0001;
const MAX_CMD: usize = 256;
const MAX_BIND: usize = 16;
const ERR_CAP: usize = 512;

const DoeInstance = struct { magic: u32 = HANDLE_MAGIC };
const DoeAdapter = struct { magic: u32 = HANDLE_MAGIC, device: ?*anyopaque = null };

const DoeDevice = struct {
    magic: u32 = HANDLE_MAGIC,
    mtl_device: ?*anyopaque = null,
    mtl_queue: ?*anyopaque = null,
};

const DoeQueue = struct { magic: u32 = HANDLE_MAGIC, dev: *DoeDevice };

const DoeBuffer = struct {
    magic: u32 = HANDLE_MAGIC,
    mtl: ?*anyopaque = null,
    size: u64 = 0,
    usage: u64 = 0,
    mapped: bool = false,
};

const DoeShaderModule = struct {
    magic: u32 = HANDLE_MAGIC,
    mtl_library: ?*anyopaque = null,
};

const DoeComputePipeline = struct {
    magic: u32 = HANDLE_MAGIC,
    mtl_pso: ?*anyopaque = null,
};

const DoeBindGroupLayout = struct {
    magic: u32 = HANDLE_MAGIC,
    entry_count: u32 = 0,
};

const DoePipelineLayout = struct { magic: u32 = HANDLE_MAGIC };

const DoeBindGroup = struct {
    magic: u32 = HANDLE_MAGIC,
    buffers: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    offsets: [MAX_BIND]u64 = [_]u64{0} ** MAX_BIND,
    count: u32 = 0,
};

const CmdTag = enum { dispatch, copy_buf };
const RecordedCmd = union(CmdTag) {
    dispatch: struct { pso: ?*anyopaque, bufs: [MAX_BIND]?*anyopaque, buf_count: u32, x: u32, y: u32, z: u32 },
    copy_buf: struct { src: ?*anyopaque, src_off: u64, dst: ?*anyopaque, dst_off: u64, size: u64 },
};

const DoeCommandEncoder = struct {
    magic: u32 = HANDLE_MAGIC,
    dev: *DoeDevice,
    cmds: std.ArrayListUnmanaged(RecordedCmd) = .{},
};

const DoeComputePass = struct {
    magic: u32 = HANDLE_MAGIC,
    enc: *DoeCommandEncoder,
    pipeline: ?*DoeComputePipeline = null,
    bind_groups: [4]?*DoeBindGroup = [_]?*DoeBindGroup{null} ** 4,
};

const DoeCommandBuffer = struct {
    magic: u32 = HANDLE_MAGIC,
    dev: *DoeDevice,
    cmds: std.ArrayListUnmanaged(RecordedCmd) = .{},
};

fn make(comptime T: type) ?*T {
    return alloc.create(T) catch null;
}

fn cast(comptime T: type, p: ?*anyopaque) ?*T {
    const ptr = p orelse return null;
    return @ptrCast(@alignCast(ptr));
}

fn opaque(p: anytype) ?*anyopaque {
    return @ptrCast(p);
}

// ============================================================
// Instance / Adapter / Device
// ============================================================

pub export fn doeNativeCreateInstance(desc: ?*anyopaque) callconv(.c) ?*anyopaque {
    _ = desc;
    const inst = make(DoeInstance) orelse return null;
    inst.* = .{};
    return opaque(inst);
}

pub export fn doeNativeInstanceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeInstance, raw)) |inst| alloc.destroy(inst);
}

pub export fn doeNativeInstanceWaitAny(inst: ?*anyopaque, count: usize, infos: [*]types.WGPUFutureWaitInfo, timeout_ns: u64) callconv(.c) u32 {
    _ = inst;
    _ = timeout_ns;
    // All operations are synchronous — mark all futures as completed.
    for (infos[0..count]) |*info| info.completed = 1;
    return 0; // WGPUWaitStatus_Success
}

// Flat adapter request: callback(status, adapter, message, userdata1, userdata2)
pub export fn doeNativeRequestAdapterFlat(
    inst: ?*anyopaque,
    _: ?*anyopaque, // options
    _: u32, // callback mode
    callback: ?*const fn (u32, ?*anyopaque, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    _ = inst;
    const device = metal_bridge_create_default_device();
    if (device == null) {
        if (callback) |cb| cb(2, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 1 };
    }
    const adapter = make(DoeAdapter) orelse {
        metal_bridge_release(device);
        if (callback) |cb| cb(2, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 1 };
    };
    adapter.* = .{ .device = device };
    if (callback) |cb| cb(1, opaque(adapter), .{ .data = null, .length = 0 }, userdata1, userdata2);
    return .{ .id = 1 };
}

pub export fn doeNativeAdapterRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeAdapter, raw)) |a| alloc.destroy(a);
}

// Flat device request.
pub export fn doeNativeRequestDeviceFlat(
    adapter_raw: ?*anyopaque,
    _: ?*anyopaque,
    _: u32,
    callback: ?*const fn (u32, ?*anyopaque, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    const adapter = cast(DoeAdapter, adapter_raw) orelse {
        if (callback) |cb| cb(2, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 2 };
    };
    const queue = metal_bridge_device_new_command_queue(adapter.device);
    const dev = make(DoeDevice) orelse {
        if (callback) |cb| cb(2, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 2 };
    };
    dev.* = .{ .mtl_device = adapter.device, .mtl_queue = queue };
    if (callback) |cb| cb(1, opaque(dev), .{ .data = null, .length = 0 }, userdata1, userdata2);
    return .{ .id = 2 };
}

pub export fn doeNativeDeviceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeDevice, raw)) |d| {
        if (d.mtl_queue) |q| metal_bridge_release(q);
        alloc.destroy(d);
    }
}

pub export fn doeNativeDeviceGetQueue(raw: ?*anyopaque) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, raw) orelse return null;
    const q = make(DoeQueue) orelse return null;
    q.* = .{ .dev = dev };
    return opaque(q);
}

// ============================================================
// Buffer
// ============================================================

pub export fn doeNativeDeviceCreateBuffer(dev_raw: ?*anyopaque, desc: ?*const types.WGPUBufferDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const buf = make(DoeBuffer) orelse return null;
    buf.* = .{ .size = d.size, .usage = d.usage };
    // All buffers shared (Apple Silicon unified memory).
    buf.mtl = metal_bridge_device_new_buffer_shared(dev.mtl_device, @intCast(d.size));
    if (buf.mtl == null) { alloc.destroy(buf); return null; }
    if (d.mappedAtCreation != 0) buf.mapped = true;
    return opaque(buf);
}

pub export fn doeNativeBufferRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBuffer, raw)) |b| {
        if (b.mtl) |m| metal_bridge_release(m);
        alloc.destroy(b);
    }
}

pub export fn doeNativeBufferUnmap(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBuffer, raw)) |b| b.mapped = false;
}

pub export fn doeNativeBufferMapAsync(
    buf_raw: ?*anyopaque,
    mode: u64,
    offset: usize,
    size: usize,
    cb_info: types.WGPUBufferMapCallbackInfo,
) callconv(.c) types.WGPUFuture {
    _ = mode;
    _ = offset;
    _ = size;
    // Shared buffers are always CPU-accessible. Just mark mapped and call back.
    if (cast(DoeBuffer, buf_raw)) |b| b.mapped = true;
    if (cb_info.callback) |cb| cb(0, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
    return .{ .id = 3 };
}

pub export fn doeNativeBufferGetConstMappedRange(buf_raw: ?*anyopaque, offset: usize, size: usize) callconv(.c) ?*anyopaque {
    _ = size;
    const buf = cast(DoeBuffer, buf_raw) orelse return null;
    const contents = metal_bridge_buffer_contents(buf.mtl) orelse return null;
    return @ptrCast(contents + offset);
}

pub export fn doeNativeBufferGetMappedRange(buf_raw: ?*anyopaque, offset: usize, size: usize) callconv(.c) ?*anyopaque {
    return doeNativeBufferGetConstMappedRange(buf_raw, offset, size);
}

// ============================================================
// Shader Module (WGSL → MSL → MTLLibrary)
// ============================================================

pub export fn doeNativeDeviceCreateShaderModule(dev_raw: ?*anyopaque, desc: ?*const types.WGPUShaderModuleDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;

    // The WGSL source is in the chained struct (WGPUShaderSourceWGSL).
    const chain = d.nextInChain orelse return null;
    const wgsl_chain: *const types.WGPUShaderSourceWGSL = @ptrCast(@alignCast(chain));
    const wgsl_data = wgsl_chain.code.data orelse return null;
    const wgsl_len = if (wgsl_chain.code.length == types.WGPU_STRLEN)
        std.mem.len(@as([*:0]const u8, @ptrCast(wgsl_data)))
    else
        wgsl_chain.code.length;
    const wgsl = wgsl_data[0..wgsl_len];

    // Translate WGSL → MSL.
    var msl_buf: [wgsl_msl.MAX_OUTPUT]u8 = undefined;
    const msl_len = wgsl_msl.translate(wgsl, &msl_buf) catch return null;

    // Compile MSL → MTLLibrary.
    var err_buf: [ERR_CAP]u8 = undefined;
    const lib = metal_bridge_device_new_library_msl(
        dev.mtl_device,
        &msl_buf,
        msl_len,
        &err_buf,
        ERR_CAP,
    ) orelse return null;

    const sm = make(DoeShaderModule) orelse {
        metal_bridge_release(lib);
        return null;
    };
    sm.* = .{ .mtl_library = lib };
    return opaque(sm);
}

pub export fn doeNativeShaderModuleRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeShaderModule, raw)) |sm| {
        if (sm.mtl_library) |l| metal_bridge_release(l);
        alloc.destroy(sm);
    }
}

// ============================================================
// Compute Pipeline
// ============================================================

pub export fn doeNativeDeviceCreateComputePipeline(dev_raw: ?*anyopaque, desc: ?*const types.WGPUComputePipelineDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const sm = cast(DoeShaderModule, d.compute.module) orelse return null;

    // Get entry point name, default to "main_kernel" (our MSL output name).
    const entry: [*:0]const u8 = "main_kernel";

    const func = metal_bridge_library_new_function(sm.mtl_library, entry) orelse return null;
    defer metal_bridge_release(func);

    var err_buf: [ERR_CAP]u8 = undefined;
    const pso = metal_bridge_device_new_compute_pipeline(dev.mtl_device, func, &err_buf, ERR_CAP) orelse return null;

    const cp = make(DoeComputePipeline) orelse {
        metal_bridge_release(pso);
        return null;
    };
    cp.* = .{ .mtl_pso = pso };
    return opaque(cp);
}

pub export fn doeNativeComputePipelineRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeComputePipeline, raw)) |p| {
        if (p.mtl_pso) |pso| metal_bridge_release(pso);
        alloc.destroy(p);
    }
}

// ============================================================
// Bind Group Layout / Bind Group / Pipeline Layout
// ============================================================

pub export fn doeNativeDeviceCreateBindGroupLayout(dev_raw: ?*anyopaque, desc: ?*const types.WGPUBindGroupLayoutDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    const d = desc orelse return null;
    const bgl = make(DoeBindGroupLayout) orelse return null;
    bgl.* = .{ .entry_count = @intCast(d.entryCount) };
    return opaque(bgl);
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
            const doe_buf = cast(DoeBuffer, e.buffer) orelse continue;
            bg.buffers[e.binding] = doe_buf.mtl;
            bg.offsets[e.binding] = e.offset;
            if (e.binding + 1 > bg.count) bg.count = e.binding + 1;
        }
    }
    return opaque(bg);
}

pub export fn doeNativeBindGroupRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBindGroup, raw)) |g| alloc.destroy(g);
}

pub export fn doeNativeDeviceCreatePipelineLayout(dev_raw: ?*anyopaque, desc: ?*const types.WGPUPipelineLayoutDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    _ = desc;
    const pl = make(DoePipelineLayout) orelse return null;
    pl.* = .{};
    return opaque(pl);
}

pub export fn doeNativePipelineLayoutRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoePipelineLayout, raw)) |l| alloc.destroy(l);
}

// ============================================================
// Command Encoder / Compute Pass
// ============================================================

pub export fn doeNativeDeviceCreateCommandEncoder(dev_raw: ?*anyopaque, desc: ?*const types.WGPUCommandEncoderDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const enc = make(DoeCommandEncoder) orelse return null;
    enc.* = .{ .dev = dev };
    return opaque(enc);
}

pub export fn doeNativeCommandEncoderRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeCommandEncoder, raw)) |e| {
        e.cmds.deinit(alloc);
        alloc.destroy(e);
    }
}

pub export fn doeNativeCommandEncoderBeginComputePass(enc_raw: ?*anyopaque, desc: ?*const types.WGPUComputePassDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const pass = make(DoeComputePass) orelse return null;
    pass.* = .{ .enc = enc };
    return opaque(pass);
}

pub export fn doeNativeComputePassSetPipeline(pass_raw: ?*anyopaque, pip_raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    pass.pipeline = cast(DoeComputePipeline, pip_raw);
}

pub export fn doeNativeComputePassSetBindGroup(pass_raw: ?*anyopaque, index: u32, bg_raw: ?*anyopaque, dyn_count: usize, dyn_offsets: ?[*]const u32) callconv(.c) void {
    _ = dyn_count;
    _ = dyn_offsets;
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    if (index < 4) pass.bind_groups[index] = cast(DoeBindGroup, bg_raw);
}

pub export fn doeNativeComputePassDispatch(pass_raw: ?*anyopaque, x: u32, y: u32, z: u32) callconv(.c) void {
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    const pip = pass.pipeline orelse return;
    var cmd = RecordedCmd{ .dispatch = .{ .pso = pip.mtl_pso, .bufs = [_]?*anyopaque{null} ** MAX_BIND, .buf_count = 0, .x = x, .y = y, .z = z } };
    // Collect buffers from bind group 0.
    if (pass.bind_groups[0]) |bg| {
        for (0..bg.count) |i| cmd.dispatch.bufs[i] = bg.buffers[i];
        cmd.dispatch.buf_count = bg.count;
    }
    pass.enc.cmds.append(alloc, cmd) catch {};
}

pub export fn doeNativeComputePassEnd(raw: ?*anyopaque) callconv(.c) void {
    _ = raw; // Nothing to do — commands already recorded.
}

pub export fn doeNativeComputePassRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeComputePass, raw)) |p| alloc.destroy(p);
}

pub export fn doeNativeCopyBufferToBuffer(enc_raw: ?*anyopaque, src_raw: ?*anyopaque, src_off: u64, dst_raw: ?*anyopaque, dst_off: u64, size: u64) callconv(.c) void {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return;
    const src = cast(DoeBuffer, src_raw) orelse return;
    const dst = cast(DoeBuffer, dst_raw) orelse return;
    enc.cmds.append(alloc, .{ .copy_buf = .{ .src = src.mtl, .src_off = src_off, .dst = dst.mtl, .dst_off = dst_off, .size = size } }) catch {};
}

pub export fn doeNativeCommandEncoderFinish(enc_raw: ?*anyopaque, desc: ?*const types.WGPUCommandBufferDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const cb = make(DoeCommandBuffer) orelse return null;
    cb.* = .{ .dev = enc.dev, .cmds = enc.cmds };
    enc.cmds = .{}; // Transfer ownership.
    return opaque(cb);
}

pub export fn doeNativeCommandBufferRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeCommandBuffer, raw)) |cb| {
        cb.cmds.deinit(alloc);
        alloc.destroy(cb);
    }
}

// ============================================================
// Queue
// ============================================================

pub export fn doeNativeQueueSubmit(q_raw: ?*anyopaque, count: usize, cmd_bufs: [*]const ?*anyopaque) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    const queue = q.dev.mtl_queue;

    for (cmd_bufs[0..count]) |raw| {
        const cb = cast(DoeCommandBuffer, raw) orelse continue;
        for (cb.cmds.items) |cmd| {
            switch (cmd) {
                .dispatch => |d| {
                    const mtl_cmd = metal_bridge_encode_compute_dispatch(
                        queue, d.pso, &d.bufs, d.buf_count, d.x, d.y, d.z,
                    );
                    if (mtl_cmd) |c| {
                        metal_bridge_command_buffer_commit(c);
                        metal_bridge_command_buffer_wait_completed(c);
                        metal_bridge_release(c);
                    }
                },
                .copy_buf => |c| {
                    // For shared buffers, memcpy is sufficient and faster.
                    const src_ptr = metal_bridge_buffer_contents(c.src) orelse continue;
                    const dst_ptr = metal_bridge_buffer_contents(c.dst) orelse continue;
                    const src_slice = (src_ptr + @as(usize, @intCast(c.src_off)))[0..@intCast(c.size)];
                    const dst_slice = (dst_ptr + @as(usize, @intCast(c.dst_off)))[0..@intCast(c.size)];
                    @memcpy(dst_slice, src_slice);
                },
            }
        }
    }
}

pub export fn doeNativeQueueWriteBuffer(q_raw: ?*anyopaque, buf_raw: ?*anyopaque, offset: u64, data: [*]const u8, size: usize) callconv(.c) void {
    _ = q_raw;
    const buf = cast(DoeBuffer, buf_raw) orelse return;
    const contents = metal_bridge_buffer_contents(buf.mtl) orelse return;
    const dst = (contents + @as(usize, @intCast(offset)))[0..size];
    @memcpy(dst, data[0..size]);
}

pub export fn doeNativeQueueRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeQueue, raw)) |q| alloc.destroy(q);
}

// ============================================================
// Instance process events (no-op for sync).
pub export fn doeNativeInstanceProcessEvents(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}
