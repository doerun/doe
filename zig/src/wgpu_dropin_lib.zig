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
const dropin_abi_procs = @import("dropin/dropin_abi_procs.zig");
const dropin_build_info = @import("dropin/dropin_build_info.zig");

const build_options = @import("build_options");
const DROPIN_BEHAVIOR_CONFIG_JSON = build_options.dropin_behavior_config_json;
const DROPIN_SYMBOL_OWNERSHIP_CONFIG_JSON = build_options.dropin_symbol_ownership_config_json;
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
    _ = dropin_build_info;
    // Native Metal backend — exports doeNative* C ABI symbols on macOS.
    if (@import("builtin").os.tag == .macos) {
        _ = @import("doe_wgpu_native.zig");
    }
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

    const root = parsed.value;
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

    if (strict_no_fallback) {
        validateModeStrings(root_obj);
    }

    return .{
        .mode = resolveModeFromLane(root_obj.get("laneModes"), default_mode),
        .strict_no_fallback = strict_no_fallback,
    };
}

fn validateModeStrings(root_obj: std.json.ObjectMap) void {
    if (root_obj.get("defaultMode")) |raw| {
        if (raw == .string and dropin_behavior_policy.parse_behavior_mode(raw.string) == null) {
            @panic("dropin-abi-behavior.json: unrecognized defaultMode value — update BehaviorMode in dropin_behavior_policy.zig");
        }
    }
    const lane_modes = root_obj.get("laneModes") orelse return;
    if (lane_modes != .object) return;
    var iter = lane_modes.object.iterator();
    while (iter.next()) |kv| {
        if (kv.value_ptr.* == .string and dropin_behavior_policy.parse_behavior_mode(kv.value_ptr.string) == null) {
            @panic("dropin-abi-behavior.json: unrecognized laneModes value — update BehaviorMode in dropin_behavior_policy.zig");
        }
    }
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

fn symbolRouteForName(symbol: []const u8) dropin_router.RouteDecision {
    const strict_no_fallback = activeStrictNoFallback();
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

fn abortMissingRequiredSymbol(symbol_name: []const u8) noreturn {
    setLastError(.symbol_missing);
    std.debug.panic("missing required WebGPU symbol: {s}", .{symbol_name});
}

pub export fn doeWgpuDropinAbortMissingRequiredSymbol(name: types.WGPUStringView) callconv(.c) noreturn {
    const symbol_name = symbolNameSlice(name) orelse {
        setLastError(.invalid_symbol_name);
        std.debug.panic("missing required WebGPU symbol: <invalid>", .{});
    };
    abortMissingRequiredSymbol(symbol_name);
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
    // Direct lookup without re-acquiring g_state_lock (caller already holds it).
    if (g_native_lib == null) return null;
    var lib = g_native_lib.?;
    return lib.lookup(FnType, symbol_name);
}

/// Resolve a standard wgpu* symbol to the corresponding doeNative* implementation.
/// Returns null for symbols not yet implemented natively.
fn resolveDoeNativeProc(comptime FnType: type, comptime symbol_name: [:0]const u8) ?FnType {
    if (comptime @import("builtin").os.tag != .macos) return null;
    const N = @import("doe_wgpu_native.zig");
    // Instance / Adapter / Device lifecycle
    if (comptime std.mem.eql(u8, symbol_name, "wgpuCreateInstance")) return @ptrCast(&N.doeNativeCreateInstance);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuInstanceRelease")) return @ptrCast(&N.doeNativeInstanceRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuInstanceWaitAny")) return @ptrCast(&N.doeNativeInstanceWaitAny);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuInstanceProcessEvents")) return @ptrCast(&N.doeNativeInstanceProcessEvents);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuInstanceRequestAdapter")) return @ptrCast(&N.doeNativeInstanceRequestAdapter);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuAdapterRequestDevice")) return @ptrCast(&N.doeNativeAdapterRequestDevice);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuAdapterRelease")) return @ptrCast(&N.doeNativeAdapterRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceRelease")) return @ptrCast(&N.doeNativeDeviceRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceGetQueue")) return @ptrCast(&N.doeNativeDeviceGetQueue);
    // Buffer
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateBuffer")) return @ptrCast(&N.doeNativeDeviceCreateBuffer);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuBufferRelease")) return @ptrCast(&N.doeNativeBufferRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuBufferUnmap")) return @ptrCast(&N.doeNativeBufferUnmap);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuBufferMapAsync")) return @ptrCast(&N.doeNativeBufferMapAsync);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuBufferGetConstMappedRange")) return @ptrCast(&N.doeNativeBufferGetConstMappedRange);
    // Shader / Compute Pipeline
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateShaderModule")) return @ptrCast(&N.doeNativeDeviceCreateShaderModule);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuShaderModuleRelease")) return @ptrCast(&N.doeNativeShaderModuleRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateComputePipeline")) return @ptrCast(&N.doeNativeDeviceCreateComputePipeline);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuComputePipelineRelease")) return @ptrCast(&N.doeNativeComputePipelineRelease);
    // Bind Group / Pipeline Layout
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateBindGroupLayout")) return @ptrCast(&N.doeNativeDeviceCreateBindGroupLayout);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuBindGroupLayoutRelease")) return @ptrCast(&N.doeNativeBindGroupLayoutRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateBindGroup")) return @ptrCast(&N.doeNativeDeviceCreateBindGroup);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuBindGroupRelease")) return @ptrCast(&N.doeNativeBindGroupRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreatePipelineLayout")) return @ptrCast(&N.doeNativeDeviceCreatePipelineLayout);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuPipelineLayoutRelease")) return @ptrCast(&N.doeNativePipelineLayoutRelease);
    // Command Encoder / Compute Pass
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateCommandEncoder")) return @ptrCast(&N.doeNativeDeviceCreateCommandEncoder);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuCommandEncoderRelease")) return @ptrCast(&N.doeNativeCommandEncoderRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuCommandEncoderBeginComputePass")) return @ptrCast(&N.doeNativeCommandEncoderBeginComputePass);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuComputePassEncoderSetPipeline")) return @ptrCast(&N.doeNativeComputePassSetPipeline);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuComputePassEncoderSetBindGroup")) return @ptrCast(&N.doeNativeComputePassSetBindGroup);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuComputePassEncoderDispatchWorkgroups")) return @ptrCast(&N.doeNativeComputePassDispatch);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuComputePassEncoderEnd")) return @ptrCast(&N.doeNativeComputePassEnd);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuComputePassEncoderRelease")) return @ptrCast(&N.doeNativeComputePassRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuCommandEncoderCopyBufferToBuffer")) return @ptrCast(&N.doeNativeCopyBufferToBuffer);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuCommandEncoderFinish")) return @ptrCast(&N.doeNativeCommandEncoderFinish);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuCommandBufferRelease")) return @ptrCast(&N.doeNativeCommandBufferRelease);
    // Queue
    if (comptime std.mem.eql(u8, symbol_name, "wgpuQueueSubmit")) return @ptrCast(&N.doeNativeQueueSubmit);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuQueueWriteBuffer")) return @ptrCast(&N.doeNativeQueueWriteBuffer);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuQueueRelease")) return @ptrCast(&N.doeNativeQueueRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuQueueOnSubmittedWorkDone")) return @ptrCast(&N.doeNativeQueueOnSubmittedWorkDone);
    // Feature queries
    if (comptime std.mem.eql(u8, symbol_name, "wgpuAdapterHasFeature")) return @ptrCast(&N.doeNativeAdapterHasFeature);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceHasFeature")) return @ptrCast(&N.doeNativeDeviceHasFeature);
    // Limits
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceGetLimits")) return @ptrCast(&N.doeNativeDeviceGetLimits);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuAdapterGetLimits")) return @ptrCast(&N.doeNativeAdapterGetLimits);
    // Texture / Render (v0.2)
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateTexture")) return @ptrCast(&N.doeNativeDeviceCreateTexture);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuTextureCreateView")) return @ptrCast(&N.doeNativeTextureCreateView);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuTextureRelease")) return @ptrCast(&N.doeNativeTextureRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuTextureViewRelease")) return @ptrCast(&N.doeNativeTextureViewRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateRenderPipeline")) return @ptrCast(&N.doeNativeDeviceCreateRenderPipeline);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuRenderPipelineRelease")) return @ptrCast(&N.doeNativeRenderPipelineRelease);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuCommandEncoderBeginRenderPass")) return @ptrCast(&N.doeNativeCommandEncoderBeginRenderPass);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuRenderPassEncoderSetPipeline")) return @ptrCast(&N.doeNativeRenderPassSetPipeline);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuRenderPassEncoderDraw")) return @ptrCast(&N.doeNativeRenderPassDraw);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuRenderPassEncoderEnd")) return @ptrCast(&N.doeNativeRenderPassEnd);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuRenderPassEncoderRelease")) return @ptrCast(&N.doeNativeRenderPassRelease);
    // Sampler
    if (comptime std.mem.eql(u8, symbol_name, "wgpuDeviceCreateSampler")) return @ptrCast(&N.doeNativeDeviceCreateSampler);
    if (comptime std.mem.eql(u8, symbol_name, "wgpuSamplerRelease")) return @ptrCast(&N.doeNativeSamplerRelease);
    return null;
}

