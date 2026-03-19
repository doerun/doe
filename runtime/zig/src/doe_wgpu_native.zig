// doe_wgpu_native.zig — Native wgpu* C ABI implementations backed by Metal, Vulkan, or D3D12.
// Implements the ~40 functions needed by doe_napi.c without Dawn.
//
// Limitations (v0.1):
// - No reference counting — release destroys immediately.
// - Vulkan path executes commands immediately (no deferred batching).

const std = @import("std");
const model = @import("model.zig");
const types = @import("core/abi/wgpu_types.zig");
const wgsl_compiler = @import("doe_wgsl/mod.zig");
const error_scope = @import("error_scope.zig");
const gpu_timeline = @import("gpu_timeline.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");
const d3d12_constants = @import("backend/d3d12/d3d12_constants.zig");
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

// Backend discriminant — selects Metal, Vulkan, or D3D12 execution paths at device level.
pub const BackendKind = enum(u8) { metal = 0, vulkan = 1, d3d12 = 2 };

// NativeVulkanRuntime import — used by buffer create/release and device lifecycle.
pub const NativeVulkanRuntime = @import("backend/vulkan/native_runtime.zig").NativeVulkanRuntime;
pub const NativeD3D12Runtime = @import("backend/d3d12/d3d12_native_runtime.zig").NativeD3D12Runtime;

pub const MAX_BIND: usize = 16;
pub const MAX_RENDER_BIND_GROUPS: usize = 4;
pub const MAX_COMPUTE_BIND_GROUPS: usize = 4;
pub const MAX_FLAT_BIND: usize = MAX_BIND * MAX_COMPUTE_BIND_GROUPS;
pub const MAX_VERTEX_BUFFERS: usize = 8;
pub const MAX_VERTEX_ATTRIBUTES: usize = 16;
pub const VERTEX_BUFFER_SLOT_BASE: u32 = 8;
pub const ERR_CAP: usize = 512;

// WebGPU status constants — must match doe_napi.c definitions.
const WGPU_MAP_ASYNC_STATUS_SUCCESS: u32 = 1;
const WGPU_MAP_ASYNC_STATUS_VALIDATION_ERROR: u32 = 4;
const D3D12_HEAP_TYPE_DEFAULT: c_int = 1;

pub const DoeInstance = struct {
    const TYPE_MAGIC = MAGIC_INSTANCE;
    magic: u32 = TYPE_MAGIC,
};

pub const DoeAdapter = struct {
    const TYPE_MAGIC = MAGIC_ADAPTER;
    magic: u32 = TYPE_MAGIC,
    mtl_device: ?*anyopaque = null,
    backend: BackendKind = .metal,
};

pub const DoeDevice = struct {
    const TYPE_MAGIC = MAGIC_DEVICE;
    magic: u32 = TYPE_MAGIC,
    mtl_device: ?*anyopaque = null,
    mtl_queue: ?*anyopaque = null,
    queue: ?*DoeQueue = null, // cached; getQueue returns this
    // Per-device error scope stack for pushErrorScope/popErrorScope.
    error_scopes: error_scope.ErrorScopeStack = error_scope.ErrorScopeStack.init(),
    backend: BackendKind = .metal,
    // Heap-allocated NativeVulkanRuntime; non-null only when backend == .vulkan.
    vk_runtime: ?*anyopaque = null,
    // Heap-allocated NativeD3D12Runtime; non-null only when backend == .d3d12.
    d3d12_runtime: ?*anyopaque = null,
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
    backend: BackendKind = .metal,
    mtl: ?*anyopaque = null,
    size: u64 = 0,
    usage: u64 = 0,
    mapped: bool = false,
    d3d12_heap_type: c_int = 0,
    d3d12_mapped_ptr: ?*anyopaque = null,
    // Vulkan-only fields: key in NativeVulkanRuntime.compute_buffers and
    // back-reference to the runtime for cleanup on release.
    vk_id: u64 = 0,
    vk_runtime_ref: ?*anyopaque = null,
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

pub const CompilationMessageKind = enum(u8) {
    none,
    @"error",
    warning,
    info,
};

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
    // Original WGSL source (heap-allocated copy, owned by this module).
    // Retained for re-translation when pipeline override constants are provided.
    wgsl_source: ?[]const u8 = null,
    compilation_message_kind: CompilationMessageKind = .none,
    compilation_message: ?[]const u8 = null,
    compilation_message_line: u32 = 0,
    compilation_message_column: u32 = 0,
};

