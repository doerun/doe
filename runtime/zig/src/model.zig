const std = @import("std");
const gpu = @import("model_gpu_types.zig");
const resource = @import("model_resource_types.zig");
const compute = @import("model_compute_types.zig");
const render = @import("model_render_types.zig");
const texture = @import("model_texture_types.zig");
const surface_control = @import("model_surface_control_types.zig");
const async_types = @import("model_async_types.zig");
const commands = @import("model_commands.zig");
const profile = @import("model_profile.zig");
const policy = @import("model_policy.zig");
const quirks = @import("model_quirks.zig");

pub const WGPUFlags = gpu.WGPUFlags;
pub const WGPUSType = gpu.WGPUSType;
pub const WGPUTextureFormat = gpu.WGPUTextureFormat;
pub const WGPUTextureUsage_None = gpu.WGPUTextureUsage_None;
pub const WGPUTextureUsage_CopySrc = gpu.WGPUTextureUsage_CopySrc;
pub const WGPUTextureUsage_CopyDst = gpu.WGPUTextureUsage_CopyDst;
pub const WGPUTextureUsage_TextureBinding = gpu.WGPUTextureUsage_TextureBinding;
pub const WGPUTextureUsage_StorageBinding = gpu.WGPUTextureUsage_StorageBinding;
pub const WGPUTextureUsage_RenderAttachment = gpu.WGPUTextureUsage_RenderAttachment;
pub const WGPUCopyStrideUndefined = gpu.WGPUCopyStrideUndefined;
pub const WGPUWholeSize = gpu.WGPUWholeSize;
pub const WGPUTextureDimension_Undefined = gpu.WGPUTextureDimension_Undefined;
pub const WGPUTextureDimension_1D = gpu.WGPUTextureDimension_1D;
pub const WGPUTextureDimension_2D = gpu.WGPUTextureDimension_2D;
pub const WGPUTextureDimension_3D = gpu.WGPUTextureDimension_3D;
pub const WGPUTextureViewDimension_Undefined = gpu.WGPUTextureViewDimension_Undefined;
pub const WGPUTextureViewDimension_1D = gpu.WGPUTextureViewDimension_1D;
pub const WGPUTextureViewDimension_2D = gpu.WGPUTextureViewDimension_2D;
pub const WGPUTextureViewDimension_2DArray = gpu.WGPUTextureViewDimension_2DArray;
pub const WGPUTextureViewDimension_Cube = gpu.WGPUTextureViewDimension_Cube;
pub const WGPUTextureViewDimension_CubeArray = gpu.WGPUTextureViewDimension_CubeArray;
pub const WGPUTextureViewDimension_3D = gpu.WGPUTextureViewDimension_3D;
pub const WGPUTextureAspect_Undefined = gpu.WGPUTextureAspect_Undefined;
pub const WGPUTextureAspect_All = gpu.WGPUTextureAspect_All;
pub const WGPUTextureAspect_StencilOnly = gpu.WGPUTextureAspect_StencilOnly;
pub const WGPUTextureAspect_DepthOnly = gpu.WGPUTextureAspect_DepthOnly;
pub const WGPUTextureFormat_Undefined = gpu.WGPUTextureFormat_Undefined;
pub const WGPUTextureFormat_R8Unorm = gpu.WGPUTextureFormat_R8Unorm;
pub const WGPUTextureFormat_R8Snorm = gpu.WGPUTextureFormat_R8Snorm;
pub const WGPUTextureFormat_R8Uint = gpu.WGPUTextureFormat_R8Uint;
pub const WGPUTextureFormat_R8Sint = gpu.WGPUTextureFormat_R8Sint;
pub const WGPUTextureFormat_R16Unorm = gpu.WGPUTextureFormat_R16Unorm;
pub const WGPUTextureFormat_R16Snorm = gpu.WGPUTextureFormat_R16Snorm;
pub const WGPUTextureFormat_R16Uint = gpu.WGPUTextureFormat_R16Uint;
pub const WGPUTextureFormat_R16Sint = gpu.WGPUTextureFormat_R16Sint;
pub const WGPUTextureFormat_R16Float = gpu.WGPUTextureFormat_R16Float;
pub const WGPUTextureFormat_RG8Unorm = gpu.WGPUTextureFormat_RG8Unorm;
pub const WGPUTextureFormat_RG8Snorm = gpu.WGPUTextureFormat_RG8Snorm;
pub const WGPUTextureFormat_RG8Uint = gpu.WGPUTextureFormat_RG8Uint;
pub const WGPUTextureFormat_RG8Sint = gpu.WGPUTextureFormat_RG8Sint;
pub const WGPUTextureFormat_R32Float = gpu.WGPUTextureFormat_R32Float;
pub const WGPUTextureFormat_R32Uint = gpu.WGPUTextureFormat_R32Uint;
pub const WGPUTextureFormat_R32Sint = gpu.WGPUTextureFormat_R32Sint;
pub const WGPUTextureFormat_RG16Uint = gpu.WGPUTextureFormat_RG16Uint;
pub const WGPUTextureFormat_RG16Sint = gpu.WGPUTextureFormat_RG16Sint;
pub const WGPUTextureFormat_RG16Float = gpu.WGPUTextureFormat_RG16Float;
pub const WGPUTextureFormat_RGBA8Unorm = gpu.WGPUTextureFormat_RGBA8Unorm;
pub const WGPUTextureFormat_RGBA8UnormSrgb = gpu.WGPUTextureFormat_RGBA8UnormSrgb;
pub const WGPUTextureFormat_RGBA8Snorm = gpu.WGPUTextureFormat_RGBA8Snorm;
pub const WGPUTextureFormat_BGRA8Unorm = gpu.WGPUTextureFormat_BGRA8Unorm;
pub const WGPUTextureFormat_BGRA8UnormSrgb = gpu.WGPUTextureFormat_BGRA8UnormSrgb;
pub const WGPUTextureFormat_RGB10A2Uint = gpu.WGPUTextureFormat_RGB10A2Uint;
pub const WGPUTextureFormat_RGB10A2Unorm = gpu.WGPUTextureFormat_RGB10A2Unorm;
pub const WGPUTextureFormat_RG11B10Ufloat = gpu.WGPUTextureFormat_RG11B10Ufloat;
pub const WGPUTextureFormat_RGB9E5Ufloat = gpu.WGPUTextureFormat_RGB9E5Ufloat;
pub const WGPUTextureFormat_RG32Float = gpu.WGPUTextureFormat_RG32Float;
pub const WGPUTextureFormat_RG32Uint = gpu.WGPUTextureFormat_RG32Uint;
pub const WGPUTextureFormat_RG32Sint = gpu.WGPUTextureFormat_RG32Sint;
pub const WGPUTextureFormat_RGBA16Uint = gpu.WGPUTextureFormat_RGBA16Uint;
pub const WGPUTextureFormat_RGBA16Sint = gpu.WGPUTextureFormat_RGBA16Sint;
pub const WGPUTextureFormat_RGBA16Float = gpu.WGPUTextureFormat_RGBA16Float;
pub const WGPUTextureFormat_RGBA32Float = gpu.WGPUTextureFormat_RGBA32Float;
pub const WGPUTextureFormat_RGBA32Uint = gpu.WGPUTextureFormat_RGBA32Uint;
pub const WGPUTextureFormat_RGBA32Sint = gpu.WGPUTextureFormat_RGBA32Sint;
pub const WGPUTextureFormat_Stencil8 = gpu.WGPUTextureFormat_Stencil8;
pub const WGPUTextureFormat_Depth16Unorm = gpu.WGPUTextureFormat_Depth16Unorm;
pub const WGPUTextureFormat_Depth24Plus = gpu.WGPUTextureFormat_Depth24Plus;
pub const WGPUTextureFormat_Depth24PlusStencil8 = gpu.WGPUTextureFormat_Depth24PlusStencil8;
pub const WGPUTextureFormat_Depth32Float = gpu.WGPUTextureFormat_Depth32Float;
pub const WGPUTextureFormat_Depth32FloatStencil8 = gpu.WGPUTextureFormat_Depth32FloatStencil8;
pub const WGPUTextureFormat_BC1RGBAUnorm = gpu.WGPUTextureFormat_BC1RGBAUnorm;
pub const WGPUTextureFormat_ASTC12x12UnormSrgb = gpu.WGPUTextureFormat_ASTC12x12UnormSrgb;
pub const WGPUShaderStage_None = gpu.WGPUShaderStage_None;
pub const WGPUShaderStage_Vertex = gpu.WGPUShaderStage_Vertex;
pub const WGPUShaderStage_Fragment = gpu.WGPUShaderStage_Fragment;
pub const WGPUShaderStage_Compute = gpu.WGPUShaderStage_Compute;
pub const WGPUBufferBindingType_Undefined = gpu.WGPUBufferBindingType_Undefined;
pub const WGPUBufferBindingType_Uniform = gpu.WGPUBufferBindingType_Uniform;
pub const WGPUBufferBindingType_Storage = gpu.WGPUBufferBindingType_Storage;
pub const WGPUBufferBindingType_ReadOnlyStorage = gpu.WGPUBufferBindingType_ReadOnlyStorage;
pub const WGPUTextureSampleType_Undefined = gpu.WGPUTextureSampleType_Undefined;
pub const WGPUTextureSampleType_Float = gpu.WGPUTextureSampleType_Float;
pub const WGPUTextureSampleType_UnfilterableFloat = gpu.WGPUTextureSampleType_UnfilterableFloat;
pub const WGPUTextureSampleType_Depth = gpu.WGPUTextureSampleType_Depth;
pub const WGPUTextureSampleType_Sint = gpu.WGPUTextureSampleType_Sint;
pub const WGPUTextureSampleType_Uint = gpu.WGPUTextureSampleType_Uint;
pub const WGPUStorageTextureAccess_Undefined = gpu.WGPUStorageTextureAccess_Undefined;
pub const WGPUStorageTextureAccess_WriteOnly = gpu.WGPUStorageTextureAccess_WriteOnly;
pub const WGPUStorageTextureAccess_ReadOnly = gpu.WGPUStorageTextureAccess_ReadOnly;
pub const WGPUStorageTextureAccess_ReadWrite = gpu.WGPUStorageTextureAccess_ReadWrite;

