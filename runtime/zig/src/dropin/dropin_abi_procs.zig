const std = @import("std");
const types = @import("../core/abi/wgpu_types.zig");
const dropin_lib = @import("../wgpu_dropin_lib.zig");
const native = @import("../doe_wgpu_native.zig");

const loadRequiredProc = dropin_lib.loadRequiredProc;
const BUFFER_MAP_SYNC_TIMEOUT_NS = 5 * std.time.ns_per_s;

const BufferMapSyncResult = struct {
    done: bool = false,
    status: types.WGPUMapAsyncStatus = 0,
};

fn buffer_map_sync_callback(
    status: types.WGPUMapAsyncStatus,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    const raw = userdata1 orelse return;
    const result: *BufferMapSyncResult = @ptrCast(@alignCast(raw));
    result.status = status;
    result.done = true;
}

pub export fn wgpuCreateInstance(a0: ?*anyopaque) callconv(.c) types.WGPUInstance {
    return native.doeNativeCreateInstance(a0);
}

pub export fn wgpuInstanceRequestAdapter(a0: types.WGPUInstance, a1: ?*const types.WGPURequestAdapterOptions, a2: types.WGPURequestAdapterCallbackInfo) callconv(.c) types.WGPUFuture {
    return native.doeNativeInstanceRequestAdapter(a0, a1, a2);
}

pub export fn wgpuInstanceWaitAny(a0: types.WGPUInstance, a1: usize, a2: [*]types.WGPUFutureWaitInfo, a3: u64) callconv(.c) types.WGPUWaitStatus {
    return @enumFromInt(native.doeNativeInstanceWaitAny(a0, a1, a2, a3));
}

pub export fn wgpuInstanceProcessEvents(a0: types.WGPUInstance) callconv(.c) void {
    native.doeNativeInstanceProcessEvents(a0);
}

pub export fn wgpuAdapterRequestDevice(a0: types.WGPUAdapter, a1: ?*const types.WGPUDeviceDescriptor, a2: types.WGPURequestDeviceCallbackInfo) callconv(.c) types.WGPUFuture {
    return native.doeNativeAdapterRequestDevice(a0, a1, a2);
}

pub export fn wgpuAdapterCreateDevice(a0: types.WGPUAdapter, a1: ?*const types.WGPUDeviceDescriptor) callconv(.c) types.WGPUDevice {
    return native.doeNativeAdapterCreateDevice(a0, a1);
}

// FFI-friendly wrappers: flattened args for runtimes that cannot pass structs by value (Bun FFI, Node ffi-napi).
// These assemble the CallbackInfo struct from scalar args and delegate to the standard C ABI functions.

pub export fn doeRequestAdapterFlat(
    instance: types.WGPUInstance,
    options: ?*const types.WGPURequestAdapterOptions,
    mode: types.WGPUCallbackMode,
    callback: types.WGPURequestAdapterCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    const info = types.WGPURequestAdapterCallbackInfo{
        .nextInChain = null,
        .mode = mode,
        .callback = callback,
        .userdata1 = userdata1,
        .userdata2 = userdata2,
    };
    return native.doeNativeInstanceRequestAdapter(instance, options, info);
}

pub export fn doeRequestDeviceFlat(
    adapter: types.WGPUAdapter,
    descriptor: ?*const types.WGPUDeviceDescriptor,
    mode: types.WGPUCallbackMode,
    callback: types.WGPURequestDeviceCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    const info = types.WGPURequestDeviceCallbackInfo{
        .nextInChain = null,
        .mode = mode,
        .callback = callback,
        .userdata1 = userdata1,
        .userdata2 = userdata2,
    };
    return native.doeNativeAdapterRequestDevice(adapter, descriptor, info);
}

pub export fn wgpuDeviceCreateBuffer(a0: types.WGPUDevice, a1: ?*const types.WGPUBufferDescriptor) callconv(.c) types.WGPUBuffer {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateBuffer, "wgpuDeviceCreateBuffer");
    return proc(a0, a1);
}

pub export fn wgpuDeviceCreateShaderModule(a0: types.WGPUDevice, a1: ?*const types.WGPUShaderModuleDescriptor) callconv(.c) types.WGPUShaderModule {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateShaderModule, "wgpuDeviceCreateShaderModule");
    return proc(a0, a1);
}

