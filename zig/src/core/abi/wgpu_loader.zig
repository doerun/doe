const std = @import("std");
const builtin = @import("builtin");
const model = @import("../../model.zig");
const types = @import("wgpu_types.zig");

pub const BUFFER_MAP_ASYNC_KEY: u64 = 0xFFFF_FFFF_FFFF_FFE0;

const DlInfo = extern struct {
    dli_fname: [*c]const u8,
    dli_fbase: ?*anyopaque,
    dli_sname: [*c]const u8,
    dli_saddr: ?*anyopaque,
};

extern fn dladdr(addr: *const anyopaque, info: *DlInfo) c_int;

pub const native_library_names = blk: {
    switch (builtin.os.tag) {
        .windows => break :blk &[_][]const u8{
            "webgpu.dll",
            "webgpu-native.dll",
            "wgpu_native.dll",
        },
        .macos => break :blk &[_][]const u8{
            "libwebgpu_dawn.dylib",
            "libwebgpu.dylib",
            "webgpu.dylib",
            "libwgpu_native.dylib",
        },
        else => break :blk &[_][]const u8{
            "libwebgpu_dawn.so",
            "libwebgpu.so",
            "libwgpu_native.so",
            "libwgpu_native.so.0",
            "wgpu_native.so",
        },
    }
};

pub const BUFFER_UPLOAD_KEY = 0xFFFF_FFFF_FFFF_FFFF;
pub const DEFAULT_TIMEOUT_NS = 2_000_000_000;
pub const QUEUE_WAIT_TIMEOUT_NS = 2_000_000_000;
pub const DEFAULT_WAIT_SLICE_NS = 50_000_000;
const FnAnySymbol = *const fn () callconv(.c) void;

pub const OPTIONAL_API_SURFACE_SYMBOLS = [_][:0]const u8{
    "wgpuBindGroupLayoutSetLabel",
    "wgpuBindGroupSetLabel",
    "wgpuBufferGetMapState",
    "wgpuBufferGetMappedRange",
    "wgpuBufferGetSize",
    "wgpuBufferGetUsage",
    "wgpuBufferReadMappedRange",
    "wgpuBufferSetLabel",
    "wgpuBufferWriteMappedRange",
    "wgpuCommandBufferSetLabel",
    "wgpuCommandEncoderInsertDebugMarker",
    "wgpuCommandEncoderPopDebugGroup",
    "wgpuCommandEncoderPushDebugGroup",
    "wgpuCommandEncoderSetLabel",
    "wgpuComputePassEncoderInsertDebugMarker",
    "wgpuComputePassEncoderPopDebugGroup",
    "wgpuComputePassEncoderPushDebugGroup",
    "wgpuComputePassEncoderSetLabel",
    "wgpuComputePipelineGetBindGroupLayout",
    "wgpuComputePipelineSetLabel",
    "wgpuDeviceGetLostFuture",
    "wgpuDeviceSetLabel",
    "wgpuExternalTextureRelease",
    "wgpuExternalTextureSetLabel",
    "wgpuPipelineLayoutSetLabel",
    "wgpuQuerySetSetLabel",
    "wgpuQueueSetLabel",
    "wgpuRenderPassEncoderInsertDebugMarker",
    "wgpuRenderPassEncoderPopDebugGroup",
    "wgpuRenderPassEncoderPushDebugGroup",
    "wgpuRenderPassEncoderSetLabel",
    "wgpuRenderPipelineSetLabel",
    "wgpuSamplerSetLabel",
    "wgpuShaderModuleSetLabel",
    "wgpuSurfaceSetLabel",
    "wgpuTextureSetLabel",
    "wgpuTextureViewSetLabel",
};

