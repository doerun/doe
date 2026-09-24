#define _GNU_SOURCE
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdlib.h>

static int enabled, fail_at, calls;
static int64_t buffers, memories, mappings;
void audit_begin(void) { enabled = 1; fail_at = calls = 0; buffers = memories = mappings = 0; }
void audit_fail(int step) { fail_at = step; calls = 0; }
int64_t audit_buffers(void) { return buffers; }
int64_t audit_memories(void) { return memories; }
int64_t audit_mappings(void) { return mappings; }
void audit_end(void) { enabled = 0; }
static int reject(void) { return enabled && fail_at && ++calls == fail_at; }
#define NEXT(name) PFN_##name real = (PFN_##name)dlsym(RTLD_NEXT, #name); if (!real) abort()
VKAPI_ATTR VkResult VKAPI_CALL vkCreateBuffer(VkDevice d, const VkBufferCreateInfo *i, const VkAllocationCallbacks *a, VkBuffer *b) {
    NEXT(vkCreateBuffer);
    if (reject()) return VK_ERROR_OUT_OF_HOST_MEMORY;
    VkResult r = real(d, i, a, b);
    if (enabled && r == VK_SUCCESS) buffers++;
    return r;
}
VKAPI_ATTR void VKAPI_CALL vkDestroyBuffer(VkDevice d, VkBuffer b, const VkAllocationCallbacks *a) {
    NEXT(vkDestroyBuffer);
    if (enabled && b) buffers--;
    real(d, b, a);
}
VKAPI_ATTR VkResult VKAPI_CALL vkAllocateMemory(VkDevice d, const VkMemoryAllocateInfo *i, const VkAllocationCallbacks *a, VkDeviceMemory *m) {
    NEXT(vkAllocateMemory);
    if (reject()) return VK_ERROR_OUT_OF_HOST_MEMORY;
    VkResult r = real(d, i, a, m);
    if (enabled && r == VK_SUCCESS) memories++;
    return r;
}
VKAPI_ATTR void VKAPI_CALL vkFreeMemory(VkDevice d, VkDeviceMemory m, const VkAllocationCallbacks *a) {
    NEXT(vkFreeMemory);
    if (enabled && m) memories--;
    real(d, m, a);
}
VKAPI_ATTR VkResult VKAPI_CALL vkBindBufferMemory(VkDevice d, VkBuffer b, VkDeviceMemory m, VkDeviceSize o) {
    NEXT(vkBindBufferMemory);
    if (reject()) return VK_ERROR_OUT_OF_HOST_MEMORY;
    return real(d, b, m, o);
}
VKAPI_ATTR VkResult VKAPI_CALL vkMapMemory(VkDevice d, VkDeviceMemory m, VkDeviceSize o, VkDeviceSize s, VkMemoryMapFlags f, void **p) {
    NEXT(vkMapMemory);
    if (reject()) return VK_ERROR_OUT_OF_HOST_MEMORY;
    VkResult r = real(d, m, o, s, f, p);
    if (enabled && r == VK_SUCCESS) mappings++;
    return r;
}
VKAPI_ATTR void VKAPI_CALL vkUnmapMemory(VkDevice d, VkDeviceMemory m) {
    NEXT(vkUnmapMemory);
    if (enabled) mappings--;
    real(d, m);
}
