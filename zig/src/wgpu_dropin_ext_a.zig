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

fn symbolView(comptime name: []const u8) types.WGPUStringView {
    return .{ .data = name.ptr, .length = name.len };
}

fn resolveRequiredProc(comptime FnType: type, comptime symbol_name: []const u8) FnType {
    const proc = wgpuGetProcAddress(symbolView(symbol_name)) orelse
        @panic("doe drop-in missing symbol: " ++ symbol_name);
    return @as(FnType, @ptrCast(proc));
}

pub export fn wgpuAdapterAddRef(a0: types.WGPUAdapter) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter) callconv(.c) void, "wgpuAdapterAddRef");
    proc(a0);
}

pub export fn wgpuAdapterGetFeatures(a0: types.WGPUAdapter, a1: *p1cap.SupportedFeatures) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter, *p1cap.SupportedFeatures) callconv(.c) void, "wgpuAdapterGetFeatures");
    proc(a0, a1);
}

pub export fn wgpuAdapterGetFormatCapabilities(a0: types.WGPUAdapter, a1: types.WGPUTextureFormat, a2: *p1cap.DawnFormatCapabilities) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter, types.WGPUTextureFormat, *p1cap.DawnFormatCapabilities) callconv(.c) types.WGPUStatus, "wgpuAdapterGetFormatCapabilities");
    return proc(a0, a1, a2);
}

pub export fn wgpuAdapterGetInfo(a0: types.WGPUAdapter, a1: *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter, *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus, "wgpuAdapterGetInfo");
    return proc(a0, a1);
}

pub export fn wgpuAdapterGetInstance(a0: types.WGPUAdapter) callconv(.c) types.WGPUInstance {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter) callconv(.c) types.WGPUInstance, "wgpuAdapterGetInstance");
    return proc(a0);
}

pub export fn wgpuAdapterGetLimits(a0: types.WGPUAdapter, a1: *p1cap.Limits) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter, *p1cap.Limits) callconv(.c) types.WGPUStatus, "wgpuAdapterGetLimits");
    return proc(a0, a1);
}

pub export fn wgpuAdapterInfoFreeMembers(a0: p1cap.AdapterInfo) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.AdapterInfo) callconv(.c) void, "wgpuAdapterInfoFreeMembers");
    proc(a0);
}

pub export fn wgpuAdapterPropertiesMemoryHeapsFreeMembers(a0: p1cap.AdapterPropertiesMemoryHeaps) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.AdapterPropertiesMemoryHeaps) callconv(.c) void, "wgpuAdapterPropertiesMemoryHeapsFreeMembers");
    proc(a0);
}

pub export fn wgpuAdapterPropertiesSubgroupMatrixConfigsFreeMembers(a0: p1cap.AdapterPropertiesSubgroupMatrixConfigs) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.AdapterPropertiesSubgroupMatrixConfigs) callconv(.c) void, "wgpuAdapterPropertiesSubgroupMatrixConfigsFreeMembers");
    proc(a0);
}

pub export fn wgpuBindGroupAddRef(a0: types.WGPUBindGroup) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUBindGroup) callconv(.c) void, "wgpuBindGroupAddRef");
    proc(a0);
}

pub export fn wgpuBindGroupLayoutAddRef(a0: types.WGPUBindGroupLayout) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUBindGroupLayout) callconv(.c) void, "wgpuBindGroupLayoutAddRef");
    proc(a0);
}

pub export fn wgpuBufferAddRef(a0: types.WGPUBuffer) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer) callconv(.c) void, "wgpuBufferAddRef");
    proc(a0);
}

pub export fn wgpuBufferDestroy(a0: types.WGPUBuffer) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUBuffer) callconv(.c) void, "wgpuBufferDestroy");
    proc(a0);
}

pub export fn wgpuCommandBufferAddRef(a0: types.WGPUCommandBuffer) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandBuffer) callconv(.c) void, "wgpuCommandBufferAddRef");
    proc(a0);
}

pub export fn wgpuCommandEncoderAddRef(a0: types.WGPUCommandEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandEncoder) callconv(.c) void, "wgpuCommandEncoderAddRef");
    proc(a0);
}

pub export fn wgpuCommandEncoderClearBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandEncoder, types.WGPUBuffer, u64, u64) callconv(.c) void, "wgpuCommandEncoderClearBuffer");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuCommandEncoderWriteBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: [*]const u8, a4: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUCommandEncoder, types.WGPUBuffer, u64, [*]const u8, u64) callconv(.c) void, "wgpuCommandEncoderWriteBuffer");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuComputePassEncoderAddRef(a0: types.WGPUComputePassEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder) callconv(.c) void, "wgpuComputePassEncoderAddRef");
    proc(a0);
}

pub export fn wgpuComputePassEncoderDispatchWorkgroupsIndirect(a0: types.WGPUComputePassEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, types.WGPUBuffer, u64) callconv(.c) void, "wgpuComputePassEncoderDispatchWorkgroupsIndirect");
    proc(a0, a1, a2);
}

pub export fn wgpuComputePassEncoderSetImmediates(a0: types.WGPUComputePassEncoder, a1: u32, a2: ?*const anyopaque, a3: usize) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, u32, ?*const anyopaque, usize) callconv(.c) void, "wgpuComputePassEncoderSetImmediates");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuComputePassEncoderSetResourceTable(a0: types.WGPUComputePassEncoder, a1: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, p1res.WGPUResourceTable) callconv(.c) void, "wgpuComputePassEncoderSetResourceTable");
    proc(a0, a1);
}

pub export fn wgpuComputePassEncoderWriteTimestamp(a0: types.WGPUComputePassEncoder, a1: types.WGPUQuerySet, a2: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, types.WGPUQuerySet, u32) callconv(.c) void, "wgpuComputePassEncoderWriteTimestamp");
    proc(a0, a1, a2);
}

pub export fn wgpuComputePipelineAddRef(a0: types.WGPUComputePipeline) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePipeline) callconv(.c) void, "wgpuComputePipelineAddRef");
    proc(a0);
}

pub export fn wgpuDawnDrmFormatCapabilitiesFreeMembers(a0: p1cap.DawnDrmFormatCapabilities) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.DawnDrmFormatCapabilities) callconv(.c) void, "wgpuDawnDrmFormatCapabilitiesFreeMembers");
    proc(a0);
}

pub export fn wgpuDeviceAddRef(a0: types.WGPUDevice) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice) callconv(.c) void, "wgpuDeviceAddRef");
    proc(a0);
}

pub export fn wgpuDeviceCreateComputePipelineAsync(a0: types.WGPUDevice, a1: *const types.WGPUComputePipelineDescriptor, a2: p0.CreateComputePipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *const types.WGPUComputePipelineDescriptor, p0.CreateComputePipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture, "wgpuDeviceCreateComputePipelineAsync");
    return proc(a0, a1, a2);
}

pub export fn wgpuDeviceCreateRenderBundleEncoder(a0: types.WGPUDevice, a1: *const anyopaque) callconv(.c) render.RenderBundleEncoder {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *const anyopaque) callconv(.c) render.RenderBundleEncoder, "wgpuDeviceCreateRenderBundleEncoder");
    return proc(a0, a1);
}

pub export fn wgpuDeviceCreateRenderPipelineAsync(a0: types.WGPUDevice, a1: *const anyopaque, a2: async_procs.CreateRenderPipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *const anyopaque, async_procs.CreateRenderPipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture, "wgpuDeviceCreateRenderPipelineAsync");
    return proc(a0, a1, a2);
}

pub export fn wgpuDeviceCreateResourceTable(a0: types.WGPUDevice, a1: *const p1res.ResourceTableDescriptor) callconv(.c) p1res.WGPUResourceTable {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *const p1res.ResourceTableDescriptor) callconv(.c) p1res.WGPUResourceTable, "wgpuDeviceCreateResourceTable");
    return proc(a0, a1);
}

pub export fn wgpuDeviceCreateSampler(a0: types.WGPUDevice, a1: ?*const anyopaque) callconv(.c) types.WGPUSampler {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, ?*const anyopaque) callconv(.c) types.WGPUSampler, "wgpuDeviceCreateSampler");
    return proc(a0, a1);
}

pub export fn wgpuDeviceDestroy(a0: types.WGPUDevice) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice) callconv(.c) void, "wgpuDeviceDestroy");
    proc(a0);
}