pub export fn wgpuShaderModuleRelease(a0: types.WGPUShaderModule) callconv(.c) void {
    native.doeNativeShaderModuleRelease(a0);
}

pub export fn wgpuDeviceCreateComputePipeline(a0: types.WGPUDevice, a1: ?*const types.WGPUComputePipelineDescriptor) callconv(.c) types.WGPUComputePipeline {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateComputePipeline, "wgpuDeviceCreateComputePipeline");
    return proc(a0, a1);
}

pub export fn wgpuComputePipelineRelease(a0: types.WGPUComputePipeline) callconv(.c) void {
    native.doeNativeComputePipelineRelease(a0);
}

pub export fn wgpuRenderPipelineRelease(a0: types.WGPURenderPipeline) callconv(.c) void {
    native.doeNativeRenderPipelineRelease(a0);
}

pub export fn wgpuDeviceCreateCommandEncoder(a0: types.WGPUDevice, a1: ?*const types.WGPUCommandEncoderDescriptor) callconv(.c) types.WGPUCommandEncoder {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateCommandEncoder, "wgpuDeviceCreateCommandEncoder");
    return proc(a0, a1);
}

pub export fn wgpuCommandEncoderBeginComputePass(a0: types.WGPUCommandEncoder, a1: ?*const types.WGPUComputePassDescriptor) callconv(.c) types.WGPUComputePassEncoder {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderBeginComputePass, "wgpuCommandEncoderBeginComputePass");
    return proc(a0, a1);
}

pub export fn wgpuDeviceCreateRenderPipeline(a0: types.WGPUDevice, a1: *const anyopaque) callconv(.c) types.WGPURenderPipeline {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateRenderPipeline, "wgpuDeviceCreateRenderPipeline");
    return proc(a0, a1);
}

pub export fn wgpuCommandEncoderBeginRenderPass(a0: types.WGPUCommandEncoder, a1: *const anyopaque) callconv(.c) types.WGPURenderPassEncoder {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderBeginRenderPass, "wgpuCommandEncoderBeginRenderPass");
    return proc(a0, a1);
}

pub export fn wgpuCommandEncoderWriteTimestamp(a0: types.WGPUCommandEncoder, a1: types.WGPUQuerySet, a2: u32) callconv(.c) void {
    native.doeNativeCommandEncoderWriteTimestamp(a0, a1, a2);
}

pub export fn wgpuCommandEncoderCopyBufferToBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: types.WGPUBuffer, a4: u64, a5: u64) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderCopyBufferToBuffer, "wgpuCommandEncoderCopyBufferToBuffer");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuCommandEncoderCopyBufferToTexture(a0: types.WGPUCommandEncoder, a1: *const types.WGPUTexelCopyBufferInfo, a2: *const types.WGPUTexelCopyTextureInfo, a3: *const types.WGPUExtent3D) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderCopyBufferToTexture, "wgpuCommandEncoderCopyBufferToTexture");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuCommandEncoderCopyTextureToBuffer(a0: types.WGPUCommandEncoder, a1: *const types.WGPUTexelCopyTextureInfo, a2: *const types.WGPUTexelCopyBufferInfo, a3: *const types.WGPUExtent3D) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderCopyTextureToBuffer, "wgpuCommandEncoderCopyTextureToBuffer");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuCommandEncoderCopyTextureToTexture(a0: types.WGPUCommandEncoder, a1: *const types.WGPUTexelCopyTextureInfo, a2: *const types.WGPUTexelCopyTextureInfo, a3: *const types.WGPUExtent3D) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderCopyTextureToTexture, "wgpuCommandEncoderCopyTextureToTexture");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuComputePassEncoderSetPipeline(a0: types.WGPUComputePassEncoder, a1: types.WGPUComputePipeline) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuComputePassEncoderSetPipeline, "wgpuComputePassEncoderSetPipeline");
    proc(a0, a1);
}

pub export fn wgpuComputePassEncoderSetBindGroup(a0: types.WGPUComputePassEncoder, a1: u32, a2: types.WGPUBindGroup, a3: usize, a4: ?[*]const u32) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuComputePassEncoderSetBindGroup, "wgpuComputePassEncoderSetBindGroup");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuComputePassEncoderDispatchWorkgroups(a0: types.WGPUComputePassEncoder, a1: u32, a2: u32, a3: u32) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuComputePassEncoderDispatchWorkgroups, "wgpuComputePassEncoderDispatchWorkgroups");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuComputePassEncoderEnd(a0: types.WGPUComputePassEncoder) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuComputePassEncoderEnd, "wgpuComputePassEncoderEnd");
    proc(a0);
}

