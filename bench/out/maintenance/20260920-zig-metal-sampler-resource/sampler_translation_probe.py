"""Compile actual bridge translation/admission functions against a recording sink.

This does not compile Objective-C or execute Metal. Symbolic native constants are
intentionally distinct from WebGPU values; Apple SDK/driver behavior is untested.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile

BRIDGE = "runtime/zig/src/backend/metal/metal_bridge.m"
BASE = "5e0e4dd969ea88bc3755e268a193f6c6b5c0fb59"


def function(source: str, name: str) -> str:
    marker = source.index(name + "(")
    start = source.rfind("\n", 0, marker) + 1
    opening = source.index("{", marker)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


PRELUDE = r'''
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
'''
SINK = r'''
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
'''
COMMON = r'''
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
'''
CURRENT = r'''
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
'''


def run_probe(root: Path, output: Path, source: str, current: bool) -> int:
    label = "current" if current else "predecessor"
    names = ["wgpu_to_mtl_filter", "wgpu_to_mtl_mip_filter", "wgpu_to_mtl_addr"]
    code = PRELUDE + "\n".join(function(source, name) for name in names)
    if current:
        code += function(source, "wgpu_to_mtl_compare") + SINK
        code += function(source, "metal_bridge_device_new_sampler_with_compare")
    code += "\nint main(void) {\n" + COMMON + (CURRENT if current else "")
    code += '\nprintf("translation/admission failures: %d\\n", failures); return failures != 0; }\n'
    path = output / f"{label}-probe.c"
    path.write_text(code, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="doe-sampler-probe-") as directory:
        binary = Path(directory) / "probe"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-I", str(root / "runtime/zig/vendor/webgpu-headers"), str(path), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
    (output / f"{label}-translation.log").write_text(
        result.stdout + result.stderr + f"exitCode={result.returncode}\n", encoding="utf-8")
    print(f"{label}: exit={result.returncode}\n{result.stdout}{result.stderr}", end="")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Doe checkout root")
    parser.add_argument("--base-ref", default=BASE, help="Pre-repair commit to reproduce")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = Path(__file__).resolve().parent
    old = subprocess.check_output(["git", "show", f"{args.base_ref}:{BRIDGE}"], cwd=root, text=True)
    predecessor = run_probe(root, output, old, False)
    current = run_probe(root, output, (root / BRIDGE).read_text(encoding="utf-8"), True)
    return int(predecessor == 0 or current != 0)


if __name__ == "__main__":
    raise SystemExit(main())
