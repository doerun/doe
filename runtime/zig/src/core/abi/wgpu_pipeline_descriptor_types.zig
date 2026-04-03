const base = @import("wgpu_base_types.zig");
const callbacks = @import("wgpu_callback_descriptor_types.zig");
const copy = @import("wgpu_copy_descriptor_types.zig");

pub const WGPUTextureViewDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    format: base.WGPUTextureFormat,
    dimension: base.WGPUTextureViewDimension,
    baseMipLevel: u32,
    mipLevelCount: u32,
    baseArrayLayer: u32,
    arrayLayerCount: u32,
    aspect: base.WGPUTextureAspect,
    usage: base.WGPUTextureUsage,
    swizzleR: base.WGPUTextureComponentSwizzle,
    swizzleG: base.WGPUTextureComponentSwizzle,
    swizzleB: base.WGPUTextureComponentSwizzle,
    swizzleA: base.WGPUTextureComponentSwizzle,
};

pub const WGPUTextureDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    usage: base.WGPUTextureUsage,
    dimension: base.WGPUTextureDimension,
    size: copy.WGPUExtent3D,
    format: base.WGPUTextureFormat,
    mipLevelCount: u32,
    sampleCount: u32,
    viewFormatCount: usize,
    viewFormats: ?[*]const base.WGPUTextureFormat,
};

pub const WGPUBufferBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
    hasDynamicOffset: base.WGPUBool,
    minBindingSize: u64,
};

pub const WGPUSamplerBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
};

pub const WGPUTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    sampleType: u32,
    viewDimension: base.WGPUTextureViewDimension,
    multisampled: base.WGPUBool,
};

pub const WGPUStorageTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    access: u32,
    format: base.WGPUTextureFormat,
    viewDimension: base.WGPUTextureViewDimension,
};

pub const WGPUBindGroupLayoutEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    visibility: base.WGPUShaderStageFlags,
    bindingArraySize: u32,
    buffer: WGPUBufferBindingLayout,
    sampler: WGPUSamplerBindingLayout,
    texture: WGPUTextureBindingLayout,
    storageTexture: WGPUStorageTextureBindingLayout,
};

pub const WGPUBindGroupEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    buffer: base.WGPUBuffer,
    offset: u64,
    size: u64,
    sampler: base.WGPUSampler,
    textureView: base.WGPUTextureView,
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
    label: base.WGPUStringView,
    entryCount: usize,
    entries: ?[*]const WGPUBindGroupLayoutEntry,
};

pub const WGPUBindGroupDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    layout: base.WGPUBindGroupLayout,
    entryCount: usize,
    entries: [*]const WGPUBindGroupEntry,
};

pub const WGPUPipelineLayoutDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    bindGroupLayoutCount: usize,
    bindGroupLayouts: [*]const base.WGPUBindGroupLayout,
    immediateSize: u32,
};

pub const WGPUBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    usage: base.WGPUBufferUsage,
    size: u64,
    mappedAtCreation: base.WGPUBool,
};

pub const WGPUShaderModuleDescriptor = extern struct {
    nextInChain: ?*callbacks.WGPUChainedStruct,
    label: base.WGPUStringView,
};

pub const WGPUShaderSourceWGSL = extern struct {
    chain: callbacks.WGPUChainedStruct,
    code: base.WGPUStringView,
};

pub const WGPUShaderSourceMSL = extern struct {
    chain: callbacks.WGPUChainedStruct,
    code: base.WGPUStringView,
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
    code: base.WGPUStringView,
    workgroup_size_x: u32,
    workgroup_size_y: u32,
    workgroup_size_z: u32,
};

pub const WGPUConstantEntry = extern struct {
    nextInChain: ?*anyopaque,
    key: base.WGPUStringView,
    value: f64,
};

pub const WGPUComputeState = extern struct {
    nextInChain: ?*anyopaque,
    module: base.WGPUShaderModule,
    entryPoint: base.WGPUStringView,
    constantCount: usize,
    constants: ?[*]const WGPUConstantEntry,
};

pub const WGPUComputePipelineDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    layout: ?*anyopaque,
    compute: WGPUComputeState,
};

pub const WGPUComputePassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    timestampWrites: ?*const WGPUPassTimestampWrites,
};

pub const WGPUPassTimestampWrites = extern struct {
    nextInChain: ?*anyopaque,
    querySet: base.WGPUQuerySet,
    beginningOfPassWriteIndex: u32,
    endOfPassWriteIndex: u32,
};

pub const WGPUCommandEncoderDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
};

pub const WGPUCommandBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
};

pub const WGPUQuerySetDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    type: base.WGPUQueryType,
    count: u32,
};

pub const WGPUSamplerDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
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
    view: base.WGPUTextureView,
    depthSlice: u32,
    resolveTarget: base.WGPUTextureView,
    loadOp: u32,
    storeOp: u32,
    clearValue: WGPUColor,
};

pub const WGPURenderPassDepthStencilAttachment = extern struct {
    view: base.WGPUTextureView,
    depthLoadOp: u32,
    depthStoreOp: u32,
    depthClearValue: f32,
    depthReadOnly: base.WGPUBool,
    stencilLoadOp: u32,
    stencilStoreOp: u32,
    stencilClearValue: u32,
    stencilReadOnly: base.WGPUBool,
};

pub const WGPURenderPassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    colorAttachmentCount: usize,
    colorAttachments: ?[*]const WGPURenderPassColorAttachment,
    depthStencilAttachment: ?*const WGPURenderPassDepthStencilAttachment,
    occlusionQuerySet: base.WGPUQuerySet,
    timestampWrites: ?*const WGPUPassTimestampWrites,
    maxDrawCount: u64,
};