pub fn loadRequiredProc(comptime FnType: type, comptime symbol_name: [:0]const u8) FnType {
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

    // For doe_metal or shared owner, try linked native implementations first (no sidecar needed).
    if (route.owner == .doe_metal or route.owner == .shared) {
        if (resolveDoeNativeProc(FnType, symbol_name)) |proc| {
            routeAndRecordForName(symbol_name, route, true);
            Cache.proc = proc;
            Cache.initialized.store(1, .release);
            setLastError(.ok);
            return proc;
        }
    }

    if (!ensureNativeLibraryLocked()) {
        routeAndRecordForName(symbol_name, route, false);
        abortMissingRequiredSymbol(symbol_name);
    }

    const resolved = switch (route.owner) {
        .dawn_delegate, .shared => nativeFromSymbol(FnType, symbol_name),
        .doe_metal, .doe_vulkan, .doe_d3d12 => if (route.fallback_used) nativeFromSymbol(FnType, symbol_name) else null,
    };

    routeAndRecordForName(symbol_name, route, resolved != null);
    if (resolved) |proc| {
        Cache.proc = proc;
        Cache.initialized.store(1, .release);
        setLastError(.ok);
        return proc;
    }
    abortMissingRequiredSymbol(symbol_name);
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
    const P = dropin_abi_procs;
    if (symbolViewEq(name, "wgpuGetProcAddress")) return fnPtr(&wgpuGetProcAddress);
    if (symbolViewEq(name, "wgpuCreateInstance")) return fnPtr(&P.wgpuCreateInstance);
    if (symbolViewEq(name, "wgpuInstanceRequestAdapter")) return fnPtr(&P.wgpuInstanceRequestAdapter);
    if (symbolViewEq(name, "wgpuInstanceWaitAny")) return fnPtr(&P.wgpuInstanceWaitAny);
    if (symbolViewEq(name, "wgpuInstanceProcessEvents")) return fnPtr(&P.wgpuInstanceProcessEvents);
    if (symbolViewEq(name, "wgpuAdapterRequestDevice")) return fnPtr(&P.wgpuAdapterRequestDevice);
    if (symbolViewEq(name, "wgpuDeviceCreateBuffer")) return fnPtr(&P.wgpuDeviceCreateBuffer);
    if (symbolViewEq(name, "wgpuDeviceCreateShaderModule")) return fnPtr(&P.wgpuDeviceCreateShaderModule);
    if (symbolViewEq(name, "wgpuShaderModuleRelease")) return fnPtr(&P.wgpuShaderModuleRelease);
    if (symbolViewEq(name, "wgpuDeviceCreateComputePipeline")) return fnPtr(&P.wgpuDeviceCreateComputePipeline);
    if (symbolViewEq(name, "wgpuComputePipelineRelease")) return fnPtr(&P.wgpuComputePipelineRelease);
    if (symbolViewEq(name, "wgpuRenderPipelineRelease")) return fnPtr(&P.wgpuRenderPipelineRelease);
    if (symbolViewEq(name, "wgpuDeviceCreateCommandEncoder")) return fnPtr(&P.wgpuDeviceCreateCommandEncoder);
    if (symbolViewEq(name, "wgpuCommandEncoderBeginComputePass")) return fnPtr(&P.wgpuCommandEncoderBeginComputePass);
    if (symbolViewEq(name, "wgpuDeviceCreateRenderPipeline")) return fnPtr(&P.wgpuDeviceCreateRenderPipeline);
    if (symbolViewEq(name, "wgpuCommandEncoderBeginRenderPass")) return fnPtr(&P.wgpuCommandEncoderBeginRenderPass);
    if (symbolViewEq(name, "wgpuCommandEncoderWriteTimestamp")) return fnPtr(&P.wgpuCommandEncoderWriteTimestamp);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyBufferToBuffer")) return fnPtr(&P.wgpuCommandEncoderCopyBufferToBuffer);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyBufferToTexture")) return fnPtr(&P.wgpuCommandEncoderCopyBufferToTexture);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyTextureToBuffer")) return fnPtr(&P.wgpuCommandEncoderCopyTextureToBuffer);
    if (symbolViewEq(name, "wgpuCommandEncoderCopyTextureToTexture")) return fnPtr(&P.wgpuCommandEncoderCopyTextureToTexture);
    if (symbolViewEq(name, "wgpuComputePassEncoderSetPipeline")) return fnPtr(&P.wgpuComputePassEncoderSetPipeline);
    if (symbolViewEq(name, "wgpuComputePassEncoderSetBindGroup")) return fnPtr(&P.wgpuComputePassEncoderSetBindGroup);
    if (symbolViewEq(name, "wgpuComputePassEncoderDispatchWorkgroups")) return fnPtr(&P.wgpuComputePassEncoderDispatchWorkgroups);
    if (symbolViewEq(name, "wgpuComputePassEncoderEnd")) return fnPtr(&P.wgpuComputePassEncoderEnd);
    if (symbolViewEq(name, "wgpuComputePassEncoderRelease")) return fnPtr(&P.wgpuComputePassEncoderRelease);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetPipeline")) return fnPtr(&P.wgpuRenderPassEncoderSetPipeline);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetVertexBuffer")) return fnPtr(&P.wgpuRenderPassEncoderSetVertexBuffer);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetIndexBuffer")) return fnPtr(&P.wgpuRenderPassEncoderSetIndexBuffer);
    if (symbolViewEq(name, "wgpuRenderPassEncoderSetBindGroup")) return fnPtr(&P.wgpuRenderPassEncoderSetBindGroup);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDraw")) return fnPtr(&P.wgpuRenderPassEncoderDraw);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDrawIndexed")) return fnPtr(&P.wgpuRenderPassEncoderDrawIndexed);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDrawIndirect")) return fnPtr(&P.wgpuRenderPassEncoderDrawIndirect);
    if (symbolViewEq(name, "wgpuRenderPassEncoderDrawIndexedIndirect")) return fnPtr(&P.wgpuRenderPassEncoderDrawIndexedIndirect);
    if (symbolViewEq(name, "wgpuRenderPassEncoderEnd")) return fnPtr(&P.wgpuRenderPassEncoderEnd);
    if (symbolViewEq(name, "wgpuRenderPassEncoderRelease")) return fnPtr(&P.wgpuRenderPassEncoderRelease);
    if (symbolViewEq(name, "wgpuCommandEncoderFinish")) return fnPtr(&P.wgpuCommandEncoderFinish);
    if (symbolViewEq(name, "wgpuDeviceGetQueue")) return fnPtr(&P.wgpuDeviceGetQueue);
    if (symbolViewEq(name, "wgpuQueueSubmit")) return fnPtr(&P.wgpuQueueSubmit);
    if (symbolViewEq(name, "wgpuQueueOnSubmittedWorkDone")) return fnPtr(&P.wgpuQueueOnSubmittedWorkDone);
    if (symbolViewEq(name, "wgpuQueueWriteBuffer")) return fnPtr(&P.wgpuQueueWriteBuffer);
    if (symbolViewEq(name, "wgpuDeviceCreateTexture")) return fnPtr(&P.wgpuDeviceCreateTexture);
    if (symbolViewEq(name, "wgpuTextureCreateView")) return fnPtr(&P.wgpuTextureCreateView);
    if (symbolViewEq(name, "wgpuDeviceCreateBindGroupLayout")) return fnPtr(&P.wgpuDeviceCreateBindGroupLayout);
    if (symbolViewEq(name, "wgpuBindGroupLayoutRelease")) return fnPtr(&P.wgpuBindGroupLayoutRelease);
    if (symbolViewEq(name, "wgpuDeviceCreateBindGroup")) return fnPtr(&P.wgpuDeviceCreateBindGroup);
    if (symbolViewEq(name, "wgpuBindGroupRelease")) return fnPtr(&P.wgpuBindGroupRelease);
    if (symbolViewEq(name, "wgpuDeviceCreatePipelineLayout")) return fnPtr(&P.wgpuDeviceCreatePipelineLayout);
    if (symbolViewEq(name, "wgpuPipelineLayoutRelease")) return fnPtr(&P.wgpuPipelineLayoutRelease);
    if (symbolViewEq(name, "wgpuTextureRelease")) return fnPtr(&P.wgpuTextureRelease);
    if (symbolViewEq(name, "wgpuTextureViewRelease")) return fnPtr(&P.wgpuTextureViewRelease);
    if (symbolViewEq(name, "wgpuInstanceRelease")) return fnPtr(&P.wgpuInstanceRelease);
    if (symbolViewEq(name, "wgpuAdapterRelease")) return fnPtr(&P.wgpuAdapterRelease);
    if (symbolViewEq(name, "wgpuDeviceRelease")) return fnPtr(&P.wgpuDeviceRelease);
    if (symbolViewEq(name, "wgpuQueueRelease")) return fnPtr(&P.wgpuQueueRelease);
    if (symbolViewEq(name, "wgpuCommandEncoderRelease")) return fnPtr(&P.wgpuCommandEncoderRelease);
    if (symbolViewEq(name, "wgpuCommandBufferRelease")) return fnPtr(&P.wgpuCommandBufferRelease);
    if (symbolViewEq(name, "wgpuBufferRelease")) return fnPtr(&P.wgpuBufferRelease);
    if (symbolViewEq(name, "wgpuAdapterHasFeature")) return fnPtr(&P.wgpuAdapterHasFeature);
    if (symbolViewEq(name, "wgpuDeviceHasFeature")) return fnPtr(&P.wgpuDeviceHasFeature);
    if (symbolViewEq(name, "wgpuDeviceCreateQuerySet")) return fnPtr(&P.wgpuDeviceCreateQuerySet);
    if (symbolViewEq(name, "wgpuCommandEncoderResolveQuerySet")) return fnPtr(&P.wgpuCommandEncoderResolveQuerySet);
    if (symbolViewEq(name, "wgpuQuerySetRelease")) return fnPtr(&P.wgpuQuerySetRelease);
    if (symbolViewEq(name, "wgpuBufferMapAsync")) return fnPtr(&P.wgpuBufferMapAsync);
    if (symbolViewEq(name, "wgpuBufferGetConstMappedRange")) return fnPtr(&P.wgpuBufferGetConstMappedRange);
    if (symbolViewEq(name, "wgpuBufferUnmap")) return fnPtr(&P.wgpuBufferUnmap);
    if (symbolViewEq(name, "wgpuDeviceCreateSampler")) return fnPtr(&P.wgpuDeviceCreateSampler);
    if (symbolViewEq(name, "wgpuSamplerRelease")) return fnPtr(&P.wgpuSamplerRelease);
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

    // doe_metal proceeds to resolveLocalProc (which delegates to loadRequiredProc → resolveDoeNativeProc).
    if (route.owner == .doe_vulkan or route.owner == .doe_d3d12) {
        if (!route.fallback_used) {
            routeAndRecordForName(symbol_name, route, false);
            setLastError(.symbol_missing);
            return null;
        }
    }

    if (resolveLocalProc(name)) |proc| {
        routeAndRecordForName(symbol_name, route, route.owner == .dawn_delegate or route.owner == .shared or route.fallback_used);
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

comptime {
    _ = @import("dropin/dropin_abi_procs.zig");
}
