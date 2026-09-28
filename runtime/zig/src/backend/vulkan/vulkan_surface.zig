// Native window-system surfaces, swapchain configuration, acquisition and presentation.
const std = @import("std");
const builtin = @import("builtin");
const surface_contract = @import("../../contracts/model/model_surface_control_types.zig");
const model_gpu_types = @import("../../contracts/model/model_texture_value_types.zig");
const common_errors = @import("../../contracts/execution.zig");
const vk = @import("vulkan_types.zig");
const c = @import("vk_constants.zig");
const vulkan_errors = @import("vulkan_errors.zig");
const VkResult = vk.VkResult;
const VkBool32 = vk.VkBool32;
const VkFlags = vk.VkFlags;
const VkInstance = vk.VkInstance;
const VkPhysicalDevice = vk.VkPhysicalDevice;
const VkDevice = vk.VkDevice;
const VkQueue = vk.VkQueue;
const VkAllocationCallbacks = vk.VkAllocationCallbacks;
const VkSurfaceKHR = vk.VkSurfaceKHR;
const VkSwapchainKHR = vk.VkSwapchainKHR;
const VkImage = vk.VkImage;
const VkSemaphore = vk.VkSemaphore;
const VkFence = vk.VkFence;
const VkStructureType = vk.VkStructureType;
const VK_SUCCESS = vk.VK_SUCCESS;
const VK_SUBOPTIMAL_KHR: i32 = 1000001003;
const VK_ERROR_OUT_OF_DATE_KHR = vulkan_errors.VK_ERROR_OUT_OF_DATE_KHR;
const VK_NULL_U64 = vk.VK_NULL_U64;
const VK_TRUE = vk.VK_TRUE;
const VK_FALSE = vk.VK_FALSE;
// VkStructureType values for surface/swapchain extensions
const VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR: i32 = 1000001000;
const VK_STRUCTURE_TYPE_PRESENT_INFO_KHR: i32 = 1000001001;
const VK_STRUCTURE_TYPE_WAYLAND_SURFACE_CREATE_INFO_KHR: i32 = 1000006000;
const VK_STRUCTURE_TYPE_XCB_SURFACE_CREATE_INFO_KHR: i32 = 1000005000;
const VK_STRUCTURE_TYPE_XLIB_SURFACE_CREATE_INFO_KHR: i32 = 1000004000;
// VkFormat for swapchain
const VK_FORMAT_UNDEFINED: u32 = 0;
const VK_FORMAT_B8G8R8A8_SRGB: u32 = 50;
const VK_FORMAT_B8G8R8A8_UNORM: u32 = 44;
const VK_FORMAT_R8G8B8A8_UNORM: u32 = 37;
const VK_FORMAT_R8G8B8A8_SRGB: u32 = 43;
// VkColorSpaceKHR
const VK_COLOR_SPACE_SRGB_NONLINEAR_KHR: u32 = 0;
// VkPresentModeKHR
const VK_PRESENT_MODE_FIFO_KHR: u32 = 2;
const VK_PRESENT_MODE_MAILBOX_KHR: u32 = 3;
const VK_PRESENT_MODE_IMMEDIATE_KHR: u32 = 0;
// VkCompositeAlphaFlagBitsKHR
const VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR: u32 = 0x00000001;
const VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR: u32 = 0x00000002;
const VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR: u32 = 0x00000004;
const VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR: u32 = 0x00000008;
// VkImageUsageFlagBitsKHR
const VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT: u32 = 0x00000010;
const VK_IMAGE_USAGE_SAMPLED_BIT: u32 = 0x00000004;
const VK_IMAGE_USAGE_TRANSFER_SRC_BIT: u32 = 0x00000001;
const VK_IMAGE_USAGE_TRANSFER_DST_BIT: u32 = 0x00000002;
// VkSharingMode
const VK_SHARING_MODE_EXCLUSIVE: u32 = 0;
// Limits
const DEFAULT_SURFACE_MAX_FRAME_LATENCY: u32 = 2;
const MAX_SWAPCHAIN_IMAGES: usize = 8;
const MAX_SURFACE_FORMATS: usize = 32;
const MAX_PRESENT_MODES: usize = 8;
const ACQUIRE_TIMEOUT_NS: u64 = std.math.maxInt(u64);
// Present mode mapping from WebGPU to Vulkan
const WGPU_PRESENT_MODE_FIFO: u32 = 0x00000001;
const WGPU_PRESENT_MODE_MAILBOX: u32 = 0x00000004;
const WGPU_PRESENT_MODE_IMMEDIATE: u32 = 0x00000003;
const WGPU_PRESENT_MODE_FIFO_RELAXED: u32 = 2;
const VK_PRESENT_MODE_FIFO_RELAXED_KHR: u32 = 1;
const WGPU_ALPHA_AUTO: u32 = 0;
const WGPU_ALPHA_OPAQUE: u32 = 1;
const WGPU_ALPHA_PREMULTIPLIED: u32 = 2;
const WGPU_ALPHA_UNPREMULTIPLIED: u32 = 3;
const WGPU_ALPHA_INHERIT: u32 = 4;
const VkSurfaceCapabilitiesKHR = extern struct {
    minImageCount: u32,
    maxImageCount: u32,
    currentExtent: VkExtent2D,
    minImageExtent: VkExtent2D,
    maxImageExtent: VkExtent2D,
    maxImageArrayLayers: u32,
    supportedTransforms: VkFlags,
    currentTransform: VkFlags,
    supportedCompositeAlpha: VkFlags,
    supportedUsageFlags: VkFlags,
};
const VkSurfaceFormatKHR = extern struct {
    format: u32,
    colorSpace: u32,
};
const VkExtent2D = extern struct {
    width: u32,
    height: u32,
};
const VkSwapchainCreateInfoKHR = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    surface: VkSurfaceKHR,
    minImageCount: u32,
    imageFormat: u32,
    imageColorSpace: u32,
    imageExtent: VkExtent2D,
    imageArrayLayers: u32,
    imageUsage: VkFlags,
    imageSharingMode: u32,
    queueFamilyIndexCount: u32,
    pQueueFamilyIndices: ?[*]const u32,
    preTransform: VkFlags,
    compositeAlpha: VkFlags,
    presentMode: u32,
    clipped: VkBool32,
    oldSwapchain: VkSwapchainKHR,
};
const VkPresentInfoKHR = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    waitSemaphoreCount: u32,
    pWaitSemaphores: ?[*]const VkSemaphore,
    swapchainCount: u32,
    pSwapchains: [*]const VkSwapchainKHR,
    pImageIndices: [*]const u32,
    pResults: ?[*]VkResult,
};
const VkWaylandSurfaceCreateInfoKHR = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    display: ?*anyopaque,
    surface: ?*anyopaque,
};
const VkXcbSurfaceCreateInfoKHR = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    connection: ?*anyopaque,
    window: u32,
};
const VkXlibSurfaceCreateInfoKHR = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    dpy: ?*anyopaque,
    window: u64,
};
// Vulkan KHR extension function externs (loaded from libvulkan at link time)
extern fn vkDestroySurfaceKHR(instance: VkInstance, surface: VkSurfaceKHR, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkGetPhysicalDeviceSurfaceSupportKHR(physicalDevice: VkPhysicalDevice, queueFamilyIndex: u32, surface: VkSurfaceKHR, pSupported: *VkBool32) callconv(.c) VkResult;
extern fn vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physicalDevice: VkPhysicalDevice, surface: VkSurfaceKHR, pSurfaceCapabilities: *VkSurfaceCapabilitiesKHR) callconv(.c) VkResult;
extern fn vkGetPhysicalDeviceSurfaceFormatsKHR(physicalDevice: VkPhysicalDevice, surface: VkSurfaceKHR, pSurfaceFormatCount: *u32, pSurfaceFormats: ?[*]VkSurfaceFormatKHR) callconv(.c) VkResult;
extern fn vkGetPhysicalDeviceSurfacePresentModesKHR(physicalDevice: VkPhysicalDevice, surface: VkSurfaceKHR, pPresentModeCount: *u32, pPresentModes: ?[*]u32) callconv(.c) VkResult;
extern fn vkCreateSwapchainKHR(device: VkDevice, pCreateInfo: *const VkSwapchainCreateInfoKHR, pAllocator: ?*const VkAllocationCallbacks, pSwapchain: *VkSwapchainKHR) callconv(.c) VkResult;
extern fn vkDestroySwapchainKHR(device: VkDevice, swapchain: VkSwapchainKHR, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkGetSwapchainImagesKHR(device: VkDevice, swapchain: VkSwapchainKHR, pSwapchainImageCount: *u32, pSwapchainImages: ?[*]VkImage) callconv(.c) VkResult;
extern fn vkAcquireNextImageKHR(device: VkDevice, swapchain: VkSwapchainKHR, timeout: u64, semaphore: VkSemaphore, fence: VkFence, pImageIndex: *u32) callconv(.c) VkResult;
extern fn vkQueuePresentKHR(queue: VkQueue, pPresentInfo: *const VkPresentInfoKHR) callconv(.c) VkResult;
// Platform-conditional surface creation externs (Wayland/XCB only on linux)
const is_linux = builtin.os.tag == .linux;

extern fn vkCreateWaylandSurfaceKHR(instance: VkInstance, pCreateInfo: *const VkWaylandSurfaceCreateInfoKHR, pAllocator: ?*const VkAllocationCallbacks, pSurface: *VkSurfaceKHR) callconv(.c) VkResult;
extern fn vkCreateXcbSurfaceKHR(instance: VkInstance, pCreateInfo: *const VkXcbSurfaceCreateInfoKHR, pAllocator: ?*const VkAllocationCallbacks, pSurface: *VkSurfaceKHR) callconv(.c) VkResult;
extern fn vkCreateXlibSurfaceKHR(instance: VkInstance, pCreateInfo: *const VkXlibSurfaceCreateInfoKHR, pAllocator: ?*const VkAllocationCallbacks, pSurface: *VkSurfaceKHR) callconv(.c) VkResult;
pub const SurfacePlatform = enum {
    headless,
    wayland,
    xcb,
    xlib,
};
pub const SurfaceCapabilities = struct {
    min_image_count: u32 = 0,
    max_image_count: u32 = 0,
    current_width: u32 = 0,
    current_height: u32 = 0,
    min_width: u32 = 0,
    min_height: u32 = 0,
    max_width: u32 = 0,
    max_height: u32 = 0,
    supported_usage: VkFlags = 0,
    supported_alpha: VkFlags = 0,
    current_transform: VkFlags = 0,
    format_count: u32 = 0,
    formats: [MAX_SURFACE_FORMATS]VkSurfaceFormatKHR = std.mem.zeroes([MAX_SURFACE_FORMATS]VkSurfaceFormatKHR),
    present_mode_count: u32 = 0,
    present_modes: [MAX_PRESENT_MODES]u32 = std.mem.zeroes([MAX_PRESENT_MODES]u32),
    present_supported: bool = false,
};
const surface_sync = @import("vk_surface_sync.zig");

pub const VulkanSurface = struct {
    // Vulkan surface object
    vk_surface: VkSurfaceKHR = VK_NULL_U64,
    platform: SurfacePlatform = .headless,
    // Swapchain state
    swapchain: VkSwapchainKHR = VK_NULL_U64,
    swapchain_images: [MAX_SWAPCHAIN_IMAGES]VkImage = [_]VkImage{VK_NULL_U64} ** MAX_SWAPCHAIN_IMAGES,
    swapchain_image_count: u32 = 0,
    swapchain_format: u32 = VK_FORMAT_B8G8R8A8_SRGB,
    swapchain_extent: VkExtent2D = .{ .width = 0, .height = 0 },
    // Synchronization
    completion: surface_sync.Completion = .{},
    // Configuration state (mirrors WebGPU surface semantics)
    configured: bool = false,
    acquired: bool = false,
    current_image_index: u32 = 0,
    acquired_texture_handle: u64 = 0,
    width: u32 = 0,
    height: u32 = 0,
    requested_format: model_gpu_types.WGPUTextureFormat = model_gpu_types.WGPUTextureFormat_BGRA8Unorm,
    format: model_gpu_types.WGPUTextureFormat = model_gpu_types.WGPUTextureFormat_RGBA8Unorm,
    usage: model_gpu_types.WGPUFlags = model_gpu_types.WGPUTextureUsage_RenderAttachment,
    alpha_mode: u32 = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
    present_mode: u32 = WGPU_PRESENT_MODE_FIFO,
    tone_mapping_mode: u32 = WGPU_CANVAS_TONE_MAPPING_MODE_STANDARD,
    desired_maximum_frame_latency: u32 = DEFAULT_SURFACE_MAX_FRAME_LATENCY,
    last_acquire_suboptimal: bool = false,
    last_present_suboptimal: bool = false,
    // Cached capabilities
    capabilities_queried: bool = false,
    cached_capabilities: SurfaceCapabilities = .{},
};
// -- Instance extension names required for surface creation --

pub const INSTANCE_SURFACE_EXTENSION: [*:0]const u8 = "VK_KHR_surface";
pub const INSTANCE_WAYLAND_EXTENSION: [*:0]const u8 = "VK_KHR_wayland_surface";
pub const INSTANCE_XCB_EXTENSION: [*:0]const u8 = "VK_KHR_xcb_surface";
pub const INSTANCE_XLIB_EXTENSION: [*:0]const u8 = "VK_KHR_xlib_surface";
pub const DEVICE_SWAPCHAIN_EXTENSION: [*:0]const u8 = "VK_KHR_swapchain";
pub const WGPU_CANVAS_TONE_MAPPING_MODE_STANDARD: u32 = 0x00000001;
pub const WGPU_CANVAS_TONE_MAPPING_MODE_EXTENDED: u32 = 0x00000002;
/// Returns instance extensions needed for surface support on this platform.
pub fn required_instance_extensions() []const [*:0]const u8 {
    if (!is_linux) return &[_][*:0]const u8{};
    // Both Wayland and XCB are common; request both so the runtime can
    // create surfaces for whichever compositor is active.
    return &[_][*:0]const u8{
        INSTANCE_SURFACE_EXTENSION,
        INSTANCE_WAYLAND_EXTENSION,
        INSTANCE_XCB_EXTENSION,
        INSTANCE_XLIB_EXTENSION,
    };
}
/// Returns device extensions needed for swapchain support.
pub fn required_device_extensions() []const [*:0]const u8 {
    if (!is_linux) return &[_][*:0]const u8{};
    return &[_][*:0]const u8{
        DEVICE_SWAPCHAIN_EXTENSION,
    };
}
/// Create a VkSurfaceKHR from a Wayland display+surface pair.
pub fn create_wayland_surface(
    instance: VkInstance,
    wl_display: ?*anyopaque,
    wl_surface: ?*anyopaque,
) common_errors.BackendNativeError!VkSurfaceKHR {
    if (!is_linux) return error.UnsupportedFeature;
    if (wl_display == null or wl_surface == null) return error.InvalidArgument;
    var surface: VkSurfaceKHR = VK_NULL_U64;
    const create_info = VkWaylandSurfaceCreateInfoKHR{
        .sType = VK_STRUCTURE_TYPE_WAYLAND_SURFACE_CREATE_INFO_KHR,
        .pNext = null,
        .flags = 0,
        .display = wl_display,
        .surface = wl_surface,
    };
    try check_vk(vkCreateWaylandSurfaceKHR(instance, &create_info, null, &surface));
    if (surface == VK_NULL_U64) return error.InvalidState;
    return surface;
}

/// Create a VkSurfaceKHR from an XCB connection+window pair.
pub fn create_xcb_surface(
    instance: VkInstance,
    xcb_connection: ?*anyopaque,
    xcb_window: u32,
) common_errors.BackendNativeError!VkSurfaceKHR {
    if (!is_linux) return error.UnsupportedFeature;
    if (xcb_connection == null) return error.InvalidArgument;

    var surface: VkSurfaceKHR = VK_NULL_U64;
    const create_info = VkXcbSurfaceCreateInfoKHR{
        .sType = VK_STRUCTURE_TYPE_XCB_SURFACE_CREATE_INFO_KHR,
        .pNext = null,
        .flags = 0,
        .connection = xcb_connection,
        .window = xcb_window,
    };
    try check_vk(vkCreateXcbSurfaceKHR(instance, &create_info, null, &surface));
    if (surface == VK_NULL_U64) return error.InvalidState;
    return surface;
}

/// Create a VkSurfaceKHR from an Xlib display+window pair.
pub fn create_xlib_surface(
    instance: VkInstance,
    xlib_display: ?*anyopaque,
    xlib_window: u64,
) common_errors.BackendNativeError!VkSurfaceKHR {
    if (!is_linux) return error.UnsupportedFeature;
    if (xlib_display == null) return error.InvalidArgument;

    var surface: VkSurfaceKHR = VK_NULL_U64;
    const create_info = VkXlibSurfaceCreateInfoKHR{
        .sType = VK_STRUCTURE_TYPE_XLIB_SURFACE_CREATE_INFO_KHR,
        .pNext = null,
        .flags = 0,
        .dpy = xlib_display,
        .window = xlib_window,
    };
    try check_vk(vkCreateXlibSurfaceKHR(instance, &create_info, null, &surface));
    if (surface == VK_NULL_U64) return error.InvalidState;
    return surface;
}

/// Destroy a VkSurfaceKHR.
pub fn destroy_surface(instance: VkInstance, surface: VkSurfaceKHR) void {
    if (surface != VK_NULL_U64) {
        vkDestroySurfaceKHR(instance, surface, null);
    }
}

/// Query whether a queue family supports presentation to a given surface.
pub fn query_present_support(
    physical_device: VkPhysicalDevice,
    queue_family_index: u32,
    surface: VkSurfaceKHR,
) common_errors.BackendNativeError!bool {
    if (surface == VK_NULL_U64) return false;
    var supported: VkBool32 = VK_FALSE;
    try check_vk(vkGetPhysicalDeviceSurfaceSupportKHR(
        physical_device,
        queue_family_index,
        surface,
        &supported,
    ));
    return supported == VK_TRUE;
}

/// Query full surface capabilities, formats, and present modes.
pub fn query_surface_capabilities(
    physical_device: VkPhysicalDevice,
    queue_family_index: u32,
    surface: VkSurfaceKHR,
) common_errors.BackendNativeError!SurfaceCapabilities {
    if (surface == VK_NULL_U64) return error.SurfaceUnavailable;

    var result = SurfaceCapabilities{};

    // Present support
    result.present_supported = try query_present_support(
        physical_device,
        queue_family_index,
        surface,
    );

    // Surface capabilities
    var caps = std.mem.zeroes(VkSurfaceCapabilitiesKHR);
    try check_vk(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physical_device, surface, &caps));
    result.min_image_count = caps.minImageCount;
    result.max_image_count = caps.maxImageCount;
    result.current_width = caps.currentExtent.width;
    result.current_height = caps.currentExtent.height;
    result.min_width = caps.minImageExtent.width;
    result.min_height = caps.minImageExtent.height;
    result.max_width = caps.maxImageExtent.width;
    result.max_height = caps.maxImageExtent.height;
    result.supported_usage = caps.supportedUsageFlags;
    result.supported_alpha = caps.supportedCompositeAlpha;
    result.current_transform = caps.currentTransform;

    // Surface formats
    var format_count: u32 = 0;
    try check_vk(vkGetPhysicalDeviceSurfaceFormatsKHR(physical_device, surface, &format_count, null));
    if (format_count > 0) {
        const capped_count = @min(format_count, MAX_SURFACE_FORMATS);
        var count_for_query: u32 = @intCast(capped_count);
        try check_vk(vkGetPhysicalDeviceSurfaceFormatsKHR(
            physical_device,
            surface,
            &count_for_query,
            &result.formats,
        ));
        result.format_count = count_for_query;
    }

    // Present modes
    var mode_count: u32 = 0;
    try check_vk(vkGetPhysicalDeviceSurfacePresentModesKHR(physical_device, surface, &mode_count, null));
    if (mode_count > 0) {
        const capped_modes = @min(mode_count, MAX_PRESENT_MODES);
        var count_for_mode_query: u32 = @intCast(capped_modes);
        try check_vk(vkGetPhysicalDeviceSurfacePresentModesKHR(
            physical_device,
            surface,
            &count_for_mode_query,
            &result.present_modes,
        ));
        result.present_mode_count = count_for_mode_query;
    }

    return result;
}

