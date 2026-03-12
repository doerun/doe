// Shared Vulkan type definitions for the Doe Vulkan backend.
// All Vulkan opaque handle types are defined here to ensure type identity
// across modules (each `opaque {}` is unique in Zig).

pub const VkResult = i32;
pub const VkBool32 = u32;
pub const VkFlags = u32;
pub const VkDeviceSize = u64;
pub const VkStructureType = i32;

pub const VkInstance = ?*opaque {};
pub const VkPhysicalDevice = ?*opaque {};
pub const VkDevice = ?*opaque {};
pub const VkQueue = ?*opaque {};
pub const VkCommandBuffer = ?*opaque {};
pub const VkAllocationCallbacks = opaque {};

pub const VkPipelineCache = u64;
pub const VkCommandPool = u64;
pub const VkFence = u64;
pub const VkBuffer = u64;
pub const VkDeviceMemory = u64;
pub const VkShaderModule = u64;
pub const VkPipelineLayout = u64;
pub const VkPipeline = u64;
pub const VkQueryPool = u64;
pub const VkDescriptorSetLayout = u64;
pub const VkDescriptorPool = u64;
pub const VkDescriptorSet = u64;
pub const VkImage = u64;
pub const VkImageView = u64;
pub const VkSemaphore = u64;
pub const VkSurfaceKHR = u64;
pub const VkSwapchainKHR = u64;

pub const VK_NULL_U64: u64 = 0;

pub const VK_SUCCESS: i32 = 0;
pub const VK_TRUE: u32 = 1;
pub const VK_FALSE: u32 = 0;