pub export fn wgpuComputePassEncoderRelease(a0: types.WGPUComputePassEncoder) callconv(.c) void {
    native.doeNativeComputePassRelease(a0);
}

pub export fn wgpuRenderPassEncoderSetPipeline(a0: types.WGPURenderPassEncoder, a1: types.WGPURenderPipeline) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderSetPipeline, "wgpuRenderPassEncoderSetPipeline");
    proc(a0, a1);
}

pub export fn wgpuRenderPassEncoderSetVertexBuffer(a0: types.WGPURenderPassEncoder, a1: u32, a2: types.WGPUBuffer, a3: u64, a4: u64) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderSetVertexBuffer, "wgpuRenderPassEncoderSetVertexBuffer");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderPassEncoderSetIndexBuffer(a0: types.WGPURenderPassEncoder, a1: types.WGPUBuffer, a2: u32, a3: u64, a4: u64) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderSetIndexBuffer, "wgpuRenderPassEncoderSetIndexBuffer");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderPassEncoderSetBindGroup(a0: types.WGPURenderPassEncoder, a1: u32, a2: types.WGPUBindGroup, a3: usize, a4: ?[*]const u32) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderSetBindGroup, "wgpuRenderPassEncoderSetBindGroup");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderPassEncoderDraw(a0: types.WGPURenderPassEncoder, a1: u32, a2: u32, a3: u32, a4: u32) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderDraw, "wgpuRenderPassEncoderDraw");
    proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderPassEncoderDrawIndexed(a0: types.WGPURenderPassEncoder, a1: u32, a2: u32, a3: u32, a4: i32, a5: u32) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderDrawIndexed, "wgpuRenderPassEncoderDrawIndexed");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuRenderPassEncoderDrawIndirect(a0: types.WGPURenderPassEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderDrawIndirect, "wgpuRenderPassEncoderDrawIndirect");
    proc(a0, a1, a2);
}

pub export fn wgpuRenderPassEncoderDrawIndexedIndirect(a0: types.WGPURenderPassEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderDrawIndexedIndirect, "wgpuRenderPassEncoderDrawIndexedIndirect");
    proc(a0, a1, a2);
}

pub export fn wgpuRenderPassEncoderEnd(a0: types.WGPURenderPassEncoder) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderEnd, "wgpuRenderPassEncoderEnd");
    proc(a0);
}

pub export fn wgpuRenderPassEncoderRelease(a0: types.WGPURenderPassEncoder) callconv(.c) void {
    native.doeNativeRenderPassRelease(a0);
}

pub export fn wgpuCommandEncoderFinish(a0: types.WGPUCommandEncoder, a1: ?*const types.WGPUCommandBufferDescriptor) callconv(.c) types.WGPUCommandBuffer {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderFinish, "wgpuCommandEncoderFinish");
    return proc(a0, a1);
}

pub export fn wgpuDeviceGetQueue(a0: types.WGPUDevice) callconv(.c) types.WGPUQueue {
    return native.doeNativeDeviceGetQueue(a0);
}

pub export fn wgpuQueueSubmit(a0: types.WGPUQueue, a1: usize, a2: [*c]types.WGPUCommandBuffer) callconv(.c) void {
    native.doeNativeQueueSubmit(a0, a1, a2);
}

pub export fn wgpuQueueOnSubmittedWorkDone(a0: types.WGPUQueue, a1: types.WGPUQueueWorkDoneCallbackInfo) callconv(.c) types.WGPUFuture {
    return native.doeNativeQueueOnSubmittedWorkDone(a0, a1);
}

pub export fn wgpuQueueWriteBuffer(a0: types.WGPUQueue, a1: types.WGPUBuffer, a2: u64, a3: ?*const anyopaque, a4: usize) callconv(.c) void {
    const data = a3 orelse return;
    native.doeNativeQueueWriteBuffer(a0, a1, a2, @ptrCast(data), a4);
}