// The format table is the intersection of implemented canvas formats and native WSI.
const CANVAS_FORMATS = [_]struct { webgpu: u32, vulkan: u32 }{
    .{ .webgpu = model_gpu_types.WGPUTextureFormat_BGRA8Unorm, .vulkan = VK_FORMAT_B8G8R8A8_UNORM },
    .{ .webgpu = model_gpu_types.WGPUTextureFormat_RGBA8Unorm, .vulkan = VK_FORMAT_R8G8B8A8_UNORM },
    .{ .webgpu = model_gpu_types.WGPUTextureFormat_BGRA8UnormSrgb, .vulkan = VK_FORMAT_B8G8R8A8_SRGB },
    .{ .webgpu = model_gpu_types.WGPUTextureFormat_RGBA8UnormSrgb, .vulkan = VK_FORMAT_R8G8B8A8_SRGB },
};
const PRESENT_MODES = [_]struct { webgpu: u32, vulkan: u32 }{
    .{ .webgpu = WGPU_PRESENT_MODE_FIFO, .vulkan = VK_PRESENT_MODE_FIFO_KHR },
    .{ .webgpu = WGPU_PRESENT_MODE_FIFO_RELAXED, .vulkan = VK_PRESENT_MODE_FIFO_RELAXED_KHR },
    .{ .webgpu = WGPU_PRESENT_MODE_IMMEDIATE, .vulkan = VK_PRESENT_MODE_IMMEDIATE_KHR },
    .{ .webgpu = WGPU_PRESENT_MODE_MAILBOX, .vulkan = VK_PRESENT_MODE_MAILBOX_KHR },
};
const ALPHA_MODES = [_]struct { webgpu: u32, vulkan: u32 }{
    .{ .webgpu = WGPU_ALPHA_INHERIT, .vulkan = VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR },
    .{ .webgpu = WGPU_ALPHA_OPAQUE, .vulkan = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR },
    .{ .webgpu = WGPU_ALPHA_PREMULTIPLIED, .vulkan = VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR },
    .{ .webgpu = WGPU_ALPHA_UNPREMULTIPLIED, .vulkan = VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR },
};
const USAGES = [_]struct { webgpu: u32, vulkan: u32 }{
    .{ .webgpu = model_gpu_types.WGPUTextureUsage_RenderAttachment, .vulkan = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT },
    .{ .webgpu = model_gpu_types.WGPUTextureUsage_CopySrc, .vulkan = VK_IMAGE_USAGE_TRANSFER_SRC_BIT },
    .{ .webgpu = model_gpu_types.WGPUTextureUsage_CopyDst, .vulkan = VK_IMAGE_USAGE_TRANSFER_DST_BIT },
    .{ .webgpu = model_gpu_types.WGPUTextureUsage_TextureBinding, .vulkan = VK_IMAGE_USAGE_SAMPLED_BIT },
};

