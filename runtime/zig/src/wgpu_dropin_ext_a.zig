const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const p1cap = @import("wgpu_p1_capability_procs.zig");
const p0 = @import("wgpu_p0_procs.zig");
const p1res = @import("wgpu_p1_resource_table_procs.zig");
const p2life = @import("wgpu_p2_lifecycle_procs.zig");
const surface = @import("full/surface/wgpu_surface_procs.zig");
const texture = @import("wgpu_texture_procs.zig");
const render = @import("full/render/wgpu_render_api.zig");
const async_procs = @import("wgpu_async_procs.zig");
const native = @import("doe_wgpu_native.zig");
const query_native = @import("doe_query_native.zig");
const error_scope = @import("error_scope.zig");

extern fn wgpuGetProcAddress(name: types.WGPUStringView) callconv(.c) p1cap.WGPUProc;
extern fn doeWgpuDropinAbortMissingRequiredSymbol(name: types.WGPUStringView) callconv(.c) noreturn;
extern fn doeNativeComputePassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void;
extern fn doeNativeQuerySetDestroy(qs_raw: ?*anyopaque) callconv(.c) void;
extern fn doeNativeQuerySetGetCount(qs_raw: ?*anyopaque) callconv(.c) u32;
extern fn doeNativeQuerySetGetType(qs_raw: ?*anyopaque) callconv(.c) types.WGPUQueryType;

const FEATURE_CANDIDATES = [_]types.WGPUFeatureName{
    types.WGPUFeatureName_CoreFeaturesAndLimits,
    types.WGPUFeatureName_DepthClipControl,
    types.WGPUFeatureName_Depth32FloatStencil8,
    types.WGPUFeatureName_TextureCompressionBC,
    types.WGPUFeatureName_TextureCompressionBCSliced3D,
    types.WGPUFeatureName_TextureCompressionETC2,
    types.WGPUFeatureName_TextureCompressionASTC,
    types.WGPUFeatureName_TextureCompressionASTCSliced3D,
    types.WGPUFeatureName_RG11B10UfloatRenderable,
    types.WGPUFeatureName_TimestampQuery,
    types.WGPUFeatureName_BGRA8UnormStorage,
    types.WGPUFeatureName_ShaderF16,
    types.WGPUFeatureName_IndirectFirstInstance,
    types.WGPUFeatureName_Float32Filterable,
    types.WGPUFeatureName_Subgroups,
    types.WGPUFeatureName_SubgroupsF16,
    types.WGPUFeatureName_Float32Blendable,
    types.WGPUFeatureName_ClipDistances,
    types.WGPUFeatureName_DualSourceBlending,
    types.WGPUFeatureName_TextureFormatsTier1,
    types.WGPUFeatureName_TextureFormatsTier2,
    types.WGPUFeatureName_PrimitiveIndex,
    types.WGPUFeatureName_TextureComponentSwizzle,
};

