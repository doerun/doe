const std = @import("std");
pub const CoreCommandKind = @import("core/command_partition.zig").CommandKind;
pub const FullCommandKind = @import("full/command_partition.zig").CommandKind;

pub const SchemaVersion = u8;
pub const CURRENT_SCHEMA_VERSION: SchemaVersion = 2;

pub const Api = enum(u8) {
    vulkan,
    metal,
    d3d12,
    webgpu,
};

pub const Scope = enum(u8) {
    alignment,
    barrier,
    layout,
    driver_toggle,
    memory,
};

pub const SafetyClass = enum(u8) {
    low,
    moderate,
    high,
    critical,
};

pub const VerificationMode = enum(u8) {
    guard_only,
    lean_preferred,
    lean_required,
};

pub const ProofLevel = enum(u8) {
    proven,
    guarded,
    rejected,
};

pub const CommandKind = enum(u8) {
    upload,
    copy_buffer_to_texture,
    barrier,
    dispatch,
    dispatch_indirect,
    kernel_dispatch,
    render_draw,
    draw_indirect,
    draw_indexed_indirect,
    render_pass,
    sampler_create,
    sampler_destroy,
    texture_write,
    texture_query,
    texture_destroy,
    surface_create,
    surface_capabilities,
    surface_configure,
    surface_acquire,
    surface_present,
    surface_unconfigure,
    surface_release,
    async_diagnostics,
    map_async,
};

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
pub const WGPUTextureFormat_Depth16Unorm: WGPUTextureFormat = 0x0000002D;
pub const WGPUTextureFormat_Depth24Plus: WGPUTextureFormat = 0x0000002E;
pub const WGPUTextureFormat_Depth24PlusStencil8: WGPUTextureFormat = 0x0000002F;
pub const WGPUTextureFormat_Depth32Float: WGPUTextureFormat = 0x00000030;
pub const WGPUTextureFormat_Depth32FloatStencil8: WGPUTextureFormat = 0x00000031;

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

pub const Command = union(CommandKind) {
    upload: UploadCommand,
    copy_buffer_to_texture: CopyCommand,
    barrier: BarrierCommand,
    dispatch: DispatchCommand,
    dispatch_indirect: DispatchIndirectCommand,
    kernel_dispatch: KernelDispatchCommand,
    render_draw: RenderDrawCommand,
    draw_indirect: DrawIndirectCommand,
    draw_indexed_indirect: DrawIndexedIndirectCommand,
    render_pass: RenderPassCommand,
    sampler_create: SamplerCreateCommand,
    sampler_destroy: SamplerDestroyCommand,
    texture_write: TextureWriteCommand,
    texture_query: TextureQueryCommand,
    texture_destroy: TextureDestroyCommand,
    surface_create: SurfaceCreateCommand,
    surface_capabilities: SurfaceCapabilitiesCommand,
    surface_configure: SurfaceConfigureCommand,
    surface_acquire: SurfaceAcquireCommand,
    surface_present: SurfacePresentCommand,
    surface_unconfigure: SurfaceUnconfigureCommand,
    surface_release: SurfaceReleaseCommand,
    async_diagnostics: AsyncDiagnosticsCommand,
    map_async: MapAsyncCommand,
};

pub const CoreCommand = union(CoreCommandKind) {
    upload: UploadCommand,
    copy_buffer_to_texture: CopyCommand,
    barrier: BarrierCommand,
    dispatch: DispatchCommand,
    dispatch_indirect: DispatchIndirectCommand,
    kernel_dispatch: KernelDispatchCommand,
    texture_write: TextureWriteCommand,
    texture_query: TextureQueryCommand,
    texture_destroy: TextureDestroyCommand,
    map_async: MapAsyncCommand,
};

