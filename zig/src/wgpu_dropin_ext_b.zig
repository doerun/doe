const types = @import("wgpu_types.zig");
const p1cap = @import("wgpu_p1_capability_procs.zig");
const p0 = @import("wgpu_p0_procs.zig");
const p1res = @import("wgpu_p1_resource_table_procs.zig");
const p2life = @import("wgpu_p2_lifecycle_procs.zig");
const surface = @import("wgpu_surface_procs.zig");
const texture = @import("wgpu_texture_procs.zig");
const render = @import("wgpu_render_api.zig");
const async_procs = @import("wgpu_async_procs.zig");

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

pub export fn wgpuRenderBundleEncoderSetImmediates(a0: p1res.WGPURenderBundleEncoder, a1: u32, a2: ?*const anyopaque, a3: usize) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1res.WGPURenderBundleEncoder, u32, ?*const anyopaque, usize) callconv(.c) void, "wgpuRenderBundleEncoderSetImmediates");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuRenderBundleEncoderSetIndexBuffer(a0: render.RenderBundleEncoder, a1: types.WGPUBuffer, a2: u32, a3: u64, a4: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, types.WGPUBuffer, u32, u64, u64) callconv(.c) void, "wgpuRenderBundleEncoderSetIndexBuffer");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderBundleEncoderSetLabel(a0: render.RenderBundleEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, types.WGPUStringView) callconv(.c) void, "wgpuRenderBundleEncoderSetLabel");
    proc(a0, a1);
}

pub export fn wgpuRenderBundleEncoderSetPipeline(a0: render.RenderBundleEncoder, a1: types.WGPURenderPipeline) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, types.WGPURenderPipeline) callconv(.c) void, "wgpuRenderBundleEncoderSetPipeline");
    proc(a0, a1);
}

pub export fn wgpuRenderBundleEncoderSetResourceTable(a0: p1res.WGPURenderBundleEncoder, a1: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1res.WGPURenderBundleEncoder, p1res.WGPUResourceTable) callconv(.c) void, "wgpuRenderBundleEncoderSetResourceTable");
    proc(a0, a1);
}

pub export fn wgpuRenderBundleEncoderSetVertexBuffer(a0: render.RenderBundleEncoder, a1: u32, a2: types.WGPUBuffer, a3: u64, a4: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, u32, types.WGPUBuffer, u64, u64) callconv(.c) void, "wgpuRenderBundleEncoderSetVertexBuffer");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderBundleRelease(a0: render.RenderBundle) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundle) callconv(.c) void, "wgpuRenderBundleRelease");
    proc(a0);
}

pub export fn wgpuRenderBundleSetLabel(a0: render.RenderBundle, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundle, types.WGPUStringView) callconv(.c) void, "wgpuRenderBundleSetLabel");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderAddRef(a0: types.WGPURenderPassEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder) callconv(.c) void, "wgpuRenderPassEncoderAddRef");
    proc(a0);
}

pub export fn wgpuRenderPassEncoderBeginOcclusionQuery(a0: types.WGPURenderPassEncoder, a1: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, u32) callconv(.c) void, "wgpuRenderPassEncoderBeginOcclusionQuery");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderEndOcclusionQuery(a0: types.WGPURenderPassEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder) callconv(.c) void, "wgpuRenderPassEncoderEndOcclusionQuery");
    proc(a0);
}

pub export fn wgpuRenderPassEncoderExecuteBundles(a0: types.WGPURenderPassEncoder, a1: usize, a2: [*]const render.RenderBundle) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, usize, [*]const render.RenderBundle) callconv(.c) void, "wgpuRenderPassEncoderExecuteBundles");
    proc(a0, a1, a2);
}

