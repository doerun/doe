const std = @import("std");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const backend_policy = @import("backend/backend_policy.zig");
const p1_capability_procs = @import("wgpu_p1_capability_procs.zig");
const dropin_ext_a = @import("wgpu_dropin_ext_a.zig");
const dropin_ext_b = @import("wgpu_dropin_ext_b.zig");
const dropin_ext_c = @import("wgpu_dropin_ext_c.zig");
const dropin_behavior_policy = @import("dropin/dropin_behavior_policy.zig");
const dropin_symbol_ownership = @import("dropin/dropin_symbol_ownership.zig");
const dropin_router = @import("dropin/dropin_router.zig");
const dropin_diagnostics = @import("dropin/dropin_diagnostics.zig");

const DROPIN_BEHAVIOR_CONFIG_JSON = @embedFile("../../config/dropin-abi-behavior.json");
const DROPIN_SYMBOL_OWNERSHIP_CONFIG_JSON = @embedFile("../../config/dropin-symbol-ownership.json");
const DROPIN_BEHAVIOR_DEFAULT_MODE: dropin_behavior_policy.BehaviorMode = .dawn_ownership;
const DROPIN_BEHAVIOR_DEFAULT_STRICT_NO_FALLBACK = true;

comptime {
    _ = dropin_ext_a;
    _ = dropin_ext_b;
    _ = dropin_ext_c;
    _ = dropin_behavior_policy;
    _ = dropin_symbol_ownership;
    _ = dropin_router;
    _ = dropin_diagnostics;
}

fn activeBehaviorMode() dropin_behavior_policy.BehaviorMode {
    return activeBehaviorConfig().mode;
}

fn activeStrictNoFallback() bool {
    return activeBehaviorConfig().strict_no_fallback;
}

const ParsedDropinBehaviorConfig = struct {
    mode: dropin_behavior_policy.BehaviorMode,
    strict_no_fallback: bool,
};

fn activeBehaviorConfig() ParsedDropinBehaviorConfig {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();

    const parsed = std.json.parseFromSlice(std.json.Value, arena.allocator(), DROPIN_BEHAVIOR_CONFIG_JSON, .{
        .ignore_unknown_fields = false,
    }) catch {
        return .{
            .mode = DROPIN_BEHAVIOR_DEFAULT_MODE,
            .strict_no_fallback = DROPIN_BEHAVIOR_DEFAULT_STRICT_NO_FALLBACK,
        };
    };
    defer parsed.deinit();

    var root = parsed.value;
    if (root != .object) {
        return .{
            .mode = DROPIN_BEHAVIOR_DEFAULT_MODE,
            .strict_no_fallback = DROPIN_BEHAVIOR_DEFAULT_STRICT_NO_FALLBACK,
        };
    }

    const root_obj = root.object;
    const default_mode = parseModeValue(root_obj.get("defaultMode")) orelse DROPIN_BEHAVIOR_DEFAULT_MODE;
    var strict_no_fallback = DROPIN_BEHAVIOR_DEFAULT_STRICT_NO_FALLBACK;
    if (root_obj.get("strictFallbackForbidden")) |raw| {
        switch (raw) {
            .bool => |value| strict_no_fallback = value,
            else => return .{
                .mode = DROPIN_BEHAVIOR_DEFAULT_MODE,
                .strict_no_fallback = DROPIN_BEHAVIOR_DEFAULT_STRICT_NO_FALLBACK,
            },
        }
    }

    return .{
        .mode = resolveModeFromLane(root_obj.get("laneModes"), default_mode),
        .strict_no_fallback = strict_no_fallback,
    };
}

fn activeSymbolOwnershipConfig() []const dropin_symbol_ownership.SymbolOwnership {
    if (g_symbol_ownership_ready.load(.acquire) != 0) {
        return g_symbol_ownership_config;
    }

    g_symbol_ownership_lock.lock();
    defer g_symbol_ownership_lock.unlock();

    if (g_symbol_ownership_ready.load(.acquire) != 0) {
        return g_symbol_ownership_config;
    }

    g_symbol_ownership_config = dropin_symbol_ownership.parse_symbol_ownership_config(
        std.heap.page_allocator,
        DROPIN_SYMBOL_OWNERSHIP_CONFIG_JSON,
    ) catch &.{};
    g_symbol_ownership_ready.store(1, .release);
    return g_symbol_ownership_config;
}

