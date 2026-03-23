// wgpu_type_callbacks.zig — Callback types, status enums, and callback info structs.
// Sharded from wgpu_types.zig to keep file size under limit.
// Uses comptime parent type pattern to reference handle/string types without circular imports.
pub fn definitions(comptime parent: type) type {
    return struct {
        pub const WGPUCallbackMode = u32;
        pub const WGPUCallbackMode_WaitAnyOnly: WGPUCallbackMode = 0x00000001;
        pub const WGPUCallbackMode_AllowProcessEvents: WGPUCallbackMode = 0x00000002;
        pub const WGPUCallbackMode_AllowSpontaneous: WGPUCallbackMode = 0x00000003;
        pub const WGPUWaitStatus = enum(u32) {
            success = 1,
            timedOut = 2,
            @"error" = 3,
            _,
        };
        pub const WGPURequestAdapterStatus = enum(u32) {
            success = 1,
            callbackCancelled = 2,
            unavailable = 3,
            @"error" = 4,
            _,
        };
        pub const WGPURequestDeviceStatus = enum(u32) {
            success = 1,
            callbackCancelled = 2,
            @"error" = 3,
            _,
        };
        pub const WGPUQueueWorkDoneStatus = enum(u32) {
            success = 1,
            callbackCancelled = 2,
            @"error" = 3,
            _,
        };
        pub const WGPUPowerPreference = enum(u32) { undefined = 0, lowPower = 1, highPerformance = 2, _ };
        pub const WGPUFeatureLevel = enum(u32) { undefined = 0, compatibility = 1, core = 2, _ };
        pub const WGPUBackendType = enum(u32) {
            undefined = 0,
            nullBackend = 1,
            webgpu = 2,
            d3d11 = 3,
            d3d12 = 4,
            metal = 5,
            vulkan = 6,
            openGl = 7,
            openGLES = 8,
            _,
        };
        pub const WGPURequestAdapterCallback = *const fn (
            status: WGPURequestAdapterStatus,
            adapter: parent.WGPUAdapter,
            message: parent.WGPUStringView,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        ) callconv(.c) void;
        pub const WGPURequestDeviceCallback = *const fn (
            status: WGPURequestDeviceStatus,
            device: parent.WGPUDevice,
            message: parent.WGPUStringView,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        ) callconv(.c) void;
        pub const WGPUQueueWorkDoneCallback = *const fn (
            status: WGPUQueueWorkDoneStatus,
            message: parent.WGPUStringView,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        ) callconv(.c) void;
        pub const WGPUDeviceLostReason = enum(u32) {
            unknown = 1,
            destroyed = 2,
            callbackCancelled = 3,
            failedCreation = 4,
            _,
        };
        pub const WGPUErrorType = enum(u32) {
            noError = 1,
            validation = 2,
            outOfMemory = 3,
            internal = 4,
            unknown = 5,
            _,
        };
        pub const WGPUDeviceLostCallback = *const fn (
            device: ?*const anyopaque,
            reason: WGPUDeviceLostReason,
            message: parent.WGPUStringView,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        ) callconv(.c) void;
        pub const WGPUUncapturedErrorCallback = *const fn (
            device: ?*const anyopaque,
            @"type": WGPUErrorType,
            message: parent.WGPUStringView,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        ) callconv(.c) void;
        pub const WGPURequestAdapterCallbackInfo = extern struct {
            nextInChain: ?*anyopaque,
            mode: WGPUCallbackMode,
            callback: ?WGPURequestAdapterCallback,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        };
        pub const WGPURequestDeviceCallbackInfo = extern struct {
            nextInChain: ?*anyopaque,
            mode: WGPUCallbackMode,
            callback: ?WGPURequestDeviceCallback,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        };
        pub const WGPUQueueWorkDoneCallbackInfo = extern struct {
            nextInChain: ?*anyopaque,
            mode: WGPUCallbackMode,
            callback: ?WGPUQueueWorkDoneCallback,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        };
        pub const WGPUDeviceLostCallbackInfo = extern struct {
            nextInChain: ?*anyopaque,
            mode: WGPUCallbackMode,
            callback: ?WGPUDeviceLostCallback,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        };
        pub const WGPUUncapturedErrorCallbackInfo = extern struct {
            nextInChain: ?*anyopaque,
            callback: ?WGPUUncapturedErrorCallback,
            userdata1: ?*anyopaque,
            userdata2: ?*anyopaque,
        };
    };
}
