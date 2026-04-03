pub const std = @import("std");
pub const abi_base = @import("core/abi/wgpu_base_types.zig");
pub const abi_descriptor = @import("core/abi/wgpu_descriptor_types.zig");
pub const types = struct {
    pub const WGPUAdapter = abi_base.WGPUAdapter;
    pub const WGPUBindGroup = abi_base.WGPUBindGroup;
    pub const WGPUBindGroupLayout = abi_base.WGPUBindGroupLayout;
    pub const WGPUBool = abi_base.WGPUBool;
    pub const WGPUBuffer = abi_base.WGPUBuffer;
    pub const WGPUCommandBuffer = abi_base.WGPUCommandBuffer;
    pub const WGPUCommandEncoder = abi_base.WGPUCommandEncoder;
    pub const WGPUComputePassEncoder = abi_base.WGPUComputePassEncoder;
    pub const WGPUComputePipeline = abi_base.WGPUComputePipeline;
    pub const WGPUDevice = abi_base.WGPUDevice;
    pub const WGPUFuture = abi_base.WGPUFuture;
    pub const WGPUInstance = abi_base.WGPUInstance;
    pub const WGPUPipelineLayout = abi_base.WGPUPipelineLayout;
    pub const WGPUQuerySet = abi_base.WGPUQuerySet;
    pub const WGPUQueryType = abi_base.WGPUQueryType;
    pub const WGPUQueue = abi_base.WGPUQueue;
    pub const WGPURenderPipeline = abi_base.WGPURenderPipeline;
    pub const WGPUStatus = abi_base.WGPUStatus;
    pub const WGPUStatus_Success = abi_base.WGPUStatus_Success;
    pub const WGPUStringView = abi_base.WGPUStringView;
    pub const WGPUTextureFormat = abi_base.WGPUTextureFormat;
    pub const WGPU_FALSE = abi_base.WGPU_FALSE;
    pub const WGPUConstantEntry = abi_descriptor.WGPUConstantEntry;
    pub const WGPUComputePipelineDescriptor = abi_descriptor.WGPUComputePipelineDescriptor;
};
pub const p1cap = @import("wgpu_p1_capability_procs.zig");
pub const p0 = @import("wgpu_p0_procs.zig");
pub const p1res = @import("wgpu_p1_resource_table_procs.zig");
pub const p2life = @import("wgpu_p2_lifecycle_procs.zig");
pub const surface = @import("full/surface/wgpu_surface_procs.zig");
pub const texture = @import("wgpu_texture_procs.zig");
pub const render = @import("full/render/wgpu_render_api.zig");
pub const async_procs = @import("wgpu_async_procs.zig");
pub const native = @import("doe_native_base.zig");
pub const query_native = @import("doe_query_native.zig");
pub const error_scope = @import("error_scope.zig");
pub const task_pool = @import("runtime/task_pool.zig");
pub const singleflight = @import("runtime/pipeline_singleflight.zig");
pub const pipeline_cache_integration = @import("runtime/pipeline_cache_integration.zig");

pub extern fn wgpuGetProcAddress(name: abi_base.WGPUStringView) callconv(.c) p1cap.WGPUProc;
pub extern fn doeWgpuDropinAbortMissingRequiredSymbol(name: abi_base.WGPUStringView) callconv(.c) noreturn;
pub extern fn doeNativeComputePassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void;
pub extern fn doeNativeQuerySetDestroy(qs_raw: ?*anyopaque) callconv(.c) void;
pub extern fn doeNativeQuerySetGetCount(qs_raw: ?*anyopaque) callconv(.c) u32;
pub extern fn doeNativeQuerySetGetType(qs_raw: ?*anyopaque) callconv(.c) abi_base.WGPUQueryType;

pub const FEATURE_CANDIDATES = [_]abi_base.WGPUFeatureName{
    abi_base.WGPUFeatureName_CoreFeaturesAndLimits,
    abi_base.WGPUFeatureName_DepthClipControl,
    abi_base.WGPUFeatureName_Depth32FloatStencil8,
    abi_base.WGPUFeatureName_TextureCompressionBC,
    abi_base.WGPUFeatureName_TextureCompressionBCSliced3D,
    abi_base.WGPUFeatureName_TextureCompressionETC2,
    abi_base.WGPUFeatureName_TextureCompressionASTC,
    abi_base.WGPUFeatureName_TextureCompressionASTCSliced3D,
    abi_base.WGPUFeatureName_RG11B10UfloatRenderable,
    abi_base.WGPUFeatureName_TimestampQuery,
    abi_base.WGPUFeatureName_BGRA8UnormStorage,
    abi_base.WGPUFeatureName_ShaderF16,
    abi_base.WGPUFeatureName_IndirectFirstInstance,
    abi_base.WGPUFeatureName_Float32Filterable,
    abi_base.WGPUFeatureName_Subgroups,
    abi_base.WGPUFeatureName_SubgroupsF16,
    abi_base.WGPUFeatureName_Float32Blendable,
    abi_base.WGPUFeatureName_ClipDistances,
    abi_base.WGPUFeatureName_DualSourceBlending,
    abi_base.WGPUFeatureName_TextureFormatsTier1,
    abi_base.WGPUFeatureName_TextureFormatsTier2,
    abi_base.WGPUFeatureName_PrimitiveIndex,
    abi_base.WGPUFeatureName_TextureComponentSwizzle,
};

