// doe_wgpu_native.zig — Native wgpu* C ABI implementations backed by Metal.
// Implements the ~40 functions needed by doe_napi.c without Dawn.
//
// Limitations (v0.1):
// - No reference counting — release destroys immediately.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const wgsl_compiler = @import("doe_wgsl/mod.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_cmd_buf_encode_blit_copy = bridge.metal_bridge_cmd_buf_encode_blit_copy;
const metal_bridge_cmd_buf_encode_compute_dispatch = bridge.metal_bridge_cmd_buf_encode_compute_dispatch;
const metal_bridge_cmd_buf_encode_compute_dispatch_indirect = bridge.metal_bridge_cmd_buf_encode_compute_dispatch_indirect;
const metal_bridge_cmd_buf_render_encoder = bridge.metal_bridge_cmd_buf_render_encoder;
const metal_bridge_command_buffer_commit = bridge.metal_bridge_command_buffer_commit;
const metal_bridge_command_buffer_encode_signal_event = bridge.metal_bridge_command_buffer_encode_signal_event;
const metal_bridge_create_command_buffer = bridge.metal_bridge_create_command_buffer;
const metal_bridge_create_default_device = bridge.metal_bridge_create_default_device;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_device_new_command_queue = bridge.metal_bridge_device_new_command_queue;
const metal_bridge_device_new_shared_event = bridge.metal_bridge_device_new_shared_event;
const metal_bridge_release = bridge.metal_bridge_release;
const metal_bridge_render_encoder_draw = bridge.metal_bridge_render_encoder_draw;
const metal_bridge_render_encoder_end = bridge.metal_bridge_render_encoder_end;
const metal_bridge_shared_event_wait = bridge.metal_bridge_shared_event_wait;

// GPA for handle allocations — page_allocator wastes 16KB per 24-byte struct.
var gpa = std.heap.GeneralPurposeAllocator(.{}){};
pub const alloc = gpa.allocator();

// ============================================================
// Handle types — heap-allocated structs cast to opaque pointers.
// Each type has a distinct magic for type-checked downcasts.
// ============================================================
const MAGIC_INSTANCE: u32 = 0xD0E1_0001;
const MAGIC_ADAPTER: u32 = 0xD0E1_0002;
const MAGIC_DEVICE: u32 = 0xD0E1_0003;
const MAGIC_QUEUE: u32 = 0xD0E1_0004;
const MAGIC_BUFFER: u32 = 0xD0E1_0005;
const MAGIC_SHADER: u32 = 0xD0E1_0006;
const MAGIC_COMPUTE_PIPE: u32 = 0xD0E1_0007;
const MAGIC_BGL: u32 = 0xD0E1_0008;
const MAGIC_PIPE_LAYOUT: u32 = 0xD0E1_0009;
const MAGIC_BIND_GROUP: u32 = 0xD0E1_000A;
const MAGIC_CMD_ENCODER: u32 = 0xD0E1_000B;
const MAGIC_COMPUTE_PASS: u32 = 0xD0E1_000C;
const MAGIC_CMD_BUFFER: u32 = 0xD0E1_000D;
const MAGIC_TEXTURE: u32 = 0xD0E1_000E;
const MAGIC_TEXTURE_VIEW: u32 = 0xD0E1_000F;
const MAGIC_SAMPLER: u32 = 0xD0E1_0010;
const MAGIC_RENDER_PIPE: u32 = 0xD0E1_0011;
const MAGIC_RENDER_PASS: u32 = 0xD0E1_0012;

pub const MAX_BIND: usize = 16;
pub const ERR_CAP: usize = 512;

// WebGPU status constants — must match doe_napi.c definitions.
const WGPU_WAIT_STATUS_SUCCESS: u32 = 1;
const WGPU_REQUEST_STATUS_SUCCESS: u32 = 1;
const WGPU_REQUEST_STATUS_ERROR: u32 = 4;
const WGPU_MAP_ASYNC_STATUS_SUCCESS: u32 = 1;

const DoeInstance = struct {
    const TYPE_MAGIC = MAGIC_INSTANCE;
    magic: u32 = TYPE_MAGIC,
};

const DoeAdapter = struct {
    const TYPE_MAGIC = MAGIC_ADAPTER;
    magic: u32 = TYPE_MAGIC,
    mtl_device: ?*anyopaque = null,
};

