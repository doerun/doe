// doe_wgpu_native.zig — Native wgpu* C ABI implementations backed by Metal.
// Implements the ~40 functions needed by doe_napi.c without Dawn.
//
// Limitations (v0.1):
// - No reference counting — release destroys immediately.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const wgsl_compiler = @import("doe_wgsl/mod.zig");
const error_scope = @import("error_scope.zig");
const gpu_timeline = @import("gpu_timeline.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_release = bridge.metal_bridge_release;

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
pub const MAX_RENDER_BIND_GROUPS: usize = 4;
pub const MAX_COMPUTE_BIND_GROUPS: usize = 4;
pub const MAX_FLAT_BIND: usize = MAX_BIND * MAX_COMPUTE_BIND_GROUPS;
pub const MAX_VERTEX_BUFFERS: usize = 8;
pub const VERTEX_BUFFER_SLOT_BASE: u32 = 8;
pub const ERR_CAP: usize = 512;

// WebGPU status constants — must match doe_napi.c definitions.
const WGPU_MAP_ASYNC_STATUS_SUCCESS: u32 = 1;

pub const DoeInstance = struct {
    const TYPE_MAGIC = MAGIC_INSTANCE;
    magic: u32 = TYPE_MAGIC,
};

pub const DoeAdapter = struct {
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
    // Per-device error scope stack for pushErrorScope/popErrorScope.
    error_scopes: error_scope.ErrorScopeStack = error_scope.ErrorScopeStack.init(),
};

pub const DeferredCopy = struct {
    src: [*]const u8,
    dst: [*]u8,
    size: usize,
};
pub const MAX_DEFERRED_COPIES: u32 = 16;

pub const DeferredResolve = struct {
    counter_buffer: ?*anyopaque,
    first_query: u32,
    query_count: u32,
    dst_mtl: ?*anyopaque,
    dst_offset: u64,
};
pub const MAX_DEFERRED_RESOLVES: u32 = 8;

pub const DoeQueue = struct {
    pub const TYPE_MAGIC = MAGIC_QUEUE;
    magic: u32 = TYPE_MAGIC,
    dev: *DoeDevice,
    pending_cmd: ?*anyopaque = null,
    mtl_event: ?*anyopaque = null, // MTLSharedEvent for user-space GPU fence
    event_counter: u64 = 0,
    // Timeline tracks monotonic submit counter and fires async callbacks.
    gpu_timeline: gpu_timeline.GpuTimeline = gpu_timeline.GpuTimeline.init(null),
    deferred_copies: [MAX_DEFERRED_COPIES]DeferredCopy = undefined,
    deferred_copy_count: u32 = 0,
    deferred_resolves: [MAX_DEFERRED_RESOLVES]DeferredResolve = undefined,
    deferred_resolve_count: u32 = 0,
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
    // True when the WGSL source uses arrayLength() — dispatch must pass _doe_sizes buffer.
    needs_sizes_buf: bool = false,
    // Precompiled shader storage for non-Metal backends.
    // SPIR-V binary (heap-allocated copy, owned by this module).
    spirv_data: ?[]const u32 = null,
    // HLSL source text (heap-allocated copy, owned by this module).
    hlsl_source: ?[]const u8 = null,
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
    needs_sizes_buf: bool = false,
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
    textures: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    samplers: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    offsets: [MAX_BIND]u64 = [_]u64{0} ** MAX_BIND,
    // Byte size of each buffer — used to fill _doe_sizes for arrayLength.
    buffer_sizes: [MAX_BIND]u64 = [_]u64{0} ** MAX_BIND,
    count: u32 = 0,
};

pub const CmdTag = enum { dispatch, dispatch_indirect, copy_buf, copy_buffer_to_texture, copy_texture_to_buffer, render_pass, write_timestamp, resolve_query_set };
pub const RecordedCmd = union(CmdTag) {
    dispatch: struct { pso: ?*anyopaque, needs_sizes_buf: bool, bufs: [MAX_FLAT_BIND]?*anyopaque, buf_sizes: [MAX_FLAT_BIND]u64, buf_count: u32, x: u32, y: u32, z: u32, wg_x: u32, wg_y: u32, wg_z: u32 },
    dispatch_indirect: struct { pso: ?*anyopaque, needs_sizes_buf: bool, bufs: [MAX_FLAT_BIND]?*anyopaque, buf_sizes: [MAX_FLAT_BIND]u64, buf_count: u32, indirect_buf: ?*anyopaque, offset: u64, wg_x: u32 = 0, wg_y: u32 = 0, wg_z: u32 = 0 },
    copy_buf: struct { src: ?*anyopaque, src_off: u64, dst: ?*anyopaque, dst_off: u64, size: u64 },
    copy_buffer_to_texture: struct {
        src_buffer: ?*anyopaque,
        src_offset: u64,
        src_bytes_per_row: u32,
        src_rows_per_image: u32,
        dst_texture: ?*anyopaque,
        dst_mip_level: u32,
        width: u32,
        height: u32,
        depth_or_array_layers: u32,
    },
    copy_texture_to_buffer: struct {
        src_texture: ?*anyopaque,
        src_mip_level: u32,
        dst_buffer: ?*anyopaque,
        dst_offset: u64,
        dst_bytes_per_row: u32,
        dst_rows_per_image: u32,
        width: u32,
        height: u32,
        depth_or_array_layers: u32,
    },
    render_pass: struct {
        pso: ?*anyopaque,
        depth_state: ?*anyopaque,
        target: ?*anyopaque,
        depth_target: ?*anyopaque,
        topology: u32,
        front_face: u32,
        cull_mode: u32,
        draw_count: u32,
        vertex_count: u32,
        instance_count: u32,
        first_vertex: u32,
        first_instance: u32,
        indexed: bool = false,
        index_buffer: ?*anyopaque = null,
        index_offset: u64 = 0,
        index_format: u32 = 0,
        index_count: u32 = 0,
        base_vertex: i32 = 0,
        bind_buffers: [MAX_FLAT_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        bind_buffer_offsets: [MAX_FLAT_BIND]u64 = [_]u64{0} ** MAX_FLAT_BIND,
        bind_textures: [MAX_FLAT_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        bind_samplers: [MAX_FLAT_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        vertex_buffers: [MAX_VERTEX_BUFFERS]?*anyopaque = [_]?*anyopaque{null} ** MAX_VERTEX_BUFFERS,
        vertex_buffer_offsets: [MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** MAX_VERTEX_BUFFERS,
        depth_compare: u32 = 0,
        depth_write_enabled: bool = false,
        unclipped_depth: bool = false,
        clear_r: f64 = 0,
        clear_g: f64 = 0,
        clear_b: f64 = 0,
        clear_a: f64 = 1,
    },
    write_timestamp: struct { counter_buffer: ?*anyopaque, query_index: u32 },
    resolve_query_set: struct { counter_buffer: ?*anyopaque, first_query: u32, query_count: u32, dst_mtl: ?*anyopaque, dst_offset: u64 },
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

pub const DoeCommandBuffer = struct {
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
    depth_or_array_layers: u32 = 1,
    dimension: u32 = 0,
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
    depth_state: ?*anyopaque = null,
    topology: u32 = 0x00000004,
    front_face: u32 = 0x00000001,
    cull_mode: u32 = 0x00000001,
    depth_compare: u32 = 0,
    depth_write_enabled: bool = false,
    unclipped_depth: bool = false,
};

pub const DoeRenderPass = struct {
    const TYPE_MAGIC = MAGIC_RENDER_PASS;
    magic: u32 = TYPE_MAGIC,
    enc: *DoeCommandEncoder,
    pipeline: ?*DoeRenderPipeline = null,
    target: ?*anyopaque = null, // MTLTexture for the render target
    depth_target: ?*anyopaque = null,
    depth_compare: u32 = 0,
    depth_write_enabled: bool = false,
    clear_r: f64 = 0,
    clear_g: f64 = 0,
    clear_b: f64 = 0,
    clear_a: f64 = 1,
    bind_groups: [MAX_RENDER_BIND_GROUPS]?*DoeBindGroup = [_]?*DoeBindGroup{null} ** MAX_RENDER_BIND_GROUPS,
    vertex_buffers: [MAX_VERTEX_BUFFERS]?*DoeBuffer = [_]?*DoeBuffer{null} ** MAX_VERTEX_BUFFERS,
    vertex_buffer_offsets: [MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** MAX_VERTEX_BUFFERS,
    index_buffer: ?*DoeBuffer = null,
    index_offset: u64 = 0,
    index_format: u32 = 0,
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

// ============================================================
// Shard re-exports
// ============================================================

// Instance / adapter / device lifecycle in doe_instance_device_native.zig.
const instance_device = @import("doe_instance_device_native.zig");
pub const doeNativeCreateInstance = instance_device.doeNativeCreateInstance;
pub const doeNativeInstanceRelease = instance_device.doeNativeInstanceRelease;
pub const doeNativeInstanceWaitAny = instance_device.doeNativeInstanceWaitAny;
pub const doeNativeRequestAdapterFlat = instance_device.doeNativeRequestAdapterFlat;
pub const doeNativeInstanceRequestAdapter = instance_device.doeNativeInstanceRequestAdapter;
pub const doeNativeAdapterRequestDevice = instance_device.doeNativeAdapterRequestDevice;
pub const doeNativeAdapterRelease = instance_device.doeNativeAdapterRelease;
pub const doeNativeRequestDeviceFlat = instance_device.doeNativeRequestDeviceFlat;
pub const doeNativeDeviceRelease = instance_device.doeNativeDeviceRelease;
pub const doeNativeDeviceGetQueue = instance_device.doeNativeDeviceGetQueue;

// Shader module and compute pipeline creation in doe_shader_native.zig.
const shader = @import("doe_shader_native.zig");
pub const doeNativeDeviceCreateShaderModule = shader.doeNativeDeviceCreateShaderModule;
pub const doeNativeShaderModuleRelease = shader.doeNativeShaderModuleRelease;
pub const doeNativeDeviceCreateComputePipeline = shader.doeNativeDeviceCreateComputePipeline;
pub const doeNativeComputePipelineRelease = shader.doeNativeComputePipelineRelease;

// Bind group, bind group layout, and pipeline layout in doe_bind_group_native.zig.
const bind_group = @import("doe_bind_group_native.zig");
pub const doeNativeDeviceCreateBindGroupLayout = bind_group.doeNativeDeviceCreateBindGroupLayout;
pub const doeNativeBindGroupLayoutRelease = bind_group.doeNativeBindGroupLayoutRelease;
pub const doeNativeDeviceCreateBindGroup = bind_group.doeNativeDeviceCreateBindGroup;
pub const doeNativeBindGroupRelease = bind_group.doeNativeBindGroupRelease;
pub const doeNativeDeviceCreatePipelineLayout = bind_group.doeNativeDeviceCreatePipelineLayout;
pub const doeNativePipelineLayoutRelease = bind_group.doeNativePipelineLayoutRelease;

// Command encoder, command buffer, and texture copy recording in doe_encoder_native.zig.
const encoder = @import("doe_encoder_native.zig");
pub const doeNativeDeviceCreateCommandEncoder = encoder.doeNativeDeviceCreateCommandEncoder;
pub const doeNativeCommandEncoderRelease = encoder.doeNativeCommandEncoderRelease;
pub const doeNativeCommandEncoderBeginComputePass = encoder.doeNativeCommandEncoderBeginComputePass;
pub const doeNativeCopyBufferToBuffer = encoder.doeNativeCopyBufferToBuffer;
pub const doeNativeCommandEncoderCopyBufferToTexture = encoder.doeNativeCommandEncoderCopyBufferToTexture;
pub const doeNativeCommandEncoderCopyTextureToBuffer = encoder.doeNativeCommandEncoderCopyTextureToBuffer;
pub const doeNativeCommandEncoderFinish = encoder.doeNativeCommandEncoderFinish;
pub const doeNativeCommandBufferRelease = encoder.doeNativeCommandBufferRelease;

// Queue submit loop, deferred-work helpers, and queue lifecycle in doe_queue_submit_native.zig.
const queue_submit = @import("doe_queue_submit_native.zig");
// Re-exported for callers (e.g. doe_compute_fast.zig) that go through doe_wgpu_native.
pub const flush_pending_work = queue_submit.flush_pending_work;
pub const try_schedule_deferred_copy = queue_submit.try_schedule_deferred_copy;
pub const doeNativeQueueSubmit = queue_submit.doeNativeQueueSubmit;
pub const doeNativeQueueFlush = queue_submit.doeNativeQueueFlush;
pub const doeNativeQueueWriteBuffer = queue_submit.doeNativeQueueWriteBuffer;
pub const doeNativeQueueRelease = queue_submit.doeNativeQueueRelease;
pub const doeNativeQueueOnSubmittedWorkDone = queue_submit.doeNativeQueueOnSubmittedWorkDone;

// Texture, Sampler, Render Pipeline, Render Pass exports in doe_render_native.zig.
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
pub const doeNativeRenderPassSetBindGroup = render.doeNativeRenderPassSetBindGroup;
pub const doeNativeRenderPassSetVertexBuffer = render.doeNativeRenderPassSetVertexBuffer;
pub const doeNativeRenderPassSetIndexBuffer = render.doeNativeRenderPassSetIndexBuffer;
pub const doeNativeRenderPassDraw = render.doeNativeRenderPassDraw;
pub const doeNativeRenderPassDrawIndexed = render.doeNativeRenderPassDrawIndexed;
pub const doeNativeRenderPassEnd = render.doeNativeRenderPassEnd;
pub const doeNativeRenderPassRelease = render.doeNativeRenderPassRelease;

// Compute pass operations (setBindGroup, dispatch, dispatchIndirect, getBindGroupLayout) in doe_compute_ext_native.zig.
const compute_ext = @import("doe_compute_ext_native.zig");
pub const doeNativeComputePassSetPipeline = compute_ext.doeNativeComputePassSetPipeline;
pub const doeNativeComputePassSetBindGroup = compute_ext.doeNativeComputePassSetBindGroup;
pub const doeNativeComputePassDispatch = compute_ext.doeNativeComputePassDispatch;
pub const doeNativeComputePassEnd = compute_ext.doeNativeComputePassEnd;
pub const doeNativeComputePassRelease = compute_ext.doeNativeComputePassRelease;
pub const doeNativeComputePipelineGetBindGroupLayout = compute_ext.doeNativeComputePipelineGetBindGroupLayout;
pub const doeNativeComputePassDispatchIndirect = compute_ext.doeNativeComputePassDispatchIndirect;

// Feature queries and device limits in doe_device_caps.zig.
const caps = @import("doe_device_caps.zig");
pub const doeNativeAdapterHasFeature = caps.doeNativeAdapterHasFeature;
pub const doeNativeDeviceHasFeature = caps.doeNativeDeviceHasFeature;
pub const doeNativeDeviceGetLimits = caps.doeNativeDeviceGetLimits;
pub const doeNativeAdapterGetLimits = caps.doeNativeAdapterGetLimits;

// QuerySet (timestamp query) exports in doe_query_native.zig.
const query = @import("doe_query_native.zig");
pub const doeNativeDeviceCreateQuerySet = query.doeNativeDeviceCreateQuerySet;
pub const doeNativeCommandEncoderWriteTimestamp = query.doeNativeCommandEncoderWriteTimestamp;
pub const doeNativeCommandEncoderResolveQuerySet = query.doeNativeCommandEncoderResolveQuerySet;
pub const doeNativeQuerySetDestroy = query.doeNativeQuerySetDestroy;

comptime {
    _ = instance_device;
    _ = shader;
    _ = bind_group;
    _ = encoder;
    _ = queue_submit;
    _ = render;
    _ = compute_ext;
    _ = caps;
    _ = query;
    _ = @import("doe_compute_fast.zig");
}

// Instance process events (no-op for sync).
pub export fn doeNativeInstanceProcessEvents(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}