pub const LoggingCallback = *const fn (u32, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;
pub const PopErrorScopeCallback = *const fn (u32, u32, abi_base.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;

pub const LoggingCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    callback: ?LoggingCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const PopErrorScopeBridgeState = struct {
    callback: ?PopErrorScopeCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub fn string_view_slice(view: abi_base.WGPUStringView) []const u8 {
    const data = view.data orelse return "";
    if (view.length == abi_base.WGPU_STRLEN) {
        return std.mem.sliceTo(@as([*:0]const u8, @ptrCast(data)), 0);
    }
    return data[0..view.length];
}

pub fn dup_string_view(view: abi_base.WGPUStringView) ?[]u8 {
    const src = string_view_slice(view);
    if (src.len == 0) return null;
    return std.heap.c_allocator.dupe(u8, src) catch null;
}

pub fn make_string_view(bytes: ?[]u8) abi_base.WGPUStringView {
    if (bytes) |owned| {
        return .{ .data = owned.ptr, .length = owned.len };
    }
    return .{ .data = null, .length = 0 };
}

pub fn bridge_pop_error_scope_callback(
    error_type: u32,
    msg: abi_base.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = userdata2;
    const state = userdata1 orelse return;
    const bridge_state: *PopErrorScopeBridgeState = @ptrCast(@alignCast(state));
    const callback = bridge_state.callback orelse return;
    callback(async_procs.POP_ERROR_SCOPE_STATUS_SUCCESS, error_type, msg, bridge_state.userdata1, bridge_state.userdata2);
}

pub fn static_string_view(comptime text: []const u8) abi_base.WGPUStringView {
    return .{ .data = text.ptr, .length = text.len };
}

pub fn backend_type_for(adapter: *native.DoeAdapter) abi_descriptor.WGPUBackendType {
    return switch (adapter.backend) {
        .metal => .metal,
        .vulkan => .vulkan,
        .d3d12 => .d3d12,
    };
}

pub fn fill_adapter_info_struct(adapter_raw: abi_base.WGPUAdapter, out: *p1cap.AdapterInfo) abi_base.WGPUStatus {
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
    return abi_base.WGPUStatus_Success;
}

pub fn fill_supported_features_from_adapter(adapter_raw: abi_base.WGPUAdapter, out: *p1cap.SupportedFeatures) void {
    out.* = p1cap.initSupportedFeatures();
    var count: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeAdapterHasFeature(adapter_raw, feature) != 0) count += 1;
    }
    if (count == 0) return;
    const owned = std.heap.c_allocator.alloc(abi_base.WGPUFeatureName, count) catch return;
    var write_index: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeAdapterHasFeature(adapter_raw, feature) == 0) continue;
        owned[write_index] = feature;
        write_index += 1;
    }
    out.featureCount = write_index;
    out.features = owned.ptr;
}

pub fn fill_supported_features_from_device(device_raw: abi_base.WGPUDevice, out: *p1cap.SupportedFeatures) void {
    out.* = p1cap.initSupportedFeatures();
    var count: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeDeviceHasFeature(device_raw, feature) != 0) count += 1;
    }
    if (count == 0) return;
    const owned = std.heap.c_allocator.alloc(abi_base.WGPUFeatureName, count) catch return;
    var write_index: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeDeviceHasFeature(device_raw, feature) == 0) continue;
        owned[write_index] = feature;
        write_index += 1;
    }
    out.featureCount = write_index;
    out.features = owned.ptr;
}

pub fn symbolView(comptime name: []const u8) abi_base.WGPUStringView {
    return .{ .data = name.ptr, .length = name.len };
}

pub fn resolveRequiredProc(comptime FnType: type, comptime symbol_name: []const u8) FnType {
    const proc = wgpuGetProcAddress(symbolView(symbol_name)) orelse
        doeWgpuDropinAbortMissingRequiredSymbol(symbolView(symbol_name));
    return @as(FnType, @ptrCast(proc));
}
