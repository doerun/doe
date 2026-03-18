#!/usr/bin/env python3
"""Batch-update browser cells in webgpu-spec-index.jsonl based on browser test evidence.

Browser backend = Chromium Track A, where Fawn replaces Dawn as the WebGPU
implementation.  The browser runtime routes through the Doe Zig runtime exposed
via Chromium WebGPU bindings.

Evidence sources:
  - browser/fawn-browser/scripts/webgpu-playwright-smoke.mjs
  - browser/fawn-browser/scripts/webgpu-playwright-layered-bench.mjs
  - browser/fawn-browser/artifacts/ (passing Doe mode results)

Classification rules:
  - "implemented"  = API exercised and verified in browser Playwright tests
  - "partial"      = runtime implements but browser test hasn't fully exercised it
  - "unreviewed"   = no browser evidence at all
  - "out_of_scope" = not applicable to browser path
"""

import json

SPEC_INDEX_PATH = "config/webgpu-spec-index.jsonl"

# ---------------------------------------------------------------------------
# Interfaces with browser test evidence for implementation status.
# ---------------------------------------------------------------------------

INTERFACE_IMPLEMENTED = {
    "GPU",
    "GPUAdapter",
    "GPUBuffer",
    "GPUBindGroup",
    "GPUBindGroupLayout",
    "GPUCanvasContext",
    "GPUCommandBuffer",
    "GPUCommandEncoder",
    "GPUComputePassEncoder",
    "GPUComputePipeline",
    "GPUDevice",
    "GPUMapMode",
    "GPUQueue",
    "GPURenderBundle",
    "GPURenderBundleEncoder",
    "GPURenderPassEncoder",
    "GPURenderPipeline",
    "GPUSampler",
    "GPUShaderModule",
    "GPUShaderStage",
    "GPUTexture",
    "GPUTextureView",
    "GPUBufferUsage",
    "GPUTextureUsage",
}

INTERFACE_PARTIAL = {
    "GPUAdapterInfo",
    "GPUComputePipelineDescriptor",
    "GPUPipelineLayout",
    "GPURenderPipelineDescriptor",
    "GPUSupportedLimits",
}

DICT_IMPLEMENTED = {
    "GPUBindGroupDescriptor",
    "GPUBindGroupEntry",
    "GPUBindGroupLayoutDescriptor",
    "GPUBindGroupLayoutEntry",
    "GPUBlendComponent",
    "GPUBlendState",
    "GPUBufferBinding",
    "GPUBufferBindingLayout",
    "GPUBufferDescriptor",
    "GPUCanvasConfiguration",
    "GPUColorDict",
    "GPUColorTargetState",
    "GPUComputePassDescriptor",
    "GPUDeviceDescriptor",
    "GPUExtent3DDict",
    "GPUFragmentState",
    "GPUMultisampleState",
    "GPUPrimitiveState",
    "GPURenderBundleEncoderDescriptor",
    "GPURenderPassColorAttachment",
    "GPURenderPassDescriptor",
    "GPUSamplerDescriptor",
    "GPUShaderModuleDescriptor",
    "GPUTexelCopyBufferInfo",
    "GPUTexelCopyTextureInfo",
    "GPUTextureDescriptor",
    "GPUVertexState",
}

DICT_PARTIAL = {
    "GPUDepthStencilState",
    "GPUPipelineLayoutDescriptor",
    "GPURenderPassDepthStencilAttachment",
    "GPURenderPassLayout",
    "GPUStencilFaceState",
    "GPUTextureBindingLayout",
    "GPUTextureViewDescriptor",
    "GPUStorageTextureBindingLayout",
    "GPUSamplerBindingLayout",
}

# ---------------------------------------------------------------------------
# Member-level overrides: (InterfaceName, MemberName) -> implemented
# ---------------------------------------------------------------------------