const LoggingCallback = *const fn (u32, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;
const PopErrorScopeCallback = *const fn (u32, u32, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;

const LoggingCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    callback: ?LoggingCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

const PopErrorScopeBridgeState = struct {
    callback: ?PopErrorScopeCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

fn bridge_pop_error_scope_callback(
    error_type: u32,
    msg: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = userdata2;
    const state = userdata1 orelse return;
    const bridge_state: *PopErrorScopeBridgeState = @ptrCast(@alignCast(state));
    const callback = bridge_state.callback orelse return;
    callback(async_procs.POP_ERROR_SCOPE_STATUS_SUCCESS, error_type, msg, bridge_state.userdata1, bridge_state.userdata2);
}

fn static_string_view(comptime text: []const u8) types.WGPUStringView {
    return .{ .data = text.ptr, .length = text.len };
}

fn backend_type_for(adapter: *native.DoeAdapter) types.WGPUBackendType {
    return switch (adapter.backend) {
        .metal => .metal,
        .vulkan => .vulkan,
        .d3d12 => .d3d12,
    };
}

fn fill_adapter_info_struct(adapter_raw: types.WGPUAdapter, out: *p1cap.AdapterInfo) types.WGPUStatus {
    const adapter = native.cast(native.DoeAdapter, adapter_raw) orelse return 0;
    out.* = p1cap.initAdapterInfo(out.nextInChain);
    out.vendor = static_string_view("Doe");
    out.architecture = switch (adapter.backend) {
        .metal => static_string_view("metal"),
        .vulkan => static_string_view("vulkan"),
        .d3d12 => static_string_view("d3d12"),
    };
    out.device = switch (adapter.backend) {
        .metal => static_string_view("Doe Metal Adapter"),
        .vulkan => static_string_view("Doe Vulkan Adapter"),
        .d3d12 => static_string_view("Doe D3D12 Adapter"),
    };
    out.description = out.device;
    out.backendType = backend_type_for(adapter);
    out.adapterType = 0x00000004; // Unknown
    out.vendorID = 0;
    out.deviceID = 0;
    out.subgroupMinSize = 0;
    out.subgroupMaxSize = 0;
    return types.WGPUStatus_Success;
}

fn fill_supported_features_from_adapter(adapter_raw: types.WGPUAdapter, out: *p1cap.SupportedFeatures) void {
    out.* = p1cap.initSupportedFeatures();
    var count: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeAdapterHasFeature(adapter_raw, feature) != 0) count += 1;
    }
    if (count == 0) return;
    const owned = std.heap.c_allocator.alloc(types.WGPUFeatureName, count) catch return;
    var write_index: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeAdapterHasFeature(adapter_raw, feature) == 0) continue;
        owned[write_index] = feature;
        write_index += 1;
    }
    out.featureCount = write_index;
    out.features = owned.ptr;
}

fn fill_supported_features_from_device(device_raw: types.WGPUDevice, out: *p1cap.SupportedFeatures) void {
    out.* = p1cap.initSupportedFeatures();
    var count: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeDeviceHasFeature(device_raw, feature) != 0) count += 1;
    }
    if (count == 0) return;
    const owned = std.heap.c_allocator.alloc(types.WGPUFeatureName, count) catch return;
    var write_index: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeDeviceHasFeature(device_raw, feature) == 0) continue;
        owned[write_index] = feature;
        write_index += 1;
    }
    out.featureCount = write_index;
    out.features = owned.ptr;
}

fn symbolView(comptime name: []const u8) types.WGPUStringView {
    return .{ .data = name.ptr, .length = name.len };
}

fn resolveRequiredProc(comptime FnType: type, comptime symbol_name: []const u8) FnType {
    const proc = wgpuGetProcAddress(symbolView(symbol_name)) orelse
        doeWgpuDropinAbortMissingRequiredSymbol(symbolView(symbol_name));
    return @as(FnType, @ptrCast(proc));
}

pub export fn wgpuAdapterAddRef(a0: types.WGPUAdapter) callconv(.c) void {
    native.doeNativeAdapterAddRef(a0);
}

pub export fn wgpuAdapterGetFeatures(a0: types.WGPUAdapter, a1: *p1cap.SupportedFeatures) callconv(.c) void {
    fill_supported_features_from_adapter(a0, a1);
}

pub export fn wgpuAdapterGetFormatCapabilities(a0: types.WGPUAdapter, a1: types.WGPUTextureFormat, a2: *p1cap.DawnFormatCapabilities) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter, types.WGPUTextureFormat, *p1cap.DawnFormatCapabilities) callconv(.c) types.WGPUStatus, "wgpuAdapterGetFormatCapabilities");
    return proc(a0, a1, a2);
}

