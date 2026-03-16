pub const WGPUFlags = u64;
pub const WGPUSType = u32;
pub const WGPUTextureFormat = u32;

pub const WGPUTextureUsage_None: WGPUFlags = 0;
pub const WGPUTextureUsage_CopySrc: WGPUFlags = 0x0000000000000001;
pub const WGPUTextureUsage_CopyDst: WGPUFlags = 0x0000000000000002;
pub const WGPUTextureUsage_TextureBinding: WGPUFlags = 0x0000000000000004;
pub const WGPUTextureUsage_StorageBinding: WGPUFlags = 0x0000000000000008;
pub const WGPUTextureUsage_RenderAttachment: WGPUFlags = 0x0000000000000010;

pub const WGPUCopyStrideUndefined: u32 = 0xFFFFFFFF;
pub const WGPUWholeSize: u64 = 0xFFFFFFFFFFFFFFFF;

pub const WGPUTextureDimension_Undefined: u32 = 0;
pub const WGPUTextureDimension_1D: u32 = 1;
pub const WGPUTextureDimension_2D: u32 = 2;
pub const WGPUTextureDimension_3D: u32 = 3;

pub const WGPUTextureViewDimension_Undefined: u32 = 0;
pub const WGPUTextureViewDimension_1D: u32 = 1;
pub const WGPUTextureViewDimension_2D: u32 = 2;
pub const WGPUTextureViewDimension_2DArray: u32 = 3;
pub const WGPUTextureViewDimension_Cube: u32 = 4;
pub const WGPUTextureViewDimension_CubeArray: u32 = 5;
pub const WGPUTextureViewDimension_3D: u32 = 6;

pub const WGPUTextureAspect_Undefined: u32 = 0;
pub const WGPUTextureAspect_All: u32 = 1;
pub const WGPUTextureAspect_StencilOnly: u32 = 2;
pub const WGPUTextureAspect_DepthOnly: u32 = 3;

