const types = @import("core/abi/wgpu_types.zig");
const p1cap = @import("wgpu_p1_capability_procs.zig");
const p2life = @import("wgpu_p2_lifecycle_procs.zig");
const surface = @import("full/surface/wgpu_surface_procs.zig");

extern fn wgpuGetProcAddress(name: types.WGPUStringView) callconv(.c) p1cap.WGPUProc;
extern fn doeWgpuDropinAbortMissingRequiredSymbol(name: types.WGPUStringView) callconv(.c) noreturn;

fn symbolView(comptime name: []const u8) types.WGPUStringView {
    return .{ .data = name.ptr, .length = name.len };
}

fn resolveRequiredProc(comptime FnType: type, comptime symbol_name: []const u8) FnType {
    const proc = wgpuGetProcAddress(symbolView(symbol_name)) orelse
        doeWgpuDropinAbortMissingRequiredSymbol(symbolView(symbol_name));
    return @as(FnType, @ptrCast(proc));
}

pub export fn wgpuBindGroupLayoutSetLabel(a0: types.WGPUBindGroupLayout, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUBindGroupLayout, types.WGPUStringView) callconv(.c) void, "wgpuBindGroupLayoutSetLabel");
    proc(a0, a1);
}

pub export fn wgpuBindGroupSetLabel(a0: types.WGPUBindGroup, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUBindGroup, types.WGPUStringView) callconv(.c) void, "wgpuBindGroupSetLabel");
    proc(a0, a1);
}

pub export fn wgpuBufferGetMapState(a0: types.WGPUBuffer) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer) callconv(.c) u32, "wgpuBufferGetMapState");
    return proc(a0);
}

pub export fn wgpuBufferGetMappedRange(a0: types.WGPUBuffer, a1: usize, a2: usize) callconv(.c) ?*anyopaque {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer, usize, usize) callconv(.c) ?*anyopaque, "wgpuBufferGetMappedRange");
    return proc(a0, a1, a2);
}

pub export fn wgpuBufferGetSize(a0: types.WGPUBuffer) callconv(.c) u64 {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer) callconv(.c) u64, "wgpuBufferGetSize");
    return proc(a0);
}

pub export fn wgpuBufferGetUsage(a0: types.WGPUBuffer) callconv(.c) types.WGPUBufferUsage {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer) callconv(.c) types.WGPUBufferUsage, "wgpuBufferGetUsage");
    return proc(a0);
}

pub export fn wgpuBufferReadMappedRange(a0: types.WGPUBuffer, a1: usize, a2: ?*anyopaque, a3: usize) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer, usize, ?*anyopaque, usize) callconv(.c) types.WGPUStatus, "wgpuBufferReadMappedRange");
    return proc(a0, a1, a2, a3);
}

pub export fn wgpuBufferSetLabel(a0: types.WGPUBuffer, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer, types.WGPUStringView) callconv(.c) void, "wgpuBufferSetLabel");
    proc(a0, a1);
}

pub export fn wgpuBufferWriteMappedRange(a0: types.WGPUBuffer, a1: usize, a2: ?*const anyopaque, a3: usize) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer, usize, ?*const anyopaque, usize) callconv(.c) types.WGPUStatus, "wgpuBufferWriteMappedRange");
    return proc(a0, a1, a2, a3);
}

pub export fn wgpuCommandBufferSetLabel(a0: types.WGPUCommandBuffer, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandBuffer, types.WGPUStringView) callconv(.c) void, "wgpuCommandBufferSetLabel");
    proc(a0, a1);
}

pub export fn wgpuCommandEncoderInsertDebugMarker(a0: types.WGPUCommandEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandEncoder, types.WGPUStringView) callconv(.c) void, "wgpuCommandEncoderInsertDebugMarker");
    proc(a0, a1);
}

pub export fn wgpuCommandEncoderPopDebugGroup(a0: types.WGPUCommandEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandEncoder) callconv(.c) void, "wgpuCommandEncoderPopDebugGroup");
    proc(a0);
}

pub export fn wgpuCommandEncoderPushDebugGroup(a0: types.WGPUCommandEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandEncoder, types.WGPUStringView) callconv(.c) void, "wgpuCommandEncoderPushDebugGroup");
    proc(a0, a1);
}

pub export fn wgpuCommandEncoderSetLabel(a0: types.WGPUCommandEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandEncoder, types.WGPUStringView) callconv(.c) void, "wgpuCommandEncoderSetLabel");
    proc(a0, a1);
}

pub export fn wgpuComputePassEncoderInsertDebugMarker(a0: types.WGPUComputePassEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, types.WGPUStringView) callconv(.c) void, "wgpuComputePassEncoderInsertDebugMarker");
    proc(a0, a1);
}

pub export fn wgpuComputePassEncoderPopDebugGroup(a0: types.WGPUComputePassEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder) callconv(.c) void, "wgpuComputePassEncoderPopDebugGroup");
    proc(a0);
}

pub export fn wgpuComputePassEncoderPushDebugGroup(a0: types.WGPUComputePassEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, types.WGPUStringView) callconv(.c) void, "wgpuComputePassEncoderPushDebugGroup");
    proc(a0, a1);
}