fn currentModuleDirectory(buffer: *[std.fs.max_path_bytes]u8) ?[]const u8 {
    if (builtin.os.tag == .windows) return null;

    var info: DlInfo = std.mem.zeroes(DlInfo);
    const symbol_addr: *const anyopaque = @ptrCast(&openLibrary);
    if (dladdr(symbol_addr, &info) == 0) return null;

    const module_path_ptr = info.dli_fname;
    if (module_path_ptr == null) return null;
    const module_path = std.mem.span(module_path_ptr);
    const dir = std.fs.path.dirname(module_path) orelse return null;
    if (dir.len > buffer.len) return null;
    @memcpy(buffer[0..dir.len], dir);
    return buffer[0..dir.len];
}

fn openLibraryRelativeToModule() ?std.DynLib {
    var module_dir_buf: [std.fs.max_path_bytes]u8 = undefined;
    const module_dir = currentModuleDirectory(&module_dir_buf) orelse return null;

    var candidate_path_buf: [std.fs.max_path_bytes]u8 = undefined;
    for (native_library_names) |candidate| {
        const full_path = std.fmt.bufPrint(
            &candidate_path_buf,
            "{s}" ++ std.fs.path.sep_str ++ "{s}",
            .{ module_dir, candidate },
        ) catch continue;
        const lib = std.DynLib.open(full_path) catch continue;
        return lib;
    }

    return null;
}

pub fn openLibrary() !std.DynLib {
    var last_err: ?anyerror = null;

    for (native_library_names) |candidate| {
        const lib = std.DynLib.open(candidate) catch |err| {
            last_err = err;
            continue;
        };
        return lib;
    }

    if (openLibraryRelativeToModule()) |lib| {
        return lib;
    }

    if (last_err) |_| {}
    return error.LibraryOpenFailed;
}

