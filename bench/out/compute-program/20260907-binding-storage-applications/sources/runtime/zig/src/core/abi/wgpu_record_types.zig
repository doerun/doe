const proc_types = @import("wgpu_proc_types.zig");

pub const WGPUBuffer = proc_types.base.WGPUBuffer;
pub const WGPUBufferUsage = proc_types.base.WGPUBufferUsage;
pub const WGPUTexture = proc_types.base.WGPUTexture;
pub const WGPUTextureFormat = proc_types.base.WGPUTextureFormat;
pub const WGPUTextureUsage = proc_types.base.WGPUTextureUsage;
pub const WGPUTextureDimension = proc_types.base.WGPUTextureDimension;
pub const WGPUBindGroup = proc_types.base.WGPUBindGroup;
pub const WGPUBindGroupLayout = proc_types.base.WGPUBindGroupLayout;
pub const WGPUTextureView = proc_types.base.WGPUTextureView;
pub const WGPURenderPipeline = proc_types.base.WGPURenderPipeline;
pub const WGPUShaderModule = proc_types.base.WGPUShaderModule;
pub const WGPUAdapter = proc_types.base.WGPUAdapter;
pub const WGPUDevice = proc_types.base.WGPUDevice;

pub const WGPUBindGroupLayoutEntry = proc_types.descriptor.WGPUBindGroupLayoutEntry;
pub const WGPUBindGroupEntry = proc_types.descriptor.WGPUBindGroupEntry;
pub const WGPURequestAdapterStatus = proc_types.descriptor.WGPURequestAdapterStatus;
pub const WGPURequestDeviceStatus = proc_types.descriptor.WGPURequestDeviceStatus;
