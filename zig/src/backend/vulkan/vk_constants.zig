// Vulkan constants, extern struct types, and extern function declarations.
//
// Centralizes all Vulkan API identifiers so runtime modules reference
// named constants instead of bare magic numbers.

const std = @import("std");
const vk = @import("vulkan_types.zig");

pub const VkBool32 = vk.VkBool32;
pub const VkFlags = vk.VkFlags;
pub const VkDeviceSize = vk.VkDeviceSize;
pub const VkStructureType = vk.VkStructureType;
pub const VkResult = vk.VkResult;
pub const VkInstance = vk.VkInstance;
pub const VkPhysicalDevice = vk.VkPhysicalDevice;
pub const VkDevice = vk.VkDevice;
pub const VkQueue = vk.VkQueue;
pub const VkCommandBuffer = vk.VkCommandBuffer;
pub const VkPipelineCache = vk.VkPipelineCache;
pub const VkCommandPool = vk.VkCommandPool;
pub const VkFence = vk.VkFence;
pub const VkBuffer = vk.VkBuffer;
pub const VkDeviceMemory = vk.VkDeviceMemory;
pub const VkShaderModule = vk.VkShaderModule;
pub const VkPipelineLayout = vk.VkPipelineLayout;
pub const VkPipeline = vk.VkPipeline;
pub const VkQueryPool = vk.VkQueryPool;
pub const VkDescriptorSetLayout = vk.VkDescriptorSetLayout;
pub const VkDescriptorPool = vk.VkDescriptorPool;
pub const VkDescriptorSet = vk.VkDescriptorSet;
pub const VkImage = vk.VkImage;
pub const VkImageView = vk.VkImageView;
pub const VkRenderPass = vk.VkRenderPass;
pub const VkFramebuffer = vk.VkFramebuffer;
pub const VkSampler = vk.VkSampler;
pub const VK_NULL_U64 = vk.VK_NULL_U64;
pub const VkAllocationCallbacks = vk.VkAllocationCallbacks;

pub const VK_SUCCESS = vk.VK_SUCCESS;
pub const VK_TRUE = vk.VK_TRUE;
pub const VK_FALSE = vk.VK_FALSE;
pub const VK_API_VERSION_1_0: u32 = 0x00400000;

// --- VkStructureType values ---
pub const VK_STRUCTURE_TYPE_APPLICATION_INFO: i32 = 0;
pub const VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO: i32 = 1;
pub const VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO: i32 = 2;
pub const VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO: i32 = 3;
pub const VK_STRUCTURE_TYPE_SUBMIT_INFO: i32 = 4;
pub const VK_STRUCTURE_TYPE_FENCE_CREATE_INFO: i32 = 8;
pub const VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO: i32 = 11;
pub const VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO: i32 = 12;
pub const VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO: i32 = 14;
pub const VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO: i32 = 15;
pub const VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO: i32 = 16;
pub const VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO: i32 = 17;
pub const VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO: i32 = 18;
pub const VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO: i32 = 28;
pub const VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO: i32 = 30;
pub const VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO: i32 = 32;
pub const VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO: i32 = 33;
pub const VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO: i32 = 34;
pub const VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET: i32 = 35;
pub const VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO: i32 = 39;
pub const VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO: i32 = 40;
pub const VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO: i32 = 42;
pub const VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER: i32 = 45;

// --- Queue and command bits ---
pub const VK_QUEUE_GRAPHICS_BIT: u32 = 0x00000001;
pub const VK_QUEUE_COMPUTE_BIT: u32 = 0x00000002;
pub const VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT: u32 = 0x00000002;
pub const VK_COMMAND_BUFFER_LEVEL_PRIMARY: i32 = 0;
pub const VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT: u32 = 0x00000001;
pub const VK_PIPELINE_BIND_POINT_COMPUTE: i32 = 1;

// --- Shader and pipeline stage bits ---
pub const VK_SHADER_STAGE_VERTEX_BIT: u32 = 0x00000001;
pub const VK_SHADER_STAGE_FRAGMENT_BIT: u32 = 0x00000010;
pub const VK_SHADER_STAGE_COMPUTE_BIT: u32 = 0x00000020;
pub const VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT: u32 = 0x00000001;
pub const VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT: u32 = 0x00000400;
pub const VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT: u32 = 0x00000800;
pub const VK_PIPELINE_STAGE_TRANSFER_BIT: u32 = 0x00001000;
pub const VK_PIPELINE_BIND_POINT_GRAPHICS: i32 = 0;