pub const DoeComputePipeline = struct {
    pub const TYPE_MAGIC = MAGIC_COMPUTE_PIPE;
    magic: u32 = TYPE_MAGIC,
    mtl_pso: ?*anyopaque = null,
    layout: ?*DoePipelineLayout = null,
    bindings: [MAX_SHADER_BINDINGS]BindingInfo = undefined,
    binding_count: u32 = 0,
    wg_x: u32 = 0,
    wg_y: u32 = 0,
    wg_z: u32 = 0,
    needs_sizes_buf: bool = false,
    // Vulkan-only: heap-allocated SPIR-V words, duplicated from the shader module.
    spirv_data: ?[]const u32 = null,
};

pub const DoeBindGroupLayout = struct {
    const TYPE_MAGIC = MAGIC_BGL;
    magic: u32 = TYPE_MAGIC,
    entry_count: u32 = 0,
    entries: ?[]DoeBindGroupLayoutEntry = null,
};

pub const DoeBindGroupLayoutEntry = struct {
    binding: u32 = 0,
    resource_kind: u32 = 0,
    texture_sample_type: u32 = types.WGPUTextureSampleType_Undefined,
    texture_view_dimension: u32 = types.WGPUTextureViewDimension_Undefined,
    texture_multisampled: bool = false,
};