pub export fn wgpuDeviceCreateTexture(a0: types.WGPUDevice, a1: ?*const types.WGPUTextureDescriptor) callconv(.c) types.WGPUTexture {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateTexture, "wgpuDeviceCreateTexture");
    return proc(a0, a1);
}

pub export fn wgpuTextureCreateView(a0: types.WGPUTexture, a1: ?*const types.WGPUTextureViewDescriptor) callconv(.c) types.WGPUTextureView {
    const proc = loadRequiredProc(types.FnWgpuTextureCreateView, "wgpuTextureCreateView");
    return proc(a0, a1);
}

pub export fn wgpuDeviceCreateBindGroupLayout(a0: types.WGPUDevice, a1: ?*const types.WGPUBindGroupLayoutDescriptor) callconv(.c) types.WGPUBindGroupLayout {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateBindGroupLayout, "wgpuDeviceCreateBindGroupLayout");
    return proc(a0, a1);
}

pub export fn wgpuBindGroupLayoutRelease(a0: types.WGPUBindGroupLayout) callconv(.c) void {
    native.doeNativeBindGroupLayoutRelease(a0);
}

pub export fn wgpuDeviceCreateBindGroup(a0: types.WGPUDevice, a1: ?*const types.WGPUBindGroupDescriptor) callconv(.c) types.WGPUBindGroup {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateBindGroup, "wgpuDeviceCreateBindGroup");
    return proc(a0, a1);
}

pub export fn wgpuBindGroupRelease(a0: types.WGPUBindGroup) callconv(.c) void {
    native.doeNativeBindGroupRelease(a0);
}

pub export fn wgpuDeviceCreatePipelineLayout(a0: types.WGPUDevice, a1: *const types.WGPUPipelineLayoutDescriptor) callconv(.c) types.WGPUPipelineLayout {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreatePipelineLayout, "wgpuDeviceCreatePipelineLayout");
    return proc(a0, a1);
}

pub export fn wgpuPipelineLayoutRelease(a0: types.WGPUPipelineLayout) callconv(.c) void {
    native.doeNativePipelineLayoutRelease(a0);
}

pub export fn wgpuTextureRelease(a0: types.WGPUTexture) callconv(.c) void {
    native.doeNativeTextureRelease(a0);
}

pub export fn wgpuTextureViewRelease(a0: types.WGPUTextureView) callconv(.c) void {
    native.doeNativeTextureViewRelease(a0);
}

pub export fn wgpuInstanceRelease(a0: types.WGPUInstance) callconv(.c) void {
    native.doeNativeInstanceRelease(a0);
}

pub export fn wgpuAdapterRelease(a0: types.WGPUAdapter) callconv(.c) void {
    native.doeNativeAdapterRelease(a0);
}

pub export fn wgpuDeviceRelease(a0: types.WGPUDevice) callconv(.c) void {
    native.doeNativeDeviceRelease(a0);
}

pub export fn wgpuQueueRelease(a0: types.WGPUQueue) callconv(.c) void {
    native.doeNativeQueueRelease(a0);
}

pub export fn wgpuCommandEncoderRelease(a0: types.WGPUCommandEncoder) callconv(.c) void {
    native.doeNativeCommandEncoderRelease(a0);
}

pub export fn wgpuCommandBufferRelease(a0: types.WGPUCommandBuffer) callconv(.c) void {
    native.doeNativeCommandBufferRelease(a0);
}

pub export fn wgpuBufferRelease(a0: types.WGPUBuffer) callconv(.c) void {
    native.doeNativeBufferRelease(a0);
}

pub export fn wgpuAdapterHasFeature(a0: types.WGPUAdapter, a1: types.WGPUFeatureName) callconv(.c) types.WGPUBool {
    return native.doeNativeAdapterHasFeature(a0, a1);
}

pub export fn wgpuDeviceHasFeature(a0: types.WGPUDevice, a1: types.WGPUFeatureName) callconv(.c) types.WGPUBool {
    return native.doeNativeDeviceHasFeature(a0, a1);
}

pub export fn wgpuDeviceCreateQuerySet(a0: types.WGPUDevice, a1: *const types.WGPUQuerySetDescriptor) callconv(.c) types.WGPUQuerySet {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateQuerySet, "wgpuDeviceCreateQuerySet");
    return proc(a0, a1);
}