pub const CopyResourceKind = resource.CopyResourceKind;
pub const CopyDirection = resource.CopyDirection;
pub const CopyTextureResource = resource.CopyTextureResource;
pub const UploadCommand = resource.UploadCommand;
pub const CopyCommand = resource.CopyCommand;

pub const DispatchCommand = compute.DispatchCommand;
pub const DispatchIndirectCommand = compute.DispatchIndirectCommand;
pub const KernelBindingResourceKind = compute.KernelBindingResourceKind;
pub const KernelBinding = compute.KernelBinding;
pub const KernelDispatchCommand = compute.KernelDispatchCommand;

pub const DEFAULT_RENDER_TARGET_HANDLE = render.DEFAULT_RENDER_TARGET_HANDLE;
pub const DEFAULT_RENDER_TARGET_WIDTH = render.DEFAULT_RENDER_TARGET_WIDTH;
pub const DEFAULT_RENDER_TARGET_HEIGHT = render.DEFAULT_RENDER_TARGET_HEIGHT;
pub const DEFAULT_RENDER_TARGET_FORMAT = render.DEFAULT_RENDER_TARGET_FORMAT;
pub const RenderDrawPipelineMode = render.RenderDrawPipelineMode;
pub const RenderDrawBindGroupMode = render.RenderDrawBindGroupMode;
pub const RenderDrawEncodeMode = render.RenderDrawEncodeMode;
pub const RenderIndexFormat = render.RenderIndexFormat;
pub const MAX_VERTEX_BUFFERS = render.MAX_VERTEX_BUFFERS;
pub const MAX_VERTEX_ATTRIBUTES = render.MAX_VERTEX_ATTRIBUTES;
pub const MAX_RENDER_BIND_ENTRIES = render.MAX_RENDER_BIND_ENTRIES;
pub const WGPUVertexStepMode_Vertex = render.WGPUVertexStepMode_Vertex;
pub const WGPUVertexStepMode_Instance = render.WGPUVertexStepMode_Instance;
pub const RenderDrawCommand = render.RenderDrawCommand;
pub const DrawIndirectCommand = render.DrawIndirectCommand;
pub const DrawIndexedIndirectCommand = render.DrawIndexedIndirectCommand;
pub const RenderPassCommand = render.RenderPassCommand;
pub const SamplerCreateCommand = render.SamplerCreateCommand;