pub export fn wgpuDeviceGetAdapter(a0: types.WGPUDevice) callconv(.c) types.WGPUAdapter {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice) callconv(.c) types.WGPUAdapter, "wgpuDeviceGetAdapter");
    return proc(a0);
}

pub export fn wgpuDeviceGetAdapterInfo(a0: types.WGPUDevice, a1: *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus, "wgpuDeviceGetAdapterInfo");
    return proc(a0, a1);
}

pub export fn wgpuDeviceGetFeatures(a0: types.WGPUDevice, a1: *p1cap.SupportedFeatures) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *p1cap.SupportedFeatures) callconv(.c) void, "wgpuDeviceGetFeatures");
    proc(a0, a1);
}

pub export fn wgpuDeviceGetLimits(a0: types.WGPUDevice, a1: *p1cap.Limits) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *p1cap.Limits) callconv(.c) types.WGPUStatus, "wgpuDeviceGetLimits");
    return proc(a0, a1);
}

pub export fn wgpuDevicePopErrorScope(a0: types.WGPUDevice, a1: async_procs.PopErrorScopeCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, async_procs.PopErrorScopeCallbackInfo) callconv(.c) types.WGPUFuture, "wgpuDevicePopErrorScope");
    return proc(a0, a1);
}

pub export fn wgpuDevicePushErrorScope(a0: types.WGPUDevice, a1: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, u32) callconv(.c) void, "wgpuDevicePushErrorScope");
    proc(a0, a1);
}

pub export fn wgpuExternalTextureAddRef(a0: p2life.WGPUExternalTexture) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p2life.WGPUExternalTexture) callconv(.c) void, "wgpuExternalTextureAddRef");
    proc(a0);
}

pub export fn wgpuGetInstanceFeatures(a0: *p1cap.SupportedInstanceFeatures) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (*p1cap.SupportedInstanceFeatures) callconv(.c) void, "wgpuGetInstanceFeatures");
    proc(a0);
}

pub export fn wgpuGetInstanceLimits(a0: *p1cap.InstanceLimits) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (*p1cap.InstanceLimits) callconv(.c) types.WGPUStatus, "wgpuGetInstanceLimits");
    return proc(a0);
}

pub export fn wgpuHasInstanceFeature(a0: p1cap.WGPUInstanceFeatureName) callconv(.c) types.WGPUBool {
    const proc = resolveRequiredProc(*const fn (p1cap.WGPUInstanceFeatureName) callconv(.c) types.WGPUBool, "wgpuHasInstanceFeature");
    return proc(a0);
}

pub export fn wgpuInstanceAddRef(a0: types.WGPUInstance) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUInstance) callconv(.c) void, "wgpuInstanceAddRef");
    proc(a0);
}

pub export fn wgpuInstanceCreateSurface(a0: types.WGPUInstance, a1: *const surface.SurfaceDescriptor) callconv(.c) surface.Surface {
    const proc = resolveRequiredProc(*const fn (types.WGPUInstance, *const surface.SurfaceDescriptor) callconv(.c) surface.Surface, "wgpuInstanceCreateSurface");
    return proc(a0, a1);
}

pub export fn wgpuInstanceGetWGSLLanguageFeatures(a0: types.WGPUInstance, a1: *p1cap.SupportedWGSLLanguageFeatures) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUInstance, *p1cap.SupportedWGSLLanguageFeatures) callconv(.c) void, "wgpuInstanceGetWGSLLanguageFeatures");
    proc(a0, a1);
}

pub export fn wgpuInstanceHasWGSLLanguageFeature(a0: types.WGPUInstance, a1: p1cap.WGPUWGSLLanguageFeatureName) callconv(.c) types.WGPUBool {
    const proc = resolveRequiredProc(*const fn (types.WGPUInstance, p1cap.WGPUWGSLLanguageFeatureName) callconv(.c) types.WGPUBool, "wgpuInstanceHasWGSLLanguageFeature");
    return proc(a0, a1);
}

pub export fn wgpuPipelineLayoutAddRef(a0: types.WGPUPipelineLayout) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUPipelineLayout) callconv(.c) void, "wgpuPipelineLayoutAddRef");
    proc(a0);
}

pub export fn wgpuQuerySetAddRef(a0: types.WGPUQuerySet) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUQuerySet) callconv(.c) void, "wgpuQuerySetAddRef");
    proc(a0);
}

