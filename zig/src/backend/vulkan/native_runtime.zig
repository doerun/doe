const std = @import("std");
const model = @import("../../model.zig");
const backend_policy = @import("../backend_policy.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const webgpu = @import("../../webgpu_ffi.zig");

// Vulkan upload path should follow device allocation limits, not an artificial
// 64MB runtime cap. Let allocation/driver failure surface explicitly.
const MAX_UPLOAD_BYTES: u64 = 0; // retained for parity with other backends
const MAX_UPLOAD_ZERO_FILL_BYTES: usize = 1024 * 1024;
const FAST_UPLOAD_BUFFER_MAX_BYTES: u64 = 1024 * 1024;
const DIRECT_UPLOAD_BUFFER_MAX_BYTES: u64 = 4 * 1024 * 1024 * 1024;
const DIRECT_UPLOAD_REUSE_SKIP_ZERO_FILL_MIN_BYTES: u64 = 4 * 1024 * 1024 * 1024;
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
const VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO: i32 = 16;
const VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO: i32 = 17;
const VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO: i32 = 18;
const VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO: i32 = 28;
const VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO: i32 = 30;
const VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO: i32 = 39;
const VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO: i32 = 40;
const VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO: i32 = 42;

const VK_QUEUE_GRAPHICS_BIT: u32 = 0x00000001;
const VK_QUEUE_COMPUTE_BIT: u32 = 0x00000002;
const VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT: u32 = 0x00000002;
const VK_COMMAND_BUFFER_LEVEL_PRIMARY: i32 = 0;
const VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT: u32 = 0x00000001;
const VK_PIPELINE_BIND_POINT_COMPUTE: i32 = 1;
const VK_SHADER_STAGE_COMPUTE_BIT: u32 = 0x00000020;
const VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT: u32 = 0x00000800;
const VK_QUERY_TYPE_TIMESTAMP: u32 = 2;
const VK_QUERY_RESULT_64_BIT: u32 = 0x00000001;
const VK_QUERY_RESULT_WAIT_BIT: u32 = 0x00000002;

const VK_BUFFER_USAGE_TRANSFER_SRC_BIT: u32 = 0x00000001;
const VK_BUFFER_USAGE_TRANSFER_DST_BIT: u32 = 0x00000002;
const VK_BUFFER_USAGE_STORAGE_BUFFER_BIT: u32 = 0x00000020;

const VK_SHARING_MODE_EXCLUSIVE: i32 = 0;
const VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT: u32 = 0x00000001;
const VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT: u32 = 0x00000002;
const VK_MEMORY_PROPERTY_HOST_COHERENT_BIT: u32 = 0x00000004;

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
extern fn vkCmdBindPipeline(commandBuffer: VkCommandBuffer, pipelineBindPoint: i32, pipeline: VkPipeline) callconv(.c) void;
extern fn vkCmdDispatch(commandBuffer: VkCommandBuffer, groupCountX: u32, groupCountY: u32, groupCountZ: u32) callconv(.c) void;
extern fn vkCmdCopyBuffer(commandBuffer: VkCommandBuffer, srcBuffer: VkBuffer, dstBuffer: VkBuffer, regionCount: u32, pRegions: [*]const VkBufferCopy) callconv(.c) void;
extern fn vkCreateBuffer(device: VkDevice, pCreateInfo: *const VkBufferCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pBuffer: *VkBuffer) callconv(.c) VkResult;
extern fn vkDestroyBuffer(device: VkDevice, buffer: VkBuffer, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkGetBufferMemoryRequirements(device: VkDevice, buffer: VkBuffer, pMemoryRequirements: *VkMemoryRequirements) callconv(.c) void;
extern fn vkAllocateMemory(device: VkDevice, pAllocateInfo: *const VkMemoryAllocateInfo, pAllocator: ?*const VkAllocationCallbacks, pMemory: *VkDeviceMemory) callconv(.c) VkResult;
extern fn vkFreeMemory(device: VkDevice, memory: VkDeviceMemory, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkBindBufferMemory(device: VkDevice, buffer: VkBuffer, memory: VkDeviceMemory, memoryOffset: VkDeviceSize) callconv(.c) VkResult;
extern fn vkMapMemory(device: VkDevice, memory: VkDeviceMemory, offset: VkDeviceSize, size: VkDeviceSize, flags: VkFlags, ppData: *?*anyopaque) callconv(.c) VkResult;
extern fn vkUnmapMemory(device: VkDevice, memory: VkDeviceMemory) callconv(.c) void;
extern fn vkGetPhysicalDeviceMemoryProperties(physicalDevice: VkPhysicalDevice, pMemoryProperties: *VkPhysicalDeviceMemoryProperties) callconv(.c) void;
extern fn vkCreateShaderModule(device: VkDevice, pCreateInfo: *const VkShaderModuleCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pShaderModule: *VkShaderModule) callconv(.c) VkResult;
extern fn vkDestroyShaderModule(device: VkDevice, shaderModule: VkShaderModule, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkCreatePipelineLayout(device: VkDevice, pCreateInfo: *const VkPipelineLayoutCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pPipelineLayout: *VkPipelineLayout) callconv(.c) VkResult;
extern fn vkDestroyPipelineLayout(device: VkDevice, pipelineLayout: VkPipelineLayout, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
extern fn vkCreateComputePipelines(device: VkDevice, pipelineCache: VkPipelineCache, createInfoCount: u32, pCreateInfos: [*]const VkComputePipelineCreateInfo, pAllocator: ?*const VkAllocationCallbacks, pPipelines: [*]VkPipeline) callconv(.c) VkResult;
extern fn vkDestroyPipeline(device: VkDevice, pipeline: VkPipeline, pAllocator: ?*const VkAllocationCallbacks) callconv(.c) void;
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
    current_shader_hash: u64 = 0,
    fast_upload_buffer: VkBuffer = VK_NULL_U64,
    fast_upload_memory: VkDeviceMemory = VK_NULL_U64,
    fast_upload_capacity: u64 = 0,
    fast_upload_mapped: ?*anyopaque = null,

    pending_uploads: std.ArrayListUnmanaged(PendingUpload) = .{},
    surfaces: std.AutoHashMapUnmanaged(u64, HeadlessSurface) = .{},

    src_pool: std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry)) = .{},
    dst_pool: std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry)) = .{},
    direct_upload_pool: std.AutoHashMapUnmanaged(u64, std.ArrayListUnmanaged(VkPoolEntry)) = .{},

    has_instance: bool = false,
    has_device: bool = false,
    has_command_pool: bool = false,
    has_primary_command_buffer: bool = false,
    has_fence: bool = false,
    has_shader_module: bool = false,
    has_pipeline_layout: bool = false,
    has_pipeline: bool = false,
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
        vk_release_pool(&self.src_pool, self.allocator, self.device);
        vk_release_pool(&self.dst_pool, self.allocator, self.device);
        vk_release_pool(&self.direct_upload_pool, self.allocator, self.device);
        self.release_fast_upload_buffer();
        self.destroy_pipeline_objects();
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
        const path = try self.resolve_kernel_spirv_path(allocator, kernel_name);
        defer allocator.free(path);

        const bytes = std.fs.cwd().readFileAlloc(allocator, path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
        defer allocator.free(bytes);
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

    pub fn set_compute_shader_spirv(self: *NativeVulkanRuntime, words: []const u32) !void {
        if (words.len == 0 or words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
        const hash = std.hash.Wyhash.hash(0, std.mem.sliceAsBytes(words));
        if (self.has_pipeline and hash == self.current_shader_hash) return;
        try self.build_pipeline_for_words(words, hash);
    }

    pub fn rebuild_compute_shader_spirv(self: *NativeVulkanRuntime, words: []const u32) !void {
        if (words.len == 0 or words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
        const hash = std.hash.Wyhash.hash(0, std.mem.sliceAsBytes(words));
        try self.build_pipeline_for_words(words, hash +% 1);
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
            try check_vk(vkResetCommandPool(self.device, self.command_pool, 0));
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
        try self.ensure_pipeline_layout();
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

    fn ensure_pipeline_layout(self: *NativeVulkanRuntime) !void {
        if (self.has_pipeline_layout) return;
        var layout_info = VkPipelineLayoutCreateInfo{ .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, .pNext = null, .flags = 0, .setLayoutCount = 0, .pSetLayouts = null, .pushConstantRangeCount = 0, .pPushConstantRanges = null };
        try check_vk(vkCreatePipelineLayout(self.device, &layout_info, null, &self.pipeline_layout));
        self.has_pipeline_layout = true;
    }

    fn build_pipeline_for_words(self: *NativeVulkanRuntime, words: []const u32, shader_hash: u64) !void {
        try self.ensure_pipeline_layout();
        self.destroy_pipeline_objects();

        var shader_info = VkShaderModuleCreateInfo{ .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, .pNext = null, .flags = 0, .codeSize = words.len * @sizeOf(u32), .pCode = words.ptr };
        try check_vk(vkCreateShaderModule(self.device, &shader_info, null, &self.shader_module));
        self.has_shader_module = true;

        const stage_info = VkPipelineShaderStageCreateInfo{ .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .pNext = null, .flags = 0, .stage = VK_SHADER_STAGE_COMPUTE_BIT, .module = self.shader_module, .pName = MAIN_ENTRY, .pSpecializationInfo = null };
        var pipeline_info = VkComputePipelineCreateInfo{ .sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO, .pNext = null, .flags = 0, .stage = stage_info, .layout = self.pipeline_layout, .basePipelineHandle = VK_NULL_U64, .basePipelineIndex = -1 };
        try check_vk(vkCreateComputePipelines(self.device, VK_NULL_U64, 1, @ptrCast(&pipeline_info), null, @ptrCast(&self.pipeline)));
        self.has_pipeline = true;
        self.current_shader_hash = shader_hash;
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
    }

    fn record_upload_copy(self: *NativeVulkanRuntime, bytes: u64, dst_usage: u32) !PendingUpload {
        try self.ensure_upload_recording();

        var src_buffer: VkBuffer = VK_NULL_U64;
        var dst_buffer: VkBuffer = VK_NULL_U64;
        var src_memory: VkDeviceMemory = VK_NULL_U64;
        var dst_memory: VkDeviceMemory = VK_NULL_U64;
        var src_fresh = true;

        // Try pool first for src (host-visible staging buffer).
        if (vk_pool_pop(&self.src_pool, bytes)) |entry| {
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
        if (vk_pool_pop(&self.dst_pool, bytes)) |entry| {
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
            vk_pool_push_or_destroy(&self.src_pool, self.allocator, self.device, item.byte_count, .{ .buffer = item.src_buffer, .memory = item.src_memory, .mapped = null });
        } else {
            if (item.src_buffer != VK_NULL_U64) vkDestroyBuffer(self.device, item.src_buffer, null);
            if (item.src_memory != VK_NULL_U64) vkFreeMemory(self.device, item.src_memory, null);
        }
        if (item.dst_buffer != VK_NULL_U64 and item.dst_memory != VK_NULL_U64) {
            vk_pool_push_or_destroy(&self.dst_pool, self.allocator, self.device, item.byte_count, .{ .buffer = item.dst_buffer, .memory = item.dst_memory, .mapped = null });
        } else {
            if (item.dst_buffer != VK_NULL_U64) vkDestroyBuffer(self.device, item.dst_buffer, null);
            if (item.dst_memory != VK_NULL_U64) vkFreeMemory(self.device, item.dst_memory, null);
        }
    }

    fn ensure_upload_recording(self: *NativeVulkanRuntime) !void {
        if (self.upload_recording_active) return;
        if (!self.has_deferred_submissions) {
            try check_vk(vkResetCommandPool(self.device, self.command_pool, 0));
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

fn file_exists(path: []const u8) bool {
    std.fs.cwd().access(path, .{}) catch return false;
    return true;
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
