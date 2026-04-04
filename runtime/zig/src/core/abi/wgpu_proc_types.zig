const binding = @import("wgpu_binding_base_types.zig");
const callback = @import("wgpu_callback_descriptor_types.zig");
const core = @import("wgpu_core_base_types.zig");
const copy = @import("wgpu_copy_descriptor_types.zig");
const feature = @import("wgpu_feature_base_types.zig");
const pipeline = @import("wgpu_pipeline_descriptor_types.zig");
const texture = @import("wgpu_texture_base_types.zig");

pub const base = struct {
    pub usingnamespace core;
    pub usingnamespace feature;
    pub usingnamespace texture;
    pub usingnamespace binding;
};

pub const descriptor = struct {
    pub usingnamespace callback;
    pub usingnamespace copy;
    pub usingnamespace pipeline;
};
