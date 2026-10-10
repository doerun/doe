#define _GNU_SOURCE
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
/* Exploratory process-wide call attribution. No timing or qualification claim. */
struct Cost { uint64_t calls, ns; };
static struct Cost costs[5];
static uint64_t now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (uint64_t)t.tv_sec*1000000000+t.tv_nsec; }
#define START(name) static PFN_##name real; if(!real) real=(PFN_##name)dlsym(RTLD_NEXT,#name); uint64_t start=now()
#define END(i) costs[i].calls++; costs[i].ns+=now()-start
VkResult vkAllocateMemory(VkDevice d,const VkMemoryAllocateInfo *i,const VkAllocationCallbacks *a,VkDeviceMemory *m) { START(vkAllocateMemory);VkResult r=real(d,i,a,m);END(0);return r; }
void vkFreeMemory(VkDevice d,VkDeviceMemory m,const VkAllocationCallbacks *a) { START(vkFreeMemory);real(d,m,a);END(1); }
VkResult vkMapMemory(VkDevice d,VkDeviceMemory m,VkDeviceSize o,VkDeviceSize s,VkMemoryMapFlags f,void **p) { START(vkMapMemory);VkResult r=real(d,m,o,s,f,p);END(2);return r; }
void vkUnmapMemory(VkDevice d,VkDeviceMemory m) { START(vkUnmapMemory);real(d,m);END(3); }
void vkDestroyDescriptorPool(VkDevice d,VkDescriptorPool p,const VkAllocationCallbacks *a) { START(vkDestroyDescriptorPool);real(d,p,a);END(4); }
__attribute__((destructor)) static void report(void) {
 const char *names[]={"vkAllocateMemory","vkFreeMemory","vkMapMemory","vkUnmapMemory","vkDestroyDescriptorPool"};
 for(int i=0;i<5;i++) fprintf(stderr,"NativeCost %s %llu %llu\n",names[i],(unsigned long long)costs[i].calls,(unsigned long long)costs[i].ns);
}