fn symbolOwnerForName(symbol: []const u8) dropin_symbol_ownership.SymbolOwner {
    if (dropin_symbol_ownership.find_symbol_ownership(activeSymbolOwnershipConfig(), symbol)) |entry| {
        return entry.owner;
    }
    return .shared;
}

fn symbolRequiredInStrict(symbol: []const u8) bool {
    if (dropin_symbol_ownership.find_symbol_ownership(activeSymbolOwnershipConfig(), symbol)) |entry| {
        return entry.required_in_strict;
    }
    return false;
}

fn symbolRouteForName(symbol: []const u8) dropin_router.RouteDecision {
    const strict_no_fallback = activeStrictNoFallback() and symbolRequiredInStrict(symbol);
    return dropin_router.decide_symbol_route(
        symbolOwnerForName(symbol),
        activeBehaviorMode(),
        strict_no_fallback,
    );
}

fn symbolNameSlice(name: types.WGPUStringView) ?[]const u8 {
    const data = name.data orelse return null;
    if (name.length == types.WGPU_STRLEN) {
        const z = @as([*:0]const u8, @ptrCast(data));
        return std.mem.sliceTo(z, 0);
    }
    if (name.length == 0) return null;
    return data[0..name.length];
}

fn symbolRouteForView(name: types.WGPUStringView) dropin_router.RouteDecision {
    if (symbolNameSlice(name)) |symbol| {
        return symbolRouteForName(symbol);
    }
    return dropin_router.decide_symbol_route(
        .shared,
        activeBehaviorMode(),
        false,
    );
}

fn parseModeValue(raw_mode: ?std.json.Value) ?dropin_behavior_policy.BehaviorMode {
    if (raw_mode == null) return null;
    return switch (raw_mode.?) {
        .string => |value| dropin_behavior_policy.parse_behavior_mode(value),
        else => null,
    };
}

fn resolveModeFromLane(
    raw_lane_modes: ?std.json.Value,
    fallback: dropin_behavior_policy.BehaviorMode,
) dropin_behavior_policy.BehaviorMode {
    const lane_modes = raw_lane_modes orelse return fallback;
    if (lane_modes != .object) return fallback;

    const lane_value = std.process.getEnvVarOwned(std.heap.page_allocator, "FAWN_BACKEND_LANE") catch |err| {
        if (err == error.EnvironmentVariableNotFound) return fallback;
        return fallback;
    };
    defer std.heap.page_allocator.free(lane_value);

    const lane = backend_policy.parse_lane(lane_value) orelse return fallback;
    const lane_modes_obj = lane_modes.object;
    const lane_key = backend_policy.lane_name(lane);

    const lane_mode = lane_modes_obj.get(lane_key) orelse return fallback;
    return parseModeValue(lane_mode) orelse fallback;
}

pub const DropinErrorCode = enum(u32) {
    ok = 0,
    library_open_failed = 1,
    symbol_missing = 2,
    invalid_symbol_name = 3,
    symbol_name_too_long = 4,
};

var g_state_lock: std.Thread.Mutex = .{};
var g_native_lib: ?std.DynLib = null;
var g_library_ready: bool = false;
var g_library_failed: bool = false;
var g_last_error_code = std.atomic.Value(u32).init(@intFromEnum(DropinErrorCode.ok));
var g_symbol_ownership_config: []const dropin_symbol_ownership.SymbolOwnership = &.{};
var g_symbol_ownership_ready: std.atomic.Value(u8) = .init(0);
var g_symbol_ownership_lock: std.Thread.Mutex = .{};
const WgpuAnyProc = *const fn () callconv(.c) void;

fn setLastError(code: DropinErrorCode) void {
    g_last_error_code.store(@intFromEnum(code), .monotonic);
}

pub export fn doeWgpuDropinLastErrorCode() callconv(.c) u32 {
    return g_last_error_code.load(.monotonic);
}

pub export fn doeWgpuDropinClearLastError() callconv(.c) void {
    setLastError(.ok);
}

fn ensureNativeLibraryLocked() bool {
    if (g_library_ready) return !g_library_failed;
    g_library_ready = true;
    g_native_lib = loader.openLibrary() catch {
        g_library_failed = true;
        setLastError(.library_open_failed);
        return false;
    };
    g_library_failed = false;
    return true;
}