pub const DoeDevice = struct {
    const TYPE_MAGIC = MAGIC_DEVICE;
    magic: u32 = TYPE_MAGIC,
    mtl_device: ?*anyopaque = null,
    mtl_queue: ?*anyopaque = null,
    queue: ?*DoeQueue = null, // cached; getQueue returns this
};

pub const DeferredCopy = struct {
    src: [*]const u8,
    dst: [*]u8,
    size: usize,
};
const MAX_DEFERRED_COPIES: u32 = 16;

pub const DoeQueue = struct {
    pub const TYPE_MAGIC = MAGIC_QUEUE;
    magic: u32 = TYPE_MAGIC,
    dev: *DoeDevice,
    pending_cmd: ?*anyopaque = null,
    mtl_event: ?*anyopaque = null, // MTLSharedEvent for user-space GPU fence
    event_counter: u64 = 0,
    deferred_copies: [MAX_DEFERRED_COPIES]DeferredCopy = undefined,
    deferred_copy_count: u32 = 0,
};

pub const DoeBuffer = struct {
    pub const TYPE_MAGIC = MAGIC_BUFFER;
    magic: u32 = TYPE_MAGIC,
    mtl: ?*anyopaque = null,
    size: u64 = 0,
    usage: u64 = 0,
    mapped: bool = false,
};

// Extract @workgroup_size(x[,y[,z]]) from WGSL source via string search.
pub fn extractWorkgroupSize(wgsl: []const u8) struct { x: u32, y: u32, z: u32 } {
    const needle = "@workgroup_size(";
    const idx = std.mem.indexOf(u8, wgsl, needle) orelse return .{ .x = 0, .y = 0, .z = 0 };
    const start = idx + needle.len;
    const end = std.mem.indexOfPos(u8, wgsl, start, ")") orelse return .{ .x = 0, .y = 0, .z = 0 };
    const args = wgsl[start..end];
    var vals = [3]u32{ 0, 0, 0 };
    var vi: usize = 0;
    for (args) |c| {
        if (c >= '0' and c <= '9') {
            vals[vi] = vals[vi] * 10 + @as(u32, c - '0');
        } else if (c == ',' and vi < 2) {
            vi += 1;
        }
    }
    return .{
        .x = if (vals[0] > 0) vals[0] else 1,
        .y = if (vals[1] > 0) vals[1] else 1,
        .z = if (vals[2] > 0) vals[2] else 1,
    };
}

// Binding metadata extracted from WGSL source during shader compilation.
// Stored on shader module and transferred to pipeline for getBindGroupLayout.
pub const BindingInfo = struct {
    group: u32,
    binding: u32,
    kind: u32 = @intFromEnum(wgsl_compiler.BindingKind.buffer),
    addr_space: u32 = 0,
    access: u32 = 0,
};

pub const MAX_SHADER_BINDINGS: usize = wgsl_compiler.MAX_BINDINGS;

pub const DoeShaderModule = struct {
    const TYPE_MAGIC = MAGIC_SHADER;
    magic: u32 = TYPE_MAGIC,
    mtl_library: ?*anyopaque = null,
    bindings: [MAX_SHADER_BINDINGS]BindingInfo = undefined,
    binding_count: u32 = 0,
    wg_x: u32 = 0, // @workgroup_size (0 = unknown)
    wg_y: u32 = 0,
    wg_z: u32 = 0,
};

pub const DoeComputePipeline = struct {
    pub const TYPE_MAGIC = MAGIC_COMPUTE_PIPE;
    magic: u32 = TYPE_MAGIC,
    mtl_pso: ?*anyopaque = null,
    bindings: [MAX_SHADER_BINDINGS]BindingInfo = undefined,
    binding_count: u32 = 0,
    wg_x: u32 = 0,
    wg_y: u32 = 0,
    wg_z: u32 = 0,
};

pub const DoeBindGroupLayout = struct {
    const TYPE_MAGIC = MAGIC_BGL;
    magic: u32 = TYPE_MAGIC,
    entry_count: u32 = 0,
};

pub const DoePipelineLayout = struct {
    const TYPE_MAGIC = MAGIC_PIPE_LAYOUT;
    magic: u32 = TYPE_MAGIC,
};