pub export fn wgpuAdapterGetInfo(a0: types.WGPUAdapter, a1: *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus {
    return fill_adapter_info_struct(a0, a1);
}

pub export fn wgpuAdapterGetInstance(a0: types.WGPUAdapter) callconv(.c) types.WGPUInstance {
    return native.doeNativeAdapterGetInstance(a0);
}

pub export fn wgpuAdapterGetLimits(a0: types.WGPUAdapter, a1: *p1cap.Limits) callconv(.c) types.WGPUStatus {
    return native.doeNativeAdapterGetLimits(a0, a1);
}

pub export fn wgpuAdapterInfoFreeMembers(a0: p1cap.AdapterInfo) callconv(.c) void {
    _ = a0;
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
    native.object_add_ref(native.DoeBindGroup, a0);
}

pub export fn wgpuBindGroupLayoutAddRef(a0: types.WGPUBindGroupLayout) callconv(.c) void {
    native.object_add_ref(native.DoeBindGroupLayout, a0);
}

pub export fn wgpuBufferAddRef(a0: types.WGPUBuffer) callconv(.c) void {
    native.object_add_ref(native.DoeBuffer, a0);
}

pub export fn wgpuBufferDestroy(a0: types.WGPUBuffer) callconv(.c) void {
    // Doe buffers are cleaned up on release; destroy is a validated no-op.
    _ = native.cast(native.DoeBuffer, a0);
}

pub export fn wgpuCommandBufferAddRef(a0: types.WGPUCommandBuffer) callconv(.c) void {
    native.object_add_ref(native.DoeCommandBuffer, a0);
}

pub export fn wgpuCommandEncoderAddRef(a0: types.WGPUCommandEncoder) callconv(.c) void {
    native.object_add_ref(native.DoeCommandEncoder, a0);
}

pub export fn wgpuCommandEncoderClearBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: u64) callconv(.c) void {
    native.doeNativeCommandEncoderClearBuffer(a0, a1, a2, a3);
}

pub export fn wgpuCommandEncoderWriteBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: [*]const u8, a4: u64) callconv(.c) void {
    // Write data directly into the Doe buffer's backing memory at the given offset.
    _ = a0;
    const size: usize = @intCast(a4);
    const offset: usize = @intCast(a2);
    const dst_ptr = native.doeNativeBufferGetMappedRange(a1, offset, size) orelse return;
    const dst: [*]u8 = @ptrCast(dst_ptr);
    @memcpy(dst[0..size], a3[0..size]);
}

pub export fn wgpuComputePassEncoderAddRef(a0: types.WGPUComputePassEncoder) callconv(.c) void {
    native.object_add_ref(native.DoeComputePass, a0);
}

pub export fn wgpuComputePassEncoderDispatchWorkgroupsIndirect(a0: types.WGPUComputePassEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    native.doeNativeComputePassDispatchIndirect(a0, a1, a2);
}

pub export fn wgpuComputePassEncoderSetImmediates(a0: types.WGPUComputePassEncoder, a1: u32, a2: ?*const anyopaque, a3: usize) callconv(.c) void {
    doeNativeComputePassSetImmediates(a0, a1, if (a2) |ptr| @as([*]const u8, @ptrCast(ptr)) else null, a3);
}

pub export fn wgpuComputePassEncoderSetResourceTable(a0: types.WGPUComputePassEncoder, a1: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, p1res.WGPUResourceTable) callconv(.c) void, "wgpuComputePassEncoderSetResourceTable");
    proc(a0, a1);
}

pub export fn wgpuComputePassEncoderWriteTimestamp(a0: types.WGPUComputePassEncoder, a1: types.WGPUQuerySet, a2: u32) callconv(.c) void {
    // Route through the command encoder timestamp path, extracting the
    // parent encoder from the compute pass.
    const pass = native.cast(native.DoeComputePass, a0) orelse return;
    query_native.doeNativeCommandEncoderWriteTimestamp(native.toOpaque(pass.enc), a1, a2);
}

pub export fn wgpuComputePipelineAddRef(a0: types.WGPUComputePipeline) callconv(.c) void {
    native.object_add_ref(native.DoeComputePipeline, a0);
}

pub export fn wgpuDawnDrmFormatCapabilitiesFreeMembers(a0: p1cap.DawnDrmFormatCapabilities) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.DawnDrmFormatCapabilities) callconv(.c) void, "wgpuDawnDrmFormatCapabilitiesFreeMembers");
    proc(a0);
}

