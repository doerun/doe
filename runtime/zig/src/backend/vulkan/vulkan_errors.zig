// Vulkan VkResult error mapping and diagnostic name lookup.

const common_errors = @import("../common/errors.zig");

pub const VulkanError = error{
    OutOfHostMemory,
    OutOfDeviceMemory,
    InitializationFailed,
    DeviceLost,
    MemoryMapFailed,
    LayerNotPresent,
    ExtensionNotPresent,
    FeatureNotPresent,
    TooManyObjects,
    FormatNotSupported,
    SurfaceLost,
};

/// Map a raw VkResult (i32) to a Zig error on failure, or return void on
/// VK_SUCCESS. Unknown negative codes conservatively map to DeviceLost.
pub fn mapVkResult(result: i32) VulkanError!void {
    if (result == 0) return; // VK_SUCCESS
    return switch (result) {
        -1 => error.OutOfHostMemory,
        -2 => error.OutOfDeviceMemory,
        -3 => error.InitializationFailed,
        -4 => error.DeviceLost,
        -5 => error.MemoryMapFailed,
        -6 => error.LayerNotPresent,
        -7 => error.ExtensionNotPresent,
        -8 => error.FeatureNotPresent,
        -9 => error.TooManyObjects,
        -10 => error.FormatNotSupported,
        -1000000000 => error.SurfaceLost,
        else => error.DeviceLost,
    };
}

/// Return a human-readable name for common VkResult codes. Useful for
/// structured log output without pulling in the full Vulkan header names.
pub fn vulkanResultName(result: i32) []const u8 {
    return switch (result) {
        0 => "VK_SUCCESS",
        1 => "VK_NOT_READY",
        2 => "VK_TIMEOUT",
        3 => "VK_EVENT_SET",
        4 => "VK_EVENT_RESET",
        5 => "VK_INCOMPLETE",
        -1 => "VK_ERROR_OUT_OF_HOST_MEMORY",
        -2 => "VK_ERROR_OUT_OF_DEVICE_MEMORY",
        -3 => "VK_ERROR_INITIALIZATION_FAILED",
        -4 => "VK_ERROR_DEVICE_LOST",
        -5 => "VK_ERROR_MEMORY_MAP_FAILED",
        -6 => "VK_ERROR_LAYER_NOT_PRESENT",
        -7 => "VK_ERROR_EXTENSION_NOT_PRESENT",
        -8 => "VK_ERROR_FEATURE_NOT_PRESENT",
        -9 => "VK_ERROR_TOO_MANY_OBJECTS",
        -10 => "VK_ERROR_FORMAT_NOT_SUPPORTED",
        -1000000000 => "VK_ERROR_SURFACE_LOST_KHR",
        else => "VK_UNKNOWN",
    };
}
