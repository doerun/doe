const std = @import("std");
const model_webgpu_types = @import("model_webgpu_types.zig");
pub const WGPUFlags = model_webgpu_types.WGPUFlags;
pub const WGPUSType = model_webgpu_types.WGPUSType;
pub const WGPUTextureFormat = model_webgpu_types.WGPUTextureFormat;
pub const WGPUTextureUsage_None = model_webgpu_types.WGPUTextureUsage_None;
pub const WGPUTextureUsage_CopySrc = model_webgpu_types.WGPUTextureUsage_CopySrc;
pub const WGPUTextureUsage_CopyDst = model_webgpu_types.WGPUTextureUsage_CopyDst;
pub const WGPUTextureUsage_TextureBinding = model_webgpu_types.WGPUTextureUsage_TextureBinding;
pub const WGPUTextureUsage_StorageBinding = model_webgpu_types.WGPUTextureUsage_StorageBinding;
pub const WGPUTextureUsage_RenderAttachment = model_webgpu_types.WGPUTextureUsage_RenderAttachment;
pub const WGPUCopyStrideUndefined = model_webgpu_types.WGPUCopyStrideUndefined;
pub const WGPUWholeSize = model_webgpu_types.WGPUWholeSize;
pub const WGPUTextureDimension_Undefined = model_webgpu_types.WGPUTextureDimension_Undefined;
pub const WGPUTextureDimension_1D = model_webgpu_types.WGPUTextureDimension_1D;
pub const WGPUTextureDimension_2D = model_webgpu_types.WGPUTextureDimension_2D;
pub const WGPUTextureDimension_3D = model_webgpu_types.WGPUTextureDimension_3D;
pub const WGPUTextureViewDimension_Undefined = model_webgpu_types.WGPUTextureViewDimension_Undefined;
pub const WGPUTextureViewDimension_1D = model_webgpu_types.WGPUTextureViewDimension_1D;
pub const WGPUTextureViewDimension_2D = model_webgpu_types.WGPUTextureViewDimension_2D;
pub const WGPUTextureViewDimension_2DArray = model_webgpu_types.WGPUTextureViewDimension_2DArray;
pub const WGPUTextureViewDimension_Cube = model_webgpu_types.WGPUTextureViewDimension_Cube;
pub const WGPUTextureViewDimension_CubeArray = model_webgpu_types.WGPUTextureViewDimension_CubeArray;
pub const WGPUTextureViewDimension_3D = model_webgpu_types.WGPUTextureViewDimension_3D;
pub const WGPUTextureAspect_Undefined = model_webgpu_types.WGPUTextureAspect_Undefined;
pub const WGPUTextureAspect_All = model_webgpu_types.WGPUTextureAspect_All;
pub const WGPUTextureAspect_StencilOnly = model_webgpu_types.WGPUTextureAspect_StencilOnly;
pub const WGPUTextureAspect_DepthOnly = model_webgpu_types.WGPUTextureAspect_DepthOnly;
pub const WGPUTextureFormat_Undefined = model_webgpu_types.WGPUTextureFormat_Undefined;
pub const WGPUTextureFormat_R8Unorm = model_webgpu_types.WGPUTextureFormat_R8Unorm;
pub const WGPUTextureFormat_R8Snorm = model_webgpu_types.WGPUTextureFormat_R8Snorm;
pub const WGPUTextureFormat_R8Uint = model_webgpu_types.WGPUTextureFormat_R8Uint;
pub const WGPUTextureFormat_R8Sint = model_webgpu_types.WGPUTextureFormat_R8Sint;
pub const WGPUTextureFormat_R16Unorm = model_webgpu_types.WGPUTextureFormat_R16Unorm;
pub const WGPUTextureFormat_R16Snorm = model_webgpu_types.WGPUTextureFormat_R16Snorm;
pub const WGPUTextureFormat_R16Uint = model_webgpu_types.WGPUTextureFormat_R16Uint;
pub const WGPUTextureFormat_R16Sint = model_webgpu_types.WGPUTextureFormat_R16Sint;
pub const WGPUTextureFormat_R16Float = model_webgpu_types.WGPUTextureFormat_R16Float;
pub const WGPUTextureFormat_RG8Unorm = model_webgpu_types.WGPUTextureFormat_RG8Unorm;
pub const WGPUTextureFormat_RG8Snorm = model_webgpu_types.WGPUTextureFormat_RG8Snorm;
pub const WGPUTextureFormat_RG8Uint = model_webgpu_types.WGPUTextureFormat_RG8Uint;
pub const WGPUTextureFormat_RG8Sint = model_webgpu_types.WGPUTextureFormat_RG8Sint;
pub const WGPUTextureFormat_R32Float = model_webgpu_types.WGPUTextureFormat_R32Float;
pub const WGPUTextureFormat_R32Uint = model_webgpu_types.WGPUTextureFormat_R32Uint;
pub const WGPUTextureFormat_R32Sint = model_webgpu_types.WGPUTextureFormat_R32Sint;
pub const WGPUTextureFormat_RG16Unorm = model_webgpu_types.WGPUTextureFormat_RG16Unorm;
pub const WGPUTextureFormat_RG16Snorm = model_webgpu_types.WGPUTextureFormat_RG16Snorm;
pub const WGPUTextureFormat_RG16Uint = model_webgpu_types.WGPUTextureFormat_RG16Uint;
pub const WGPUTextureFormat_RG16Sint = model_webgpu_types.WGPUTextureFormat_RG16Sint;
pub const WGPUTextureFormat_RG16Float = model_webgpu_types.WGPUTextureFormat_RG16Float;
pub const WGPUTextureFormat_RGBA8Unorm = model_webgpu_types.WGPUTextureFormat_RGBA8Unorm;
pub const WGPUTextureFormat_RGBA8UnormSrgb = model_webgpu_types.WGPUTextureFormat_RGBA8UnormSrgb;
pub const WGPUTextureFormat_RGBA8Snorm = model_webgpu_types.WGPUTextureFormat_RGBA8Snorm;
pub const WGPUTextureFormat_RGBA8Uint = model_webgpu_types.WGPUTextureFormat_RGBA8Uint;
pub const WGPUTextureFormat_RGBA8Sint = model_webgpu_types.WGPUTextureFormat_RGBA8Sint;
pub const WGPUTextureFormat_BGRA8Unorm = model_webgpu_types.WGPUTextureFormat_BGRA8Unorm;
pub const WGPUTextureFormat_BGRA8UnormSrgb = model_webgpu_types.WGPUTextureFormat_BGRA8UnormSrgb;
pub const WGPUTextureFormat_Depth16Unorm = model_webgpu_types.WGPUTextureFormat_Depth16Unorm;
pub const WGPUTextureFormat_Depth24Plus = model_webgpu_types.WGPUTextureFormat_Depth24Plus;
pub const WGPUTextureFormat_Depth24PlusStencil8 = model_webgpu_types.WGPUTextureFormat_Depth24PlusStencil8;
pub const WGPUTextureFormat_Depth32Float = model_webgpu_types.WGPUTextureFormat_Depth32Float;
pub const WGPUTextureFormat_Depth32FloatStencil8 = model_webgpu_types.WGPUTextureFormat_Depth32FloatStencil8;
pub const WGPUShaderStage_None = model_webgpu_types.WGPUShaderStage_None;
pub const WGPUShaderStage_Vertex = model_webgpu_types.WGPUShaderStage_Vertex;
pub const WGPUShaderStage_Fragment = model_webgpu_types.WGPUShaderStage_Fragment;
pub const WGPUShaderStage_Compute = model_webgpu_types.WGPUShaderStage_Compute;
pub const WGPUBufferBindingType_Undefined = model_webgpu_types.WGPUBufferBindingType_Undefined;
pub const WGPUBufferBindingType_Uniform = model_webgpu_types.WGPUBufferBindingType_Uniform;
pub const WGPUBufferBindingType_Storage = model_webgpu_types.WGPUBufferBindingType_Storage;
pub const WGPUBufferBindingType_ReadOnlyStorage = model_webgpu_types.WGPUBufferBindingType_ReadOnlyStorage;
pub const WGPUTextureSampleType_Undefined = model_webgpu_types.WGPUTextureSampleType_Undefined;
pub const WGPUTextureSampleType_Float = model_webgpu_types.WGPUTextureSampleType_Float;
pub const WGPUTextureSampleType_UnfilterableFloat = model_webgpu_types.WGPUTextureSampleType_UnfilterableFloat;
pub const WGPUTextureSampleType_Depth = model_webgpu_types.WGPUTextureSampleType_Depth;
pub const WGPUTextureSampleType_Sint = model_webgpu_types.WGPUTextureSampleType_Sint;
pub const WGPUTextureSampleType_Uint = model_webgpu_types.WGPUTextureSampleType_Uint;
pub const WGPUStorageTextureAccess_Undefined = model_webgpu_types.WGPUStorageTextureAccess_Undefined;
pub const WGPUStorageTextureAccess_WriteOnly = model_webgpu_types.WGPUStorageTextureAccess_WriteOnly;
pub const WGPUStorageTextureAccess_ReadOnly = model_webgpu_types.WGPUStorageTextureAccess_ReadOnly;
pub const WGPUStorageTextureAccess_ReadWrite = model_webgpu_types.WGPUStorageTextureAccess_ReadWrite;
pub const CopyResourceKind = model_webgpu_types.CopyResourceKind;
pub const CopyDirection = model_webgpu_types.CopyDirection;
pub const CopyTextureResource = model_webgpu_types.CopyTextureResource;
pub const UploadCommand = model_webgpu_types.UploadCommand;
pub const CopyCommand = model_webgpu_types.CopyCommand;
pub const BarrierCommand = model_webgpu_types.BarrierCommand;
pub const DispatchCommand = model_webgpu_types.DispatchCommand;
pub const DispatchIndirectCommand = model_webgpu_types.DispatchIndirectCommand;
pub const KernelBindingResourceKind = model_webgpu_types.KernelBindingResourceKind;
pub const KernelBinding = model_webgpu_types.KernelBinding;
pub const KernelDispatchCommand = model_webgpu_types.KernelDispatchCommand;
pub const DEFAULT_RENDER_TARGET_HANDLE = model_webgpu_types.DEFAULT_RENDER_TARGET_HANDLE;
pub const DEFAULT_RENDER_TARGET_WIDTH = model_webgpu_types.DEFAULT_RENDER_TARGET_WIDTH;
pub const DEFAULT_RENDER_TARGET_HEIGHT = model_webgpu_types.DEFAULT_RENDER_TARGET_HEIGHT;
pub const DEFAULT_RENDER_TARGET_FORMAT = model_webgpu_types.DEFAULT_RENDER_TARGET_FORMAT;
pub const RenderDrawPipelineMode = model_webgpu_types.RenderDrawPipelineMode;
pub const RenderDrawBindGroupMode = model_webgpu_types.RenderDrawBindGroupMode;
pub const RenderDrawEncodeMode = model_webgpu_types.RenderDrawEncodeMode;
pub const RenderIndexFormat = model_webgpu_types.RenderIndexFormat;
pub const RenderIndexData = model_webgpu_types.RenderIndexData;
pub const RenderDrawCommand = model_webgpu_types.RenderDrawCommand;
pub const DrawIndirectCommand = model_webgpu_types.DrawIndirectCommand;
pub const DrawIndexedIndirectCommand = model_webgpu_types.DrawIndexedIndirectCommand;
pub const RenderPassCommand = model_webgpu_types.RenderPassCommand;
pub const SamplerCreateCommand = model_webgpu_types.SamplerCreateCommand;
pub const SamplerDestroyCommand = model_webgpu_types.SamplerDestroyCommand;
pub const TextureWriteCommand = model_webgpu_types.TextureWriteCommand;
pub const TextureQueryCommand = model_webgpu_types.TextureQueryCommand;
pub const TextureDestroyCommand = model_webgpu_types.TextureDestroyCommand;
pub const SurfaceCreateCommand = model_webgpu_types.SurfaceCreateCommand;
pub const SurfaceCapabilitiesCommand = model_webgpu_types.SurfaceCapabilitiesCommand;
pub const SurfaceConfigureCommand = model_webgpu_types.SurfaceConfigureCommand;
pub const SurfaceAcquireCommand = model_webgpu_types.SurfaceAcquireCommand;
pub const SurfacePresentCommand = model_webgpu_types.SurfacePresentCommand;
pub const SurfaceUnconfigureCommand = model_webgpu_types.SurfaceUnconfigureCommand;
pub const SurfaceReleaseCommand = model_webgpu_types.SurfaceReleaseCommand;
pub const AsyncDiagnosticsMode = model_webgpu_types.AsyncDiagnosticsMode;
pub const AsyncDiagnosticsFeaturePolicy = model_webgpu_types.AsyncDiagnosticsFeaturePolicy;
pub const AsyncDiagnosticsCommand = model_webgpu_types.AsyncDiagnosticsCommand;
pub const MapAsyncMode = model_webgpu_types.MapAsyncMode;
pub const MapAsyncCommand = model_webgpu_types.MapAsyncCommand;
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