pub export fn wgpuDeviceAddRef(a0: types.WGPUDevice) callconv(.c) void {
    native.doeNativeDeviceAddRef(a0);
}

pub export fn wgpuDeviceCreateComputePipelineAsync(a0: types.WGPUDevice, a1: *const types.WGPUComputePipelineDescriptor, a2: p0.CreateComputePipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture {
    // Synchronous creation, then invoke callback with success/failure.
    const pipeline = native.doeNativeDeviceCreateComputePipeline(a0, a1);
    if (a2.callback) |cb| {
        if (pipeline != null) {
            cb(p0.CREATE_COMPUTE_PIPELINE_ASYNC_STATUS_SUCCESS, pipeline, .{ .data = null, .length = 0 }, a2.userdata1, a2.userdata2);
        } else {
            const msg = "pipeline creation failed";
            cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
        }
    }
    return .{ .id = 7 };
}

pub export fn wgpuDeviceCreateRenderBundleEncoder(a0: types.WGPUDevice, a1: *const anyopaque) callconv(.c) render.RenderBundleEncoder {
    return native.doeNativeDeviceCreateRenderBundleEncoder(a0, @ptrCast(@alignCast(a1)));
}

pub export fn wgpuDeviceCreateRenderPipelineAsync(a0: types.WGPUDevice, a1: *const anyopaque, a2: async_procs.CreateRenderPipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture {
    // Synchronous creation, then invoke callback with success/failure.
    const pipeline = native.doeNativeDeviceCreateRenderPipeline(a0, @constCast(a1));
    if (a2.callback) |cb| {
        if (pipeline != null) {
            cb(async_procs.CREATE_PIPELINE_ASYNC_STATUS_SUCCESS, pipeline, .{ .data = null, .length = 0 }, a2.userdata1, a2.userdata2);
        } else {
            const msg = "render pipeline creation failed";
            cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
        }
    }
    return .{ .id = 8 };
}

pub export fn wgpuDeviceCreateExternalTexture(a0: types.WGPUDevice, a1: ?*const anyopaque) callconv(.c) p2life.WGPUExternalTexture {
    return native.doeNativeDeviceCreateExternalTexture(a0, a1);
}

pub export fn wgpuDeviceCreateResourceTable(a0: types.WGPUDevice, a1: *const p1res.ResourceTableDescriptor) callconv(.c) p1res.WGPUResourceTable {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *const p1res.ResourceTableDescriptor) callconv(.c) p1res.WGPUResourceTable, "wgpuDeviceCreateResourceTable");
    return proc(a0, a1);
}

pub export fn wgpuDeviceDestroy(a0: types.WGPUDevice) callconv(.c) void {
    _ = a0;
}

pub export fn wgpuDeviceGetAdapter(a0: types.WGPUDevice) callconv(.c) types.WGPUAdapter {
    return native.doeNativeDeviceGetAdapter(a0);
}