fn selectSurfaceFormat(formats: []const VkSurfaceFormatKHR, requested: u32) !VkSurfaceFormatKHR {
    for (CANVAS_FORMATS) |candidate| {
        if (candidate.webgpu != requested) continue;
        for (formats) |format| {
            // VK_FORMAT_UNDEFINED permits any format, but still fixes color space.
            if ((format.format == candidate.vulkan or format.format == VK_FORMAT_UNDEFINED) and
                format.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR)
                return .{ .format = candidate.vulkan, .colorSpace = format.colorSpace };
        }
    }
    return error.UnsupportedFeature;
}

pub const CanvasCapabilities = struct {
    formats: [CANVAS_FORMATS.len]u32 = undefined,
    format_count: usize = 0,
    present_modes: [PRESENT_MODES.len]u32 = undefined,
    present_mode_count: usize = 0,
    alpha_modes: [ALPHA_MODES.len]u32 = undefined,
    alpha_mode_count: usize = 0,
    usages: u32 = 0,
};

pub fn canvasCapabilities(caps: SurfaceCapabilities) !CanvasCapabilities {
    if (!caps.present_supported) return error.SurfaceUnavailable;
    var result = CanvasCapabilities{};
    for (CANVAS_FORMATS) |format| {
        _ = selectSurfaceFormat(caps.formats[0..caps.format_count], format.webgpu) catch continue;
        result.formats[result.format_count] = format.webgpu;
        result.format_count += 1;
    }
    for (PRESENT_MODES) |mode| {
        if (std.mem.indexOfScalar(u32, caps.present_modes[0..caps.present_mode_count], mode.vulkan) == null) continue;
        result.present_modes[result.present_mode_count] = mode.webgpu;
        result.present_mode_count += 1;
    }
    for (ALPHA_MODES) |mode| {
        if (caps.supported_alpha & mode.vulkan == 0) continue;
        result.alpha_modes[result.alpha_mode_count] = mode.webgpu;
        result.alpha_mode_count += 1;
    }
    for (USAGES) |usage| {
        if (caps.supported_usage & usage.vulkan != 0) result.usages |= usage.webgpu;
    }
    if (result.format_count == 0 or result.alpha_mode_count == 0 or
        std.mem.indexOfScalar(u32, result.present_modes[0..result.present_mode_count], WGPU_PRESENT_MODE_FIFO) == null or
        result.usages & model_gpu_types.WGPUTextureUsage_RenderAttachment == 0) return error.UnsupportedFeature;
    return result;
}