pub export fn wgpuCommandEncoderResolveQuerySet(a0: types.WGPUCommandEncoder, a1: types.WGPUQuerySet, a2: u32, a3: u32, a4: types.WGPUBuffer, a5: u64) callconv(.c) void {
    native.doeNativeCommandEncoderResolveQuerySet(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuQuerySetRelease(a0: types.WGPUQuerySet) callconv(.c) void {
    native.doeNativeQuerySetRelease(a0);
}

pub export fn wgpuBufferMapAsync(a0: types.WGPUBuffer, a1: types.WGPUMapMode, a2: usize, a3: usize, a4: types.WGPUBufferMapCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = loadRequiredProc(types.FnWgpuBufferMapAsync, "wgpuBufferMapAsync");
    return proc(a0, a1, a2, a3, a4);
}

// FFI-friendly buffer map: flattened args for runtimes that cannot pass WGPUBufferMapCallbackInfo by value.
pub export fn doeBufferMapAsyncFlat(
    buffer: types.WGPUBuffer,
    mode: types.WGPUMapMode,
    offset: usize,
    size: usize,
    cb_mode: types.WGPUCallbackMode,
    callback: types.WGPUBufferMapCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    const info = types.WGPUBufferMapCallbackInfo{
        .nextInChain = null,
        .mode = cb_mode,
        .callback = callback,
        .userdata1 = userdata1,
        .userdata2 = userdata2,
    };
    const proc = loadRequiredProc(types.FnWgpuBufferMapAsync, "wgpuBufferMapAsync");
    return proc(buffer, mode, offset, size, info);
}

pub export fn doeBufferMapSyncFlat(
    instance: types.WGPUInstance,
    buffer: types.WGPUBuffer,
    mode: types.WGPUMapMode,
    offset: usize,
    size: usize,
) callconv(.c) types.WGPUMapAsyncStatus {
    var result = BufferMapSyncResult{};
    const info = types.WGPUBufferMapCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_AllowProcessEvents,
        .callback = buffer_map_sync_callback,
        .userdata1 = @ptrCast(&result),
        .userdata2 = null,
    };
    const map_proc = loadRequiredProc(types.FnWgpuBufferMapAsync, "wgpuBufferMapAsync");
    const future = map_proc(buffer, mode, offset, size, info);
    if (future.id == 0) return 0;
    const process_events = loadRequiredProc(types.FnWgpuInstanceProcessEvents, "wgpuInstanceProcessEvents");
    const start_ns = std.time.nanoTimestamp();
    while (!result.done) {
        process_events(instance);
        if (std.time.nanoTimestamp() - start_ns >= BUFFER_MAP_SYNC_TIMEOUT_NS) return 0;
    }
    return result.status;
}

// FFI-friendly queue work-done: flattened args for runtimes that cannot pass WGPUQueueWorkDoneCallbackInfo by value.
pub export fn doeQueueOnSubmittedWorkDoneFlat(
    queue: types.WGPUQueue,
    cb_mode: types.WGPUCallbackMode,
    callback: types.WGPUQueueWorkDoneCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) types.WGPUFuture {
    const info = types.WGPUQueueWorkDoneCallbackInfo{
        .nextInChain = null,
        .mode = cb_mode,
        .callback = callback,
        .userdata1 = userdata1,
        .userdata2 = userdata2,
    };
    const proc = loadRequiredProc(types.FnWgpuQueueOnSubmittedWorkDone, "wgpuQueueOnSubmittedWorkDone");
    return proc(queue, info);
}

pub export fn wgpuBufferGetConstMappedRange(a0: types.WGPUBuffer, a1: usize, a2: usize) callconv(.c) ?*const anyopaque {
    const proc = loadRequiredProc(types.FnWgpuBufferGetConstMappedRange, "wgpuBufferGetConstMappedRange");
    return proc(a0, a1, a2);
}

pub export fn wgpuBufferUnmap(a0: types.WGPUBuffer) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuBufferUnmap, "wgpuBufferUnmap");
    proc(a0);
}

pub export fn wgpuDeviceCreateSampler(a0: types.WGPUDevice, a1: ?*const types.WGPUSamplerDescriptor) callconv(.c) types.WGPUSampler {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateSampler, "wgpuDeviceCreateSampler");
    return proc(a0, a1);
}

pub export fn wgpuSamplerRelease(a0: types.WGPUSampler) callconv(.c) void {
    native.doeNativeSamplerRelease(a0);
}
