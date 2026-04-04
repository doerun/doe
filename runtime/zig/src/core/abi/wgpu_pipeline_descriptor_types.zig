const binding = @import("wgpu_binding_base_types.zig");
const callbacks = @import("wgpu_callback_descriptor_types.zig");
const core = @import("wgpu_core_base_types.zig");
const copy = @import("wgpu_copy_descriptor_types.zig");
const texture = @import("wgpu_texture_base_types.zig");

pub const WGPUTextureViewDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    format: texture.WGPUTextureFormat,
    dimension: texture.WGPUTextureViewDimension,
    baseMipLevel: u32,
    mipLevelCount: u32,
    baseArrayLayer: u32,
    arrayLayerCount: u32,
    aspect: texture.WGPUTextureAspect,
    usage: texture.WGPUTextureUsage,
    swizzleR: texture.WGPUTextureComponentSwizzle,
    swizzleG: texture.WGPUTextureComponentSwizzle,
    swizzleB: texture.WGPUTextureComponentSwizzle,
    swizzleA: texture.WGPUTextureComponentSwizzle,
};

pub const WGPUTextureDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    usage: texture.WGPUTextureUsage,
    dimension: texture.WGPUTextureDimension,
    size: copy.WGPUExtent3D,
    format: texture.WGPUTextureFormat,
    mipLevelCount: u32,
    sampleCount: u32,
    viewFormatCount: usize,
    viewFormats: ?[*]const texture.WGPUTextureFormat,
};

pub const WGPUBufferBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
    hasDynamicOffset: core.WGPUBool,
    minBindingSize: u64,
};

pub const WGPUSamplerBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
};

pub const WGPUTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    sampleType: u32,
    viewDimension: texture.WGPUTextureViewDimension,
    multisampled: core.WGPUBool,
};

pub const WGPUStorageTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    access: u32,
    format: texture.WGPUTextureFormat,
    viewDimension: texture.WGPUTextureViewDimension,
};

pub const WGPUBindGroupLayoutEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    visibility: binding.WGPUShaderStageFlags,
    bindingArraySize: u32,
    buffer: WGPUBufferBindingLayout,
    sampler: WGPUSamplerBindingLayout,
    texture: WGPUTextureBindingLayout,
    storageTexture: WGPUStorageTextureBindingLayout,
};

pub const WGPUBindGroupEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    buffer: core.WGPUBuffer,
    offset: u64,
    size: u64,
    sampler: core.WGPUSampler,
    textureView: core.WGPUTextureView,
};

pub const WGPUExternalTextureBindingLayout = extern struct {
    chain: callbacks.WGPUChainedStruct,
};

pub const WGPUExternalTextureBindingEntry = extern struct {
    chain: callbacks.WGPUChainedStruct,
    externalTexture: base.WGPUExternalTexture,
};

pub const WGPUBindGroupLayoutDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    entryCount: usize,
    entries: ?[*]const WGPUBindGroupLayoutEntry,
};

pub const WGPUBindGroupDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    layout: core.WGPUBindGroupLayout,
    entryCount: usize,
    entries: [*]const WGPUBindGroupEntry,
};

pub const WGPUPipelineLayoutDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    bindGroupLayoutCount: usize,
    bindGroupLayouts: [*]const core.WGPUBindGroupLayout,
    immediateSize: u32,
};

pub const WGPUBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    usage: core.WGPUBufferUsage,
    size: u64,
    mappedAtCreation: core.WGPUBool,
};

pub const WGPUShaderModuleDescriptor = extern struct {
    nextInChain: ?*callbacks.WGPUChainedStruct,
    label: core.WGPUStringView,
};

pub const WGPUShaderSourceWGSL = extern struct {
    chain: callbacks.WGPUChainedStruct,
    code: core.WGPUStringView,
};

pub const WGPUShaderSourceMSL = extern struct {
    chain: callbacks.WGPUChainedStruct,
    code: core.WGPUStringView,
    workgroup_size_x: u32,
    workgroup_size_y: u32,
    workgroup_size_z: u32,
};

pub const WGPUShaderSourceSPIRV = extern struct {
    chain: callbacks.WGPUChainedStruct,
    code: [*]const u32,
    code_size: u32,
    workgroup_size_x: u32,
    workgroup_size_y: u32,
    workgroup_size_z: u32,
};

pub const WGPUShaderSourceHLSL = extern struct {
    chain: callbacks.WGPUChainedStruct,
    code: core.WGPUStringView,
    workgroup_size_x: u32,
    workgroup_size_y: u32,
    workgroup_size_z: u32,
};

pub const WGPUConstantEntry = extern struct {
    nextInChain: ?*anyopaque,
    key: core.WGPUStringView,
    value: f64,
};

pub const WGPUComputeState = extern struct {
    nextInChain: ?*anyopaque,
    module: core.WGPUShaderModule,
    entryPoint: core.WGPUStringView,
    constantCount: usize,
    constants: ?[*]const WGPUConstantEntry,
};

pub const WGPUComputePipelineDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    layout: ?*anyopaque,
    compute: WGPUComputeState,
};

pub const WGPUComputePassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    timestampWrites: ?*const WGPUPassTimestampWrites,
};

pub const WGPUPassTimestampWrites = extern struct {
    nextInChain: ?*anyopaque,
    querySet: core.WGPUQuerySet,
    beginningOfPassWriteIndex: u32,
    endOfPassWriteIndex: u32,
};

pub const WGPUCommandEncoderDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
};

pub const WGPUCommandBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
};

pub const WGPUQuerySetDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    type: core.WGPUQueryType,
    count: u32,
};

pub const WGPUSamplerDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    addressModeU: u32,
    addressModeV: u32,
    addressModeW: u32,
    magFilter: u32,
    minFilter: u32,
    mipmapFilter: u32,
    lodMinClamp: f32,
    lodMaxClamp: f32,
    compare: u32,
    maxAnisotropy: u16,
};

pub const WGPUColor = extern struct {
    r: f64,
    g: f64,
    b: f64,
    a: f64,
};

pub const WGPURenderPassColorAttachment = extern struct {
    nextInChain: ?*anyopaque,
    view: core.WGPUTextureView,
    depthSlice: u32,
    resolveTarget: core.WGPUTextureView,
    loadOp: u32,
    storeOp: u32,
    clearValue: WGPUColor,
};

pub const WGPURenderPassDepthStencilAttachment = extern struct {
    view: core.WGPUTextureView,
    depthLoadOp: u32,
    depthStoreOp: u32,
    depthClearValue: f32,
    depthReadOnly: core.WGPUBool,
    stencilLoadOp: u32,
    stencilStoreOp: u32,
    stencilClearValue: u32,
    stencilReadOnly: core.WGPUBool,
};

pub const WGPURenderPassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: core.WGPUStringView,
    colorAttachmentCount: usize,
    colorAttachments: ?[*]const WGPURenderPassColorAttachment,
    depthStencilAttachment: ?*const WGPURenderPassDepthStencilAttachment,
    occlusionQuerySet: core.WGPUQuerySet,
    timestampWrites: ?*const WGPUPassTimestampWrites,
    maxDrawCount: u64,
};