fn ensureNativeLibrary() bool {
    g_state_lock.lock();
    defer g_state_lock.unlock();
    return ensureNativeLibraryLocked();
}

fn unsupportedProc() callconv(.c) usize {
    setLastError(.symbol_missing);
    return 0;
}

pub export fn doeWgpuDropinUnsupportedProc() callconv(.c) usize {
    return unsupportedProc();
}

fn unsupportedSymbol(comptime symbol_name: []const u8, comptime FnType: type) FnType {
    return @as(FnType, @ptrCast(&unsupportedProc));
}

fn routeAndRecordForName(
    symbol_name: []const u8,
    route: dropin_router.RouteDecision,
    resolved: bool,
) void {
    dropin_diagnostics.record(
        symbol_name,
        dropin_symbol_ownership.symbol_owner_name(route.owner),
        resolved,
        route.fallback_used,
    );
}

fn nativeFromSymbol(comptime FnType: type, comptime symbol_name: [:0]const u8) ?FnType {
    return loadOptionalProc(FnType, symbol_name);
}

fn loadRequiredProc(comptime FnType: type, comptime symbol_name: [:0]const u8) FnType {
    const Cache = struct {
        const symbol_key = symbol_name;
        var initialized = std.atomic.Value(u8).init(0);
        var proc: ?FnType = null;
    };
    _ = Cache.symbol_key;

    if (Cache.initialized.load(.acquire) != 0) {
        return Cache.proc.?;
    }

    g_state_lock.lock();
    defer g_state_lock.unlock();

    if (Cache.initialized.load(.monotonic) != 0) {
        return Cache.proc.?;
    }
    const route = symbolRouteForName(symbol_name);
    if (!ensureNativeLibraryLocked()) {
        routeAndRecordForName(symbol_name, route, false);
        return unsupportedSymbol(symbol_name, FnType);
    }

    const resolved = switch (route.owner) {
        .dawn_oracle, .shared => nativeFromSymbol(FnType, symbol_name),
        .zig_metal, .zig_vulkan => if (route.fallback_used) nativeFromSymbol(FnType, symbol_name) else null,
    };

    routeAndRecordForName(symbol_name, route, resolved != null);
    if (resolved) |proc| {
        Cache.proc = proc;
        Cache.initialized.store(1, .release);
        setLastError(.ok);
        return proc;
    }
    const proc = unsupportedSymbol(symbol_name, FnType);
    Cache.proc = proc;
    Cache.initialized.store(1, .release);
    return proc;
}

fn loadOptionalProc(comptime FnType: type, comptime symbol_name: [:0]const u8) ?FnType {
    const Cache = struct {
        const symbol_key = symbol_name;
        var initialized = std.atomic.Value(u8).init(0);
        var proc: ?FnType = null;
    };
    _ = Cache.symbol_key;

    if (Cache.initialized.load(.acquire) != 0) {
        return Cache.proc;
    }

    g_state_lock.lock();
    defer g_state_lock.unlock();

    if (Cache.initialized.load(.monotonic) != 0) {
        return Cache.proc;
    }

    if (!ensureNativeLibraryLocked()) return null;
    var lib = g_native_lib.?;
    Cache.proc = lib.lookup(FnType, symbol_name);
    Cache.initialized.store(1, .release);
    return Cache.proc;
}

fn fnPtr(value: anytype) p1_capability_procs.WGPUProc {
    return @as(p1_capability_procs.WGPUProc, @ptrCast(value));
}

fn symbolViewEq(name: types.WGPUStringView, comptime expected: []const u8) bool {
    const data = name.data orelse return false;
    if (name.length == types.WGPU_STRLEN) {
        const z = @as([*:0]const u8, @ptrCast(data));
        return std.mem.eql(u8, std.mem.span(z), expected);
    }
    if (name.length != expected.len) return false;
    return std.mem.eql(u8, data[0..name.length], expected);
}

fn toZeroTerminatedSymbolName(
    name: types.WGPUStringView,
    buffer: *[256]u8,
) ?[:0]const u8 {
    const data = name.data orelse {
        setLastError(.invalid_symbol_name);
        return null;
    };

    if (name.length == types.WGPU_STRLEN) {
        const z = @as([*:0]const u8, @ptrCast(data));
        return std.mem.span(z);
    }

    if (name.length == 0) {
        setLastError(.invalid_symbol_name);
        return null;
    }

    if (name.length >= buffer.len) {
        setLastError(.symbol_name_too_long);
        return null;
    }

    @memcpy(buffer[0..name.length], data[0..name.length]);
    buffer[name.length] = 0;
    return buffer[0..name.length :0];
}

