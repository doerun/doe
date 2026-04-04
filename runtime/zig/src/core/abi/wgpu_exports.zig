const binding = @import("wgpu_binding_base_types.zig");
const callback = @import("wgpu_callback_descriptor_types.zig");
const core = @import("wgpu_core_base_types.zig");
const copy = @import("wgpu_copy_descriptor_types.zig");
const feature = @import("wgpu_feature_base_types.zig");
const pipeline = @import("wgpu_pipeline_descriptor_types.zig");
const texture = @import("wgpu_texture_base_types.zig");

pub const wgpu_handle_types = @import("wgpu_handle_types.zig");
pub const wgpu_core_base_types = @import("wgpu_core_base_types.zig");
pub const wgpu_feature_base_types = @import("wgpu_feature_base_types.zig");
pub const wgpu_texture_base_types = @import("wgpu_texture_base_types.zig");
pub const wgpu_binding_base_types = @import("wgpu_binding_base_types.zig");
pub const wgpu_base_types = struct {
    pub usingnamespace core;
    pub usingnamespace feature;
    pub usingnamespace texture;
    pub usingnamespace binding;
};
pub const wgpu_callback_descriptor_types = @import("wgpu_callback_descriptor_types.zig");
pub const wgpu_copy_descriptor_types = @import("wgpu_copy_descriptor_types.zig");
pub const wgpu_pipeline_descriptor_types = @import("wgpu_pipeline_descriptor_types.zig");
pub const wgpu_descriptor_types = struct {
    pub usingnamespace callback;
    pub usingnamespace copy;
    pub usingnamespace pipeline;
};
pub const wgpu_execution_types = @import("wgpu_execution_types.zig");
pub const wgpu_loader = @import("wgpu_loader.zig");
pub const wgpu_record_types = @import("wgpu_record_types.zig");
pub const wgpu_proc_types = @import("wgpu_proc_types.zig");
pub const wgpu_runtime_records = @import("wgpu_runtime_records.zig");
pub const wgpu_runtime_abi = @import("wgpu_runtime_abi.zig");
pub const wgpu_runtime_state_defs = @import("wgpu_runtime_state_defs.zig");
pub const wgpu_state_types = @import("wgpu_state_types.zig");
pub const wgpu_types = @import("wgpu_runtime_abi.zig");