pub const WGPUTextureFormat_Undefined: WGPUTextureFormat = 0;
pub const WGPUTextureFormat_R8Unorm: WGPUTextureFormat = 0x00000001;
pub const WGPUTextureFormat_R8Snorm: WGPUTextureFormat = 0x00000002;
pub const WGPUTextureFormat_R8Uint: WGPUTextureFormat = 0x00000003;
pub const WGPUTextureFormat_R8Sint: WGPUTextureFormat = 0x00000004;
pub const WGPUTextureFormat_R16Unorm: WGPUTextureFormat = 0x00000005;
pub const WGPUTextureFormat_R16Snorm: WGPUTextureFormat = 0x00000006;
pub const WGPUTextureFormat_R16Uint: WGPUTextureFormat = 0x00000007;
pub const WGPUTextureFormat_R16Sint: WGPUTextureFormat = 0x00000008;
pub const WGPUTextureFormat_R16Float: WGPUTextureFormat = 0x00000009;
pub const WGPUTextureFormat_RG8Unorm: WGPUTextureFormat = 0x0000000A;
pub const WGPUTextureFormat_RG8Snorm: WGPUTextureFormat = 0x0000000B;
pub const WGPUTextureFormat_RG8Uint: WGPUTextureFormat = 0x0000000C;
pub const WGPUTextureFormat_RG8Sint: WGPUTextureFormat = 0x0000000D;
pub const WGPUTextureFormat_R32Float: WGPUTextureFormat = 0x0000000E;
pub const WGPUTextureFormat_R32Uint: WGPUTextureFormat = 0x0000000F;
pub const WGPUTextureFormat_R32Sint: WGPUTextureFormat = 0x00000010;
pub const WGPUTextureFormat_RG16Unorm: WGPUTextureFormat = 0x00000011;
pub const WGPUTextureFormat_RG16Snorm: WGPUTextureFormat = 0x00000012;
pub const WGPUTextureFormat_RG16Uint: WGPUTextureFormat = 0x00000013;
pub const WGPUTextureFormat_RG16Sint: WGPUTextureFormat = 0x00000014;
pub const WGPUTextureFormat_RG16Float: WGPUTextureFormat = 0x00000015;
pub const WGPUTextureFormat_RGBA8Unorm: WGPUTextureFormat = 0x00000016;
pub const WGPUTextureFormat_RGBA8UnormSrgb: WGPUTextureFormat = 0x00000017;
pub const WGPUTextureFormat_RGBA8Snorm: WGPUTextureFormat = 0x00000018;
pub const WGPUTextureFormat_RGBA8Uint: WGPUTextureFormat = 0x00000019;
pub const WGPUTextureFormat_RGBA8Sint: WGPUTextureFormat = 0x0000001A;
pub const WGPUTextureFormat_BGRA8Unorm: WGPUTextureFormat = 0x0000001B;
pub const WGPUTextureFormat_BGRA8UnormSrgb: WGPUTextureFormat = 0x0000001C;
pub const WGPUTextureFormat_RGB10A2Uint: WGPUTextureFormat = 0x0000001D;
pub const WGPUTextureFormat_RGB10A2Unorm: WGPUTextureFormat = 0x0000001E;
pub const WGPUTextureFormat_RG11B10Ufloat: WGPUTextureFormat = 0x0000001F;
pub const WGPUTextureFormat_RGB9E5Ufloat: WGPUTextureFormat = 0x00000020;
pub const WGPUTextureFormat_RG32Float: WGPUTextureFormat = 0x00000021;
pub const WGPUTextureFormat_RG32Uint: WGPUTextureFormat = 0x00000022;
pub const WGPUTextureFormat_RG32Sint: WGPUTextureFormat = 0x00000023;
pub const WGPUTextureFormat_RGBA16Uint: WGPUTextureFormat = 0x00000024;
pub const WGPUTextureFormat_RGBA16Sint: WGPUTextureFormat = 0x00000025;
pub const WGPUTextureFormat_RGBA16Float: WGPUTextureFormat = 0x00000026;
pub const WGPUTextureFormat_RGBA32Float: WGPUTextureFormat = 0x00000027;
pub const WGPUTextureFormat_RGBA32Uint: WGPUTextureFormat = 0x00000028;
pub const WGPUTextureFormat_RGBA32Sint: WGPUTextureFormat = 0x00000029;
pub const WGPUTextureFormat_Stencil8: WGPUTextureFormat = 0x0000002C;
pub const WGPUTextureFormat_Depth16Unorm: WGPUTextureFormat = 0x0000002D;
pub const WGPUTextureFormat_Depth24Plus: WGPUTextureFormat = 0x0000002E;
pub const WGPUTextureFormat_Depth24PlusStencil8: WGPUTextureFormat = 0x0000002F;
pub const WGPUTextureFormat_Depth32Float: WGPUTextureFormat = 0x00000030;
pub const WGPUTextureFormat_Depth32FloatStencil8: WGPUTextureFormat = 0x00000031;