pub const FullCommand = union(FullCommandKind) {
    render_draw: RenderDrawCommand,
    draw_indirect: DrawIndirectCommand,
    draw_indexed_indirect: DrawIndexedIndirectCommand,
    render_pass: RenderPassCommand,
    sampler_create: SamplerCreateCommand,
    sampler_destroy: SamplerDestroyCommand,
    surface_create: SurfaceCreateCommand,
    surface_capabilities: SurfaceCapabilitiesCommand,
    surface_configure: SurfaceConfigureCommand,
    surface_acquire: SurfaceAcquireCommand,
    surface_present: SurfacePresentCommand,
    surface_unconfigure: SurfaceUnconfigureCommand,
    surface_release: SurfaceReleaseCommand,
    async_diagnostics: AsyncDiagnosticsCommand,
};

pub const UseTemporaryBufferAction = struct {
    alignment_bytes: u32,
};

pub const UseTemporaryRenderTextureAction = struct {
    min_mip_level: u32,
};

pub const ToggleAction = struct {
    toggle_name: []const u8,
};

pub const QuirkAction = union(enum) {
    use_temporary_buffer: UseTemporaryBufferAction,
    use_temporary_render_texture: UseTemporaryRenderTextureAction,
    toggle: ToggleAction,
    no_op: void,
};

pub const MatchSpec = struct {
    vendor: []const u8,
    api: Api,
    device_family: ?[]const u8 = null,
    driver_range: ?[]const u8 = null,
};

pub const Provenance = struct {
    source_repo: []const u8,
    source_path: []const u8,
    source_commit: []const u8,
    observed_at: []const u8,
};

pub const Quirk = struct {
    schema_version: SchemaVersion,
    quirk_id: []const u8,
    scope: Scope,
    match_spec: MatchSpec,
    action: QuirkAction,
    safety_class: SafetyClass,
    verification_mode: VerificationMode,
    proof_level: ProofLevel,
    provenance: Provenance,
    priority: u32 = 0,
};

pub const DeviceProfile = struct {
    vendor: []const u8,
    api: Api,
    device_family: ?[]const u8 = null,
    driver_version: SemVer,
};

pub const SemVer = struct {
    major: u32,
    minor: u32,
    patch: u32,

    pub fn parse(text: []const u8) !SemVer {
        var major: u32 = 0;
        var minor: u32 = 0;
        var patch: u32 = 0;
        var numbers_seen: u32 = 0;

        var it = std.mem.splitScalar(u8, text, '.');
        while (it.next()) |part| {
            if (part.len == 0) return error.InvalidVersion;
            const value = std.fmt.parseInt(u32, part, 10) catch return error.InvalidVersion;
            switch (numbers_seen) {
                0 => major = value,
                1 => minor = value,
                2 => patch = value,
                else => return error.InvalidVersion,
            }
            numbers_seen += 1;
        }

        return SemVer{ .major = major, .minor = minor, .patch = patch };
    }

    pub fn cmp(self: SemVer, other: SemVer) std.math.Order {
        if (self.major > other.major) return .gt;
        if (self.major < other.major) return .lt;
        if (self.minor > other.minor) return .gt;
        if (self.minor < other.minor) return .lt;
        if (self.patch > other.patch) return .gt;
        if (self.patch < other.patch) return .lt;
        return .eq;
    }

    pub fn equals(self: SemVer, other: SemVer) bool {
        return self.cmp(other) == .eq;
    }

    pub fn ge(self: SemVer, other: SemVer) bool {
        return self.cmp(other) != .lt;
    }

    pub fn gt(self: SemVer, other: SemVer) bool {
        return self.cmp(other) == .gt;
    }

    pub fn lt(self: SemVer, other: SemVer) bool {
        return self.cmp(other) == .lt;
    }
};

pub fn parse_api(raw: []const u8) !Api {
    if (std.ascii.eqlIgnoreCase(raw, "vulkan")) return .vulkan;
    if (std.ascii.eqlIgnoreCase(raw, "metal")) return .metal;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12")) return .d3d12;
    if (std.ascii.eqlIgnoreCase(raw, "webgpu")) return .webgpu;
    return error.InvalidApi;
}

pub fn parse_scope(raw: []const u8) !Scope {
    if (std.ascii.eqlIgnoreCase(raw, "alignment")) return .alignment;
    if (std.ascii.eqlIgnoreCase(raw, "barrier")) return .barrier;
    if (std.ascii.eqlIgnoreCase(raw, "layout")) return .layout;
    if (std.ascii.eqlIgnoreCase(raw, "driver_toggle")) return .driver_toggle;
    if (std.ascii.eqlIgnoreCase(raw, "memory")) return .memory;
    return error.InvalidScope;
}