// --- Query ---
pub const VK_QUERY_TYPE_TIMESTAMP: u32 = 2;
pub const VK_QUERY_RESULT_64_BIT: u32 = 0x00000001;
pub const VK_QUERY_RESULT_WAIT_BIT: u32 = 0x00000002;

// --- Buffer usage ---
pub const VK_BUFFER_USAGE_TRANSFER_SRC_BIT: u32 = 0x00000001;
pub const VK_BUFFER_USAGE_TRANSFER_DST_BIT: u32 = 0x00000002;
pub const VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT: u32 = 0x00000010;
pub const VK_BUFFER_USAGE_STORAGE_BUFFER_BIT: u32 = 0x00000020;
pub const VK_BUFFER_USAGE_INDEX_BUFFER_BIT: u32 = 0x00000040;
pub const VK_BUFFER_USAGE_VERTEX_BUFFER_BIT: u32 = 0x00000080;

// --- Image usage ---
pub const VK_IMAGE_USAGE_TRANSFER_SRC_BIT: u32 = 0x00000001;
pub const VK_IMAGE_USAGE_TRANSFER_DST_BIT: u32 = 0x00000002;
pub const VK_IMAGE_USAGE_SAMPLED_BIT: u32 = 0x00000004;
pub const VK_IMAGE_USAGE_STORAGE_BIT: u32 = 0x00000008;
pub const VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT: u32 = 0x00000010;

// --- Memory and sharing ---
pub const VK_SHARING_MODE_EXCLUSIVE: i32 = 0;
pub const VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT: u32 = 0x00000001;
pub const VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT: u32 = 0x00000002;
pub const VK_MEMORY_PROPERTY_HOST_COHERENT_BIT: u32 = 0x00000004;

// --- Access flags ---
pub const VK_ACCESS_SHADER_READ_BIT: u32 = 0x00000020;
pub const VK_ACCESS_SHADER_WRITE_BIT: u32 = 0x00000040;
pub const VK_ACCESS_COLOR_ATTACHMENT_READ_BIT: u32 = 0x00000080;
pub const VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT: u32 = 0x00000100;
pub const VK_ACCESS_TRANSFER_WRITE_BIT: u32 = 0x00001000;

// --- Descriptor types ---
pub const VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE: u32 = 2;
pub const VK_DESCRIPTOR_TYPE_STORAGE_IMAGE: u32 = 3;
pub const VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER: u32 = 6;
pub const VK_DESCRIPTOR_TYPE_STORAGE_BUFFER: u32 = 7;
pub const VK_WHOLE_SIZE: u64 = std.math.maxInt(u64);
pub const MAX_DESCRIPTOR_SETS: usize = 4;
pub const MAX_DESCRIPTOR_SETS_U32: u32 = 4;

// --- Image format and layout ---
pub const VK_IMAGE_TYPE_2D: u32 = 1;
pub const VK_IMAGE_VIEW_TYPE_2D: u32 = 1;
pub const VK_IMAGE_TILING_OPTIMAL: u32 = 0;
pub const VK_IMAGE_LAYOUT_UNDEFINED: u32 = 0;
pub const VK_IMAGE_LAYOUT_GENERAL: u32 = 1;
pub const VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL: u32 = 2;
pub const VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL: u32 = 7;
pub const VK_IMAGE_ASPECT_COLOR_BIT: u32 = 0x00000001;
pub const VK_SAMPLE_COUNT_1_BIT: u32 = 0x00000001;
pub const VK_COMPONENT_SWIZZLE_IDENTITY: u32 = 0;
pub const VK_FORMAT_R8G8B8A8_UNORM: u32 = 37;

// --- VkResult error codes (named for fail-fast error mapping) ---
pub const VK_ERROR_TOO_MANY_OBJECTS: VkResult = -7;
pub const VK_ERROR_FORMAT_NOT_SUPPORTED: VkResult = -9;
pub const VK_ERROR_FRAGMENTED_POOL: VkResult = -10;
pub const VK_ERROR_UNKNOWN: VkResult = -11;