MEMBER_IMPLEMENTED = {
    ("GPU", "requestAdapter"),
    ("GPU", "getPreferredCanvasFormat"),
    ("GPU", "wgslLanguageFeatures"),
    ("GPUAdapter", "requestDevice"),
    ("GPUAdapter", "features"),
    ("GPUAdapter", "info"),
    ("GPUAdapter", "limits"),
    ("GPUDevice", "createBuffer"),
    ("GPUDevice", "createTexture"),
    ("GPUDevice", "createSampler"),
    ("GPUDevice", "createShaderModule"),
    ("GPUDevice", "createComputePipeline"),
    ("GPUDevice", "createComputePipelineAsync"),
    ("GPUDevice", "createRenderPipeline"),
    ("GPUDevice", "createBindGroup"),
    ("GPUDevice", "createBindGroupLayout"),
    ("GPUDevice", "createCommandEncoder"),
    ("GPUDevice", "createRenderBundleEncoder"),
    ("GPUDevice", "features"),
    ("GPUDevice", "limits"),
    ("GPUDevice", "queue"),
    ("GPUDevice", "label"),
    ("GPUQueue", "submit"),
    ("GPUQueue", "writeBuffer"),
    ("GPUQueue", "writeTexture"),
    ("GPUQueue", "onSubmittedWorkDone"),
    ("GPUQueue", "label"),
    ("GPUBuffer", "mapAsync"),
    ("GPUBuffer", "getMappedRange"),
    ("GPUBuffer", "unmap"),
    ("GPUBuffer", "destroy"),
    ("GPUBuffer", "size"),
    ("GPUBuffer", "usage"),
    ("GPUBuffer", "label"),
    ("GPUTexture", "createView"),
    ("GPUTexture", "destroy"),
    ("GPUTexture", "width"),
    ("GPUTexture", "height"),
    ("GPUTexture", "depthOrArrayLayers"),
    ("GPUTexture", "format"),
    ("GPUTexture", "sampleCount"),
    ("GPUTexture", "mipLevelCount"),
    ("GPUTexture", "dimension"),
    ("GPUTexture", "usage"),
    ("GPUTexture", "label"),
    ("GPUTextureView", "label"),
    ("GPUShaderModule", "label"),
    ("GPUComputePipeline", "getBindGroupLayout"),
    ("GPUComputePipeline", "label"),
    ("GPURenderPipeline", "getBindGroupLayout"),
    ("GPURenderPipeline", "label"),
    ("GPUCommandEncoder", "beginComputePass"),
    ("GPUCommandEncoder", "beginRenderPass"),
    ("GPUCommandEncoder", "copyBufferToBuffer"),
    ("GPUCommandEncoder", "copyTextureToBuffer"),
    ("GPUCommandEncoder", "finish"),
    ("GPUCommandEncoder", "label"),
    ("GPUComputePassEncoder", "setPipeline"),
    ("GPUComputePassEncoder", "setBindGroup"),
    ("GPUComputePassEncoder", "dispatchWorkgroups"),
    ("GPUComputePassEncoder", "end"),
    ("GPUComputePassEncoder", "label"),
    ("GPURenderPassEncoder", "setPipeline"),
    ("GPURenderPassEncoder", "setBindGroup"),
    ("GPURenderPassEncoder", "draw"),
    ("GPURenderPassEncoder", "end"),
    ("GPURenderPassEncoder", "executeBundles"),
    ("GPURenderPassEncoder", "setViewport"),
    ("GPURenderPassEncoder", "setScissorRect"),
    ("GPURenderPassEncoder", "label"),
    ("GPURenderBundleEncoder", "setPipeline"),
    ("GPURenderBundleEncoder", "draw"),
    ("GPURenderBundleEncoder", "finish"),
    ("GPURenderBundleEncoder", "label"),
    ("GPURenderBundle", "label"),
    ("GPUSampler", "label"),
    ("GPUBindGroup", "label"),
    ("GPUBindGroupLayout", "label"),
    ("GPUCommandBuffer", "label"),
    ("GPUCanvasContext", "configure"),
    ("GPUCanvasContext", "getCurrentTexture"),
    ("GPUCanvasContext", "canvas"),
    ("GPUMapMode", "READ"),
    ("GPUBufferUsage", "COPY_DST"),
    ("GPUBufferUsage", "COPY_SRC"),
    ("GPUBufferUsage", "STORAGE"),
    ("GPUBufferUsage", "MAP_READ"),
    ("GPUBufferUsage", "MAP_WRITE"),
    ("GPUTextureUsage", "RENDER_ATTACHMENT"),
    ("GPUTextureUsage", "COPY_SRC"),
    ("GPUTextureUsage", "COPY_DST"),
    ("GPUTextureUsage", "TEXTURE_BINDING"),
    ("GPUShaderStage", "COMPUTE"),
    ("GPUShaderStage", "VERTEX"),
    ("GPUShaderStage", "FRAGMENT"),
}