fn resolveLocalProc(name: types.WGPUStringView) p1_capability_procs.WGPUProc {
    if (symbolViewEq(name, "wgpuGetProcAddress")) return fnPtr(&wgpuGetProcAddress);
    if (symbolViewEq(name, "wgpuCreateInstance")) return fnPtr(&wgpuCreateInstance);
    if (symbolViewEq(name, "wgpuInstanceRequestAdapter")) return fnPtr(&wgpuInstanceRequestAdapter);
    if (symbolViewEq(name, "wgpuInstanceWaitAny")) return fnPtr(&wgpuInstanceWaitAny);
    if (symbolViewEq(name, "wgpuInstanceProcessEvents")) return fnPtr(&wgpuInstanceProcessEvents);
    if (symbolViewEq(name, "wgpuAdapterRequestDevice")) return fnPtr(&wgpuAdapterRequestDevice);
    if (symbolViewEq(name, "wgpuDeviceCreateBuffer")) return fnPtr(&wgpuDeviceCreateBuffer);
    if (symbolViewEq(name, "wgpuDeviceCreateShaderModule")) return fnPtr(&wgpuDeviceCreateShaderModule);
    if (symbolViewEq(name, "wgpuShaderModuleRelease")) return fnPtr(&wgpuShaderModuleRelease);
    if (symbolViewEq(name, "wgpuDeviceCreateComputePipeline")) return fnPtr(&wgpuDeviceCreateComputePipeline);
    if (symbolViewEq(name, "wgpuComputePipelineRelease")) return fnPtr(&wgpuComputePipelineRelease);
    if (symbolViewEq(name, "wgpuRenderPipelineRelease")) return fnPtr(&wgpuRenderPipelineRelease);
    if (symbolViewEq(name, "wgpuDeviceCreateCommandEncoder")) return fnPtr(&wgpuDeviceCreateCommandEncoder);
    if (symbolViewEq(name, "wgpuCommandEncoderBeginComputePass")) return fnPtr(&wgpuCommandEncoderBeginComputePass);
    if (symbolViewEq(name, "wgpuDeviceCreateRenderPipeline")) return fnPtr(&wgpuDeviceCreateRenderPipeline);
    if (symbolViewEq(name, "wgpuCommandEncoderBeginRenderPass")) return fnPtr(&wgpuCommandEncoderBeginRenderPass);
    if (symbolViewEq(name, "wgpuCommandEncoderWriteTimestamp")) return fnPtr(&wgpuCommandEncoderWriteTimestamp);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyBufferToBuffer")) return fnPtr(&wgpuCommandEncoderCopyBufferToBuffer);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyBufferToTexture")) return fnPtr(&wgpuCommandEncoderCopyBufferToTexture);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyTextureToBuffer")) return fnPtr(&wgpuCommandEncoderCopyTextureToBuffer);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyTextureToTexture")) return fnPtr(&wgpuCommandEncoderCopyTextureToTexture);
    if (symbolViewEq(name, "wgpuComputePassEncoderSetPipeline")) return fnPtr(&wgpuComputePassEncoderSetPipeline);
    if (symbolViewEq(name, "wgpuComputePassEncoderSetBindGroup")) return fnPtr(&wgpuComputePassEncoderSetBindGroup);
    if (symbolViewEq(name, "wgpuComputePassEncoderDispatchWorkgroups")) return fnPtr(&wgpuComputePassEncoderDispatchWorkgroups);
    if (symbolViewEq(name, "wgpuComputePassEncoderEnd")) return fnPtr(&wgpuComputePassEncoderEnd);
    if (symbolViewEq(name, "wgpuComputePassEncoderRelease")) return fnPtr(&wgpuComputePassEncoderRelease);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetPipeline")) return fnPtr(&wgpuRenderPassEncoderSetPipeline);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetVertexBuffer")) return fnPtr(&wgpuRenderPassEncoderSetVertexBuffer);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetIndexBuffer")) return fnPtr(&wgpuRenderPassEncoderSetIndexBuffer);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetBindGroup")) return fnPtr(&wgpuRenderPassEncoderSetBindGroup);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDraw")) return fnPtr(&wgpuRenderPassEncoderDraw);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDrawIndexed")) return fnPtr(&wgpuRenderPassEncoderDrawIndexed);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDrawIndirect")) return fnPtr(&wgpuRenderPassEncoderDrawIndirect);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDrawIndexedIndirect")) return fnPtr(&wgpuRenderPassEncoderDrawIndexedIndirect);
    if (symbolViewEq(name, "wgpuRenderPassEncoderEnd")) return fnPtr(&wgpuRenderPassEncoderEnd);
    if (symbolViewEq(name, "wgpuRenderPassEncoderRelease")) return fnPtr(&wgpuRenderPassEncoderRelease);
    if (symbolViewEq(name, "wgpuCommandEncoderFinish")) return fnPtr(&wgpuCommandEncoderFinish);
    if (symbolViewEq(name, "wgpuDeviceGetQueue")) return fnPtr(&wgpuDeviceGetQueue);
    if (symbolViewEq(name, "wgpuQueueSubmit")) return fnPtr(&wgpuQueueSubmit);
    if (symbolViewEq(name, "wgpuQueueOnSubmittedWorkDone")) return fnPtr(&wgpuQueueOnSubmittedWorkDone);
    if (symbolViewEq(name, "wgpuQueueWriteBuffer")) return fnPtr(&wgpuQueueWriteBuffer);
    if (symbolViewEq(name, "wgpuDeviceCreateTexture")) return fnPtr(&wgpuDeviceCreateTexture);
    if (symbolViewEq(name, "wgpuTextureCreateView")) return fnPtr(&wgpuTextureCreateView);
    if (symbolViewEq(name, "wgpuDeviceCreateBindGroupLayout")) return fnPtr(&wgpuDeviceCreateBindGroupLayout);
    if (symbolViewEq(name, "wgpuBindGroupLayoutRelease")) return fnPtr(&wgpuBindGroupLayoutRelease);
    if (symbolViewEq(name, "wgpuDeviceCreateBindGroup")) return fnPtr(&wgpuDeviceCreateBindGroup);
    if (symbolViewEq(name, "wgpuBindGroupRelease")) return fnPtr(&wgpuBindGroupRelease);
    if (symbolViewEq(name, "wgpuDeviceCreatePipelineLayout")) return fnPtr(&wgpuDeviceCreatePipelineLayout);
    if (symbolViewEq(name, "wgpuPipelineLayoutRelease")) return fnPtr(&wgpuPipelineLayoutRelease);
    if (symbolViewEq(name, "wgpuTextureRelease")) return fnPtr(&wgpuTextureRelease);
    if (symbolViewEq(name, "wgpuTextureViewRelease")) return fnPtr(&wgpuTextureViewRelease);
    if (symbolViewEq(name, "wgpuInstanceRelease")) return fnPtr(&wgpuInstanceRelease);
    if (symbolViewEq(name, "wgpuAdapterRelease")) return fnPtr(&wgpuAdapterRelease);
    if (symbolViewEq(name, "wgpuDeviceRelease")) return fnPtr(&wgpuDeviceRelease);
    if (symbolViewEq(name, "wgpuQueueRelease")) return fnPtr(&wgpuQueueRelease);
    if (symbolViewEq(name, "wgpuCommandEncoderRelease")) return fnPtr(&wgpuCommandEncoderRelease);
    if (symbolViewEq(name, "wgpuCommandBufferRelease")) return fnPtr(&wgpuCommandBufferRelease);
    if (symbolViewEq(name, "wgpuBufferRelease")) return fnPtr(&wgpuBufferRelease);
    if (symbolViewEq(name, "wgpuAdapterHasFeature")) return fnPtr(&wgpuAdapterHasFeature);
    if (symbolViewEq(name, "wgpuDeviceHasFeature")) return fnPtr(&wgpuDeviceHasFeature);
    if (symbolViewEq(name, "wgpuDeviceCreateQuerySet")) return fnPtr(&wgpuDeviceCreateQuerySet);
    if (symbolViewEq(name, "wgpuCommandEncoderResolveQuerySet")) return fnPtr(&wgpuCommandEncoderResolveQuerySet);
    if (symbolViewEq(name, "wgpuQuerySetRelease")) return fnPtr(&wgpuQuerySetRelease);
    if (symbolViewEq(name, "wgpuBufferMapAsync")) return fnPtr(&wgpuBufferMapAsync);
    if (symbolViewEq(name, "wgpuBufferGetConstMappedRange")) return fnPtr(&wgpuBufferGetConstMappedRange);
    if (symbolViewEq(name, "wgpuBufferUnmap")) return fnPtr(&wgpuBufferUnmap);
    return null;
}