// ASTC compressed texture formats (texture-compression-astc feature)
pub const WGPUTextureFormat_ASTC4x4Unorm: WGPUTextureFormat = 0x0000004A;
pub const WGPUTextureFormat_ASTC4x4UnormSrgb: WGPUTextureFormat = 0x0000004B;
pub const WGPUTextureFormat_ASTC5x4Unorm: WGPUTextureFormat = 0x0000004C;
pub const WGPUTextureFormat_ASTC5x4UnormSrgb: WGPUTextureFormat = 0x0000004D;
pub const WGPUTextureFormat_ASTC5x5Unorm: WGPUTextureFormat = 0x0000004E;
pub const WGPUTextureFormat_ASTC5x5UnormSrgb: WGPUTextureFormat = 0x0000004F;
pub const WGPUTextureFormat_ASTC6x5Unorm: WGPUTextureFormat = 0x00000050;
pub const WGPUTextureFormat_ASTC6x5UnormSrgb: WGPUTextureFormat = 0x00000051;
pub const WGPUTextureFormat_ASTC6x6Unorm: WGPUTextureFormat = 0x00000052;
pub const WGPUTextureFormat_ASTC6x6UnormSrgb: WGPUTextureFormat = 0x00000053;
pub const WGPUTextureFormat_ASTC8x5Unorm: WGPUTextureFormat = 0x00000054;
pub const WGPUTextureFormat_ASTC8x5UnormSrgb: WGPUTextureFormat = 0x00000055;
pub const WGPUTextureFormat_ASTC8x6Unorm: WGPUTextureFormat = 0x00000056;
pub const WGPUTextureFormat_ASTC8x6UnormSrgb: WGPUTextureFormat = 0x00000057;
pub const WGPUTextureFormat_ASTC8x8Unorm: WGPUTextureFormat = 0x00000058;
pub const WGPUTextureFormat_ASTC8x8UnormSrgb: WGPUTextureFormat = 0x00000059;
pub const WGPUTextureFormat_ASTC10x5Unorm: WGPUTextureFormat = 0x0000005A;
pub const WGPUTextureFormat_ASTC10x5UnormSrgb: WGPUTextureFormat = 0x0000005B;
pub const WGPUTextureFormat_ASTC10x6Unorm: WGPUTextureFormat = 0x0000005C;
pub const WGPUTextureFormat_ASTC10x6UnormSrgb: WGPUTextureFormat = 0x0000005D;
pub const WGPUTextureFormat_ASTC10x8Unorm: WGPUTextureFormat = 0x0000005E;
pub const WGPUTextureFormat_ASTC10x8UnormSrgb: WGPUTextureFormat = 0x0000005F;
pub const WGPUTextureFormat_ASTC10x10Unorm: WGPUTextureFormat = 0x00000060;
pub const WGPUTextureFormat_ASTC10x10UnormSrgb: WGPUTextureFormat = 0x00000061;
pub const WGPUTextureFormat_ASTC12x10Unorm: WGPUTextureFormat = 0x00000062;
pub const WGPUTextureFormat_ASTC12x10UnormSrgb: WGPUTextureFormat = 0x00000063;
pub const WGPUTextureFormat_ASTC12x12Unorm: WGPUTextureFormat = 0x00000064;
pub const WGPUTextureFormat_ASTC12x12UnormSrgb: WGPUTextureFormat = 0x00000065;

// ASTC format range for validation
pub const ASTC_FORMAT_FIRST: WGPUTextureFormat = WGPUTextureFormat_ASTC4x4Unorm;
pub const ASTC_FORMAT_LAST: WGPUTextureFormat = WGPUTextureFormat_ASTC12x12UnormSrgb;

pub fn isASTCFormat(format: WGPUTextureFormat) bool {
    return format >= ASTC_FORMAT_FIRST and format <= ASTC_FORMAT_LAST;
}

pub const WGPUShaderStage_None: WGPUFlags = 0x0000000000000000;
pub const WGPUShaderStage_Vertex: WGPUFlags = 0x0000000000000001;
pub const WGPUShaderStage_Fragment: WGPUFlags = 0x0000000000000002;
pub const WGPUShaderStage_Compute: WGPUFlags = 0x0000000000000004;

pub const WGPUBufferBindingType_Undefined: u32 = 0x00000001;
pub const WGPUBufferBindingType_Uniform: u32 = 0x00000002;
pub const WGPUBufferBindingType_Storage: u32 = 0x00000003;
pub const WGPUBufferBindingType_ReadOnlyStorage: u32 = 0x00000004;

pub const WGPUTextureSampleType_Undefined: u32 = 0x00000001;
pub const WGPUTextureSampleType_Float: u32 = 0x00000002;
pub const WGPUTextureSampleType_UnfilterableFloat: u32 = 0x00000003;
pub const WGPUTextureSampleType_Depth: u32 = 0x00000004;
pub const WGPUTextureSampleType_Sint: u32 = 0x00000005;
pub const WGPUTextureSampleType_Uint: u32 = 0x00000006;

pub const WGPUStorageTextureAccess_Undefined: u32 = 0x00000001;
pub const WGPUStorageTextureAccess_WriteOnly: u32 = 0x00000002;
pub const WGPUStorageTextureAccess_ReadOnly: u32 = 0x00000003;
pub const WGPUStorageTextureAccess_ReadWrite: u32 = 0x00000004;