pub const DoeBindGroup = struct {
    pub const TYPE_MAGIC = MAGIC_BIND_GROUP;
    magic: u32 = TYPE_MAGIC,
    buffers: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    offsets: [MAX_BIND]u64 = [_]u64{0} ** MAX_BIND,
    count: u32 = 0,
};

pub const CmdTag = enum { dispatch, dispatch_indirect, copy_buf, render_pass };
pub const RecordedCmd = union(CmdTag) {
    dispatch: struct { pso: ?*anyopaque, bufs: [MAX_BIND]?*anyopaque, buf_count: u32, x: u32, y: u32, z: u32, wg_x: u32, wg_y: u32, wg_z: u32 },
    dispatch_indirect: struct { pso: ?*anyopaque, bufs: [MAX_BIND]?*anyopaque, buf_count: u32, indirect_buf: ?*anyopaque, offset: u64, wg_x: u32 = 0, wg_y: u32 = 0, wg_z: u32 = 0 },
    copy_buf: struct { src: ?*anyopaque, src_off: u64, dst: ?*anyopaque, dst_off: u64, size: u64 },
    render_pass: struct { pso: ?*anyopaque, target: ?*anyopaque, draw_count: u32, vertex_count: u32, instance_count: u32 },
};

pub const DoeCommandEncoder = struct {
    const TYPE_MAGIC = MAGIC_CMD_ENCODER;
    magic: u32 = TYPE_MAGIC,
    dev: *DoeDevice,
    cmds: std.ArrayListUnmanaged(RecordedCmd) = .{},
};

pub const DoeComputePass = struct {
    const TYPE_MAGIC = MAGIC_COMPUTE_PASS;
    magic: u32 = TYPE_MAGIC,
    enc: *DoeCommandEncoder,
    pipeline: ?*DoeComputePipeline = null,
    bind_groups: [4]?*DoeBindGroup = [_]?*DoeBindGroup{null} ** 4,
};

const DoeCommandBuffer = struct {
    const TYPE_MAGIC = MAGIC_CMD_BUFFER;
    magic: u32 = TYPE_MAGIC,
    dev: *DoeDevice,
    cmds: std.ArrayListUnmanaged(RecordedCmd) = .{},
};

pub const DoeTexture = struct {
    const TYPE_MAGIC = MAGIC_TEXTURE;
    magic: u32 = TYPE_MAGIC,
    mtl: ?*anyopaque = null,
    format: u32 = 0,
    width: u32 = 0,
    height: u32 = 0,
};

pub const DoeTextureView = struct {
    const TYPE_MAGIC = MAGIC_TEXTURE_VIEW;
    magic: u32 = TYPE_MAGIC,
    tex: *DoeTexture,
};

pub const DoeSampler = struct {
    const TYPE_MAGIC = MAGIC_SAMPLER;
    magic: u32 = TYPE_MAGIC,
    mtl: ?*anyopaque = null,
};

pub const DoeRenderPipeline = struct {
    const TYPE_MAGIC = MAGIC_RENDER_PIPE;
    magic: u32 = TYPE_MAGIC,
    mtl_pso: ?*anyopaque = null,
};

pub const DoeRenderPass = struct {
    const TYPE_MAGIC = MAGIC_RENDER_PASS;
    magic: u32 = TYPE_MAGIC,
    enc: *DoeCommandEncoder,
    pipeline: ?*DoeRenderPipeline = null,
    target: ?*anyopaque = null, // MTLTexture for the render target
};

pub fn make(comptime T: type) ?*T {
    return alloc.create(T) catch null;
}

pub fn cast(comptime T: type, p: ?*anyopaque) ?*T {
    const ptr = p orelse return null;
    const result: *T = @ptrCast(@alignCast(ptr));
    if (result.magic != T.TYPE_MAGIC) return null;
    return result;
}

pub fn toOpaque(p: anytype) ?*anyopaque {
    return @ptrCast(p);
}

// ============================================================
// Instance / Adapter / Device
// ============================================================

pub export fn doeNativeCreateInstance(desc: ?*anyopaque) callconv(.c) ?*anyopaque {
    _ = desc;
    const inst = make(DoeInstance) orelse return null;
    inst.* = .{};
    return toOpaque(inst);
}

