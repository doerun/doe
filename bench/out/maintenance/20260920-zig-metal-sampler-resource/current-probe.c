
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
    return f == WGPUFilterMode_Linear ? MTLSamplerMinMagFilterLinear : MTLSamplerMinMagFilterNearest;
}
static MTLSamplerMipFilter wgpu_to_mtl_mip_filter(uint32_t f) {
    return f == WGPUMipmapFilterMode_Linear ? MTLSamplerMipFilterLinear : MTLSamplerMipFilterNearest;
}
static MTLSamplerAddressMode wgpu_to_mtl_addr(uint32_t a) {
    switch (a) {
        case WGPUAddressMode_Repeat: return MTLSamplerAddressModeRepeat;
        case WGPUAddressMode_MirrorRepeat: return MTLSamplerAddressModeMirrorRepeat;
        default: return MTLSamplerAddressModeClampToEdge;
    }
}static MTLCompareFunction wgpu_to_mtl_compare(uint32_t compare_fn) {
    switch (compare_fn) {
        case 0x00000001: return MTLCompareFunctionNever;
        case 0x00000002: return MTLCompareFunctionLess;
        case 0x00000003: return MTLCompareFunctionEqual;
        case 0x00000004: return MTLCompareFunctionLessEqual;
        case 0x00000005: return MTLCompareFunctionGreater;
        case 0x00000006: return MTLCompareFunctionNotEqual;
        case 0x00000007: return MTLCompareFunctionGreaterEqual;
        case 0x00000008: return MTLCompareFunctionAlways;
        default: return MTLCompareFunctionAlways;
    }
}
static unsigned calls;
static struct { MetalHandle device; MTLSamplerMinMagFilter min, mag;
 MTLSamplerMipFilter mip; MTLSamplerAddressMode u,v,w; float low,high;
 MTLCompareFunction compare; uint16_t anisotropy; } captured;
