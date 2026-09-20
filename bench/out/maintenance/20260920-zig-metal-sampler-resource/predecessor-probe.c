
#include <stdint.h>
#include <stdio.h>
#include <math.h>
#include "webgpu.h"
typedef void* MetalHandle;
typedef enum { MTLSamplerMinMagFilterNearest=101, MTLSamplerMinMagFilterLinear } MTLSamplerMinMagFilter;
typedef enum { MTLSamplerMipFilterNearest=201, MTLSamplerMipFilterLinear } MTLSamplerMipFilter;
typedef enum { MTLSamplerAddressModeClampToEdge=301, MTLSamplerAddressModeMirrorClampToEdge,
 MTLSamplerAddressModeRepeat, MTLSamplerAddressModeMirrorRepeat } MTLSamplerAddressMode;
typedef enum { MTLCompareFunctionNever=401, MTLCompareFunctionLess, MTLCompareFunctionEqual,
 MTLCompareFunctionLessEqual, MTLCompareFunctionGreater, MTLCompareFunctionNotEqual,
 MTLCompareFunctionGreaterEqual, MTLCompareFunctionAlways } MTLCompareFunction;
static int failures;
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL: %s\n", #c); ++failures; } } while(0)
static MTLSamplerMinMagFilter wgpu_to_mtl_filter(uint32_t f) {
    return (f == 1) ? MTLSamplerMinMagFilterLinear : MTLSamplerMinMagFilterNearest;
}
static MTLSamplerMipFilter wgpu_to_mtl_mip_filter(uint32_t f) {
    return (f == 1) ? MTLSamplerMipFilterLinear : MTLSamplerMipFilterNearest;
}
static MTLSamplerAddressMode wgpu_to_mtl_addr(uint32_t a) {
    switch (a) {
        case 0: return MTLSamplerAddressModeClampToEdge;
        case 1: return MTLSamplerAddressModeMirrorClampToEdge;
        case 3: return MTLSamplerAddressModeMirrorRepeat;
        default: return MTLSamplerAddressModeRepeat;
    }
}
int main(void) {

CHECK(wgpu_to_mtl_filter(WGPUFilterMode_Nearest) == MTLSamplerMinMagFilterNearest);
CHECK(wgpu_to_mtl_filter(WGPUFilterMode_Linear) == MTLSamplerMinMagFilterLinear);
CHECK(wgpu_to_mtl_mip_filter(WGPUMipmapFilterMode_Nearest) == MTLSamplerMipFilterNearest);
CHECK(wgpu_to_mtl_mip_filter(WGPUMipmapFilterMode_Linear) == MTLSamplerMipFilterLinear);
CHECK(wgpu_to_mtl_addr(WGPUAddressMode_ClampToEdge) == MTLSamplerAddressModeClampToEdge);
CHECK(wgpu_to_mtl_addr(WGPUAddressMode_Repeat) == MTLSamplerAddressModeRepeat);
CHECK(wgpu_to_mtl_addr(WGPUAddressMode_MirrorRepeat) == MTLSamplerAddressModeMirrorRepeat);
CHECK(wgpu_to_mtl_filter(WGPUFilterMode_Undefined) == MTLSamplerMinMagFilterNearest);
CHECK(wgpu_to_mtl_mip_filter(WGPUMipmapFilterMode_Undefined) == MTLSamplerMipFilterNearest);
CHECK(wgpu_to_mtl_addr(WGPUAddressMode_Undefined) == MTLSamplerAddressModeClampToEdge);

printf("translation/admission failures: %d\n", failures); return failures != 0; }