pub fn loadProcs(lib: std.DynLib) !types.Procs {
    const procs: types.Procs = .{
        .wgpuCreateInstance = try loadProc(lib, "wgpuCreateInstance", types.FnWgpuCreateInstance),
        .wgpuInstanceRequestAdapter = try loadProc(lib, "wgpuInstanceRequestAdapter", types.FnWgpuInstanceRequestAdapter),
        .wgpuInstanceWaitAny = try loadProc(lib, "wgpuInstanceWaitAny", types.FnWgpuInstanceWaitAny),
        .wgpuInstanceProcessEvents = try loadProc(lib, "wgpuInstanceProcessEvents", types.FnWgpuInstanceProcessEvents),
        .wgpuAdapterRequestDevice = try loadProc(lib, "wgpuAdapterRequestDevice", types.FnWgpuAdapterRequestDevice),
        .wgpuDeviceCreateBuffer = try loadProc(lib, "wgpuDeviceCreateBuffer", types.FnWgpuDeviceCreateBuffer),
        .wgpuDeviceCreateShaderModule = try loadProc(lib, "wgpuDeviceCreateShaderModule", types.FnWgpuDeviceCreateShaderModule),
        .wgpuShaderModuleRelease = try loadProc(lib, "wgpuShaderModuleRelease", types.FnWgpuShaderModuleRelease),
        .wgpuDeviceCreateComputePipeline = try loadProc(lib, "wgpuDeviceCreateComputePipeline", types.FnWgpuDeviceCreateComputePipeline),
        .wgpuComputePipelineRelease = try loadProc(lib, "wgpuComputePipelineRelease", types.FnWgpuComputePipelineRelease),
        .wgpuRenderPipelineRelease = try loadOptionalProc(lib, "wgpuRenderPipelineRelease", types.FnWgpuRenderPipelineRelease),
        .wgpuDeviceCreateCommandEncoder = try loadProc(lib, "wgpuDeviceCreateCommandEncoder", types.FnWgpuDeviceCreateCommandEncoder),
        .wgpuCommandEncoderBeginComputePass = try loadProc(lib, "wgpuCommandEncoderBeginComputePass", types.FnWgpuCommandEncoderBeginComputePass),
        .wgpuDeviceCreateRenderPipeline = try loadOptionalProc(lib, "wgpuDeviceCreateRenderPipeline", types.FnWgpuDeviceCreateRenderPipeline),
        .wgpuCommandEncoderBeginRenderPass = try loadOptionalProc(lib, "wgpuCommandEncoderBeginRenderPass", types.FnWgpuCommandEncoderBeginRenderPass),
        .wgpuCommandEncoderWriteTimestamp = try loadOptionalProc(lib, "wgpuCommandEncoderWriteTimestamp", types.FnWgpuCommandEncoderWriteTimestamp),
        .wgpuCommandEncoderCopyBufferToBuffer = try loadProc(lib, "wgpuCommandEncoderCopyBufferToBuffer", types.FnWgpuCommandEncoderCopyBufferToBuffer),
        .wgpuCommandEncoderCopyBufferToTexture = try loadProc(lib, "wgpuCommandEncoderCopyBufferToTexture", types.FnWgpuCommandEncoderCopyBufferToTexture),
        .wgpuCommandEncoderCopyTextureToBuffer = try loadProc(lib, "wgpuCommandEncoderCopyTextureToBuffer", types.FnWgpuCommandEncoderCopyTextureToBuffer),
        .wgpuCommandEncoderCopyTextureToTexture = try loadProc(lib, "wgpuCommandEncoderCopyTextureToTexture", types.FnWgpuCommandEncoderCopyTextureToTexture),
        .wgpuComputePassEncoderSetBindGroup = try loadProc(lib, "wgpuComputePassEncoderSetBindGroup", types.FnWgpuComputePassEncoderSetBindGroup),
        .wgpuComputePassEncoderSetPipeline = try loadProc(lib, "wgpuComputePassEncoderSetPipeline", types.FnWgpuComputePassEncoderSetPipeline),
        .wgpuComputePassEncoderDispatchWorkgroups = try loadProc(lib, "wgpuComputePassEncoderDispatchWorkgroups", types.FnWgpuComputePassEncoderDispatchWorkgroups),
        .wgpuComputePassEncoderEnd = try loadProc(lib, "wgpuComputePassEncoderEnd", types.FnWgpuComputePassEncoderEnd),
        .wgpuComputePassEncoderRelease = try loadProc(lib, "wgpuComputePassEncoderRelease", types.FnWgpuComputePassEncoderRelease),
        .wgpuRenderPassEncoderSetPipeline = try loadOptionalProc(lib, "wgpuRenderPassEncoderSetPipeline", types.FnWgpuRenderPassEncoderSetPipeline),
        .wgpuRenderPassEncoderSetVertexBuffer = try loadOptionalProc(lib, "wgpuRenderPassEncoderSetVertexBuffer", types.FnWgpuRenderPassEncoderSetVertexBuffer),
        .wgpuRenderPassEncoderSetIndexBuffer = try loadOptionalProc(lib, "wgpuRenderPassEncoderSetIndexBuffer", types.FnWgpuRenderPassEncoderSetIndexBuffer),
        .wgpuRenderPassEncoderSetBindGroup = try loadOptionalProc(lib, "wgpuRenderPassEncoderSetBindGroup", types.FnWgpuRenderPassEncoderSetBindGroup),
        .wgpuRenderPassEncoderDraw = try loadOptionalProc(lib, "wgpuRenderPassEncoderDraw", types.FnWgpuRenderPassEncoderDraw),
        .wgpuRenderPassEncoderDrawIndexed = try loadOptionalProc(lib, "wgpuRenderPassEncoderDrawIndexed", types.FnWgpuRenderPassEncoderDrawIndexed),
        .wgpuRenderPassEncoderDrawIndirect = try loadOptionalProc(lib, "wgpuRenderPassEncoderDrawIndirect", types.FnWgpuRenderPassEncoderDrawIndirect),
        .wgpuRenderPassEncoderDrawIndexedIndirect = try loadOptionalProc(lib, "wgpuRenderPassEncoderDrawIndexedIndirect", types.FnWgpuRenderPassEncoderDrawIndexedIndirect),
        .wgpuRenderPassEncoderEnd = try loadOptionalProc(lib, "wgpuRenderPassEncoderEnd", types.FnWgpuRenderPassEncoderEnd),
        .wgpuRenderPassEncoderRelease = try loadOptionalProc(lib, "wgpuRenderPassEncoderRelease", types.FnWgpuRenderPassEncoderRelease),
        .wgpuDeviceCreateTexture = try loadProc(lib, "wgpuDeviceCreateTexture", types.FnWgpuDeviceCreateTexture),
        .wgpuTextureCreateView = try loadProc(lib, "wgpuTextureCreateView", types.FnWgpuTextureCreateView),
        .wgpuDeviceCreateBindGroupLayout = try loadProc(lib, "wgpuDeviceCreateBindGroupLayout", types.FnWgpuDeviceCreateBindGroupLayout),
        .wgpuBindGroupLayoutRelease = try loadProc(lib, "wgpuBindGroupLayoutRelease", types.FnWgpuBindGroupLayoutRelease),
        .wgpuDeviceCreateBindGroup = try loadProc(lib, "wgpuDeviceCreateBindGroup", types.FnWgpuDeviceCreateBindGroup),
        .wgpuBindGroupRelease = try loadProc(lib, "wgpuBindGroupRelease", types.FnWgpuBindGroupRelease),
        .wgpuDeviceCreatePipelineLayout = try loadProc(lib, "wgpuDeviceCreatePipelineLayout", types.FnWgpuDeviceCreatePipelineLayout),
        .wgpuPipelineLayoutRelease = try loadProc(lib, "wgpuPipelineLayoutRelease", types.FnWgpuPipelineLayoutRelease),
        .wgpuTextureRelease = try loadProc(lib, "wgpuTextureRelease", types.FnWgpuTextureRelease),
        .wgpuTextureViewRelease = try loadProc(lib, "wgpuTextureViewRelease", types.FnWgpuTextureViewRelease),
        .wgpuCommandEncoderFinish = try loadProc(lib, "wgpuCommandEncoderFinish", types.FnWgpuCommandEncoderFinish),
        .wgpuDeviceGetQueue = try loadProc(lib, "wgpuDeviceGetQueue", types.FnWgpuDeviceGetQueue),
        .wgpuQueueSubmit = try loadProc(lib, "wgpuQueueSubmit", types.FnWgpuQueueSubmit),
        .wgpuQueueOnSubmittedWorkDone = try loadProc(lib, "wgpuQueueOnSubmittedWorkDone", types.FnWgpuQueueOnSubmittedWorkDone),
        .wgpuQueueWriteBuffer = try loadProc(lib, "wgpuQueueWriteBuffer", types.FnWgpuQueueWriteBuffer),
        .wgpuInstanceRelease = try loadProc(lib, "wgpuInstanceRelease", types.FnWgpuInstanceRelease),
        .wgpuAdapterRelease = try loadProc(lib, "wgpuAdapterRelease", types.FnWgpuAdapterRelease),
        .wgpuDeviceRelease = try loadProc(lib, "wgpuDeviceRelease", types.FnWgpuDeviceRelease),
        .wgpuQueueRelease = try loadProc(lib, "wgpuQueueRelease", types.FnWgpuQueueRelease),
        .wgpuCommandEncoderRelease = try loadProc(lib, "wgpuCommandEncoderRelease", types.FnWgpuCommandEncoderRelease),
        .wgpuCommandBufferRelease = try loadProc(lib, "wgpuCommandBufferRelease", types.FnWgpuCommandBufferRelease),
        .wgpuBufferRelease = try loadProc(lib, "wgpuBufferRelease", types.FnWgpuBufferRelease),
        .wgpuAdapterHasFeature = try loadProc(lib, "wgpuAdapterHasFeature", types.FnWgpuAdapterHasFeature),
        .wgpuDeviceHasFeature = try loadOptionalProc(lib, "wgpuDeviceHasFeature", types.FnWgpuDeviceHasFeature),
        .wgpuDeviceCreateQuerySet = try loadProc(lib, "wgpuDeviceCreateQuerySet", types.FnWgpuDeviceCreateQuerySet),
        .wgpuCommandEncoderResolveQuerySet = try loadProc(lib, "wgpuCommandEncoderResolveQuerySet", types.FnWgpuCommandEncoderResolveQuerySet),
        .wgpuQuerySetRelease = try loadProc(lib, "wgpuQuerySetRelease", types.FnWgpuQuerySetRelease),
        .wgpuBufferMapAsync = try loadProc(lib, "wgpuBufferMapAsync", types.FnWgpuBufferMapAsync),
        .wgpuBufferGetConstMappedRange = try loadProc(lib, "wgpuBufferGetConstMappedRange", types.FnWgpuBufferGetConstMappedRange),
        .wgpuBufferGetMappedRange = try loadProc(lib, "wgpuBufferGetMappedRange", types.FnWgpuBufferGetMappedRange),
        .wgpuBufferUnmap = try loadProc(lib, "wgpuBufferUnmap", types.FnWgpuBufferUnmap),
    };
    preloadOptionalApiSurfaceSymbols(lib);
    return procs;
}