pub fn preferred_canvas_format_from_surface_formats(formats: []const VkSurfaceFormatKHR) u32 {
    for (CANVAS_FORMATS) |candidate| {
        _ = selectSurfaceFormat(formats, candidate.webgpu) catch continue;
        return candidate.webgpu;
    }
    return model_gpu_types.WGPUTextureFormat_Undefined;
}

pub const AdmittedConfiguration = struct {
    format: VkSurfaceFormatKHR,
    extent: VkExtent2D,
    present_mode: u32,
    alpha: u32,
    usage: VkFlags,
};

/// Validate before retiring an existing swapchain. No field is silently substituted.
pub fn admitConfiguration(caps: SurfaceCapabilities, request: surface_contract.SurfaceConfigureCommand) !AdmittedConfiguration {
    const canvas = try canvasCapabilities(caps);
    if (request.tone_mapping_mode != WGPU_CANVAS_TONE_MAPPING_MODE_STANDARD) return error.UnsupportedFeature;
    const format = try selectSurfaceFormat(caps.formats[0..caps.format_count], request.format);
    if (request.width < caps.min_width or request.width > caps.max_width or
        request.height < caps.min_height or request.height > caps.max_height or
        request.width == 0 or request.height == 0) return error.InvalidArgument;
    if (caps.current_width != std.math.maxInt(u32) and
        (request.width != caps.current_width or request.height != caps.current_height)) return error.UnsupportedFeature;
    if (request.usage & ~canvas.usages != 0 or request.usage & model_gpu_types.WGPUTextureUsage_RenderAttachment == 0) return error.UnsupportedFeature;
    var usage: VkFlags = 0;
    for (USAGES) |entry| {
        if (request.usage & entry.webgpu != 0) usage |= entry.vulkan;
    }
    const present = if (request.present_mode == 0) WGPU_PRESENT_MODE_FIFO else request.present_mode;
    if (std.mem.indexOfScalar(u32, canvas.present_modes[0..canvas.present_mode_count], present) == null) return error.UnsupportedFeature;
    const alpha = if (request.alpha_mode == WGPU_ALPHA_AUTO) canvas.alpha_modes[0] else request.alpha_mode;
    if (std.mem.indexOfScalar(u32, canvas.alpha_modes[0..canvas.alpha_mode_count], alpha) == null) return error.UnsupportedFeature;
    var native_present: u32 = undefined;
    var native_alpha: u32 = undefined;
    for (PRESENT_MODES) |entry| {
        if (entry.webgpu == present) {
            native_present = entry.vulkan;
            break;
        }
    }
    for (ALPHA_MODES) |entry| {
        if (entry.webgpu == alpha) {
            native_alpha = entry.vulkan;
            break;
        }
    }
    return .{ .format = format, .extent = .{ .width = request.width, .height = request.height }, .present_mode = native_present, .alpha = native_alpha, .usage = usage };
}