pub const TextureWriteCommand = texture.TextureWriteCommand;
pub const TextureQueryCommand = texture.TextureQueryCommand;

pub const SurfaceConfigureCommand = surface_control.SurfaceConfigureCommand;
pub const WGPUCanvasToneMappingMode_Standard = surface_control.WGPUCanvasToneMappingMode_Standard;
pub const WGPUCanvasToneMappingMode_Extended = surface_control.WGPUCanvasToneMappingMode_Extended;

pub const AsyncDiagnosticsMode = async_types.AsyncDiagnosticsMode;
pub const AsyncDiagnosticsFeaturePolicy = async_types.AsyncDiagnosticsFeaturePolicy;
pub const AsyncDiagnosticsCommand = async_types.AsyncDiagnosticsCommand;
pub const MapAsyncMode = async_types.MapAsyncMode;
pub const MapAsyncCommand = async_types.MapAsyncCommand;

pub const CoreCommandKind = commands.CoreCommandKind;
pub const FullCommandKind = commands.FullCommandKind;
pub const CoreCommand = commands.CoreCommand;
pub const FullCommand = commands.FullCommand;
pub const CommandKind = commands.CommandKind;
pub const Command = commands.Command;
pub const core_command_kind = commands.core_command_kind;
pub const full_command_kind = commands.full_command_kind;
pub const is_core_command_kind = commands.is_core_command_kind;
pub const is_full_command_kind = commands.is_full_command_kind;
pub const as_core_command = commands.as_core_command;
pub const as_full_command = commands.as_full_command;
pub const command_kind = commands.command_kind;
pub const command_kind_name = commands.command_kind_name;