pub export fn doeNativeInstanceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeInstance, raw)) |inst| alloc.destroy(inst);
}

pub export fn doeNativeInstanceWaitAny(inst: ?*anyopaque, count: usize, infos: [*]types.WGPUFutureWaitInfo, timeout_ns: u64) callconv(.c) u32 {
    _ = inst;
    _ = timeout_ns;
    for (infos[0..count]) |*info| info.completed = 1;
    return WGPU_WAIT_STATUS_SUCCESS;
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
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 1 };
    }
    const adapter = make(DoeAdapter) orelse {
        metal_bridge_release(device);
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 1 };
    };
    adapter.* = .{ .mtl_device = device };
    if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(adapter), .{ .data = null, .length = 0 }, userdata1, userdata2);
    return .{ .id = 1 };
}

// Standard-signature wrappers for routing layer compatibility.
// Flat versions above are used by doe_napi.c's bypass path; these take callback info structs.

pub export fn doeNativeInstanceRequestAdapter(
    inst: ?*anyopaque,
    options: ?*const types.WGPURequestAdapterOptions,
    info: types.WGPURequestAdapterCallbackInfo,
) callconv(.c) types.WGPUFuture {
    _ = options;
    _ = inst;
    const empty_msg = types.WGPUStringView{ .data = null, .length = 0 };
    const device = metal_bridge_create_default_device();
    if (device == null) {
        info.callback(.@"error", null, empty_msg, info.userdata1, info.userdata2);
        return .{ .id = 1 };
    }
    const adapter = make(DoeAdapter) orelse {
        metal_bridge_release(device);
        info.callback(.@"error", null, empty_msg, info.userdata1, info.userdata2);
        return .{ .id = 1 };
    };
    adapter.* = .{ .mtl_device = device };
    info.callback(.success, toOpaque(adapter), empty_msg, info.userdata1, info.userdata2);
    return .{ .id = 1 };
}

pub export fn doeNativeAdapterRequestDevice(
    adapter_raw: ?*anyopaque,
    desc: ?*const types.WGPUDeviceDescriptor,
    info: types.WGPURequestDeviceCallbackInfo,
) callconv(.c) types.WGPUFuture {
    _ = desc;
    const empty_msg = types.WGPUStringView{ .data = null, .length = 0 };
    const adapter = cast(DoeAdapter, adapter_raw) orelse {
        info.callback(.@"error", null, empty_msg, info.userdata1, info.userdata2);
        return .{ .id = 2 };
    };
    const queue = metal_bridge_device_new_command_queue(adapter.mtl_device);
    const dev = make(DoeDevice) orelse {
        info.callback(.@"error", null, empty_msg, info.userdata1, info.userdata2);
        return .{ .id = 2 };
    };
    dev.* = .{ .mtl_device = adapter.mtl_device, .mtl_queue = queue };
    info.callback(.success, toOpaque(dev), empty_msg, info.userdata1, info.userdata2);
    return .{ .id = 2 };
}

pub export fn doeNativeAdapterRelease(raw: ?*anyopaque) callconv(.c) void {
    // Adapter does NOT own the MTLDevice — device ownership transfers to DoeDevice.
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
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 2 };
    };
    const queue = metal_bridge_device_new_command_queue(adapter.mtl_device);
    const dev = make(DoeDevice) orelse {
        if (callback) |cb| cb(WGPU_REQUEST_STATUS_ERROR, null, .{ .data = null, .length = 0 }, userdata1, userdata2);
        return .{ .id = 2 };
    };
    dev.* = .{ .mtl_device = adapter.mtl_device, .mtl_queue = queue };
    if (callback) |cb| cb(WGPU_REQUEST_STATUS_SUCCESS, toOpaque(dev), .{ .data = null, .length = 0 }, userdata1, userdata2);
    return .{ .id = 2 };
}

pub export fn doeNativeDeviceRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeDevice, raw)) |d| {
        if (d.queue) |q| alloc.destroy(q);
        if (d.mtl_queue) |q| metal_bridge_release(q);
        if (d.mtl_device) |dev| metal_bridge_release(dev);
        alloc.destroy(d);
    }
}