fn resolveNativeProc(name: types.WGPUStringView) p1_capability_procs.WGPUProc {
    if (!ensureNativeLibrary()) return null;

    if (loadOptionalProc(p1_capability_procs.FnGetProcAddress, "wgpuGetProcAddress")) |native_get_proc_address| {
        const resolved = native_get_proc_address(name);
        if (resolved != null) return resolved;
    }

    var buffer: [256]u8 = undefined;
    const zname = toZeroTerminatedSymbolName(name, &buffer) orelse return null;

    g_state_lock.lock();
    defer g_state_lock.unlock();

    if (!ensureNativeLibraryLocked()) return null;
    var lib = g_native_lib.?;
    const resolved = lib.lookup(WgpuAnyProc, zname) orelse return null;
    return @as(p1_capability_procs.WGPUProc, resolved);
}

pub export fn wgpuGetProcAddress(name: types.WGPUStringView) callconv(.c) p1_capability_procs.WGPUProc {
    const route = symbolRouteForView(name);
    const symbol_name = symbolNameSlice(name) orelse {
        setLastError(.invalid_symbol_name);
        return null;
    };

    if (route.owner == .zig_metal or route.owner == .zig_vulkan) {
        if (!route.fallback_used) {
            routeAndRecordForName(symbol_name, route, false);
            setLastError(.symbol_missing);
            return null;
        }
    }

    if (resolveLocalProc(name)) |proc| {
        routeAndRecordForName(symbol_name, route, route.owner == .dawn_oracle or route.owner == .shared or route.fallback_used);
        setLastError(.ok);
        return proc;
    }

    if (resolveNativeProc(name)) |proc| {
        routeAndRecordForName(symbol_name, route, true);
        setLastError(.ok);
        return proc;
    }

    routeAndRecordForName(symbol_name, route, false);
    setLastError(.symbol_missing);
    return null;
}

