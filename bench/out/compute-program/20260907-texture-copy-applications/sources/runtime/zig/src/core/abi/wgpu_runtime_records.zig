const record_types = @import("wgpu_record_types.zig");
const defs = @import("wgpu_type_records.zig").definitions(record_types);

pub const BufferRecord = defs.BufferRecord;
pub const TextureRecord = defs.TextureRecord;
pub const DispatchPassArtifacts = defs.DispatchPassArtifacts;
pub const RenderPipelineCacheEntry = defs.RenderPipelineCacheEntry;
pub const RenderTextureViewCacheEntry = defs.RenderTextureViewCacheEntry;
pub const DispatchPassGroup = defs.DispatchPassGroup;
pub const RequestState = defs.RequestState;
pub const DeviceRequestState = defs.DeviceRequestState;