/// Create (or recreate) a swapchain for the given surface.
pub fn create_swapchain(
    device: VkDevice,
    surface_state: *VulkanSurface,
    queue_family_index: u32,
    admitted: AdmittedConfiguration,
) common_errors.BackendNativeError!void {
    if (surface_state.vk_surface == VK_NULL_U64) return error.SurfaceUnavailable;

    const caps = surface_state.cached_capabilities;
    // Image count: prefer one more than minimum for triple buffering
    var image_count: u32 = caps.min_image_count + 1;
    if (caps.max_image_count > 0 and image_count > caps.max_image_count) {
        image_count = caps.max_image_count;
    }

    std.debug.assert(surface_state.swapchain == VK_NULL_U64);

    const create_info = VkSwapchainCreateInfoKHR{
        .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
        .pNext = null,
        .flags = 0,
        .surface = surface_state.vk_surface,
        .minImageCount = image_count,
        .imageFormat = admitted.format.format,
        .imageColorSpace = admitted.format.colorSpace,
        .imageExtent = admitted.extent,
        .imageArrayLayers = 1,
        .imageUsage = admitted.usage,
        .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE,
        .queueFamilyIndexCount = 1,
        .pQueueFamilyIndices = @ptrCast(&queue_family_index),
        .preTransform = caps.current_transform,
        .compositeAlpha = admitted.alpha,
        .presentMode = admitted.present_mode,
        .clipped = VK_TRUE,
        .oldSwapchain = VK_NULL_U64,
    };

    try check_vk(vkCreateSwapchainKHR(device, &create_info, null, &surface_state.swapchain));
    errdefer destroy_swapchain(device, surface_state);

    var actual_image_count: u32 = 0;
    try check_vk(vkGetSwapchainImagesKHR(device, surface_state.swapchain, &actual_image_count, null));
    if (actual_image_count == 0) return error.InvalidState;
    if (actual_image_count > MAX_SWAPCHAIN_IMAGES) return error.InvalidState;
    try check_vk(vkGetSwapchainImagesKHR(
        device,
        surface_state.swapchain,
        &actual_image_count,
        &surface_state.swapchain_images,
    ));
    surface_state.swapchain_image_count = actual_image_count;
    surface_state.swapchain_format = admitted.format.format;
    surface_state.swapchain_extent = admitted.extent;
    surface_state.format = surface_state.requested_format;
    surface_state.last_acquire_suboptimal = false;
    surface_state.last_present_suboptimal = false;

    surface_state.completion = try surface_sync.Completion.init(device);
}