MEMBER_PARTIAL = {
    ("GPUDevice", "createPipelineLayout"),
    ("GPUDevice", "createQuerySet"),
    ("GPUDevice", "createRenderPipelineAsync"),
    ("GPUDevice", "destroy"),
    ("GPUDevice", "pushErrorScope"),
    ("GPUDevice", "popErrorScope"),
    ("GPUDevice", "addEventListener"),
    ("GPUDevice", "removeEventListener"),
    ("GPUDevice", "adapterInfo"),
    ("GPUDevice", "lost"),
    ("GPUDevice", "onuncapturederror"),
    ("GPUBuffer", "mapState"),
    ("GPUComputePassEncoder", "dispatchWorkgroupsIndirect"),
    ("GPURenderPassEncoder", "drawIndexed"),
    ("GPURenderPassEncoder", "drawIndirect"),
    ("GPURenderPassEncoder", "drawIndexedIndirect"),
    ("GPURenderPassEncoder", "setVertexBuffer"),
    ("GPURenderPassEncoder", "setIndexBuffer"),
    ("GPURenderPassEncoder", "setBlendConstant"),
    ("GPURenderPassEncoder", "setStencilReference"),
    ("GPURenderPassEncoder", "beginOcclusionQuery"),
    ("GPURenderPassEncoder", "endOcclusionQuery"),
    ("GPURenderPassEncoder", "insertDebugMarker"),
    ("GPURenderPassEncoder", "pushDebugGroup"),
    ("GPURenderPassEncoder", "popDebugGroup"),
    ("GPURenderBundleEncoder", "drawIndexed"),
    ("GPURenderBundleEncoder", "drawIndirect"),
    ("GPURenderBundleEncoder", "drawIndexedIndirect"),
    ("GPURenderBundleEncoder", "setBindGroup"),
    ("GPURenderBundleEncoder", "setVertexBuffer"),
    ("GPURenderBundleEncoder", "setIndexBuffer"),
    ("GPURenderBundleEncoder", "insertDebugMarker"),
    ("GPURenderBundleEncoder", "pushDebugGroup"),
    ("GPURenderBundleEncoder", "popDebugGroup"),
    ("GPUCommandEncoder", "copyBufferToTexture"),
    ("GPUCommandEncoder", "copyTextureToTexture"),
    ("GPUCommandEncoder", "clearBuffer"),
    ("GPUCommandEncoder", "resolveQuerySet"),
    ("GPUCommandEncoder", "insertDebugMarker"),
    ("GPUCommandEncoder", "pushDebugGroup"),
    ("GPUCommandEncoder", "popDebugGroup"),
    ("GPUComputePassEncoder", "insertDebugMarker"),
    ("GPUComputePassEncoder", "pushDebugGroup"),
    ("GPUComputePassEncoder", "popDebugGroup"),
    ("GPUCanvasContext", "unconfigure"),
    ("GPUCanvasContext", "getConfiguration"),
    ("GPUQueue", "copyExternalImageToTexture"),
    ("GPUMapMode", "WRITE"),
    ("GPUBufferUsage", "INDEX"),
    ("GPUBufferUsage", "INDIRECT"),
    ("GPUBufferUsage", "VERTEX"),
    ("GPUBufferUsage", "UNIFORM"),
    ("GPUBufferUsage", "QUERY_RESOLVE"),
    ("GPUTextureUsage", "STORAGE_BINDING"),
    ("GPUTextureUsage", "TRANSIENT_ATTACHMENT"),
}

# ---------------------------------------------------------------------------
# String unions exercised in browser tests
# ---------------------------------------------------------------------------

STRING_UNION_IMPLEMENTED = {
    "GPUAutoLayoutMode",
    "GPULoadOp",
    "GPUStoreOp",
    "GPUPrimitiveTopology",
    "GPUFilterMode",
    "GPUCanvasAlphaMode",
    "GPUTextureDimension",
}

STRING_UNION_PARTIAL = {
    "GPUAddressMode",
    "GPUBlendFactor",
    "GPUBlendOperation",
    "GPUBufferBindingType",
    "GPUBufferMapState",
    "GPUCompareFunction",
    "GPUCullMode",
    "GPUFrontFace",
    "GPUIndexFormat",
    "GPUMipmapFilterMode",
    "GPUTextureAspect",
    "GPUTextureFormat",
    "GPUTextureSampleType",
    "GPUTextureViewDimension",
    "GPUVertexFormat",
    "GPUVertexStepMode",
    "GPUFeatureName",
    "GPUPowerPreference",
    "GPUQueryType",
    "GPUSamplerBindingType",
    "GPUStencilOperation",
    "GPUStorageTextureAccess",
    "GPUErrorFilter",
}

STRING_VALUE_IMPLEMENTED = {
    ("GPUAutoLayoutMode", "auto"),
    ("GPULoadOp", "clear"),
    ("GPULoadOp", "load"),
    ("GPUStoreOp", "store"),
    ("GPUStoreOp", "discard"),
    ("GPUPrimitiveTopology", "triangle-list"),
    ("GPUFilterMode", "nearest"),
    ("GPUFilterMode", "linear"),
    ("GPUCanvasAlphaMode", "opaque"),
    ("GPUCanvasAlphaMode", "premultiplied"),
    ("GPUTextureDimension", "2d"),
    ("GPUTextureFormat", "rgba8unorm"),
    ("GPUTextureFormat", "bgra8unorm"),
    ("GPUTextureFormat", "rgba8unorm-srgb"),
    ("GPUTextureFormat", "bgra8unorm-srgb"),
    ("GPUBufferBindingType", "storage"),
    ("GPUBufferBindingType", "uniform"),
    ("GPUTextureSampleType", "float"),
    ("GPUTextureViewDimension", "2d"),
    ("GPUTextureAspect", "all"),
}