pub const CopyResourceKind = enum(u8) {
    buffer,
    texture,
};

pub const CopyDirection = enum(u8) {
    buffer_to_buffer,
    buffer_to_texture,
    texture_to_buffer,
    texture_to_texture,
};

pub const CopyTextureResource = struct {
    handle: u64,
    kind: CopyResourceKind = .buffer,
    width: u32 = 1,
    height: u32 = 1,
    depth_or_array_layers: u32 = 1,
    format: WGPUTextureFormat = WGPUTextureFormat_Undefined,
    usage: WGPUFlags = 0,
    dimension: u32 = WGPUTextureDimension_Undefined,
    view_dimension: u32 = WGPUTextureViewDimension_Undefined,
    mip_level: u32 = 0,
    sample_count: u32 = 1,
    aspect: u32 = WGPUTextureAspect_Undefined,
    bytes_per_row: u32 = 0,
    rows_per_image: u32 = 0,
    offset: u64 = 0,
};

pub const UploadCommand = struct {
    bytes: usize,
    align_bytes: u32,
};

pub const CopyCommand = struct {
    direction: CopyDirection,
    src: CopyTextureResource,
    dst: CopyTextureResource,
    bytes: usize,
    uses_temporary_buffer: bool = false,
    temporary_buffer_alignment: u32 = 0,
};

pub const BarrierCommand = struct {
    dependency_count: u32,
};

pub const DispatchCommand = struct {
    x: u32,
    y: u32,
    z: u32,
};

pub const DispatchIndirectCommand = DispatchCommand;

pub const KernelBindingResourceKind = enum(u8) {
    buffer,
    texture,
    storage_texture,
};

pub const KernelBinding = struct {
    binding: u32,
    group: u32 = 0,
    resource_kind: KernelBindingResourceKind,
    resource_handle: u64,
    visibility: WGPUFlags = WGPUShaderStage_Compute,
    buffer_offset: u64 = 0,
    buffer_size: u64 = WGPUWholeSize,
    buffer_type: u32 = WGPUBufferBindingType_Undefined,
    texture_sample_type: u32 = WGPUTextureSampleType_Undefined,
    texture_view_dimension: u32 = WGPUTextureViewDimension_Undefined,
    storage_texture_access: u32 = WGPUStorageTextureAccess_Undefined,
    texture_aspect: u32 = WGPUTextureAspect_Undefined,
    texture_format: WGPUTextureFormat = WGPUTextureFormat_Undefined,
    texture_multisampled: bool = false,
};

pub const KernelDispatchCommand = struct {
    kernel: []const u8,
    entry_point: ?[]const u8 = null,
    x: u32,
    y: u32,
    z: u32,
    repeat: u32 = 1,
    warmup_dispatch_count: u32 = 0,
    initialize_buffers_on_create: bool = false,
    bindings: ?[]const KernelBinding = null,
};

pub const DEFAULT_RENDER_TARGET_HANDLE: u64 = 0xFFFF_FFFF_FFFF_FFFE;
pub const DEFAULT_RENDER_TARGET_WIDTH: u32 = 64;
pub const DEFAULT_RENDER_TARGET_HEIGHT: u32 = 64;
pub const DEFAULT_RENDER_TARGET_FORMAT: WGPUTextureFormat = WGPUTextureFormat_RGBA8Unorm;

pub const RenderDrawPipelineMode = enum {
    static,
    redundant,
};

pub const RenderDrawBindGroupMode = enum {
    no_change,
    redundant,
};

pub const RenderDrawEncodeMode = enum {
    render_pass,
    render_bundle,
};

pub const RenderIndexFormat = enum {
    uint16,
    uint32,
};

pub const RenderIndexData = union(RenderIndexFormat) {
    uint16: []const u16,
    uint32: []const u32,
};

