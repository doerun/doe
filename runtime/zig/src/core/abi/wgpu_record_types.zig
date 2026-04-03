const base = @import("wgpu_base_types.zig");
const descriptor = @import("wgpu_descriptor_types.zig");

pub const WGPUBuffer = base.WGPUBuffer;
pub const WGPUBufferUsage = base.WGPUBufferUsage;
pub const WGPUTexture = base.WGPUTexture;
pub const WGPUTextureFormat = base.WGPUTextureFormat;
pub const WGPUTextureUsage = base.WGPUTextureUsage;
pub const WGPUTextureDimension = base.WGPUTextureDimension;
pub const WGPUBindGroup = base.WGPUBindGroup;
pub const WGPUBindGroupLayout = base.WGPUBindGroupLayout;
pub const WGPUTextureView = base.WGPUTextureView;
pub const WGPURenderPipeline = base.WGPURenderPipeline;
pub const WGPUShaderModule = base.WGPUShaderModule;
pub const WGPUAdapter = base.WGPUAdapter;
pub const WGPUDevice = base.WGPUDevice;

pub const WGPUBindGroupLayoutEntry = descriptor.WGPUBindGroupLayoutEntry;
pub const WGPUBindGroupEntry = descriptor.WGPUBindGroupEntry;
pub const WGPURequestAdapterStatus = descriptor.WGPURequestAdapterStatus;
pub const WGPURequestDeviceStatus = descriptor.WGPURequestDeviceStatus;