pub export fn wgpuQuerySetDestroy(a0: types.WGPUQuerySet) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUQuerySet) callconv(.c) void, "wgpuQuerySetDestroy");
    proc(a0);
}

pub export fn wgpuQuerySetGetCount(a0: types.WGPUQuerySet) callconv(.c) u32 {
    const proc = resolveRequiredProc(*const fn (types.WGPUQuerySet) callconv(.c) u32, "wgpuQuerySetGetCount");
    return proc(a0);
}

pub export fn wgpuQuerySetGetType(a0: types.WGPUQuerySet) callconv(.c) types.WGPUQueryType {
    const proc = resolveRequiredProc(*const fn (types.WGPUQuerySet) callconv(.c) types.WGPUQueryType, "wgpuQuerySetGetType");
    return proc(a0);
}

pub export fn wgpuQueueAddRef(a0: types.WGPUQueue) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUQueue) callconv(.c) void, "wgpuQueueAddRef");
    proc(a0);
}

pub export fn wgpuRenderBundleAddRef(a0: render.RenderBundle) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundle) callconv(.c) void, "wgpuRenderBundleAddRef");
    proc(a0);
}

pub export fn wgpuRenderBundleEncoderAddRef(a0: render.RenderBundleEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder) callconv(.c) void, "wgpuRenderBundleEncoderAddRef");
    proc(a0);
}

pub export fn wgpuRenderBundleEncoderDraw(a0: render.RenderBundleEncoder, a1: u32, a2: u32, a3: u32, a4: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, u32, u32, u32, u32) callconv(.c) void, "wgpuRenderBundleEncoderDraw");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderBundleEncoderDrawIndexed(a0: render.RenderBundleEncoder, a1: u32, a2: u32, a3: u32, a4: i32, a5: u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, u32, u32, u32, i32, u32) callconv(.c) void, "wgpuRenderBundleEncoderDrawIndexed");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuRenderBundleEncoderDrawIndexedIndirect(a0: render.RenderBundleEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, types.WGPUBuffer, u64) callconv(.c) void, "wgpuRenderBundleEncoderDrawIndexedIndirect");
    proc(a0, a1, a2);
}

pub export fn wgpuRenderBundleEncoderDrawIndirect(a0: render.RenderBundleEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, types.WGPUBuffer, u64) callconv(.c) void, "wgpuRenderBundleEncoderDrawIndirect");
    proc(a0, a1, a2);
}

pub export fn wgpuRenderBundleEncoderFinish(a0: render.RenderBundleEncoder, a1: ?*const anyopaque) callconv(.c) render.RenderBundle {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, ?*const anyopaque) callconv(.c) render.RenderBundle, "wgpuRenderBundleEncoderFinish");
    return proc(a0, a1);
}

pub export fn wgpuRenderBundleEncoderInsertDebugMarker(a0: render.RenderBundleEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, types.WGPUStringView) callconv(.c) void, "wgpuRenderBundleEncoderInsertDebugMarker");
    proc(a0, a1);
}

pub export fn wgpuRenderBundleEncoderPopDebugGroup(a0: render.RenderBundleEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder) callconv(.c) void, "wgpuRenderBundleEncoderPopDebugGroup");
    proc(a0);
}

pub export fn wgpuRenderBundleEncoderPushDebugGroup(a0: render.RenderBundleEncoder, a1: types.WGPUStringView) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, types.WGPUStringView) callconv(.c) void, "wgpuRenderBundleEncoderPushDebugGroup");
    proc(a0, a1);
}

pub export fn wgpuRenderBundleEncoderRelease(a0: render.RenderBundleEncoder) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder) callconv(.c) void, "wgpuRenderBundleEncoderRelease");
    proc(a0);
}

pub export fn wgpuRenderBundleEncoderSetBindGroup(a0: render.RenderBundleEncoder, a1: u32, a2: types.WGPUBindGroup, a3: usize, a4: ?[*]const u32) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (render.RenderBundleEncoder, u32, types.WGPUBindGroup, usize, ?[*]const u32) callconv(.c) void, "wgpuRenderBundleEncoderSetBindGroup");
    proc(a0, a1, a2, a3, a4);
}
