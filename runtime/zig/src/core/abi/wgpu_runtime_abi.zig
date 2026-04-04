const binding = @import("wgpu_binding_base_types.zig");
const callback = @import("wgpu_callback_descriptor_types.zig");
const core = @import("wgpu_core_base_types.zig");
const copy = @import("wgpu_copy_descriptor_types.zig");
const feature = @import("wgpu_feature_base_types.zig");
const pipeline = @import("wgpu_pipeline_descriptor_types.zig");
const proc_aliases = @import("wgpu_type_proc_aliases.zig");
const records = @import("wgpu_runtime_records.zig");
const runtime_state = @import("wgpu_runtime_state_defs.zig");
const texture = @import("wgpu_texture_base_types.zig");

pub usingnamespace core;
pub usingnamespace feature;
pub usingnamespace texture;
pub usingnamespace binding;
pub usingnamespace callback;
pub usingnamespace copy;
pub usingnamespace pipeline;

pub const BufferRecord = records.BufferRecord;
pub const TextureRecord = records.TextureRecord;
pub const DispatchPassArtifacts = records.DispatchPassArtifacts;
pub const RenderPipelineCacheEntry = records.RenderPipelineCacheEntry;
pub const RenderTextureViewCacheEntry = records.RenderTextureViewCacheEntry;
pub const DispatchPassGroup = records.DispatchPassGroup;
pub const RequestState = records.RequestState;
pub const DeviceRequestState = records.DeviceRequestState;

pub const QueueSubmitState = runtime_state.QueueSubmitState;
pub const BufferMapState = runtime_state.BufferMapState;
pub const UncapturedErrorState = runtime_state.UncapturedErrorState;
pub const KernelSource = runtime_state.KernelSource;
pub const KernelLookupResult = runtime_state.KernelLookupResult;
pub const PipelineCacheEntry = runtime_state.PipelineCacheEntry;

pub usingnamespace proc_aliases;