static int fail_factory;
static MetalHandle new_sampler(MetalHandle device, MTLSamplerMinMagFilter min, MTLSamplerMinMagFilter mag,
 MTLSamplerMipFilter mip, MTLSamplerAddressMode u, MTLSamplerAddressMode v, MTLSamplerAddressMode w,
 float low, float high, MTLCompareFunction compare, uint16_t anisotropy) {
 ++calls; captured.device=device; captured.min=min; captured.mag=mag; captured.mip=mip;
 captured.u=u; captured.v=v; captured.w=w; captured.low=low; captured.high=high;
 captured.compare=compare; captured.anisotropy=anisotropy;
 return fail_factory ? NULL : &captured;
}
MetalHandle metal_bridge_device_new_sampler_with_compare(
    MetalHandle device_h,
    uint32_t min_filter,
    uint32_t mag_filter,
    uint32_t mipmap_filter,
    uint32_t addr_u,
    uint32_t addr_v,
    uint32_t addr_w,
    float lod_min,
    float lod_max,
    uint32_t compare,
    uint16_t max_aniso)
{
    if (min_filter > WGPUFilterMode_Linear || mag_filter > WGPUFilterMode_Linear ||
        mipmap_filter > WGPUMipmapFilterMode_Linear ||
        addr_u > WGPUAddressMode_MirrorRepeat || addr_v > WGPUAddressMode_MirrorRepeat ||
        addr_w > WGPUAddressMode_MirrorRepeat || compare > WGPUCompareFunction_Always) return NULL;
    enum { MAX_SAMPLER_ANISOTROPY = 16 };
    if (!isfinite(lod_min) || !isfinite(lod_max) || lod_min < 0 || lod_max < lod_min ||
        max_aniso == 0 || max_aniso > MAX_SAMPLER_ANISOTROPY) return NULL;
    if (max_aniso > 1 && (min_filter != WGPUFilterMode_Linear ||
        mag_filter != WGPUFilterMode_Linear || mipmap_filter != WGPUMipmapFilterMode_Linear)) return NULL;
    return new_sampler(device_h,
        wgpu_to_mtl_filter(min_filter), wgpu_to_mtl_filter(mag_filter),
        wgpu_to_mtl_mip_filter(mipmap_filter),
        wgpu_to_mtl_addr(addr_u), wgpu_to_mtl_addr(addr_v), wgpu_to_mtl_addr(addr_w),
        lod_min, lod_max,
        compare == WGPUCompareFunction_Undefined ? MTLCompareFunctionNever : wgpu_to_mtl_compare(compare),
        max_aniso);
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

int device;
#define CREATE(a,b,c,d,e,f,g,h,i,j) metal_bridge_device_new_sampler_with_compare(&device,a,b,c,d,e,f,g,h,i,j)
CHECK(CREATE(1,2,2,1,2,3,0,32,WGPUCompareFunction_Less,1) != NULL);
CHECK(captured.device == &device && captured.min == MTLSamplerMinMagFilterNearest);
CHECK(captured.mag == MTLSamplerMinMagFilterLinear && captured.mip == MTLSamplerMipFilterLinear);
CHECK(captured.u == MTLSamplerAddressModeClampToEdge && captured.v == MTLSamplerAddressModeRepeat);
CHECK(captured.w == MTLSamplerAddressModeMirrorRepeat && captured.compare == MTLCompareFunctionLess);
CHECK(captured.low == 0 && captured.high == 32 && captured.anisotropy == 1);
const MTLCompareFunction expected[] = { MTLCompareFunctionNever, MTLCompareFunctionNever,
 MTLCompareFunctionLess, MTLCompareFunctionEqual, MTLCompareFunctionLessEqual, MTLCompareFunctionGreater,
 MTLCompareFunctionNotEqual, MTLCompareFunctionGreaterEqual, MTLCompareFunctionAlways };
for (unsigned compare=0; compare<=WGPUCompareFunction_Always; ++compare) {
 CHECK(CREATE(2,2,2,0,0,0,1,16,compare,16) != NULL);
 CHECK(captured.compare == expected[compare] && captured.anisotropy == 16);
}
CHECK(CREATE(0,0,0,0,0,0,0,32,0,1) != NULL);
CHECK(captured.min == MTLSamplerMinMagFilterNearest && captured.u == MTLSamplerAddressModeClampToEdge);
unsigned before = calls;
CHECK(CREATE(3,1,1,1,1,1,0,32,0,1) == NULL);
CHECK(CREATE(1,3,1,1,1,1,0,32,0,1) == NULL);
CHECK(CREATE(1,1,3,1,1,1,0,32,0,1) == NULL);
CHECK(CREATE(1,1,1,4,1,1,0,32,0,1) == NULL);
CHECK(CREATE(1,1,1,1,4,1,0,32,0,1) == NULL);
CHECK(CREATE(1,1,1,1,1,4,0,32,0,1) == NULL);
CHECK(CREATE(1,1,1,1,1,1,0,32,9,1) == NULL);
CHECK(CREATE(1,1,1,1,1,1,-1,32,0,1) == NULL);
CHECK(CREATE(1,1,1,1,1,1,2,1,0,1) == NULL);
CHECK(CREATE(1,1,1,1,1,1,NAN,32,0,1) == NULL);
CHECK(CREATE(1,1,1,1,1,1,0,INFINITY,0,1) == NULL);
CHECK(CREATE(2,2,2,1,1,1,0,32,0,0) == NULL);
CHECK(CREATE(2,2,2,1,1,1,0,32,0,17) == NULL);
CHECK(CREATE(1,2,2,1,1,1,0,32,0,2) == NULL);
CHECK(CREATE(2,1,2,1,1,1,0,32,0,2) == NULL);
CHECK(CREATE(2,2,1,1,1,1,0,32,0,2) == NULL);
CHECK(calls == before);
fail_factory = 1;
CHECK(CREATE(1,1,1,1,1,1,0,32,0,1) == NULL);
CHECK(calls == before + 1);

printf("translation/admission failures: %d\n", failures); return failures != 0; }
