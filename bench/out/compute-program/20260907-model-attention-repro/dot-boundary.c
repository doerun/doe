/* Diagnostic interposer: retain source rounding boundaries around OpDot sums. */
#define _GNU_SOURCE
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

enum { HEADER_WORDS = 5, OP_TYPE_VOID = 19, OP_DECORATE = 71,
       OP_FADD = 129, OP_DOT = 148, NO_CONTRACTION = 42 };

VKAPI_ATTR VkResult VKAPI_CALL vkCreateShaderModule(VkDevice device,
        const VkShaderModuleCreateInfo *info, const VkAllocationCallbacks *alloc,
        VkShaderModule *module) {
    void *loader = dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL);
    PFN_vkCreateShaderModule real = loader ? (PFN_vkCreateShaderModule)dlsym(loader, "vkCreateShaderModule") : NULL;
    if (!real) return VK_ERROR_INITIALIZATION_FAILED;
    const uint32_t *words = info->pCode;
    size_t count = info->codeSize / sizeof(uint32_t);
    if (count < HEADER_WORDS) return real(device, info, alloc, module);
    uint8_t *kinds = calloc(words[3], 1);
    uint32_t *ids = malloc(count * sizeof(uint32_t));
    if (!kinds || !ids) { free(kinds); free(ids); return VK_ERROR_OUT_OF_HOST_MEMORY; }
    size_t n = 0, insertion = count;
    for (size_t i = HEADER_WORDS; i < count;) {
        uint32_t length = words[i] >> 16, op = words[i] & 0xffff;
        if (!length || i + length > count) { free(kinds); free(ids); return VK_ERROR_INITIALIZATION_FAILED; }
        if (op >= OP_TYPE_VOID && op <= 39 && insertion == count) insertion = i;
        if (op == OP_DOT && length == 5 && words[i+2] < words[3]) kinds[words[i+2]] = 1;
        i += length;
    }
    for (size_t i = HEADER_WORDS; i < count; i += words[i] >> 16) {
        uint32_t length = words[i] >> 16, op = words[i] & 0xffff;
        if (op == OP_FADD && length == 5 && words[i+3] < words[3] && words[i+4] < words[3]
                && (kinds[words[i+3]] || kinds[words[i+4]])) ids[n++] = words[i+2];
    }
#ifdef DOE_REPRO_DONT_UNROLL
    n = 0;
#endif
    uint32_t *patched = malloc((count + 3*n) * sizeof(uint32_t));
    if (!patched) { free(kinds); free(ids); return VK_ERROR_OUT_OF_HOST_MEMORY; }
    memcpy(patched, words, insertion * sizeof(uint32_t));
    for (size_t i = 0; i < n; i++) {
        patched[insertion+3*i] = (3u << 16) | OP_DECORATE;
        patched[insertion+3*i+1] = ids[i];
        patched[insertion+3*i+2] = NO_CONTRACTION;
    }
    memcpy(patched + insertion + 3*n, words + insertion, (count - insertion) * sizeof(uint32_t));
    VkShaderModuleCreateInfo changed = *info;
    changed.codeSize = (count + 3*n) * sizeof(uint32_t);
    changed.pCode = patched;
#ifdef DOE_REPRO_DONT_UNROLL
    size_t loops = 0;
    for (size_t i = HEADER_WORDS; i < count; i += patched[i] >> 16) {
        if ((patched[i] & 0xffff) == 246 && (patched[i] >> 16) == 4) {
#ifdef DOE_REPRO_MULTI_DOT_LOOPS
            size_t dots = 0, nested = 0;
            for (size_t j = i + 4; j < count; j += patched[j] >> 16) {
                uint32_t op = patched[j] & 0xffff;
                if (op == 248 && patched[j+1] == patched[i+1]) break;
                dots += op == OP_DOT;
                nested += op == 246;
            }
            if (dots < 2 || nested) continue;
#endif
            patched[i+3] = 2;
            loops++;
        }
    }
    fprintf(stderr, "{\"diagnostic\":\"dont-unroll\",\"loops\":%zu}\n", loops);
#endif
    fprintf(stderr, "{\"diagnostic\":\"dot-add-boundary\",\"decorations\":%zu}\n", n);
    VkResult result = real(device, &changed, alloc, module);
    free(patched); free(kinds); free(ids);
    return result;
}
