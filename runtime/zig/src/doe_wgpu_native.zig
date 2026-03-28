// doe_wgpu_native.zig — Native wgpu* C ABI implementations backed by Metal, Vulkan, or D3D12.
// Implements the ~40 functions needed by doe_napi.c without Dawn.
// Limitations (v0.1): Vulkan path executes commands immediately (no deferred batching).
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
pub const BackendKind = enum(u8) { metal = 0, vulkan = 1, d3d12 = 2 };
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
const WGPU_MAP_ASYNC_STATUS_SUCCESS: u32 = 1;
const WGPU_MAP_ASYNC_STATUS_VALIDATION_ERROR: u32 = 4;
const D3D12_HEAP_TYPE_DEFAULT: c_int = 1;
pub const DoeInstance = struct {
    const TYPE_MAGIC = MAGIC_INSTANCE;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
};
pub const DoeAdapter = struct {
    const TYPE_MAGIC = MAGIC_ADAPTER;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    instance: ?*DoeInstance = null,
    mtl_device: ?*anyopaque = null,
    backend: BackendKind = .metal,
};
pub const DoeDevice = struct {
    const TYPE_MAGIC = MAGIC_DEVICE;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    adapter: ?*DoeAdapter = null,
    mtl_device: ?*anyopaque = null,
    mtl_queue: ?*anyopaque = null,
    queue: ?*DoeQueue = null, // weak cached queue; queue retains the device
    // Per-device error scope stack for pushErrorScope/popErrorScope.
    error_scopes: error_scope.ErrorScopeStack = error_scope.ErrorScopeStack.init(),
    // Device lost callback — stored for future delivery; not yet auto-fired.
    device_lost_callback: ?types.WGPUDeviceLostCallback = null,
    device_lost_userdata1: ?*anyopaque = null,
    device_lost_userdata2: ?*anyopaque = null,
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
    ref_count: u32 = 1,
    // Queue retains the device so queue handles stay valid after early device release.
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
    ref_count: u32 = 1,
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
    // Cached host-visible mapped pointer for Vulkan buffers. Avoids HashMap
    // lookup on the writeBuffer hot path (same pattern as d3d12_mapped_ptr).
    vk_mapped_ptr: ?[*]u8 = null,
};
pub const extractWorkgroupSize = @import("doe_wgsl/shader_info.zig").extractWorkgroupSize;
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
    ref_count: u32 = 1,
    mtl_library: ?*anyopaque = null,
    bindings: [MAX_SHADER_BINDINGS]BindingInfo = undefined,
    binding_count: u32 = 0,
    bindings_ready: bool = false,
    wg_x: u32 = 0, // @workgroup_size (0 = unknown)
    wg_y: u32 = 0,
    wg_z: u32 = 0,
    needs_sizes_buf: bool = false,
    dispatch_preconditions: []const wgsl_compiler.ir.DispatchPrecondition = &.{},
    texture_dispatch_preconditions: []const wgsl_compiler.ir.TextureDispatchPrecondition = &.{},
    spirv_data: ?[]const u32 = null,
    vertex_spirv_data: ?[]const u32 = null,
    fragment_spirv_data: ?[]const u32 = null,
    hlsl_source: ?[]const u8 = null,
    wgsl_source: ?[]const u8 = null,
    compilation_message_kind: CompilationMessageKind = .none,
    compilation_message: ?[]const u8 = null,
    compilation_message_line: u32 = 0,
    compilation_message_column: u32 = 0,
};
pub const DoeComputePipeline = struct {
    pub const TYPE_MAGIC = MAGIC_COMPUTE_PIPE;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    mtl_pso: ?*anyopaque = null,
    layout: ?*DoePipelineLayout = null,
    shader_module: ?*DoeShaderModule = null,
    binding_count: u32 = 0,
    wg_x: u32 = 0,
    wg_y: u32 = 0,
    wg_z: u32 = 0,
    needs_sizes_buf: bool = false,
    dispatch_preconditions: []const wgsl_compiler.ir.DispatchPrecondition = &.{},
    texture_dispatch_preconditions: []const wgsl_compiler.ir.TextureDispatchPrecondition = &.{},
    spirv_data: ?[]const u32 = null,
};
pub const DoeBindGroupLayout = struct {
    const TYPE_MAGIC = MAGIC_BGL;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    entry_count: u32 = 0,
    entries: ?[]DoeBindGroupLayoutEntry = null,
};
pub const DoeBindGroupLayoutEntry = struct {
    binding: u32 = 0,
    resource_kind: u32 = 0,
    texture_sample_type: u32 = types.WGPUTextureSampleType_Undefined,
    texture_view_dimension: u32 = types.WGPUTextureViewDimension_Undefined,
    texture_multisampled: bool = false,
    binding_array_size: u32 = 0,
};
pub const DoePipelineLayout = struct {
    const TYPE_MAGIC = MAGIC_PIPE_LAYOUT;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    immediate_size: u32 = 0,
    bind_group_layout_count: u32 = 0,
    bind_group_layouts: [MAX_COMPUTE_BIND_GROUPS]?*DoeBindGroupLayout = [_]?*DoeBindGroupLayout{null} ** MAX_COMPUTE_BIND_GROUPS,
};
pub const DoeBindGroup = struct {
    pub const TYPE_MAGIC = MAGIC_BIND_GROUP;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    buffers: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    textures: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    texture_views: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    samplers: [MAX_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_BIND,
    retained_buffers: [MAX_BIND]?*DoeBuffer = [_]?*DoeBuffer{null} ** MAX_BIND,
    retained_texture_views: [MAX_BIND]?*DoeTextureView = [_]?*DoeTextureView{null} ** MAX_BIND,
    retained_samplers: [MAX_BIND]?*DoeSampler = [_]?*DoeSampler{null} ** MAX_BIND,
    retained_external_textures: [MAX_BIND]types.WGPUExternalTexture = [_]types.WGPUExternalTexture{null} ** MAX_BIND,
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
        resolve_target: ?*anyopaque = null,
        depth_target: ?*anyopaque,
        target_view_handle: u64 = 0,
        resolve_target_view_handle: u64 = 0,
        depth_target_view_handle: u64 = 0,
        target_format: u32 = 0,
        depth_stencil_format: u32 = 0,
        sample_count: u32 = 1,
        depth_slice: u32 = 0,
        depth_read_only: bool = false,
        stencil_read_only: bool = false,
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
    ref_count: u32 = 1,
    dev: *DoeDevice,
    cmds: std.ArrayListUnmanaged(RecordedCmd) = .{},
};
pub const DoeComputePass = struct {
    const TYPE_MAGIC = MAGIC_COMPUTE_PASS;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    enc: *DoeCommandEncoder,
    pipeline: ?*DoeComputePipeline = null,
    bind_groups: [4]?*DoeBindGroup = [_]?*DoeBindGroup{null} ** 4,
};
pub const DoeCommandBuffer = struct {
    const TYPE_MAGIC = MAGIC_CMD_BUFFER;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    dev: *DoeDevice,
    cmds: std.ArrayListUnmanaged(RecordedCmd) = .{},
};
pub const DoeTexture = struct {
    const TYPE_MAGIC = MAGIC_TEXTURE;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
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
    ref_count: u32 = 1,
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
    ref_count: u32 = 1,
    backend: BackendKind = .metal,
    mtl: ?*anyopaque = null,
    // Vulkan-only: back-reference to the runtime for vkDestroySampler on release.
    vk_runtime_ref: ?*anyopaque = null,
};
pub const DoeRenderPipeline = struct {
    const TYPE_MAGIC = MAGIC_RENDER_PIPE;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
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
    vertex_spirv_data: ?[]const u32 = null,
    fragment_spirv_data: ?[]const u32 = null,
    vertex_entry_point: ?[]const u8 = null,
    fragment_entry_point: ?[]const u8 = null,
};
pub const DoeRenderPass = struct {
    const TYPE_MAGIC = MAGIC_RENDER_PASS;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    enc: *DoeCommandEncoder,
    pipeline: ?*DoeRenderPipeline = null,
    max_draw_count: u64 = 50_000_000,
    recorded_draw_count: u64 = 0,
    target: ?*anyopaque = null, // MTLTexture for the render target
    resolve_target: ?*anyopaque = null,
    depth_target: ?*anyopaque = null,
    target_view_handle: u64 = 0,
    resolve_target_view_handle: u64 = 0,
    depth_target_view_handle: u64 = 0,
    target_format: u32 = 0,
    depth_stencil_format: u32 = 0,
    sample_count: u32 = 1,
    depth_slice: u32 = 0,
    depth_read_only: bool = false,
    stencil_read_only: bool = false,
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

pub fn object_add_ref(comptime T: type, raw: ?*anyopaque) void {
    const obj = cast(T, raw) orelse return;
    obj.ref_count +|= 1;
}

pub fn object_should_destroy(obj: anytype) bool {
    if (obj.ref_count > 1) {
        obj.ref_count -= 1;
        return false;
    }
    return true;
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

const buffer_ops = @import("doe_buffer_ops_native.zig");
pub const doeNativeDeviceCreateBuffer = buffer_ops.doeNativeDeviceCreateBuffer;
pub const doeNativeBufferRelease = buffer_ops.doeNativeBufferRelease;
pub const doeNativeBufferUnmap = buffer_ops.doeNativeBufferUnmap;
pub const doeNativeBufferGetMapState = buffer_ops.doeNativeBufferGetMapState;
pub const doeNativeBufferMapAsync = buffer_ops.doeNativeBufferMapAsync;
pub const doeNativeBufferGetConstMappedRange = buffer_ops.doeNativeBufferGetConstMappedRange;
pub const doeNativeBufferGetMappedRange = buffer_ops.doeNativeBufferGetMappedRange;

// ============================================================
// Shard re-exports
// ============================================================
const instance_device = @import("doe_instance_device_native.zig");
pub const doeNativeCreateInstance = instance_device.doeNativeCreateInstance;
pub const doeNativeInstanceAddRef = instance_device.doeNativeInstanceAddRef;
pub const doeNativeInstanceRelease = instance_device.doeNativeInstanceRelease;
pub const doeNativeInstanceWaitAny = instance_device.doeNativeInstanceWaitAny;
pub const doeNativeRequestAdapterFlat = instance_device.doeNativeRequestAdapterFlat;
pub const doeNativeInstanceRequestAdapter = instance_device.doeNativeInstanceRequestAdapter;
pub const doeNativeAdapterAddRef = instance_device.doeNativeAdapterAddRef;
pub const doeNativeAdapterRequestDevice = instance_device.doeNativeAdapterRequestDevice;
pub const doeNativeAdapterCreateDevice = instance_device.doeNativeAdapterCreateDevice;
pub const doeNativeAdapterGetInstance = instance_device.doeNativeAdapterGetInstance;
pub const doeNativeAdapterRelease = instance_device.doeNativeAdapterRelease;
pub const doeNativeRequestDeviceFlat = instance_device.doeNativeRequestDeviceFlat;
pub const doeNativeDeviceAddRef = instance_device.doeNativeDeviceAddRef;
pub const doeNativeDeviceRelease = instance_device.doeNativeDeviceRelease;
pub const doeNativeDeviceGetAdapter = instance_device.doeNativeDeviceGetAdapter;
pub const doeNativeDeviceGetQueue = instance_device.doeNativeDeviceGetQueue;
const shader = @import("doe_shader_native.zig");
pub const doeNativeDeviceCreateShaderModule = shader.doeNativeDeviceCreateShaderModule;
pub const doeNativeShaderModuleRelease = shader.doeNativeShaderModuleRelease;
pub const doeNativeDeviceCreateComputePipeline = shader.doeNativeDeviceCreateComputePipeline;
pub const doeNativeComputePipelineRelease = shader.doeNativeComputePipelineRelease;
const bind_group = @import("doe_bind_group_native.zig");
pub const doeNativeDeviceCreateBindGroupLayout = bind_group.doeNativeDeviceCreateBindGroupLayout;
pub const doeNativeBindGroupLayoutRelease = bind_group.doeNativeBindGroupLayoutRelease;
pub const doeNativeDeviceCreateBindGroup = bind_group.doeNativeDeviceCreateBindGroup;
pub const doeNativeBindGroupRelease = bind_group.doeNativeBindGroupRelease;
pub const doeNativeDeviceCreatePipelineLayout = bind_group.doeNativeDeviceCreatePipelineLayout;
pub const doeNativePipelineLayoutRelease = bind_group.doeNativePipelineLayoutRelease;
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
const queue_submit = @import("doe_queue_submit_native.zig");
// Re-exported for callers (e.g. doe_compute_fast.zig) that go through doe_wgpu_native.
pub const flush_pending_work = queue_submit.flush_pending_work;
pub const try_schedule_deferred_copy = queue_submit.try_schedule_deferred_copy;
pub const doeNativeQueueSubmit = queue_submit.doeNativeQueueSubmit;
pub const doeNativeQueueFlush = queue_submit.doeNativeQueueFlush;
pub const doeNativeQueueWriteBuffer = queue_submit.doeNativeQueueWriteBuffer;
pub const doeNativeQueueCopyTextureForBrowser = queue_submit.doeNativeQueueCopyTextureForBrowser;
pub const doeNativeQueueAddRef = queue_submit.doeNativeQueueAddRef;
pub const doeNativeQueueRelease = queue_submit.doeNativeQueueRelease;
pub const doeNativeQueueOnSubmittedWorkDone = queue_submit.doeNativeQueueOnSubmittedWorkDone;
const render = @import("doe_render_native.zig");
pub const doeNativeDeviceCreateTexture = render.doeNativeDeviceCreateTexture;
pub const doeNativeTextureCreateView = render.doeNativeTextureCreateView;
pub const doeNativeTextureDestroy = render.doeNativeTextureDestroy;
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
pub const doeNativeRenderPassDrawIndirect = render.doeNativeRenderPassDrawIndirect;
pub const doeNativeRenderPassDrawIndexedIndirect = render.doeNativeRenderPassDrawIndexedIndirect;
pub const doeNativeRenderPassEnd = render.doeNativeRenderPassEnd;
pub const doeNativeRenderPassRelease = render.doeNativeRenderPassRelease;
const compute_ext = @import("doe_compute_ext_native.zig");
const bundle = @import("doe_bundle_native.zig");
pub const doeNativeComputePassSetPipeline = compute_ext.doeNativeComputePassSetPipeline;
pub const doeNativeComputePassSetBindGroup = compute_ext.doeNativeComputePassSetBindGroup;
pub const doeNativeComputePassDispatch = compute_ext.doeNativeComputePassDispatch;
pub const doeNativeComputePassEnd = compute_ext.doeNativeComputePassEnd;
pub const doeNativeComputePassRelease = compute_ext.doeNativeComputePassRelease;
pub const doeNativeComputePipelineGetBindGroupLayout = compute_ext.doeNativeComputePipelineGetBindGroupLayout;
pub const doeNativeRenderPipelineGetBindGroupLayout = bundle.doeNativeRenderPipelineGetBindGroupLayout;
pub const doeNativeDeviceCreateRenderBundleEncoder = bundle.doeNativeDeviceCreateRenderBundleEncoder;
pub const doeNativeRenderBundleEncoderFinish = bundle.doeNativeRenderBundleEncoderFinish;
pub const doeNativeRenderBundleRelease = bundle.doeNativeRenderBundleRelease;
pub const doeNativeRenderBundleEncoderRelease = bundle.doeNativeRenderBundleEncoderRelease;
pub const doeNativeRenderBundleEncoderSetPipeline = bundle.doeNativeRenderBundleEncoderSetPipeline;
pub const doeNativeRenderBundleEncoderSetBindGroup = bundle.doeNativeRenderBundleEncoderSetBindGroup;
pub const doeNativeRenderBundleEncoderSetVertexBuffer = bundle.doeNativeRenderBundleEncoderSetVertexBuffer;
pub const doeNativeRenderBundleEncoderSetIndexBuffer = bundle.doeNativeRenderBundleEncoderSetIndexBuffer;
pub const doeNativeRenderBundleEncoderDraw = bundle.doeNativeRenderBundleEncoderDraw;
pub const doeNativeRenderBundleEncoderDrawIndexed = bundle.doeNativeRenderBundleEncoderDrawIndexed;
pub const doeNativeRenderBundleEncoderDrawIndirect = bundle.doeNativeRenderBundleEncoderDrawIndirect;
pub const doeNativeRenderBundleEncoderDrawIndexedIndirect = bundle.doeNativeRenderBundleEncoderDrawIndexedIndirect;
pub const doeNativeRenderBundleEncoderInsertDebugMarker = bundle.doeNativeRenderBundleEncoderInsertDebugMarker;
pub const doeNativeRenderBundleEncoderPushDebugGroup = bundle.doeNativeRenderBundleEncoderPushDebugGroup;
pub const doeNativeRenderBundleEncoderPopDebugGroup = bundle.doeNativeRenderBundleEncoderPopDebugGroup;
pub const doeNativeRenderPassExecuteBundles = bundle.doeNativeRenderPassExecuteBundles;
pub const doeNativeComputePassDispatchIndirect = compute_ext.doeNativeComputePassDispatchIndirect;
pub const doeNativeComputePassInsertDebugMarker = compute_ext.doeNativeComputePassInsertDebugMarker;
pub const doeNativeComputePassPushDebugGroup = compute_ext.doeNativeComputePassPushDebugGroup;
pub const doeNativeComputePassPopDebugGroup = compute_ext.doeNativeComputePassPopDebugGroup;
const caps = @import("doe_device_caps.zig");
pub const doeNativeAdapterHasFeature = caps.doeNativeAdapterHasFeature;
pub const doeNativeDeviceHasFeature = caps.doeNativeDeviceHasFeature;
pub const doeNativeDeviceGetLimits = caps.doeNativeDeviceGetLimits;
pub const doeNativeAdapterGetLimits = caps.doeNativeAdapterGetLimits;
const query = @import("doe_query_native.zig");
pub const doeNativeDeviceCreateQuerySet = query.doeNativeDeviceCreateQuerySet;
pub const doeNativeCommandEncoderWriteTimestamp = query.doeNativeCommandEncoderWriteTimestamp;
pub const doeNativeCommandEncoderResolveQuerySet = query.doeNativeCommandEncoderResolveQuerySet;
pub const doeNativeQuerySetDestroy = query.doeNativeQuerySetDestroy;
pub const doeNativeQuerySetRelease = query.doeNativeQuerySetRelease;
pub const doeNativeQuerySetGetCount = query.doeNativeQuerySetGetCount;
pub const doeNativeQuerySetGetType = query.doeNativeQuerySetGetType;
pub const doeNativeRenderPassBeginOcclusionQuery = query.doeNativeRenderPassBeginOcclusionQuery;
pub const doeNativeRenderPassEndOcclusionQuery = query.doeNativeRenderPassEndOcclusionQuery;
const canvas_event = @import("doe_canvas_event_native.zig");
pub const doeNativeAdapterGetPreferredCanvasFormat = canvas_event.doeNativeAdapterGetPreferredCanvasFormat;
pub const doeNativeDeviceAddEventListener = canvas_event.doeNativeDeviceAddEventListener;
pub const doeNativeDeviceRemoveEventListener = canvas_event.doeNativeDeviceRemoveEventListener;
const error_scope_native = @import("doe_error_scope_native.zig");
pub const doeNativeDevicePushErrorScope = error_scope_native.doeNativeDevicePushErrorScope;
pub const doeNativeDevicePopErrorScope = error_scope_native.doeNativeDevicePopErrorScope;
pub const doeNativeDevicePopErrorScopeFlat = error_scope_native.doeNativeDevicePopErrorScopeFlat;
pub const doeNativeDeviceSetUncapturedErrorCallback = error_scope_native.doeNativeDeviceSetUncapturedErrorCallback;
pub const doeNativeDeviceInjectError = error_scope_native.doeNativeDeviceInjectError;
const cache_adapter = @import("doe_cache_adapter_native.zig");

const immediates_external = @import("doe_immediates_external_native.zig");
pub const doeNativeBindingCommandsSetImmediates = immediates_external.doeNativeBindingCommandsSetImmediates;
pub const doeNativeComputePassSetImmediates = immediates_external.doeNativeComputePassSetImmediates;
pub const doeNativeRenderPassSetImmediates = immediates_external.doeNativeRenderPassSetImmediates;
pub const doeNativeRenderBundleEncoderSetImmediates = immediates_external.doeNativeRenderBundleEncoderSetImmediates;
pub const doeNativeQueueCopyExternalImageToTexture = queue_submit.doeNativeQueueCopyExternalImageToTexture;
pub const doeNativeQueueCopyExternalTextureForBrowser = queue_submit.doeNativeQueueCopyExternalTextureForBrowser;
const external_texture_native = @import("doe_external_texture_native.zig");
pub const doeNativeDeviceImportExternalTexture = external_texture_native.doeNativeDeviceImportExternalTexture;
pub const doeNativeDeviceCreateExternalTexture = external_texture_native.doeNativeDeviceCreateExternalTexture;
pub const doeNativeExternalTextureAddRef = external_texture_native.doeNativeExternalTextureAddRef;
pub const doeNativeExternalTextureRelease = external_texture_native.doeNativeExternalTextureRelease;
pub const doeNativeExternalTextureDestroy = external_texture_native.doeNativeExternalTextureDestroy;
pub const doeNativeExternalTextureExpire = external_texture_native.doeNativeExternalTextureExpire;
pub const doeNativeExternalTextureRefresh = external_texture_native.doeNativeExternalTextureRefresh;
pub const doeNativeExternalTextureSetLabel = external_texture_native.doeNativeExternalTextureSetLabel;
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
const adapter_info = @import("doe_adapter_info_native.zig");
pub const doeNativeAdapterGetInfo = adapter_info.doeNativeAdapterGetInfo;
pub const doeNativeAdapterFreeInfo = adapter_info.doeNativeAdapterFreeInfo;
const shader_compilation_info = @import("doe_shader_compilation_info_native.zig");
pub const doeNativeShaderModuleGetCompilationInfo = shader_compilation_info.doeNativeShaderModuleGetCompilationInfo;
const command_texture = @import("doe_command_texture_native.zig");
pub const doeNativeCommandEncoderClearBuffer = command_texture.doeNativeCommandEncoderClearBuffer;
pub const doeNativeCommandEncoderCopyTextureToTexture = command_texture.doeNativeCommandEncoderCopyTextureToTexture;
pub const doeNativeQueueWriteTexture = command_texture.doeNativeQueueWriteTexture;
const surface_native = @import("doe_surface_native.zig");
pub const doeNativeInstanceCreateSurface = surface_native.doeNativeInstanceCreateSurface;
pub const doeNativeSurfaceSetXcbHandle = surface_native.doeNativeSurfaceSetXcbHandle;
pub const doeNativeSurfaceSetWaylandHandle = surface_native.doeNativeSurfaceSetWaylandHandle;
pub const doeNativeSurfaceConfigure = surface_native.doeNativeSurfaceConfigure;
pub const doeNativeSurfaceGetCurrentTexture = surface_native.doeNativeSurfaceGetCurrentTexture;
pub const doeNativeSurfacePresent = surface_native.doeNativeSurfacePresent;
pub const doeNativeSurfaceUnconfigure = surface_native.doeNativeSurfaceUnconfigure;
pub const doeNativeSurfaceRelease = surface_native.doeNativeSurfaceRelease;
pub const doeNativeSurfaceGetCapabilities = surface_native.doeNativeSurfaceGetCapabilities;
pub const doeNativeSurfaceCapabilitiesFreeMembers = surface_native.doeNativeSurfaceCapabilitiesFreeMembers;
pub const doeAbiBridgeInstanceCreateSurface = surface_native.doeAbiBridgeInstanceCreateSurface;
pub const doeAbiBridgeSurfaceConfigure = surface_native.doeAbiBridgeSurfaceConfigure;
pub const doeAbiBridgeSurfaceGetCurrentTexture = surface_native.doeAbiBridgeSurfaceGetCurrentTexture;
pub const doeAbiBridgeSurfacePresent = surface_native.doeAbiBridgeSurfacePresent;
pub const DoeSurface = surface_native.DoeSurface;
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
    _ = @import("doe_bundle_native.zig");
    _ = label_store;
    _ = buffer_ops;
}

// Instance process events — drain deferred work-done callbacks.
// Chromium expects onSubmittedWorkDone callbacks to fire here, not inline
// during the queueOnSubmittedWorkDone C proc call.
pub export fn doeNativeInstanceProcessEvents(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
    @import("doe_queue_submit_native.zig").drain_global_work_done();
}
