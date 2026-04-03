const abi_base = @import("../../core/abi/wgpu_base_types.zig");
const abi_descriptor = @import("../../core/abi/wgpu_descriptor_types.zig");

pub const WGPUSType_RenderPassPixelLocalStorage: abi_base.WGPUSType = 0x00050010;
pub const WGPUSType_PipelineLayoutPixelLocalStorage: abi_base.WGPUSType = 0x00050011;

pub const RenderColor = extern struct {
    r: f64,
    g: f64,
    b: f64,
    a: f64,
};

pub const RenderBundleDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: abi_base.WGPUStringView,
};

pub const RenderBundleEncoderDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: abi_base.WGPUStringView,
    colorFormatCount: usize,
    colorFormats: [*]const abi_base.WGPUTextureFormat,
    depthStencilFormat: abi_base.WGPUTextureFormat,
    sampleCount: u32,
    depthReadOnly: abi_base.WGPUBool,
    stencilReadOnly: abi_base.WGPUBool,
};

pub const RenderDrawIndirectArgs = extern struct {
    vertex_count: u32,
    instance_count: u32,
    first_vertex: u32,
    first_instance: u32,
};

pub const RenderDrawIndexedIndirectArgs = extern struct {
    index_count: u32,
    instance_count: u32,
    first_index: u32,
    base_vertex: i32,
    first_instance: u32,
};

pub const RenderPassColorAttachment = extern struct {
    nextInChain: ?*anyopaque,
    view: abi_base.WGPUTextureView,
    depthSlice: u32,
    resolveTarget: abi_base.WGPUTextureView,
    loadOp: u32,
    storeOp: u32,
    clearValue: RenderColor,
};

pub const RenderPassStorageAttachment = extern struct {
    nextInChain: ?*anyopaque,
    offset: u64,
    storage: abi_base.WGPUTextureView,
    loadOp: u32,
    storeOp: u32,
    clearValue: RenderColor,
};

pub const PipelineLayoutStorageAttachment = extern struct {
    nextInChain: ?*anyopaque,
    offset: u64,
    format: abi_base.WGPUTextureFormat,
};

pub const PipelineLayoutPixelLocalStorage = extern struct {
    chain: abi_descriptor.WGPUChainedStruct,
    totalPixelLocalStorageSize: u64,
    storageAttachmentCount: usize,
    storageAttachments: [*]const PipelineLayoutStorageAttachment,
};

pub const RenderPassPixelLocalStorage = extern struct {
    chain: abi_descriptor.WGPUChainedStruct,
    totalPixelLocalStorageSize: u64,
    storageAttachmentCount: usize,
    storageAttachments: [*]const RenderPassStorageAttachment,
};

pub const RenderPassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: abi_base.WGPUStringView,
    colorAttachmentCount: usize,
    colorAttachments: [*]const RenderPassColorAttachment,
    depthStencilAttachment: ?*const anyopaque,
    occlusionQuerySet: abi_base.WGPUQuerySet,
    timestampWrites: ?*const abi_descriptor.WGPUPassTimestampWrites,
    maxDrawCount: u64,
};

pub const RenderPassDepthStencilAttachment = extern struct {
    nextInChain: ?*anyopaque,
    view: abi_base.WGPUTextureView,
    depthLoadOp: u32,
    depthStoreOp: u32,
    depthClearValue: f32,
    depthReadOnly: abi_base.WGPUBool,
    stencilLoadOp: u32,
    stencilStoreOp: u32,
    stencilClearValue: u32,
    stencilReadOnly: abi_base.WGPUBool,
};

pub const RenderConstantEntry = extern struct {
    nextInChain: ?*anyopaque,
    key: abi_base.WGPUStringView,
    value: f64,
};

pub const RenderVertexState = extern struct {
    nextInChain: ?*anyopaque,
    module: abi_base.WGPUShaderModule,
    entryPoint: abi_base.WGPUStringView,
    constantCount: usize,
    constants: ?[*]const RenderConstantEntry,
    bufferCount: usize,
    buffers: ?*const anyopaque,
};

pub const RenderVertexAttribute = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
    offset: u64,
    shaderLocation: u32,
};

pub const RenderVertexBufferLayout = extern struct {
    nextInChain: ?*anyopaque,
    stepMode: u32,
    arrayStride: u64,
    attributeCount: usize,
    attributes: ?[*]const RenderVertexAttribute,
};

pub const RenderColorTargetState = extern struct {
    nextInChain: ?*anyopaque,
    format: abi_base.WGPUTextureFormat,
    blend: ?*const anyopaque,
    writeMask: u64,
};

pub const RenderFragmentState = extern struct {
    nextInChain: ?*anyopaque,
    module: abi_base.WGPUShaderModule,
    entryPoint: abi_base.WGPUStringView,
    constantCount: usize,
    constants: ?[*]const RenderConstantEntry,
    targetCount: usize,
    targets: [*]const RenderColorTargetState,
};

pub const RenderPrimitiveState = extern struct {
    nextInChain: ?*anyopaque,
    topology: u32,
    stripIndexFormat: u32,
    frontFace: u32,
    cullMode: u32,
    unclippedDepth: abi_base.WGPUBool,
};

pub const RenderMultisampleState = extern struct {
    nextInChain: ?*anyopaque,
    count: u32,
    mask: u32,
    alphaToCoverageEnabled: abi_base.WGPUBool,
};

pub const RenderStencilFaceState = extern struct {
    compare: u32,
    failOp: u32,
    depthFailOp: u32,
    passOp: u32,
};

pub const RenderDepthStencilState = extern struct {
    nextInChain: ?*anyopaque,
    format: abi_base.WGPUTextureFormat,
    depthWriteEnabled: u32,
    depthCompare: u32,
    stencilFront: RenderStencilFaceState,
    stencilBack: RenderStencilFaceState,
    stencilReadMask: u32,
    stencilWriteMask: u32,
    depthBias: i32,
    depthBiasSlopeScale: f32,
    depthBiasClamp: f32,
};

pub const RenderPipelineDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: abi_base.WGPUStringView,
    layout: abi_base.WGPUPipelineLayout,
    vertex: RenderVertexState,
    primitive: RenderPrimitiveState,
    depthStencil: ?*const RenderDepthStencilState,
    multisample: RenderMultisampleState,
    fragment: ?*const RenderFragmentState,
};
