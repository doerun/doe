const std = @import("std");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");

pub const CREATE_PIPELINE_ASYNC_STATUS_SUCCESS: u32 = 1;
pub const POP_ERROR_SCOPE_STATUS_SUCCESS: u32 = 1;
pub const COMPILATION_INFO_STATUS_SUCCESS: u32 = 1;
pub const ERROR_FILTER_VALIDATION: u32 = 1;
pub const ERROR_FILTER_OUT_OF_MEMORY: u32 = 2;
pub const ERROR_FILTER_INTERNAL: u32 = 3;

const CreateRenderPipelineAsyncCallback = *const fn (u32, types.WGPURenderPipeline, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;
const PopErrorScopeCallback = *const fn (u32, u32, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;
const CompilationInfoCallback = *const fn (u32, ?*const anyopaque, ?*anyopaque, ?*anyopaque) callconv(.c) void;

pub const CreateRenderPipelineAsyncCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: types.WGPUCallbackMode,
    callback: ?CreateRenderPipelineAsyncCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const PopErrorScopeCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: types.WGPUCallbackMode,
    callback: ?PopErrorScopeCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const CompilationInfoCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: types.WGPUCallbackMode,
    callback: ?CompilationInfoCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

const FnDeviceCreateRenderPipelineAsync = *const fn (types.WGPUDevice, *const anyopaque, CreateRenderPipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture;
const FnDevicePushErrorScope = *const fn (types.WGPUDevice, u32) callconv(.c) void;
const FnDevicePopErrorScope = *const fn (types.WGPUDevice, PopErrorScopeCallbackInfo) callconv(.c) types.WGPUFuture;
const FnShaderModuleGetCompilationInfo = *const fn (types.WGPUShaderModule, CompilationInfoCallbackInfo) callconv(.c) types.WGPUFuture;

pub const AsyncProcs = struct {
    device_create_render_pipeline_async: FnDeviceCreateRenderPipelineAsync,
    device_push_error_scope: FnDevicePushErrorScope,
    device_pop_error_scope: FnDevicePopErrorScope,
    shader_module_get_compilation_info: FnShaderModuleGetCompilationInfo,
};

pub const RenderPipelineAsyncState = struct {
    done: bool = false,
    status: u32 = 0,
    pipeline: types.WGPURenderPipeline = null,
};

pub const PopErrorScopeState = struct {
    done: bool = false,
    status: u32 = 0,
    error_type: u32 = 0,
};

pub const CompilationInfoState = struct {
    done: bool = false,
    status: u32 = 0,
};

fn loadProc(comptime T: type, lib: std.DynLib, comptime name: [:0]const u8) ?T {
    var mutable = lib;
    return mutable.lookup(T, name);
}

pub fn loadAsyncProcs(dyn_lib: ?std.DynLib) ?AsyncProcs {
    const lib = dyn_lib orelse return null;
    return .{
        .device_create_render_pipeline_async = loadProc(FnDeviceCreateRenderPipelineAsync, lib, "wgpuDeviceCreateRenderPipelineAsync") orelse return null,
        .device_push_error_scope = loadProc(FnDevicePushErrorScope, lib, "wgpuDevicePushErrorScope") orelse return null,
        .device_pop_error_scope = loadProc(FnDevicePopErrorScope, lib, "wgpuDevicePopErrorScope") orelse return null,
        .shader_module_get_compilation_info = loadProc(FnShaderModuleGetCompilationInfo, lib, "wgpuShaderModuleGetCompilationInfo") orelse return null,
    };
}

pub fn createRenderPipelineAsyncAndWait(
    async_procs: AsyncProcs,
    instance: types.WGPUInstance,
    procs: types.Procs,
    device: types.WGPUDevice,
    descriptor: *const anyopaque,
) !types.WGPURenderPipeline {
    var state = RenderPipelineAsyncState{};
    const callback_info = CreateRenderPipelineAsyncCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_AllowProcessEvents,
        .callback = renderPipelineAsyncCallback,
        .userdata1 = &state,
        .userdata2 = null,
    };
    const future = async_procs.device_create_render_pipeline_async(device, descriptor, callback_info);
    if (future.id == 0) return error.AsyncFutureUnavailable;
    try processEventsUntil(instance, procs, &state.done, loader.DEFAULT_TIMEOUT_NS);
    if (!state.done) return error.AsyncFutureTimedOut;
    if (state.status != CREATE_PIPELINE_ASYNC_STATUS_SUCCESS) return error.AsyncPipelineCreationFailed;
    return state.pipeline orelse error.AsyncPipelineCreationFailed;
}

pub fn pushErrorScope(async_procs: AsyncProcs, device: types.WGPUDevice, filter: u32) void {
    async_procs.device_push_error_scope(device, filter);
}

pub fn popErrorScopeAndWait(
    async_procs: AsyncProcs,
    instance: types.WGPUInstance,
    procs: types.Procs,
    device: types.WGPUDevice,
) !PopErrorScopeState {
    var state = PopErrorScopeState{};
    const callback_info = PopErrorScopeCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_AllowProcessEvents,
        .callback = popErrorScopeCallback,
        .userdata1 = &state,
        .userdata2 = null,
    };
    const future = async_procs.device_pop_error_scope(device, callback_info);
    if (future.id == 0) return error.AsyncFutureUnavailable;
    try processEventsUntil(instance, procs, &state.done, loader.DEFAULT_TIMEOUT_NS);
    if (!state.done) return error.AsyncFutureTimedOut;
    return state;
}

pub fn requestShaderCompilationInfoAndWait(
    async_procs: AsyncProcs,
    instance: types.WGPUInstance,
    procs: types.Procs,
    shader_module: types.WGPUShaderModule,
) !CompilationInfoState {
    var state = CompilationInfoState{};
    const callback_info = CompilationInfoCallbackInfo{
        .nextInChain = null,
        .mode = types.WGPUCallbackMode_AllowProcessEvents,
        .callback = compilationInfoCallback,
        .userdata1 = &state,
        .userdata2 = null,
    };
    const future = async_procs.shader_module_get_compilation_info(shader_module, callback_info);
    if (future.id == 0) return error.AsyncFutureUnavailable;
    try processEventsUntil(instance, procs, &state.done, loader.DEFAULT_TIMEOUT_NS);
    if (!state.done) return error.AsyncFutureTimedOut;
    return state;
}

fn processEventsUntil(
    instance: types.WGPUInstance,
    procs: types.Procs,
    done: *const bool,
    timeout_ns: u64,
) !void {
    const start = std.time.nanoTimestamp();
    var spins: u32 = 0;
    while (!done.*) {
        procs.wgpuInstanceProcessEvents(instance);
        const elapsed = std.time.nanoTimestamp() - start;
        if (elapsed >= timeout_ns) return error.WaitTimedOut;
        spins += 1;
        if (spins > 1000) std.Thread.sleep(1_000);
    }
}

fn renderPipelineAsyncCallback(
    status: u32,
    pipeline: types.WGPURenderPipeline,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    const state = @as(*RenderPipelineAsyncState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    state.status = status;
    state.pipeline = pipeline;
}

fn popErrorScopeCallback(
    status: u32,
    error_type: u32,
    message: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = message;
    _ = userdata2;
    const state = @as(*PopErrorScopeState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    state.status = status;
    state.error_type = error_type;
}

fn compilationInfoCallback(
    status: u32,
    compilation_info: ?*const anyopaque,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = compilation_info;
    _ = userdata2;
    const state = @as(*CompilationInfoState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    state.status = status;
}