// --- Surface / present mode constants (shared with configure_surface) ---
pub const VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR: u32 = 0x00000001;
pub const VK_PRESENT_MODE_FIFO_KHR: u32 = 0x00000002;

// --- Default frame latency for surface configuration ---
pub const DEFAULT_SURFACE_MAX_FRAME_LATENCY: u32 = 2;

// --- Render pass constants ---
pub const VK_ATTACHMENT_LOAD_OP_CLEAR: u32 = 1;
pub const VK_ATTACHMENT_LOAD_OP_DONT_CARE: u32 = 2;
pub const VK_ATTACHMENT_STORE_OP_STORE: u32 = 0;
pub const VK_ATTACHMENT_STORE_OP_DONT_CARE: u32 = 1;
pub const VK_SUBPASS_EXTERNAL: u32 = std.math.maxInt(u32);
pub const VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT: u32 = 0x00002000;

// --- Graphics pipeline structure type IDs ---
pub const VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO: i32 = 38;
pub const VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO: i32 = 37;
pub const VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO: i32 = 28 - 1; // sType = 27
pub const VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO: i32 = 19;
pub const VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO: i32 = 20;
pub const VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO: i32 = 22;
pub const VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO: i32 = 23;
pub const VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO: i32 = 24;
pub const VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO: i32 = 26;
pub const VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO: i32 = 27;
pub const VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO: i32 = 43;
pub const VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO: i32 = 31;
pub const VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO: i32 = 25;

// --- Graphics topology and polygon mode ---
pub const VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST: u32 = 3;
pub const VK_POLYGON_MODE_FILL: u32 = 0;
pub const VK_CULL_MODE_NONE: u32 = 0;
pub const VK_FRONT_FACE_COUNTER_CLOCKWISE: u32 = 0;
pub const VK_LOGIC_OP_CLEAR: u32 = 0;

// --- Color blend ---
pub const VK_COLOR_COMPONENT_R_BIT: u32 = 0x00000001;
pub const VK_COLOR_COMPONENT_G_BIT: u32 = 0x00000002;
pub const VK_COLOR_COMPONENT_B_BIT: u32 = 0x00000004;
pub const VK_COLOR_COMPONENT_A_BIT: u32 = 0x00000008;
pub const VK_BLEND_FACTOR_ONE: u32 = 1;
pub const VK_BLEND_FACTOR_ZERO: u32 = 0;
pub const VK_BLEND_OP_ADD: u32 = 0;

// --- Dynamic state ---
pub const VK_DYNAMIC_STATE_VIEWPORT: u32 = 0;
pub const VK_DYNAMIC_STATE_SCISSOR: u32 = 1;

// --- Sampler constants ---
pub const VK_FILTER_NEAREST: u32 = 0;
pub const VK_SAMPLER_MIPMAP_MODE_NEAREST: u32 = 0;
pub const VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE: u32 = 2;
pub const VK_BORDER_COLOR_FLOAT_TRANSPARENT_BLACK: u32 = 0;
pub const VK_COMPARE_OP_NEVER: u32 = 0;

// --- Index type ---
pub const VK_INDEX_TYPE_UINT16: u32 = 0;
pub const VK_INDEX_TYPE_UINT32: u32 = 1;

// --- Descriptor type for combined image sampler ---
pub const VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER: u32 = 1;

// --- Extern struct types ---

pub const VkApplicationInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    pApplicationName: ?[*:0]const u8,
    applicationVersion: u32,
    pEngineName: ?[*:0]const u8,
    engineVersion: u32,
    apiVersion: u32,
};

pub const VkInstanceCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    pApplicationInfo: ?*const VkApplicationInfo,
    enabledLayerCount: u32,
    ppEnabledLayerNames: ?[*]const [*:0]const u8,
    enabledExtensionCount: u32,
    ppEnabledExtensionNames: ?[*]const [*:0]const u8,
};

pub const VkDeviceQueueCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    queueFamilyIndex: u32,
    queueCount: u32,
    pQueuePriorities: [*]const f32,
};

pub const VkDeviceCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    queueCreateInfoCount: u32,
    pQueueCreateInfos: [*]const VkDeviceQueueCreateInfo,
    enabledLayerCount: u32,
    ppEnabledLayerNames: ?[*]const [*:0]const u8,
    enabledExtensionCount: u32,
    ppEnabledExtensionNames: ?[*]const [*:0]const u8,
    pEnabledFeatures: ?*const anyopaque,
};