pub export fn wgpuCreateInstance(a0: ?*anyopaque) callconv(.c) types.WGPUInstance {
    const proc = loadRequiredProc(types.FnWgpuCreateInstance, "wgpuCreateInstance");
    return proc(a0);
}

pub export fn wgpuInstanceRequestAdapter(a0: types.WGPUInstance, a1: ?*const types.WGPURequestAdapterOptions, a2: types.WGPURequestAdapterCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = loadRequiredProc(types.FnWgpuInstanceRequestAdapter, "wgpuInstanceRequestAdapter");
    return proc(a0, a1, a2);
}

pub export fn wgpuInstanceWaitAny(a0: types.WGPUInstance, a1: usize, a2: [*]types.WGPUFutureWaitInfo, a3: u64) callconv(.c) types.WGPUWaitStatus {
    const proc = loadRequiredProc(types.FnWgpuInstanceWaitAny, "wgpuInstanceWaitAny");
    return proc(a0, a1, a2, a3);
}

pub export fn wgpuInstanceProcessEvents(a0: types.WGPUInstance) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuInstanceProcessEvents, "wgpuInstanceProcessEvents");
    proc(a0);
}

pub export fn wgpuAdapterRequestDevice(a0: types.WGPUAdapter, a1: ?*const types.WGPUDeviceDescriptor, a2: types.WGPURequestDeviceCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = loadRequiredProc(types.FnWgpuAdapterRequestDevice, "wgpuAdapterRequestDevice");
    return proc(a0, a1, a2);
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
    const proc = loadRequiredProc(types.FnWgpuShaderModuleRelease, "wgpuShaderModuleRelease");
    proc(a0);
}

pub export fn wgpuDeviceCreateComputePipeline(a0: types.WGPUDevice, a1: ?*const types.WGPUComputePipelineDescriptor) callconv(.c) types.WGPUComputePipeline {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateComputePipeline, "wgpuDeviceCreateComputePipeline");
    return proc(a0, a1);
}