pub fn parse_safety(raw: []const u8) !SafetyClass {
    if (std.ascii.eqlIgnoreCase(raw, "low")) return .low;
    if (std.ascii.eqlIgnoreCase(raw, "moderate")) return .moderate;
    if (std.ascii.eqlIgnoreCase(raw, "high")) return .high;
    if (std.ascii.eqlIgnoreCase(raw, "critical")) return .critical;
    return error.InvalidSafetyClass;
}

pub fn parse_verification_mode(raw: []const u8) !VerificationMode {
    if (std.ascii.eqlIgnoreCase(raw, "guard_only")) return .guard_only;
    if (std.ascii.eqlIgnoreCase(raw, "lean_preferred")) return .lean_preferred;
    if (std.ascii.eqlIgnoreCase(raw, "lean_required")) return .lean_required;
    return error.InvalidVerificationMode;
}

pub fn parse_proof_level(raw: []const u8) !ProofLevel {
    if (std.ascii.eqlIgnoreCase(raw, "proven")) return .proven;
    if (std.ascii.eqlIgnoreCase(raw, "guarded")) return .guarded;
    if (std.ascii.eqlIgnoreCase(raw, "rejected")) return .rejected;
    return error.InvalidProofLevel;
}

pub fn verification_mode_name(mode: VerificationMode) []const u8 {
    return switch (mode) {
        .guard_only => "guard_only",
        .lean_preferred => "lean_preferred",
        .lean_required => "lean_required",
    };
}

pub fn proof_level_name(level: ProofLevel) []const u8 {
    return switch (level) {
        .proven => "proven",
        .guarded => "guarded",
        .rejected => "rejected",
    };
}

pub fn requiresProof(mode: VerificationMode) bool {
    return mode == .lean_required;
}

pub fn needsStrongestProof(level: ProofLevel) bool {
    return level == .proven;
}

pub fn core_command_kind(kind: CommandKind) ?CoreCommandKind {
    return @import("core/command_partition.zig").fromCombined(kind);
}

pub fn full_command_kind(kind: CommandKind) ?FullCommandKind {
    return @import("full/command_partition.zig").fromCombined(kind);
}

pub fn is_core_command_kind(kind: CommandKind) bool {
    return core_command_kind(kind) != null;
}

pub fn is_full_command_kind(kind: CommandKind) bool {
    return full_command_kind(kind) != null;
}

pub fn as_core_command(cmd: Command) ?CoreCommand {
    return switch (cmd) {
        .upload => |payload| .{ .upload = payload },
        .copy_buffer_to_texture => |payload| .{ .copy_buffer_to_texture = payload },
        .barrier => |payload| .{ .barrier = payload },
        .dispatch => |payload| .{ .dispatch = payload },
        .dispatch_indirect => |payload| .{ .dispatch_indirect = payload },
        .kernel_dispatch => |payload| .{ .kernel_dispatch = payload },
        .texture_write => |payload| .{ .texture_write = payload },
        .texture_query => |payload| .{ .texture_query = payload },
        .texture_destroy => |payload| .{ .texture_destroy = payload },
        .map_async => |payload| .{ .map_async = payload },
        else => null,
    };
}

pub fn as_full_command(cmd: Command) ?FullCommand {
    return switch (cmd) {
        .render_draw => |payload| .{ .render_draw = payload },
        .draw_indirect => |payload| .{ .draw_indirect = payload },
        .draw_indexed_indirect => |payload| .{ .draw_indexed_indirect = payload },
        .render_pass => |payload| .{ .render_pass = payload },
        .sampler_create => |payload| .{ .sampler_create = payload },
        .sampler_destroy => |payload| .{ .sampler_destroy = payload },
        .surface_create => |payload| .{ .surface_create = payload },
        .surface_capabilities => |payload| .{ .surface_capabilities = payload },
        .surface_configure => |payload| .{ .surface_configure = payload },
        .surface_acquire => |payload| .{ .surface_acquire = payload },
        .surface_present => |payload| .{ .surface_present = payload },
        .surface_unconfigure => |payload| .{ .surface_unconfigure = payload },
        .surface_release => |payload| .{ .surface_release = payload },
        .async_diagnostics => |payload| .{ .async_diagnostics = payload },
        else => null,
    };
}