pub const VkCommandPoolCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    queueFamilyIndex: u32,
};

pub const VkCommandBufferAllocateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    commandPool: VkCommandPool,
    level: i32,
    commandBufferCount: u32,
};

pub const VkFenceCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
};

pub const VkBufferCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    size: VkDeviceSize,
    usage: VkFlags,
    sharingMode: i32,
    queueFamilyIndexCount: u32,
    pQueueFamilyIndices: ?[*]const u32,
};

pub const VkImageCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    imageType: u32,
    format: u32,
    extent: VkExtent3D,
    mipLevels: u32,
    arrayLayers: u32,
    samples: u32,
    tiling: u32,
    usage: VkFlags,
    sharingMode: i32,
    queueFamilyIndexCount: u32,
    pQueueFamilyIndices: ?[*]const u32,
    initialLayout: u32,
};

pub const VkMemoryAllocateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    allocationSize: VkDeviceSize,
    memoryTypeIndex: u32,
};

pub const VkMemoryRequirements = extern struct {
    size: VkDeviceSize,
    alignment: VkDeviceSize,
    memoryTypeBits: u32,
};

pub const VkCommandBufferBeginInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    pInheritanceInfo: ?*const anyopaque,
};

pub const VkSubmitInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    waitSemaphoreCount: u32,
    pWaitSemaphores: ?[*]const u64,
    pWaitDstStageMask: ?[*]const VkFlags,
    commandBufferCount: u32,
    pCommandBuffers: [*]const VkCommandBuffer,
    signalSemaphoreCount: u32,
    pSignalSemaphores: ?[*]const u64,
};

pub const VkShaderModuleCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    codeSize: usize,
    pCode: [*]const u32,
};

pub const VkPipelineLayoutCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    setLayoutCount: u32,
    pSetLayouts: ?[*]const u64,
    pushConstantRangeCount: u32,
    pPushConstantRanges: ?*const anyopaque,
};

pub const VkPipelineShaderStageCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    stage: VkFlags,
    module: VkShaderModule,
    pName: ?[*:0]const u8,
    pSpecializationInfo: ?*const anyopaque,
};

pub const VkDescriptorSetLayoutBinding = extern struct {
    binding: u32,
    descriptorType: u32,
    descriptorCount: u32,
    stageFlags: VkFlags,
    pImmutableSamplers: ?*const anyopaque,
};

pub const VkDescriptorSetLayoutCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    bindingCount: u32,
    pBindings: ?[*]const VkDescriptorSetLayoutBinding,
};

pub const VkDescriptorPoolSize = extern struct {
    type: u32,
    descriptorCount: u32,
};

pub const VkDescriptorPoolCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    maxSets: u32,
    poolSizeCount: u32,
    pPoolSizes: ?[*]const VkDescriptorPoolSize,
};

pub const VkDescriptorSetAllocateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    descriptorPool: VkDescriptorPool,
    descriptorSetCount: u32,
    pSetLayouts: [*]const VkDescriptorSetLayout,
};

pub const VkDescriptorBufferInfo = extern struct {
    buffer: VkBuffer,
    offset: VkDeviceSize,
    range: VkDeviceSize,
};

pub const VkDescriptorImageInfo = extern struct {
    sampler: u64,
    imageView: VkImageView,
    imageLayout: u32,
};

pub const VkWriteDescriptorSet = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    dstSet: VkDescriptorSet,
    dstBinding: u32,
    dstArrayElement: u32,
    descriptorCount: u32,
    descriptorType: u32,
    pImageInfo: ?*const anyopaque,
    pBufferInfo: ?[*]const VkDescriptorBufferInfo,
    pTexelBufferView: ?*const anyopaque,
};

pub const VkComputePipelineCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    stage: VkPipelineShaderStageCreateInfo,
    layout: VkPipelineLayout,
    basePipelineHandle: VkPipeline,
    basePipelineIndex: i32,
};

pub const VkBufferCopy = extern struct {
    srcOffset: VkDeviceSize,
    dstOffset: VkDeviceSize,
    size: VkDeviceSize,
};

pub const VkQueryPoolCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    queryType: u32,
    queryCount: u32,
    pipelineStatistics: VkFlags,
};