pub export fn doeNativeDeviceGetQueue(raw: ?*anyopaque) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, raw) orelse return null;
    if (dev.queue) |q| return toOpaque(q);
    const q = make(DoeQueue) orelse return null;
    q.* = .{ .dev = dev };
    q.mtl_event = metal_bridge_device_new_shared_event(dev.mtl_device);
    dev.queue = q;
    return toOpaque(q);
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
    if (buf.mtl == null) {
        alloc.destroy(buf);
        return null;
    }
    if (d.mappedAtCreation != 0) buf.mapped = true;
    return toOpaque(buf);
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

/// Wait for any pending GPU work on the queue, then release the command buffer.
/// Also executes deferred CPU copies that depend on the completed GPU work.
/// Uses MTLSharedEvent for GPU→CPU sync (direct memory poll, no GCD intermediary).
pub fn flush_pending_work(q: *DoeQueue) void {
    if (q.pending_cmd) |cmd| {
        if (q.mtl_event) |ev| {
            metal_bridge_shared_event_wait(ev, q.event_counter);
        }
        metal_bridge_release(cmd);
        q.pending_cmd = null;
    }
    executeDeferredCopies(q);
}

fn executeDeferredCopies(q: *DoeQueue) void {
    for (q.deferred_copies[0..q.deferred_copy_count]) |dc| {
        @memcpy(dc.dst[0..dc.size], dc.src[0..dc.size]);
    }
    q.deferred_copy_count = 0;
}

