const common_errors = @import("../common/errors.zig");
const vk = @import("vk_constants.zig");
const structs = @import("vk_structs.zig");

pub extern fn vkCreateInstance(pCreateInfo: *const structs.VkInstanceCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pInstance: *vk.VkInstance) callconv(.c) vk.VkResult;
pub extern fn vkDestroyInstance(instance: vk.VkInstance, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkEnumeratePhysicalDevices(instance: vk.VkInstance, pPhysicalDeviceCount: *u32, pPhysicalDevices: ?[*]vk.VkPhysicalDevice) callconv(.c) vk.VkResult;
pub extern fn vkGetPhysicalDeviceQueueFamilyProperties(physicalDevice: vk.VkPhysicalDevice, pQueueFamilyPropertyCount: *u32, pQueueFamilyProperties: ?[*]structs.VkQueueFamilyProperties) callconv(.c) void;
pub extern fn vkCreateDevice(physicalDevice: vk.VkPhysicalDevice, pCreateInfo: *const structs.VkDeviceCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pDevice: *vk.VkDevice) callconv(.c) vk.VkResult;
pub extern fn vkDestroyDevice(device: vk.VkDevice, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkGetDeviceQueue(device: vk.VkDevice, queueFamilyIndex: u32, queueIndex: u32, pQueue: *vk.VkQueue) callconv(.c) void;
pub extern fn vkCreateCommandPool(device: vk.VkDevice, pCreateInfo: *const structs.VkCommandPoolCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pCommandPool: *vk.VkCommandPool) callconv(.c) vk.VkResult;
pub extern fn vkDestroyCommandPool(device: vk.VkDevice, commandPool: vk.VkCommandPool, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkAllocateCommandBuffers(device: vk.VkDevice, pAllocateInfo: *const structs.VkCommandBufferAllocateInfo, pCommandBuffers: [*]vk.VkCommandBuffer) callconv(.c) vk.VkResult;
pub extern fn vkResetCommandPool(device: vk.VkDevice, commandPool: vk.VkCommandPool, flags: vk.VkFlags) callconv(.c) vk.VkResult;
pub extern fn vkCreateFence(device: vk.VkDevice, pCreateInfo: *const structs.VkFenceCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pFence: *vk.VkFence) callconv(.c) vk.VkResult;
pub extern fn vkDestroyFence(device: vk.VkDevice, fence: vk.VkFence, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkResetFences(device: vk.VkDevice, fenceCount: u32, pFences: [*]const vk.VkFence) callconv(.c) vk.VkResult;
pub extern fn vkWaitForFences(device: vk.VkDevice, fenceCount: u32, pFences: [*]const vk.VkFence, waitAll: vk.VkBool32, timeout: u64) callconv(.c) vk.VkResult;
pub extern fn vkQueueSubmit(queue: vk.VkQueue, submitCount: u32, pSubmits: [*]const structs.VkSubmitInfo, fence: vk.VkFence) callconv(.c) vk.VkResult;
pub extern fn vkQueueWaitIdle(queue: vk.VkQueue) callconv(.c) vk.VkResult;
pub extern fn vkBeginCommandBuffer(commandBuffer: vk.VkCommandBuffer, pBeginInfo: *const structs.VkCommandBufferBeginInfo) callconv(.c) vk.VkResult;
pub extern fn vkEndCommandBuffer(commandBuffer: vk.VkCommandBuffer) callconv(.c) vk.VkResult;
pub extern fn vkResetCommandBuffer(commandBuffer: vk.VkCommandBuffer, flags: vk.VkFlags) callconv(.c) vk.VkResult;
pub extern fn vkCmdBindPipeline(commandBuffer: vk.VkCommandBuffer, pipelineBindPoint: i32, pipeline: vk.VkPipeline) callconv(.c) void;
pub extern fn vkCmdDispatch(commandBuffer: vk.VkCommandBuffer, groupCountX: u32, groupCountY: u32, groupCountZ: u32) callconv(.c) void;
pub extern fn vkCmdCopyBuffer(commandBuffer: vk.VkCommandBuffer, srcBuffer: vk.VkBuffer, dstBuffer: vk.VkBuffer, regionCount: u32, pRegions: [*]const structs.VkBufferCopy) callconv(.c) void;
pub extern fn vkCmdCopyBufferToImage(commandBuffer: vk.VkCommandBuffer, srcBuffer: vk.VkBuffer, dstImage: vk.VkImage, dstImageLayout: u32, regionCount: u32, pRegions: [*]const structs.VkBufferImageCopy) callconv(.c) void;
pub extern fn vkCmdPipelineBarrier(commandBuffer: vk.VkCommandBuffer, srcStageMask: vk.VkFlags, dstStageMask: vk.VkFlags, dependencyFlags: vk.VkFlags, memoryBarrierCount: u32, pMemoryBarriers: ?*const anyopaque, bufferMemoryBarrierCount: u32, pBufferMemoryBarriers: ?*const anyopaque, imageMemoryBarrierCount: u32, pImageMemoryBarriers: ?[*]const structs.VkImageMemoryBarrier) callconv(.c) void;
pub extern fn vkCreateBuffer(device: vk.VkDevice, pCreateInfo: *const structs.VkBufferCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pBuffer: *vk.VkBuffer) callconv(.c) vk.VkResult;
pub extern fn vkDestroyBuffer(device: vk.VkDevice, buffer: vk.VkBuffer, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkGetBufferMemoryRequirements(device: vk.VkDevice, buffer: vk.VkBuffer, pMemoryRequirements: *structs.VkMemoryRequirements) callconv(.c) void;
pub extern fn vkCreateImage(device: vk.VkDevice, pCreateInfo: *const structs.VkImageCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pImage: *vk.VkImage) callconv(.c) vk.VkResult;
pub extern fn vkDestroyImage(device: vk.VkDevice, image: vk.VkImage, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkGetImageMemoryRequirements(device: vk.VkDevice, image: vk.VkImage, pMemoryRequirements: *structs.VkMemoryRequirements) callconv(.c) void;
pub extern fn vkBindImageMemory(device: vk.VkDevice, image: vk.VkImage, memory: vk.VkDeviceMemory, memoryOffset: vk.VkDeviceSize) callconv(.c) vk.VkResult;
pub extern fn vkCreateImageView(device: vk.VkDevice, pCreateInfo: *const structs.VkImageViewCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pView: *vk.VkImageView) callconv(.c) vk.VkResult;
pub extern fn vkDestroyImageView(device: vk.VkDevice, imageView: vk.VkImageView, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkAllocateMemory(device: vk.VkDevice, pAllocateInfo: *const structs.VkMemoryAllocateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pMemory: *vk.VkDeviceMemory) callconv(.c) vk.VkResult;
pub extern fn vkFreeMemory(device: vk.VkDevice, memory: vk.VkDeviceMemory, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkBindBufferMemory(device: vk.VkDevice, buffer: vk.VkBuffer, memory: vk.VkDeviceMemory, memoryOffset: vk.VkDeviceSize) callconv(.c) vk.VkResult;
pub extern fn vkMapMemory(device: vk.VkDevice, memory: vk.VkDeviceMemory, offset: vk.VkDeviceSize, size: vk.VkDeviceSize, flags: vk.VkFlags, ppData: *?*anyopaque) callconv(.c) vk.VkResult;
pub extern fn vkUnmapMemory(device: vk.VkDevice, memory: vk.VkDeviceMemory) callconv(.c) void;
pub extern fn vkGetPhysicalDeviceMemoryProperties(physicalDevice: vk.VkPhysicalDevice, pMemoryProperties: *structs.VkPhysicalDeviceMemoryProperties) callconv(.c) void;
pub extern fn vkCreateShaderModule(device: vk.VkDevice, pCreateInfo: *const structs.VkShaderModuleCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pShaderModule: *vk.VkShaderModule) callconv(.c) vk.VkResult;
pub extern fn vkDestroyShaderModule(device: vk.VkDevice, shaderModule: vk.VkShaderModule, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateDescriptorSetLayout(device: vk.VkDevice, pCreateInfo: *const structs.VkDescriptorSetLayoutCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pSetLayout: *vk.VkDescriptorSetLayout) callconv(.c) vk.VkResult;
pub extern fn vkDestroyDescriptorSetLayout(device: vk.VkDevice, descriptorSetLayout: vk.VkDescriptorSetLayout, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateDescriptorPool(device: vk.VkDevice, pCreateInfo: *const structs.VkDescriptorPoolCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pDescriptorPool: *vk.VkDescriptorPool) callconv(.c) vk.VkResult;
pub extern fn vkDestroyDescriptorPool(device: vk.VkDevice, descriptorPool: vk.VkDescriptorPool, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkAllocateDescriptorSets(device: vk.VkDevice, pAllocateInfo: *const structs.VkDescriptorSetAllocateInfo, pDescriptorSets: [*]vk.VkDescriptorSet) callconv(.c) vk.VkResult;
pub extern fn vkUpdateDescriptorSets(device: vk.VkDevice, descriptorWriteCount: u32, pDescriptorWrites: ?[*]const structs.VkWriteDescriptorSet, descriptorCopyCount: u32, pDescriptorCopies: ?*const anyopaque) callconv(.c) void;
pub extern fn vkCreatePipelineLayout(device: vk.VkDevice, pCreateInfo: *const structs.VkPipelineLayoutCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pPipelineLayout: *vk.VkPipelineLayout) callconv(.c) vk.VkResult;
pub extern fn vkDestroyPipelineLayout(device: vk.VkDevice, pipelineLayout: vk.VkPipelineLayout, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateComputePipelines(device: vk.VkDevice, pipelineCache: vk.VkPipelineCache, createInfoCount: u32, pCreateInfos: [*]const structs.VkComputePipelineCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pPipelines: [*]vk.VkPipeline) callconv(.c) vk.VkResult;
pub extern fn vkDestroyPipeline(device: vk.VkDevice, pipeline: vk.VkPipeline, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCmdBindDescriptorSets(commandBuffer: vk.VkCommandBuffer, pipelineBindPoint: i32, layout: vk.VkPipelineLayout, firstSet: u32, descriptorSetCount: u32, pDescriptorSets: ?[*]const vk.VkDescriptorSet, dynamicOffsetCount: u32, pDynamicOffsets: ?[*]const u32) callconv(.c) void;
pub extern fn vkCreateQueryPool(device: vk.VkDevice, pCreateInfo: *const structs.VkQueryPoolCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pQueryPool: *vk.VkQueryPool) callconv(.c) vk.VkResult;
pub extern fn vkDestroyQueryPool(device: vk.VkDevice, queryPool: vk.VkQueryPool, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCmdWriteTimestamp(commandBuffer: vk.VkCommandBuffer, pipelineStage: vk.VkFlags, queryPool: vk.VkQueryPool, query: u32) callconv(.c) void;
pub extern fn vkGetQueryPoolResults(device: vk.VkDevice, queryPool: vk.VkQueryPool, firstQuery: u32, queryCount: u32, dataSize: usize, pData: ?*anyopaque, stride: vk.VkDeviceSize, flags: vk.VkFlags) callconv(.c) vk.VkResult;
pub extern fn vkCreateRenderPass(device: vk.VkDevice, pCreateInfo: *const structs.VkRenderPassCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pRenderPass: *vk.VkRenderPass) callconv(.c) vk.VkResult;
pub extern fn vkDestroyRenderPass(device: vk.VkDevice, renderPass: vk.VkRenderPass, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateFramebuffer(device: vk.VkDevice, pCreateInfo: *const structs.VkFramebufferCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pFramebuffer: *vk.VkFramebuffer) callconv(.c) vk.VkResult;
pub extern fn vkDestroyFramebuffer(device: vk.VkDevice, framebuffer: vk.VkFramebuffer, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCreateGraphicsPipelines(device: vk.VkDevice, pipelineCache: vk.VkPipelineCache, createInfoCount: u32, pCreateInfos: [*]const structs.VkGraphicsPipelineCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pPipelines: [*]vk.VkPipeline) callconv(.c) vk.VkResult;
pub extern fn vkCreateSampler(device: vk.VkDevice, pCreateInfo: *const structs.VkSamplerCreateInfo, pAllocator: ?*const vk.VkAllocationCallbacks, pSampler: *vk.VkSampler) callconv(.c) vk.VkResult;
pub extern fn vkDestroySampler(device: vk.VkDevice, sampler: vk.VkSampler, pAllocator: ?*const vk.VkAllocationCallbacks) callconv(.c) void;
pub extern fn vkCmdBeginRenderPass(commandBuffer: vk.VkCommandBuffer, pRenderPassBegin: *const structs.VkRenderPassBeginInfo, contents: u32) callconv(.c) void;
pub extern fn vkCmdEndRenderPass(commandBuffer: vk.VkCommandBuffer) callconv(.c) void;
pub extern fn vkCmdSetViewport(commandBuffer: vk.VkCommandBuffer, firstViewport: u32, viewportCount: u32, pViewports: [*]const structs.VkViewport) callconv(.c) void;
pub extern fn vkCmdSetScissor(commandBuffer: vk.VkCommandBuffer, firstScissor: u32, scissorCount: u32, pScissors: [*]const structs.VkRect2D) callconv(.c) void;
pub extern fn vkCmdBindVertexBuffers(commandBuffer: vk.VkCommandBuffer, firstBinding: u32, bindingCount: u32, pBuffers: [*]const vk.VkBuffer, pOffsets: [*]const vk.VkDeviceSize) callconv(.c) void;
pub extern fn vkCmdBindIndexBuffer(commandBuffer: vk.VkCommandBuffer, buffer: vk.VkBuffer, offset: vk.VkDeviceSize, indexType: u32) callconv(.c) void;
pub extern fn vkCmdDraw(commandBuffer: vk.VkCommandBuffer, vertexCount: u32, instanceCount: u32, firstVertex: u32, firstInstance: u32) callconv(.c) void;
pub extern fn vkCmdDrawIndexed(commandBuffer: vk.VkCommandBuffer, indexCount: u32, instanceCount: u32, firstIndex: u32, vertexOffset: i32, firstInstance: u32) callconv(.c) void;

pub fn check_vk(result: vk.VkResult) common_errors.BackendNativeError!void {
    if (result == vk.VK_SUCCESS) return;
    return map_vk_result(result);
}

pub fn map_vk_result(result: vk.VkResult) common_errors.BackendNativeError {
    return switch (result) {
        vk.VK_ERROR_TOO_MANY_OBJECTS,
        vk.VK_ERROR_FORMAT_NOT_SUPPORTED,
        vk.VK_ERROR_FRAGMENTED_POOL,
        vk.VK_ERROR_UNKNOWN,
        => error.UnsupportedFeature,
        else => error.InvalidState,
    };
}

const std = @import("std");

test "check_vk succeeds on VK_SUCCESS" {
    try check_vk(vk.VK_SUCCESS);
}

test "check_vk returns error on failure code" {
    const result = check_vk(vk.VK_ERROR_TOO_MANY_OBJECTS);
    try std.testing.expectEqual(error.UnsupportedFeature, result);
}

test "map_vk_result maps TOO_MANY_OBJECTS to UnsupportedFeature" {
    try std.testing.expectEqual(error.UnsupportedFeature, map_vk_result(vk.VK_ERROR_TOO_MANY_OBJECTS));
}

test "map_vk_result maps FORMAT_NOT_SUPPORTED to UnsupportedFeature" {
    try std.testing.expectEqual(error.UnsupportedFeature, map_vk_result(vk.VK_ERROR_FORMAT_NOT_SUPPORTED));
}

test "map_vk_result maps FRAGMENTED_POOL to UnsupportedFeature" {
    try std.testing.expectEqual(error.UnsupportedFeature, map_vk_result(vk.VK_ERROR_FRAGMENTED_POOL));
}

test "map_vk_result maps UNKNOWN to UnsupportedFeature" {
    try std.testing.expectEqual(error.UnsupportedFeature, map_vk_result(vk.VK_ERROR_UNKNOWN));
}

test "map_vk_result maps other errors to InvalidState" {
    // VK_ERROR_OUT_OF_HOST_MEMORY = -1, not in the UnsupportedFeature set
    try std.testing.expectEqual(error.InvalidState, map_vk_result(-1));
    // VK_ERROR_OUT_OF_DEVICE_MEMORY = -2
    try std.testing.expectEqual(error.InvalidState, map_vk_result(-2));
}
