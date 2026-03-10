const std = @import("std");
const model = @import("../../model.zig");
const backend_policy = @import("../backend_policy.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const doe_wgsl = @import("../../doe_wgsl/mod.zig");

// Vulkan upload path should follow device allocation limits, not an artificial
// 64MB runtime cap. Let allocation/driver failure surface explicitly.
const MAX_UPLOAD_BYTES: u64 = 0; // retained for parity with other backends
const MAX_UPLOAD_ZERO_FILL_BYTES: usize = 1024 * 1024;
const FAST_UPLOAD_BUFFER_MAX_BYTES: u64 = 1024 * 1024;
const DIRECT_UPLOAD_BUFFER_MAX_BYTES: u64 = 4 * 1024 * 1024 * 1024;
const DIRECT_UPLOAD_REUSE_SKIP_ZERO_FILL_MIN_BYTES: u64 = 4 * 1024 * 1024 * 1024;
const HOT_UPLOAD_POOL_CACHE_MAX_BYTES: u64 = 64 * 1024;
const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;
const WAIT_TIMEOUT_NS: u64 = std.math.maxInt(u64);
const DEFAULT_KERNEL_ROOT = "bench/kernels";
const MAIN_ENTRY: [*:0]const u8 = "main";
const APP_NAME: [*:0]const u8 = "doe-zig-runtime";
const ENGINE_NAME: [*:0]const u8 = "doe-vulkan-runtime";
const SPIRV_MAGIC: u32 = 0x07230203;

const VK_SUCCESS: i32 = 0;
const VK_TRUE: u32 = 1;
const VK_FALSE: u32 = 0;
const VK_API_VERSION_1_0: u32 = 0x00400000;

const VK_STRUCTURE_TYPE_APPLICATION_INFO: i32 = 0;
const VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO: i32 = 1;
const VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO: i32 = 2;
const VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO: i32 = 3;
const VK_STRUCTURE_TYPE_SUBMIT_INFO: i32 = 4;
const VK_STRUCTURE_TYPE_FENCE_CREATE_INFO: i32 = 8;
const VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO: i32 = 11;
const VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO: i32 = 12;
const VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO: i32 = 14;
const VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO: i32 = 15;
const VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO: i32 = 16;
const VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO: i32 = 17;
const VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO: i32 = 18;
const VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO: i32 = 28;
const VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO: i32 = 30;
const VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO: i32 = 32;
const VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO: i32 = 33;
const VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO: i32 = 34;
const VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET: i32 = 35;
const VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO: i32 = 39;
const VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO: i32 = 40;
const VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO: i32 = 42;
const VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER: i32 = 45;

const VK_QUEUE_GRAPHICS_BIT: u32 = 0x00000001;
const VK_QUEUE_COMPUTE_BIT: u32 = 0x00000002;
const VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT: u32 = 0x00000002;
const VK_COMMAND_BUFFER_LEVEL_PRIMARY: i32 = 0;
const VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT: u32 = 0x00000001;
const VK_PIPELINE_BIND_POINT_COMPUTE: i32 = 1;
const VK_SHADER_STAGE_COMPUTE_BIT: u32 = 0x00000020;
const VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT: u32 = 0x00000001;
const VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT: u32 = 0x00000800;
const VK_PIPELINE_STAGE_TRANSFER_BIT: u32 = 0x00001000;
const VK_QUERY_TYPE_TIMESTAMP: u32 = 2;
const VK_QUERY_RESULT_64_BIT: u32 = 0x00000001;
const VK_QUERY_RESULT_WAIT_BIT: u32 = 0x00000002;

const VK_BUFFER_USAGE_TRANSFER_SRC_BIT: u32 = 0x00000001;
const VK_BUFFER_USAGE_TRANSFER_DST_BIT: u32 = 0x00000002;
const VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT: u32 = 0x00000010;
const VK_BUFFER_USAGE_STORAGE_BUFFER_BIT: u32 = 0x00000020;
const VK_IMAGE_USAGE_TRANSFER_SRC_BIT: u32 = 0x00000001;
const VK_IMAGE_USAGE_TRANSFER_DST_BIT: u32 = 0x00000002;
const VK_IMAGE_USAGE_SAMPLED_BIT: u32 = 0x00000004;
const VK_IMAGE_USAGE_STORAGE_BIT: u32 = 0x00000008;

const VK_SHARING_MODE_EXCLUSIVE: i32 = 0;
const VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT: u32 = 0x00000001;
const VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT: u32 = 0x00000002;
const VK_MEMORY_PROPERTY_HOST_COHERENT_BIT: u32 = 0x00000004;
const VK_ACCESS_SHADER_READ_BIT: u32 = 0x00000020;
const VK_ACCESS_SHADER_WRITE_BIT: u32 = 0x00000040;
const VK_ACCESS_TRANSFER_WRITE_BIT: u32 = 0x00001000;
const VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE: u32 = 2;
const VK_DESCRIPTOR_TYPE_STORAGE_IMAGE: u32 = 3;
const VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER: u32 = 6;
const VK_DESCRIPTOR_TYPE_STORAGE_BUFFER: u32 = 7;
const VK_WHOLE_SIZE: u64 = std.math.maxInt(u64);
const MAX_DESCRIPTOR_SETS: usize = 4;
const MAX_DESCRIPTOR_SETS_U32: u32 = 4;
const VK_IMAGE_TYPE_2D: u32 = 1;
const VK_IMAGE_VIEW_TYPE_2D: u32 = 1;
const VK_IMAGE_TILING_OPTIMAL: u32 = 0;
const VK_IMAGE_LAYOUT_UNDEFINED: u32 = 0;
const VK_IMAGE_LAYOUT_GENERAL: u32 = 1;
const VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL: u32 = 7;
const VK_IMAGE_ASPECT_COLOR_BIT: u32 = 0x00000001;
const VK_SAMPLE_COUNT_1_BIT: u32 = 0x00000001;
const VK_COMPONENT_SWIZZLE_IDENTITY: u32 = 0;
const VK_FORMAT_R8G8B8A8_UNORM: u32 = 37;
const DEFAULT_RUNTIME_TEXTURE_USAGE: model.WGPUFlags =
    model.WGPUTextureUsage_TextureBinding |
    model.WGPUTextureUsage_StorageBinding |
    model.WGPUTextureUsage_CopyDst;
const REQUIRED_TEXTURE_UPLOAD_USAGE: model.WGPUFlags = model.WGPUTextureUsage_CopyDst;

const VkBool32 = u32;
const VkFlags = u32;
const VkDeviceSize = u64;
const VkStructureType = i32;
const VkResult = i32;
const VkInstance = ?*opaque {};
const VkPhysicalDevice = ?*opaque {};
const VkDevice = ?*opaque {};
const VkQueue = ?*opaque {};
const VkCommandBuffer = ?*opaque {};
const VkPipelineCache = u64;
const VkCommandPool = u64;
const VkFence = u64;
const VkBuffer = u64;
const VkDeviceMemory = u64;
const VkShaderModule = u64;
const VkPipelineLayout = u64;
const VkPipeline = u64;
const VkQueryPool = u64;
const VkDescriptorSetLayout = u64;
const VkDescriptorPool = u64;
const VkDescriptorSet = u64;
const VkImage = u64;
const VkImageView = u64;
const VK_NULL_U64: u64 = 0;

const VkAllocationCallbacks = opaque {};

const VkApplicationInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    pApplicationName: ?[*:0]const u8,
    applicationVersion: u32,
    pEngineName: ?[*:0]const u8,
    engineVersion: u32,
    apiVersion: u32,
};

const VkInstanceCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    pApplicationInfo: ?*const VkApplicationInfo,
    enabledLayerCount: u32,
    ppEnabledLayerNames: ?[*]const [*:0]const u8,
    enabledExtensionCount: u32,
    ppEnabledExtensionNames: ?[*]const [*:0]const u8,
};

const VkDeviceQueueCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    queueFamilyIndex: u32,
    queueCount: u32,
    pQueuePriorities: [*]const f32,
};

const VkDeviceCreateInfo = extern struct {
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

const VkCommandPoolCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    queueFamilyIndex: u32,
};

const VkCommandBufferAllocateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    commandPool: VkCommandPool,
    level: i32,
    commandBufferCount: u32,
};

const VkFenceCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
};

const VkBufferCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    size: VkDeviceSize,
    usage: VkFlags,
    sharingMode: i32,
    queueFamilyIndexCount: u32,
    pQueueFamilyIndices: ?[*]const u32,
};

const VkImageCreateInfo = extern struct {
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

const VkMemoryAllocateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    allocationSize: VkDeviceSize,
    memoryTypeIndex: u32,
};

const VkMemoryRequirements = extern struct {
    size: VkDeviceSize,
    alignment: VkDeviceSize,
    memoryTypeBits: u32,
};

const VkCommandBufferBeginInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    pInheritanceInfo: ?*const anyopaque,
};

const VkSubmitInfo = extern struct {
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

const VkShaderModuleCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    codeSize: usize,
    pCode: [*]const u32,
};

const VkPipelineLayoutCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    setLayoutCount: u32,
    pSetLayouts: ?[*]const u64,
    pushConstantRangeCount: u32,
    pPushConstantRanges: ?*const anyopaque,
};

const VkPipelineShaderStageCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    stage: VkFlags,
    module: VkShaderModule,
    pName: ?[*:0]const u8,
    pSpecializationInfo: ?*const anyopaque,
};

const VkDescriptorSetLayoutBinding = extern struct {
    binding: u32,
    descriptorType: u32,
    descriptorCount: u32,
    stageFlags: VkFlags,
    pImmutableSamplers: ?*const anyopaque,
};

const VkDescriptorSetLayoutCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    bindingCount: u32,
    pBindings: ?[*]const VkDescriptorSetLayoutBinding,
};

const VkDescriptorPoolSize = extern struct {
    type: u32,
    descriptorCount: u32,
};

const VkDescriptorPoolCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    maxSets: u32,
    poolSizeCount: u32,
    pPoolSizes: ?[*]const VkDescriptorPoolSize,
};

const VkDescriptorSetAllocateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    descriptorPool: VkDescriptorPool,
    descriptorSetCount: u32,
    pSetLayouts: [*]const VkDescriptorSetLayout,
};

const VkDescriptorBufferInfo = extern struct {
    buffer: VkBuffer,
    offset: VkDeviceSize,
    range: VkDeviceSize,
};

const VkDescriptorImageInfo = extern struct {
    sampler: u64,
    imageView: VkImageView,
    imageLayout: u32,
};

const VkWriteDescriptorSet = extern struct {
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

const VkComputePipelineCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    stage: VkPipelineShaderStageCreateInfo,
    layout: VkPipelineLayout,
    basePipelineHandle: VkPipeline,
    basePipelineIndex: i32,
};

const VkBufferCopy = extern struct {
    srcOffset: VkDeviceSize,
    dstOffset: VkDeviceSize,
    size: VkDeviceSize,
};

const VkQueryPoolCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    queryType: u32,
    queryCount: u32,
    pipelineStatistics: VkFlags,
};

const VkExtent3D = extern struct {
    width: u32,
    height: u32,
    depth: u32,
};

const VkComponentMapping = extern struct {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
};

const VkImageSubresourceRange = extern struct {
    aspectMask: VkFlags,
    baseMipLevel: u32,
    levelCount: u32,
    baseArrayLayer: u32,
    layerCount: u32,
};

const VkImageViewCreateInfo = extern struct {
    sType: VkStructureType,
    pNext: ?*const anyopaque,
    flags: VkFlags,
    image: VkImage,
    viewType: u32,
    format: u32,
    components: VkComponentMapping,
    subresourceRange: VkImageSubresourceRange,
};

const VkImageSubresourceLayers = extern struct {
    aspectMask: VkFlags,
    mipLevel: u32,
    baseArrayLayer: u32,
    layerCount: u32,
};

const VkOffset3D = extern struct {
    x: i32,
    y: i32,
    z: i32,
};

const VkBufferImageCopy = extern struct {
    bufferOffset: VkDeviceSize,
    bufferRowLength: u32,
    bufferImageHeight: u32,
    imageSubresource: VkImageSubresourceLayers,
    imageOffset: VkOffset3D,
    imageExtent: VkExtent3D,
};