pub const DoePipelineLayout = struct {
    const TYPE_MAGIC = MAGIC_PIPE_LAYOUT;
    magic: u32 = TYPE_MAGIC,
    immediate_size: u32 = 0,
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

pub const CmdTag = enum { dispatch, dispatch_indirect, copy_buf, copy_buffer_to_texture, copy_texture_to_buffer, clear_buffer, copy_texture_to_texture, render_pass, write_timestamp, resolve_query_set };
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
    clear_buffer: struct {
        buffer: ?*anyopaque, // MTLBuffer
        offset: u64,
        size: u64,
    },
    copy_texture_to_texture: struct {
        src_texture: ?*anyopaque,
        src_mip: u32,
        src_slice: u32,
        src_x: u32,
        src_y: u32,
        src_z: u32,
        dst_texture: ?*anyopaque,
        dst_mip: u32,
        dst_slice: u32,
        dst_x: u32,
        dst_y: u32,
        dst_z: u32,
        width: u32,
        height: u32,
        depth_or_layers: u32,
    },
    render_pass: struct {
        pso: ?*anyopaque,
        root_signature: ?*anyopaque = null,
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
        index_buffer_size: u64 = 0,
        index_count: u32 = 0,
        first_index: u32 = 0,
        base_vertex: i32 = 0,
        bind_buffers: [MAX_FLAT_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        bind_buffer_offsets: [MAX_FLAT_BIND]u64 = [_]u64{0} ** MAX_FLAT_BIND,
        bind_textures: [MAX_FLAT_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        bind_samplers: [MAX_FLAT_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        vertex_buffers: [MAX_VERTEX_BUFFERS]?*anyopaque = [_]?*anyopaque{null} ** MAX_VERTEX_BUFFERS,
        vertex_buffer_offsets: [MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** MAX_VERTEX_BUFFERS,
        vertex_buffer_sizes: [MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** MAX_VERTEX_BUFFERS,
        indirect: bool = false,
        indirect_buffer: ?*anyopaque = null,
        indirect_offset: u64 = 0,
        blend_constant: [4]f32 = .{ 0, 0, 0, 0 },
        stencil_reference: u32 = 0,
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
    backend: BackendKind = .metal,
    mtl: ?*anyopaque = null,
    format: u32 = 0,
    width: u32 = 0,
    height: u32 = 0,
    depth_or_array_layers: u32 = 1,
    dimension: u32 = 0,
    mip_level_count: u32 = 1,
    sample_count: u32 = 1,
    usage: u64 = 0,
    texture_binding_view_dimension: u32 = 0,
    view_format_count: usize = 0,
    // Vulkan-only: key in NativeVulkanRuntime.textures and back-reference
    // to the runtime for explicit release on doeNativeTextureRelease.
    vk_id: u64 = 0,
    vk_runtime_ref: ?*anyopaque = null,
};

pub const DoeTextureView = struct {
    const TYPE_MAGIC = MAGIC_TEXTURE_VIEW;
    magic: u32 = TYPE_MAGIC,
    backend: BackendKind = .metal,
    tex: *DoeTexture,
    handle: ?*anyopaque = null,
    format: u32 = 0,
    dimension: u32 = 0,
    base_mip_level: u32 = 0,
    mip_level_count: u32 = 0,
    base_array_layer: u32 = 0,
    array_layer_count: u32 = 0,
    aspect: u32 = 0,
    usage: u64 = 0,
};

pub const DoeSampler = struct {
    const TYPE_MAGIC = MAGIC_SAMPLER;
    magic: u32 = TYPE_MAGIC,
    backend: BackendKind = .metal,
    mtl: ?*anyopaque = null,
    // Vulkan-only: back-reference to the runtime for vkDestroySampler on release.
    vk_runtime_ref: ?*anyopaque = null,
};

pub const DoeRenderPipeline = struct {
    const TYPE_MAGIC = MAGIC_RENDER_PIPE;
    magic: u32 = TYPE_MAGIC,
    mtl_pso: ?*anyopaque = null,
    backend_root_signature: ?*anyopaque = null,
    layout: ?*DoePipelineLayout = null,
    vertex_layout_count: u32 = 0,
    vertex_layouts: [model.MAX_VERTEX_BUFFERS]model.RenderVertexBufferLayout = [_]model.RenderVertexBufferLayout{.{}} ** model.MAX_VERTEX_BUFFERS,
    depth_state: ?*anyopaque = null,
    topology: u32 = 0x00000004,
    front_face: u32 = 0x00000001,
    cull_mode: u32 = 0x00000001,
    depth_stencil_format: u32 = 0,
    depth_compare: u32 = 0,
    depth_write_enabled: bool = false,
    unclipped_depth: bool = false,
    stencil_front_compare: u32 = 0x00000008,
    stencil_front_fail_op: u32 = 0,
    stencil_front_depth_fail_op: u32 = 0,
    stencil_front_pass_op: u32 = 0,
    stencil_back_compare: u32 = 0x00000008,
    stencil_back_fail_op: u32 = 0,
    stencil_back_depth_fail_op: u32 = 0,
    stencil_back_pass_op: u32 = 0,
    stencil_read_mask: u32 = 0xFFFF_FFFF,
    stencil_write_mask: u32 = 0xFFFF_FFFF,
    blend_enabled: bool = false,
    color_operation: u32 = 0,
    color_src_factor: u32 = 0,
    color_dst_factor: u32 = 0,
    alpha_operation: u32 = 0,
    alpha_src_factor: u32 = 0,
    alpha_dst_factor: u32 = 0,
    color_write_mask: u32 = 0xF,
    sample_count: u32 = 1,
    vertex_buffer_count: u32 = 0,
    vertex_buffer_strides: [MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** MAX_VERTEX_BUFFERS,
    vertex_step_modes: [MAX_VERTEX_BUFFERS]u32 = [_]u32{0} ** MAX_VERTEX_BUFFERS,
    vertex_attribute_count: u32 = 0,
    vertex_attribute_formats: [MAX_VERTEX_ATTRIBUTES]u32 = [_]u32{0} ** MAX_VERTEX_ATTRIBUTES,
    vertex_attribute_offsets: [MAX_VERTEX_ATTRIBUTES]u64 = [_]u64{0} ** MAX_VERTEX_ATTRIBUTES,
    vertex_attribute_locations: [MAX_VERTEX_ATTRIBUTES]u32 = [_]u32{0} ** MAX_VERTEX_ATTRIBUTES,
    vertex_attribute_buffer_slots: [MAX_VERTEX_ATTRIBUTES]u32 = [_]u32{0} ** MAX_VERTEX_ATTRIBUTES,
};

pub const DoeRenderPass = struct {
    const TYPE_MAGIC = MAGIC_RENDER_PASS;
    magic: u32 = TYPE_MAGIC,
    enc: *DoeCommandEncoder,
    pipeline: ?*DoeRenderPipeline = null,
    max_draw_count: u64 = 50_000_000,
    recorded_draw_count: u64 = 0,
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
    vertex_buffer_sizes: [MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** MAX_VERTEX_BUFFERS,
    index_buffer: ?*DoeBuffer = null,
    index_offset: u64 = 0,
    index_format: u32 = 0,
    index_buffer_size: u64 = 0,
    viewport_x: f32 = 0,
    viewport_y: f32 = 0,
    viewport_width: ?f32 = null,
    viewport_height: ?f32 = null,
    viewport_min_depth: f32 = 0,
    viewport_max_depth: f32 = 1,
    scissor_x: u32 = 0,
    scissor_y: u32 = 0,
    scissor_width: ?u32 = null,
    scissor_height: ?u32 = null,
    blend_constant: [4]f32 = .{ 0, 0, 0, 0 },
    stencil_reference: u32 = 0,
    occlusion_query_set: ?*anyopaque = null,
    occlusion_query_active: bool = false,
    occlusion_query_index: u32 = 0,
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

// Cast the vk_runtime opaque pointer on a DoeDevice to NativeVulkanRuntime.
// Returns null when the device is Metal-backed or the pointer is unset.
pub fn device_vk_runtime(dev: *DoeDevice) ?*NativeVulkanRuntime {
    const ptr = dev.vk_runtime orelse return null;
    return @as(*NativeVulkanRuntime, @ptrCast(@alignCast(ptr)));
}

pub fn device_d3d12_runtime(dev: *DoeDevice) ?*NativeD3D12Runtime {
    const ptr = dev.d3d12_runtime orelse return null;
    return @as(*NativeD3D12Runtime, @ptrCast(@alignCast(ptr)));
}

fn d3d12_buffer_bounds_ok(buf: *const DoeBuffer, offset: usize, size: usize) bool {
    const offset_u64: u64 = @intCast(offset);
    const size_u64: u64 = @intCast(size);
    if (offset_u64 > buf.size) return false;
    if (size_u64 > buf.size - offset_u64) return false;
    return true;
}

fn d3d12_upload_heap_usage_supported(usage: u64) bool {
    const disallowed =
        types.WGPUBufferUsage_MapRead |
        types.WGPUBufferUsage_CopyDst |
        types.WGPUBufferUsage_Storage |
        types.WGPUBufferUsage_QueryResolve;
    return (usage & disallowed) == 0;
}

fn d3d12_buffer_heap_type(desc: *const types.WGPUBufferDescriptor) ?c_int {
    const usage = desc.usage;
    const wants_map_read = (usage & types.WGPUBufferUsage_MapRead) != 0;
    const wants_map_write = (usage & types.WGPUBufferUsage_MapWrite) != 0;
    if (wants_map_read and wants_map_write) return null;
    if (wants_map_read) {
        if (desc.mappedAtCreation != 0) return null;
        return d3d12_constants.HEAP_TYPE_READBACK;
    }
    if (wants_map_write) return d3d12_constants.HEAP_TYPE_UPLOAD;
    if (desc.mappedAtCreation != 0) {
        if (!d3d12_upload_heap_usage_supported(usage)) return null;
        return d3d12_constants.HEAP_TYPE_UPLOAD;
    }
    return D3D12_HEAP_TYPE_DEFAULT;
}

extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_map(resource: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_unmap(resource: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

// ============================================================
// Buffer
// ============================================================

pub export fn doeNativeDeviceCreateBuffer(dev_raw: ?*anyopaque, desc: ?*const types.WGPUBufferDescriptor) callconv(.c) ?*anyopaque {
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const buf = make(DoeBuffer) orelse return null;
    buf.* = .{ .backend = dev.backend, .size = d.size, .usage = d.usage };

    if (dev.backend == .vulkan) {
        const rt = device_vk_runtime(dev) orelse {
            alloc.destroy(buf);
            return null;
        };
        // Use the buffer's heap address as a stable, unique key in the runtime map.
        const id: u64 = @intFromPtr(buf);
        buf.vk_id = id;
        buf.vk_runtime_ref = @ptrCast(rt);
        const vk_resources = @import("backend/vulkan/vk_resources.zig");
        const cb = vk_resources.create_compute_buffer(rt, d.size, false) catch {
            alloc.destroy(buf);
            return null;
        };
        rt.compute_buffers.put(rt.allocator, id, cb) catch {
            vk_resources.release_compute_buffer(rt, cb);
            alloc.destroy(buf);
            return null;
        };
        if (d.mappedAtCreation != 0) buf.mapped = true;
        const result = toOpaque(buf);
        label_store.set(result, d.label.data, d.label.length);
        return result;
    }

    if (dev.backend == .d3d12) {
        const rt = device_d3d12_runtime(dev) orelse {
            alloc.destroy(buf);
            return null;
        };
        const heap_type = d3d12_buffer_heap_type(d) orelse {
            alloc.destroy(buf);
            return null;
        };
        buf.mtl = d3d12_bridge_device_create_buffer(rt.device, @intCast(d.size), heap_type);
        if (buf.mtl == null) {
            alloc.destroy(buf);
            return null;
        }
        buf.d3d12_heap_type = heap_type;
        if (d.mappedAtCreation != 0) {
            buf.d3d12_mapped_ptr = d3d12_bridge_resource_map(buf.mtl) orelse {
                d3d12_bridge_release(buf.mtl);
                alloc.destroy(buf);
                return null;
            };
            buf.mapped = true;
        }
        const result = toOpaque(buf);
        label_store.set(result, d.label.data, d.label.length);
        return result;
    }

    // Metal path: all buffers use shared (unified) memory on Apple Silicon.
    buf.mtl = metal_bridge_device_new_buffer_shared(dev.mtl_device, @intCast(d.size));
    if (buf.mtl == null) {
        alloc.destroy(buf);
        return null;
    }
    if (d.mappedAtCreation != 0) buf.mapped = true;
    const result = toOpaque(buf);
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeBufferRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBuffer, raw)) |b| {
        label_store.remove(raw);
        if (b.backend == .vulkan and b.vk_id != 0) {
            // Destroy the VkBuffer explicitly rather than waiting for device deinit.
            if (b.vk_runtime_ref) |rt_ptr| {
                const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
                const vk_resources = @import("backend/vulkan/vk_resources.zig");
                if (rt.compute_buffers.fetchRemove(b.vk_id)) |entry| {
                    vk_resources.release_compute_buffer(rt, entry.value);
                }
            }
            alloc.destroy(b);
            return;
        }
        if (b.backend == .d3d12) {
            if (b.d3d12_mapped_ptr != null and b.mtl != null) {
                d3d12_bridge_resource_unmap(b.mtl);
                b.d3d12_mapped_ptr = null;
            }
            if (b.mtl) |handle| d3d12_bridge_release(handle);
            alloc.destroy(b);
            return;
        }
        if (b.mtl) |m| metal_bridge_release(m);
        alloc.destroy(b);
    }
}

pub export fn doeNativeBufferUnmap(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBuffer, raw)) |b| {
        if (b.backend == .d3d12 and b.d3d12_mapped_ptr != null and b.mtl != null) {
            d3d12_bridge_resource_unmap(b.mtl);
            b.d3d12_mapped_ptr = null;
        }
        b.mapped = false;
    }
}

pub export fn doeNativeBufferMapAsync(
    buf_raw: ?*anyopaque,
    mode: u64,
    offset: usize,
    size: usize,
    cb_info: types.WGPUBufferMapCallbackInfo,
) callconv(.c) types.WGPUFuture {
    const b = cast(DoeBuffer, buf_raw) orelse {
        cb_info.callback(WGPU_MAP_ASYNC_STATUS_VALIDATION_ERROR, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
        return .{ .id = 3 };
    };
    if (!d3d12_buffer_bounds_ok(b, offset, size)) {
        cb_info.callback(WGPU_MAP_ASYNC_STATUS_VALIDATION_ERROR, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
        return .{ .id = 3 };
    }
    if (b.backend == .d3d12) {
        const wants_read = (mode & types.WGPUMapMode_Read) != 0;
        const wants_write = (mode & types.WGPUMapMode_Write) != 0;
        const expect_heap: c_int = if (wants_read and !wants_write)
            d3d12_constants.HEAP_TYPE_READBACK
        else if (wants_write and !wants_read)
            d3d12_constants.HEAP_TYPE_UPLOAD
        else
            0;
        if (expect_heap == 0 or b.d3d12_heap_type != expect_heap or b.mtl == null) {
            cb_info.callback(WGPU_MAP_ASYNC_STATUS_VALIDATION_ERROR, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
            return .{ .id = 3 };
        }
        if (b.d3d12_mapped_ptr == null) {
            b.d3d12_mapped_ptr = d3d12_bridge_resource_map(b.mtl);
        }
        if (b.d3d12_mapped_ptr == null) {
            cb_info.callback(WGPU_MAP_ASYNC_STATUS_VALIDATION_ERROR, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
            return .{ .id = 3 };
        }
        b.mapped = true;
        cb_info.callback(WGPU_MAP_ASYNC_STATUS_SUCCESS, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
        return .{ .id = 3 };
    }
    b.mapped = true;
    cb_info.callback(WGPU_MAP_ASYNC_STATUS_SUCCESS, .{ .data = null, .length = 0 }, cb_info.userdata1, cb_info.userdata2);
    return .{ .id = 3 };
}

pub export fn doeNativeBufferGetConstMappedRange(buf_raw: ?*anyopaque, offset: usize, size: usize) callconv(.c) ?*anyopaque {
    const buf = cast(DoeBuffer, buf_raw) orelse return null;
    if (!buf.mapped or !d3d12_buffer_bounds_ok(buf, offset, size)) return null;

    if (buf.backend == .vulkan and buf.vk_id != 0) {
        // Return a pointer into the persistently-mapped Vulkan host-visible allocation.
        if (buf.vk_runtime_ref) |rt_ptr| {
            const rt: *NativeVulkanRuntime = @ptrCast(@alignCast(rt_ptr));
            const cb = rt.compute_buffers.get(buf.vk_id) orelse return null;
            const base: [*]u8 = @ptrCast(cb.mapped orelse return null);
            return @ptrCast(base + offset);
        }
        return null;
    }

    if (buf.backend == .d3d12) {
        const mapped = buf.d3d12_mapped_ptr orelse return null;
        const base: [*]u8 = @ptrCast(mapped);
        return @ptrCast(base + offset);
    }

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
pub const doeNativeCommandEncoderInsertDebugMarker = encoder.doeNativeCommandEncoderInsertDebugMarker;
pub const doeNativeCommandEncoderPushDebugGroup = encoder.doeNativeCommandEncoderPushDebugGroup;
pub const doeNativeCommandEncoderPopDebugGroup = encoder.doeNativeCommandEncoderPopDebugGroup;

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
pub const doeNativeComputePassInsertDebugMarker = compute_ext.doeNativeComputePassInsertDebugMarker;
pub const doeNativeComputePassPushDebugGroup = compute_ext.doeNativeComputePassPushDebugGroup;
pub const doeNativeComputePassPopDebugGroup = compute_ext.doeNativeComputePassPopDebugGroup;

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
pub const doeNativeQuerySetGetCount = query.doeNativeQuerySetGetCount;
pub const doeNativeQuerySetGetType = query.doeNativeQuerySetGetType;
pub const doeNativeRenderPassBeginOcclusionQuery = query.doeNativeRenderPassBeginOcclusionQuery;
pub const doeNativeRenderPassEndOcclusionQuery = query.doeNativeRenderPassEndOcclusionQuery;

// Canvas format query and DOM EventTarget stubs in doe_canvas_event_native.zig.
const canvas_event = @import("doe_canvas_event_native.zig");
pub const doeNativeAdapterGetPreferredCanvasFormat = canvas_event.doeNativeAdapterGetPreferredCanvasFormat;
pub const doeNativeDeviceAddEventListener = canvas_event.doeNativeDeviceAddEventListener;
pub const doeNativeDeviceRemoveEventListener = canvas_event.doeNativeDeviceRemoveEventListener;

// Error scope lifecycle (pushErrorScope/popErrorScope/setUncapturedErrorCallback/injectError).
const error_scope_native = @import("doe_error_scope_native.zig");
pub const doeNativeDevicePushErrorScope = error_scope_native.doeNativeDevicePushErrorScope;
pub const doeNativeDevicePopErrorScope = error_scope_native.doeNativeDevicePopErrorScope;
pub const doeNativeDevicePopErrorScopeFlat = error_scope_native.doeNativeDevicePopErrorScopeFlat;
pub const doeNativeDeviceSetUncapturedErrorCallback = error_scope_native.doeNativeDeviceSetUncapturedErrorCallback;
pub const doeNativeDeviceInjectError = error_scope_native.doeNativeDeviceInjectError;

// Pipeline cache, multi-adapter, and device-lost callbacks.
const cache_adapter = @import("doe_cache_adapter_native.zig");

// setImmediates forwarding plus importExternalTexture unsupported stub in doe_immediates_external_native.zig.
const immediates_external = @import("doe_immediates_external_native.zig");
pub const doeNativeBindingCommandsSetImmediates = immediates_external.doeNativeBindingCommandsSetImmediates;
pub const doeNativeComputePassSetImmediates = immediates_external.doeNativeComputePassSetImmediates;
pub const doeNativeRenderPassSetImmediates = immediates_external.doeNativeRenderPassSetImmediates;
pub const doeNativeRenderBundleEncoderSetImmediates = immediates_external.doeNativeRenderBundleEncoderSetImmediates;
pub const doeNativeDeviceImportExternalTexture = immediates_external.doeNativeDeviceImportExternalTexture;

// RenderPassEncoder control methods (setViewport, setScissorRect, setBlendConstant,
// setStencilReference, pushDebugGroup, popDebugGroup, insertDebugMarker).
const render_pass_controls = @import("doe_render_pass_controls_native.zig");
pub const doeNativeRenderPassSetViewport = render_pass_controls.doeNativeRenderPassSetViewport;
pub const doeNativeRenderPassSetScissorRect = render_pass_controls.doeNativeRenderPassSetScissorRect;
pub const doeNativeRenderPassSetBlendConstant = render_pass_controls.doeNativeRenderPassSetBlendConstant;
pub const doeNativeRenderPassSetStencilReference = render_pass_controls.doeNativeRenderPassSetStencilReference;
pub const doeNativeRenderPassPushDebugGroup = render_pass_controls.doeNativeRenderPassPushDebugGroup;
pub const doeNativeRenderPassPopDebugGroup = render_pass_controls.doeNativeRenderPassPopDebugGroup;
pub const doeNativeRenderPassInsertDebugMarker = render_pass_controls.doeNativeRenderPassInsertDebugMarker;

// GPUAdapter.info native implementation in doe_adapter_info_native.zig.
const adapter_info = @import("doe_adapter_info_native.zig");
pub const doeNativeAdapterGetInfo = adapter_info.doeNativeAdapterGetInfo;
pub const doeNativeAdapterFreeInfo = adapter_info.doeNativeAdapterFreeInfo;

// GPUShaderModule.getCompilationInfo() in doe_shader_compilation_info_native.zig.
const shader_compilation_info = @import("doe_shader_compilation_info_native.zig");
pub const doeNativeShaderModuleGetCompilationInfo = shader_compilation_info.doeNativeShaderModuleGetCompilationInfo;

// clearBuffer, copyTextureToTexture, writeTexture in doe_command_texture_native.zig.
const command_texture = @import("doe_command_texture_native.zig");
pub const doeNativeCommandEncoderClearBuffer = command_texture.doeNativeCommandEncoderClearBuffer;
pub const doeNativeCommandEncoderCopyTextureToTexture = command_texture.doeNativeCommandEncoderCopyTextureToTexture;
pub const doeNativeQueueWriteTexture = command_texture.doeNativeQueueWriteTexture;

// Surface lifecycle (Vulkan) in doe_surface_native.zig.
const surface_native = @import("doe_surface_native.zig");
pub const doeNativeInstanceCreateSurface = surface_native.doeNativeInstanceCreateSurface;
pub const doeNativeSurfaceSetXcbHandle = surface_native.doeNativeSurfaceSetXcbHandle;
pub const doeNativeSurfaceSetWaylandHandle = surface_native.doeNativeSurfaceSetWaylandHandle;
pub const doeNativeSurfaceConfigure = surface_native.doeNativeSurfaceConfigure;
pub const doeNativeSurfaceGetCurrentTexture = surface_native.doeNativeSurfaceGetCurrentTexture;
pub const doeNativeSurfacePresent = surface_native.doeNativeSurfacePresent;
pub const doeNativeSurfaceUnconfigure = surface_native.doeNativeSurfaceUnconfigure;
pub const doeNativeSurfaceRelease = surface_native.doeNativeSurfaceRelease;

// Object debug label store in doe_label_store.zig.
pub const label_store = @import("doe_label_store.zig");
pub const doeNativeObjectSetLabel = label_store.doeNativeObjectSetLabel;
pub const doeNativeObjectGetLabel = label_store.doeNativeObjectGetLabel;
pub const doeNativeObjectRemoveLabel = label_store.doeNativeObjectRemoveLabel;

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
    _ = canvas_event;
    _ = error_scope_native;
    _ = cache_adapter;
    _ = immediates_external;
    _ = render_pass_controls;
    _ = adapter_info;
    _ = shader_compilation_info;
    _ = command_texture;
    _ = surface_native;
    _ = @import("doe_compute_fast.zig");
    // Render bundle encoder / bundle exports (sharded file).
    _ = @import("doe_bundle_native.zig");
    // Object debug label store exports.
    _ = label_store;
}

// Instance process events (no-op for sync).
pub export fn doeNativeInstanceProcessEvents(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}