pub fn command_kind(cmd: Command) CommandKind {
    return switch (cmd) {
        .upload => .upload,
        .copy_buffer_to_texture => .copy_buffer_to_texture,
        .barrier => .barrier,
        .dispatch => .dispatch,
        .dispatch_indirect => .dispatch_indirect,
        .kernel_dispatch => .kernel_dispatch,
        .render_draw => .render_draw,
        .draw_indirect => .draw_indirect,
        .draw_indexed_indirect => .draw_indexed_indirect,
        .render_pass => .render_pass,
        .sampler_create => .sampler_create,
        .sampler_destroy => .sampler_destroy,
        .texture_write => .texture_write,
        .texture_query => .texture_query,
        .texture_destroy => .texture_destroy,
        .surface_create => .surface_create,
        .surface_capabilities => .surface_capabilities,
        .surface_configure => .surface_configure,
        .surface_acquire => .surface_acquire,
        .surface_present => .surface_present,
        .surface_unconfigure => .surface_unconfigure,
        .surface_release => .surface_release,
        .async_diagnostics => .async_diagnostics,
        .map_async => .map_async,
    };
}

pub fn command_kind_name(cmd: CommandKind) []const u8 {
    return switch (cmd) {
        .upload => "upload",
        .copy_buffer_to_texture => "copy_buffer_to_texture",
        .barrier => "barrier",
        .dispatch => "dispatch",
        .dispatch_indirect => "dispatch_indirect",
        .kernel_dispatch => "kernel_dispatch",
        .render_draw => "render_draw",
        .draw_indirect => "draw_indirect",
        .draw_indexed_indirect => "draw_indexed_indirect",
        .render_pass => "render_pass",
        .sampler_create => "sampler_create",
        .sampler_destroy => "sampler_destroy",
        .texture_write => "texture_write",
        .texture_query => "texture_query",
        .texture_destroy => "texture_destroy",
        .surface_create => "surface_create",
        .surface_capabilities => "surface_capabilities",
        .surface_configure => "surface_configure",
        .surface_acquire => "surface_acquire",
        .surface_present => "surface_present",
        .surface_unconfigure => "surface_unconfigure",
        .surface_release => "surface_release",
        .async_diagnostics => "async_diagnostics",
        .map_async => "map_async",
    };
}

pub fn scope_name(scope: Scope) []const u8 {
    return switch (scope) {
        .alignment => "alignment",
        .barrier => "barrier",
        .layout => "layout",
        .driver_toggle => "driver_toggle",
        .memory => "memory",
    };
}

pub fn safety_class_name(class: SafetyClass) []const u8 {
    return switch (class) {
        .low => "low",
        .moderate => "moderate",
        .high => "high",
        .critical => "critical",
    };
}

// --- inline tests ---

const testing = std.testing;

test "SemVer.parse valid three-part version" {
    const v = try SemVer.parse("1.2.3");
    try testing.expectEqual(@as(u32, 1), v.major);
    try testing.expectEqual(@as(u32, 2), v.minor);
    try testing.expectEqual(@as(u32, 3), v.patch);
}

test "SemVer.parse single number yields major only" {
    const v = try SemVer.parse("5");
    try testing.expectEqual(@as(u32, 5), v.major);
    try testing.expectEqual(@as(u32, 0), v.minor);
    try testing.expectEqual(@as(u32, 0), v.patch);
}

test "SemVer.parse two-part version" {
    const v = try SemVer.parse("10.20");
    try testing.expectEqual(@as(u32, 10), v.major);
    try testing.expectEqual(@as(u32, 20), v.minor);
    try testing.expectEqual(@as(u32, 0), v.patch);
}

test "SemVer.parse rejects empty part" {
    try testing.expectError(error.InvalidVersion, SemVer.parse("1..3"));
}