pub export fn wgpuComputePipelineRelease(a0: types.WGPUComputePipeline) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuComputePipelineRelease, "wgpuComputePipelineRelease");
    proc(a0);
}

pub export fn wgpuRenderPipelineRelease(a0: types.WGPURenderPipeline) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuRenderPipelineRelease, "wgpuRenderPipelineRelease");
    proc(a0);
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
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderWriteTimestamp, "wgpuCommandEncoderWriteTimestamp");
    proc(a0, a1, a2);
}

pub export fn wgpuCommandEncoderCopyBufferToBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: types.WGPUBuffer, a4: u64, a5: u64) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderCopyBufferToBuffer, "wgpuCommandEncoderCopyBufferToBuffer");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuCommandEncoderCopyBufferToTexture(a0: types.WGPUCommandEncoder, a1: *const types.WGPUTexelCopyBufferInfo, a2: *const types.WGPUTexelCopyTextureInfo, a3: types.WGPUExtent3D) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderCopyBufferToTexture, "wgpuCommandEncoderCopyBufferToTexture");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuCommandEncoderCopyTextureToBuffer(a0: types.WGPUCommandEncoder, a1: *const types.WGPUTexelCopyTextureInfo, a2: *const types.WGPUTexelCopyBufferInfo, a3: types.WGPUExtent3D) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderCopyTextureToBuffer, "wgpuCommandEncoderCopyTextureToBuffer");
    proc(a0, a1, a2, a3);
}

pub export fn wgpuCommandEncoderCopyTextureToTexture(a0: types.WGPUCommandEncoder, a1: *const types.WGPUTexelCopyTextureInfo, a2: *const types.WGPUTexelCopyTextureInfo, a3: types.WGPUExtent3D) callconv(.c) void {
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
    const proc = loadRequiredProc(types.FnWgpuComputePassEncoderRelease, "wgpuComputePassEncoderRelease");
    proc(a0);
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
    const proc = loadRequiredProc(types.FnWgpuRenderPassEncoderRelease, "wgpuRenderPassEncoderRelease");
    proc(a0);
}

pub export fn wgpuCommandEncoderFinish(a0: types.WGPUCommandEncoder, a1: ?*const types.WGPUCommandBufferDescriptor) callconv(.c) types.WGPUCommandBuffer {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderFinish, "wgpuCommandEncoderFinish");
    return proc(a0, a1);
}

pub export fn wgpuDeviceGetQueue(a0: types.WGPUDevice) callconv(.c) types.WGPUQueue {
    const proc = loadRequiredProc(types.FnWgpuDeviceGetQueue, "wgpuDeviceGetQueue");
    return proc(a0);
}

pub export fn wgpuQueueSubmit(a0: types.WGPUQueue, a1: usize, a2: [*c]types.WGPUCommandBuffer) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuQueueSubmit, "wgpuQueueSubmit");
    proc(a0, a1, a2);
}

pub export fn wgpuQueueOnSubmittedWorkDone(a0: types.WGPUQueue, a1: types.WGPUQueueWorkDoneCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = loadRequiredProc(types.FnWgpuQueueOnSubmittedWorkDone, "wgpuQueueOnSubmittedWorkDone");
    return proc(a0, a1);
}

pub export fn wgpuQueueWriteBuffer(a0: types.WGPUQueue, a1: types.WGPUBuffer, a2: u64, a3: ?*const anyopaque, a4: usize) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuQueueWriteBuffer, "wgpuQueueWriteBuffer");
    proc(a0, a1, a2, a3, a4);
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
    const proc = loadRequiredProc(types.FnWgpuBindGroupLayoutRelease, "wgpuBindGroupLayoutRelease");
    proc(a0);
}

pub export fn wgpuDeviceCreateBindGroup(a0: types.WGPUDevice, a1: ?*const types.WGPUBindGroupDescriptor) callconv(.c) types.WGPUBindGroup {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateBindGroup, "wgpuDeviceCreateBindGroup");
    return proc(a0, a1);
}

pub export fn wgpuBindGroupRelease(a0: types.WGPUBindGroup) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuBindGroupRelease, "wgpuBindGroupRelease");
    proc(a0);
}

pub export fn wgpuDeviceCreatePipelineLayout(a0: types.WGPUDevice, a1: *const types.WGPUPipelineLayoutDescriptor) callconv(.c) types.WGPUPipelineLayout {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreatePipelineLayout, "wgpuDeviceCreatePipelineLayout");
    return proc(a0, a1);
}

