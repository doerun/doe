#define _GNU_SOURCE
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Test-only interposition. All accepted operations execute on the real driver.
static const char *fault = "";
static unsigned delayed, violations, acquisitions, presentations, signals, failures;
static unsigned live_swapchains, live_fences, live_semaphores, live_views;
static VkFence acquisition, presentation;
static VkSemaphore finished;
static int acquisition_pending, presentation_pending, signal_pending;
#define REAL(name) PFN_##name real = (PFN_##name)dlsym(RTLD_NEXT, #name)
#define CHECK(condition) do { if (!(condition)) { ++violations; fprintf(stderr,"order violation line=%d\n",__LINE__); } } while (0)
void doe_surface_test_arm(const char *mode) { fault = mode; delayed = 3; }
static int take(const char *name) { if (strcmp(fault,name)) return 0; fault=""; ++failures; return 1; }
VKAPI_ATTR VkResult VKAPI_CALL vkCreateImageView(VkDevice d,const VkImageViewCreateInfo *i,const VkAllocationCallbacks *a,VkImageView *v) {
    if(take("create-view")) return VK_ERROR_OUT_OF_HOST_MEMORY;
    REAL(vkCreateImageView); VkResult r=real(d,i,a,v); if(r==VK_SUCCESS) ++live_views; return r;
}
VKAPI_ATTR void VKAPI_CALL vkDestroyImageView(VkDevice d,VkImageView v,const VkAllocationCallbacks *a) {
    CHECK(live_views); --live_views; REAL(vkDestroyImageView); real(d,v,a);
}
VKAPI_ATTR void VKAPI_CALL vkGetPhysicalDeviceFeatures2(VkPhysicalDevice d,VkPhysicalDeviceFeatures2 *f) {
    REAL(vkGetPhysicalDeviceFeatures2); real(d,f);
    if (!strcmp(fault,"unsupported")) for (VkBaseOutStructure *p=f->pNext; p; p=p->pNext)
        if (p->sType==VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SWAPCHAIN_MAINTENANCE_1_FEATURES_EXT) {
            ((VkPhysicalDeviceSwapchainMaintenance1FeaturesEXT *)p)->swapchainMaintenance1=VK_FALSE; take("unsupported");
        }
}
VKAPI_ATTR VkResult VKAPI_CALL vkCreateSwapchainKHR(VkDevice d,const VkSwapchainCreateInfoKHR *i,const VkAllocationCallbacks *a,VkSwapchainKHR *s) {
    REAL(vkCreateSwapchainKHR); VkResult r=real(d,i,a,s); if(r==VK_SUCCESS) ++live_swapchains; return r;
}
VKAPI_ATTR void VKAPI_CALL vkDestroySwapchainKHR(VkDevice d,VkSwapchainKHR s,const VkAllocationCallbacks *a) {
    CHECK(!acquisition_pending && !presentation_pending); CHECK(live_swapchains); --live_swapchains;
    REAL(vkDestroySwapchainKHR); real(d,s,a);
}
VKAPI_ATTR VkResult VKAPI_CALL vkGetSwapchainImagesKHR(VkDevice d,VkSwapchainKHR s,uint32_t *n,VkImage *images) {
    if(take("images")) return VK_ERROR_OUT_OF_HOST_MEMORY;
    REAL(vkGetSwapchainImagesKHR); return real(d,s,n,images);
}
VKAPI_ATTR VkResult VKAPI_CALL vkCreateFence(VkDevice d,const VkFenceCreateInfo *i,const VkAllocationCallbacks *a,VkFence *f) {
    if(take("create-fence")) return VK_ERROR_OUT_OF_HOST_MEMORY;
    REAL(vkCreateFence); VkResult r=real(d,i,a,f); if(r==VK_SUCCESS) ++live_fences; return r;
}
VKAPI_ATTR void VKAPI_CALL vkDestroyFence(VkDevice d,VkFence f,const VkAllocationCallbacks *a) {
    CHECK(f!=acquisition || !acquisition_pending); CHECK(f!=presentation || !presentation_pending);
    CHECK(live_fences); --live_fences; REAL(vkDestroyFence); real(d,f,a);
    if(f==acquisition) acquisition=VK_NULL_HANDLE;
    if(f==presentation) presentation=VK_NULL_HANDLE;
}
VKAPI_ATTR VkResult VKAPI_CALL vkCreateSemaphore(VkDevice d,const VkSemaphoreCreateInfo *i,const VkAllocationCallbacks *a,VkSemaphore *s) {
    if(take("create-semaphore")) return VK_ERROR_OUT_OF_HOST_MEMORY;
    REAL(vkCreateSemaphore); VkResult r=real(d,i,a,s); if(r==VK_SUCCESS) ++live_semaphores;
    if(r==VK_SUCCESS && !i->pNext) finished=*s;
    return r;
}
VKAPI_ATTR void VKAPI_CALL vkDestroySemaphore(VkDevice d,VkSemaphore s,const VkAllocationCallbacks *a) {
    CHECK(s!=finished || !presentation_pending); CHECK(live_semaphores); --live_semaphores;
    REAL(vkDestroySemaphore); real(d,s,a); if(s==finished) { finished=VK_NULL_HANDLE; signal_pending=0; }
}
VKAPI_ATTR VkResult VKAPI_CALL vkAcquireNextImageKHR(VkDevice d,VkSwapchainKHR s,uint64_t timeout,VkSemaphore sem,VkFence fence,uint32_t *index) {
    CHECK(fence && !sem); CHECK(!acquisition_pending && !presentation_pending && !signal_pending);
    REAL(vkAcquireNextImageKHR); VkResult r=real(d,s,timeout,sem,fence,index);
    if(r==VK_SUCCESS || r==VK_SUBOPTIMAL_KHR) { acquisition=fence; acquisition_pending=1; ++acquisitions; }
    return r;
}
VKAPI_ATTR VkResult VKAPI_CALL vkWaitForFences(VkDevice d,uint32_t n,const VkFence *f,VkBool32 all,uint64_t timeout) {
    if(n==1 && ((*f==acquisition && !strcmp(fault,"acquire-wait")) || (*f==presentation && !strcmp(fault,"present-wait")))) {
        if(delayed) { --delayed; ++failures; return VK_TIMEOUT; } fault="";
    }
    REAL(vkWaitForFences); VkResult r=real(d,n,f,all,timeout);
    if(r==VK_SUCCESS) for(uint32_t x=0;x<n;++x) {
        if(f[x]==acquisition) acquisition_pending=0;
        if(f[x]==presentation) presentation_pending=0;
    }
    if(n==1 && *f==acquisition && take("device-lost")) return VK_ERROR_DEVICE_LOST;
    return r;
}
VKAPI_ATTR VkResult VKAPI_CALL vkQueueSubmit(VkQueue q,uint32_t n,const VkSubmitInfo *infos,VkFence f) {
    CHECK(!acquisition_pending);
    int publishes=0;
    for(uint32_t i=0;i<n;++i) for(uint32_t j=0;j<infos[i].signalSemaphoreCount;++j)
        if(infos[i].pSignalSemaphores[j]==finished) publishes=1;
    if(publishes && take("submit-reject")) return VK_ERROR_OUT_OF_DEVICE_MEMORY;
    if(publishes) CHECK(!signal_pending && !presentation_pending);
    REAL(vkQueueSubmit); VkResult r=real(q,n,infos,f);
    if(publishes && r==VK_SUCCESS) {signal_pending=1; ++signals;}
    return r;
}
VKAPI_ATTR VkResult VKAPI_CALL vkQueuePresentKHR(VkQueue q,const VkPresentInfoKHR *i) {
    CHECK(i->waitSemaphoreCount==1 && i->pWaitSemaphores[0]==finished && signal_pending && !acquisition_pending);
    const VkSwapchainPresentFenceInfoEXT *f=(const VkSwapchainPresentFenceInfoEXT *)i->pNext;
    CHECK(f && f->sType==VK_STRUCTURE_TYPE_SWAPCHAIN_PRESENT_FENCE_INFO_EXT && f->swapchainCount==1 && f->pFences[0]);
    if(take("present-reject")) return VK_ERROR_OUT_OF_HOST_MEMORY;
    REAL(vkQueuePresentKHR); VkResult r=real(q,i);
    presentation=f->pFences[0]; presentation_pending=1; signal_pending=0; ++presentations;
    if(take("outdated")) return VK_ERROR_OUT_OF_DATE_KHR;
    return r;
}
__attribute__((destructor)) static void report(void) {
    CHECK(!live_swapchains && !live_fences && !live_semaphores && !live_views);
    fprintf(stderr,"{\"observer\":true,\"acquires\":%u,\"presents\":%u,\"signals\":%u,\"injectedFailures\":%u,\"violations\":%u,\"liveSwapchains\":%u,\"liveFences\":%u,\"liveSemaphores\":%u,\"liveImageViews\":%u}\n",acquisitions,presentations,signals,failures,violations,live_swapchains,live_fences,live_semaphores,live_views);
    if(violations) abort();
}