test "SemVer.parse rejects four-part version" {
    try testing.expectError(error.InvalidVersion, SemVer.parse("1.2.3.4"));
}

test "SemVer.parse rejects non-numeric part" {
    try testing.expectError(error.InvalidVersion, SemVer.parse("1.abc.3"));
}

test "SemVer comparison ordering" {
    const v1 = SemVer{ .major = 1, .minor = 0, .patch = 0 };
    const v2 = SemVer{ .major = 2, .minor = 0, .patch = 0 };
    const v1_1 = SemVer{ .major = 1, .minor = 1, .patch = 0 };
    const v1_0_1 = SemVer{ .major = 1, .minor = 0, .patch = 1 };

    try testing.expect(v1.lt(v2));
    try testing.expect(v2.gt(v1));
    try testing.expect(v1.lt(v1_1));
    try testing.expect(v1.lt(v1_0_1));
    try testing.expect(v1.equals(v1));
    try testing.expect(v1.ge(v1));
    try testing.expect(v2.ge(v1));
    try testing.expect(!v1.gt(v1));
    try testing.expectEqual(std.math.Order.eq, v1.cmp(v1));
}

test "parse_api accepts all backends case-insensitively" {
    try testing.expectEqual(Api.vulkan, try parse_api("vulkan"));
    try testing.expectEqual(Api.metal, try parse_api("Metal"));
    try testing.expectEqual(Api.d3d12, try parse_api("D3D12"));
    try testing.expectEqual(Api.webgpu, try parse_api("WEBGPU"));
    try testing.expectError(error.InvalidApi, parse_api("opengl"));
}

test "parse_scope accepts all scopes and rejects unknown" {
    try testing.expectEqual(Scope.alignment, try parse_scope("alignment"));
    try testing.expectEqual(Scope.barrier, try parse_scope("BARRIER"));
    try testing.expectEqual(Scope.layout, try parse_scope("layout"));
    try testing.expectEqual(Scope.driver_toggle, try parse_scope("driver_toggle"));
    try testing.expectEqual(Scope.memory, try parse_scope("memory"));
    try testing.expectError(error.InvalidScope, parse_scope("unknown"));
}

test "parse_safety accepts all classes and rejects unknown" {
    try testing.expectEqual(SafetyClass.low, try parse_safety("low"));
    try testing.expectEqual(SafetyClass.moderate, try parse_safety("Moderate"));
    try testing.expectEqual(SafetyClass.high, try parse_safety("HIGH"));
    try testing.expectEqual(SafetyClass.critical, try parse_safety("critical"));
    try testing.expectError(error.InvalidSafetyClass, parse_safety("extreme"));
}

test "parse_verification_mode accepts all modes and rejects unknown" {
    try testing.expectEqual(VerificationMode.guard_only, try parse_verification_mode("guard_only"));
    try testing.expectEqual(VerificationMode.lean_preferred, try parse_verification_mode("lean_preferred"));
    try testing.expectEqual(VerificationMode.lean_required, try parse_verification_mode("LEAN_REQUIRED"));
    try testing.expectError(error.InvalidVerificationMode, parse_verification_mode("auto"));
}

test "parse_proof_level accepts all levels and rejects unknown" {
    try testing.expectEqual(ProofLevel.proven, try parse_proof_level("proven"));
    try testing.expectEqual(ProofLevel.guarded, try parse_proof_level("guarded"));
    try testing.expectEqual(ProofLevel.rejected, try parse_proof_level("REJECTED"));
    try testing.expectError(error.InvalidProofLevel, parse_proof_level("pending"));
}

test "verification_mode_name round-trips with parse_verification_mode" {
    inline for (.{ VerificationMode.guard_only, VerificationMode.lean_preferred, VerificationMode.lean_required }) |mode| {
        const name = verification_mode_name(mode);
        const parsed = try parse_verification_mode(name);
        try testing.expectEqual(mode, parsed);
    }
}