pub const VkExtent3D = extern struct {
    width: u32,
    height: u32,
    depth: u32,
};

pub const VkComponentMapping = extern struct {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
};

pub const VkImageSubresourceRange = extern struct {
    aspectMask: VkFlags,
    baseMipLevel: u32,
    levelCount: u32,
    baseArrayLayer: u32,
    layerCount: u32,
};

pub const VkImageViewCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    image: VkImage,
    viewType: u32,
    format: u32,
    components: VkComponentMapping,
    subresourceRange: VkImageSubresourceRange,
};

pub const VkImageSubresourceLayers = extern struct {
    aspectMask: VkFlags,
    mipLevel: u32,
    baseArrayLayer: u32,
    layerCount: u32,
};

pub const VkOffset3D = extern struct {
    x: i32,
    y: i32,
    z: i32,
};

pub const VkBufferImageCopy = extern struct {
    bufferOffset: VkDeviceSize,
    bufferRowLength: u32,
    bufferImageHeight: u32,
    imageSubresource: VkImageSubresourceLayers,
    imageOffset: VkOffset3D,
    imageExtent: VkExtent3D,
};

pub const VkImageMemoryBarrier = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    srcAccessMask: VkFlags,
    dstAccessMask: VkFlags,
    oldLayout: u32,
    newLayout: u32,
    srcQueueFamilyIndex: u32,
    dstQueueFamilyIndex: u32,
    image: VkImage,
    subresourceRange: VkImageSubresourceRange,
};

pub const VkQueueFamilyProperties = extern struct {
    queueFlags: VkFlags,
    queueCount: u32,
    timestampValidBits: u32,
    minImageTransferGranularity: VkExtent3D,
};

pub const VkMemoryType = extern struct {
    propertyFlags: VkFlags,
    heapIndex: u32,
};

pub const VkMemoryHeap = extern struct {
    size: VkDeviceSize,
    flags: VkFlags,
};

pub const VkPhysicalDeviceMemoryProperties = extern struct {
    memoryTypeCount: u32,
    memoryTypes: [32]VkMemoryType,
    memoryHeapCount: u32,
    memoryHeaps: [16]VkMemoryHeap,
};

// --- Extern Vulkan function declarations ---