pub fn try_schedule_deferred_copy(
    q: *DoeQueue,
    src_raw: ?*anyopaque,
    src_off: u64,
    dst_raw: ?*anyopaque,
    dst_off: u64,
    size: u64,
) bool {
    if (size == 0 or q.deferred_copy_count >= MAX_DEFERRED_COPIES) return false;
    const src = cast(DoeBuffer, src_raw) orelse return false;
    const dst = cast(DoeBuffer, dst_raw) orelse return false;
    const copy_size: usize = @intCast(size);
    const src_offset: usize = @intCast(src_off);
    const dst_offset: usize = @intCast(dst_off);
    if (src_offset + copy_size > src.size or dst_offset + copy_size > dst.size) return false;
    const src_ptr = metal_bridge_buffer_contents(src.mtl) orelse return false;
    const dst_ptr = metal_bridge_buffer_contents(dst.mtl) orelse return false;
    q.deferred_copies[q.deferred_copy_count] = .{
        .src = src_ptr + src_offset,
        .dst = dst_ptr + dst_offset,
        .size = copy_size,
    };
    q.deferred_copy_count += 1;
    return true;
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
    if (cast(DoeBuffer, buf_raw)) |b| b.mapped = true;
    cb_info.callback(WGPU_MAP_ASYNC_STATUS_SUCCESS, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
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

// Shader module and compute pipeline creation in doe_shader_native.zig.
const shader = @import("doe_shader_native.zig");
pub const doeNativeDeviceCreateShaderModule = shader.doeNativeDeviceCreateShaderModule;
pub const doeNativeShaderModuleRelease = shader.doeNativeShaderModuleRelease;
pub const doeNativeDeviceCreateComputePipeline = shader.doeNativeDeviceCreateComputePipeline;
pub const doeNativeComputePipelineRelease = shader.doeNativeComputePipelineRelease;

// Bind group, bind group layout, and pipeline layout exports are in doe_bind_group_native.zig.
const bind_group = @import("doe_bind_group_native.zig");
pub const doeNativeDeviceCreateBindGroupLayout = bind_group.doeNativeDeviceCreateBindGroupLayout;
pub const doeNativeBindGroupLayoutRelease = bind_group.doeNativeBindGroupLayoutRelease;
pub const doeNativeDeviceCreateBindGroup = bind_group.doeNativeDeviceCreateBindGroup;
pub const doeNativeBindGroupRelease = bind_group.doeNativeBindGroupRelease;
pub const doeNativeDeviceCreatePipelineLayout = bind_group.doeNativeDeviceCreatePipelineLayout;
pub const doeNativePipelineLayoutRelease = bind_group.doeNativePipelineLayoutRelease;

// ============================================================
// Command Encoder / Compute Pass
// ============================================================

pub export fn doeNativeDeviceCreateCommandEncoder(dev_raw: ?*anyopaque, desc: ?*const types.WGPUCommandEncoderDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const enc = make(DoeCommandEncoder) orelse return null;
    enc.* = .{ .dev = dev };
    return toOpaque(enc);
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
    return toOpaque(pass);
}

pub export fn doeNativeCopyBufferToBuffer(enc_raw: ?*anyopaque, src_raw: ?*anyopaque, src_off: u64, dst_raw: ?*anyopaque, dst_off: u64, size: u64) callconv(.c) void {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return;
    const src = cast(DoeBuffer, src_raw) orelse return;
    const dst = cast(DoeBuffer, dst_raw) orelse return;
    enc.cmds.append(alloc, .{ .copy_buf = .{
        .src = src.mtl,
        .src_off = src_off,
        .dst = dst.mtl,
        .dst_off = dst_off,
        .size = size,
    } }) catch std.debug.panic("doe_wgpu_native: OOM recording copy command", .{});
}

pub export fn doeNativeCommandEncoderFinish(enc_raw: ?*anyopaque, desc: ?*const types.WGPUCommandBufferDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const cb = make(DoeCommandBuffer) orelse return null;
    cb.* = .{ .dev = enc.dev, .cmds = enc.cmds };
    enc.cmds = .{}; // Transfer ownership.
    return toOpaque(cb);
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

    // Flush any prior pending GPU work before encoding new commands.
    flush_pending_work(q);

    // Batch all recorded commands into a single MTLCommandBuffer.
    const mtl_cmd = metal_bridge_create_command_buffer(queue) orelse return;
    var has_gpu_work = false;

    for (cmd_bufs[0..count]) |raw| {
        const cb = cast(DoeCommandBuffer, raw) orelse continue;
        for (cb.cmds.items) |cmd| {
            switch (cmd) {
                .dispatch => |d| {
                    var bufs_copy = d.bufs;
                    metal_bridge_cmd_buf_encode_compute_dispatch(
                        mtl_cmd,
                        d.pso,
                        @as(?[*]?*anyopaque, &bufs_copy),
                        d.buf_count,
                        d.x,
                        d.y,
                        d.z,
                        d.wg_x,
                        d.wg_y,
                        d.wg_z,
                    );
                    has_gpu_work = true;
                },
                .copy_buf => |c| {
                    // Apple Silicon unified memory: defer as CPU memcpy after GPU completion
                    // whenever both buffers expose shared contents.
                    if (!try_schedule_deferred_copy(q, c.src, c.src_off, c.dst, c.dst_off, c.size)) {
                        metal_bridge_cmd_buf_encode_blit_copy(
                            mtl_cmd,
                            c.src,
                            @intCast(c.src_off),
                            c.dst,
                            @intCast(c.dst_off),
                            @intCast(c.size),
                        );
                        has_gpu_work = true;
                    }
                },
                .dispatch_indirect => |d| {
                    var bufs_copy = d.bufs;
                    metal_bridge_cmd_buf_encode_compute_dispatch_indirect(
                        mtl_cmd,
                        d.pso,
                        @as(?[*]?*anyopaque, &bufs_copy),
                        d.buf_count,
                        d.indirect_buf,
                        d.offset,
                        d.wg_x,
                        d.wg_y,
                        d.wg_z,
                    );
                    has_gpu_work = true;
                },
                .render_pass => |r| {
                    const renc = metal_bridge_cmd_buf_render_encoder(mtl_cmd, r.pso, r.target);
                    if (renc) |e| {
                        metal_bridge_render_encoder_draw(e, r.draw_count, r.vertex_count, r.instance_count, 0, r.pso);
                        metal_bridge_render_encoder_end(e);
                        metal_bridge_release(e);
                    }
                    has_gpu_work = true;
                },
            }
        }
    }

    if (has_gpu_work) {
        // Signal shared event after GPU work completes (direct GPU→CPU sync).
        q.event_counter += 1;
        metal_bridge_command_buffer_encode_signal_event(mtl_cmd, q.mtl_event, q.event_counter);
        metal_bridge_command_buffer_commit(mtl_cmd);
        q.pending_cmd = mtl_cmd;
    } else {
        metal_bridge_release(mtl_cmd);
        executeDeferredCopies(q);
    }
}

/// Flush pending GPU work. Called before CPU reads (mapAsync) and at queue release.
pub export fn doeNativeQueueFlush(q_raw: ?*anyopaque) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    flush_pending_work(q);
}

const compute_fast = @import("doe_compute_fast.zig");

pub export fn doeNativeQueueWriteBuffer(q_raw: ?*anyopaque, buf_raw: ?*anyopaque, offset: u64, data: [*]const u8, size: usize) callconv(.c) void {
    _ = q_raw;
    const buf = cast(DoeBuffer, buf_raw) orelse return;
    const contents = metal_bridge_buffer_contents(buf.mtl) orelse return;
    const dst = (contents + @as(usize, @intCast(offset)))[0..size];
    @memcpy(dst, data[0..size]);
}

pub export fn doeNativeQueueRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeQueue, raw)) |q| {
        flush_pending_work(q);
        if (q.mtl_event) |ev| metal_bridge_release(ev);
        alloc.destroy(q);
    }
}