/// Destroy the swapchain and associated resources (not the VkSurfaceKHR itself).
pub fn destroy_swapchain(device: VkDevice, surface_state: *VulkanSurface) void {
    surface_state.completion.deinit(device);
    if (surface_state.swapchain != VK_NULL_U64) {
        vkDestroySwapchainKHR(device, surface_state.swapchain, null);
        surface_state.swapchain = VK_NULL_U64;
    }
    surface_state.swapchain_image_count = 0;
    surface_state.swapchain_images = [_]VkImage{VK_NULL_U64} ** MAX_SWAPCHAIN_IMAGES;
    surface_state.swapchain_extent = .{ .width = 0, .height = 0 };
}

/// Acquire the next swapchain image. Returns the image index.
pub fn acquire_next_image(
    device: VkDevice,
    surface_state: *VulkanSurface,
) common_errors.BackendNativeError!u32 {
    if (surface_state.swapchain == VK_NULL_U64) return error.SurfaceUnavailable;

    try surface_state.completion.waitPresent(device);
    if (surface_state.acquired) {
        try surface_state.completion.waitAcquire(device);
        return surface_state.current_image_index;
    }
    try check_vk(c.vkResetFences(device, 1, @ptrCast(&surface_state.completion.acquire_fence)));
    var image_index: u32 = 0;
    const result = vkAcquireNextImageKHR(
        device,
        surface_state.swapchain,
        ACQUIRE_TIMEOUT_NS,
        VK_NULL_U64,
        surface_state.completion.acquire_fence,
        &image_index,
    );
    switch (result) {
        VK_SUCCESS, VK_SUBOPTIMAL_KHR => {
            surface_state.current_image_index = image_index;
            surface_state.acquired = true;
            surface_state.completion.acquire_pending = true;
            try surface_state.completion.waitAcquire(device);
            surface_state.last_acquire_suboptimal = result == VK_SUBOPTIMAL_KHR;
            return image_index;
        },
        c.VK_TIMEOUT => return error.SyncUnavailable,
        VK_ERROR_OUT_OF_DATE_KHR => {
            // Swapchain needs recreation; caller should reconfigure
            return error.SurfaceUnavailable;
        },
        else => {
            try check_vk(result);
            unreachable;
        },
    }
}

