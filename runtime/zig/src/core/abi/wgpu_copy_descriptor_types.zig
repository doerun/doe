const core = @import("wgpu_core_base_types.zig");
const texture = @import("wgpu_texture_base_types.zig");
const callbacks = @import("wgpu_callback_descriptor_types.zig");

pub const WGPUExtent3D = extern struct {
    width: u32,
    height: u32,
    depthOrArrayLayers: u32,
};

pub const WGPUExtent2D = extern struct {
    width: u32,
    height: u32,
};

pub const WGPUOrigin3D = extern struct {
    x: u32,
    y: u32,
    z: u32,
};

pub const WGPUTexelCopyBufferLayout = extern struct {
    offset: u64,
    bytesPerRow: u32,
    rowsPerImage: u32,
};

pub const WGPUTexelCopyBufferInfo = extern struct {
    layout: WGPUTexelCopyBufferLayout,
    buffer: core.WGPUBuffer,
};

pub const WGPUTexelCopyTextureInfo = extern struct {
    texture: core.WGPUTexture,
    mipLevel: u32,
    origin: WGPUOrigin3D,
    aspect: texture.WGPUTextureAspect,
};

pub const WGPUCopyTextureForBrowserOptions = extern struct {
    nextInChain: ?*callbacks.WGPUChainedStruct,
    flipY: core.WGPUBool,
    needsColorSpaceConversion: core.WGPUBool,
    srcAlphaMode: core.WGPUAlphaMode,
    srcTransferFunctionParameters: ?[*]const f32,
    conversionMatrix: ?[*]const f32,
    dstTransferFunctionParameters: ?[*]const f32,
    dstAlphaMode: core.WGPUAlphaMode,
    internalUsage: core.WGPUBool,
};

pub const WGPUImageCopyExternalTexture = extern struct {
    nextInChain: ?*callbacks.WGPUChainedStruct,
    externalTexture: core.WGPUExternalTexture,
    origin: WGPUOrigin3D,
    naturalSize: WGPUExtent2D,
};
