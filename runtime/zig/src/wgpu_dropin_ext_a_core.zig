pub const std = @import("std");
pub const types = @import("core/abi/wgpu_types.zig");
pub const p1cap = @import("wgpu_p1_capability_procs.zig");
pub const p0 = @import("wgpu_p0_procs.zig");
pub const p1res = @import("wgpu_p1_resource_table_procs.zig");
pub const p2life = @import("wgpu_p2_lifecycle_procs.zig");
pub const surface = @import("full/surface/wgpu_surface_procs.zig");
pub const texture = @import("wgpu_texture_procs.zig");
pub const render = @import("full/render/wgpu_render_api.zig");
pub const async_procs = @import("wgpu_async_procs.zig");
pub const native = @import("doe_wgpu_native.zig");
pub const query_native = @import("doe_query_native.zig");
pub const error_scope = @import("error_scope.zig");
pub const task_pool = @import("runtime/task_pool.zig");
pub const singleflight = @import("runtime/pipeline_singleflight.zig");
pub const pipeline_cache_integration = @import("runtime/pipeline_cache_integration.zig");

pub extern fn wgpuGetProcAddress(name: types.WGPUStringView) callconv(.c) p1cap.WGPUProc;
pub extern fn doeWgpuDropinAbortMissingRequiredSymbol(name: types.WGPUStringView) callconv(.c) noreturn;
pub extern fn doeNativeComputePassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void;
pub extern fn doeNativeQuerySetDestroy(qs_raw: ?*anyopaque) callconv(.c) void;
pub extern fn doeNativeQuerySetGetCount(qs_raw: ?*anyopaque) callconv(.c) u32;
pub extern fn doeNativeQuerySetGetType(qs_raw: ?*anyopaque) callconv(.c) types.WGPUQueryType;

pub const FEATURE_CANDIDATES = [_]types.WGPUFeatureName{
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

pub const LoggingCallback = *const fn (u32, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;
pub const PopErrorScopeCallback = *const fn (u32, u32, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;

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

pub fn string_view_slice(view: types.WGPUStringView) []const u8 {
    const data = view.data orelse return "";
    if (view.length == types.WGPU_STRLEN) {
        return std.mem.sliceTo(@as([*:0]const u8, @ptrCast(data)), 0);
    }
    return data[0..view.length];
}

pub fn dup_string_view(view: types.WGPUStringView) ?[]u8 {
    const src = string_view_slice(view);
    if (src.len == 0) return null;
    return std.heap.c_allocator.dupe(u8, src) catch null;
}

pub fn make_string_view(bytes: ?[]u8) types.WGPUStringView {
    if (bytes) |owned| {
        return .{ .data = owned.ptr, .length = owned.len };
    }
    return .{ .data = null, .length = 0 };
}

pub fn bridge_pop_error_scope_callback(
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

pub fn static_string_view(comptime text: []const u8) types.WGPUStringView {
    return .{ .data = text.ptr, .length = text.len };
}

pub fn backend_type_for(adapter: *native.DoeAdapter) types.WGPUBackendType {
    return switch (adapter.backend) {
        .metal => .metal,
        .vulkan => .vulkan,
        .d3d12 => .d3d12,
    };
}

pub fn fill_adapter_info_struct(adapter_raw: types.WGPUAdapter, out: *p1cap.AdapterInfo) types.WGPUStatus {
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

pub fn fill_supported_features_from_adapter(adapter_raw: types.WGPUAdapter, out: *p1cap.SupportedFeatures) void {
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

pub fn fill_supported_features_from_device(device_raw: types.WGPUDevice, out: *p1cap.SupportedFeatures) void {
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

pub fn symbolView(comptime name: []const u8) types.WGPUStringView {
    return .{ .data = name.ptr, .length = name.len };
}

pub fn resolveRequiredProc(comptime FnType: type, comptime symbol_name: []const u8) FnType {
    const proc = wgpuGetProcAddress(symbolView(symbol_name)) orelse
        doeWgpuDropinAbortMissingRequiredSymbol(symbolView(symbol_name));
    return @as(FnType, @ptrCast(proc));
}