pub export fn wgpuRenderPassEncoderMultiDrawIndexedIndirect(a0: types.WGPURenderPassEncoder, a1: types.WGPUBuffer, a2: u64, a3: u32, a4: types.WGPUBuffer, a5: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, types.WGPUBuffer, u64, u32, types.WGPUBuffer, u64) callconv(.c) void, "wgpuRenderPassEncoderMultiDrawIndexedIndirect");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuRenderPassEncoderMultiDrawIndirect(a0: types.WGPURenderPassEncoder, a1: types.WGPUBuffer, a2: u64, a3: u32, a4: types.WGPUBuffer, a5: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, types.WGPUBuffer, u64, u32, types.WGPUBuffer, u64) callconv(.c) void, "wgpuRenderPassEncoderMultiDrawIndirect");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuRenderPassEncoderPixelLocalStorageBarrier(a0: types.WGPURenderPassEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder) callconv(.c) void, "wgpuRenderPassEncoderPixelLocalStorageBarrier");
    proc(a0);
}

pub export fn wgpuRenderPassEncoderSetBlendConstant(a0: types.WGPURenderPassEncoder, a1: *const render.BlendColor) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, *const render.BlendColor) callconv(.c) void, "wgpuRenderPassEncoderSetBlendConstant");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderSetImmediates(a0: types.WGPURenderPassEncoder, a1: u32, a2: ?*const anyopaque, a3: usize) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, u32, ?*const anyopaque, usize) callconv(.c) void, "wgpuRenderPassEncoderSetImmediates");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuRenderPassEncoderSetResourceTable(a0: types.WGPURenderPassEncoder, a1: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, p1res.WGPUResourceTable) callconv(.c) void, "wgpuRenderPassEncoderSetResourceTable");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderSetScissorRect(a0: types.WGPURenderPassEncoder, a1: u32, a2: u32, a3: u32, a4: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, u32, u32, u32, u32) callconv(.c) void, "wgpuRenderPassEncoderSetScissorRect");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderPassEncoderSetStencilReference(a0: types.WGPURenderPassEncoder, a1: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, u32) callconv(.c) void, "wgpuRenderPassEncoderSetStencilReference");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderSetViewport(a0: types.WGPURenderPassEncoder, a1: f32, a2: f32, a3: f32, a4: f32, a5: f32, a6: f32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, f32, f32, f32, f32, f32, f32) callconv(.c) void, "wgpuRenderPassEncoderSetViewport");
    proc(a0, a1, a2, a3, a4, a5, a6);
}

pub export fn wgpuRenderPassEncoderWriteTimestamp(a0: types.WGPURenderPassEncoder, a1: types.WGPUQuerySet, a2: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPassEncoder, types.WGPUQuerySet, u32) callconv(.c) void, "wgpuRenderPassEncoderWriteTimestamp");
    proc(a0, a1, a2);
}

pub export fn wgpuRenderPipelineAddRef(a0: types.WGPURenderPipeline) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPipeline) callconv(.c) void, "wgpuRenderPipelineAddRef");
    proc(a0);
}

pub export fn wgpuRenderPipelineGetBindGroupLayout(a0: types.WGPURenderPipeline, a1: u32) callconv(.c) types.WGPUBindGroupLayout {
    const proc = resolveRequiredProc(*const fn (types.WGPURenderPipeline, u32) callconv(.c) types.WGPUBindGroupLayout, "wgpuRenderPipelineGetBindGroupLayout");
    return proc(a0, a1);
}

pub export fn wgpuResourceTableAddRef(a0: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1res.WGPUResourceTable) callconv(.c) void, "wgpuResourceTableAddRef");
    proc(a0);
}

pub export fn wgpuResourceTableDestroy(a0: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1res.WGPUResourceTable) callconv(.c) void, "wgpuResourceTableDestroy");
    proc(a0);
}

pub export fn wgpuResourceTableGetSize(a0: p1res.WGPUResourceTable) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (p1res.WGPUResourceTable) callconv(.c) u32, "wgpuResourceTableGetSize");
    return proc(a0);
}