/// Present the acquired swapchain image.
pub fn present_image(
    device: VkDevice,
    queue: VkQueue,
    surface_state: *VulkanSurface,
) common_errors.BackendNativeError!void {
    if (surface_state.swapchain == VK_NULL_U64 or !surface_state.acquired) {
        return error.SurfaceUnavailable;
    }

    if (!surface_state.completion.present_ready) return error.InvalidState;
    try check_vk(c.vkResetFences(device, 1, @ptrCast(&surface_state.completion.present_fence)));
    const fence_info = surface_sync.PresentFenceInfo{ .pFences = &surface_state.completion.present_fence };
    const present_info = VkPresentInfoKHR{
        .sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR,
        .pNext = @ptrCast(&fence_info),
        .waitSemaphoreCount = 1,
        .pWaitSemaphores = @ptrCast(&surface_state.completion.render_finished),
        .swapchainCount = 1,
        .pSwapchains = @ptrCast(&surface_state.swapchain),
        .pImageIndices = @ptrCast(&surface_state.current_image_index),
        .pResults = null,
    };

    const result = vkQueuePresentKHR(queue, &present_info);
    if (@import("vk_sync.zig").submissionRejected(result)) return check_vk(result);
    surface_state.completion.present_ready = false;
    surface_state.completion.present_pending = true;
    surface_state.completion.device_lost = result == vulkan_errors.VK_ERROR_DEVICE_LOST;
    surface_state.acquired = false;
    surface_state.last_present_suboptimal = result == VK_SUBOPTIMAL_KHR;

    switch (result) {
        VK_SUCCESS, VK_SUBOPTIMAL_KHR => return,
        VK_ERROR_OUT_OF_DATE_KHR => {
            return error.SurfaceUnavailable;
        },
        else => return check_vk(result),
    }
}

/// Full cleanup of a VulkanSurface: swapchain, sync objects, and the surface itself.
pub fn destroy_all(
    instance: VkInstance,
    device: VkDevice,
    surface_state: *VulkanSurface,
) void {
    destroy_swapchain(device, surface_state);
    destroy_surface(instance, surface_state.vk_surface);
    surface_state.vk_surface = VK_NULL_U64;
    surface_state.configured = false;
    surface_state.acquired = false;
}

// Delegate to vulkan_errors.zig — single source of truth for VkResult mapping.
const check_vk = vulkan_errors.check_vk;
