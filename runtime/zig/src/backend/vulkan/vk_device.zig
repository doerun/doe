// Vulkan instance, physical device, and device lifecycle.
//
// Handles bootstrap (instance creation, adapter selection, device+queue
// creation, command pool, fence) and memory type queries.

const std = @import("std");
const c = @import("vk_constants.zig");
const vulkan_surface = @import("vulkan_surface.zig");
const common_errors = @import("../common/errors.zig");

const VkResult = c.VkResult;
const VkInstance = c.VkInstance;
const VkPhysicalDevice = c.VkPhysicalDevice;
const VkDevice = c.VkDevice;
const VkQueue = c.VkQueue;
const VkCommandPool = c.VkCommandPool;
const VkCommandBuffer = c.VkCommandBuffer;
const VkFence = c.VkFence;
const VK_NULL_U64 = c.VK_NULL_U64;

const APP_NAME: [*:0]const u8 = "doe-zig-runtime";
const ENGINE_NAME: [*:0]const u8 = "doe-vulkan-runtime";

pub const QueueFamilySelection = struct {
    index: u32,
    supports_graphics: bool,
    timestamp_valid_bits: u32,
    queue_count: u32,
};

pub const PhysicalDeviceSelection = struct {
    index: u32,
    queue: QueueFamilySelection,
    score: u64,
};

/// Opaque NativeVulkanRuntime reference; fields accessed through this module
/// are the device/instance lifecycle subset.
const Runtime = @import("native_runtime.zig").NativeVulkanRuntime;

pub fn bootstrap(self: *Runtime) !void {
    try create_instance(self);
    try select_physical_device(self);
    try create_device_and_queue(self);
    try create_command_pool_and_primary_buffer(self);
    try create_fence(self);
}

pub fn create_instance(self: *Runtime) !void {
    const surface_exts = vulkan_surface.required_instance_extensions();
    var app_info = c.VkApplicationInfo{
        .sType = c.VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pNext = null,
        .pApplicationName = APP_NAME,
        .applicationVersion = 0,
        .pEngineName = ENGINE_NAME,
        .engineVersion = 0,
        .apiVersion = c.VK_API_VERSION_1_0,
    };
    var create_info = c.VkInstanceCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .pApplicationInfo = &app_info,
        .enabledLayerCount = 0,
        .ppEnabledLayerNames = null,
        .enabledExtensionCount = @intCast(surface_exts.len),
        .ppEnabledExtensionNames = if (surface_exts.len > 0) surface_exts.ptr else null,
    };
    try c.check_vk(c.vkCreateInstance(&create_info, null, &self.instance));
    self.has_instance = true;
}

pub fn select_physical_device(self: *Runtime) !void {
    var count: u32 = 0;
    try c.check_vk(c.vkEnumeratePhysicalDevices(self.instance, &count, null));
    if (count == 0) return error.UnsupportedFeature;
    const devices = try self.allocator.alloc(VkPhysicalDevice, count);
    defer self.allocator.free(devices);
    try c.check_vk(c.vkEnumeratePhysicalDevices(self.instance, &count, devices.ptr));
    const selection = try select_preferred_physical_device(self, devices[0..count]);
    self.physical_device = devices[selection.index];
    self.adapter_ordinal_value = selection.index;
    self.queue_family_index = selection.queue.index;
    self.queue_family_index_value_cache = selection.queue.index;
    self.present_capable_value = selection.queue.supports_graphics;
    self.timestamp_query_supported_value = selection.queue.timestamp_valid_bits > 0;
}

pub fn create_device_and_queue(self: *Runtime) !void {
    const device_exts = vulkan_surface.required_device_extensions();
    var priority: f32 = 1.0;
    var queue_info = c.VkDeviceQueueCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .queueFamilyIndex = self.queue_family_index,
        .queueCount = 1,
        .pQueuePriorities = @ptrCast(&priority),
    };
    var device_info = c.VkDeviceCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .queueCreateInfoCount = 1,
        .pQueueCreateInfos = @ptrCast(&queue_info),
        .enabledLayerCount = 0,
        .ppEnabledLayerNames = null,
        .enabledExtensionCount = @intCast(device_exts.len),
        .ppEnabledExtensionNames = if (device_exts.len > 0) device_exts.ptr else null,
        .pEnabledFeatures = null,
    };
    try c.check_vk(c.vkCreateDevice(self.physical_device, &device_info, null, &self.device));
    self.has_device = true;
    c.vkGetDeviceQueue(self.device, self.queue_family_index, 0, &self.queue);
    if (self.queue == null) return error.InvalidState;
}