pub const RenderDrawCommand = struct {
    draw_count: u32,
    vertex_count: u32 = 3,
    instance_count: u32 = 1,
    first_vertex: u32 = 0,
    first_instance: u32 = 0,
    index_count: ?u32 = null,
    first_index: u32 = 0,
    base_vertex: i32 = 0,
    index_data: ?RenderIndexData = null,
    target_handle: u64 = DEFAULT_RENDER_TARGET_HANDLE,
    target_width: u32 = DEFAULT_RENDER_TARGET_WIDTH,
    target_height: u32 = DEFAULT_RENDER_TARGET_HEIGHT,
    target_format: WGPUTextureFormat = DEFAULT_RENDER_TARGET_FORMAT,
    uses_temporary_render_texture: bool = false,
    temporary_render_texture_min_mip_level: u32 = 0,
    pipeline_mode: RenderDrawPipelineMode = .static,
    bind_group_mode: RenderDrawBindGroupMode = .no_change,
    encode_mode: RenderDrawEncodeMode = .render_bundle,
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
    bind_group_dynamic_offsets: ?[]const u32 = null,
};

pub const DrawIndirectCommand = RenderDrawCommand;
pub const DrawIndexedIndirectCommand = RenderDrawCommand;
pub const RenderPassCommand = RenderDrawCommand;

pub const SamplerCreateCommand = struct {
    handle: u64,
    address_mode_u: u32 = 2,
    address_mode_v: u32 = 2,
    address_mode_w: u32 = 2,
    mag_filter: u32 = 1,
    min_filter: u32 = 1,
    mipmap_filter: u32 = 1,
    lod_min_clamp: f32 = 0,
    lod_max_clamp: f32 = 32,
    compare: u32 = 0,
    max_anisotropy: u16 = 1,
};

pub const SamplerDestroyCommand = struct {
    handle: u64,
};

pub const TextureWriteCommand = struct {
    texture: CopyTextureResource,
    data: []const u8,
};

pub const TextureQueryCommand = struct {
    handle: u64,
    expected_width: ?u32 = null,
    expected_height: ?u32 = null,
    expected_depth_or_array_layers: ?u32 = null,
    expected_format: ?WGPUTextureFormat = null,
    expected_dimension: ?u32 = null,
    expected_view_dimension: ?u32 = null,
    expected_sample_count: ?u32 = null,
    expected_usage: ?WGPUFlags = null,
};

pub const TextureDestroyCommand = struct {
    handle: u64,
};

pub const SurfaceCreateCommand = struct {
    handle: u64,
};

pub const SurfaceCapabilitiesCommand = struct {
    handle: u64,
};

pub const SurfaceConfigureCommand = struct {
    handle: u64,
    width: u32,
    height: u32,
    format: WGPUTextureFormat = WGPUTextureFormat_RGBA8Unorm,
    usage: WGPUFlags = WGPUTextureUsage_RenderAttachment,
    alpha_mode: u32 = 0x00000001,
    present_mode: u32 = 0x00000002,
    desired_maximum_frame_latency: u32 = 2,
};

pub const SurfaceAcquireCommand = struct {
    handle: u64,
};

pub const SurfacePresentCommand = struct {
    handle: u64,
};

pub const SurfaceUnconfigureCommand = struct {
    handle: u64,
};

pub const SurfaceReleaseCommand = struct {
    handle: u64,
};

pub const AsyncDiagnosticsMode = enum {
    pipeline_async,
    capability_introspection,
    resource_table_immediates,
    lifecycle_refcount,
    pixel_local_storage,
    full,
};

pub const AsyncDiagnosticsFeaturePolicy = enum {
    strict,
    emulate_when_unavailable,
};

pub const AsyncDiagnosticsCommand = struct {
    target_format: WGPUTextureFormat = WGPUTextureFormat_RGBA8Unorm,
    mode: AsyncDiagnosticsMode = .pipeline_async,
    iterations: u32 = 1,
    feature_policy: AsyncDiagnosticsFeaturePolicy = .strict,
};

pub const MapAsyncMode = enum {
    read,
    write,
};

pub const MapAsyncCommand = struct {
    bytes: usize,
    mode: MapAsyncMode = .write,
};