test "proof_level_name round-trips with parse_proof_level" {
    inline for (.{ ProofLevel.proven, ProofLevel.guarded, ProofLevel.rejected }) |level| {
        const name = proof_level_name(level);
        const parsed = try parse_proof_level(name);
        try testing.expectEqual(level, parsed);
    }
}

test "requiresProof only true for lean_required" {
    try testing.expect(requiresProof(.lean_required));
    try testing.expect(!requiresProof(.lean_preferred));
    try testing.expect(!requiresProof(.guard_only));
}

test "needsStrongestProof only true for proven" {
    try testing.expect(needsStrongestProof(.proven));
    try testing.expect(!needsStrongestProof(.guarded));
    try testing.expect(!needsStrongestProof(.rejected));
}

test "command_kind_name returns correct string for selected kinds" {
    try testing.expectEqualStrings("upload", command_kind_name(.upload));
    try testing.expectEqualStrings("kernel_dispatch", command_kind_name(.kernel_dispatch));
    try testing.expectEqualStrings("render_draw", command_kind_name(.render_draw));
    try testing.expectEqualStrings("map_async", command_kind_name(.map_async));
}

test "scope_name and safety_class_name return correct strings" {
    try testing.expectEqualStrings("alignment", scope_name(.alignment));
    try testing.expectEqualStrings("memory", scope_name(.memory));
    try testing.expectEqualStrings("low", safety_class_name(.low));
    try testing.expectEqualStrings("critical", safety_class_name(.critical));
}

test "is_core_command_kind and is_full_command_kind partition correctly" {
    // Core commands
    try testing.expect(is_core_command_kind(.upload));
    try testing.expect(is_core_command_kind(.dispatch));
    try testing.expect(is_core_command_kind(.kernel_dispatch));
    try testing.expect(is_core_command_kind(.map_async));
    try testing.expect(!is_full_command_kind(.upload));
    try testing.expect(!is_full_command_kind(.dispatch));

    // Full commands
    try testing.expect(is_full_command_kind(.render_draw));
    try testing.expect(is_full_command_kind(.sampler_create));
    try testing.expect(is_full_command_kind(.async_diagnostics));
    try testing.expect(!is_core_command_kind(.render_draw));
    try testing.expect(!is_core_command_kind(.sampler_create));
}

test "as_core_command converts core union variants" {
    const cmd = Command{ .upload = .{ .bytes = 1024, .align_bytes = 256 } };
    const core = as_core_command(cmd);
    try testing.expect(core != null);
    try testing.expectEqual(@as(usize, 1024), core.?.upload.bytes);
    try testing.expectEqual(@as(u32, 256), core.?.upload.align_bytes);
}

test "as_core_command returns null for full-only variants" {
    const cmd = Command{ .render_draw = .{ .draw_count = 1 } };
    try testing.expect(as_core_command(cmd) == null);
}

test "as_full_command converts full union variants" {
    const cmd = Command{ .sampler_create = .{ .handle = 42 } };
    const full = as_full_command(cmd);
    try testing.expect(full != null);
    try testing.expectEqual(@as(u64, 42), full.?.sampler_create.handle);
}

test "as_full_command returns null for core-only variants" {
    const cmd = Command{ .barrier = .{ .dependency_count = 3 } };
    try testing.expect(as_full_command(cmd) == null);
}

test "texture usage flags are distinct powers of two" {
    const flags = [_]WGPUFlags{
        WGPUTextureUsage_CopySrc,
        WGPUTextureUsage_CopyDst,
        WGPUTextureUsage_TextureBinding,
        WGPUTextureUsage_StorageBinding,
        WGPUTextureUsage_RenderAttachment,
    };
    // Each flag is a distinct power of two (no overlap when ORed pairwise)
    for (flags, 0..) |a, i| {
        try testing.expect(a != 0);
        try testing.expect(a & (a - 1) == 0); // power of two check
        for (flags[i + 1 ..]) |b| {
            try testing.expect(a != b);
            try testing.expect(a & b == 0);
        }
    }
}

test "command_kind extracts tag from Command union" {
    const cmd = Command{ .dispatch = .{ .x = 1, .y = 2, .z = 3 } };
    try testing.expectEqual(CommandKind.dispatch, command_kind(cmd));
}