pub export fn wgpuPipelineLayoutRelease(a0: types.WGPUPipelineLayout) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuPipelineLayoutRelease, "wgpuPipelineLayoutRelease");
    proc(a0);
}

pub export fn wgpuTextureRelease(a0: types.WGPUTexture) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuTextureRelease, "wgpuTextureRelease");
    proc(a0);
}

pub export fn wgpuTextureViewRelease(a0: types.WGPUTextureView) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuTextureViewRelease, "wgpuTextureViewRelease");
    proc(a0);
}

pub export fn wgpuInstanceRelease(a0: types.WGPUInstance) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuInstanceRelease, "wgpuInstanceRelease");
    proc(a0);
}

pub export fn wgpuAdapterRelease(a0: types.WGPUAdapter) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuAdapterRelease, "wgpuAdapterRelease");
    proc(a0);
}

pub export fn wgpuDeviceRelease(a0: types.WGPUDevice) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuDeviceRelease, "wgpuDeviceRelease");
    proc(a0);
}

pub export fn wgpuQueueRelease(a0: types.WGPUQueue) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuQueueRelease, "wgpuQueueRelease");
    proc(a0);
}

pub export fn wgpuCommandEncoderRelease(a0: types.WGPUCommandEncoder) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderRelease, "wgpuCommandEncoderRelease");
    proc(a0);
}

pub export fn wgpuCommandBufferRelease(a0: types.WGPUCommandBuffer) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandBufferRelease, "wgpuCommandBufferRelease");
    proc(a0);
}

pub export fn wgpuBufferRelease(a0: types.WGPUBuffer) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuBufferRelease, "wgpuBufferRelease");
    proc(a0);
}

pub export fn wgpuAdapterHasFeature(a0: types.WGPUAdapter, a1: types.WGPUFeatureName) callconv(.c) types.WGPUBool {
    const proc = loadRequiredProc(types.FnWgpuAdapterHasFeature, "wgpuAdapterHasFeature");
    return proc(a0, a1);
}

pub export fn wgpuDeviceHasFeature(a0: types.WGPUDevice, a1: types.WGPUFeatureName) callconv(.c) types.WGPUBool {
    const proc = loadRequiredProc(types.FnWgpuDeviceHasFeature, "wgpuDeviceHasFeature");
    return proc(a0, a1);
}

pub export fn wgpuDeviceCreateQuerySet(a0: types.WGPUDevice, a1: *const types.WGPUQuerySetDescriptor) callconv(.c) types.WGPUQuerySet {
    const proc = loadRequiredProc(types.FnWgpuDeviceCreateQuerySet, "wgpuDeviceCreateQuerySet");
    return proc(a0, a1);
}

pub export fn wgpuCommandEncoderResolveQuerySet(a0: types.WGPUCommandEncoder, a1: types.WGPUQuerySet, a2: u32, a3: u32, a4: types.WGPUBuffer, a5: u64) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuCommandEncoderResolveQuerySet, "wgpuCommandEncoderResolveQuerySet");
    proc(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuQuerySetRelease(a0: types.WGPUQuerySet) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuQuerySetRelease, "wgpuQuerySetRelease");
    proc(a0);
}

pub export fn wgpuBufferMapAsync(a0: types.WGPUBuffer, a1: types.WGPUMapMode, a2: usize, a3: usize, a4: types.WGPUBufferMapCallbackInfo) callconv(.c) types.WGPUFuture {
    const proc = loadRequiredProc(types.FnWgpuBufferMapAsync, "wgpuBufferMapAsync");
    return proc(a0, a1, a2, a3, a4);
}

pub export fn wgpuBufferGetConstMappedRange(a0: types.WGPUBuffer, a1: usize, a2: usize) callconv(.c) ?*const anyopaque {
    const proc = loadRequiredProc(types.FnWgpuBufferGetConstMappedRange, "wgpuBufferGetConstMappedRange");
    return proc(a0, a1, a2);
}

pub export fn wgpuBufferUnmap(a0: types.WGPUBuffer) callconv(.c) void {
    const proc = loadRequiredProc(types.FnWgpuBufferUnmap, "wgpuBufferUnmap");
    proc(a0);
}