pub fn preloadOptionalApiSurfaceSymbols(lib: std.DynLib) void {
    var mutable = lib;
    inline for (OPTIONAL_API_SURFACE_SYMBOLS) |name| {
        _ = mutable.lookup(FnAnySymbol, name);
    }
}

fn loadProc(
    lib: std.DynLib,
    comptime name: [:0]const u8,
    comptime T: type,
) !T {
    var mutable = lib;
    return mutable.lookup(T, name) orelse error.SymbolMissing;
}

fn loadOptionalProc(
    lib: std.DynLib,
    comptime name: [:0]const u8,
    comptime T: type,
) !?T {
    var mutable = lib;
    return mutable.lookup(T, name);
}

pub fn queueWorkDoneCallback(
    status: types.WGPUQueueWorkDoneStatus,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    const state = @as(*types.QueueSubmitState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    state.status = status;
}

pub fn adapterCallback(
    status: types.WGPURequestAdapterStatus,
    adapter: types.WGPUAdapter,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    const state = @as(*types.RequestState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    state.status = status;
    state.adapter = adapter;
}

pub fn deviceRequestCallback(
    status: types.WGPURequestDeviceStatus,
    device: types.WGPUDevice,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    const state = @as(*types.DeviceRequestState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    state.status = status;
    state.device = device;
}

pub fn bufferMapCallback(
    status: types.WGPUMapAsyncStatus,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    const state = @as(*types.BufferMapState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    state.status = status;
}

pub fn uncapturedErrorCallback(
    _: ?*const anyopaque,
    error_type: types.WGPUErrorType,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    _: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    const state_ptr = userdata1 orelse return;
    const state = @as(*types.UncapturedErrorState, @ptrCast(@alignCast(state_ptr)));
    state.error_type.store(@intFromEnum(error_type), .release);
    state.pending.store(1, .release);
}

pub fn alignTo(value: u64, alignment: u64) u64 {
    if (alignment == 0) return value;
    const mask = alignment - 1;
    return (value + mask) & ~mask;
}

pub fn emptyStringView() types.WGPUStringView {
    return types.WGPUStringView{ .data = null, .length = types.WGPU_STRLEN };
}

pub fn stringView(source: []const u8) types.WGPUStringView {
    if (source.len == 0) return emptyStringView();
    return types.WGPUStringView{
        .data = source.ptr,
        .length = source.len,
    };
}

pub fn normalizeCopyLayoutValue(raw_layout: u32) u32 {
    if (raw_layout == 0 or raw_layout == model.WGPUCopyStrideUndefined) return types.WGPU_COPY_STRIDE_UNDEFINED;
    return raw_layout;
}

pub fn normalizeTextureAspect(raw_aspect: u32) types.WGPUTextureAspect {
    return switch (raw_aspect) {
        model.WGPUTextureAspect_DepthOnly => types.WGPUTextureAspect_DepthOnly,
        model.WGPUTextureAspect_StencilOnly => types.WGPUTextureAspect_StencilOnly,
        else => types.WGPUTextureAspect_All,
    };
}
