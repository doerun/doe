const contract_types = @import("wgpu_state_contract_types.zig");
const defs = @import("wgpu_state_types.zig").definitions(contract_types);

pub const QueueSubmitState = defs.QueueSubmitState;
pub const BufferMapState = defs.BufferMapState;
pub const UncapturedErrorState = defs.UncapturedErrorState;
pub const KernelSource = defs.KernelSource;
pub const KernelLookupResult = defs.KernelLookupResult;
pub const PipelineCacheEntry = defs.PipelineCacheEntry;