const VkImageMemoryBarrier = extern struct {
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

const VkQueueFamilyProperties = extern struct {
    queueFlags: VkFlags,
    queueCount: u32,
    timestampValidBits: u32,
    minImageTransferGranularity: VkExtent3D,
};

const VkMemoryType = extern struct {
    propertyFlags: VkFlags,
    heapIndex: u32,
};

const VkMemoryHeap = extern struct {
    size: VkDeviceSize,
    flags: VkFlags,
};

const VkPhysicalDeviceMemoryProperties = extern struct {
    memoryTypeCount: u32,
    memoryTypes: [32]VkMemoryType,
    memoryHeapCount: u32,
    memoryHeaps: [16]VkMemoryHeap,
};

extern fn vkCreateInstance(pCreateInfo: *const VkInstanceCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pInstance: *VkInstance) callconv(.c) VkResult;
extern fn vkDestroyInstance(instance: VkInstance, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkEnumeratePhysicalDevices(instance: VkInstance, pPhysicalDeviceCount: *u32, pPhysicalDevices: ?[*]VkPhysicalDevice) callconv(.c) VkResult;
extern fn vkGetPhysicalDeviceQueueFamilyProperties(physicalDevice: VkPhysicalDevice, pQueueFamilyPropertyCount: *u32, pQueueFamilyProperties: ?[*]VkQueueFamilyProperties) callconv(.c) void;
extern fn vkCreateDevice(physicalDevice: VkPhysicalDevice, pCreateInfo: *const VkDeviceCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pDevice: *VkDevice) callconv(.c) VkResult;
extern fn vkDestroyDevice(device: VkDevice, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkGetDeviceQueue(device: VkDevice, queueFamilyIndex: u32, queueIndex: u32, pQueue: *VkQueue) callconv(.c) void;
extern fn vkCreateCommandPool(device: VkDevice, pCreateInfo: *const VkCommandPoolCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pCommandPool: *VkCommandPool) callconv(.c) VkResult;
extern fn vkDestroyCommandPool(device: VkDevice, commandPool: VkCommandPool, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkAllocateCommandBuffers(device: VkDevice, pAllocateInfo: *const VkCommandBufferAllocateInfo, pCommandBuffers: [*]VkCommandBuffer) callconv(.c) VkResult;
extern fn vkResetCommandPool(device: VkDevice, commandPool: VkCommandPool, flags: VkFlags) callconv(.c) VkResult;
extern fn vkCreateFence(device: VkDevice, pCreateInfo: *const VkFenceCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pFence: *VkFence) callconv(.c) VkResult;
extern fn vkDestroyFence(device: VkDevice, fence: VkFence, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkResetFences(device: VkDevice, fenceCount: u32, pFences: [*]const VkFence) callconv(.c) VkResult;
extern fn vkWaitForFences(device: VkDevice, fenceCount: u32, pFences: [*]const VkFence, waitAll: VkBool32, timeout: u64) callconv(.c) VkResult;
extern fn vkQueueSubmit(queue: VkQueue, submitCount: u32, pSubmits: [*]const VkSubmitInfo, fence: VkFence) callconv(.c) VkResult;
extern fn vkQueueWaitIdle(queue: VkQueue) callconv(.c) VkResult;
extern fn vkBeginCommandBuffer(commandBuffer: VkCommandBuffer, pBeginInfo: *const VkCommandBufferBeginInfo) callconv(.c) VkResult;
extern fn vkEndCommandBuffer(commandBuffer: VkCommandBuffer) callconv(.c) VkResult;
extern fn vkResetCommandBuffer(commandBuffer: VkCommandBuffer, flags: VkFlags) callconv(.c) VkResult;
extern fn vkCmdBindPipeline(commandBuffer: VkCommandBuffer, pipelineBindPoint: i32, pipeline: VkPipeline) callconv(.c) void;
extern fn vkCmdDispatch(commandBuffer: VkCommandBuffer, groupCountX: u32, groupCountY: u32, groupCountZ: u32) callconv(.c) void;
extern fn vkCmdCopyBuffer(commandBuffer: VkCommandBuffer, srcBuffer: VkBuffer, dstBuffer: VkBuffer, regionCount: u32, pRegions: [*]const VkBufferCopy) callconv(.c) void;
extern fn vkCmdCopyBufferToImage(commandBuffer: VkCommandBuffer, srcBuffer: VkBuffer, dstImage: VkImage, dstImageLayout: u32, regionCount: u32, pRegions: [*]const VkBufferImageCopy) callconv(.c) void;
extern fn vkCmdPipelineBarrier(commandBuffer: VkCommandBuffer, srcStageMask: VkFlags, dstStageMask: VkFlags, dependencyFlags: VkFlags, memoryBarrierCount: u32, pMemoryBarriers: ?*const anyopaque, bufferMemoryBarrierCount: u32, pBufferMemoryBarriers: ?*const anyopaque, imageMemoryBarrierCount: u32, pImageMemoryBarriers: ?[*]const VkImageMemoryBarrier) callconv(.c) void;
extern fn vkCreateBuffer(device: VkDevice, pCreateInfo: *const VkBufferCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pBuffer: *VkBuffer) callconv(.c) VkResult;
extern fn vkDestroyBuffer(device: VkDevice, buffer: VkBuffer, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkGetBufferMemoryRequirements(device: VkDevice, buffer: VkBuffer, pMemoryRequirements: *VkMemoryRequirements) callconv(.c) void;
extern fn vkCreateImage(device: VkDevice, pCreateInfo: *const VkImageCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pImage: *VkImage) callconv(.c) VkResult;
extern fn vkDestroyImage(device: VkDevice, image: VkImage, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkGetImageMemoryRequirements(device: VkDevice, image: VkImage, pMemoryRequirements: *VkMemoryRequirements) callconv(.c) void;
extern fn vkBindImageMemory(device: VkDevice, image: VkImage, memory: VkDeviceMemory, memoryOffset: VkDeviceSize) callconv(.c) VkResult;
extern fn vkCreateImageView(device: VkDevice, pCreateInfo: *const VkImageViewCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pView: *VkImageView) callconv(.c) VkResult;
extern fn vkDestroyImageView(device: VkDevice, imageView: VkImageView, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkAllocateMemory(device: VkDevice, pAllocateInfo: *const VkMemoryAllocateInfo, pAllocator: ?*const VkAllocationCallbacks, pMemory: *VkDeviceMemory) callconv(.c) VkResult;
extern fn vkFreeMemory(device: VkDevice, memory: VkDeviceMemory, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkBindBufferMemory(device: VkDevice, buffer: VkBuffer, memory: VkDeviceMemory, memoryOffset: VkDeviceSize) callconv(.c) VkResult;
extern fn vkMapMemory(device: VkDevice, memory: VkDeviceMemory, offset: VkDeviceSize, size: VkDeviceSize, flags: VkFlags, ppData: *?*anyopaque) callconv(.c) VkResult;
extern fn vkUnmapMemory(device: VkDevice, memory: VkDeviceMemory) callconv(.c) void;
extern fn vkGetPhysicalDeviceMemoryProperties(physicalDevice: VkPhysicalDevice, pMemoryProperties: *VkPhysicalDeviceMemoryProperties) callconv(.c) void;
extern fn vkCreateShaderModule(device: VkDevice, pCreateInfo: *const VkShaderModuleCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pShaderModule: *VkShaderModule) callconv(.c) VkResult;
extern fn vkDestroyShaderModule(device: VkDevice, shaderModule: VkShaderModule, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkCreateDescriptorSetLayout(device: VkDevice, pCreateInfo: *const VkDescriptorSetLayoutCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pSetLayout: *VkDescriptorSetLayout) callconv(.c) VkResult;
extern fn vkDestroyDescriptorSetLayout(device: VkDevice, descriptorSetLayout: VkDescriptorSetLayout, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkCreateDescriptorPool(device: VkDevice, pCreateInfo: *const VkDescriptorPoolCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pDescriptorPool: *VkDescriptorPool) callconv(.c) VkResult;
extern fn vkDestroyDescriptorPool(device: VkDevice, descriptorPool: VkDescriptorPool, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkAllocateDescriptorSets(device: VkDevice, pAllocateInfo: *const VkDescriptorSetAllocateInfo, pDescriptorSets: [*]VkDescriptorSet) callconv(.c) VkResult;
extern fn vkUpdateDescriptorSets(device: VkDevice, descriptorWriteCount: u32, pDescriptorWrites: ?[*]const VkWriteDescriptorSet, descriptorCopyCount: u32, pDescriptorCopies: ?*const anyopaque) callconv(.c) void;
extern fn vkCreatePipelineLayout(device: VkDevice, pCreateInfo: *const VkPipelineLayoutCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pPipelineLayout: *VkPipelineLayout) callconv(.c) VkResult;
extern fn vkDestroyPipelineLayout(device: VkDevice, pipelineLayout: VkPipelineLayout, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkCreateComputePipelines(device: VkDevice, pipelineCache: VkPipelineCache, createInfoCount: u32, pCreateInfos: [*]const VkComputePipelineCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pPipelines: [*]VkPipeline) callconv(.c) VkResult;
extern fn vkDestroyPipeline(device: VkDevice, pipeline: VkPipeline, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkCmdBindDescriptorSets(commandBuffer: VkCommandBuffer, pipelineBindPoint: i32, layout: VkPipelineLayout, firstSet: u32, descriptorSetCount: u32, pDescriptorSets: ?[*]const VkDescriptorSet, dynamicOffsetCount: u32, pDynamicOffsets: ?[*]const u32) callconv(.c) void;
extern fn vkCreateQueryPool(device: VkDevice, pCreateInfo: *const VkQueryPoolCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pQueryPool: *VkQueryPool) callconv(.c) VkResult;
extern fn vkDestroyQueryPool(device: VkDevice, queryPool: VkQueryPool, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkCmdWriteTimestamp(commandBuffer: VkCommandBuffer, pipelineStage: VkFlags, queryPool: VkQueryPool, query: u32) callconv(.c) void;
extern fn vkGetQueryPoolResults(device: VkDevice, queryPool: VkQueryPool, firstQuery: u32, queryCount: u32, dataSize: usize, pData: ?*anyopaque, stride: VkDeviceSize, flags: VkFlags) callconv(.c) VkResult;

pub const DispatchMetrics = struct {
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    gpu_timestamp_ns: u64 = 0,
    gpu_timestamp_attempted: bool = false,
    gpu_timestamp_valid: bool = false,
};

const PendingUpload = struct {
    src_buffer: VkBuffer,
    src_memory: VkDeviceMemory,
    dst_buffer: VkBuffer,
    dst_memory: VkDeviceMemory,
    byte_count: u64 = 0,
};

const VkPoolEntry = struct {
    buffer: VkBuffer,
    memory: VkDeviceMemory,
    mapped: ?*anyopaque = null,
};

const ComputeBuffer = struct {
    buffer: VkBuffer,
    memory: VkDeviceMemory,
    mapped: ?*anyopaque,
    size: u64,
};

const TextureResource = struct {
    image: VkImage,
    memory: VkDeviceMemory,
    view: VkImageView,
    width: u32,
    height: u32,
    mip_levels: u32,
    format: model.WGPUTextureFormat,
    usage: model.WGPUFlags,
    layout: u32,
};

const DescriptorInfoKind = enum {
    buffer,
    image,
};

const PendingDescriptorWrite = struct {
    set_index: u32,
    binding: u32,
    descriptor_type: u32,
    kind: DescriptorInfoKind,
    info_index: usize,
};

const UploadPathKind = enum {
    fast_mapped,
    direct_mapped,
    staged_copy,
};

const MAX_POOL_ENTRIES_PER_SIZE: usize = 8;

const QueueFamilySelection = struct {
    index: u32,
    supports_graphics: bool,
    timestamp_valid_bits: u32,
    queue_count: u32,
};

const PhysicalDeviceSelection = struct {
    index: u32,
    queue: QueueFamilySelection,
    score: u64,
};

const HeadlessSurface = struct {
    configured: bool = false,
    acquired: bool = false,
    width: u32 = 0,
    height: u32 = 0,
    format: model.WGPUTextureFormat = model.WGPUTextureFormat_RGBA8Unorm,
    usage: model.WGPUFlags = model.WGPUTextureUsage_RenderAttachment,
    alpha_mode: u32 = 0x00000001,
    present_mode: u32 = 0x00000002,
    desired_maximum_frame_latency: u32 = 2,
};

pub const NativeVulkanRuntime = struct {
    allocator: std.mem.Allocator,
    kernel_root: ?[]const u8,

    instance: VkInstance = null,
    physical_device: VkPhysicalDevice = null,
    device: VkDevice = null,
    queue: VkQueue = null,

    adapter_ordinal_value: ?u32 = null,
    queue_family_index: u32 = 0,
    queue_family_index_value_cache: ?u32 = null,
    present_capable_value: ?bool = null,
    timestamp_query_supported_value: bool = false,
    command_pool: VkCommandPool = VK_NULL_U64,
    primary_command_buffer: VkCommandBuffer = null,
    fence: VkFence = VK_NULL_U64,

    shader_module: VkShaderModule = VK_NULL_U64,
    pipeline_layout: VkPipelineLayout = VK_NULL_U64,
    pipeline: VkPipeline = VK_NULL_U64,
    descriptor_pool: VkDescriptorPool = VK_NULL_U64,
    descriptor_set_layouts: [MAX_DESCRIPTOR_SETS]VkDescriptorSetLayout = [_]VkDescriptorSetLayout{VK_NULL_U64} ** MAX_DESCRIPTOR_SETS,
    descriptor_sets: [MAX_DESCRIPTOR_SETS]VkDescriptorSet = [_]VkDescriptorSet{VK_NULL_U64} ** MAX_DESCRIPTOR_SETS,
    descriptor_set_count: u32 = 0,
    current_pipeline_hash: u64 = 0,
    current_layout_hash: u64 = 0,
    current_entry_point_owned: ?[:0]u8 = null,
    fast_upload_buffer: VkBuffer = VK_NULL_U64,
    fast_upload_memory: VkDeviceMemory = VK_NULL_U64,
    fast_upload_capacity: u64 = 0,
    fast_upload_mapped: ?*anyopaque = null,

    pending_uploads: std.ArrayListUnmanaged(PendingUpload) = .{},
    surfaces: std.AutoHashMapUnmanaged(u64, HeadlessSurface) = .{},

    src_pool: std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry)) = .{},
    dst_pool: std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry)) = .{},
    direct_upload_pool: std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry)) = .{},
    hot_src_pool_entry: ?VkPoolEntry = null,
    hot_src_pool_size: u64 = 0,
    hot_dst_pool_entry: ?VkPoolEntry = null,
    hot_dst_pool_size: u64 = 0,
    compute_buffers: std.AutoHashMapUnmanaged(u64, ComputeBuffer) = .{},
    textures: std.AutoHashMapUnmanaged(u64, TextureResource) = .{},

    has_instance: bool = false,
    has_device: bool = false,
    has_command_pool: bool = false,
    has_primary_command_buffer: bool = false,
    has_fence: bool = false,
    has_shader_module: bool = false,
    has_pipeline_layout: bool = false,
    has_pipeline: bool = false,
    has_descriptor_pool: bool = false,
    has_deferred_submissions: bool = false,
    upload_recording_active: bool = false,

    pub fn init(allocator: std.mem.Allocator, kernel_root: ?[]const u8) !NativeVulkanRuntime {
        var self = NativeVulkanRuntime{ .allocator = allocator, .kernel_root = kernel_root };
        errdefer self.deinit();
        try self.bootstrap();
        return self;
    }

    pub fn deinit(self: *NativeVulkanRuntime) void {
        _ = self.flush_queue() catch {};
        self.release_pending_uploads();
        self.pending_uploads.deinit(self.allocator);
        self.surfaces.deinit(self.allocator);
        release_pool_entry(self.device, self.hot_src_pool_entry);
        release_pool_entry(self.device, self.hot_dst_pool_entry);
        self.hot_src_pool_entry = null;
        self.hot_dst_pool_entry = null;
        vk_release_pool(&self.src_pool, self.allocator, self.device);
        vk_release_pool(&self.dst_pool, self.allocator, self.device);
        vk_release_pool(&self.direct_upload_pool, self.allocator, self.device);
        self.release_fast_upload_buffer();
        self.destroy_pipeline_objects();
        self.destroy_descriptor_state();
        self.release_compute_buffers();
        self.release_textures();
        if (self.has_fence) {
            vkDestroyFence(self.device, self.fence, null);
            self.has_fence = false;
            self.fence = VK_NULL_U64;
        }
        if (self.has_command_pool) {
            vkDestroyCommandPool(self.device, self.command_pool, null);
            self.has_command_pool = false;
            self.has_primary_command_buffer = false;
            self.command_pool = VK_NULL_U64;
            self.primary_command_buffer = null;
        }
        if (self.has_device) {
            vkDestroyDevice(self.device, null);
            self.has_device = false;
            self.device = null;
            self.queue = null;
        }
        if (self.has_instance) {
            vkDestroyInstance(self.instance, null);
            self.has_instance = false;
            self.instance = null;
            self.physical_device = null;
        }
    }

    pub fn load_kernel_source(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
        if (kernel_name.len == 0) return error.InvalidArgument;
        const path = try self.resolve_kernel_path(allocator, kernel_name);
        defer allocator.free(path);
        return std.fs.cwd().readFileAlloc(allocator, path, MAX_KERNEL_SOURCE_BYTES) catch error.ShaderCompileFailed;
    }

    pub fn load_kernel_spirv(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
        if (kernel_name.len == 0) return error.InvalidArgument;
        const path = self.resolve_kernel_spirv_path(allocator, kernel_name) catch |err| switch (err) {
            error.UnsupportedFeature => return try self.compile_kernel_wgsl_to_spirv(allocator, kernel_name),
            else => return err,
        };
        defer allocator.free(path);

        const bytes = std.fs.cwd().readFileAlloc(allocator, path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
        defer allocator.free(bytes);
        return try words_from_spirv_bytes(allocator, bytes);
    }

    fn compile_kernel_wgsl_to_spirv(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
        const source_path = try self.resolve_kernel_path(allocator, kernel_name);
        defer allocator.free(source_path);
        if (!std.mem.endsWith(u8, source_path, ".wgsl")) return error.UnsupportedFeature;

        const wgsl = std.fs.cwd().readFileAlloc(allocator, source_path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
        defer allocator.free(wgsl);

        var spirv_buf = try allocator.alloc(u8, doe_wgsl.MAX_SPIRV_OUTPUT);
        defer allocator.free(spirv_buf);
        const spirv_len = doe_wgsl.translateToSpirv(allocator, wgsl, spirv_buf) catch return error.ShaderCompileFailed;
        return try words_from_spirv_bytes(allocator, spirv_buf[0..spirv_len]);
    }

    pub fn set_compute_shader_spirv(
        self: *NativeVulkanRuntime,
        words: []const u32,
        entry_point: ?[]const u8,
        bindings: ?[]const model.KernelBinding,
        initialize_buffers_on_create: bool,
    ) !void {
        if (words.len == 0 or words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
        const pipeline_hash = compute_pipeline_hash(words, entry_point, bindings);
        if (!self.has_pipeline or pipeline_hash != self.current_pipeline_hash) {
            try self.build_pipeline_for_words(words, pipeline_hash, entry_point, bindings);
        }
        try self.prepare_descriptor_sets(bindings, initialize_buffers_on_create);
    }

    pub fn rebuild_compute_shader_spirv(self: *NativeVulkanRuntime, words: []const u32) !void {
        if (words.len == 0 or words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
        const hash = std.hash.Wyhash.hash(0, std.mem.sliceAsBytes(words));
        try self.build_pipeline_for_words(words, hash +% 1, null, null);
    }

    pub fn upload_bytes(
        self: *NativeVulkanRuntime,
        bytes: u64,
        mode: webgpu.UploadBufferUsageMode,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !void {
        if (bytes == 0) return error.InvalidArgument;

        switch (classify_upload_path(upload_path_policy, mode, bytes)) {
            .fast_mapped => {
                try self.ensure_fast_upload_buffer(bytes);
                if (self.fast_upload_mapped) |raw| {
                    const fill_len = bounded_upload_fill_len(bytes);
                    @memset(@as([*]u8, @ptrCast(raw))[0..fill_len], 0);
                }
                return;
            },
            .direct_mapped => {
                if (try self.try_direct_upload(bytes, VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT)) {
                    return;
                }
            },
            .staged_copy => {},
        }

        const dst_usage: u32 = switch (mode) {
            .copy_dst_copy_src => VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,
            .copy_dst => VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,
        };

        const upload = try self.record_upload_copy(bytes, dst_usage);
        errdefer self.release_upload(upload);
        try self.pending_uploads.append(self.allocator, upload);
        self.has_deferred_submissions = true;
    }

    pub fn barrier(self: *NativeVulkanRuntime, queue_wait_mode: webgpu.QueueWaitMode) !u64 {
        const start_ns = common_timing.now_ns();
        switch (queue_wait_mode) {
            .process_events, .wait_any => {
                if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
                    _ = try self.flush_queue();
                }
            },
        }
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn run_dispatch(
        self: *NativeVulkanRuntime,
        x: u32,
        y: u32,
        z: u32,
        queue_sync_mode: webgpu.QueueSyncMode,
        queue_wait_mode: webgpu.QueueWaitMode,
        gpu_timestamp_mode: webgpu.GpuTimestampMode,
    ) !DispatchMetrics {
        if (x == 0 or y == 0 or z == 0) return error.InvalidArgument;
        if (!self.has_pipeline) {
            return error.Unsupported;
        }

        const encode_start = common_timing.now_ns();
        var command_buffer: VkCommandBuffer = null;

        if (queue_sync_mode == .per_command) {
            if (self.has_deferred_submissions) _ = try self.flush_queue();
            try check_vk(vkResetCommandPool(self.device, self.command_pool, 0));
            command_buffer = self.primary_command_buffer;
        } else {
            var alloc_info = VkCommandBufferAllocateInfo{
                .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
                .pNext = null,
                .commandPool = self.command_pool,
                .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
                .commandBufferCount = 1,
            };
            try check_vk(vkAllocateCommandBuffers(self.device, &alloc_info, @ptrCast(&command_buffer)));
        }

        var begin_info = VkCommandBufferBeginInfo{
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try check_vk(vkBeginCommandBuffer(command_buffer, &begin_info));
        vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_COMPUTE, self.pipeline);
        self.bind_descriptor_sets(command_buffer);
        vkCmdDispatch(command_buffer, x, y, z);
        try check_vk(vkEndCommandBuffer(command_buffer));

        const encode_end = common_timing.now_ns();
        const encode_ns = common_timing.ns_delta(encode_end, encode_start);

        var submit_info = VkSubmitInfo{
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .pNext = null,
            .waitSemaphoreCount = 0,
            .pWaitSemaphores = null,
            .pWaitDstStageMask = null,
            .commandBufferCount = 1,
            .pCommandBuffers = @ptrCast(&command_buffer),
            .signalSemaphoreCount = 0,
            .pSignalSemaphores = null,
        };

        const submit_start = common_timing.now_ns();
        if (queue_sync_mode == .per_command) {
            try check_vk(vkResetFences(self.device, 1, @ptrCast(&self.fence)));
            try check_vk(vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
            const wait_all: VkBool32 = if (queue_wait_mode == .wait_any) VK_FALSE else VK_TRUE;
            try check_vk(vkWaitForFences(self.device, 1, @ptrCast(&self.fence), wait_all, WAIT_TIMEOUT_NS));
        } else {
            try check_vk(vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), VK_NULL_U64));
            self.has_deferred_submissions = true;
        }
        const submit_end = common_timing.now_ns();

        var gpu_timestamp_ns: u64 = 0;
        var gpu_timestamp_attempted = false;
        var gpu_timestamp_valid = false;
        if (gpu_timestamp_mode != .off) {
            if (queue_sync_mode != .per_command) {
                if (gpu_timestamp_mode == .require) return error.TimingPolicyMismatch;
            } else if (self.timestamp_query_supported()) {
                gpu_timestamp_attempted = true;
                gpu_timestamp_ns = try self.collect_dispatch_gpu_timestamp();
                gpu_timestamp_valid = gpu_timestamp_ns > 0;
                if (gpu_timestamp_mode == .require and !gpu_timestamp_valid) return error.TimingPolicyMismatch;
            } else if (gpu_timestamp_mode == .require) {
                return error.TimingPolicyMismatch;
            }
        }
        return .{
            .encode_ns = encode_ns,
            .submit_wait_ns = common_timing.ns_delta(submit_end, submit_start),
            .gpu_timestamp_ns = gpu_timestamp_ns,
            .gpu_timestamp_attempted = gpu_timestamp_attempted,
            .gpu_timestamp_valid = gpu_timestamp_valid,
        };
    }

    pub fn flush_queue(self: *NativeVulkanRuntime) !u64 {
        if (!self.has_device) return 0;
        const start_ns = common_timing.now_ns();
        if (self.pending_uploads.items.len > 0) {
            try self.finish_pending_upload_recording();
            var upload_command_buffer = self.primary_command_buffer;
            var submit = VkSubmitInfo{
                .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
                .pNext = null,
                .waitSemaphoreCount = 0,
                .pWaitSemaphores = null,
                .pWaitDstStageMask = null,
                .commandBufferCount = 1,
                .pCommandBuffers = @ptrCast(&upload_command_buffer),
                .signalSemaphoreCount = 0,
                .pSignalSemaphores = null,
            };
            try check_vk(vkQueueSubmit(self.queue, 1, @ptrCast(&submit), VK_NULL_U64));
            self.has_deferred_submissions = true;
        }
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            try check_vk(vkQueueWaitIdle(self.queue));
            try check_vk(vkResetCommandBuffer(self.primary_command_buffer, 0));
            self.has_deferred_submissions = false;
            self.upload_recording_active = false;
        }
        self.release_pending_uploads();
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn prewarm_upload_path(
        self: *NativeVulkanRuntime,
        max_upload_bytes: u64,
        mode: webgpu.UploadBufferUsageMode,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !void {
        if (max_upload_bytes == 0) return;
        const prewarm_bytes = if (MAX_UPLOAD_BYTES == 0)
            max_upload_bytes
        else
            @min(max_upload_bytes, MAX_UPLOAD_BYTES);
        try self.upload_bytes(prewarm_bytes, mode, upload_path_policy);
        _ = try self.flush_queue();
    }

    pub fn lifecycle_probe(self: *NativeVulkanRuntime, iterations: u32) !u64 {
        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try self.create_destroy_lifecycle_buffer(256);
        }
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    pub fn pipeline_async_probe(self: *NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8, iterations: u32) !u64 {
        const spirv_words = try self.load_kernel_spirv(allocator, kernel_name);
        defer allocator.free(spirv_words);

        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try self.rebuild_compute_shader_spirv(spirv_words);
        }
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    pub fn resource_table_immediates_emulation_probe(
        self: *NativeVulkanRuntime,
        iterations: u32,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !u64 {
        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try self.create_destroy_lifecycle_buffer(256);
            try self.upload_bytes(64, .copy_dst, upload_path_policy);
            _ = try self.flush_queue();
        }
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    pub fn pixel_local_storage_emulation_probe(
        self: *NativeVulkanRuntime,
        iterations: u32,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !u64 {
        const count = if (iterations > 0) iterations else 1;
        const start_ns = common_timing.now_ns();
        var index: u32 = 0;
        while (index < count) : (index += 1) {
            try self.create_destroy_lifecycle_buffer(512);
            try self.upload_bytes(128, .copy_dst, upload_path_policy);
            _ = try self.barrier(.process_events);
        }
        _ = try self.flush_queue();
        return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    }

    pub fn adapter_ordinal(self: *const NativeVulkanRuntime) ?u32 {
        return self.adapter_ordinal_value;
    }

    pub fn queue_family_index_value(self: *const NativeVulkanRuntime) ?u32 {
        return self.queue_family_index_value_cache;
    }

    pub fn present_capable(self: *const NativeVulkanRuntime) ?bool {
        return self.present_capable_value;
    }

    pub fn texture_write(self: *NativeVulkanRuntime, cmd: model.TextureWriteCommand) !void {
        const resource = try self.ensure_texture_resource(cmd.texture);
        if (cmd.data.len == 0) {
            try self.ensure_texture_shader_layout(resource);
            return;
        }
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            _ = try self.flush_queue();
        }

        const staging = try self.create_host_visible_buffer(@intCast(cmd.data.len), VK_BUFFER_USAGE_TRANSFER_SRC_BIT);
        defer self.destroy_host_visible_buffer(staging);
        if (staging.mapped) |raw| {
            @memcpy(@as([*]u8, @ptrCast(raw))[0..cmd.data.len], cmd.data);
        }

        try check_vk(vkResetCommandPool(self.device, self.command_pool, 0));
        var begin_info = VkCommandBufferBeginInfo{
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try check_vk(vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
        try self.transition_texture_layout(
            self.primary_command_buffer,
            resource.*,
            resource.layout,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            0,
            VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT,
        );

        var region = VkBufferImageCopy{
            .bufferOffset = 0,
            .bufferRowLength = if (cmd.texture.bytes_per_row > 0)
                cmd.texture.bytes_per_row / bytes_per_pixel_for_texture_format(cmd.texture.format)
            else
                0,
            .bufferImageHeight = cmd.texture.rows_per_image,
            .imageSubresource = .{
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .mipLevel = cmd.texture.mip_level,
                .baseArrayLayer = 0,
                .layerCount = 1,
            },
            .imageOffset = .{ .x = 0, .y = 0, .z = 0 },
            .imageExtent = .{
                .width = @max(cmd.texture.width >> @intCast(cmd.texture.mip_level), 1),
                .height = @max(cmd.texture.height >> @intCast(cmd.texture.mip_level), 1),
                .depth = 1,
            },
        };
        vkCmdCopyBufferToImage(
            self.primary_command_buffer,
            staging.buffer,
            resource.image,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            1,
            @ptrCast(&region),
        );

        try self.transition_texture_layout(
            self.primary_command_buffer,
            resource.*,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            VK_IMAGE_LAYOUT_GENERAL,
            VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        );
        try check_vk(vkEndCommandBuffer(self.primary_command_buffer));

        var submit_info = VkSubmitInfo{
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .pNext = null,
            .waitSemaphoreCount = 0,
            .pWaitSemaphores = null,
            .pWaitDstStageMask = null,
            .commandBufferCount = 1,
            .pCommandBuffers = @ptrCast(&self.primary_command_buffer),
            .signalSemaphoreCount = 0,
            .pSignalSemaphores = null,
        };
        try check_vk(vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try check_vk(vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
        try check_vk(vkWaitForFences(self.device, 1, @ptrCast(&self.fence), VK_TRUE, WAIT_TIMEOUT_NS));
        resource.layout = VK_IMAGE_LAYOUT_GENERAL;
    }

    pub fn texture_query(self: *NativeVulkanRuntime, cmd: model.TextureQueryCommand) !void {
        const texture = self.textures.get(cmd.handle) orelse return error.InvalidState;
        if (cmd.expected_width) |width| if (texture.width != width) return error.InvalidState;
        if (cmd.expected_height) |height| if (texture.height != height) return error.InvalidState;
        if (cmd.expected_depth_or_array_layers) |layers| if (layers != 1) return error.InvalidState;
        if (cmd.expected_format) |format| if (texture.format != format) return error.InvalidState;
        if (cmd.expected_dimension) |dimension| if (dimension != model.WGPUTextureDimension_2D) return error.InvalidState;
        if (cmd.expected_view_dimension) |view_dimension| if (view_dimension != model.WGPUTextureViewDimension_2D) return error.InvalidState;
        if (cmd.expected_sample_count) |sample_count| if (sample_count != 1) return error.InvalidState;
        if (cmd.expected_usage) |usage| if ((texture.usage & usage) != usage) return error.InvalidState;
    }

    pub fn texture_destroy(self: *NativeVulkanRuntime, cmd: model.TextureDestroyCommand) !void {
        if (self.textures.fetchRemove(cmd.handle)) |entry| {
            self.release_texture_resource(entry.value);
        }
    }

    pub fn create_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        if (handle == 0) return error.InvalidArgument;
        const result = try self.surfaces.getOrPut(self.allocator, handle);
        if (result.found_existing) return error.InvalidState;
        result.value_ptr.* = .{};
    }

    pub fn get_surface_capabilities(self: *NativeVulkanRuntime, handle: u64) !void {
        _ = self.surfaces.get(handle) orelse return error.SurfaceUnavailable;
    }

    pub fn configure_surface(self: *NativeVulkanRuntime, cmd: model.SurfaceConfigureCommand) !void {
        if (cmd.width == 0 or cmd.height == 0) return error.InvalidArgument;
        const surface = self.surfaces.getPtr(cmd.handle) orelse return error.SurfaceUnavailable;
        surface.* = .{
            .configured = true,
            .acquired = false,
            .width = cmd.width,
            .height = cmd.height,
            .format = cmd.format,
            .usage = if (cmd.usage == 0) model.WGPUTextureUsage_RenderAttachment else cmd.usage,
            .alpha_mode = if (cmd.alpha_mode == 0) 0x00000001 else cmd.alpha_mode,
            .present_mode = if (cmd.present_mode == 0) 0x00000002 else cmd.present_mode,
            .desired_maximum_frame_latency = if (cmd.desired_maximum_frame_latency == 0) 2 else cmd.desired_maximum_frame_latency,
        };
    }

    pub fn acquire_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
        if (!surface.configured or surface.acquired) return error.SurfaceUnavailable;
        surface.acquired = true;
    }

    pub fn present_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
        if (!surface.configured or !surface.acquired) return error.SurfaceUnavailable;
        surface.acquired = false;
        _ = try self.flush_queue();
    }

    pub fn unconfigure_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        const surface = self.surfaces.getPtr(handle) orelse return error.SurfaceUnavailable;
        surface.configured = false;
        surface.acquired = false;
        surface.width = 0;
        surface.height = 0;
    }

    pub fn release_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        if (!self.surfaces.remove(handle)) return error.SurfaceUnavailable;
    }

    fn bootstrap(self: *NativeVulkanRuntime) !void {
        try self.create_instance();
        try self.select_physical_device();
        try self.create_device_and_queue();
        try self.create_command_pool_and_primary_buffer();
        try self.create_fence();
    }

    fn create_instance(self: *NativeVulkanRuntime) !void {
        var app_info = VkApplicationInfo{ .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .pNext = null, .pApplicationName = APP_NAME, .applicationVersion = 0, .pEngineName = ENGINE_NAME, .engineVersion = 0, .apiVersion = VK_API_VERSION_1_0 };
        var create_info = VkInstanceCreateInfo{ .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pNext = null, .flags = 0, .pApplicationInfo = &app_info, .enabledLayerCount = 0, .ppEnabledLayerNames = null, .enabledExtensionCount = 0, .ppEnabledExtensionNames = null };
        try check_vk(vkCreateInstance(&create_info, null, &self.instance));
        self.has_instance = true;
    }

    fn select_physical_device(self: *NativeVulkanRuntime) !void {
        var count: u32 = 0;
        try check_vk(vkEnumeratePhysicalDevices(self.instance, &count, null));
        if (count == 0) return error.UnsupportedFeature;
        const devices = try self.allocator.alloc(VkPhysicalDevice, count);
        defer self.allocator.free(devices);
        try check_vk(vkEnumeratePhysicalDevices(self.instance, &count, devices.ptr));
        const selection = try self.select_preferred_physical_device(devices[0..count]);
        self.physical_device = devices[selection.index];
        self.adapter_ordinal_value = selection.index;
        self.queue_family_index = selection.queue.index;
        self.queue_family_index_value_cache = selection.queue.index;
        self.present_capable_value = selection.queue.supports_graphics;
        self.timestamp_query_supported_value = selection.queue.timestamp_valid_bits > 0;
    }

    fn create_device_and_queue(self: *NativeVulkanRuntime) !void {
        var priority: f32 = 1.0;
        var queue_info = VkDeviceQueueCreateInfo{ .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .pNext = null, .flags = 0, .queueFamilyIndex = self.queue_family_index, .queueCount = 1, .pQueuePriorities = @ptrCast(&priority) };
        var device_info = VkDeviceCreateInfo{ .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .pNext = null, .flags = 0, .queueCreateInfoCount = 1, .pQueueCreateInfos = @ptrCast(&queue_info), .enabledLayerCount = 0, .ppEnabledLayerNames = null, .enabledExtensionCount = 0, .ppEnabledExtensionNames = null, .pEnabledFeatures = null };
        try check_vk(vkCreateDevice(self.physical_device, &device_info, null, &self.device));
        self.has_device = true;
        vkGetDeviceQueue(self.device, self.queue_family_index, 0, &self.queue);
        if (self.queue == null) return error.InvalidState;
    }

    fn create_command_pool_and_primary_buffer(self: *NativeVulkanRuntime) !void {
        var pool_info = VkCommandPoolCreateInfo{ .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, .pNext = null, .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = self.queue_family_index };
        try check_vk(vkCreateCommandPool(self.device, &pool_info, null, &self.command_pool));
        self.has_command_pool = true;

        var alloc_info = VkCommandBufferAllocateInfo{ .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .pNext = null, .commandPool = self.command_pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1 };
        try check_vk(vkAllocateCommandBuffers(self.device, &alloc_info, @ptrCast(&self.primary_command_buffer)));
        self.has_primary_command_buffer = true;
    }

    fn create_fence(self: *NativeVulkanRuntime) !void {
        var fence_info = VkFenceCreateInfo{ .sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO, .pNext = null, .flags = 0 };
        try check_vk(vkCreateFence(self.device, &fence_info, null, &self.fence));
        self.has_fence = true;
    }

    fn ensure_pipeline_layout(self: *NativeVulkanRuntime, bindings: ?[]const model.KernelBinding) !void {
        const layout_hash = compute_layout_hash(bindings);
        if (self.has_pipeline_layout and layout_hash == self.current_layout_hash) return;

        self.destroy_descriptor_state();
        errdefer self.destroy_descriptor_state();

        var set_count: u32 = 0;
        if (bindings) |bs| {
            for (bs) |binding| {
                if (binding.group >= MAX_DESCRIPTOR_SETS_U32) return error.UnsupportedFeature;
                set_count = @max(set_count, binding.group + 1);
            }
        }

        const set_count_usize: usize = @intCast(set_count);
        var per_set_bindings = try self.allocator.alloc(std.ArrayListUnmanaged(VkDescriptorSetLayoutBinding), set_count_usize);
        defer {
            for (per_set_bindings) |*list| list.deinit(self.allocator);
            self.allocator.free(per_set_bindings);
        }
        for (per_set_bindings) |*list| list.* = .{};

        if (bindings) |bs| {
            for (bs) |binding| {
                try per_set_bindings[@intCast(binding.group)].append(self.allocator, .{
                    .binding = binding.binding,
                    .descriptorType = try descriptor_type_for_binding(binding),
                    .descriptorCount = 1,
                    .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT,
                    .pImmutableSamplers = null,
                });
            }
        }

        self.descriptor_set_count = set_count;
        var set_index: usize = 0;
        while (set_index < set_count_usize) : (set_index += 1) {
            const set_bindings = per_set_bindings[set_index].items;
            var layout_info = VkDescriptorSetLayoutCreateInfo{
                .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
                .pNext = null,
                .flags = 0,
                .bindingCount = @intCast(set_bindings.len),
                .pBindings = if (set_bindings.len > 0) set_bindings.ptr else null,
            };
            try check_vk(vkCreateDescriptorSetLayout(self.device, &layout_info, null, &self.descriptor_set_layouts[set_index]));
        }

        var layout_info = VkPipelineLayoutCreateInfo{
            .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .setLayoutCount = self.descriptor_set_count,
            .pSetLayouts = if (self.descriptor_set_count > 0) @ptrCast(self.descriptor_set_layouts[0..@intCast(self.descriptor_set_count)].ptr) else null,
            .pushConstantRangeCount = 0,
            .pPushConstantRanges = null,
        };
        try check_vk(vkCreatePipelineLayout(self.device, &layout_info, null, &self.pipeline_layout));
        self.has_pipeline_layout = true;
        self.current_layout_hash = layout_hash;
    }

    fn build_pipeline_for_words(
        self: *NativeVulkanRuntime,
        words: []const u32,
        pipeline_hash: u64,
        entry_point: ?[]const u8,
        bindings: ?[]const model.KernelBinding,
    ) !void {
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            _ = try self.flush_queue();
        }
        try self.ensure_pipeline_layout(bindings);
        self.destroy_pipeline_objects();
        errdefer self.destroy_pipeline_objects();

        const entry_name = entry_point orelse "main";
        const owned_entry = try self.allocator.dupeZ(u8, entry_name);
        errdefer self.allocator.free(owned_entry);

        var shader_info = VkShaderModuleCreateInfo{ .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, .pNext = null, .flags = 0, .codeSize = words.len * @sizeOf(u32), .pCode = words.ptr };
        try check_vk(vkCreateShaderModule(self.device, &shader_info, null, &self.shader_module));
        self.has_shader_module = true;

        const stage_info = VkPipelineShaderStageCreateInfo{ .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .pNext = null, .flags = 0, .stage = VK_SHADER_STAGE_COMPUTE_BIT, .module = self.shader_module, .pName = owned_entry.ptr, .pSpecializationInfo = null };
        var pipeline_info = VkComputePipelineCreateInfo{ .sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO, .pNext = null, .flags = 0, .stage = stage_info, .layout = self.pipeline_layout, .basePipelineHandle = VK_NULL_U64, .basePipelineIndex = -1 };
        try check_vk(vkCreateComputePipelines(self.device, VK_NULL_U64, 1, @ptrCast(&pipeline_info), null, @ptrCast(&self.pipeline)));
        self.has_pipeline = true;
        self.current_entry_point_owned = owned_entry;
        self.current_pipeline_hash = pipeline_hash;
    }

    fn ensure_fast_upload_buffer(self: *NativeVulkanRuntime, bytes: u64) !void {
        if (self.fast_upload_capacity >= bytes and self.fast_upload_mapped != null) return;
        self.release_fast_upload_buffer();

        var buffer_info = VkBufferCreateInfo{
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .size = bytes,
            .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
            .queueFamilyIndexCount = 0,
            .pQueueFamilyIndices = null,
        };
        try check_vk(vkCreateBuffer(self.device, &buffer_info, null, &self.fast_upload_buffer));
        errdefer self.release_fast_upload_buffer();

        var requirements = std.mem.zeroes(VkMemoryRequirements);
        vkGetBufferMemoryRequirements(self.device, self.fast_upload_buffer, &requirements);
        const memory_index = try self.find_memory_type_index(
            requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        );
        var alloc_info = VkMemoryAllocateInfo{
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .pNext = null,
            .allocationSize = requirements.size,
            .memoryTypeIndex = memory_index,
        };
        try check_vk(vkAllocateMemory(self.device, &alloc_info, null, &self.fast_upload_memory));
        try check_vk(vkBindBufferMemory(self.device, self.fast_upload_buffer, self.fast_upload_memory, 0));
        try check_vk(vkMapMemory(self.device, self.fast_upload_memory, 0, bytes, 0, &self.fast_upload_mapped));
        self.fast_upload_capacity = bytes;
    }

    fn release_fast_upload_buffer(self: *NativeVulkanRuntime) void {
        if (self.fast_upload_mapped != null) {
            vkUnmapMemory(self.device, self.fast_upload_memory);
            self.fast_upload_mapped = null;
        }
        if (self.fast_upload_buffer != VK_NULL_U64) {
            vkDestroyBuffer(self.device, self.fast_upload_buffer, null);
            self.fast_upload_buffer = VK_NULL_U64;
        }
        if (self.fast_upload_memory != VK_NULL_U64) {
            vkFreeMemory(self.device, self.fast_upload_memory, null);
            self.fast_upload_memory = VK_NULL_U64;
        }
        self.fast_upload_capacity = 0;
    }

    fn destroy_pipeline_objects(self: *NativeVulkanRuntime) void {
        if (self.has_pipeline) {
            vkDestroyPipeline(self.device, self.pipeline, null);
            self.has_pipeline = false;
            self.pipeline = VK_NULL_U64;
        }
        if (self.has_shader_module) {
            vkDestroyShaderModule(self.device, self.shader_module, null);
            self.has_shader_module = false;
            self.shader_module = VK_NULL_U64;
        }
        if (self.current_entry_point_owned) |entry_name| {
            self.allocator.free(entry_name);
            self.current_entry_point_owned = null;
        }
        self.current_pipeline_hash = 0;
    }

    fn destroy_descriptor_state(self: *NativeVulkanRuntime) void {
        if (self.has_descriptor_pool) {
            vkDestroyDescriptorPool(self.device, self.descriptor_pool, null);
            self.has_descriptor_pool = false;
            self.descriptor_pool = VK_NULL_U64;
        }
        var set_index: usize = 0;
        while (set_index < MAX_DESCRIPTOR_SETS) : (set_index += 1) {
            if (self.descriptor_set_layouts[set_index] != VK_NULL_U64) {
                vkDestroyDescriptorSetLayout(self.device, self.descriptor_set_layouts[set_index], null);
                self.descriptor_set_layouts[set_index] = VK_NULL_U64;
            }
            self.descriptor_sets[set_index] = VK_NULL_U64;
        }
        self.descriptor_set_count = 0;
        if (self.has_pipeline_layout) {
            vkDestroyPipelineLayout(self.device, self.pipeline_layout, null);
            self.has_pipeline_layout = false;
            self.pipeline_layout = VK_NULL_U64;
        }
        self.current_layout_hash = 0;
    }

    fn prepare_descriptor_sets(
        self: *NativeVulkanRuntime,
        bindings: ?[]const model.KernelBinding,
        initialize_buffers_on_create: bool,
    ) !void {
        if (self.descriptor_set_count == 0) return;
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            _ = try self.flush_queue();
        }
        try self.ensure_descriptor_pool(bindings);

        const bs = bindings orelse return error.InvalidArgument;
        var buffer_infos = std.ArrayListUnmanaged(VkDescriptorBufferInfo){};
        defer buffer_infos.deinit(self.allocator);
        var image_infos = std.ArrayListUnmanaged(VkDescriptorImageInfo){};
        defer image_infos.deinit(self.allocator);
        var pending_writes = std.ArrayListUnmanaged(PendingDescriptorWrite){};
        defer pending_writes.deinit(self.allocator);
        var writes = std.ArrayListUnmanaged(VkWriteDescriptorSet){};
        defer writes.deinit(self.allocator);

        for (bs) |binding| {
            const descriptor_type = try descriptor_type_for_binding(binding);
            switch (binding.resource_kind) {
                .buffer => {
                    const required_size = try self.required_compute_buffer_size(binding);
                    const compute_buffer = try self.ensure_compute_buffer(
                        binding.resource_handle,
                        required_size,
                        initialize_buffers_on_create,
                    );
                    try buffer_infos.append(self.allocator, .{
                        .buffer = compute_buffer.buffer,
                        .offset = binding.buffer_offset,
                        .range = try descriptor_range(binding, compute_buffer.size),
                    });
                    try pending_writes.append(self.allocator, .{
                        .set_index = binding.group,
                        .binding = binding.binding,
                        .descriptor_type = descriptor_type,
                        .kind = .buffer,
                        .info_index = buffer_infos.items.len - 1,
                    });
                },
                .texture, .storage_texture => {
                    const texture = self.textures.getPtr(binding.resource_handle) orelse return error.InvalidState;
                    try validate_texture_binding(binding, texture.*);
                    try self.ensure_texture_shader_layout(texture);
                    try image_infos.append(self.allocator, .{
                        .sampler = 0,
                        .imageView = texture.view,
                        .imageLayout = texture.layout,
                    });
                    try pending_writes.append(self.allocator, .{
                        .set_index = binding.group,
                        .binding = binding.binding,
                        .descriptor_type = descriptor_type,
                        .kind = .image,
                        .info_index = image_infos.items.len - 1,
                    });
                },
            }
        }

        for (pending_writes.items) |pending| {
            try writes.append(self.allocator, .{
                .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
                .pNext = null,
                .dstSet = self.descriptor_sets[@intCast(pending.set_index)],
                .dstBinding = pending.binding,
                .dstArrayElement = 0,
                .descriptorCount = 1,
                .descriptorType = pending.descriptor_type,
                .pImageInfo = if (pending.kind == .image) @ptrCast(&image_infos.items[pending.info_index]) else null,
                .pBufferInfo = if (pending.kind == .buffer) @ptrCast(&buffer_infos.items[pending.info_index]) else null,
                .pTexelBufferView = null,
            });
        }

        if (writes.items.len > 0) {
            vkUpdateDescriptorSets(self.device, @intCast(writes.items.len), writes.items.ptr, 0, null);
        }
    }

    fn ensure_descriptor_pool(self: *NativeVulkanRuntime, bindings: ?[]const model.KernelBinding) !void {
        if (self.has_descriptor_pool) return;
        if (self.descriptor_set_count == 0) return;

        var uniform_count: u32 = 0;
        var storage_count: u32 = 0;
        var sampled_image_count: u32 = 0;
        var storage_image_count: u32 = 0;
        if (bindings) |bs| {
            for (bs) |binding| {
                switch (try descriptor_type_for_binding(binding)) {
                    VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER => uniform_count += 1,
                    VK_DESCRIPTOR_TYPE_STORAGE_BUFFER => storage_count += 1,
                    VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE => sampled_image_count += 1,
                    VK_DESCRIPTOR_TYPE_STORAGE_IMAGE => storage_image_count += 1,
                    else => return error.UnsupportedFeature,
                }
            }
        }

        var pool_sizes: [4]VkDescriptorPoolSize = undefined;
        var pool_size_count: usize = 0;
        if (uniform_count > 0) {
            pool_sizes[pool_size_count] = .{ .type = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, .descriptorCount = uniform_count };
            pool_size_count += 1;
        }
        if (storage_count > 0) {
            pool_sizes[pool_size_count] = .{ .type = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .descriptorCount = storage_count };
            pool_size_count += 1;
        }
        if (sampled_image_count > 0) {
            pool_sizes[pool_size_count] = .{ .type = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, .descriptorCount = sampled_image_count };
            pool_size_count += 1;
        }
        if (storage_image_count > 0) {
            pool_sizes[pool_size_count] = .{ .type = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, .descriptorCount = storage_image_count };
            pool_size_count += 1;
        }

        var pool_info = VkDescriptorPoolCreateInfo{
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .maxSets = self.descriptor_set_count,
            .poolSizeCount = @intCast(pool_size_count),
            .pPoolSizes = if (pool_size_count > 0) pool_sizes[0..pool_size_count].ptr else null,
        };
        try check_vk(vkCreateDescriptorPool(self.device, &pool_info, null, &self.descriptor_pool));
        errdefer {
            vkDestroyDescriptorPool(self.device, self.descriptor_pool, null);
            self.descriptor_pool = VK_NULL_U64;
        }

        var alloc_info = VkDescriptorSetAllocateInfo{
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
            .pNext = null,
            .descriptorPool = self.descriptor_pool,
            .descriptorSetCount = self.descriptor_set_count,
            .pSetLayouts = self.descriptor_set_layouts[0..@intCast(self.descriptor_set_count)].ptr,
        };
        try check_vk(vkAllocateDescriptorSets(self.device, &alloc_info, self.descriptor_sets[0..@intCast(self.descriptor_set_count)].ptr));
        self.has_descriptor_pool = true;
    }

    fn ensure_compute_buffer(
        self: *NativeVulkanRuntime,
        handle: u64,
        required_size: u64,
        initialize_buffers_on_create: bool,
    ) !ComputeBuffer {
        if (handle == 0 or required_size == 0) return error.InvalidArgument;
        if (self.compute_buffers.getPtr(handle)) |existing| {
            if (existing.size >= required_size) return existing.*;
            if (self.has_deferred_submissions) _ = try self.flush_queue();
            self.release_compute_buffer(existing.*);
            existing.* = try self.create_compute_buffer(required_size, initialize_buffers_on_create);
            return existing.*;
        }

        const compute_buffer = try self.create_compute_buffer(required_size, initialize_buffers_on_create);
        try self.compute_buffers.put(self.allocator, handle, compute_buffer);
        return self.compute_buffers.get(handle).?;
    }

    fn required_compute_buffer_size(
        self: *const NativeVulkanRuntime,
        binding: model.KernelBinding,
    ) !u64 {
        if (binding.resource_kind != .buffer) return error.UnsupportedFeature;
        if (binding.buffer_size == model.WGPUWholeSize) {
            if (self.compute_buffers.get(binding.resource_handle)) |existing| {
                return existing.size;
            }
            return error.InvalidArgument;
        }
        return std.math.add(u64, binding.buffer_offset, binding.buffer_size) catch error.InvalidArgument;
    }

    fn create_compute_buffer(
        self: *NativeVulkanRuntime,
        bytes: u64,
        initialize_buffers_on_create: bool,
    ) !ComputeBuffer {
        var buffer: VkBuffer = VK_NULL_U64;
        var memory: VkDeviceMemory = VK_NULL_U64;
        var mapped: ?*anyopaque = null;

        var buffer_info = VkBufferCreateInfo{
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .size = bytes,
            .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
                VK_BUFFER_USAGE_TRANSFER_DST_BIT |
                VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT |
                VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
            .queueFamilyIndexCount = 0,
            .pQueueFamilyIndices = null,
        };
        try check_vk(vkCreateBuffer(self.device, &buffer_info, null, &buffer));
        errdefer if (buffer != VK_NULL_U64) vkDestroyBuffer(self.device, buffer, null);

        var requirements = std.mem.zeroes(VkMemoryRequirements);
        vkGetBufferMemoryRequirements(self.device, buffer, &requirements);
        const memory_index = try self.find_memory_type_index(
            requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        );
        var alloc_info = VkMemoryAllocateInfo{
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .pNext = null,
            .allocationSize = requirements.size,
            .memoryTypeIndex = memory_index,
        };
        try check_vk(vkAllocateMemory(self.device, &alloc_info, null, &memory));
        errdefer if (memory != VK_NULL_U64) vkFreeMemory(self.device, memory, null);

        try check_vk(vkBindBufferMemory(self.device, buffer, memory, 0));
        try check_vk(vkMapMemory(self.device, memory, 0, bytes, 0, &mapped));
        errdefer if (mapped != null) vkUnmapMemory(self.device, memory);

        if (initialize_buffers_on_create and mapped != null) {
            @memset(@as([*]u8, @ptrCast(mapped.?))[0..@intCast(bytes)], 0);
        }

        return .{
            .buffer = buffer,
            .memory = memory,
            .mapped = mapped,
            .size = bytes,
        };
    }

    fn release_compute_buffer(self: *NativeVulkanRuntime, compute_buffer: ComputeBuffer) void {
        if (compute_buffer.mapped != null) {
            vkUnmapMemory(self.device, compute_buffer.memory);
        }
        vkDestroyBuffer(self.device, compute_buffer.buffer, null);
        vkFreeMemory(self.device, compute_buffer.memory, null);
    }

    fn release_compute_buffers(self: *NativeVulkanRuntime) void {
        var iterator = self.compute_buffers.valueIterator();
        while (iterator.next()) |buffer| {
            self.release_compute_buffer(buffer.*);
        }
        self.compute_buffers.deinit(self.allocator);
    }

    fn create_host_visible_buffer(self: *NativeVulkanRuntime, bytes: u64, usage: u32) !ComputeBuffer {
        var buffer: VkBuffer = VK_NULL_U64;
        var memory: VkDeviceMemory = VK_NULL_U64;
        var mapped: ?*anyopaque = null;

        var buffer_info = VkBufferCreateInfo{
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .size = bytes,
            .usage = usage,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
            .queueFamilyIndexCount = 0,
            .pQueueFamilyIndices = null,
        };
        try check_vk(vkCreateBuffer(self.device, &buffer_info, null, &buffer));
        errdefer if (buffer != VK_NULL_U64) vkDestroyBuffer(self.device, buffer, null);

        var requirements = std.mem.zeroes(VkMemoryRequirements);
        vkGetBufferMemoryRequirements(self.device, buffer, &requirements);
        const memory_index = try self.find_memory_type_index(
            requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        );
        var alloc_info = VkMemoryAllocateInfo{
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .pNext = null,
            .allocationSize = requirements.size,
            .memoryTypeIndex = memory_index,
        };
        try check_vk(vkAllocateMemory(self.device, &alloc_info, null, &memory));
        errdefer if (memory != VK_NULL_U64) vkFreeMemory(self.device, memory, null);

        try check_vk(vkBindBufferMemory(self.device, buffer, memory, 0));
        try check_vk(vkMapMemory(self.device, memory, 0, bytes, 0, &mapped));
        errdefer if (mapped != null) vkUnmapMemory(self.device, memory);

        return .{
            .buffer = buffer,
            .memory = memory,
            .mapped = mapped,
            .size = bytes,
        };
    }

    fn destroy_host_visible_buffer(self: *NativeVulkanRuntime, buffer: ComputeBuffer) void {
        self.release_compute_buffer(buffer);
    }

    fn ensure_texture_resource(self: *NativeVulkanRuntime, texture: model.CopyTextureResource) !*TextureResource {
        if (texture.handle == 0) return error.InvalidArgument;
        if (texture.width == 0 or texture.height == 0) return error.InvalidArgument;
        const mip_levels: u32 = if (texture.mip_level > 0) texture.mip_level + 1 else 1;
        if (self.textures.getPtr(texture.handle)) |existing| {
            if (existing.width == texture.width and
                existing.height == texture.height and
                existing.mip_levels == mip_levels and
                existing.format == texture.format and
                existing.usage == texture.usage)
            {
                return existing;
            }
            if (self.has_deferred_submissions) _ = try self.flush_queue();
            self.release_texture_resource(existing.*);
            existing.* = try self.create_texture_resource(texture, mip_levels);
            return existing;
        }

        try self.textures.put(self.allocator, texture.handle, try self.create_texture_resource(texture, mip_levels));
        return self.textures.getPtr(texture.handle).?;
    }

    fn ensure_texture_shader_layout(self: *NativeVulkanRuntime, texture: *TextureResource) !void {
        if (texture.layout == VK_IMAGE_LAYOUT_GENERAL) return;
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            _ = try self.flush_queue();
        }

        try check_vk(vkResetCommandPool(self.device, self.command_pool, 0));
        var begin_info = VkCommandBufferBeginInfo{
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try check_vk(vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
        const source = texture_transition_source(texture.layout);
        try self.transition_texture_layout(
            self.primary_command_buffer,
            texture.*,
            texture.layout,
            VK_IMAGE_LAYOUT_GENERAL,
            source.src_access_mask,
            VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT,
            source.src_stage,
            VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        );
        try check_vk(vkEndCommandBuffer(self.primary_command_buffer));

        var submit_info = VkSubmitInfo{
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .pNext = null,
            .waitSemaphoreCount = 0,
            .pWaitSemaphores = null,
            .pWaitDstStageMask = null,
            .commandBufferCount = 1,
            .pCommandBuffers = @ptrCast(&self.primary_command_buffer),
            .signalSemaphoreCount = 0,
            .pSignalSemaphores = null,
        };
        try check_vk(vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try check_vk(vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
        try check_vk(vkWaitForFences(self.device, 1, @ptrCast(&self.fence), VK_TRUE, WAIT_TIMEOUT_NS));
        texture.layout = VK_IMAGE_LAYOUT_GENERAL;
    }

    fn create_texture_resource(
        self: *NativeVulkanRuntime,
        texture: model.CopyTextureResource,
        mip_levels: u32,
    ) !TextureResource {
        var image: VkImage = VK_NULL_U64;
        var memory: VkDeviceMemory = VK_NULL_U64;
        var view: VkImageView = VK_NULL_U64;
        const usage = effective_texture_usage(texture.usage);

        var image_info = VkImageCreateInfo{
            .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .imageType = VK_IMAGE_TYPE_2D,
            .format = try texture_format_to_vk(texture.format),
            .extent = .{
                .width = texture.width,
                .height = texture.height,
                .depth = 1,
            },
            .mipLevels = mip_levels,
            .arrayLayers = 1,
            .samples = VK_SAMPLE_COUNT_1_BIT,
            .tiling = VK_IMAGE_TILING_OPTIMAL,
            .usage = image_usage_for_texture(usage),
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
            .queueFamilyIndexCount = 0,
            .pQueueFamilyIndices = null,
            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        };
        try check_vk(vkCreateImage(self.device, &image_info, null, &image));
        errdefer if (image != VK_NULL_U64) vkDestroyImage(self.device, image, null);

        var requirements = std.mem.zeroes(VkMemoryRequirements);
        vkGetImageMemoryRequirements(self.device, image, &requirements);
        const memory_index = try self.find_memory_type_index(
            requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,
        );
        var alloc_info = VkMemoryAllocateInfo{
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .pNext = null,
            .allocationSize = requirements.size,
            .memoryTypeIndex = memory_index,
        };
        try check_vk(vkAllocateMemory(self.device, &alloc_info, null, &memory));
        errdefer if (memory != VK_NULL_U64) vkFreeMemory(self.device, memory, null);

        try check_vk(vkBindImageMemory(self.device, image, memory, 0));

        var view_info = VkImageViewCreateInfo{
            .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .image = image,
            .viewType = VK_IMAGE_VIEW_TYPE_2D,
            .format = try texture_format_to_vk(texture.format),
            .components = .{
                .r = VK_COMPONENT_SWIZZLE_IDENTITY,
                .g = VK_COMPONENT_SWIZZLE_IDENTITY,
                .b = VK_COMPONENT_SWIZZLE_IDENTITY,
                .a = VK_COMPONENT_SWIZZLE_IDENTITY,
            },
            .subresourceRange = .{
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .baseMipLevel = 0,
                .levelCount = mip_levels,
                .baseArrayLayer = 0,
                .layerCount = 1,
            },
        };
        try check_vk(vkCreateImageView(self.device, &view_info, null, &view));
        errdefer if (view != VK_NULL_U64) vkDestroyImageView(self.device, view, null);

        return .{
            .image = image,
            .memory = memory,
            .view = view,
            .width = texture.width,
            .height = texture.height,
            .mip_levels = mip_levels,
            .format = texture.format,
            .usage = usage,
            .layout = VK_IMAGE_LAYOUT_UNDEFINED,
        };
    }

    fn release_texture_resource(self: *NativeVulkanRuntime, texture: TextureResource) void {
        if (texture.view != VK_NULL_U64) vkDestroyImageView(self.device, texture.view, null);
        if (texture.image != VK_NULL_U64) vkDestroyImage(self.device, texture.image, null);
        if (texture.memory != VK_NULL_U64) vkFreeMemory(self.device, texture.memory, null);
    }

    fn release_textures(self: *NativeVulkanRuntime) void {
        var iterator = self.textures.valueIterator();
        while (iterator.next()) |texture| {
            self.release_texture_resource(texture.*);
        }
        self.textures.deinit(self.allocator);
    }

    fn transition_texture_layout(
        self: *NativeVulkanRuntime,
        command_buffer: VkCommandBuffer,
        texture: TextureResource,
        old_layout: u32,
        new_layout: u32,
        src_access_mask: u32,
        dst_access_mask: u32,
        src_stage: u32,
        dst_stage: u32,
    ) !void {
        _ = self;
        var image_barrier = VkImageMemoryBarrier{
            .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .pNext = null,
            .srcAccessMask = src_access_mask,
            .dstAccessMask = dst_access_mask,
            .oldLayout = old_layout,
            .newLayout = new_layout,
            .srcQueueFamilyIndex = std.math.maxInt(u32),
            .dstQueueFamilyIndex = std.math.maxInt(u32),
            .image = texture.image,
            .subresourceRange = .{
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .baseMipLevel = 0,
                .levelCount = texture.mip_levels,
                .baseArrayLayer = 0,
                .layerCount = 1,
            },
        };
        vkCmdPipelineBarrier(
            command_buffer,
            src_stage,
            dst_stage,
            0,
            0,
            null,
            0,
            null,
            1,
            @ptrCast(&image_barrier),
        );
    }

    fn bind_descriptor_sets(self: *NativeVulkanRuntime, command_buffer: VkCommandBuffer) void {
        if (!self.has_descriptor_pool or self.descriptor_set_count == 0) return;
        vkCmdBindDescriptorSets(
            command_buffer,
            VK_PIPELINE_BIND_POINT_COMPUTE,
            self.pipeline_layout,
            0,
            self.descriptor_set_count,
            self.descriptor_sets[0..@intCast(self.descriptor_set_count)].ptr,
            0,
            null,
        );
    }

    fn record_upload_copy(self: *NativeVulkanRuntime, bytes: u64, dst_usage: u32) !PendingUpload {
        try self.ensure_upload_recording();

        var src_buffer: VkBuffer = VK_NULL_U64;
        var dst_buffer: VkBuffer = VK_NULL_U64;
        var src_memory: VkDeviceMemory = VK_NULL_U64;
        var dst_memory: VkDeviceMemory = VK_NULL_U64;
        var src_fresh = true;

        // Try pool first for src (host-visible staging buffer).
        if (hot_pool_pop(&self.hot_src_pool_entry, &self.hot_src_pool_size, bytes)) |entry| {
            src_buffer = entry.buffer;
            src_memory = entry.memory;
            src_fresh = false;
        } else if (vk_pool_pop(&self.src_pool, bytes)) |entry| {
            src_buffer = entry.buffer;
            src_memory = entry.memory;
            src_fresh = false;
        } else {
            var src_info = VkBufferCreateInfo{ .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .pNext = null, .flags = 0, .size = bytes, .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT, .sharingMode = VK_SHARING_MODE_EXCLUSIVE, .queueFamilyIndexCount = 0, .pQueueFamilyIndices = null };
            try check_vk(vkCreateBuffer(self.device, &src_info, null, &src_buffer));
            errdefer vkDestroyBuffer(self.device, src_buffer, null);

            var src_req = std.mem.zeroes(VkMemoryRequirements);
            vkGetBufferMemoryRequirements(self.device, src_buffer, &src_req);
            const src_mem_index = try self.find_memory_type_index(src_req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
            var src_alloc_info = VkMemoryAllocateInfo{ .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .pNext = null, .allocationSize = src_req.size, .memoryTypeIndex = src_mem_index };
            try check_vk(vkAllocateMemory(self.device, &src_alloc_info, null, &src_memory));
            errdefer vkFreeMemory(self.device, src_memory, null);
            try check_vk(vkBindBufferMemory(self.device, src_buffer, src_memory, 0));
        }

        // Try pool for dst (device-local storage buffer).
        if (hot_pool_pop(&self.hot_dst_pool_entry, &self.hot_dst_pool_size, bytes)) |entry| {
            dst_buffer = entry.buffer;
            dst_memory = entry.memory;
        } else if (vk_pool_pop(&self.dst_pool, bytes)) |entry| {
            dst_buffer = entry.buffer;
            dst_memory = entry.memory;
        } else {
            const permissive_dst_usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
            const effective_usage = if (dst_usage == 0) permissive_dst_usage else dst_usage | VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
            var dst_info = VkBufferCreateInfo{ .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .pNext = null, .flags = 0, .size = bytes, .usage = effective_usage, .sharingMode = VK_SHARING_MODE_EXCLUSIVE, .queueFamilyIndexCount = 0, .pQueueFamilyIndices = null };
            try check_vk(vkCreateBuffer(self.device, &dst_info, null, &dst_buffer));
            errdefer vkDestroyBuffer(self.device, dst_buffer, null);

            var dst_req = std.mem.zeroes(VkMemoryRequirements);
            vkGetBufferMemoryRequirements(self.device, dst_buffer, &dst_req);
            const dst_mem_index = try self.find_memory_type_index(dst_req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
            var dst_alloc_info = VkMemoryAllocateInfo{ .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .pNext = null, .allocationSize = dst_req.size, .memoryTypeIndex = dst_mem_index };
            try check_vk(vkAllocateMemory(self.device, &dst_alloc_info, null, &dst_memory));
            errdefer vkFreeMemory(self.device, dst_memory, null);
            try check_vk(vkBindBufferMemory(self.device, dst_buffer, dst_memory, 0));
        }
        // Only zero-fill fresh (non-pooled) src allocations.
        if (src_fresh) {
            var mapped: ?*anyopaque = null;
            try check_vk(vkMapMemory(self.device, src_memory, 0, bytes, 0, &mapped));
            if (mapped) |raw| {
                const fill_len = @min(@as(usize, @intCast(bytes)), MAX_UPLOAD_ZERO_FILL_BYTES);
                @memset(@as([*]u8, @ptrCast(raw))[0..fill_len], 0);
            }
            vkUnmapMemory(self.device, src_memory);
        }

        var region = VkBufferCopy{ .srcOffset = 0, .dstOffset = 0, .size = bytes };
        vkCmdCopyBuffer(self.primary_command_buffer, src_buffer, dst_buffer, 1, @ptrCast(&region));

        return .{
            .src_buffer = src_buffer,
            .src_memory = src_memory,
            .dst_buffer = dst_buffer,
            .dst_memory = dst_memory,
            .byte_count = bytes,
        };
    }

    fn try_direct_upload(self: *NativeVulkanRuntime, bytes: u64, dst_usage: u32) !bool {
        self.record_direct_upload(bytes, dst_usage) catch |err| switch (err) {
            error.UnsupportedFeature => return false,
            else => return err,
        };
        return true;
    }

    fn record_direct_upload(self: *NativeVulkanRuntime, bytes: u64, dst_usage: u32) !void {
        var dst_buffer: VkBuffer = VK_NULL_U64;
        var dst_memory: VkDeviceMemory = VK_NULL_U64;
        var dst_mapped: ?*anyopaque = null;
        var dst_fresh = false;

        if (vk_pool_pop(&self.direct_upload_pool, bytes)) |entry| {
            dst_buffer = entry.buffer;
            dst_memory = entry.memory;
            dst_mapped = entry.mapped;
        } else {
            const effective_usage = if (dst_usage == 0)
                VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT
            else
                dst_usage;
            var dst_info = VkBufferCreateInfo{
                .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
                .pNext = null,
                .flags = 0,
                .size = bytes,
                .usage = effective_usage,
                .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
                .queueFamilyIndexCount = 0,
                .pQueueFamilyIndices = null,
            };
            try check_vk(vkCreateBuffer(self.device, &dst_info, null, &dst_buffer));
            errdefer vkDestroyBuffer(self.device, dst_buffer, null);

            var dst_req = std.mem.zeroes(VkMemoryRequirements);
            vkGetBufferMemoryRequirements(self.device, dst_buffer, &dst_req);
            const dst_mem_index = try self.find_memory_type_index(
                dst_req.memoryTypeBits,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
            );
            var dst_alloc_info = VkMemoryAllocateInfo{
                .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
                .pNext = null,
                .allocationSize = dst_req.size,
                .memoryTypeIndex = dst_mem_index,
            };
            try check_vk(vkAllocateMemory(self.device, &dst_alloc_info, null, &dst_memory));
            errdefer vkFreeMemory(self.device, dst_memory, null);
            try check_vk(vkBindBufferMemory(self.device, dst_buffer, dst_memory, 0));
            try check_vk(vkMapMemory(self.device, dst_memory, 0, bytes, 0, &dst_mapped));
            dst_fresh = true;
        }

        errdefer {
            if (dst_buffer != VK_NULL_U64 and dst_memory != VK_NULL_U64) {
                vk_pool_push_or_destroy(
                    &self.direct_upload_pool,
                    self.allocator,
                    self.device,
                    bytes,
                    .{ .buffer = dst_buffer, .memory = dst_memory, .mapped = dst_mapped },
                );
            } else {
                if (dst_buffer != VK_NULL_U64) vkDestroyBuffer(self.device, dst_buffer, null);
                if (dst_memory != VK_NULL_U64) vkFreeMemory(self.device, dst_memory, null);
            }
        }

        if (dst_fresh or bytes < DIRECT_UPLOAD_REUSE_SKIP_ZERO_FILL_MIN_BYTES) {
            const fill_len: usize = @intCast(bytes);
            if (dst_mapped) |raw| {
                @memset(@as([*]u8, @ptrCast(raw))[0..fill_len], 0);
            }
        }

        vk_pool_push_or_destroy(
            &self.direct_upload_pool,
            self.allocator,
            self.device,
            bytes,
            .{ .buffer = dst_buffer, .memory = dst_memory, .mapped = dst_mapped },
        );
    }

    fn release_pending_uploads(self: *NativeVulkanRuntime) void {
        for (self.pending_uploads.items) |item| {
            self.release_upload(item);
        }
        self.pending_uploads.clearRetainingCapacity();
    }

    fn release_upload(self: *NativeVulkanRuntime, item: PendingUpload) void {
        if (item.src_buffer != VK_NULL_U64 and item.src_memory != VK_NULL_U64) {
            if (!hot_pool_store(&self.hot_src_pool_entry, &self.hot_src_pool_size, item.byte_count, .{ .buffer = item.src_buffer, .memory = item.src_memory, .mapped = null })) {
                vk_pool_push_or_destroy(&self.src_pool, self.allocator, self.device, item.byte_count, .{ .buffer = item.src_buffer, .memory = item.src_memory, .mapped = null });
            }
        } else {
            if (item.src_buffer != VK_NULL_U64) vkDestroyBuffer(self.device, item.src_buffer, null);
            if (item.src_memory != VK_NULL_U64) vkFreeMemory(self.device, item.src_memory, null);
        }
        if (item.dst_buffer != VK_NULL_U64 and item.dst_memory != VK_NULL_U64) {
            if (!hot_pool_store(&self.hot_dst_pool_entry, &self.hot_dst_pool_size, item.byte_count, .{ .buffer = item.dst_buffer, .memory = item.dst_memory, .mapped = null })) {
                vk_pool_push_or_destroy(&self.dst_pool, self.allocator, self.device, item.byte_count, .{ .buffer = item.dst_buffer, .memory = item.dst_memory, .mapped = null });
            }
        } else {
            if (item.dst_buffer != VK_NULL_U64) vkDestroyBuffer(self.device, item.dst_buffer, null);
            if (item.dst_memory != VK_NULL_U64) vkFreeMemory(self.device, item.dst_memory, null);
        }
    }

    fn ensure_upload_recording(self: *NativeVulkanRuntime) !void {
        if (self.upload_recording_active) return;
        if (!self.has_deferred_submissions) {
            try check_vk(vkResetCommandBuffer(self.primary_command_buffer, 0));
        }
        var begin = VkCommandBufferBeginInfo{
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try check_vk(vkBeginCommandBuffer(self.primary_command_buffer, &begin));
        self.upload_recording_active = true;
    }

    fn finish_pending_upload_recording(self: *NativeVulkanRuntime) !void {
        if (!self.upload_recording_active) return;
        try check_vk(vkEndCommandBuffer(self.primary_command_buffer));
        self.upload_recording_active = false;
    }

    fn select_preferred_physical_device(self: *NativeVulkanRuntime, devices: []const VkPhysicalDevice) !PhysicalDeviceSelection {
        var best: ?PhysicalDeviceSelection = null;
        for (devices, 0..) |device, index| {
            const queue = self.select_queue_family_for_device(device) catch continue;
            const score = self.score_physical_device(device, queue);
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

    fn select_queue_family_for_device(self: *NativeVulkanRuntime, device: VkPhysicalDevice) !QueueFamilySelection {
        var count: u32 = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(device, &count, null);
        if (count == 0) return error.UnsupportedFeature;
        const props = try self.allocator.alloc(VkQueueFamilyProperties, count);
        defer self.allocator.free(props);
        vkGetPhysicalDeviceQueueFamilyProperties(device, &count, props.ptr);

        var best: ?QueueFamilySelection = null;
        for (props, 0..) |family, idx| {
            if ((family.queueFlags & VK_QUEUE_COMPUTE_BIT) == 0 or family.queueCount == 0) continue;
            const candidate = QueueFamilySelection{
                .index = @as(u32, @intCast(idx)),
                .supports_graphics = (family.queueFlags & VK_QUEUE_GRAPHICS_BIT) != 0,
                .timestamp_valid_bits = family.timestampValidBits,
                .queue_count = family.queueCount,
            };
            if (best == null or queue_selection_score(candidate) > queue_selection_score(best.?)) {
                best = candidate;
            }
        }
        return best orelse error.UnsupportedFeature;
    }

    fn score_physical_device(self: *NativeVulkanRuntime, device: VkPhysicalDevice, queue: QueueFamilySelection) u64 {
        _ = self;
        var memory_props = std.mem.zeroes(VkPhysicalDeviceMemoryProperties);
        vkGetPhysicalDeviceMemoryProperties(device, &memory_props);

        var device_local_heap_bytes: u64 = 0;
        var type_index: u32 = 0;
        while (type_index < memory_props.memoryTypeCount) : (type_index += 1) {
            const memory_type = memory_props.memoryTypes[type_index];
            if ((memory_type.propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) == 0) continue;
            if (memory_type.heapIndex >= memory_props.memoryHeapCount) continue;
            device_local_heap_bytes +|= memory_props.memoryHeaps[memory_type.heapIndex].size;
        }

        return queue_selection_score(queue) + (device_local_heap_bytes / (1024 * 1024));
    }

    fn find_memory_type_index(self: *NativeVulkanRuntime, type_bits: u32, required_flags: u32) !u32 {
        var memory_props = std.mem.zeroes(VkPhysicalDeviceMemoryProperties);
        vkGetPhysicalDeviceMemoryProperties(self.physical_device, &memory_props);
        var i: u32 = 0;
        while (i < memory_props.memoryTypeCount) : (i += 1) {
            const supports_type = (type_bits & (@as(u32, 1) << @as(u5, @intCast(i)))) != 0;
            if (!supports_type) continue;
            if ((memory_props.memoryTypes[i].propertyFlags & required_flags) == required_flags) return i;
        }
        return error.UnsupportedFeature;
    }

    fn create_destroy_lifecycle_buffer(self: *NativeVulkanRuntime, bytes: u64) !void {
        var buffer: VkBuffer = VK_NULL_U64;
        var memory: VkDeviceMemory = VK_NULL_U64;
        var buffer_info = VkBufferCreateInfo{
            .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .size = bytes,
            .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT,
            .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
            .queueFamilyIndexCount = 0,
            .pQueueFamilyIndices = null,
        };
        try check_vk(vkCreateBuffer(self.device, &buffer_info, null, &buffer));
        defer if (buffer != VK_NULL_U64) vkDestroyBuffer(self.device, buffer, null);

        var requirements = std.mem.zeroes(VkMemoryRequirements);
        vkGetBufferMemoryRequirements(self.device, buffer, &requirements);
        const memory_index = try self.find_memory_type_index(
            requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        );
        var alloc_info = VkMemoryAllocateInfo{
            .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
            .pNext = null,
            .allocationSize = requirements.size,
            .memoryTypeIndex = memory_index,
        };
        try check_vk(vkAllocateMemory(self.device, &alloc_info, null, &memory));
        defer if (memory != VK_NULL_U64) vkFreeMemory(self.device, memory, null);
        try check_vk(vkBindBufferMemory(self.device, buffer, memory, 0));
    }

    fn timestamp_query_supported(self: *const NativeVulkanRuntime) bool {
        if (!self.has_device or self.queue == null) return false;
        return self.queue_family_index_value_cache != null and self.timestamp_query_supported_value;
    }

    fn collect_dispatch_gpu_timestamp(self: *NativeVulkanRuntime) !u64 {
        var query_pool: VkQueryPool = VK_NULL_U64;
        defer if (query_pool != VK_NULL_U64) vkDestroyQueryPool(self.device, query_pool, null);

        var create_info = VkQueryPoolCreateInfo{
            .sType = VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .queryType = VK_QUERY_TYPE_TIMESTAMP,
            .queryCount = 2,
            .pipelineStatistics = 0,
        };
        try check_vk(vkCreateQueryPool(self.device, &create_info, null, &query_pool));

        try check_vk(vkResetCommandPool(self.device, self.command_pool, 0));
        var begin_info = VkCommandBufferBeginInfo{
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
            .pNext = null,
            .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
            .pInheritanceInfo = null,
        };
        try check_vk(vkBeginCommandBuffer(self.primary_command_buffer, &begin_info));
        vkCmdWriteTimestamp(self.primary_command_buffer, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, query_pool, 0);
        vkCmdBindPipeline(self.primary_command_buffer, VK_PIPELINE_BIND_POINT_COMPUTE, self.pipeline);
        self.bind_descriptor_sets(self.primary_command_buffer);
        vkCmdDispatch(self.primary_command_buffer, 1, 1, 1);
        vkCmdWriteTimestamp(self.primary_command_buffer, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, query_pool, 1);
        try check_vk(vkEndCommandBuffer(self.primary_command_buffer));

        var submit_info = VkSubmitInfo{
            .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
            .pNext = null,
            .waitSemaphoreCount = 0,
            .pWaitSemaphores = null,
            .pWaitDstStageMask = null,
            .commandBufferCount = 1,
            .pCommandBuffers = @ptrCast(&self.primary_command_buffer),
            .signalSemaphoreCount = 0,
            .pSignalSemaphores = null,
        };
        try check_vk(vkResetFences(self.device, 1, @ptrCast(&self.fence)));
        try check_vk(vkQueueSubmit(self.queue, 1, @ptrCast(&submit_info), self.fence));
        try check_vk(vkWaitForFences(self.device, 1, @ptrCast(&self.fence), VK_TRUE, WAIT_TIMEOUT_NS));

        var results: [2]u64 = .{ 0, 0 };
        try check_vk(vkGetQueryPoolResults(
            self.device,
            query_pool,
            0,
            2,
            @sizeOf(@TypeOf(results)),
            &results,
            @sizeOf(u64),
            VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WAIT_BIT,
        ));
        if (results[1] <= results[0]) return 0;
        return results[1] - results[0];
    }

    fn resolve_kernel_path(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
        const direct = try allocator.dupe(u8, kernel_name);
        if (file_exists(direct)) return direct;
        allocator.free(direct);

        const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
        const rooted = try std.fmt.allocPrint(allocator, "{s}/{s}", .{ root, kernel_name });
        if (file_exists(rooted)) return rooted;
        allocator.free(rooted);

        if (!std.mem.endsWith(u8, kernel_name, ".wgsl")) {
            const with_suffix = try std.fmt.allocPrint(allocator, "{s}/{s}.wgsl", .{ root, kernel_name });
            if (file_exists(with_suffix)) return with_suffix;
            allocator.free(with_suffix);
        }
        return error.ShaderCompileFailed;
    }

    fn resolve_kernel_spirv_path(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
        const source_path = try self.resolve_kernel_path(allocator, kernel_name);
        defer allocator.free(source_path);

        if (std.mem.endsWith(u8, source_path, ".spv") or std.mem.endsWith(u8, source_path, ".spirv")) {
            return try allocator.dupe(u8, source_path);
        }

        const sibling_spv = try std.fmt.allocPrint(allocator, "{s}.spv", .{source_path});
        if (file_exists(sibling_spv)) return sibling_spv;
        allocator.free(sibling_spv);

        if (std.mem.lastIndexOfScalar(u8, source_path, '.')) |idx| {
            const replaced = try std.fmt.allocPrint(allocator, "{s}.spv", .{source_path[0..idx]});
            if (file_exists(replaced)) return replaced;
            allocator.free(replaced);
        }

        return error.UnsupportedFeature;
    }
};

fn queue_selection_score(selection: QueueFamilySelection) u64 {
    var score: u64 = 0;
    score +|= @as(u64, selection.queue_count) * 100;
    if (selection.supports_graphics) score +|= 10_000;
    if (selection.timestamp_valid_bits > 0) score +|= 1_000;
    return score;
}

fn descriptor_type_for_binding(binding: model.KernelBinding) !u32 {
    return switch (binding.resource_kind) {
        .buffer => switch (binding.buffer_type) {
            model.WGPUBufferBindingType_Uniform => VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
            model.WGPUBufferBindingType_Storage,
            model.WGPUBufferBindingType_ReadOnlyStorage,
            => VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
            else => error.UnsupportedFeature,
        },
        .texture => VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE,
        .storage_texture => VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
    };
}

fn validate_texture_binding(binding: model.KernelBinding, texture: TextureResource) !void {
    if (binding.texture_view_dimension != model.WGPUTextureViewDimension_Undefined and
        binding.texture_view_dimension != model.WGPUTextureViewDimension_2D) return error.UnsupportedFeature;
    if (binding.texture_multisampled) return error.UnsupportedFeature;
    if (binding.texture_aspect != model.WGPUTextureAspect_Undefined and
        binding.texture_aspect != model.WGPUTextureAspect_All) return error.UnsupportedFeature;
    if (binding.texture_format != model.WGPUTextureFormat_Undefined and
        binding.texture_format != texture.format) return error.InvalidState;

    switch (binding.resource_kind) {
        .buffer => return error.InvalidArgument,
        .texture => {
            if ((texture.usage & model.WGPUTextureUsage_TextureBinding) == 0) return error.InvalidState;
            switch (binding.texture_sample_type) {
                model.WGPUTextureSampleType_Undefined,
                model.WGPUTextureSampleType_Float,
                model.WGPUTextureSampleType_UnfilterableFloat,
                => {},
                else => return error.UnsupportedFeature,
            }
        },
        .storage_texture => {
            if ((texture.usage & model.WGPUTextureUsage_StorageBinding) == 0) return error.InvalidState;
            switch (binding.storage_texture_access) {
                model.WGPUStorageTextureAccess_Undefined,
                model.WGPUStorageTextureAccess_WriteOnly,
                => {},
                else => return error.UnsupportedFeature,
            }
        },
    }
}

fn descriptor_range(binding: model.KernelBinding, buffer_size: u64) !u64 {
    if (binding.resource_kind != .buffer) return error.UnsupportedFeature;
    if (binding.buffer_size == model.WGPUWholeSize) {
        if (binding.buffer_offset > buffer_size) return error.InvalidArgument;
        return VK_WHOLE_SIZE;
    }
    if (binding.buffer_size == 0) return error.InvalidArgument;
    const end = std.math.add(u64, binding.buffer_offset, binding.buffer_size) catch return error.InvalidArgument;
    if (end > buffer_size) return error.InvalidArgument;
    return binding.buffer_size;
}

fn effective_texture_usage(requested: model.WGPUFlags) model.WGPUFlags {
    if (requested == 0) return DEFAULT_RUNTIME_TEXTURE_USAGE;
    return requested | REQUIRED_TEXTURE_UPLOAD_USAGE;
}

const TextureTransitionSource = struct {
    src_access_mask: u32,
    src_stage: u32,
};

fn texture_transition_source(layout: u32) TextureTransitionSource {
    return switch (layout) {
        VK_IMAGE_LAYOUT_UNDEFINED => .{
            .src_access_mask = 0,
            .src_stage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
        },
        VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL => .{
            .src_access_mask = VK_ACCESS_TRANSFER_WRITE_BIT,
            .src_stage = VK_PIPELINE_STAGE_TRANSFER_BIT,
        },
        VK_IMAGE_LAYOUT_GENERAL => .{
            .src_access_mask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT,
            .src_stage = VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        },
        else => .{
            .src_access_mask = 0,
            .src_stage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
        },
    };
}

fn compute_layout_hash(bindings: ?[]const model.KernelBinding) u64 {
    var hasher = std.hash.Wyhash.init(0);
    if (bindings) |bs| {
        for (bs) |binding| {
            hasher.update(std.mem.asBytes(&binding.group));
            hasher.update(std.mem.asBytes(&binding.binding));
            hasher.update(std.mem.asBytes(&binding.resource_kind));
            hasher.update(std.mem.asBytes(&binding.buffer_type));
            hasher.update(std.mem.asBytes(&binding.texture_sample_type));
            hasher.update(std.mem.asBytes(&binding.texture_view_dimension));
            hasher.update(std.mem.asBytes(&binding.storage_texture_access));
            hasher.update(std.mem.asBytes(&binding.texture_format));
            hasher.update(std.mem.asBytes(&binding.texture_multisampled));
        }
    }
    return hasher.final();
}

fn texture_format_to_vk(format: model.WGPUTextureFormat) !u32 {
    return switch (format) {
        model.WGPUTextureFormat_RGBA8Unorm => VK_FORMAT_R8G8B8A8_UNORM,
        else => error.UnsupportedFeature,
    };
}

fn image_usage_for_texture(usage: model.WGPUFlags) u32 {
    var out: u32 = VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    if ((usage & model.WGPUTextureUsage_TextureBinding) != 0) out |= VK_IMAGE_USAGE_SAMPLED_BIT;
    if ((usage & model.WGPUTextureUsage_StorageBinding) != 0) out |= VK_IMAGE_USAGE_STORAGE_BIT;
    if ((usage & model.WGPUTextureUsage_CopySrc) != 0) out |= VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    if ((usage & model.WGPUTextureUsage_CopyDst) != 0) out |= VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    return out;
}

fn bytes_per_pixel_for_texture_format(format: model.WGPUTextureFormat) u32 {
    return switch (format) {
        model.WGPUTextureFormat_RGBA8Unorm => 4,
        else => 4,
    };
}

fn compute_pipeline_hash(
    words: []const u32,
    entry_point: ?[]const u8,
    bindings: ?[]const model.KernelBinding,
) u64 {
    var hasher = std.hash.Wyhash.init(0);
    const layout_hash = compute_layout_hash(bindings);
    hasher.update(std.mem.sliceAsBytes(words));
    hasher.update(entry_point orelse "main");
    hasher.update(std.mem.asBytes(&layout_hash));
    return hasher.final();
}

fn file_exists(path: []const u8) bool {
    std.fs.cwd().access(path, .{}) catch return false;
    return true;
}

fn words_from_spirv_bytes(allocator: std.mem.Allocator, bytes: []const u8) ![]u32 {
    if (bytes.len == 0 or (bytes.len % 4) != 0) return error.ShaderCompileFailed;

    const words = try allocator.alloc(u32, bytes.len / 4);
    errdefer allocator.free(words);
    for (words, 0..) |*word, i| {
        const start = i * 4;
        const chunk: *const [4]u8 = @ptrCast(bytes[start .. start + 4].ptr);
        word.* = std.mem.readInt(u32, chunk, .little);
    }
    if (words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
    return words;
}

pub fn upload_uses_fast_path(
    upload_path_policy: backend_policy.UploadPathPolicy,
    mode: webgpu.UploadBufferUsageMode,
    bytes: u64,
) bool {
    return classify_upload_path(upload_path_policy, mode, bytes) == .fast_mapped;
}

pub fn upload_uses_direct_path(
    upload_path_policy: backend_policy.UploadPathPolicy,
    mode: webgpu.UploadBufferUsageMode,
    bytes: u64,
) bool {
    return classify_upload_path(upload_path_policy, mode, bytes) == .direct_mapped;
}

fn classify_upload_path(
    upload_path_policy: backend_policy.UploadPathPolicy,
    mode: webgpu.UploadBufferUsageMode,
    bytes: u64,
) UploadPathKind {
    if (upload_path_policy == .staged_copy_only) return .staged_copy;
    if (mode == .copy_dst and bytes <= FAST_UPLOAD_BUFFER_MAX_BYTES) return .fast_mapped;
    if (mode == .copy_dst and bytes <= DIRECT_UPLOAD_BUFFER_MAX_BYTES) return .direct_mapped;
    return .staged_copy;
}

fn bounded_upload_fill_len(bytes: u64) usize {
    return @min(@as(usize, @intCast(bytes)), MAX_UPLOAD_ZERO_FILL_BYTES);
}

fn check_vk(result: VkResult) common_errors.BackendNativeError!void {
    if (result == VK_SUCCESS) return;
    return map_vk_result(result);
}

fn map_vk_result(result: VkResult) common_errors.BackendNativeError {
    return switch (result) {
        -7, -9, -10, -11 => error.UnsupportedFeature,
        else => error.InvalidState,
    };
}

const VkPool = std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry));

fn vk_pool_pop(pool: *VkPool, size: u64) ?VkPoolEntry {
    if (pool.getPtr(size)) |list| {
        if (list.items.len > 0) return list.pop();
    }
    return null;
}

fn hot_pool_pop(entry: *?VkPoolEntry, size_slot: *u64, size: u64) ?VkPoolEntry {
    if (size <= HOT_UPLOAD_POOL_CACHE_MAX_BYTES and entry.* != null and size_slot.* == size) {
        const out = entry.*;
        entry.* = null;
        size_slot.* = 0;
        return out;
    }
    return null;
}

fn hot_pool_store(entry: *?VkPoolEntry, size_slot: *u64, size: u64, value: VkPoolEntry) bool {
    if (size > HOT_UPLOAD_POOL_CACHE_MAX_BYTES or entry.* != null) return false;
    entry.* = value;
    size_slot.* = size;
    return true;
}

fn vk_pool_push_or_destroy(pool: *VkPool, allocator: std.mem.Allocator, device: VkDevice, size: u64, entry: VkPoolEntry) void {
    const gop = pool.getOrPut(allocator, size) catch {
        if (entry.mapped != null) vkUnmapMemory(device, entry.memory);
        vkDestroyBuffer(device, entry.buffer, null);
        vkFreeMemory(device, entry.memory, null);
        return;
    };
    if (!gop.found_existing) gop.value_ptr.* = .{};
    if (gop.value_ptr.items.len >= MAX_POOL_ENTRIES_PER_SIZE) {
        if (entry.mapped != null) vkUnmapMemory(device, entry.memory);
        vkDestroyBuffer(device, entry.buffer, null);
        vkFreeMemory(device, entry.memory, null);
        return;
    }
    gop.value_ptr.append(allocator, entry) catch {
        if (entry.mapped != null) vkUnmapMemory(device, entry.memory);
        vkDestroyBuffer(device, entry.buffer, null);
        vkFreeMemory(device, entry.memory, null);
    };
}

fn release_pool_entry(device: VkDevice, entry: ?VkPoolEntry) void {
    if (entry) |value| {
        if (value.mapped != null) vkUnmapMemory(device, value.memory);
        vkDestroyBuffer(device, value.buffer, null);
        vkFreeMemory(device, value.memory, null);
    }
}

fn vk_release_pool(pool: *VkPool, allocator: std.mem.Allocator, device: VkDevice) void {
    var it = pool.valueIterator();
    while (it.next()) |list| {
        for (list.items) |entry| {
            if (entry.mapped != null) vkUnmapMemory(device, entry.memory);
            vkDestroyBuffer(device, entry.buffer, null);
            vkFreeMemory(device, entry.memory, null);
        }
        var m = list.*;
        m.deinit(allocator);
    }
    pool.deinit(allocator);
}