pub export fn wgpuResourceTableInsertBinding(a0: p1res.WGPUResourceTable, a1: *const p1res.BindingResource) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (p1res.WGPUResourceTable, *const p1res.BindingResource) callconv(.c) u32, "wgpuResourceTableInsertBinding");
    return proc(a0, a1);
}

pub export fn wgpuResourceTableRelease(a0: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1res.WGPUResourceTable) callconv(.c) void, "wgpuResourceTableRelease");
    proc(a0);
}

pub export fn wgpuResourceTableRemoveBinding(a0: p1res.WGPUResourceTable, a1: u32) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (p1res.WGPUResourceTable, u32) callconv(.c) types.WGPUStatus, "wgpuResourceTableRemoveBinding");
    return proc(a0, a1);
}

pub export fn wgpuResourceTableUpdate(a0: p1res.WGPUResourceTable, a1: u32, a2: *const p1res.BindingResource) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (p1res.WGPUResourceTable, u32, *const p1res.BindingResource) callconv(.c) types.WGPUStatus, "wgpuResourceTableUpdate");
    return proc(a0, a1, a2);
}

pub export fn wgpuSamplerAddRef(a0: types.WGPUSampler) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUSampler) callconv(.c) void, "wgpuSamplerAddRef");
    proc(a0);
}

pub export fn wgpuSamplerRelease(a0: types.WGPUSampler) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUSampler) callconv(.c) void, "wgpuSamplerRelease");
    proc(a0);
}

pub export fn wgpuShaderModuleAddRef(a0: types.WGPUShaderModule) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUShaderModule) callconv(.c) void, "wgpuShaderModuleAddRef");
    proc(a0);
}

pub export fn wgpuShaderModuleGetCompilationInfo(a0: types.WGPUShaderModule, a1: async_procs.CompilationInfoCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = resolveRequiredProc(*const fn (types.WGPUShaderModule, async_procs.CompilationInfoCallbackInfo) callconv(.c) types.WGPUFuture, "wgpuShaderModuleGetCompilationInfo");
    return proc(a0, a1);
}

pub export fn wgpuSharedBufferMemoryAddRef(a0: p2life.WGPUSharedBufferMemory) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUSharedBufferMemory) callconv(.c) void, "wgpuSharedBufferMemoryAddRef");
    proc(a0);
}

pub export fn wgpuSharedFenceAddRef(a0: p2life.WGPUSharedFence) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUSharedFence) callconv(.c) void, "wgpuSharedFenceAddRef");
    proc(a0);
}

pub export fn wgpuSharedTextureMemoryAddRef(a0: p2life.WGPUSharedTextureMemory) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUSharedTextureMemory) callconv(.c) void, "wgpuSharedTextureMemoryAddRef");
    proc(a0);
}

pub export fn wgpuSupportedFeaturesFreeMembers(a0: p1cap.SupportedFeatures) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.SupportedFeatures) callconv(.c) void, "wgpuSupportedFeaturesFreeMembers");
    proc(a0);
}

pub export fn wgpuSupportedInstanceFeaturesFreeMembers(a0: p1cap.SupportedInstanceFeatures) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.SupportedInstanceFeatures) callconv(.c) void, "wgpuSupportedInstanceFeaturesFreeMembers");
    proc(a0);
}

pub export fn wgpuSupportedWGSLLanguageFeaturesFreeMembers(a0: p1cap.SupportedWGSLLanguageFeatures) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.SupportedWGSLLanguageFeatures) callconv(.c) void, "wgpuSupportedWGSLLanguageFeaturesFreeMembers");
    proc(a0);
}

pub export fn wgpuSurfaceAddRef(a0: p2life.WGPUSurface) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUSurface) callconv(.c) void, "wgpuSurfaceAddRef");
    proc(a0);
}

pub export fn wgpuSurfaceCapabilitiesFreeMembers(a0: surface.SurfaceCapabilities) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (surface.SurfaceCapabilities) callconv(.c) void, "wgpuSurfaceCapabilitiesFreeMembers");
    proc(a0);
}