pub const DeviceProfile = profile.DeviceProfile;
pub const SemVer = profile.SemVer;

pub const SchemaVersion = policy.SchemaVersion;
pub const CURRENT_SCHEMA_VERSION = policy.CURRENT_SCHEMA_VERSION;
pub const Api = policy.Api;
pub const Scope = policy.Scope;
pub const SafetyClass = policy.SafetyClass;
pub const VerificationMode = policy.VerificationMode;
pub const ProofLevel = policy.ProofLevel;
pub const parse_api = policy.parse_api;
pub const parse_scope = policy.parse_scope;
pub const parse_safety = policy.parse_safety;
pub const parse_verification_mode = policy.parse_verification_mode;
pub const parse_proof_level = policy.parse_proof_level;
pub const verification_mode_name = policy.verification_mode_name;
pub const proof_level_name = policy.proof_level_name;
pub const requiresProof = policy.requiresProof;
pub const needsStrongestProof = policy.needsStrongestProof;
pub const scope_name = policy.scope_name;
pub const safety_class_name = policy.safety_class_name;

pub const MatchSpec = quirks.MatchSpec;
pub const QuirkAction = quirks.QuirkAction;
pub const Quirk = quirks.Quirk;

const testing = std.testing;

test "texture usage flags are distinct powers of two" {
    const flags = [_]WGPUFlags{
        WGPUTextureUsage_CopySrc,
        WGPUTextureUsage_CopyDst,
        WGPUTextureUsage_TextureBinding,
        WGPUTextureUsage_StorageBinding,
        WGPUTextureUsage_RenderAttachment,
    };
    for (flags, 0..) |a, i| {
        try testing.expect(a != 0);
        try testing.expect(a & (a - 1) == 0);
        for (flags[i + 1 ..]) |b| {
            try testing.expect(a != b);
            try testing.expect(a & b == 0);
        }
    }
}