pub fn create_command_pool_and_primary_buffer(self: *Runtime) !void {
    var pool_info = c.VkCommandPoolCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
        .queueFamilyIndex = self.queue_family_index,
    };
    try c.check_vk(c.vkCreateCommandPool(self.device, &pool_info, null, &self.command_pool));
    self.has_command_pool = true;

    var alloc_info = c.VkCommandBufferAllocateInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .pNext = null,
        .commandPool = self.command_pool,
        .level = c.VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1,
    };
    try c.check_vk(c.vkAllocateCommandBuffers(self.device, &alloc_info, @ptrCast(&self.primary_command_buffer)));
    self.has_primary_command_buffer = true;
}

pub fn create_fence(self: *Runtime) !void {
    var fence_info = c.VkFenceCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_FENCE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
    };
    try c.check_vk(c.vkCreateFence(self.device, &fence_info, null, &self.fence));
    self.has_fence = true;
}

pub fn find_memory_type_index(self: *Runtime, type_bits: u32, required_flags: u32) !u32 {
    var memory_props = std.mem.zeroes(c.VkPhysicalDeviceMemoryProperties);
    c.vkGetPhysicalDeviceMemoryProperties(self.physical_device, &memory_props);
    var i: u32 = 0;
    while (i < memory_props.memoryTypeCount) : (i += 1) {
        const supports_type = (type_bits & (@as(u32, 1) << @as(u5, @intCast(i)))) != 0;
        if (!supports_type) continue;
        if ((memory_props.memoryTypes[i].propertyFlags & required_flags) == required_flags) return i;
    }
    return error.UnsupportedFeature;
}

fn select_preferred_physical_device(self: *Runtime, devices: []const VkPhysicalDevice) !PhysicalDeviceSelection {
    var best: ?PhysicalDeviceSelection = null;
    for (devices, 0..) |device, index| {
        const queue = select_queue_family_for_device(self, device) catch continue;
        const score = score_physical_device(device, queue);
        const candidate = PhysicalDeviceSelection{
            .index = @as(u32, @intCast(index)),
            .queue = queue,
            .score = score,
        };
        if (best == null or candidate.score > best.?.score) {
            best = candidate;
        }
    }
    return best orelse error.UnsupportedFeature;
}

fn select_queue_family_for_device(self: *Runtime, device: VkPhysicalDevice) !QueueFamilySelection {
    var count: u32 = 0;
    c.vkGetPhysicalDeviceQueueFamilyProperties(device, &count, null);
    if (count == 0) return error.UnsupportedFeature;
    const props = try self.allocator.alloc(c.VkQueueFamilyProperties, count);
    defer self.allocator.free(props);
    c.vkGetPhysicalDeviceQueueFamilyProperties(device, &count, props.ptr);

    var best: ?QueueFamilySelection = null;
    for (props, 0..) |family, idx| {
        if ((family.queueFlags & c.VK_QUEUE_COMPUTE_BIT) == 0 or family.queueCount == 0) continue;
        const candidate = QueueFamilySelection{
            .index = @as(u32, @intCast(idx)),
            .supports_graphics = (family.queueFlags & c.VK_QUEUE_GRAPHICS_BIT) != 0,
            .timestamp_valid_bits = family.timestampValidBits,
            .queue_count = family.queueCount,
        };
        if (best == null or queue_selection_score(candidate) > queue_selection_score(best.?)) {
            best = candidate;
        }
    }
    return best orelse error.UnsupportedFeature;
}

fn score_physical_device(device: VkPhysicalDevice, queue: QueueFamilySelection) u64 {
    var memory_props = std.mem.zeroes(c.VkPhysicalDeviceMemoryProperties);
    c.vkGetPhysicalDeviceMemoryProperties(device, &memory_props);

    var device_local_heap_bytes: u64 = 0;
    var type_index: u32 = 0;
    while (type_index < memory_props.memoryTypeCount) : (type_index += 1) {
        const memory_type = memory_props.memoryTypes[type_index];
        if ((memory_type.propertyFlags & c.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) == 0) continue;
        if (memory_type.heapIndex >= memory_props.memoryHeapCount) continue;
        device_local_heap_bytes +|= memory_props.memoryHeaps[memory_type.heapIndex].size;
    }

    return queue_selection_score(queue) + (device_local_heap_bytes / (1024 * 1024));
}

pub fn queue_selection_score(selection: QueueFamilySelection) u64 {
    var score: u64 = 0;
    score +|= @as(u64, selection.queue_count) * 100;
    if (selection.supports_graphics) score +|= 10_000;
    if (selection.timestamp_valid_bits > 0) score +|= 1_000;
    return score;
}