pub export fn wgpuComputePassEncoderSetLabel(a0: types.WGPUComputePassEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, types.WGPUStringView) callconv(.c) void, "wgpuComputePassEncoderSetLabel");
    proc(a0, a1);
}

pub export fn wgpuComputePipelineGetBindGroupLayout(a0: types.WGPUComputePipeline, a1: u32) callconv(.c) types.WGPUBindGroupLayout {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePipeline, u32) callconv(.c) types.WGPUBindGroupLayout, "wgpuComputePipelineGetBindGroupLayout");
    return proc(a0, a1);
}

pub export fn wgpuComputePipelineSetLabel(a0: types.WGPUComputePipeline, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePipeline, types.WGPUStringView) callconv(.c) void, "wgpuComputePipelineSetLabel");
    proc(a0, a1);
}

pub export fn wgpuDeviceGetLostFuture(a0: types.WGPUDevice) callconv(.c) types.WGPUFuture {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice) callconv(.c) types.WGPUFuture, "wgpuDeviceGetLostFuture");
    return proc(a0);
}

pub export fn wgpuDeviceSetLabel(a0: types.WGPUDevice, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, types.WGPUStringView) callconv(.c) void, "wgpuDeviceSetLabel");
    proc(a0, a1);
}

pub export fn wgpuExternalTextureRelease(a0: p2life.WGPUExternalTexture) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUExternalTexture) callconv(.c) void, "wgpuExternalTextureRelease");
    proc(a0);
}

pub export fn wgpuExternalTextureSetLabel(a0: p2life.WGPUExternalTexture, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUExternalTexture, types.WGPUStringView) callconv(.c) void, "wgpuExternalTextureSetLabel");
    proc(a0, a1);
}

pub export fn wgpuPipelineLayoutSetLabel(a0: types.WGPUPipelineLayout, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUPipelineLayout, types.WGPUStringView) callconv(.c) void, "wgpuPipelineLayoutSetLabel");
    proc(a0, a1);
}

pub export fn wgpuQuerySetSetLabel(a0: types.WGPUQuerySet, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUQuerySet, types.WGPUStringView) callconv(.c) void, "wgpuQuerySetSetLabel");
    proc(a0, a1);
}

pub export fn wgpuQueueSetLabel(a0: types.WGPUQueue, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUQueue, types.WGPUStringView) callconv(.c) void, "wgpuQueueSetLabel");
    proc(a0, a1);
}

pub export fn wgpuQueueWriteTexture(a0: types.WGPUQueue, a1: *const types.WGPUTexelCopyTextureInfo, a2: ?*const anyopaque, a3: usize, a4: *const types.WGPUTexelCopyBufferLayout, a5: *const types.WGPUExtent3D) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUQueue, *const types.WGPUTexelCopyTextureInfo, ?*const anyopaque, usize, *const types.WGPUTexelCopyBufferLayout, *const types.WGPUExtent3D) callconv(.c) void, "wgpuQueueWriteTexture");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuRenderPassEncoderInsertDebugMarker(a0: types.WGPURenderPassEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, types.WGPUStringView) callconv(.c) void, "wgpuRenderPassEncoderInsertDebugMarker");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderPopDebugGroup(a0: types.WGPURenderPassEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder) callconv(.c) void, "wgpuRenderPassEncoderPopDebugGroup");
    proc(a0);
}

pub export fn wgpuRenderPassEncoderPushDebugGroup(a0: types.WGPURenderPassEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, types.WGPUStringView) callconv(.c) void, "wgpuRenderPassEncoderPushDebugGroup");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderSetLabel(a0: types.WGPURenderPassEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, types.WGPUStringView) callconv(.c) void, "wgpuRenderPassEncoderSetLabel");
    proc(a0, a1);
}

pub export fn wgpuRenderPipelineSetLabel(a0: types.WGPURenderPipeline, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPipeline, types.WGPUStringView) callconv(.c) void, "wgpuRenderPipelineSetLabel");
    proc(a0, a1);
}

pub export fn wgpuSamplerSetLabel(a0: types.WGPUSampler, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUSampler, types.WGPUStringView) callconv(.c) void, "wgpuSamplerSetLabel");
    proc(a0, a1);
}

pub export fn wgpuShaderModuleSetLabel(a0: types.WGPUShaderModule, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUShaderModule, types.WGPUStringView) callconv(.c) void, "wgpuShaderModuleSetLabel");
    proc(a0, a1);
}

pub export fn wgpuSurfaceSetLabel(a0: surface.Surface, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (surface.Surface, types.WGPUStringView) callconv(.c) void, "wgpuSurfaceSetLabel");
    proc(a0, a1);
}

pub export fn wgpuTextureSetLabel(a0: types.WGPUTexture, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture, types.WGPUStringView) callconv(.c) void, "wgpuTextureSetLabel");
    proc(a0, a1);
}

pub export fn wgpuTextureViewSetLabel(a0: types.WGPUTextureView, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUTextureView, types.WGPUStringView) callconv(.c) void, "wgpuTextureViewSetLabel");
    proc(a0, a1);
}
