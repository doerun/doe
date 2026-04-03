const std = @import("std");

pub const WGPUInstance = ?*anyopaque;
pub const WGPUAdapter = ?*anyopaque;
pub const WGPUDevice = ?*anyopaque;
pub const WGPUQueue = ?*anyopaque;
pub const WGPUBuffer = ?*anyopaque;
pub const WGPUTexture = ?*anyopaque;
pub const WGPUTextureView = ?*anyopaque;
pub const WGPUExternalTexture = ?*anyopaque;
pub const WGPUShaderModule = ?*anyopaque;
pub const WGPUSampler = ?*anyopaque;
pub const WGPUComputePipeline = ?*anyopaque;
pub const WGPURenderPipeline = ?*anyopaque;
pub const WGPUComputePassEncoder = ?*anyopaque;
pub const WGPURenderPassEncoder = ?*anyopaque;
pub const WGPUBindGroupLayout = ?*anyopaque;
pub const WGPUBindGroup = ?*anyopaque;
pub const WGPUPipelineLayout = ?*anyopaque;
pub const WGPUCommandEncoder = ?*anyopaque;
pub const WGPUCommandBuffer = ?*anyopaque;
pub const WGPUQuerySet = ?*anyopaque;

pub const WGPUFuture = extern struct {
    id: u64,
};

pub const WGPUStringView = extern struct {
    data: ?[*]const u8,
    length: usize,
};

pub const WGPUBool = u32;
pub const WGPUStatus = u32;

pub const WGPU_STRLEN = std.math.maxInt(usize);
pub const WGPU_FALSE: WGPUBool = 0;
pub const WGPU_TRUE: WGPUBool = 1;
pub const WGPUStatus_Success: WGPUStatus = 1;