pub export fn wgpuDeviceGetAdapterInfo(a0: types.WGPUDevice, a1: *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus {
    const adapter = native.doeNativeDeviceGetAdapter(a0) orelse return 0;
    defer native.doeNativeAdapterRelease(adapter);
    return fill_adapter_info_struct(adapter, a1);
}

pub export fn wgpuDeviceGetFeatures(a0: types.WGPUDevice, a1: *p1cap.SupportedFeatures) callconv(.c) void {
    fill_supported_features_from_device(a0, a1);
}

pub export fn wgpuDeviceGetLimits(a0: types.WGPUDevice, a1: *p1cap.Limits) callconv(.c) types.WGPUStatus {
    return native.doeNativeDeviceGetLimits(a0, a1);
}

pub export fn wgpuDevicePopErrorScope(a0: types.WGPUDevice, a1: async_procs.PopErrorScopeCallbackInfo) callconv(.c) types.WGPUFuture {
    const dev = native.cast(native.DoeDevice, a0) orelse {
        if (a1.callback) |callback| {
            callback(
                async_procs.POP_ERROR_SCOPE_STATUS_SUCCESS,
                error_scope.ERROR_TYPE_INTERNAL,
                .{ .data = null, .length = 0 },
                a1.userdata1,
                a1.userdata2,
            );
        }
        return .{ .id = 5 };
    };
    var state = PopErrorScopeBridgeState{
        .callback = a1.callback,
        .userdata1 = a1.userdata1,
        .userdata2 = a1.userdata2,
    };
    if (!dev.error_scopes.pop(.{
        .next_in_chain = null,
        .mode = 0,
        .callback = bridge_pop_error_scope_callback,
        .userdata1 = &state,
        .userdata2 = null,
    })) {
        if (a1.callback) |callback| {
            callback(
                async_procs.POP_ERROR_SCOPE_STATUS_SUCCESS,
                error_scope.ERROR_TYPE_INTERNAL,
                .{ .data = null, .length = 0 },
                a1.userdata1,
                a1.userdata2,
            );
        }
    }
    return .{ .id = 5 };
}

pub export fn wgpuDevicePushErrorScope(a0: types.WGPUDevice, a1: u32) callconv(.c) void {
    native.doeNativeDevicePushErrorScope(a0, a1);
}

pub export fn wgpuDeviceSetUncapturedErrorCallback(
    a0: types.WGPUDevice,
    callback: ?error_scope.UncapturedErrorCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    native.doeNativeDeviceSetUncapturedErrorCallback(a0, callback, userdata1, userdata2);
}

pub export fn wgpuDeviceSetLoggingCallback(a0: types.WGPUDevice, a1: LoggingCallbackInfo) callconv(.c) void {
    _ = a0;
    _ = a1;
}

pub export fn wgpuDeviceTick(a0: types.WGPUDevice) callconv(.c) types.WGPUBool {
    const dev = native.cast(native.DoeDevice, a0) orelse return types.WGPU_FALSE;
    if (dev.queue) |queue| {
        queue.gpu_timeline.drain_ready();
    }
    return types.WGPU_FALSE;
}

pub export fn wgpuExternalTextureAddRef(a0: p2life.WGPUExternalTexture) callconv(.c) void {
    native.doeNativeExternalTextureAddRef(a0);
}

pub export fn wgpuGetInstanceFeatures(a0: *p1cap.SupportedInstanceFeatures) callconv(.c) void {
    a0.* = p1cap.initSupportedInstanceFeatures();
}

pub export fn wgpuGetInstanceLimits(a0: *p1cap.InstanceLimits) callconv(.c) types.WGPUStatus {
    a0.* = p1cap.initInstanceLimits();
    return types.WGPUStatus_Success;
}

pub export fn wgpuHasInstanceFeature(a0: p1cap.WGPUInstanceFeatureName) callconv(.c) types.WGPUBool {
    _ = a0;
    return types.WGPU_FALSE;
}

pub export fn wgpuInstanceAddRef(a0: types.WGPUInstance) callconv(.c) void {
    native.doeNativeInstanceAddRef(a0);
}

pub export fn wgpuInstanceCreateSurface(a0: types.WGPUInstance, a1: *const surface.SurfaceDescriptor) callconv(.c) surface.Surface {
    // Route through native Doe surface creation when the instance is a Doe handle.
    if (native.cast(native.DoeInstance, a0) != null) {
        return native.doeAbiBridgeInstanceCreateSurface(a0, a1);
    }
    const proc = resolveRequiredProc(*const fn (types.WGPUInstance, *const surface.SurfaceDescriptor) callconv(.c) surface.Surface, "wgpuInstanceCreateSurface");
    return proc(a0, a1);
}

pub export fn wgpuInstanceGetWGSLLanguageFeatures(a0: types.WGPUInstance, a1: *p1cap.SupportedWGSLLanguageFeatures) callconv(.c) void {
    _ = a0;
    a1.* = p1cap.initSupportedWGSLLanguageFeatures();
}

pub export fn wgpuInstanceHasWGSLLanguageFeature(a0: types.WGPUInstance, a1: p1cap.WGPUWGSLLanguageFeatureName) callconv(.c) types.WGPUBool {
    _ = a0;
    _ = a1;
    return types.WGPU_FALSE;
}

pub export fn wgpuPipelineLayoutAddRef(a0: types.WGPUPipelineLayout) callconv(.c) void {
    native.object_add_ref(native.DoePipelineLayout, a0);
}

pub export fn wgpuQuerySetAddRef(a0: types.WGPUQuerySet) callconv(.c) void {
    native.object_add_ref(query_native.DoeQuerySet, a0);
}

pub export fn wgpuQuerySetDestroy(a0: types.WGPUQuerySet) callconv(.c) void {
    doeNativeQuerySetDestroy(a0);
}

pub export fn wgpuQuerySetGetCount(a0: types.WGPUQuerySet) callconv(.c) u32 {
    return doeNativeQuerySetGetCount(a0);
}

pub export fn wgpuQuerySetGetType(a0: types.WGPUQuerySet) callconv(.c) types.WGPUQueryType {
    return doeNativeQuerySetGetType(a0);
}

pub export fn wgpuQueueAddRef(a0: types.WGPUQueue) callconv(.c) void {
    native.doeNativeQueueAddRef(a0);
}

pub export fn wgpuRenderBundleAddRef(_: render.RenderBundle) callconv(.c) void {
    // Render bundles are opaque Doe allocations; no ref counting yet.
}

pub export fn wgpuRenderBundleEncoderAddRef(_: render.RenderBundleEncoder) callconv(.c) void {
    // Render bundle encoders are opaque Doe allocations; no ref counting yet.
}

pub export fn wgpuRenderBundleEncoderDraw(a0: render.RenderBundleEncoder, a1: u32, a2: u32, a3: u32, a4: u32) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDraw(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderBundleEncoderDrawIndexed(a0: render.RenderBundleEncoder, a1: u32, a2: u32, a3: u32, a4: i32, a5: u32) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDrawIndexed(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuRenderBundleEncoderDrawIndexedIndirect(a0: render.RenderBundleEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDrawIndexedIndirect(a0, a1, a2);
}

pub export fn wgpuRenderBundleEncoderDrawIndirect(a0: render.RenderBundleEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDrawIndirect(a0, a1, a2);
}

pub export fn wgpuRenderBundleEncoderFinish(a0: render.RenderBundleEncoder, a1: ?*const anyopaque) callconv(.c) render.RenderBundle {
    return native.doeNativeRenderBundleEncoderFinish(a0, @ptrCast(@alignCast(a1)));
}

pub export fn wgpuRenderBundleEncoderInsertDebugMarker(a0: render.RenderBundleEncoder, a1: types.WGPUStringView) callconv(.c) void {
    native.doeNativeRenderBundleEncoderInsertDebugMarker(a0, if (a1.data) |d| d else null, a1.length);
}

pub export fn wgpuRenderBundleEncoderPopDebugGroup(a0: render.RenderBundleEncoder) callconv(.c) void {
    native.doeNativeRenderBundleEncoderPopDebugGroup(a0);
}

pub export fn wgpuRenderBundleEncoderPushDebugGroup(a0: render.RenderBundleEncoder, a1: types.WGPUStringView) callconv(.c) void {
    native.doeNativeRenderBundleEncoderPushDebugGroup(a0, if (a1.data) |d| d else null, a1.length);
}

pub export fn wgpuRenderBundleEncoderRelease(a0: render.RenderBundleEncoder) callconv(.c) void {
    native.doeNativeRenderBundleEncoderRelease(a0);
}

pub export fn wgpuRenderBundleEncoderSetBindGroup(a0: render.RenderBundleEncoder, a1: u32, a2: types.WGPUBindGroup, a3: usize, a4: ?[*]const u32) callconv(.c) void {
    native.doeNativeRenderBundleEncoderSetBindGroup(a0, a1, a2, a3, a4);
}