pub export fn wgpuSurfaceConfigure(a0: surface.Surface, a1: *const surface.SurfaceConfiguration) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (surface.Surface, *const surface.SurfaceConfiguration) callconv(.c) void, "wgpuSurfaceConfigure");
    proc(a0, a1);
}

pub export fn wgpuSurfaceGetCapabilities(a0: surface.Surface, a1: types.WGPUAdapter, a2: *surface.SurfaceCapabilities) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (surface.Surface, types.WGPUAdapter, *surface.SurfaceCapabilities) callconv(.c) u32, "wgpuSurfaceGetCapabilities");
    return proc(a0, a1, a2);
}

pub export fn wgpuSurfaceGetCurrentTexture(a0: surface.Surface, a1: *surface.SurfaceTexture) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (surface.Surface, *surface.SurfaceTexture) callconv(.c) void, "wgpuSurfaceGetCurrentTexture");
    proc(a0, a1);
}

pub export fn wgpuSurfacePresent(a0: surface.Surface) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (surface.Surface) callconv(.c) u32, "wgpuSurfacePresent");
    return proc(a0);
}

pub export fn wgpuSurfaceRelease(a0: surface.Surface) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (surface.Surface) callconv(.c) void, "wgpuSurfaceRelease");
    proc(a0);
}

pub export fn wgpuSurfaceUnconfigure(a0: surface.Surface) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (surface.Surface) callconv(.c) void, "wgpuSurfaceUnconfigure");
    proc(a0);
}

pub export fn wgpuTexelBufferViewAddRef(a0: p2life.WGPUTexelBufferView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUTexelBufferView) callconv(.c) void, "wgpuTexelBufferViewAddRef");
    proc(a0);
}

pub export fn wgpuTextureAddRef(a0: types.WGPUTexture) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) void, "wgpuTextureAddRef");
    proc(a0);
}

pub export fn wgpuTextureDestroy(a0: types.WGPUTexture) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) void, "wgpuTextureDestroy");
    proc(a0);
}

pub export fn wgpuTextureGetDepthOrArrayLayers(a0: types.WGPUTexture) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) u32, "wgpuTextureGetDepthOrArrayLayers");
    return proc(a0);
}

pub export fn wgpuTextureGetDimension(a0: types.WGPUTexture) callconv(.c) types.WGPUTextureDimension {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureDimension, "wgpuTextureGetDimension");
    return proc(a0);
}

pub export fn wgpuTextureGetFormat(a0: types.WGPUTexture) callconv(.c) types.WGPUTextureFormat {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureFormat, "wgpuTextureGetFormat");
    return proc(a0);
}

pub export fn wgpuTextureGetHeight(a0: types.WGPUTexture) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) u32, "wgpuTextureGetHeight");
    return proc(a0);
}

pub export fn wgpuTextureGetMipLevelCount(a0: types.WGPUTexture) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) u32, "wgpuTextureGetMipLevelCount");
    return proc(a0);
}

pub export fn wgpuTextureGetSampleCount(a0: types.WGPUTexture) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) u32, "wgpuTextureGetSampleCount");
    return proc(a0);
}

pub export fn wgpuTextureGetTextureBindingViewDimension(a0: types.WGPUTexture) callconv(.c) types.WGPUTextureViewDimension {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureViewDimension, "wgpuTextureGetTextureBindingViewDimension");
    return proc(a0);
}

pub export fn wgpuTextureGetUsage(a0: types.WGPUTexture) callconv(.c) types.WGPUTextureUsage {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) types.WGPUTextureUsage, "wgpuTextureGetUsage");
    return proc(a0);
}

pub export fn wgpuTextureGetWidth(a0: types.WGPUTexture) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (types.WGPUTexture) callconv(.c) u32, "wgpuTextureGetWidth");
    return proc(a0);
}

pub export fn wgpuTextureViewAddRef(a0: types.WGPUTextureView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUTextureView) callconv(.c) void, "wgpuTextureViewAddRef");
    proc(a0);
}