def get_browser(row):
    return row.setdefault("browser", {})


def update_interface(row):
    name = row["name"]
    all_implemented = INTERFACE_IMPLEMENTED | DICT_IMPLEMENTED
    all_partial = INTERFACE_PARTIAL | DICT_PARTIAL
    browser = get_browser(row)
    status = browser.get("impl", "unreviewed")

    if name in all_implemented:
        if status in ("unreviewed", "partial", "not_wired"):
            browser["impl"] = "implemented"
            browser["notes"] = ["Verified via Playwright browser smoke and layered bench."]
            if browser.get("correct", "unreviewed") == "unreviewed":
                browser["correct"] = "integration"
            if browser.get("perf", "unreviewed") == "unreviewed":
                browser["perf"] = "diagnostic"
    elif name in all_partial:
        if status in ("unreviewed", "not_wired"):
            browser["impl"] = "partial"
            browser["notes"] = ["Runtime implements but browser test coverage is incomplete."]
            if browser.get("correct", "unreviewed") == "unreviewed":
                browser["correct"] = "integration"


def update_member(row):
    key = (row["parent"], row["name"])
    browser = get_browser(row)
    status = browser.get("impl", "unreviewed")

    if key in MEMBER_IMPLEMENTED:
        if status in ("unreviewed", "partial", "not_wired"):
            browser["impl"] = "implemented"
            if browser.get("correct", "unreviewed") == "unreviewed":
                browser["correct"] = "integration"
            if browser.get("perf", "unreviewed") == "unreviewed":
                browser["perf"] = "diagnostic"
    elif key in MEMBER_PARTIAL:
        if status in ("unreviewed", "not_wired"):
            browser["impl"] = "partial"
            browser["notes"] = ["Runtime supports; browser test not yet exercised."]


def update_union(row):
    name = row["name"]
    browser = get_browser(row)
    status = browser.get("impl", "unreviewed")

    if name in STRING_UNION_IMPLEMENTED:
        if status in ("unreviewed", "partial", "not_wired"):
            browser["impl"] = "implemented"
            browser["notes"] = ["Exercised in browser Playwright tests."]
            if browser.get("correct", "unreviewed") == "unreviewed":
                browser["correct"] = "integration"
            if browser.get("perf", "unreviewed") == "unreviewed":
                browser["perf"] = "not_meaningful"
    elif name in STRING_UNION_PARTIAL:
        if status in ("unreviewed", "not_wired"):
            browser["impl"] = "partial"
            browser["notes"] = ["Some values exercised in browser tests; full coverage pending."]
            if browser.get("correct", "unreviewed") == "unreviewed":
                browser["correct"] = "integration"


def update_value(row):
    key = (row["parent"], row["name"])
    browser = get_browser(row)
    status = browser.get("impl", "unreviewed")

    if key in STRING_VALUE_IMPLEMENTED:
        if status in ("unreviewed", "partial", "not_wired"):
            browser["impl"] = "implemented"
            if browser.get("correct", "unreviewed") == "unreviewed":
                browser["correct"] = "integration"
            if browser.get("perf", "unreviewed") == "unreviewed":
                browser["perf"] = "not_meaningful"


def count_browser_statuses(rows):
    counts = {}
    for row in rows:
        kind = row.get("kind")
        if kind in ("interface", "member", "union", "value"):
            s = row.get("browser", {}).get("impl", "unreviewed")
            counts[s] = counts.get(s, 0) + 1
    return counts


def main():
    with open(SPEC_INDEX_PATH) as f:
        rows = [json.loads(line) for line in f]

    print("Before update:")
    before = count_browser_statuses(rows)
    for s, c in sorted(before.items()):
        print(f"  {s}: {c}")

    for row in rows:
        kind = row.get("kind")
        if kind == "header":
            row["lastUpdated"] = "2026-03-17"
        elif kind == "interface":
            update_interface(row)
        elif kind == "member":
            update_member(row)
        elif kind == "union":
            update_union(row)
        elif kind == "value":
            update_value(row)

    print("\nAfter update:")
    after = count_browser_statuses(rows)
    for s, c in sorted(after.items()):
        print(f"  {s}: {c}")

    with open(SPEC_INDEX_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")

    print(f"\nBrowser spec index updated in {SPEC_INDEX_PATH}")


if __name__ == "__main__":
    main()