// Texture, Sampler, Render Pipeline, Render Pass exports are in doe_render_native.zig.
const render = @import("doe_render_native.zig");
pub const doeNativeDeviceCreateTexture = render.doeNativeDeviceCreateTexture;
pub const doeNativeTextureCreateView = render.doeNativeTextureCreateView;
pub const doeNativeTextureRelease = render.doeNativeTextureRelease;
pub const doeNativeTextureViewRelease = render.doeNativeTextureViewRelease;
pub const doeNativeDeviceCreateSampler = render.doeNativeDeviceCreateSampler;
pub const doeNativeSamplerRelease = render.doeNativeSamplerRelease;
pub const doeNativeDeviceCreateRenderPipeline = render.doeNativeDeviceCreateRenderPipeline;
pub const doeNativeRenderPipelineRelease = render.doeNativeRenderPipelineRelease;
pub const doeNativeCommandEncoderBeginRenderPass = render.doeNativeCommandEncoderBeginRenderPass;
pub const doeNativeRenderPassSetPipeline = render.doeNativeRenderPassSetPipeline;
pub const doeNativeRenderPassDraw = render.doeNativeRenderPassDraw;
pub const doeNativeRenderPassEnd = render.doeNativeRenderPassEnd;
pub const doeNativeRenderPassRelease = render.doeNativeRenderPassRelease;

// ============================================================
// Queue: onSubmittedWorkDone — Doe is synchronous, so call back immediately.
pub export fn doeNativeQueueOnSubmittedWorkDone(q_raw: ?*anyopaque, info: types.WGPUQueueWorkDoneCallbackInfo) callconv(.c) types.WGPUFuture {
    _ = q_raw;
    info.callback(.success, .{ .data = null, .length = 0 }, info.userdata1, info.userdata2);
    return .{ .id = 4 };
}

// Compute extensions (getBindGroupLayout, dispatchIndirect) in doe_compute_ext_native.zig.
const compute_ext = @import("doe_compute_ext_native.zig");
pub const doeNativeComputePassSetPipeline = compute_ext.doeNativeComputePassSetPipeline;
pub const doeNativeComputePassSetBindGroup = compute_ext.doeNativeComputePassSetBindGroup;
pub const doeNativeComputePassDispatch = compute_ext.doeNativeComputePassDispatch;
pub const doeNativeComputePassEnd = compute_ext.doeNativeComputePassEnd;
pub const doeNativeComputePassRelease = compute_ext.doeNativeComputePassRelease;
pub const doeNativeComputePipelineGetBindGroupLayout = compute_ext.doeNativeComputePipelineGetBindGroupLayout;
pub const doeNativeComputePassDispatchIndirect = compute_ext.doeNativeComputePassDispatchIndirect;

// Feature queries and device limits are in doe_device_caps.zig.
const caps = @import("doe_device_caps.zig");
pub const doeNativeAdapterHasFeature = caps.doeNativeAdapterHasFeature;
pub const doeNativeDeviceHasFeature = caps.doeNativeDeviceHasFeature;
pub const doeNativeDeviceGetLimits = caps.doeNativeDeviceGetLimits;
pub const doeNativeAdapterGetLimits = caps.doeNativeAdapterGetLimits;

comptime {
    _ = shader;
    _ = bind_group;
    _ = compute_fast;
    _ = render;
    _ = compute_ext;
    _ = caps;
}

// Instance process events (no-op for sync).
pub export fn doeNativeInstanceProcessEvents(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}