pub extern fn vkCreateInstance(pCreateInfo: *const VkInstanceCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pInstance: *VkInstance) callconv(.c) VkResult;
pub extern fn vkDestroyInstance(instance: VkInstance, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkEnumeratePhysicalDevices(instance: VkInstance, pPhysicalDeviceCount: *u32, pPhysicalDevices: ?[*]VkPhysicalDevice) callconv(.c) VkResult;
pub extern fn vkGetPhysicalDeviceQueueFamilyProperties(physicalDevice: VkPhysicalDevice, pQueueFamilyPropertyCount: *u32, pQueueFamilyProperties: ?[*]VkQueueFamilyProperties) callconv(.c) void;
pub extern fn vkCreateDevice(physicalDevice: VkPhysicalDevice, pCreateInfo: *const VkDeviceCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pDevice: *VkDevice) callconv(.c) VkResult;
pub extern fn vkDestroyDevice(device: VkDevice, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkGetDeviceQueue(device: VkDevice, queueFamilyIndex: u32, queueIndex: u32, pQueue: *VkQueue) callconv(.c) void;
pub extern fn vkCreateCommandPool(device: VkDevice, pCreateInfo: *const VkCommandPoolCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pCommandPool: *VkCommandPool) callconv(.c) VkResult;
pub extern fn vkDestroyCommandPool(device: VkDevice, commandPool: VkCommandPool, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkAllocateCommandBuffers(device: VkDevice, pAllocateInfo: *const VkCommandBufferAllocateInfo, pCommandBuffers: [*]VkCommandBuffer) callconv(.c) VkResult;
pub extern fn vkResetCommandPool(device: VkDevice, commandPool: VkCommandPool, flags: VkFlags) callconv(.c) VkResult;
pub extern fn vkCreateFence(device: VkDevice, pCreateInfo: *const VkFenceCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pFence: *VkFence) callconv(.c) VkResult;
pub extern fn vkDestroyFence(device: VkDevice, fence: VkFence, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkResetFences(device: VkDevice, fenceCount: u32, pFences: [*]const VkFence) callconv(.c) VkResult;
pub extern fn vkWaitForFences(device: VkDevice, fenceCount: u32, pFences: [*]const VkFence, waitAll: VkBool32, timeout: u64) callconv(.c) VkResult;
pub extern fn vkQueueSubmit(queue: VkQueue, submitCount: u32, pSubmits: [*]const VkSubmitInfo, fence: VkFence) callconv(.c) VkResult;
pub extern fn vkQueueWaitIdle(queue: VkQueue) callconv(.c) VkResult;
pub extern fn vkBeginCommandBuffer(commandBuffer: VkCommandBuffer, pBeginInfo: *const VkCommandBufferBeginInfo) callconv(.c) VkResult;
pub extern fn vkEndCommandBuffer(commandBuffer: VkCommandBuffer) callconv(.c) VkResult;
pub extern fn vkResetCommandBuffer(commandBuffer: VkCommandBuffer, flags: VkFlags) callconv(.c) VkResult;
pub extern fn vkCmdBindPipeline(commandBuffer: VkCommandBuffer, pipelineBindPoint: i32, pipeline: VkPipeline) callconv(.c) void;
pub extern fn vkCmdDispatch(commandBuffer: VkCommandBuffer, groupCountX: u32, groupCountY: u32, groupCountZ: u32) callconv(.c) void;
pub extern fn vkCmdCopyBuffer(commandBuffer: VkCommandBuffer, srcBuffer: VkBuffer, dstBuffer: VkBuffer, regionCount: u32, pRegions: [*]const VkBufferCopy) callconv(.c) void;
pub extern fn vkCmdCopyBufferToImage(commandBuffer: VkCommandBuffer, srcBuffer: VkBuffer, dstImage: VkImage, dstImageLayout: u32, regionCount: u32, pRegions: [*]const VkBufferImageCopy) callconv(.c) void;
pub extern fn vkCmdPipelineBarrier(commandBuffer: VkCommandBuffer, srcStageMask: VkFlags, dstStageMask: VkFlags, dependencyFlags: VkFlags, memoryBarrierCount: u32, pMemoryBarriers: ?*const anyopaque, bufferMemoryBarrierCount: u32, pBufferMemoryBarriers: ?*const anyopaque, imageMemoryBarrierCount: u32, pImageMemoryBarriers: ?[*]const VkImageMemoryBarrier) callconv(.c) void;
pub extern fn vkCreateBuffer(device: VkDevice, pCreateInfo: *const VkBufferCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pBuffer: *VkBuffer) callconv(.c) VkResult;
pub extern fn vkDestroyBuffer(device: VkDevice, buffer: VkBuffer, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkGetBufferMemoryRequirements(device: VkDevice, buffer: VkBuffer, pMemoryRequirements: *VkMemoryRequirements) callconv(.c) void;
pub extern fn vkCreateImage(device: VkDevice, pCreateInfo: *const VkImageCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pImage: *VkImage) callconv(.c) VkResult;
pub extern fn vkDestroyImage(device: VkDevice, image: VkImage, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkGetImageMemoryRequirements(device: VkDevice, image: VkImage, pMemoryRequirements: *VkMemoryRequirements) callconv(.c) void;
pub extern fn vkBindImageMemory(device: VkDevice, image: VkImage, memory: VkDeviceMemory, memoryOffset: VkDeviceSize) callconv(.c) VkResult;
pub extern fn vkCreateImageView(device: VkDevice, pCreateInfo: *const VkImageViewCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pView: *VkImageView) callconv(.c) VkResult;
pub extern fn vkDestroyImageView(device: VkDevice, imageView: VkImageView, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkAllocateMemory(device: VkDevice, pAllocateInfo: *const VkMemoryAllocateInfo, pAllocator: ?*const VkAllocationCallbacks, pMemory: *VkDeviceMemory) callconv(.c) VkResult;
pub extern fn vkFreeMemory(device: VkDevice, memory: VkDeviceMemory, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkBindBufferMemory(device: VkDevice, buffer: VkBuffer, memory: VkDeviceMemory, memoryOffset: VkDeviceSize) callconv(.c) VkResult;
pub extern fn vkMapMemory(device: VkDevice, memory: VkDeviceMemory, offset: VkDeviceSize, size: VkDeviceSize, flags: VkFlags, ppData: *?*anyopaque) callconv(.c) VkResult;
pub extern fn vkUnmapMemory(device: VkDevice, memory: VkDeviceMemory) callconv(.c) void;
pub extern fn vkGetPhysicalDeviceMemoryProperties(physicalDevice: VkPhysicalDevice, pMemoryProperties: *VkPhysicalDeviceMemoryProperties) callconv(.c) void;
pub extern fn vkCreateShaderModule(device: VkDevice, pCreateInfo: *const VkShaderModuleCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pShaderModule: *VkShaderModule) callconv(.c) VkResult;
pub extern fn vkDestroyShaderModule(device: VkDevice, shaderModule: VkShaderModule, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateDescriptorSetLayout(device: VkDevice, pCreateInfo: *const VkDescriptorSetLayoutCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pSetLayout: *VkDescriptorSetLayout) callconv(.c) VkResult;
pub extern fn vkDestroyDescriptorSetLayout(device: VkDevice, descriptorSetLayout: VkDescriptorSetLayout, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateDescriptorPool(device: VkDevice, pCreateInfo: *const VkDescriptorPoolCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pDescriptorPool: *VkDescriptorPool) callconv(.c) VkResult;
pub extern fn vkDestroyDescriptorPool(device: VkDevice, descriptorPool: VkDescriptorPool, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkAllocateDescriptorSets(device: VkDevice, pAllocateInfo: *const VkDescriptorSetAllocateInfo, pDescriptorSets: [*]VkDescriptorSet) callconv(.c) VkResult;
pub extern fn vkUpdateDescriptorSets(device: VkDevice, descriptorWriteCount: u32, pDescriptorWrites: ?[*]const VkWriteDescriptorSet, descriptorCopyCount: u32, pDescriptorCopies: ?*const anyopaque) callconv(.c) void;
pub extern fn vkCreatePipelineLayout(device: VkDevice, pCreateInfo: *const VkPipelineLayoutCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pPipelineLayout: *VkPipelineLayout) callconv(.c) VkResult;
pub extern fn vkDestroyPipelineLayout(device: VkDevice, pipelineLayout: VkPipelineLayout, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateComputePipelines(device: VkDevice, pipelineCache: VkPipelineCache, createInfoCount: u32, pCreateInfos: [*]const VkComputePipelineCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pPipelines: [*]VkPipeline) callconv(.c) VkResult;
pub extern fn vkDestroyPipeline(device: VkDevice, pipeline: VkPipeline, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCmdBindDescriptorSets(commandBuffer: VkCommandBuffer, pipelineBindPoint: i32, layout: VkPipelineLayout, firstSet: u32, descriptorSetCount: u32, pDescriptorSets: ?[*]const VkDescriptorSet, dynamicOffsetCount: u32, pDynamicOffsets: ?[*]const u32) callconv(.c) void;
pub extern fn vkCreateQueryPool(device: VkDevice, pCreateInfo: *const VkQueryPoolCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pQueryPool: *VkQueryPool) callconv(.c) VkResult;
pub extern fn vkDestroyQueryPool(device: VkDevice, queryPool: VkQueryPool, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCmdWriteTimestamp(commandBuffer: VkCommandBuffer, pipelineStage: VkFlags, queryPool: VkQueryPool, query: u32) callconv(.c) void;
pub extern fn vkGetQueryPoolResults(device: VkDevice, queryPool: VkQueryPool, firstQuery: u32, queryCount: u32, dataSize: usize, pData: ?*anyopaque, stride: VkDeviceSize, flags: VkFlags) callconv(.c) VkResult;

// --- Error mapping ---

pub fn check_vk(result: VkResult) common_errors.BackendNativeError!void {
    if (result == VK_SUCCESS) return;
    return map_vk_result(result);
}

pub fn map_vk_result(result: VkResult) common_errors.BackendNativeError {
    return switch (result) {
        VK_ERROR_TOO_MANY_OBJECTS,
        VK_ERROR_FORMAT_NOT_SUPPORTED,
        VK_ERROR_FRAGMENTED_POOL,
        VK_ERROR_UNKNOWN,
        => error.UnsupportedFeature,
        else => error.InvalidState,
    };
}

const common_errors = @import("../common/errors.zig");
